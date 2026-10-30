"""Physical constants retained from the original GEMINI correlations.

| Name | Value | Unit | Meaning |
| --- | --- | --- | --- |
| ``G`` | 9.81 | m/s2 | gravitational acceleration |
| ``G_FT`` | 32.17405 | ft/s2 | gravitational acceleration, historical Beggs–Brill basis |
| ``ESP_REFERENCE_FREQUENCY`` | 60.0 | Hz | frequency of the ESP catalogue curves |
| ``ESP_EFFICIENCY_FLOW_FACTOR`` | 135773 | - | historical US ESP efficiency factor |
| ``CO2_MOLAR_MASS`` | 0.04401 | kg/mol | molar mass of CO2 |
| ``MIN_PATH_PRESSURE`` | 0.001 | Pa | floor of marched pipe-path pressures |
| ``VALVE_REFERENCE_DENSITY`` | 1000.0 | kg/m3 | reference density of the IEC 60534 Kv |

Every constant is a ``gemini.ops.Constant``: it acts as its float on concrete values and becomes
a named graph input when the physics is traced. Use ``.value`` or ``float(constant)`` where a
plain float is needed, and ``ops.maximum``/``ops.minimum`` instead of the builtins.
"""

from gemini.ops import Constant

G = Constant("G", 9.81, "m/s2", "gravitational acceleration")
G_FT = Constant(
    "G_FT", 32.17405, "ft/s2", "gravitational acceleration, historical Beggs-Brill basis"
)
ESP_REFERENCE_FREQUENCY = Constant(
    "ESP_REFERENCE_FREQUENCY", 60.0, "Hz", "frequency of the ESP catalogue curves"
)
ESP_EFFICIENCY_FLOW_FACTOR = Constant(
    "ESP_EFFICIENCY_FLOW_FACTOR", 135773, "-", "historical US ESP efficiency factor"
)
CO2_MOLAR_MASS = Constant("CO2_MOLAR_MASS", 0.04401, "kg/mol", "molar mass of CO2")
MIN_PATH_PRESSURE = Constant(
    "MIN_PATH_PRESSURE", 0.001, "Pa", "floor of marched pipe-path pressures"
)
VALVE_REFERENCE_DENSITY = Constant(
    "VALVE_REFERENCE_DENSITY",
    1000.0,
    "kg/m3",
    "reference water density rho_0 of the flow coefficient (IEC 60534-2-1)",
)
