"""Unit conversions at package and correlation boundaries; historical factors retained.

The ``*_to_*`` functions convert at correlation boundaries that use US or laboratory units.
``_UNITS`` is the single table of public data units: every unit maps to its SI unit, a scale
and an offset, ``si = value * scale + offset``. ``to_si``, ``convert``, ``value_in_si``,
``si_unit``, ``names``, ``parse``, ``fits`` and the unit sets of ``Profile`` and ``Stream`` all
read it. ``define_quantity`` records the SI unit of each named quantity (the types package calls
it once per quantity), so ``names(quantity)`` and ``fits(unit, quantity)`` need no upward import.

Each conversion factor is declared once, as a named module constant below, and both the table
and the converters read that constant. A converter whose body equals that of another quantity's
converter (``kgh_to_kgs`` and ``m3h_to_m3s``) is an alias of it.

Validity: every converter is valid for any finite number; the argument is returned scaled (and
offset for temperatures), with no range check. Source: NIST Special Publication 811 (2008) for
the exact definitions (bar, inch, foot, psi, hour, degree Celsius). Where a value is a retained
number of the original GEMINI (the millidarcy, barrel per day, foot of head, brake horsepower,
lbm/ft3 and psi factors), that historical factor is kept bit for bit, whatever its digits.

The converters are not decorated with ``@ops.physics``: they sit on the hot path of every
binding and plain operators work on every backend, so the registry wrapper would only add cost.
"""

import math
import re
from dataclasses import dataclass

import numpy as np

from gemini.errors import ValidationError
from gemini.utils.strings import close_matches, did_you_mean, join_names

KILO = 1000
MEGA = 1e6
GIGA = 1e9
MILLI = 1e-3
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
SECONDS_PER_YEAR = 365.25 * SECONDS_PER_DAY
ZERO_CELSIUS = 273.15
"""Temperature [K] of 0 degC."""
PA_PER_BAR = 1e5
PA_PER_KPA = 1e3
STANDARD_ATMOSPHERE = 101325
"""Standard atmosphere [Pa], the offset of gauge pressure."""
JOULES_PER_KWH = 3.6e6
M_PER_INCH = 0.0254
M_PER_FOOT = 0.3048
FAHRENHEIT_PER_KELVIN = 1.8
FAHRENHEIT_OFFSET = 32
PSI_PER_BAR = 14.503774
M2_PER_MILLIDARCY = 9.869233e-16
BBL_PER_DAY_PER_M3S = 543439.650564
PA_PER_FOOT_HEAD = 2988.30167
W_PER_BHP = 745.7
KGM3_PER_LBMFT3 = 1.601846e1
HALF_TURN_DEGREES = 180
MOL_M3_PA_PER_MOL_L_BAR = 0.01
API_VELOCITY_FACTOR = 0.3048 / math.sqrt(0.0283 / 0.454)

__all__ = ["Quantity", "names", "parse", "convert", "fits"]


def bar_to_pa(x: float) -> float:
    """Convert [bar] to [Pa]: ``x * 1e5``."""
    return x * PA_PER_BAR


def pa_to_bar(x: float) -> float:
    """Convert [Pa] to [bar]: ``x / 1e5``."""
    return x / PA_PER_BAR


m3s_per_bar_to_si = pa_to_bar
"""Convert the historical runtime's [m3/s/bar] index to [m3/s/Pa]: ``x / 1e5``."""


def c_to_k(x: float) -> float:
    """Convert [degC] to [K]: ``x + 273.15``."""
    return x + ZERO_CELSIUS


def k_to_c(x: float) -> float:
    """Convert [K] to [degC]: ``x - 273.15``."""
    return x - ZERO_CELSIUS


def m3h_to_m3s(x: float) -> float:
    """Convert [m3/h] to [m3/s]: ``x / 3600``."""
    return x / SECONDS_PER_HOUR


kgh_to_kgs = m3h_to_m3s
"""Convert [kg/h] to [kg/s]: ``x / 3600``."""


def m3s_to_m3h(x: float) -> float:
    """Convert [m3/s] to [m3/h]: ``x * 3600``."""
    return x * SECONDS_PER_HOUR


