"""Physical aliases enforce bounds and retain dimensional metadata."""

import pytest
from pydantic import BaseModel, ValidationError

from gemini.core.types.quantities import Efficiency, Pressure, PressureDifference, Temperature


class Sample(BaseModel):
    """Independent example contracts."""

    p: Pressure
    dp: PressureDifference
    T: Temperature
    efficiency: Efficiency


def test_quantities():
    """Signed differences remain legal; absolute pressure and efficiency have physical bounds."""
    values = dict(p=0, dp=-100, T=300, efficiency=1)
    assert Sample(**values).dp == -100
    for name, value in (("p", -1), ("T", 0), ("efficiency", 0), ("efficiency", 1.1)):
        with pytest.raises(ValidationError):
            Sample(**(values | {name: value}))
    schema = Sample.model_json_schema()["properties"]
    assert schema["p"]["unit"] == "Pa"
    assert schema["p"]["quantity"] == "pressure"
    assert schema["p"]["minimum"] == 0
