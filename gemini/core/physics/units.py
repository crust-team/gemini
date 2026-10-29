"""Unit conversions at package and correlation boundaries; historical factors retained.

The ``*_to_*`` functions convert at correlation boundaries that use US or laboratory units.
``_UNITS`` is the single table of public data units: every unit maps to its SI unit, a scale
and an offset, ``si = value * scale + offset``. ``to_si``, ``convert``, ``value_in_si``,
``si_unit`` and the unit sets of ``Profile`` and ``Stream`` all read it.
"""

import math
import re
from dataclasses import dataclass

from gemini.errors import UnitError
from gemini.utils.strings import did_you_mean

SECONDS_PER_DAY = 24 * 3600
SECONDS_PER_YEAR = 365.25 * SECONDS_PER_DAY
API_VELOCITY_FACTOR = 0.3048 / math.sqrt(0.0283 / 0.454)


def bar_to_pa(x: float) -> float:
    """Convert [bar] to [Pa]."""
    return x * 1e5


def pa_to_bar(x: float) -> float:
    """Convert [Pa] to [bar]."""
    return x / 1e5


def c_to_k(x: float) -> float:
    """Convert [degC] to [K]."""
    return x + 273.15


def k_to_c(x: float) -> float:
    """Convert [K] to [degC]."""
    return x - 273.15


def m3h_to_m3s(x: float) -> float:
    """Convert [m3/h] to [m3/s]."""
    return x / 3600


def m3s_to_m3h(x: float) -> float:
    """Convert [m3/s] to [m3/h]."""
    return x * 3600


def md_to_m2(x: float) -> float:
    """Convert [mD] to [m2]."""
    return x * 9.869233e-16


def m2_to_md(x: float) -> float:
    """Convert [m2] to [mD]."""
    return x / 9.869233e-16


def m3s_to_bbl_per_day(x: float) -> float:
    """Convert [m3/s] to [bbl/day]."""
    return x * 543439.650564


def bbl_per_day_to_m3s(x: float) -> float:
    """Convert [bbl/day] to [m3/s]."""
    return x / 543439.650564


def ft_head_to_pa(x: float) -> float:
    """Convert [ft head] to [Pa]."""
    return x * 2988.30167


def pa_to_ft_head(x: float) -> float:
    """Convert [Pa] to [ft head]."""
    return x / 2988.30167


def bhp_to_w(x: float) -> float:
    """Convert [bhp] to [W]."""
    return x * 745.7


def w_to_bhp(x: float) -> float:
    """Convert [W] to [bhp]."""
    return x / 745.7


def m_to_ft(x: float) -> float:
    """Convert [m] to [ft]."""
    return x / 3.048e-1


def ft_to_m(x: float) -> float:
    """Convert [ft] to [m]."""
    return x * 3.048e-1


def kgm3_to_lbmft3(x: float) -> float:
    """Convert [kg/m3] to [lbm/ft3]."""
    return x / 1.601846e1


def lbmft3_to_kgm3(x: float) -> float:
    """Convert [lbm/ft3] to [kg/m3]."""
    return x * 1.601846e1


def pas_to_cp(x: float) -> float:
    """Convert [Pa s] to [cP]."""
    return x / 1e-3


def cp_to_pas(x: float) -> float:
    """Convert [cP] to [Pa s]."""
    return x * 1e-3


def nm_to_dyne_cm(x: float) -> float:
    """Convert [N/m] to [dyne/cm]."""
    return x / 1e-3


def dyne_cm_to_nm(x: float) -> float:
    """Convert [dyne/cm] to [N/m]."""
    return x * 1e-3


def inch_to_m(x: float) -> float:
    """Convert [inch] to [m]."""
    return x * 0.0254


def m_to_inch(x: float) -> float:
    """Convert [m] to [inch]."""
    return x / 0.0254


def m_to_mm(x: float) -> float:
    """Convert [m] to [mm]."""
    return x * 1000


def mm_to_m(x: float) -> float:
    """Convert [mm] to [m]."""
    return x / 1000


def m3s_to_m3day(x: float) -> float:
    """Convert [m3/s] to [m3/day]."""
    return x * SECONDS_PER_DAY


def m3day_to_m3s(x: float) -> float:
    """Convert [m3/day] to [m3/s]."""
    return x / SECONDS_PER_DAY


def index_to_si(x: float) -> float:
    """Convert [m3/h/bar] to [m3/s/Pa]."""
    return x / 3600 / 1e5


def index_from_si(x: float) -> float:
    """Convert [m3/s/Pa] to [m3/h/bar]."""
    return x * 3600 * 1e5


def c_to_f(x: float) -> float:
    """Convert [degC] to [degF]."""
    return x * 1.8 + 32


def bar_to_psi(x: float) -> float:
    """Convert [bar] to [psi]."""
    return x * 14.503774


def kgm3_to_mgl(x: float) -> float:
    """Convert [kg/m3] to [mg/l]."""
    return x * 1000


def mgl_to_kgm3(x: float) -> float:
    """Convert [mg/l] to [kg/m3]."""
    return x / 1000


def pa_to_gpa(x: float) -> float:
    """Convert [Pa] to [GPa]."""
    return x / 1e9


def gpa_to_pa(x: float) -> float:
    """Convert [GPa] to [Pa]."""
    return x * 1e9


def rad_to_deg(x: float) -> float:
    """Convert [rad] to [deg]."""
    return x * 180 / math.pi


