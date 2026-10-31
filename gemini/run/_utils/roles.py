"""What each unit of a plant is for: read from the wiring, not from its class.

A unit whose useful outlet feeds the ``HeatingGrid``, directly or through other modules of the
circuit, is a heating unit, and one that feeds the ``CoolingGrid`` a cooling unit. A ``HeatPump`` is
either: its ``sink_out`` heats, and its ``source_out`` cools as a compression chiller. Its condenser
then rejects to a cooler, which is the environment.
"""

from gemini._utils.strings import join_path
from gemini.errors import ValidationError
from gemini.modules.cooling import AbsorptionUnit, AdsorptionChiller
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.heating import HeatPump
from gemini.plants._utils.plan import members

COOLING_KINDS = ("absorption", "adsorption", "compression")
"""The kinds of cooling unit, heat-driven first: the default ``rules["cooling_order"]``."""
HEAT_DRIVEN = ("absorption", "adsorption")
"""The kinds of cooling unit whose drive heat adds to the heat need."""
CHILLERS = {"absorption": AbsorptionUnit, "adsorption": AdsorptionChiller}
"""The class of each heat-driven kind."""


def _reaches(plant, path, port, grid):
    """Return whether the outlet ``path.port`` feeds a module of class ``grid``."""
    fed = plant.feeds(join_path(path, port))
    return any(isinstance(plant.get_submodule(item), grid) for item in fed)


def _one(found, label):
    """Return the only item of ``found``, or ``None``; more than one breaks the design."""
    if len(found) > 1:
        raise ValidationError(
            f"schedule: {len(found)} units of role {label}: {', '.join(found)}; expected at most "
            "one per role and kind",
            code="invalid_design",
        )
    return found[0] if found else None


def heat_pumps(plant):
    """Return ``(heating, cooling)``, the paths of the heat pumps of each role, or ``None``."""
    pumps = [path for path, module in members(plant) if isinstance(module, HeatPump)]
    heating = [path for path in pumps if _reaches(plant, path, "sink_out", HeatingGrid)]
    cooling = [path for path in pumps if _reaches(plant, path, "source_out", CoolingGrid)]
    both = set(heating) & set(cooling)
    if both:
        raise ValidationError(
            f"schedule: {', '.join(sorted(both))} feeds both grids; expected one role, because a "
            "heat pump has one setpoint",
            code="invalid_design",
        )
    return _one(heating, "heating heat pump"), _one(cooling, "compression chiller")


def cooling_units(plant):
    """Return ``{kind: path}`` of the cooling units of ``plant``."""
    units = {"compression": heat_pumps(plant)[1]}
    for kind, chiller in CHILLERS.items():
        found = [
            path
            for path, module in members(plant)
            if isinstance(module, chiller) and _reaches(plant, path, "chilled_out", CoolingGrid)
        ]
        units[kind] = _one(found, f"{kind} chiller")
    return {kind: units[kind] for kind in COOLING_KINDS if units[kind] is not None}
