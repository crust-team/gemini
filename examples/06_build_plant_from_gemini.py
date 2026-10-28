"""Load the example graph, inspect its tree and save the portable configuration."""

from pathlib import Path

from gemini.core.config.build import build_plant, plant_to_config, save_config
from gemini.core.config.gemini_loader import load_gemini

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
config = load_gemini(DATA)
plant = build_plant(config)
for path, module in plant.named_modules():
    print(f"{path or plant.path}: {module.name} ({module.fidelity})")
save_config(plant_to_config(plant), DATA / "plant.json")
print(f"Saved {DATA / 'plant.json'}; ignored {len(config.ignored)} documented fields.")
