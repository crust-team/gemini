"""Build a small treatment train plant from filters with the plant builder.

Run from the repository root: PYTHONPATH=. python examples/core/basics/02_custom_plant.py
"""

import gemini as gm

COUNT = 2

plant = gm.Plant("TreatmentTrain")
for index in range(COUNT):
    plant.add("Filter", f"filter_{index}")
for index in range(COUNT - 1):
    plant.connect(f"filter_{index}", f"filter_{index + 1}")
plant.connect("inlet", "filter_0.inlet")
plant.connect(f"filter_{COUNT - 1}.outlet", "outlet")
result = plant(inlet=gm.Stream(flow="10 kg/s", T="60 C", p="10 bar"))
print(result.outlets.outlet)
