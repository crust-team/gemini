"""Print pump performance at three frequencies using the example pump parameters."""

from pathlib import Path

from gemini.core.base.stream import Stream
from gemini.core.modules.pumps import ESP
from gemini.core.physics import units
from gemini.core.plant import param_mapping as mapping

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
pump = ESP(mapping.esp_params_from_gemini(mapping.read_property(DATA / "esp_1ee3.param")))
suction = Stream(m_dot=units.m3h_to_m3s(130) * 1000, T=units.c_to_k(80), p=units.bar_to_pa(60))
print("Frequency [Hz]  Head [bar]  Power [W]  Efficiency [-]")
for frequency in (40, 50, 60):
    out, _ = pump({"frequency": frequency}, {"suction": suction})
    print(
        f"{frequency:14.0f}  {units.pa_to_bar(out.head):10.3f}"
        f"  {out.power:9.2f}  {out.efficiency:.4f}"
    )
print("The example has zero power coefficients, so power and efficiency are zero.")
