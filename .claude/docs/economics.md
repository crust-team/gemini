# Economics, KPIs, checks and well analysis

The packages `gemini.economics`, `gemini.checks`, `gemini.analysis` (with `gm.kpi`), `gemini.testing`
and `gemini.optim` sit above `gemini.engine`. They read a plant and a finished run through the public
API only, and every return is plain JSON (`to_plain`: no NumPy types, `NaN` and infinity are `null`) in the
[return shapes](api.md#return-shapes). A value the inputs cannot give is never a guess. Each name is
`real` or raises `NotImplementedYet` with its final signature and a full docstring.

## What a run gives

`Results` stores the leaf columns (`path.field`, the outputs and the port quantities), not the
composite outputs. Everything below is read from the edge modules:

- Heat delivered is what the water loses across the `HeatingGrid` leaves and cold delivered what
  it gains across the `CoolingGrid` leaves (`analysis/series.py`: `delivered_heat`,
  `delivered_cold`). **Useful** heat and cold are that less the `surplus` of the grid, so at most the
  demand (`useful_heat`, `useful_cold`). `gm.kpi.totals` gives all three; every KPI and levelised
  cost reads the useful energy: a heat nobody needed costs money and earns nothing.
- Electricity bought and sold are `net_import` and `net_export` of the `ElectricityGrid`, gas
  bought is `gas_out.chemical_flow` of the `GasGrid`, waste `waste_in.mass_flow` of the `WasteGrid`
  and chemicals `chemical_out.mass_flow` of the `ChemicalGrid` (`edge_total`). `gm.kpi.totals`
  gives them, with the emissions and the losses.
- CO2 comes from one place: `Atmosphere` computes `co2_emission` and `methane_emission` [kg/s] from
  the gas that reaches `gas_in`.
- A tick with no value (a skipped or failed row) adds no energy and is left out of ratios and peaks.
- The window of a run is the sum of its tick durations. Annual figures scale the window to one year
  (`SECONDS_PER_YEAR`, 365.25 days): the run is taken as representative of a year.

A plant without a consumer leaf, such as the doublet heat plant, delivers no heat in these terms, so
its heat and cold KPIs and levelised costs are `null` with that reason.

## `gm.economics`

Every function returns a value with the parts of its result as more keys, each a value or a text;
`unit` is the currency (`EUR`), `EUR/year`, `EUR/J`, `year` or `kg`. `A` is the annuity factor, the
sum over the lifetime years of `1 / (1 + discount_rate) ** t`, in years. Every function takes
`on_error="raise"`: a value the inputs cannot give raises `ValidationError`, code `no_value`, or
`missing_assumption`, naming it, for an assumption nobody gave. With `on_error="record"` nothing is raised and it is
`{value: null, unit, reason}`.

| Name | Returns |
|---|---|
| `Assumptions` | frozen object; see the table of sources below |
| `capex(plant, assumptions=None)` | `total_cost(plant)`: investment in the currency of the declared costs, with `price_year` and `source` |
| `opex(plant, results, assumptions=None)` | fixed + variable cost per year + yearly bill of grid electricity and purchased gas (`fuel_purchased` at `gas_price`; co-produced gas costs nothing); `components` lists the parts |
| `lcoh(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | `(capex + opex A) / (useful heat A)` in currency/J, `A` the annuity factor |
| `lcoc(...)` | the same with the useful cold |
| `annualised_cost(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | `capex / A + opex` in currency/year, with `capex`, `opex`, `annuity_factor`, `discount_rate`, `lifetime_years` |
| `lcts(...)` | levelised cost of thermal supply, the team's design metric: `annualised_cost / (heat + cold)` in currency/J, heat and cold delivered per year, with `annualised_cost`, `heat`, `cold`; it needs no `heat_cost_share` |
| `co2(plant, results, assumptions=None)` | kg of CO2-equivalent over the window: the leaf `co2_emission`, `methane_emission` times `methane_gwp`, grid electricity times `electricity_emission_factor` |
| `npv(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | `-capex + (revenue - opex) A` |
| `payback(plant, results, assumptions=None)` | `capex / (revenue - opex)` in years, undiscounted |

`Cost` and `total_cost` (`types/cost.py`) are the one cost implementation. Every equipment module
that has a cost declares `capex(assumptions)`, which returns a `Cost` from its own design values and
a cost factor of `Assumptions` through `scaled_cost(assumptions, factor, size)`; a composite adds only
its own part. A factor without a value raises `ValidationError`, code `missing_assumption`, under
`"record"` `{value: null, reason}`. A plant with no declaring module has no value, with the reason "no
module declares a cost". Costs in different currencies or price years raise `ValidationError`;
assumptions in another currency than the costs raise `ValidationError`.

| Module | `capex` |
| --- | --- |
| `Doublet` with a design | `drilling_cost` times twice the depth, plus `pump_cost` times the shaft power at `nominal_flow`; without a design, none |
| `HeatPump`, `Boiler`, `AbsorptionUnit` | `heat_pump_cost`, `boiler_cost`, `chiller_cost` times `capacity` |
| `CHP` | `chp_cost` times `electric_capacity` |
| `HeatExchanger` | `exchanger_cost` times `thermal_conductance` |
| `Degasser`, `Flare`, `GasMakeup` | `degasser_cost`, `flare_cost`, `makeup_cost`, fixed items |

`lcoh` charges the whole plant cost to the heat. A plant that also delivers cold has no value ("the
split of its cost is not defined") unless `heat_cost_share` gives the part charged to heat; `lcoc`
gets the rest. `lcts` needs no share: with a `heat_cost_share` of 1, `lcts` is `lcoh` times its
energy over `heat + cold`. It has no value when the run delivers neither. `lcoh` and `lcoc` keep the
one expression `(capex + opex A) / (energy A)`: `annualised_cost` and they share `lifetime_cost`
(`capex + opex A`) and not the division, which would move the last bits of their numbers. Levelised
cost, `npv` and `payback` assume constant yearly energy and cost over the
lifetime, with no degradation, tax, replacement or residual value.

Missing user inputs raise `ValidationError` with code `missing_assumption` and the path
`assumptions.<name>`: a discount rate or lifetime given nowhere, an electricity or gas price for an
energy the run buys, a heat or cold price for a product it delivers, an electricity emission factor
for grid electricity drawn. A price is asked for only when its energy is non-zero.

### Sources of the `Assumptions` defaults

| Field | Unit | Default | Source |
|---|---|---|---|
| `currency` | text | `"EUR"` | label only, the default of `Cost`; not a price |
| `methane_gwp` | - | 29.8 | IPCC Sixth Assessment Report, Working Group I, ch. 7, table 7.15 (Forster et al. 2021): fossil methane over 100 years |
| `discount_rate` | per year | None | depends on the project; the user gives it |
| `lifetime_years` | years | None | depends on the equipment; the user gives it |
| `electricity_price` | currency/J | None | depends on country, year and contract |
| `gas_price` | currency/MWh | None | per MWh of fuel energy; depends on country, year and contract |
| `heat_price`, `cold_price` | currency/J | None | depends on the contract |
| `heat_cost_share` | - | None | a choice of the assessment |
| `electricity_emission_factor` | kg/J | None | depends on the grid and the year |

### Sources of the cost factors

All are in `cost_price_year` = 2015, the prices of the Danish catalogue; `Assumptions` has the
citation of each in `COST_SOURCES`, and `capex` returns it in `source`.

| Field | Unit | Default | Source |
|---|---|---|---|
| `drilling_cost` | currency/m of well | 1239.13 | SDE+ 2013 reference case, 5.7 MEUR net drilling for a doublet at 2300 m, over 2 x 2300 m (Mijnlieff et al. 2013, EGC, slide 26). Per doublet by the table's own sum: 6.2 MWth at 1527 EUR/kWth is 9.5 MEUR. A 2013 figure, not escalated. The 3000 m case gives 1833 EUR/m: use it for deep designs |
| `degasser_cost` | currency | 1 000 000 | SDE+ 2013 reference case, reserve for separation of hydrocarbons per doublet (same slide), a 2013 figure, not escalated |
| `heat_pump_cost` | currency/W | 0.67 | Danish Energy Agency, Technology Data for Energy Plants, April 2020, ch. 40, compression heat pump, excess heat, 10 MW, 2020 |
| `boiler_cost` | currency/W | 0.06 | same catalogue, ch. 44, district heating boiler, natural gas, 2020 |
| `chp_cost` | currency/W electric | 0.95 | same catalogue, ch. 06, spark ignition engine, natural gas, 1-10 MWe, 2020 |
| `pump_cost`, `chiller_cost`, `exchanger_cost`, `flare_cost`, `makeup_cost` | | None | no source found; using one raises `missing_assumption` |

Convert at the boundary: EUR/MWh divided by 3.6e9 is EUR/J, kg/GJ divided by 1e9 is kg/J.

## `gm.kpi`

`gm.kpi.compute(plant, results)` returns `{name: {value, unit}}` for `gm.kpi.names()`; a KPI the run
cannot give is `null` with a `reason`. With
E(x) the sum over ticks of x times the tick duration:

| Name | Unit | Definition |
|---|---|---|
| `heating_coverage` | - | E(useful heat) / E(useful heat + `unmet_demand`) over the `HeatingGrid` leaves |
| `cooling_coverage` | - | E(useful cold) / E(useful cold + `unmet_sensible` + `unmet_latent`) over the `CoolingGrid` leaves |
| `cop` | - | E(useful heat) / E(`ElectricityGrid.power_out`); cooling not counted |
| `peak_heat` | W | largest tick sum of useful heat (delivered power, not the demand peak) |
| `peak_cold` | W | largest tick sum of useful cold |

## `gm.checks`

Each check returns the check `{name, passed, value, limit}`, `value` and `limit` being values; a
violated limit is `passed: false`, never an error (`passed` is `None`, with a `reason` in `value`,
when the results hold nothing the check can judge). Because `Results` has no streams, the enthalpy and mass
closure of `modules/_utils/balance.py` (sum in minus sum out per call) cannot be recomputed from
it, and the checks audit what the columns hold:

| Check | Covers | `value`, `limit` |
|---|---|---|
| `energy_balance(results)` | the leaf columns named in `ENERGY_INPUTS` and `ENERGY_OUTPUTS` of `_utils/balance.py`, except the signed `heat_accumulation`: finite or missing, not negative | smallest power [W], 1e-9 W |
| `plant_balance(plant, run)` | mass and energy in = out + losses + change of stored energy, per module (1e-9) and for the root (1e-6) | a list of checks, the worst relative residual of each |
| `mass_balance(results)` | the leaf outputs whose unit in `results.units` is kg/s: finite or missing, not negative | smallest flow [kg/s], 1e-12 kg/s |
| `bounds(plant, results)` | every recorded output with a declared limit (`ge`, `gt`, `le`, `lt` of its `Declaration`) | number of values outside, 0 |
| `operating_days(plant, results, days)` | the days each doublet ran: the UTC days on which `<doublet>.reservoir.liquid_flow`, the column behind `Doublet.flow`, is above zero on a tick | a list of checks, one per doublet, exact: days run, `days`, both in `day` |
| `run_all(plant, results, days=None)` | the first three above, and `operating_days` when `days` is given | `{passed, checks}` |

`gm.checks.Limits` holds limits a user sets, `(path pattern, output, min, max)`:

```python
limits = gm.checks.Limits()
limits.add("d*.reservoir.liquid_flow", min="50 m3/h", max="300 m3/h")
limits.add("d*.brine_cooling", max="40 K")
limits.add("heat_users.supply_in_T", min="100 degC")
checks = gm.checks.limits(plant, results, limits)
```

`add` checks the units and needs no plant; `to_dict` and `from_dict` give a plain dictionary to store.
`gm.checks.limits` matches each pattern against the module paths, name by name (`*` stays within one
name, so `d*.power` is not `d0.esp.power`); a pattern or output that matches nothing raises
`ValidationError`, code `unknown_name`, with suggestions. It returns one check per matched module and
output, `value` the worst value of the run and `limit` the limit, `[min, max]` with both. Only ticks
on which the module carried flow are judged: the minimum flow holds while a doublet runs. A violated
limit is an answer. `Results` holds leaf columns, so an output of a composite is read through the
paths its combination names: `Doublet` declares `brine_cooling`
(`Output.difference("riser.wellhead_out.T", "injector.wellhead_in.T")`), and the liquid volume flow of
a doublet is `reservoir.liquid_flow` of its reservoir.

A real closure check needs the engine to record each call's residual (`balance.energy_balance`)
as a result column; that is a change to the engine, not to this package.

## `gm.analysis`

| Name | Status | Notes |
|---|---|---|
| `nodal(plant, well, conditions)` | real, production wells | IPR, VLP and operating point from `gemini/analysis/solves.py`; the plant is not changed |
| `pump_curve(plant, pump, measured=None)` | real | the polynomial head curve of the pump at 60 Hz (the private `_head_curve` of `gemini/analysis/wells.py`), theoretical head of measured points, `gm.analysis.fit_head_correction` |
| `corrosion_forecast(model, until)` | real | `co2_corrosion_rate`, `wall_loss`, `time_to_minimum_wall` |
| `injectivity(data, well)` | `NotImplementedYet` | Hall analysis not built |
| `calibrate_pump(plant, pump, measured)` | `NotImplementedYet` | no module applies the `correction_factors` of `ESP` (only the legacy import and export read it); it will run `gm.optim.calibrate` |
| `calibrate_corrosion(logs)` | `NotImplementedYet` | no fit of the correlation constants to logs exists |
| `erosion(plant, well)` | `NotImplementedYet` | a plant holds neither flow nor solids content, and the retained model has no solids fraction |

`nodal` takes `conditions` as one dict or a list of dicts (a what-if): `wellhead_pressure` [Pa],
`rates` as the `[low, high]` bracket [kg/s] and `frequency` [Hz] for an ESP; strings with units
are accepted. A case whose bracket leaves the well model's domain raises `PhysicsError`; with `on_error="record"`
the case carries the problem in `error` and the other cases still run. The VLP is the wellhead pressure the well, ESP and riser
deliver at each rate; the operating point is where it falls to the wellhead pressure asked for.

`pump_curve` head is a pressure difference in Pa; the head of a fluid column in metres is
`head / (density g)`. The correction is `theoretical = slope * measured + offset` (offset in Pa).

## `gm.testing` and `gm.optim`

`gm.testing.check_module` and `gm.modules.load_file` are described in
[modules.md](modules.md#registry-categories-and-streams).

`gm.optim.minimize(plant, profile, variables, objective, constraints=None, evaluations=100, *,
assumptions=None)` searches design values on a fixed run input. Each trial copies the plant, sets
the variables with `set_params`, simulates `profile` and reads the metric, so the plant is not
changed. The search is `scipy.optimize.differential_evolution` from a Latin hypercube, seed fixed,
with five candidates per variable: the population times the generations is the number of
simulations, so `evaluations` is a hard limit and a smaller budget than one population raises
`ValidationError`. A trial that fails, has no value or breaks a constraint is in `history` with its
`reason` and is never `best`. `gm.optim.sample(plant, profile, distributions, metrics, count, seed=0,
*, assumptions=None)` draws `normal`, `uniform` and `triangular` parameters with
`numpy.random.default_rng(seed)`, one simulation each, and summarises each metric as `mean`, `p5`,
`p50`, `p95`; a draw whose run failed has its `reason` and stays out of the summary.

A metric is a name of `gm.kpi.names()` or `lcoh`, `lcoc`, `lcts`, `annualised_cost`, `co2`; these
read `assumptions`. `profile` is required: the run input of a design comes from `gm.schedule`, which
needs the rules `doublet_flow` and `max_brine_cooling`, and it stays fixed over the trials, so a
plan made for one design is what every trial runs. `parameters` in `best`, `history` and `samples`
are numbers in SI, the input of the next `set_params`.
