"""Erosion rate meta-model dispatching to industry correlations."""

from gemini.core.physics._legacy.erosion.correlation.API import ErosionAPI
from gemini.core.physics._legacy.erosion.correlation.DNV import ErosionDNV
from gemini.core.physics._legacy.erosion.correlation.OKA import ErosionOKA
from gemini.core.physics._legacy.erosion.correlation.TULSA import ErosionTULSA
from gemini.core.physics._legacy.model_abstract import StaticModel

# -- canonical model names ------------------------------------------------
MODEL_DNVGL = "DNVGL"
MODEL_OKA = "OKA"
MODEL_API = "API"
MODEL_TULSA = "E/CRC Tulsa"

# Map user-facing spellings (upper-cased) to canonical names.
_ALIASES = {
    "DNVGL": MODEL_DNVGL,
    "DNV": MODEL_DNVGL,
    "OKA": MODEL_OKA,
    "API": MODEL_API,
    "E/CRC TULSA": MODEL_TULSA,
    "TULSA": MODEL_TULSA,
    "ECRC": MODEL_TULSA,
}

# Canonical name -> correlation class exposing calculate_erosion_rate().
_RATE_CORRELATIONS = {
    MODEL_DNVGL: ErosionDNV,
    MODEL_OKA: ErosionOKA,
    MODEL_TULSA: ErosionTULSA,
}


def normalize_model_name(name):
    """Resolve a user-facing erosion model name to its canonical form."""
    key = str(name).strip().upper()
    canonical = _ALIASES.get(key)
    if canonical is None:
        raise ValueError(f"Unknown erosion_model '{name}'.")
    return canonical


def is_velocity_model(name):
    """Return whether the model yields a velocity limit (API) rather than a rate."""
    return normalize_model_name(name) == MODEL_API


class ErosionModel(StaticModel):
    """Erosion correlation dispatcher (OKA, DNVGL, API, E/CRC Tulsa)."""

    def __init__(self):
        """Initialize erosion model."""
        self.parameters = {}
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters."""
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Generate an initial state based on user parameters."""
        pass

    def update_state(self, u, x):
        """Update the state based on input u and state x."""
        pass

    def calculate_output(self, u, x):
        """Calculate erosion output based on input u and state x."""
        self.output = self._calculate(u)

    def get_output(self):
        """Get output of the model."""
        return self.output

    def _calculate(self, u):
        """Run the selected erosion correlation."""
        model_key = normalize_model_name(self.parameters.get("erosion_model", MODEL_DNVGL))

        correlation_input = dict(u)
        out = {
            "erosion_rate_mm_yr": None,
            "erosion_velocity_ms": None,
        }

        # -- velocity-limit model (API) -------------------------------------
        if model_key == MODEL_API:
            rho_fluid_kgm3 = float(correlation_input.get("rho_fluid", 0))
            out["erosion_velocity_ms"] = ErosionAPI.calculate_erosion_velocity(rho_fluid_kgm3)
            return out

        # -- rate models (DNVGL, OKA, E/CRC Tulsa) --------------------------
        correlation = _RATE_CORRELATIONS[model_key]
        out["erosion_rate_mm_yr"] = correlation.calculate_erosion_rate(correlation_input)
        return out
