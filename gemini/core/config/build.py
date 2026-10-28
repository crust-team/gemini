"""Construct handwritten plants and round-trip their portable design configurations."""

from pathlib import Path

from gemini.core.config.schema import ModuleConfig, PlantConfig
from gemini.core.engine import registry


def build_plant(config: PlantConfig, at=None):
    """Instantiate equipment with the parameter snapshot active at the requested instant."""
    cls = registry.get(config.plant_type)
    if cls.category != "plant" or not hasattr(cls, "from_config"):
        raise ValueError(f"{config.plant_type!r} is not a configurable plant")
    plant = cls.from_config(config, at=at)
    plant.config = config.model_copy(deep=True)
    plant.bindings = config.model_copy(deep=True).bindings
    plant.boundary = config.model_copy(deep=True).boundary
    for name, item in config.modules.items():
        module = plant.get_submodule(name)
        module.param_history = [p.model_copy(deep=True) for p in item.params]
        module._active_from = item.at(at).valid_from
        module._param_overrides = dict(item.overrides)
    if config.state:
        plant.load_state_dict(config.state)
        for name, item in config.modules.items():
            plant.get_submodule(name)._active_from = item.active_from
    plant.skip_counts = {}
    return plant


def plant_to_config(plant) -> PlantConfig:
    """Export current design without replacing the historical parameter snapshots."""
    config = (
        plant.config.model_copy(deep=True)
        if hasattr(plant, "config")
        else PlantConfig(name=plant.name, plant_type=plant.name, modules={})
    )
    config.bindings = plant.bindings
    config.boundary = plant.boundary
    config.state = plant.state_dict()
    for name, module in plant.named_modules():
        if not name or module._children:
            continue
        config.modules[name] = ModuleConfig(
            type=module.name, fluid=module._fluid,
            params=module.param_history,
            overrides=module._param_overrides, active_from=module._active_from,
        )
    return PlantConfig.model_validate(config.model_dump())


def save_config(config, path):
    """Write portable JSON with full precision and stable indentation."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(config.model_dump_json(indent=2) + "\n")


def load_config(path):
    """Validate a saved plant configuration."""
    return PlantConfig.model_validate_json(Path(path).read_text())
