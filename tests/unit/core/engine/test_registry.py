"""Class-creation module registry contracts."""

import pytest

from gemini.core.modules import catalogue


def test_known_modules_are_registered_and_grouped():
    """Derived names resolve without filesystem discovery."""
    grouped = catalogue.list_modules()
    assert "esp" in grouped["pumps"]
    assert catalogue.get("heat_exchanger").__name__ == "HeatExchanger"
    assert catalogue.create("esp").missing_parameters()
    with pytest.raises(ValueError, match="Unknown module"):
        catalogue.get("missing")