def md_to_m2(x: float) -> float:
    """Convert [mD] to [m2]: ``x * 9.869233e-16``."""
    return x * M2_PER_MILLIDARCY


def m2_to_md(x: float) -> float:
    """Convert [m2] to [mD]: ``x / 9.869233e-16``."""
    return x / M2_PER_MILLIDARCY


def m3s_to_bbl_per_day(x: float) -> float:
    """Convert [m3/s] to [bbl/day]: ``x * 543439.650564``."""
    return x * BBL_PER_DAY_PER_M3S


def bbl_per_day_to_m3s(x: float) -> float:
    """Convert [bbl/day] to [m3/s]: ``x / 543439.650564``."""
    return x / BBL_PER_DAY_PER_M3S


def ft_head_to_pa(x: float) -> float:
    """Convert [ft head] to [Pa]: ``x * 2988.30167``."""
    return x * PA_PER_FOOT_HEAD


def pa_to_ft_head(x: float) -> float:
    """Convert [Pa] to [ft head]: ``x / 2988.30167``."""
    return x / PA_PER_FOOT_HEAD


def bhp_to_w(x: float) -> float:
    """Convert [bhp] to [W]: ``x * 745.7``."""
    return x * W_PER_BHP


def w_to_bhp(x: float) -> float:
    """Convert [W] to [bhp]: ``x / 745.7``."""
    return x / W_PER_BHP


def m_to_ft(x: float) -> float:
    """Convert [m] to [ft]: ``x / 0.3048``."""
    return x / M_PER_FOOT


def ft_to_m(x: float) -> float:
    """Convert [ft] to [m]: ``x * 0.3048``."""
    return x * M_PER_FOOT


def kgm3_to_lbmft3(x: float) -> float:
    """Convert [kg/m3] to [lbm/ft3]: ``x / 16.01846``."""
    return x / KGM3_PER_LBMFT3


def lbmft3_to_kgm3(x: float) -> float:
    """Convert [lbm/ft3] to [kg/m3]: ``x * 16.01846``."""
    return x * KGM3_PER_LBMFT3


def pas_to_cp(x: float) -> float:
    """Convert [Pa s] to [cP]: ``x / 1e-3``."""
    return x / MILLI


nm_to_dyne_cm = pas_to_cp
"""Convert [N/m] to [dyne/cm]: ``x / 1e-3``."""


def cp_to_pas(x: float) -> float:
    """Convert [cP] to [Pa s]: ``x * 1e-3``."""
    return x * MILLI


dyne_cm_to_nm = cp_to_pas
"""Convert [dyne/cm] to [N/m]: ``x * 1e-3``."""


def inch_to_m(x: float) -> float:
    """Convert [inch] to [m]: ``x * 0.0254``."""
    return x * M_PER_INCH


def m_to_inch(x: float) -> float:
    """Convert [m] to [inch]: ``x / 0.0254``."""
    return x / M_PER_INCH


def m_to_mm(x: float) -> float:
    """Convert [m] to [mm]: ``x * 1000``."""
    return x * KILO


kgm3_to_mgl = m_to_mm
"""Convert [kg/m3] to [mg/l]: ``x * 1000``."""


def mm_to_m(x: float) -> float:
    """Convert [mm] to [m]: ``x / 1000``."""
    return x / KILO


mgl_to_kgm3 = mm_to_m
"""Convert [mg/l] to [kg/m3]: ``x / 1000``."""


def m3s_to_m3day(x: float) -> float:
    """Convert [m3/s] to [m3/day]: ``x * 86400``."""
    return x * SECONDS_PER_DAY


def m3day_to_m3s(x: float) -> float:
    """Convert [m3/day] to [m3/s]: ``x / 86400``."""
    return x / SECONDS_PER_DAY


def index_to_si(x: float) -> float:
    """Convert [m3/h/bar] to [m3/s/Pa]: ``x / 3600 / 1e5``."""
    return x / SECONDS_PER_HOUR / PA_PER_BAR


def index_from_si(x: float) -> float:
    """Convert [m3/s/Pa] to [m3/h/bar]: ``x * 3600 * 1e5``."""
    return x * SECONDS_PER_HOUR * PA_PER_BAR


