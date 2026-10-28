"""Calculate the three existing theoretical ESP tags from one component evaluation."""

import numpy as np

from gemini.core.base.stream import Stream
from gemini.core.base.unit_module import TwinModule
from gemini.core.engine import registry
from gemini.core.physics import units
from gemini.core.plant import param_mapping as mapping


class ESPTheoretical(TwinModule):
    """Theoretical head, power and discharge pressure with the original tag names and units."""

    output_tags = (
        "esp_theoretical_head",
        "esp_theoretical_power",
        "esp_theoretical_outlet_pressure",
    )

    def link(self):
        """Link measured flow, drive frequency and suction pressure to the three outputs."""
        for name in ("esp_flow", "esp_frequency", "esp_inlet_pressure"):
            self.link_input(self.unit, "measured", name)
        for name in self.output_tags:
            self.link_output(self.unit, "calculated", name)

    def update_model_parameter(self, timestamp):
        """Build the pump for the property snapshot active at this timestamp."""
        index = self.get_parameter_index(self.unit, timestamp)
        params = mapping.esp_params_from_gemini(
            mapping.snapshot(self.unit.parameters["property"], index)
        )
        params["coefficient_precision"] = "float32"
        self.pump = registry.create("esp", params)

    def calculate_row(self, values):
        """Convert plant flow [m3/h] and pressures [bar] at the tag boundary."""
        flow, frequency, inlet = (
            values[k] for k in ("esp_flow", "esp_frequency", "esp_inlet_pressure")
        )
        if flow is None or frequency is None:
            return dict.fromkeys(self.output_tags)
        if frequency == 0:
            head = power = 0.0
        else:
            suction = Stream(
                m_dot=units.m3h_to_m3s(flow) * 1000,
                T=300,
                p=units.bar_to_pa(inlet) if inlet is not None else 0,
            )
            out, _ = self.pump.compute({"frequency": frequency}, {"suction": suction})
            # Preserve the float32 Pa-to-bar conversion performed before the old database write.
            head = float(units.pa_to_bar(np.float32(out.head)))
            power = out.power
        return dict(zip(self.output_tags, (head, power, None if inlet is None else head + inlet)))
