"""Physical aliases enforce bounds and retain dimensional metadata."""

from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

from gemini.core.physics import units
from gemini.core.types import Output, quantities
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


def test_every_quantity_unit_is_a_known_si_unit():
    """Each declared quantity's unit is in the unit table and is its own SI unit."""
    for name in dir(quantities):
        value = getattr(quantities, name)
        for field in get_args(value)[1:]:
            unit = field.json_schema_extra["unit"]
            assert units.si_unit(unit) == unit, name


def test_energy_output_quantities_are_additive_watts():
    """Each energy output has its own additive quantity in W; plain Power and MassFlow differ."""
    names = {
        "Electricity": "electricity",
        "ElectricityGenerated": "electricity_generated",
        "Fuel": "fuel",
        "HeatLoss": "heat_loss",
        "HeatSupplied": "heat_supplied",
        "HeatAbsorbed": "heat_absorbed",
        "HeatAccumulation": "heat_accumulation",
        "Duty": "duty",
        "HydraulicPower": "hydraulic_power",
    }
    for alias, quantity in names.items():
        output = Output(getattr(quantities, alias))
        assert (output.quantity, output.unit, output.additive) == (quantity, "W", True)
        assert output.validate(-5.0) == -5.0
    assert not Output(quantities.Power).additive
    assert Output(quantities.MassFlow).additive
