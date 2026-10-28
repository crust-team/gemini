"""Injection bottomhole-pressure and injectivity tags using SI components."""

from gemini.core.base.stream import Stream
from gemini.core.base.unit_module import TwinModule
from gemini.core.engine import registry
from gemini.core.physics import units
from gemini.core.plant import param_mapping as mapping


class InjectionWellTwin(TwinModule):
    """Preserve the existing injection pressure and injectivity output tags."""

    output_tags = ("injectionwell_bottomhole_pressure", "injectionwell_injectivity_index")

    def link(self):
        """Link measured wellhead conditions to the two calculated outputs."""
        for tag in (
            "injectionwell_flow",
            "injectionwell_wellhead_pressure",
            "injectionwell_wellhead_temperature",
        ):
            self.link_input(self.unit, "measured", tag)
        for tag in self.output_tags:
            self.link_output(self.unit, "calculated", tag)

    def update_model_parameter(self, timestamp):
        """Build the receiving reservoir and injection-well components."""
        reservoir = self.unit.to_units[0]
        w = mapping.snapshot(
            self.unit.parameters["property"], self.get_parameter_index(self.unit, timestamp)
        )
        r = mapping.snapshot(
            reservoir.parameters["property"], self.get_parameter_index(reservoir, timestamp)
        )
        self.reservoir = registry.create(
            "injection_reservoir", mapping.injection_reservoir_params_from_gemini(r, w)
        )
        self.well = registry.create("injectionwell", mapping.injectionwell_params_from_gemini(w))
        self.well.fluid = self.reservoir.fluid

    def calculate_row(self, values):
        """Return pressure [bar] and injectivity [m3/h/bar] at the tag boundary."""
        flow, p, T = (
            values[k]
            for k in (
                "injectionwell_flow",
                "injectionwell_wellhead_pressure",
                "injectionwell_wellhead_temperature",
            )
        )
        if any(v is None for v in (flow, p, T)):
            return dict.fromkeys(self.output_tags)
        rho = self.well.fluid.properties(units.bar_to_pa(p), units.c_to_k(T)).rho_l
        stream = Stream(
            m_dot=-units.m3h_to_m3s(flow) * rho, p=units.bar_to_pa(p), T=units.c_to_k(T)
        )
        out, _ = self.well({}, {"wellhead": stream})
        index = self.reservoir.injectivity_from_measurements(
            units.m3h_to_m3s(flow), out.bottomhole_pressure
        )
        return dict(
            zip(
                self.output_tags,
                (units.pa_to_bar(out.bottomhole_pressure), units.index_from_si(index)),
            )
        )
