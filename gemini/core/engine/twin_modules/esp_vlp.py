"""ESP intake and discharge inference using reservoir and well components."""

from gemini.core.base.stream import Stream
from gemini.core.base.unit_module import TwinModule
from gemini.core.engine import registry
from gemini.core.physics import units
from gemini.core.plant import param_mapping as mapping


class ESPVLP(TwinModule):
    """Infer the original VLP inlet, outlet and head tags."""

    output_tags = ("esp_vlp_ipr_inlet_pressure", "esp_vlp_outlet_pressure", "esp_vlp_head")

    def link(self):
        """Retain measured-well and measured-pump wiring."""
        well = self.unit.from_units[0]
        for tag in ("esp_flow", "esp_inlet_pressure"):
            self.link_input(self.unit, "measured", tag)
        for tag in ("productionwell_wellhead_pressure", "productionwell_wellhead_temperature"):
            self.link_input(well, "measured", tag)
        for tag in self.output_tags:
            self.link_output(self.unit, "calculated", tag)

    def update_model_parameter(self, timestamp):
        """Create component snapshots while preserving the legacy adapter conventions."""
        well = self.unit.from_units[0]
        reservoir = well.from_units[0]

        def properties(unit):
            return mapping.snapshot(
                unit.parameters["property"], self.get_parameter_index(unit, timestamp)
            )

        w, e, r = properties(well), properties(self.unit), properties(reservoir)
        params = mapping.production_reservoir_params_from_gemini(r, w)
        # NOTE(refactor): old IPR combined flow [m3/s] with PI labelled [m3/h/bar].
        # Preserve that dashboard result here; the public reservoir mapper uses correct SI.
        params["productivity_index"] = units.m3s_per_bar_to_si(
            w["productionwell_productivity_index"]
        )
        self.reservoir = registry.create("production_reservoir", params)
        self.well = registry.create("productionwell", mapping.legacy_esp_well_params(w, e))
        self.well.fluid = self.reservoir.fluid
        # NOTE(refactor): old outlet correction always used the first ESP parameter snapshot.
        first = mapping.snapshot(self.unit.parameters["property"], 0)
        self.correction = mapping.esp_params_from_gemini(first)["correction_factor"]

    def calculate_row(self, values):
        """Return pressure tags [bar], preserving measured-intake subtraction for VLP head."""
        flow = values["esp_flow"]
        result = dict.fromkeys(self.output_tags)
        if flow is None:
            return result
        rho = self.reservoir.fluid.properties(
            self.reservoir.params.pressure, self.reservoir.params.temperature
        ).rho_l
        mass = units.m3h_to_m3s(flow) * rho
        _, streams = self.reservoir.compute({"m_dot": mass}, {})
        intake = self.well.intake_conditions(streams["sandface"])
        result["esp_vlp_ipr_inlet_pressure"] = units.pa_to_bar(intake.p)
        p, T = (
            values["productionwell_wellhead_pressure"],
            values["productionwell_wellhead_temperature"],
        )
        if p is not None and T is not None:
            discharge = self.well.discharge_from_wellhead(
                Stream(m_dot=mass, p=units.bar_to_pa(p), T=units.c_to_k(T))
            )
            a, b = self.correction
            result["esp_vlp_outlet_pressure"] = units.pa_to_bar(a * discharge.p + b)
            if values["esp_inlet_pressure"] is not None:
                result["esp_vlp_head"] = (
                    result["esp_vlp_outlet_pressure"] - values["esp_inlet_pressure"]
                )
        return result
