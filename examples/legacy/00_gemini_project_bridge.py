"""Convert old files in both directions.

Run from the repository root: PYTHONPATH=. python examples/legacy/00_gemini_project_bridge.py
"""

import argparse
from pathlib import Path

import gemini as gm
from gemini.utils import legacy

parser = argparse.ArgumentParser()
parser.add_argument("--out", default="runs/bridge")
arguments = parser.parse_args()
source = Path("examples/legacy/gemini_project_bridge/old_project")
target = Path(arguments.out)
target.mkdir(parents=True, exist_ok=True)

project = legacy.read_project(source)
plant = legacy.to_plant(project, gm.plants.get("DoubletHeatPlant"))
old_frame = legacy.read_csv(source / "doublet_2024_old.csv")
data = legacy.to_dataset(project, old_frame)
plant.save(target / "plant.json")
frame = data.to_frame()
frame.index.name = "time"
frame.reset_index().to_csv(target / "doublet_2024_15min.csv", index=False, float_format="%.17g")
results = gm.replay(plant, data.window(end="2024-06-07T01:00:00Z"))
legacy.write_csv(legacy.results_to_frame(results, project), target / "results_old.csv")
legacy.write_project(legacy.from_plant(plant, project), target / "old_project")
print("Converted", len(data), "rows; wiring:", legacy.check_wiring(plant, project))
