"""Turn a plant into a dictionary, build it back, and save and load it.

Shows ``to_dict``, ``gm.plants.from_dict``, ``save`` and ``gm.Plant.load``.

Run with ``python examples/basics/06_save_and_load.py``.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import gemini as gm

PLANT = Path(__file__).resolve().parents[2] / "datasets/doublet_heat/plant.json"


def main():
    """Round-trip a plant through a dictionary and through a file."""
    plant = gm.Plant.load(PLANT)
    plant.set_params("heat_exchanger", {"thermal_conductance": "3500000 W/K"})
    spec = plant.to_dict()
    print(f"Modules in the spec:     {len(spec['modules'])}")
    print(f"Connections in the spec: {len(spec['connections'])}")

    rebuilt = gm.plants.from_dict(spec)
    print(f"Same spec rebuilt:       {rebuilt.to_dict() == spec}")

    with TemporaryDirectory() as folder:
        path = Path(folder) / "plant.json"
        plant.save(path)
        loaded = gm.Plant.load(path)
    conductance = loaded.params_at("heat_exchanger")["thermal_conductance"]
    print(f"Conductance after load:  {conductance / 1e3:.0f} kW/K")
    print(f"Same spec loaded:        {loaded.to_dict() == spec}")


if __name__ == "__main__":
    main()
