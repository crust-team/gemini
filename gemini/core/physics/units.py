"""Unit conversions at package and correlation boundaries; historical factors retained."""

import math

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


def to_si(value: float, unit: str) -> float:
    """Convert a bound scalar to SI; volume flow remains [m3/s] until density is known."""
    conversions = {
        "bar": (1e5, 0),
        "barg": (1e5, 101325),
        "degC": (1, 273.15),
        "K": (1, 0),
        "m3/h": (1 / 3600, 0),
        "m3/s": (1, 0),
        "kg/s": (1, 0),
        "Hz": (1, 0),
        "W": (1, 0),
        "kW": (1000, 0),
        "MW": (1e6, 0),
        "J": (1, 0),
        "kWh": (3.6e6, 0),
        "currency/J": (1, 0),
        "currency/kWh": (1 / 3.6e6, 0),
        "Pa": (1, 0),
        "-": (1, 0),
    }
    if unit not in conversions:
        raise ValueError(f"Unknown data unit {unit!r}")
    scale, offset = conversions[unit]
    return float(value) * scale + offset