def deg_to_rad(x: float) -> float:
    """Convert [deg] to [rad]."""
    return x * math.pi / 180


def m3s_per_bar_to_si(x: float) -> float:
    """Convert the historical runtime's m3/s/bar index to [m3/s/Pa]."""
    return x / 1e5


def kgh_to_kgs(x: float) -> float:
    """Convert [kg/h] to [kg/s]."""
    return x / 3600


def m2_to_mm2(x: float) -> float:
    """Convert [m2] to [mm2]."""
    return x * 1e6


def ms_to_mm_year(x: float) -> float:
    """Convert penetration speed [m/s] to [mm/year]."""
    return x * 1000 * SECONDS_PER_YEAR


def mol_l_bar_to_mol_m3_pa(x: float) -> float:
    """Convert Henry solubility constant [mol/l/bar] to [mol/m3/Pa]."""
    return x * 0.01


_UNITS = {
    "Pa": ("Pa", 1, 0),
    "bar": ("Pa", 1e5, 0),
    "barg": ("Pa", 1e5, 101325),
    "K": ("K", 1, 0),
    "degC": ("K", 1, 273.15),
    "C": ("K", 1, 273.15),
    "°C": ("K", 1, 273.15),
    "m3/s": ("m3/s", 1, 0),
    "m3/h": ("m3/s", 1 / 3600, 0),
    "l/s": ("m3/s", 1e-3, 0),
    "kg/s": ("kg/s", 1, 0),
    "t/h": ("kg/s", 1000 / 3600, 0),
    "Hz": ("Hz", 1, 0),
    "W": ("W", 1, 0),
    "kW": ("W", 1000, 0),
    "MW": ("W", 1e6, 0),
    "J": ("J", 1, 0),
    "kWh": ("J", 3.6e6, 0),
    "currency": ("currency", 1, 0),
    "currency/year": ("currency/year", 1, 0),
    "currency/J": ("currency/J", 1, 0),
    "currency/kWh": ("currency/J", 1 / 3.6e6, 0),
    "currency/s": ("currency/s", 1, 0),
    "currency/h": ("currency/s", 1 / 3600, 0),
    "m": ("m", 1, 0),
    "ft": ("m", 0.3048, 0),
    "s": ("s", 1, 0),
    "min": ("s", 60, 0),
    "h": ("s", 3600, 0),
    "d": ("s", 86400, 0),
    "m/s": ("m/s", 1, 0),
    "m2": ("m2", 1, 0),
    "m3": ("m3", 1, 0),
    "rad": ("rad", 1, 0),
    "kg/m3": ("kg/m3", 1, 0),
    "g/m3": ("kg/m3", 1e-3, 0),
    "mg/l": ("kg/m3", 1e-3, 0),
    "Pa.s": ("Pa.s", 1, 0),
    "J/kg/K": ("J/kg/K", 1, 0),
    "J/kg": ("J/kg", 1, 0),
    "kJ/kg": ("J/kg", 1000, 0),
    "J/K": ("J/K", 1, 0),
    "kWh/K": ("J/K", 3.6e6, 0),
    "J/m3/K": ("J/m3/K", 1, 0),
    "MJ/m3/K": ("J/m3/K", 1e6, 0),
    "m2/s": ("m2/s", 1, 0),
    "W/m": ("W/m", 1, 0),
    "m.K/W": ("m.K/W", 1, 0),
    "K/m": ("K/m", 1, 0),
    "K/km": ("K/m", 1e-3, 0),
    "kg": ("kg", 1, 0),
    "t": ("kg", 1000, 0),
    "m3/s/Pa^0.5": ("m3/s/Pa^0.5", 1, 0),
    "m3/h/bar^0.5": ("m3/s/Pa^0.5", 1 / 3600 / 1e5**0.5, 0),
    "W/m/K": ("W/m/K", 1, 0),
    "W/m2/K": ("W/m2/K", 1, 0),
    "W/K": ("W/K", 1, 0),
    "m3/s/Pa": ("m3/s/Pa", 1, 0),
    "m3/h/bar": ("m3/s/Pa", 1 / 3600 / 1e5, 0),
    "-": ("-", 1, 0),
    "ppm": ("-", 1e-6, 0),
}

_NUMBER_AND_UNIT = re.compile(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+(.+?)\s*")


@dataclass(frozen=True)
class Quantity:
    """A scalar and unit accepted at public API boundaries."""

    value: float
    unit: str


def _entry(unit, path="units"):
    """Return ``(si_unit, scale, offset)`` of a known unit."""
    if unit not in _UNITS:
        raise UnitError(
            f"{path}: unit = {unit!r}; expected a known unit{did_you_mean(unit, _UNITS)}"
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


def to_si(value: float, unit: str, quantity: str | None = None) -> float:
    """Convert a bound scalar to SI; volume flow remains [m3/s] until density is known."""
    _, scale, _ = _entry(unit, "units.to_si")
    return float(value) * scale + _offset(unit, quantity)


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
        raise UnitError(f"{path}: unit = {supplied!r}; expected a unit of {expected_unit!r}")
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
        raise UnitError(
            f"units.convert: unit = {to_unit!r}; expected a unit of {source[0]!r} "
            f"to convert from {from_unit!r}"
        )
    si = to_si(value, from_unit, quantity)
    return (si - _offset(to_unit, quantity)) / target[1]
