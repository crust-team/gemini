"""The names of the first stored plants, which the oldest golden files still hold."""

from gemini.types.fluid import Fluid

RENAMED_NAMES = {
    "approach_T": "approach_temperature",
    "bep_flow": "best_efficiency_flow",
    "bep_ratio": "best_efficiency_ratio",
    "building_return_T": "building_return_temperature",
    "building_supply_T": "building_supply_temperature",
    "capped": "is_capped",
    "carnot_efficiency": "carnot_fraction",
    "clogging_dp": "clogging_pressure_drop",
    "correction_factor": "correction_factors",
    "depth": "borehole_depth",
    "dp": "nominal_pressure_drop",
    "dp_cold": "cold_pressure_drop",
    "dp_cold_nominal": "cold_nominal_pressure_drop",
    "dp_friction": "friction_pressure_drop",
    "dp_gravity": "gravity_pressure_drop",
    "dp_hot": "hot_pressure_drop",
    "dp_hot_nominal": "hot_nominal_pressure_drop",
    "dp_nominal": "nominal_pressure_drop",
    "flow_dp": "flow_pressure_drop",
    "fluid_mean_T": "fluid_mean_temperature",
    "fraction_of_carnot": "carnot_fraction",
    "friction_correlation_2p": "two_phase_friction_correlation",
    "ground_T": "ground_temperature",
    "head_coeff": "head_coefficients",
    "heat_loss_coefficient": "heat_loss_conductance",
    "heat_transfer_coeff": "heat_transfer_coefficient",
    "hydrostatic_dp": "hydrostatic_pressure_drop",
    "ice_heat_capacity": "ice_specific_heat",
    "in_operating_window": "is_in_operating_window",
    "lmtd": "log_mean_temperature_difference",
    "lorenz_efficiency": "lorenz_fraction",
    "m_dot_cold_nominal": "cold_nominal_mass_flow",
    "m_dot_hot_nominal": "hot_nominal_mass_flow",
    "m_dot_nominal": "nominal_mass_flow",
    "max_flow": "maximum_flow",
    "min_flow": "minimum_flow",
    "no_stages": "stage_count",
    "ntu": "transfer_units",
    "output_max": "maximum_output",
    "output_min": "minimum_output",
    "p_out": "outlet_pressure",
    "power_coeff": "power_coefficients",
    "production_T": "production_out_T",
    "rock_conductivity": "ground_conductivity",
    "rock_diffusivity": "ground_diffusivity",
    "skin_dp": "skin_pressure_drop",
    "thickness": "aquifer_thickness",
    "u_value": "heat_transfer_coefficient",
    "ua": "thermal_conductance",
    "water_heat_capacity": "water_specific_heat",
}

FLUID_NAMES = {"liquid_density": "density", "liquid_viscosity": "viscosity"}


def fluid_names(stored):
    """Return stored data with every fluid in it, at any depth, in the form of 0.2.0."""
    if isinstance(stored, list):
        return [fluid_names(item) for item in stored]
    if not isinstance(stored, dict):
        return stored
    renamed = {FLUID_NAMES.get(key, key): fluid_names(value) for key, value in stored.items()}
    if "property_model" in renamed:
        return Fluid.model_validate(renamed).model_dump(mode="json")
    return renamed
