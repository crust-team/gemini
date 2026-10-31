"""Build a small treatment train plant from filters with the plant builder.

Run from the repository root: PYTHONPATH=. python examples/plants/basics/02_custom_plant.py
"""

import gemini as gm

COUNT = 2

plant = gm.Plant("TreatmentTrain")
for index in range(COUNT):
    plant.add("Filter", f"filter_{index}")
for index in range(COUNT - 1):
    plant.connect(f"filter_{index}", f"filter_{index + 1}")
plant.connect("fluid_in", "filter_0.fluid_in")
plant.connect(f"filter_{COUNT - 1}.fluid_out", "fluid_out")
result = plant(fluid_in=gm.Stream(flow="10 kg/s", T="60 C", p="10 bar"))
print(result.outlets.fluid_out)
