"""Parameter, port and schema contracts for every declared equipment module."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gemini.core.modules.heat import Boiler, HeatExchanger
from gemini.core.modules.pumps import ESP, BoosterPump, InjectionPump
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.modules.treatment import Blowdown, Degasser, Filter
from gemini.core.types.flows import Stream
from gemini.legacy import tables as mapping

DATA = Path(__file__).parents[4] / "examples/legacy/gemini_project_bridge/old_project"


def example_modules():
    """Build equipment from the checked-in example property blocks."""

    def read(name):
        return mapping.read_property(DATA / name)

    return [
        HeatExchanger(mapping.heatexchanger_params_from_gemini(read("heat_exchanger_3410.param"))),
        ESP(mapping.esp_params_from_gemini(read("esp_1ee3.param"))),
        ProductionWell(
            mapping.productionwell_params_from_gemini(read("production_well_c774.param"))
        ),
        InjectionWell(mapping.injectionwell_params_from_gemini(read("injection_well_a06b.param"))),
        ProductionReservoir(
            mapping.production_reservoir_params_from_gemini(
                read("reservoir_c1b5.param"), read("production_well_c774.param")
            )
        ),
        InjectionReservoir(
            mapping.injection_reservoir_params_from_gemini(
                read("reservoir_28fc.param"), read("injection_well_a06b.param")
            )
        ),
        InjectionPump(mapping.injectionpump_params_from_gemini(read("injection_pump_3808.param"))),
        BoosterPump(mapping.boosterpump_params_from_gemini({})),
        Degasser(mapping.degasser_params_from_gemini(read("degasser_e846.param"))),
        Filter(mapping.filter_params_from_gemini(read("filter_b1ed.param"))),
        Blowdown(mapping.blowdown_params_from_gemini({})),
        Boiler(
            mapping.boiler_params_from_gemini(dict(fuel="electric", capacity=1e6, efficiency=0.9))
        ),
    ]


@pytest.mark.parametrize("module", example_modules(), ids=lambda c: c.name)
def test_schema_and_ports(module):
    """All modules expose serialisable schemas and reject extra or missing stream ports."""
    schema = module.schema()
    assert set(schema) == {
        "name",
        "category",
        "description",
        "inlets",
        "outlets",
        "params",
        "inputs",
        "outputs",
        "soft_sensors",
        "calibratable",
        "stateful",
        "fidelity",
    }
    json.dumps(schema)
    for model in (module.Params, module.Inputs, module.Outputs):
        for field in model.model_fields.values():
            assert field.description and "[" in field.description and "]" in field.description
    inputs = (
        {"frequency": 60}
        if module.name == "esp"
        else (
            {"m_dot": 40}
            if module.name == "production_reservoir"
            else {"setpoint_T": 360} if module.name == "boiler" else {}
        )
    )
    with pytest.raises(ValueError, match=module.name + ": inlet ports"):
        module(inputs, {"unexpected": Stream(m_dot=1, T=300, p=1e5)})
    if module.inlets:
        with pytest.raises(ValueError, match="missing"):
            module(inputs, {})


@pytest.mark.parametrize("module", example_modules(), ids=lambda c: c.name)
def test_parameter_failures(module):
    """Reject unknown fields, wrong types, missing required data and nonphysical values."""
    p = module.params.model_dump()
    with pytest.raises(ValidationError):
        module.Params.model_validate(p | {"unexpected": 1})
    for name, field in module.Params.model_fields.items():
        if field.is_required():
            missing = p.copy()
            missing.pop(name)
            with pytest.raises(ValidationError):
                module.Params.model_validate(missing)
        if isinstance(p.get(name), (float, int)):
            with pytest.raises(ValidationError):
                module.Params.model_validate(p | {name: "invalid"})
            if any(
                getattr(c, "gt", None) is not None or getattr(c, "ge", None) is not None
                for c in field.metadata
            ):
                with pytest.raises(ValidationError):
                    module.Params.model_validate(p | {name: -1})
