"""Abstract base interfaces for Gemini simulation models."""

from abc import ABC, abstractmethod
from typing import Any


class Model(ABC):
    """Common base for all simulation models."""

    def __init__(self):
        """Model initialization."""
        self.parameters: dict[str, Any] = {}
        self.output: dict[str, Any] = {}

    def update_parameters(self, parameters: dict[str, Any]):
        """Update model parameters."""
        self.parameters.update(parameters)

    @abstractmethod
    def calculate_output(self, u: dict[str, Any], x: Any = None):
        """Calculate output of the model."""
        pass

    def get_output(self):
        """Get output of the model as a copy."""
        return dict(self.output)


class StaticModel(Model):
    """Base class for algebraic/stateless models (y = f(u, p))."""

    def initialize_state(self, x: Any = None):
        """Stateless models do not use internal state."""
        return None

    def update_state(self, u: dict[str, Any], x: Any = None):
        """Stateless models do not evolve internal state."""
        return None


class DynamicModel(Model):
    """Base class for dynamic/stateful models (x_next = g(x, u, p), y = f(x, u, p))."""

    @abstractmethod
    def initialize_state(self, x: Any):
        """Generate an initial state based on user parameters."""
        pass

    @abstractmethod
    def update_state(self, u: dict[str, Any], x: Any):
        """Update the state based on input u and state x."""
        pass
