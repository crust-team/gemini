"""Construct handwritten plants and round-trip their portable design configurations."""

from pathlib import Path

from gemini.core.config.schema import DatedParams, ModuleConfig, PlantConfig
from gemini.core.engine import registry


def build_plant(config: PlantConfig, at=None):
    """Instantiate equipment with the parameter snapshot active at the requested instant."""
    cls = registry.get(config.plant_type)
    if cls.category != "plant" or not hasattr(cls, "from_config"):
        raise ValueError(f"{config.plant_type!r} is not a configurable plant")
    plant = cls.from_config(config, at=at)
    plant.config = config.model_copy(deep=True)
    plant._active_snapshots = {
        name: item.at(at).valid_from for name, item in config.modules.items()
    }
    plant._parameter_overrides = {}
    plant.skip_counts = {}
    return plant


def plant_to_config(plant) -> PlantConfig:
    """Export current design state while retaining bindings and parameter history."""
    config = (
        plant.config.model_copy(deep=True)
        if hasattr(plant, "config")
        else PlantConfig(name=plant.name, plant_type=plant.name, modules={})
    )
    state = plant.state_dict()
    for name, module in plant.named_modules():
        if not name or module._children:
            continue
        if name in config.modules:
            item = config.modules[name]
            item.fluid = module._fluid
            active = getattr(plant, "_active_snapshots", {}).get(name, item.params[-1].valid_from)
            item.params = [
                DatedParams(
                    valid_from=p.valid_from,
                    params=state[name]["params"] if p.valid_from == active else p.params,
                )
                for p in item.params
            ]
        else:
            config.modules[name] = ModuleConfig(
                type=module.name,
                fluid=module.fluid,
                params=[DatedParams(params=state[name]["params"])],
            )
    return PlantConfig.model_validate(config.model_dump())


def save_config(config, path):
    """Write portable JSON with full precision and stable indentation."""
    Path(path).write_text(config.model_dump_json(indent=2) + "\n")


def load_config(path):
    """Validate a saved plant configuration."""
    return PlantConfig.model_validate_json(Path(path).read_text())
