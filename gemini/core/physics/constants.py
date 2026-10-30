"""Physical constants retained from the original GEMINI correlations.

| Name | Value | Unit | Meaning |
| --- | --- | --- | --- |
| ``G`` | 9.81 | m/s2 | gravitational acceleration |
| ``G_FT`` | 32.17405 | ft/s2 | gravitational acceleration, historical Beggs–Brill basis |
| ``ESP_REFERENCE_FREQUENCY`` | 60.0 | Hz | frequency of the ESP catalogue curves |
| ``ESP_EFFICIENCY_FLOW_FACTOR`` | 135773 | - | historical US ESP efficiency factor |
| ``CO2_MOLAR_MASS`` | 0.04401 | kg/mol | molar mass of CO2 |
| ``MIN_PATH_PRESSURE`` | 0.001 | Pa | floor of marched pipe-path pressures |

The ESP constants are ``gemini.ops.Constant`` objects: they act as their float on concrete
values and become named graph inputs when the ESP is traced. The others are still plain floats.
"""

from gemini.ops import Constant

G = 9.81
G_FT = 32.17405
ESP_REFERENCE_FREQUENCY = Constant(
    "ESP_REFERENCE_FREQUENCY", 60.0, "Hz", "frequency of the ESP catalogue curves"
)
ESP_EFFICIENCY_FLOW_FACTOR = Constant(
    "ESP_EFFICIENCY_FLOW_FACTOR", 135773, "-", "historical US ESP efficiency factor"
)
CO2_MOLAR_MASS = 0.04401
MIN_PATH_PRESSURE = 0.001
