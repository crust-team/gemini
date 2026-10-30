# Economics, KPIs, checks and well analysis

The packages `gemini.economics`, `gemini.checks`, `gemini.analysis` (with `gm.kpi`), `gemini.testing`
and `gemini.optim` sit above `gemini.engine`. They read a plant and a finished run through the public
API only, and every return is plain JSON (`to_plain`: no NumPy types, `NaN` and infinity are `null`) in the
[return shapes](api.md#return-shapes). A value the inputs cannot give is never a guess. Each name is
`real` or raises `NotImplementedYet` with its final signature and a full docstring.

## What a run gives

`Results` stores leaf output columns (`path.field`), not the streams that cross the leaves and not
the composite outputs. Everything below is therefore built from declared leaf outputs:

- Heat delivered is `heat_supplied` of the `HeatConsumer` leaves and cold delivered is
  `heat_absorbed` of the `CoolingConsumer` leaves (`analysis/series.py`: `leaf_total`).
- Electricity, fuel and generation are the leaf columns of those names, summed over every path
  (`results_total`). Grid electricity per tick is `max(0, electricity - electricity_generated)` and
  CO2 is `gemini.modules.balance.emissions` over those totals: one implementation, the
  weights are the emission factors (a weight of 1 and 0 gives the fuel energy, 0 and 1 the grid
  energy).
- A tick with no value (a skipped or failed row) adds no energy and is left out of ratios and peaks.
- The window of a run is the sum of its tick durations. Annual figures scale the window to one year
  (`SECONDS_PER_YEAR`, 365.25 days): the run is taken as representative of a year.

A plant without a consumer leaf, such as the doublet heat plant, delivers no heat in these terms, so
its heat and cold KPIs and levelised costs are `null` with that reason.

## `gm.economics`

Every function returns a value with the parts of its result as more keys, each a value or a text;
`unit` is the currency (`EUR`), `EUR/year`, `EUR/J`, `year` or `kg`. Every function takes
`on_error="raise"`: a value the inputs cannot give raises `ValidationError`, code `no_value`, or
`missing_value` for an assumption nobody gave. With `on_error="record"` nothing is raised and it is
`{value: null, unit, reason}`.

| Name | Returns |
|---|---|
| `Assumptions` | frozen object; see the table of sources below |
| `capex(plant, assumptions=None)` | `total_cost(plant)`: investment in the currency of the declared costs, with `price_year` and `source` |
| `opex(plant, results, assumptions=None)` | fixed + variable cost per year + yearly bill of grid electricity and fuel; `components` lists the parts |
| `lcoh(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | `(capex + opex A) / (heat A)` in currency/J, `A` the annuity factor |
| `lcoc(...)` | the same with the cold delivered |
| `co2(plant, results, assumptions=None)` | kg over the window, from `balance.emissions` |
| `npv(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | `-capex + (revenue - opex) A` |
| `payback(plant, results, assumptions=None)` | `capex / (revenue - opex)` in years, undiscounted |

`Cost` and `total_cost` (`types/cost.py`) are the one cost implementation. **No built-in module
declares a cost**, so for a plant of built-in modules `capex` and `opex` have no value, with the reason "no module
declares a cost" (under `"record"`, `opex` still lists the energy bill in `components`), and
`lcoh`, `lcoc`, `npv` and `payback` follow. A module declares its cost by defining `capex()` that
returns a `Cost`. Costs in different currencies or price years raise `ValidationError`; assumptions
in another currency than the costs raise `ValidationError`.

Missing user inputs raise `ValidationError` with code `missing_value` and the path
`assumptions.<name>`: a discount rate or lifetime given nowhere, an electricity or fuel price for an
energy the run draws, a heat or cold price for a product it delivers, an electricity emission factor
for grid electricity drawn. A price is asked for only when its energy is non-zero.

`lcoh` charges the whole plant cost to the heat, so a plant that also delivers cold has no value ("the split of its cost is not defined"); `lcoc` likewise. Levelised cost, `npv` and `payback`
assume constant yearly energy and cost over the lifetime, with no degradation, tax, replacement or
residual value.

### Sources of the `Assumptions` defaults

| Field | Unit | Default | Source |
|---|---|---|---|
| `currency` | text | `"EUR"` | label only, the default of `Cost`; not a price |
| `fuel_emission_factor` | kg/J | 56.1e-9 | IPCC 2006 Guidelines for National Greenhouse Gas Inventories, vol. 2 Energy, ch. 2, table 2.2: natural gas, 56 100 kg CO2/TJ on the net calorific value. Natural gas only |
| `discount_rate` | per year | None | depends on the project; the user gives it |
| `lifetime_years` | years | None | depends on the equipment; the user gives it |
| `electricity_price`, `fuel_price` | currency/J | None | depends on country, year and contract |
| `heat_price`, `cold_price` | currency/J | None | depends on the contract |
| `electricity_emission_factor` | kg/J | None | depends on the grid and the year |

Convert at the boundary: EUR/MWh divided by 3.6e9 is EUR/J, kg/GJ divided by 1e9 is kg/J.

## `gm.kpi`

`gm.kpi.compute(plant, results)` returns `{name: {value, unit}}` for `gm.kpi.names()`; a KPI the run
cannot give is `null` with a `reason`. With
E(x) the sum over ticks of x times the tick duration:

| Name | Unit | Definition |
|---|---|---|
| `heating_coverage` | - | E(`heat_supplied`) / E(`heat_supplied` + `unmet_demand`) over the `HeatConsumer` leaves |
| `cooling_coverage` | - | E(`heat_absorbed`) / E(`heat_absorbed` + `unmet_sensible` + `unmet_latent`) over the `CoolingConsumer` leaves |
| `cop` | - | E(`heat_supplied` of the heat consumers) / E(`electricity` of every leaf); cooling not counted |
| `peak_heat` | W | largest tick sum of `heat_supplied` (delivered power, not the demand peak) |
| `peak_cold` | W | largest tick sum of `heat_absorbed` |

## `gm.checks`

Each check returns the check `{name, passed, value, limit}`, `value` and `limit` being values; a
violated limit is `passed: false`, never an error (`passed` is `None`, with a `reason` in `value`,
when the results hold nothing the check can judge). Because `Results` has no streams, the enthalpy and mass
closure of `modules/balance.py` (sum in minus sum out per call) cannot be recomputed from
it, and the checks audit what the columns hold:

| Check | Covers | `value`, `limit` |
|---|---|---|
| `energy_balance(results)` | the leaf columns named in `ENERGY_INPUTS` and `ENERGY_OUTPUTS` of `balance.py`, except the signed `heat_accumulation`: finite or missing, not negative | smallest power [W], 1e-9 W |
| `mass_balance(results)` | the leaf outputs whose unit in `results.units` is kg/s: finite or missing, not negative | smallest flow [kg/s], 1e-12 kg/s |
| `bounds(plant, results)` | every recorded output with a declared limit (`ge`, `gt`, `le`, `lt` of its `Declaration`) | number of values outside, 0 |
| `run_all(plant, results)` | the three above | `{passed, checks}` |

A real closure check needs the engine to record each call's residual (`balance.energy_balance`)
as a result column; that is a change to the engine, not to this package.

## `gm.analysis`

| Name | Status | Notes |
|---|---|---|
| `nodal(plant, well, conditions)` | real, production wells | IPR, VLP and operating point from `plants/nodal.py`; the plant is not changed |
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
[modules.md](modules.md#registry-categories-and-streams). `gm.optim.minimize` and `gm.optim.sample`
(uncertainty sampling) have their final signatures and raise `NotImplementedYet`.
