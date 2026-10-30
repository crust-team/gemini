"""Well performance: nodal analysis, injectivity and the pump head curve."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np

from gemini.analysis.fits import fit_head_correction
from gemini.errors import GeminiError, NotImplementedYet, PhysicsError, ValidationError
from gemini.errors.base import check_on_error
from gemini.modules.plants import nodal as solves
from gemini.modules.pumps import ESP
from gemini.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.modules.wells import ProductionWell
from gemini.physics import constants, units
from gemini.types.shapes import value
from gemini.utils.jsonable import to_plain

CURVE_POINTS = 21
"""Number of rates on the IPR and VLP curves of ``nodal``, from the low to the high bracket end."""


@dataclass(frozen=True)
class _Chain:
    """The production chain of a well: reservoir, lower well, optional ESP and upper well."""

    reservoir: Any
    lower: Any
    esp: Any
    upper: Any


def _chain(plant, well):
    """Return the production chain below the plant path ``well``."""
    module = plant.get_module(well)
    inside = list(module.modules())
    reservoirs = [item for item in inside if isinstance(item, ProductionReservoir)]
    if not reservoirs:
        if any(isinstance(item, InjectionReservoir) for item in inside):
            raise NotImplementedYet(f"nodal: well = {well!r}; injection wells are not solved yet")
        raise ValidationError(
            f"nodal: well = {well!r}; expected a path that holds a ProductionReservoir", path=well
        )
    wells = {item.segment: item for item in inside if isinstance(item, ProductionWell)}
    esps = [item for item in inside if isinstance(item, ESP)]
    if esps and {"below_esp", "above_esp"} <= wells.keys():
        return _Chain(reservoirs[0], wells["below_esp"], esps[0], wells["above_esp"])
    if not esps and "full" in wells:
        return _Chain(reservoirs[0], wells["full"], None, None)
    raise ValidationError(
        f"nodal: well = {well!r}; segments = {sorted(wells)}, ESPs = {len(esps)}; expected one "
        "ProductionWell 'full', or an ESP with the segments 'below_esp' and 'above_esp'",
        code="invalid_design",
    )


def _required(conditions, name):
    if name not in conditions:
        raise ValidationError(
            f"nodal: conditions.{name} is missing; expected it", path=name, code="missing_value"
        )
    return conditions[name]


def _case_inputs(chain, conditions):
    """Return the SI wellhead pressure [Pa], rate bracket [kg/s] and ESP frequency [Hz]."""
    pressure = units.value_in_si(
        _required(conditions, "wellhead_pressure"), "Pa", "conditions.wellhead_pressure", "pressure"
    )
    low, high = (
        units.value_in_si(value, "kg/s", "conditions.rates", "mass_flow")
        for value in _required(conditions, "rates")
    )
    frequency = None
    if chain.esp is not None:
        frequency = units.value_in_si(
            _required(conditions, "frequency"), "Hz", "conditions.frequency", "frequency"
        )
    return float(pressure), (float(low), float(high)), frequency


def _lift(chain, rate):
    """Return the wellhead pressure [Pa] that the well lifts the inflow of ``rate`` to."""
    stream = chain.lower.trial_outlets({"bottom": chain.reservoir.sandface_stream(rate)}).wellhead
    if chain.esp is not None:
        stream = chain.esp.trial_outlets({"suction": stream}).discharge
        stream = chain.upper.trial_outlets({"bottom": stream}).wellhead
    return stream.p


def _curves(chain, pressure, rates):
    """Return the IPR, the VLP and the operating point for a rate bracket."""
    low, high = rates
    sampled = np.linspace(low, high, CURVE_POINTS)
    inflow = [chain.reservoir.sandface_stream(rate).p for rate in sampled]
    lift = [_lift(chain, rate) for rate in sampled]
    ipr = {"rate": value(sampled, "kg/s"), "pressure": value(inflow, "Pa")}
    vlp = {"rate": value(sampled, "kg/s"), "pressure": value(lift, "Pa")}
    rate = solves.solve_production_rate(
        chain.reservoir, chain.lower, pressure, rates, esp=chain.esp, riser=chain.upper
    )
    point = {
        "rate": value(rate, "kg/s"),
        "wellhead_pressure": value(pressure, "Pa"),
        "sandface_pressure": value(chain.reservoir.sandface_stream(rate).p, "Pa"),
    }
    return ipr, vlp, point


def _case(chain, conditions, on_error):
    """Return the curves and the operating point of one set of conditions."""
    case = {
        "conditions": conditions,
        "ipr": None,
        "vlp": None,
        "operating_point": None,
        "error": None,
    }
    try:
        pressure, rates, frequency = _case_inputs(chain, conditions)
        if chain.esp is not None:
            chain.esp.frequency = frequency
        case["ipr"], case["vlp"], case["operating_point"] = _curves(chain, pressure, rates)
    except GeminiError as error:
        if on_error == "raise":
            raise
        case["error"] = error.to_dict()
    return case


def nodal(plant, well, conditions, on_error="raise"):
    """Return the IPR and VLP curves and the operating point of a production well.

    The IPR (inflow performance) is the sandface pressure the reservoir delivers at each rate.
    The VLP (vertical lift performance) is the wellhead pressure the well, the ESP and the riser
    deliver from that inflow at each rate: the node is the wellhead, and the operating point is
    where the VLP falls to the wellhead pressure the surface plant holds. The solve is the one
    of ``plants.nodal.solve_production_rate``. The plant is not changed: the ESP frequency
    of a case is set on a copy.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    well : str
        Dotted path of the module that holds the whole chain, for example ``"doublet"``: one
        ``ProductionReservoir`` and either one full ``ProductionWell`` or an ``ESP`` with the
        ``below_esp`` and ``above_esp`` segments. An injection chain raises
        ``NotImplementedYet``.
    conditions : dict or list of dict
        One case, or several for a what-if. Each has ``wellhead_pressure`` [Pa], ``rates``, the
        ``[low, high]`` bracket [kg/s] of the curves and of the solve (a trial outside the well
        model's domain fails the case), and ``frequency`` [Hz] when the chain has an ESP. Numbers
        are SI; unit strings such as ``"3 bar"`` are accepted.
    on_error : {"raise", "record"}, optional
        A case that fails raises; ``"record"`` puts its problem in ``error`` and runs the others.

    Returns
    -------
    dict
        Plain JSON ``{well, cases}``. Each case holds ``conditions`` as given, ``ipr`` and ``vlp``
        as ``{rate, pressure}``, each a value with 21 points from the low to the high rate,
        ``operating_point`` as ``{rate, wellhead_pressure, sandface_pressure}``, each a value, and
        ``error``. Under ``on_error="record"`` a case whose bracket leaves the well model's domain
        or has no sign change has ``None`` curves and operating point and its problem in ``error``.
    """
    check_on_error(on_error)
    chain_plant = deepcopy(plant)
    chain = _chain(chain_plant, well)
    cases = [conditions] if isinstance(conditions, dict) else list(conditions)
    return to_plain(
        {
            "well": well,
            "cases": [_case(chain, case, on_error) for case in cases],
        }
    )


def injectivity(data, well):
    """Return the Hall integral, its derivative and the skin lines of an injection well.

    Parameters
    ----------
    data : Dataset or DataFrame
        Injection history with a UTC time index: wellhead or bottomhole pressure [Pa] and
        injection rate [m3/s].
    well : str
        Dotted path of the injection well in the plant the data belongs to.

    Returns
    -------
    dict
        Plain JSON with the Hall integral [Pa s], its derivative against cumulative injected
        volume [Pa s/m3] and the fitted skin lines, each with its unit.

    Raises
    ------
    NotImplementedYet
        Always: the Hall analysis is not built yet.
    """
    raise NotImplementedYet("analysis.injectivity")


def _points(measured):
    """Return the measured head points in SI as a list of ``{flow, frequency, head}``."""
    return [
        {
            "flow": float(units.value_in_si(point["flow"], "m3/s", "measured.flow", "volume_flow")),
            "frequency": float(
                units.value_in_si(point["frequency"], "Hz", "measured.frequency", "frequency")
            ),
            "head": float(
                units.value_in_si(point["head"], "Pa", "measured.head", "pressure_difference")
            ),
        }
        for point in measured or ()
    ]


def _correction(points):
    """Return the affine correction of theoretical head on measured head, or why it has none."""
    if not points:
        return value(None, "-", "no measured points")
    try:
        return fit_head_correction(
            [point["head"] for point in points], [point["theoretical_head"] for point in points]
        )
    except PhysicsError as error:
        return value(None, "-", str(error))


def _measured_point(point):
    """Return one measured point with every number as a value."""
    return {
        "flow": value(point["flow"], "m3/s"),
        "frequency": value(point["frequency"], "Hz"),
        "head": value(point["head"], "Pa"),
        "theoretical_head": value(point["theoretical_head"], "Pa"),
    }


def _head_curve(module, frequency, n_points=50):
    """Return plotting points (flow [m3/s], head [Pa]) of an ESP at a frequency [Hz].

    The flows run from zero to twice the speed-scaled maximum flow; the head is evaluated at the
    flow referred to the reference speed.
    """
    if frequency <= 0 or n_points < 2:
        raise ValidationError(
            f"{module.path}: positive frequency and at least two curve points required; got "
            f"frequency = {frequency} Hz, n_points = {n_points}",
            code="invalid_design",
        )
    scale = frequency / constants.ESP_REFERENCE_FREQUENCY
    return [
        (float(flow), module.head_function(flow / scale, frequency))
        for flow in np.linspace(0, 2 * module.maximum_flow * scale, n_points)
    ]


def pump_curve(plant, pump, measured=None):
    """Return an ESP's head curve at the reference frequency and the fit of measured points.

    The curve is the pump's polynomial head curve (``_head_curve``) at the reference
    frequency of 60 Hz, for flows from zero to twice the maximum flow. Head is a pressure
    difference in Pa; the head of a fluid column in metres is ``head / (density * g)`` with the
    density of the pumped fluid.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    pump : str
        Dotted path of an ``ESP``, for example ``"doublet.esp"``.
    measured : list of dict, optional
        Points ``{flow, frequency, head}`` in m3/s, Hz and Pa (unit strings accepted).

    Returns
    -------
    dict
        Plain JSON ``{pump, frequency, curve, measured, correction}``, every number a value.
        ``curve`` is ``{flow, head}``. Each measured point gains ``theoretical_head`` [Pa], the
        pump's head at its flow and frequency. ``correction`` is ``{slope, offset}`` of the
        least-squares line ``theoretical_head = slope * head + offset`` (offset in Pa), or a value
        ``None`` with a ``reason`` when fewer than two distinct measured heads are given. This is
        the retained ``fit_head_correction``; no module applies the correction yet, so it is a
        diagnosis, not a parameter to set.
    """
    module = plant.get_module(pump)
    if not isinstance(module, ESP):
        raise ValidationError(
            f"pump_curve: pump = {pump!r}; expected the path of an ESP", path=pump
        )
    points = _points(measured)
    for point in points:
        point["theoretical_head"] = float(module.head_function(point["flow"], point["frequency"]))
    reference = constants.ESP_REFERENCE_FREQUENCY.value
    flows, heads = zip(*_head_curve(module, reference))
    return {
        "pump": pump,
        "frequency": value(reference, "Hz"),
        "curve": {"flow": value(flows, "m3/s"), "head": value(heads, "Pa")},
        "measured": [_measured_point(point) for point in points],
        "correction": _correction(points),
    }


def calibrate_pump(plant, pump, measured):
    """Return the pump parameters that make the model match measured operation.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    pump : str
        Dotted path of an ``ESP``.
    measured : Dataset or DataFrame
        Operation with bound ``head``, ``power`` or ``discharge_pressure`` columns and at least
        six distinct flows.

    Returns
    -------
    dict
        Plain JSON ``{pump, params, rms_before, rms_after}``, ``params`` ready for
        ``plant.set_params(pump, params)`` (``head_coefficients`` and ``power_coefficients``).

    Raises
    ------
    NotImplementedYet
        Always: it will run ``gm.optim.calibrate`` and report the result in this form.
    """
    raise NotImplementedYet("analysis.calibrate_pump")
