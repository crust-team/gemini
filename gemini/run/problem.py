"""One problem: the demand, the site, the constraints and the assumptions of a plant's run."""

from copy import deepcopy
from fnmatch import fnmatchcase

import numpy as np

from gemini import units
from gemini._utils.strings import join_path
from gemini.errors import ValidationError
from gemini.run._utils import demand as demand_frame
from gemini.run.assumptions import CARRIERS, Assumptions
from gemini.run.constraint import Constraint


class Problem:
    """What a plant is asked to do, in one object: every call takes ``(plant, problem)``.

    Parameters
    ----------
    demand : DataFrame
        The run input of ``gm.data.from_csv`` or ``from_values``, or several joined: any constant
        step and length.
    site : dict, optional
        Values of the plant parameters that describe the site, keyed by parameter path with ``*``,
        with their units: ``{"d*.gradient": "30 K/km", "d*.surface_temperature": "12 degC"}``.
    constraints : list of Constraint, optional
        The limits of the run.
    assumptions : Assumptions, optional
        Rates, prices and cost factors.

    Raises
    ------
    ValidationError
        ``invalid_value`` for an argument of another type or a price profile that is not on the
        demand index, ``invalid_unit`` for a site value with an unknown unit, and what
        ``gm.data.from_csv`` raises for a demand.
    """

    def __init__(self, demand, site=None, constraints=None, assumptions=None):
        """Validate the four parts; a part left out is empty."""
        self.demand = demand_frame.from_frame(demand)
        self.site = _checked_site({} if site is None else site)
        self.constraints = _checked_constraints([] if constraints is None else constraints)
        self.assumptions = Assumptions() if assumptions is None else assumptions
        if not isinstance(self.assumptions, Assumptions):
            raise ValidationError(
                f"problem: assumptions = {type(assumptions).__name__}; expected a gm.Assumptions",
                path="assumptions",
                code="invalid_value",
            )
        _check_price_profiles(self.assumptions, len(self.demand))

    def apply_site(self, plant):
        """Return a copy of ``plant`` with the site values, or ``plant`` when there are none.

        ``plant`` itself never changes. A pattern that matches no parameter raises ``unknown_name``
        and a parameter the plant states too raises ``conflicting_value`` naming the path.
        """
        if not self.site:
            return plant
        values = _site_values(plant, self.site)
        sited = deepcopy(plant)
        for path, params in sorted(values.items(), key=lambda item: item[0].count(".")):
            sited.set_params(path, params)
        return sited

    def to_dict(self):
        """Return the problem as plain data, the demand in the shape ``from_values`` takes."""
        return {
            "demand": demand_frame.to_dict(self.demand),
            "site": dict(self.site),
            "constraints": [constraint.to_dict() for constraint in self.constraints],
            "assumptions": self.assumptions.to_dict(),
        }

    @classmethod
    def from_dict(cls, data):
        """Return the problem of a dictionary of ``to_dict``."""
        unknown = [name for name in data if name not in cls.schema()["properties"]]
        if "demand" not in data or unknown:
            raise ValidationError(
                f"problem: keys = {sorted(data)}; expected demand, site, constraints, assumptions",
                path="demand" if "demand" not in data else unknown[0],
                code="missing_value" if "demand" not in data else "unknown_name",
            )
        return cls(
            demand_frame.from_dict(data["demand"]),
            data.get("site"),
            [Constraint.from_dict(item) for item in data.get("constraints", [])],
            Assumptions.from_dict(data.get("assumptions", {})),
        )

    @classmethod
    def schema(cls):
        """Return the JSON Schema (draft 2020-12) of ``to_dict``."""
        number_or_text = {"type": ["number", "string"]}
        demand = {
            "type": "object",
            "required": ["start", "step", "units", "values"],
            "properties": {
                "start": {"type": "string"},
                "step": {"type": ["number", "string"]},
                "units": {"type": "object"},
                "quantities": {"type": "object"},
                "values": {
                    "type": "object",
                    "additionalProperties": {"type": "array", "items": {"type": "number"}},
                },
            },
        }
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Problem",
            "type": "object",
            "required": ["demand"],
            "additionalProperties": False,
            "properties": {
                "demand": demand,
                "site": {"type": "object", "additionalProperties": number_or_text},
                "constraints": {"type": "array", "items": Constraint.schema()},
                "assumptions": Assumptions.schema(),
            },
        }


def _checked_site(site):
    """Return ``site``, its keys parameter paths and its values numbers or texts with a unit."""
    if not isinstance(site, dict):
        raise ValidationError(
            f"problem: site = {type(site).__name__}; expected a dict of path to value",
            path="site",
            code="invalid_value",
        )
    for path, value in site.items():
        if isinstance(value, str):
            units.si_unit(units.parse(value)[1])
        elif not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError(
                f"problem: site[{path!r}] = {value!r}; expected a number or a text with its unit",
                path=f"site.{path}",
                code="invalid_value",
            )
    return dict(site)


def _matching_modules(plant, pattern):
    """Return the paths of the modules of ``plant`` that fit ``pattern``, name by name."""
    wanted = pattern.split(".")
    return [
        path
        for path, _ in plant.named_modules()
        if len(path.split(".")) == len(wanted) and all(map(fnmatchcase, path.split("."), wanted))
    ]


def _site_values(plant, site):
    """Return ``{module path: {parameter: value}}`` of ``site``, each match checked on its own."""
    values = {}
    for pattern, value in site.items():
        modules, _, name = pattern.rpartition(".")
        found = [
            path
            for path in _matching_modules(plant, modules)
            if name in plant.get_submodule(path)._parameters
        ]
        if not found:
            raise ValidationError(
                f"problem: site path {pattern!r} matches no parameter",
                path=f"site.{pattern}",
                code="unknown_name",
            )
        for path in found:
            if plant.get_submodule(path)._params_at(None).get(name) is not None:
                raise ValidationError(
                    f"problem: site path {pattern!r} sets {join_path(path, name)}, which the "
                    "plant states too; expected one of the two",
                    path=join_path(path, name),
                    code="conflicting_value",
                )
            values.setdefault(path, {})[name] = value
    return values


def _checked_constraints(constraints):
    """Return ``constraints`` as a list, or raise for an item that is no ``Constraint``."""
    for constraint in constraints:
        if not isinstance(constraint, Constraint):
            raise ValidationError(
                f"problem: constraint = {constraint!r}; expected a gm.Constraint",
                path="constraints",
                code="invalid_value",
            )
    return list(constraints)


def _check_price_profiles(assumptions, rows):
    """Raise unless every price profile has one value per row of the demand."""
    for carrier in CARRIERS:
        price = assumptions.price(carrier, required=False)
        if isinstance(price, np.ndarray) and len(price) != rows:
            raise ValidationError(
                f"problem: price of {carrier} has {len(price)} values; expected {rows}, one per "
                "row of the demand",
                path=f"assumptions.prices.{carrier}",
                code="invalid_value",
            )
