# Hackathon inputs

The inputs of the GEMINI agentic geothermal design hackathon, as the organisers released them on
2026-10-29. The requirements document is dated 28 October 2026. These files are unchanged:
`GEMINI_Heating_Demand_Daily_2027.csv`, `GEMINI_Cooling_Demand_Daily_2027.csv` and
`GEMINI_Hackathon_Challenge_Requirements.pdf`.

`gm.profiles.get("heating_demand")` and `gm.profiles.get("cooling_demand")` read the two CSV files.
The profiles are synthetic: 365 daily-average power values, 1 January to 31 December 2027.

| Profile | Peak | Peak date | Year |
| --- | --- | --- | --- |
| Heating | 30.0 MWth | 2027-01-28 | 111.67 GWh/yr |
| Cooling | 10.0 MWcool | 2027-07-19 | 23.74 GWh/yr |

## Reservoir

| Parameter | Value |
| --- | --- |
| Midpoint depth | 2,500 m TVD |
| Gross thickness | 100 m |
| Geothermal gradient | 30 °C/km |
| Reference surface temperature | 12 °C |
| Reservoir pressure | 250 bar(g) |
| Permeability | 200 mD |

For another well depth the organisers allow hydrostatic pressure for the reservoir pressure and the
gradient for the reservoir temperature.

## Brine and associated gas

| Parameter | Value |
| --- | --- |
| Brine density | 1,030 kg/m³, constant |
| Dynamic viscosity | 0.40 mPa·s, constant |
| Gas-liquid ratio | 0.8 Nm³ gas per m³ produced liquid |
| Methane in the produced gas | 80 mol% |
| Carbon dioxide in the produced gas | 20 mol% |
| Fluid composition | Fixed baseline; variable PVT optional |

A normal cubic metre is at 0 °C and 1.01325 bar(a). The ratio is the gas that can be liberated at
standard conditions.

## Limits

| Constraint | Value | Status |
| --- | --- | --- |
| Geothermal doublets | 1 to 3 | Design variable |
| Maximum production flow | 300 m³/h per doublet | Hard cap |
| Minimum stable flow while active | 50 m³/h per doublet | Hard cap |
| Maximum brine cooling | 40 °C, producer to injector | Hard cap |
| Pump hydraulic efficiency | 70% | Simplified |
| Production and injection volume | Equal liquid volumes, same reservoir | Required |
| Annual operation of a doublet | 330 daily steps | Daily power and energy balance |
| Heating supply temperature | 100 °C | Fixed |
| Cooling supply temperature | 20 °C | Fixed |