def c_to_f(x: float) -> float:
    """Convert [degC] to [degF]: ``x * 1.8 + 32``."""
    return x * FAHRENHEIT_PER_KELVIN + FAHRENHEIT_OFFSET


def bar_to_psi(x: float) -> float:
    """Convert [bar] to [psi]: ``x * 14.503774``."""
    return x * PSI_PER_BAR


def pa_to_gpa(x: float) -> float:
    """Convert [Pa] to [GPa]: ``x / 1e9``."""
    return x / GIGA


def gpa_to_pa(x: float) -> float:
    """Convert [GPa] to [Pa]: ``x * 1e9``."""
    return x * GIGA


def rad_to_deg(x: float) -> float:
    """Convert [rad] to [deg]: ``x * 180 / pi``."""
    return x * HALF_TURN_DEGREES / math.pi


def deg_to_rad(x: float) -> float:
    """Convert [deg] to [rad]: ``x * pi / 180``."""
    return x * math.pi / HALF_TURN_DEGREES


def m2_to_mm2(x: float) -> float:
    """Convert [m2] to [mm2]: ``x * 1e6``."""
    return x * MEGA


def ms_to_mm_year(x: float) -> float:
    """Convert penetration speed [m/s] to [mm/year]: ``x * 1000 * 31557600``."""
    return x * KILO * SECONDS_PER_YEAR


def mol_l_bar_to_mol_m3_pa(x: float) -> float:
    """Convert Henry solubility constant [mol/l/bar] to [mol/m3/Pa]: ``x * 0.01``."""
    return x * MOL_M3_PA_PER_MOL_L_BAR


_UNITS = {
    "Pa": ("Pa", 1, 0),
    "bar": ("Pa", PA_PER_BAR, 0),
    "barg": ("Pa", PA_PER_BAR, STANDARD_ATMOSPHERE),
    "bar(g)": ("Pa", PA_PER_BAR, STANDARD_ATMOSPHERE),
    "kPa": ("Pa", PA_PER_KPA, 0),
    "MPa": ("Pa", MEGA, 0),
    "K": ("K", 1, 0),
    "degC": ("K", 1, ZERO_CELSIUS),
    "C": ("K", 1, ZERO_CELSIUS),
    "°C": ("K", 1, ZERO_CELSIUS),
    "m3/s": ("m3/s", 1, 0),
    "m3/h": ("m3/s", 1 / SECONDS_PER_HOUR, 0),
    "l/s": ("m3/s", MILLI, 0),
    "kg/s": ("kg/s", 1, 0),
    "t/h": ("kg/s", KILO / SECONDS_PER_HOUR, 0),
    "Hz": ("Hz", 1, 0),
    "rpm": ("Hz", 1 / SECONDS_PER_MINUTE, 0),
    "W": ("W", 1, 0),
    "kW": ("W", KILO, 0),
    "MW": ("W", MEGA, 0),
    "J": ("J", 1, 0),
    "kWh": ("J", JOULES_PER_KWH, 0),
    "currency": ("currency", 1, 0),
    "currency/year": ("currency/year", 1, 0),
    "currency/J": ("currency/J", 1, 0),
    "currency/kWh": ("currency/J", 1 / JOULES_PER_KWH, 0),
    "currency/s": ("currency/s", 1, 0),
    "currency/h": ("currency/s", 1 / SECONDS_PER_HOUR, 0),
    "m": ("m", 1, 0),
    "km": ("m", KILO, 0),
    "mm": ("m", MILLI, 0),
    "in": ("m", M_PER_INCH, 0),
    "ft": ("m", M_PER_FOOT, 0),
    "s": ("s", 1, 0),
    "min": ("s", SECONDS_PER_MINUTE, 0),
    "h": ("s", SECONDS_PER_HOUR, 0),
    "d": ("s", SECONDS_PER_DAY, 0),
    "m/s": ("m/s", 1, 0),
    "m2": ("m2", 1, 0),
    "m3": ("m3", 1, 0),
    "rad": ("rad", 1, 0),
    "kg/m3": ("kg/m3", 1, 0),
    "g/m3": ("kg/m3", MILLI, 0),
    "mg/l": ("kg/m3", MILLI, 0),
    "Pa.s": ("Pa.s", 1, 0),
    "J/kg/K": ("J/kg/K", 1, 0),
    "J/kg": ("J/kg", 1, 0),
    "kJ/kg": ("J/kg", KILO, 0),
    "J/K": ("J/K", 1, 0),
    "kWh/K": ("J/K", JOULES_PER_KWH, 0),
    "J/m3/K": ("J/m3/K", 1, 0),
    "MJ/m3/K": ("J/m3/K", MEGA, 0),
    "m2/s": ("m2/s", 1, 0),
    "W/m": ("W/m", 1, 0),
    "m.K/W": ("m.K/W", 1, 0),
    "K/m": ("K/m", 1, 0),
    "K/km": ("K/m", MILLI, 0),
    "kg": ("kg", 1, 0),
    "t": ("kg", KILO, 0),
    "m3/s/Pa^0.5": ("m3/s/Pa^0.5", 1, 0),
    "m3/h/bar^0.5": ("m3/s/Pa^0.5", 1 / SECONDS_PER_HOUR / PA_PER_BAR**0.5, 0),
    "W/m/K": ("W/m/K", 1, 0),
    "W/m2/K": ("W/m2/K", 1, 0),
    "W/K": ("W/K", 1, 0),
    "m3/s/Pa": ("m3/s/Pa", 1, 0),
    "m3/h/bar": ("m3/s/Pa", 1 / SECONDS_PER_HOUR / PA_PER_BAR, 0),
    "-": ("-", 1, 0),
    "ppm": ("-", 1e-6, 0),
}

