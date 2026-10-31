# Shallow district sample problem

A second sample problem, unlike the first: an hourly demand of three winter weeks on one shallow,
colder doublet, a 65 °C network and other limits. Every value is invented for testing and none is
measured data. Only `examples/` and `tests/` read this folder, and nothing under `gemini/` knows it.

`examples/cases/shallow_district.py` runs it through the same general functions as any problem:
`gm.profiles.from_csv`, `gm.plants.from_dict`, `gm.checks.Limits.from_dict`, `gm.schedule` and
`gm.simulate`.

| File | Holds |
| --- | --- |
| `demand.csv` | 504 hourly rows from 2026-01-12: `timestamp`, `heat_kw`, `cool_kw`, a daily cycle with a morning peak, lower at night and at the weekend; written once from a formula |
| `plant.json` | A plant dict of class `HeatingHeatPumpCoolingPlant` on one doublet |
| `rules.json` | The rules of `gm.schedule` |
| `limits.json` | The checks of the run, a `gm.checks.Limits` dict |

## Values

| Value | Setting | Why |
| --- | --- | --- |
| Depth | 1300 m | A shallow doublet |
| Geotherm | 36 K/km from 9 °C | Gives about 56 °C, so a heat pump is needed for 65 °C |
| Reservoir and sink pressure | 120 barg | Near hydrostatic at this depth |
| Thickness, permeability | 60 m, 450 mD | A thin, good sand |
| Well diameter | 0.216 m | A smaller well |
| Brine | 1012 kg/m³, 0.55 mPa·s | A low-salinity brine |
| Gas-liquid ratio | 0.15 Nm³/m³, 92 % CH4, 8 % CO2 | Little gas |
| Nominal flow, wellhead pressure | 130 m³/h, 8 bar | Sized for the peak |
| Pump efficiency | 0.65, both pumps | |
| Injection pressure | 36 bar | Lower values gave a negative head |
| Heat exchanger | 250 kW/K | Small network |
| Heat pump | 1.6 MW, source not below 27 °C | Lifts to the supply |
| Boiler | 3.5 MW, efficiency 0.92 | Covers the peak |
| Heating supply, return | 65 °C, 38 °C at 5 bar | A low-temperature network |
| Compression chiller | 0.4 MW, supply 16 °C, return 22 °C at 3 bar | Heat-free cooling |
| Cooler | 1 MW, 6 K approach, 18 °C, 60 kg/s | Rejects the chiller heat |
| Air | 6 °C | A cold season |
| Pipes | 400 m, 0.2 m inside diameter | |

## Rules and limits

| Rule or limit | Value |
| --- | --- |
| Doublet flow | 35 to 180 m³/h |
| Brine cooling | at most 22 K |
| Operating time | 450 h of 504: its 54 outage steps are the lowest-demand hours |
| Pump efficiency | 0.6 to 0.68 |
| Volume balance | within 1e-5 m³/s |
| Heating supply | at least 65 °C |
| Cooling supply | at most 16 °C |
