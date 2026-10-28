"""The complete public-API acceptance script."""

import gemini as gm

# Load a GEMINI project folder or our own plant.json.
plant = gm.load_plant("datasets/geothermal_doublet")
print(plant)

data = gm.Dataset.from_csv("datasets/geothermal_doublet/geothermal_example_dataset.csv")
engine = gm.Engine()
res = engine.replay(plant, data)
print(res.summary())
esp_power = res["doublet.esp"].power

engine.save_checkpoint("runs/replay.ckpt")
engine2 = gm.Engine.load_checkpoint("runs/replay.ckpt")
res2 = engine2.resume()

fit = gm.optim.calibrate(plant, data, "heat_exchanger", fields=["ua"])
print(fit)
plant.save("runs/my_plant.json")
assert gm.load_plant("runs/my_plant.json").state_dict() == plant.state_dict()

profiles = {
    "Qp": gm.Profile.constant(150, unit="m3/h", clock=gm.Clock.days(2027, 1, 1, days=1)),
    "ESP_freq": gm.Profile.constant(55, unit="Hz", clock=gm.Clock.days(2027, 1, 1, days=1)),
}
sim = engine.simulate(
    plant, gm.Dataset.from_profiles(profiles), clock=gm.Clock.days(2027, 1, 1, days=1)
)
print(sim.summary())

live_data = gm.Dataset.from_csv_driver("datasets/geothermal_doublet")
out = engine.live(plant, live_data, checkpoint="runs/live.ckpt", now="2024-06-08T00:00:00Z")