_NUMBER_AND_UNIT = re.compile(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+(.+?)\s*")


_QUANTITY_UNITS = {}


@dataclass(frozen=True)
class Quantity:
    """A scalar and unit accepted at public API boundaries."""

    value: float
    unit: str


def _entry(unit, path="units"):
    """Return ``(si_unit, scale, offset)`` of a known unit."""
    if unit not in _UNITS:
        raise ValidationError(
            f"{path}: unit = {unit!r}; expected a known unit{did_you_mean(unit, _UNITS)}",
            code="invalid_unit",
        )
    return _UNITS[unit]


def _offset(unit, quantity):
    """Return the offset of ``unit``, or zero for a ``*_difference`` quantity.

    A difference of 10 degC is a difference of 10 K, and a pressure difference in barg equals
    the same difference in bar, so differences convert by scale only.
    """
    if quantity is not None and quantity.endswith("_difference"):
        return 0
    return _UNITS[unit][2]


def si_unit(unit):
    """Return the SI unit that ``unit`` converts to, or ``None`` for an unknown unit."""
    entry = _UNITS.get(unit)
    return entry[0] if entry else None


def si_conversion(unit, quantity=None):
    """Return ``(scale, offset)`` with ``to_si(value) == float(value) * scale + offset``.

    Array code converts a whole column with the same two numbers, which gives the bits of the
    scalar conversion row by row.
    """
    _, scale, _ = _entry(unit, "units.si_conversion")
    return scale, _offset(unit, quantity)


def to_si(value: float, unit: str, quantity: str | None = None) -> float:
    """Convert a bound scalar to SI; volume flow remains [m3/s] until density is known."""
    scale, offset = si_conversion(unit, quantity)
    return float(value) * scale + offset


def array_to_si(values, unit, quantity=None):
    """Convert an array-like of ``unit`` values to SI, element for element as ``to_si`` does."""
    scale, offset = si_conversion(unit, quantity)
    return np.asarray(values, dtype=float) * scale + offset


def array_convert(values, from_unit, to_unit, quantity=None):
    """Convert an array-like between units of one dimension, element for element as ``convert``."""
    si = array_to_si(values, from_unit, quantity)
    return (si - _offset(to_unit, quantity)) / _entry(to_unit, "units.convert")[1]


def split_quantity(value):
    """Return ``(number, unit)`` for a ``Quantity`` or ``"<number> <unit>"`` text.

    Any other value, including text that is not a number followed by a unit, returns
    ``(value, None)``.
    """
    if isinstance(value, Quantity):
        return value.value, value.unit
    if isinstance(value, str):
        match = _NUMBER_AND_UNIT.fullmatch(value)
        if match is not None:
            return float(match.group(1)), match.group(2)
    return value, None


def value_in_si(value, expected_unit=None, path="value", quantity=None):
    """Convert a unit string or ``Quantity`` to a declaration's SI unit.

    Values without a unit, and every value of a declaration without a unit, pass unchanged.
    ``quantity`` names the declared quantity so that differences ignore unit offsets.
    """
    number, supplied = split_quantity(value)
    if supplied is None or expected_unit is None:
        return value
    if _entry(supplied, path)[0] != expected_unit:
        raise ValidationError(
            f"{path}: unit = {supplied!r}; expected a unit of {expected_unit!r}",
            code="invalid_unit",
        )
    return to_si(number, supplied, quantity)


def convert(value, from_unit, to_unit, quantity=None):
    """Convert a scalar between units of the same dimension through SI.

    A unit converts to itself even when it is not in the unit table. ``quantity`` names the
    declared quantity so that differences ignore unit offsets.
    """
    if from_unit == to_unit and from_unit not in _UNITS:
        return value
    source, target = _entry(from_unit, "units.convert"), _entry(to_unit, "units.convert")
    if source[0] != target[0]:
        raise ValidationError(
            f"units.convert: unit = {to_unit!r}; expected a unit of {source[0]!r} "
            f"to convert from {from_unit!r}",
            code="invalid_unit",
        )
    si = to_si(value, from_unit, quantity)
    return (si - _offset(to_unit, quantity)) / target[1]


def define_quantity(name, unit):
    """Record that the quantity ``name`` is stored in the SI unit ``unit``.

    Defining a name again with the same unit changes nothing; another unit raises
    ``ValidationError``.
    """
    known = _QUANTITY_UNITS.setdefault(name, unit)
    if known != unit:
        raise ValidationError(
            f"units.define_quantity: quantity {name!r} = {unit!r}; already {known!r}",
            code="invalid_unit",
        )


def _quantity_si_unit(quantity):
    """Return the SI unit of a named quantity, or raise with the closest names."""
    if quantity not in _QUANTITY_UNITS:
        raise ValidationError(
            f"units: quantity = {quantity!r}; expected one of "
            f"{join_names(sorted(_QUANTITY_UNITS))}{did_you_mean(quantity, _QUANTITY_UNITS)}",
            suggestions=close_matches(quantity, _QUANTITY_UNITS),
            code="unknown_name",
        )
    return _QUANTITY_UNITS[quantity]


def family(quantity):
    """Return the first quantity defined with the SI unit of ``quantity``, the head of its family.

    ``power`` for ``duty`` or ``electricity``, ``pressure`` for ``pressure_difference``,
    ``temperature`` for ``temperature_difference`` and ``length`` for ``elevation``.
    """
    target = _quantity_si_unit(quantity)
    return next(name for name, unit in _QUANTITY_UNITS.items() if unit == target)


def names(quantity=None):
    """Return the sorted unit names, or those of one quantity such as ``"pressure"``.

    Every unit name returned converts with ``convert``; an unknown quantity raises
    ``ValidationError`` with the closest names.
    """
    if quantity is None:
        return sorted(_UNITS)
    target = _quantity_si_unit(quantity)
    return sorted(unit for unit, entry in _UNITS.items() if entry[0] == target)


def parse(text):
    """Return ``(value, unit)`` of ``"<number> <unit>"`` text such as ``"150 m3/h"``.

    The value stays in the given unit; the unit must be known. Text that is not a number and a
    unit separated by a space raises ``ValidationError``.
    """
    value, unit = split_quantity(text)
    if unit is None:
        raise ValidationError(
            f"units.parse: text = {text!r}; expected '<number> <unit>', e.g. '150 m3/h'",
            code="invalid_unit",
        )
    _entry(unit, "units.parse")
    return value, unit


def fits(unit, quantity):
    """Whether ``unit`` is a known unit of the named ``quantity`` (``"pressure"``, ``"power"``).

    An unknown unit does not fit; an unknown quantity raises ``ValidationError``.
    """
    return si_unit(unit) == _quantity_si_unit(quantity)
