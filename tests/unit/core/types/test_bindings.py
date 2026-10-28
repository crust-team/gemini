"""Binding metadata tests."""

from gemini.core.types import Binding, ModuleBindings


def test_binding_metadata_is_strict():
    """Bindings retain raw units and named columns."""
    bound = ModuleBindings(inputs={"frequency": Binding(column="f", unit="Hz")})
    assert bound.inputs["frequency"].column == "f"
