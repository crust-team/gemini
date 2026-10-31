# Equipment catalogue

Every shipped equipment class, with its model and the numbers it needs. Import a class from
`gemini.modules` (also `gm.modules.<Name>`); composite plants are in `gm.plants`. How to
write, call, step and compose modules is in [modules.md](modules.md); quantities, fluids and the
energy outputs are in [types.md](types.md); the correlations behind the models are in
[physics.md](physics.md).

Shared conventions, stated once here and not repeated per module:

- Values are SI (K, Pa, kg/s, m, W, J, s). Every numeric declaration also accepts a unit string
  such as `"80 C"`, `"6 bar"` or `"40 m3/h"`; see [types.md](types.md#fluid). A parameter
  without a default is required: set it with `update_params` before the first call.
- Properties come from each stream's `Fluid`; unless a module says otherwise it uses the
  constant liquid heat capacity `cp_l` and density `rho_l` of that fluid.
- Unless stated, a module has no pressure loss and passes mass flow and fluid unchanged.
- Reverse (negative) mass flow raises `gm.errors.PhysicsError` in every module except
  `Filter`, `Degasser`, `PressurizationTank`, the wells and `InjectionReservoir`; zero flow is
  always a valid stopped state.
- Bad design data found at call time (inconsistent parameters, a geometry outside a relation's
  range) raises `ValidationError`; inputs outside a model's domain raise
  `PhysicsError`.
- Energy that leaves or enters a leaf outside its streams uses the fixed additive outputs of
  [types.md](types.md#energy-outputs-and-balances): `electricity`, `fuel`, `heat_absorbed`,
  `heat_loss`, `heat_supplied`, `electricity_generated` and the signed `heat_accumulation`.
- **Energy audit** below states what `energy_balance(module, result)` shows for one call.
  *Closed* means `relative_residual < 1e-12` and `mass_balance(...)["residual"] == 0` are
  tested. Otherwise the documented residual is named; it is never hidden by an invented loss.
- Stateful modules integrate their `State` values in `_advance_states`; call them with
  `module.step(state, dt, inlets)`. A plain call evaluates at the initial states.
- Every leaf is written with `gemini.ops`, so it traces into a computation graph. The exceptions
  are the graph breaks, which run tick by tick: `ThermalDecline`, `AquiferStorage`,
  `BoreholeField`, `ThermalStorage`, `IceStorage` and `PIDController`, stateful until `scan` exists
  (see [native-engine.md](native-engine.md)). Structural parameters, fixed in a trace and a graph
  cache guard, are `ProductionReservoir`/`InjectionReservoir` `drainage_radius`,
  `ProductionWell.esp_depth` and `Degasser.separation_efficiency`.

## Overview

| Category | Class | Ports (in -> out) | State | Model |
| --- | --- | --- | --- | --- |
| Subsurface | `ProductionReservoir` | none -> `sandface_out` | no | linear IPR, radial diagnostics |
| Subsurface | `InjectionReservoir` | `sandface_in` -> none | no | linear injectivity |
| Subsurface | `ThermalDecline` | `fluid_in` -> `fluid_out` | yes | Gringarten–Sauty breakthrough |
| Subsurface | `BoreholeField` | `fluid_in` -> `fluid_out` | yes | lumped ground, steady-flux cell |
| Subsurface | `DownholeHeatExchanger` | `fluid_in` -> `fluid_out` | no | Ramey profile, coaxial |
| Wells | `ProductionWell` | `bottom_in` -> `wellhead_out` | no | DPDT path traversal upward |
| Wells | `InjectionWell` | `wellhead_in` -> `bottom_out` | no | DPDT path traversal downward |
| Pumps | `ESP` | `fluid_in` -> `fluid_out` | no | TNO polynomial head and power, isothermal |
| Pumps | `InjectionPump` | `fluid_in` -> `fluid_out` | no | setpoint or curve head, `Q dp / eta` |
| Pumps | `CentrifugalPump` | `fluid_in` -> `fluid_out` | no | quadratic head, affinity laws |
| Pumps | `LineShaftPump` | `fluid_in` -> `fluid_out` | no | ESP curves plus shaft friction |
| Pumps | `GasCompressor` | `fluid_in` -> `fluid_out` | no | ideal-gas intercooled stages |
| Treatment | `Filter` | `fluid_in` -> `fluid_out` | no | quadratic clean loss, clogging health |
| Treatment | `Degasser` | `fluid_in` -> `liquid_out`, `gas_out` | no | free-gas split and vessel pressure |
| Treatment | `Blowdown` | `fluid_in` -> `fluid_out`, `waste_out` | no | commanded bleed |
| Treatment | `Desander` | `fluid_in` -> `fluid_out` | no | constant removal share, quadratic loss |
| Treatment | `InhibitorDosing` | `fluid_in` -> `fluid_out` | no | dose proportional to flow |
| Treatment | `Vent` | `fluid_in` -> `fluid_out` | no | vent or flare emissions |
| Treatment | `Flare` | `gas_in` -> none | no | burns its gas, emissions from the composition |
| Exchangers | `HeatExchanger` | `hot_in`, `cold_in` -> `hot_out`, `cold_out` | no | effectiveness-NTU |
| Exchangers | `Cooler` | `fluid_in` -> `fluid_out` | no | dry or wet approach, fan power |
| Heating | `Boiler` | `fluid_in`, `fuel_in` -> `fluid_out`, `gas_out` | no | setpoint duty, co-produced gas first |
| Heating | `ElectricBoiler` | `fluid_in` -> `fluid_out` | no | setpoint duty, capacity, efficiency |
| Heating | `HeatPump` | `source_in`, `sink_in` -> `source_out`, `sink_out` | no | Carnot or Lorenz COP |
| Heating | `CHP` | `fluid_in`, `fuel_in` -> `fluid_out`, `gas_out` | no | Willans line, dump cooler |
| Cooling | `AbsorptionUnit` | three `*_in` -> `*_out` circuits | no | characteristic equation |
| Cooling | `AdsorptionChiller` | three `*_in` -> `*_out` circuits | no | characteristic equation |
| Power | `ORC` | `fluid_in` -> `fluid_out` | no | Lorenz-cycle fraction, bypass cap |
| Power | `Separator` | `fluid_in` -> `liquid_out`, `gas_out` | no | IF97 flash |
| Power | `FlashTurbine` | `fluid_in` -> `fluid_out` | no | Baumann wet expansion, condenser |
| Power | `GridConnection` | none | no | net import/export, limits, tariff |
| Storage | `AquiferStorage` | `injection_in` -> `production_out` | yes | warm and cold stores |
| Storage | `ThermalStorage` | `charge_*`, `discharge_*` | yes | fully mixed tank |
| Storage | `IceStorage` | `fluid_in` -> `fluid_out` | yes | lumped ice store, piecewise exact |
| Piping | `Pipe` | `fluid_in` -> `fluid_out` | no | Darcy–Weisbach, static head, exponential loss |
| Piping | `GasGrid` | none -> `gas_out` | no | a fuel source without flow, marks grid gas |
| Piping | `GasMakeup` | `fluid_in` -> `fluid_out` | no | marks that a burner may draw grid gas |
| Piping | `Valve` | `fluid_in` -> `fluid_out` | no | IEC 60534 liquid sizing, inherent curve |
| Piping | `Splitter` | `fluid_in` -> `branch1_out`, `branch2_out` | no | commanded mass split |
| Piping | `Mixer` | `branch1_in`, `branch2_in` -> `fluid_out` | no | adiabatic, lower pressure |
| Piping | `PressurizationTank` | `fluid_in` -> `fluid_out` | no | outlet at the pressure setpoint |
| Demand | `HeatConsumer` | `supply_in` -> `return_out` | no | demand capped by return floor |
| Demand | `CoolingConsumer` | `supply_in` -> `return_out` | no | sensible, latent, dew point |
| Control | `PIDController` | none | yes | discrete PID, clamping anti-windup |
| Plants | `Doublet` | `return_in` -> `supply_out` | no | reservoir, wells, ESP, injector, sink |
| Plants | `MultiWellPlant` | `return_in` -> `supply_out` | no | N producers, M injectors |
| Plants | `HeatingSubstation` | `supply_in` -> `return_out` | no | valve, HX, heat consumer |
| Plants | `CoolingSubstation` | `supply_in` -> `return_out` | no | valve, HX, cooler |
| Plants | `DistrictNetwork` | `supply_in` -> `return_out` | no | pump, pipes, substations |
| Plants | `ATESPlant` | `return_in` -> `supply_out` | child | ATES, pump, HX, heat pump |

## Pumps

### ESP

Electrical submersible pump inside a production well, on the retained TNO R11363 polynomial
basis (`gemini.physics.pumps`).

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters**:
  - `stage_count` (`Count`, required).
  - `head_coefficients`, `power_coefficients` (`list[float]`, shape 6, calibratable, required): ft of head
    and bhp per stage at 60 Hz with flow in bbl/day (mixed legacy units, see
    [types.md](types.md#quantities-and-declarations)).
  - `pump_type` (`str | None`, default `None`) and `setting_depth` (`Length`, default 0): read only
    by the legacy import and export.
  - `motor_efficiency` (`Efficiency`, default 1, which preserves every legacy power number).
  - `minimum_flow` (default 0), `maximum_flow` (default 1 m3/s), `best_efficiency_flow` (default 0.04 m3/s):
    operating window and best-efficiency flow at 60 Hz, scaled by `frequency / 60 Hz`.
  - `correction_factors` (`(Dimensionless, PressureDifference)`, default `(1, 0)`) and `tubing`
    (`Length | None`, default `None`): read only by the legacy import and export.
  - `drift_threshold` (`Fraction`, default 0.10): health alarm limit on relative drift.
- **Controls**: `frequency` (`Frequency`, required). **Boundaries, states**: none.
- **Outputs**: `head`, `power` (shaft), `efficiency` (`Dimensionless`, may exceed one),
  `discharge_pressure` (all soft sensors), `flow`, `is_in_operating_window`, `best_efficiency_ratio`,
  `electricity`.
- **Model**: `H = pumps.head(Q, f, N, head_coefficients)` with `H ~ (f/60)^2`,
  `P = pumps.power(Q, f, N, power_coefficients)` with `P ~ (f/60)^3`, `discharge.p = suction.p + H`,
  `electricity = P / motor_efficiency`. Efficiency is the retained hydraulic-efficiency
  formula, zero below 0.1 W shaft power. Under `runtime.set_precision("float32")` the
  coefficients use NumPy float32 for golden parity.
- **Physics**: `diagnostics.relative_drift`, `diagnostics.remaining_margin`, `energy.input_power`,
  `pumps.best_efficiency_ratio`, `pumps.esp_efficiency`, `pumps.head`,
  `pumps.is_in_operating_window`, `pumps.power`, `pumps.speed_ratio`
- **Health**: worst relative drift of measured `power`, `head` and `discharge_pressure`, alarm
  above `drift_threshold` or outside the operating window.
- **Assumptions and validity**: isothermal; empirical curves valid on their fitted flow range.
  Reverse flow raises `PhysicsError`. The fits
  (`gm.analysis.fit_head_coefficients`, `gm.analysis.fit_head_correction`) are in `gm.analysis`;
  `head_curve` is the private helper of `gm.analysis.pump_curve`.
- **Energy audit**: unresolved pump power. The pump is isothermal and allocates no
  electricity to work or loss, so `residual == unresolved_power == electricity` and
  `thermal_residual` closes. See [refactor-notes.md](refactor-notes.md).

```python
import gemini as gm
from gemini.modules import ESP, energy_balance

esp = ESP().update_params(
    stage_count=12,
    head_coefficients=[83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21],
    power_coefficients=[10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
    motor_efficiency=0.9,
)
result = esp(fluid_in=gm.Stream(flow="200 m3/h", T="70 C", p="10 bar"), frequency="50 Hz")
assert round(result.outputs.get("head", unit="bar"), 2) == 16.23
assert round(result.outputs.electricity) == 118246
assert energy_balance(esp, result)["unresolved_power"] == result.outputs.electricity
```

### InjectionPump

Injection (booster) pump that raises the brine to a discharge pressure.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters**: `stage_count` (`Count | None`, default `None`), `pump_type` (default
  `"unspecified"`, read only by the legacy import and export), `efficiency` (`Efficiency`,
  default 0.7, calibratable; the example plant selects 0.8, see
  [refactor-notes.md](refactor-notes.md)), `head_coefficients`, `power_coefficients`
  (`list[float] | None`, shape 6, default `None`, ESP basis).
- **Controls**: `pressure_setpoint` (`Pressure | None`, default `None`), `frequency`
  (`Frequency`, default 60 Hz, used with curves).
- **Outputs**: `head`, `power`, `discharge_pressure` (soft sensors), `electricity`.
- **Model**: with `head_coefficients` (and `stage_count`) the head is the ESP polynomial; otherwise
  `head = pressure_setpoint - suction.p`. Power is `pumps.power` when both curves are given,
  else `Q head / efficiency`; `electricity = power`.
- **Physics**: `energy.input_power`, `pumps.head`, `pumps.hydraulic_power`, `pumps.power`
- **Validity**: a negative head (setpoint below suction) and reverse flow raise
  `PhysicsError`; neither a setpoint nor a head curve raises `ValidationError`.
- **Energy audit**: unresolved pump power, as `ESP`.

```python
import gemini as gm
from gemini.modules import InjectionPump

pump = InjectionPump().update_params(efficiency=0.8)
result = pump(fluid_in=gm.Stream(flow="150 m3/h", T="40 C", p="5 bar"), pressure_setpoint="51.5 bar")
assert round(result.outputs.get("head", unit="bar"), 6) == 46.5
assert round(result.outputs.electricity, 1) == 242187.5
```

### CentrifugalPump

Variable-speed booster or circulation pump (surface centrifugal pump on a drive) with a
quadratic head curve and affinity-law speed scaling. It replaces the former `BoosterPump`.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters** (all required; curves and efficiencies are pump-specific datasheet values):
  - `head_coefficients` (`list[float]`, shape 3, calibratable): `c0` [Pa], `c1` [Pa s/m3],
    `c2` [Pa s2/m6] of `H(Q)` at the rated speed.
  - `rated_frequency` (`Frequency`): supply frequency of the head curve.
  - `best_efficiency` (`Efficiency`, calibratable), `best_efficiency_flow` (`VolumeFlow`, > 0):
    hydraulic efficiency and flow at the best-efficiency point (BEP) at rated speed.
  - `motor_efficiency` (`Efficiency`): wire to shaft.
- **Controls**: `frequency` (`Frequency`). **Boundaries, states**: none.
- **Outputs**: `flow`, `head` (soft sensor), `hydraulic_power`, `shaft_power` (soft sensor),
  `efficiency` (`Fraction`, hydraulic), `electricity`, `heat_loss`, `fluid_out_T`.
- **Model**: with `s = frequency / rated_frequency` and the suction volume flow `Q`:
  - `H = c0 s^2 + c1 s Q + c2 Q^2`;
  - `x = Q / (s Q_bep)`, `eta = eta_bep x (2 - x)` (Ulanicki, Kahler and Coulbeck 2008, J. Water
    Resour. Plann. Manage. 134(1), 88-93);
  - `P_hydraulic = Q H`, `P_shaft = P_hydraulic / eta`, `electricity = P_shaft / eta_motor`,
    `heat_loss = electricity - P_shaft`;
  - `discharge.p = suction.p + H`, `discharge.T = suction.T + (P_shaft - P_hydraulic) / (m_dot
    cp)`: pump losses heat the liquid, motor losses go to the room.
- **Physics**: `energy.input_power`, `heat_transfer.temperature_change`,
  `pumps.best_efficiency_ratio`, `pumps.centrifugal_head`, `pumps.hydraulic_power`,
  `pumps.parabolic_efficiency`, `pumps.speed_ratio`
- **Assumptions**: incompressible liquid, constant `cp`, efficiency independent of speed
  (affinity laws, about 0.5 to 1.1 of rated speed), no leakage or recirculation.
- **Validity**: zero flow is a stopped pump (no head, no power). `x >= 2`, a negative head or
  reverse flow raise `PhysicsError` (pump off its curve). Deadhead (running against a
  closed valve) is outside the steady model.
- **Energy audit**: first-law closed when the flow work `Q H` is counted; `energy_balance`
  excludes pressure energy, so its `residual` equals `hydraulic_power` and `unresolved_power`
  is zero (both tested).

```python
import gemini as gm
from gemini.modules import CentrifugalPump

pump = CentrifugalPump().update_params(
    head_coefficients=[6e5, 0, -4e7], rated_frequency="50 Hz", best_efficiency=0.8,
    best_efficiency_flow="180 m3/h", motor_efficiency=0.95,
)
result = pump(fluid_in=gm.Stream(flow="150 m3/h", T="60 C", p="3 bar"), frequency="45 Hz")
assert round(result.outputs.get("head", unit="bar"), 3) == 4.166
assert round(result.outputs.efficiency, 3) == 0.796
assert round(result.outputs.electricity) == 22963
```

### LineShaftPump

Downhole multistage (vertical turbine) pump driven by a surface motor through a line shaft.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters** (all required): `stage_count` (`Count`), `head_coefficients`, `power_coefficients`
  (`list[float]`, shape 6, calibratable, ESP basis), `setting_depth` (`Length`, the shaft
  length), `shaft_friction_loss` (`LinearPower`, >= 0, friction power per metre at 60 Hz),
  `motor_efficiency` (`Efficiency`).
- **Controls**: `frequency` (`Frequency`). **Boundaries, states**: none.
- **Outputs**: `flow`, `head` (soft sensor), `pump_power`, `shaft_friction_power`,
  `shaft_power` (soft sensor), `efficiency` (`Dimensionless`, `Q H / P_pump`, zero below 0.1 W,
  not bounded by one), `electricity`.
- **Model**: `H` and `P_pump` as `ESP`; `P_friction = shaft_friction_loss * setting_depth * f /
  60 Hz` (constant bearing friction torque, the form of manufacturer line-shaft friction
  tables; ANSI/HI 2.3); `P_shaft = P_pump + P_friction`, `electricity = P_shaft /
  motor_efficiency`; `discharge.T = suction.T`.
- **Physics**: `energy.input_power`, `pumps.head`, `pumps.line_shaft_friction_power`, `pumps.power`,
  `pumps.pump_efficiency`, `pumps.speed_ratio`
- **Assumptions**: isothermal like `ESP`, because the empirical polynomials do not guarantee
  `P_pump >= Q H`. Thrust bearing, shaft stretch and column friction are not modelled.
- **Validity**: reverse flow, a negative head or a negative pump power raise
  `PhysicsError`; zero flow runs at shutoff head and power.
- **Energy audit**: unresolved pump power (it is in the pump tuple of `balance.py`).

```python
import gemini as gm
from gemini.modules import LineShaftPump

pump = LineShaftPump().update_params(
    stage_count=12,
    head_coefficients=[83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21],
    power_coefficients=[10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
    setting_depth="300 m", shaft_friction_loss=5, motor_efficiency=0.9,
)
out = pump(fluid_in=gm.Stream(flow="200 m3/h", T="70 C", p="10 bar"), frequency="50 Hz").outputs
assert round(out.get("head", unit="bar"), 2) == 16.23
assert out.shaft_friction_power == 1250.0 and round(out.electricity) == 119635
```

### GasCompressor

Electric compressor for the non-condensable gas from a `Degasser` or `Separator`, with equal
intercooled stages.

- **Ports**: `fluid_in` -> `fluid_out`. `m_dot` is the gas mass flow; the stream's `fluid` is
  passed through and its liquid property model is not used.
- **Parameters**: `isentropic_efficiency` (`Efficiency`, calibratable, required; typically
  0.7 to 0.85), `heat_capacity_ratio` (`Ratio`, > 1, required), `gas_specific_heat`
  (`SpecificHeat`, required; CO2 about 846 J/kg/K at 300 K), `stage_count` (`Count`, default
  1), `motor_efficiency` (`Efficiency`, required).
- **Controls**: `pressure_setpoint` (`Pressure`, the discharge pressure).
- **Outputs**: `pressure_ratio`, `shaft_power` (soft sensor), `electricity`, `fluid_out_T`
  (soft sensor), `heat_loss`.
- **Model** (`modules/pumps/_physics.py`; GPSA Engineering Data Book, 14th ed., Section 13, Z = 1):
  `r = pressure_setpoint / p_s`, stage ratio `r^(1/N)`,
  `T_2 = T_1 + T_1 (r^((k-1)/(k N)) - 1) / eta_s`, `P_shaft = m_dot N cp (T_2 - T_1)`,
  `electricity = P_shaft / eta_motor`, `heat_loss = electricity - P_shaft / N` (intercooler
  duty plus motor loss). The gas leaves the last stage at `T_2` (no aftercooler).
- **Physics**: `compression.heat_rejected`, `compression.overall_pressure_ratio`,
  `compression.shaft_power`, `compression.specific_compression_work`,
  `compression.stage_outlet_temperature`, `compression.stage_pressure_ratio`, `energy.input_power`
- **Assumptions and validity**: ideal gas with constant `k` and `cp`, perfect intercooling to
  the suction temperature without pressure loss; stage ratios up to about 4. A setpoint below
  the suction pressure or reverse flow raises `PhysicsError`; zero flow draws no power.
- **Energy audit**: closed in gas enthalpy, `electricity = m_dot cp (T_2 - T_1) + heat_loss`
  (tested). `energy_balance` values streams with the liquid `cp_l`, so its residual
  `m_dot (T_2 - T_1) (cp - cp_l)` is not meaningful here.

```python
import gemini as gm
from gemini.modules import GasCompressor

compressor = GasCompressor().update_params(
    isentropic_efficiency=0.75, heat_capacity_ratio=1.29, gas_specific_heat=846,
    stage_count=2, motor_efficiency=0.95,
)
out = compressor(
    fluid_in=gm.Stream(m_dot=0.05, T="40 C", p="1.2 bar"), pressure_setpoint="12 bar"
).outputs
assert round(out.pressure_ratio, 9) == 10 and round(out.shaft_power) == 10434
assert round(out.discharge_T, 1) == 436.5
```

## Piping

The pipe and the valve model a single-phase liquid in the forward direction: a free-gas fraction
(`fluid.gas_mass_fraction > 0`) raises `PhysicsError`.

### Pipe

Surface pipeline with wall friction, an elevation change and heat exchange with its
surroundings.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters**:
  - `length` (`Length`, > 0, required), including the equivalent length of fittings.
  - `inner_diameter` (`Length`, > 0, required).
  - `roughness` (`Length`, default 4.5e-5 m, new commercial steel: Moody 1944, Crane TP-410).
  - `elevation_change` (`Elevation`, signed, required): outlet minus inlet height.
  - `heat_transfer_coefficient` (`HeatTransferCoefficient`, required): overall coefficient on the inner wall
    area `pi d L`, the convention of the well path model.
- **Boundaries**: `ambient_temperature` (`Temperature`, required).
- **Outputs**: `pressure_drop` (friction plus static head; negative for a descending pipe at
  low flow), `velocity`, `fluid_out_T`, `heat_loss`, `heat_absorbed` (nonnegative; the one that
  applies is nonzero).
- **Model**:
  - `v = m_dot / (rho pi d^2 / 4)`, `Re = rho v d / mu`;
  - friction `f L/d rho v^2 / 2`: laminar `f = 64/Re` up to Re = 2300, Swamee–Jain (1976) from
    Re = 4000 (`hydraulics.darcy_weisbach_dp`), linear interpolation of the drop in between
    (a continuous bridge, no physical claim);
  - `p_out = p_in - friction_pressure_drop - rho g dz`;
  - `T_out = T_amb + (T_in - T_amb) exp(-NTU)`, `NTU = U pi d L / (m_dot cp)` (Incropera et al.
    2007, Section 8.3), the exact profile for constant U, cp and ambient.
- **Physics**: `geometry.mean_velocity`, `heat_transfer.ambient_effectiveness`,
  `heat_transfer.effectiveness_outlet_temperature`, `heat_transfer.heat_rate`,
  `heat_transfer.signed_parts`, `hydraulics.hydrostatic_dp`, `hydraulics.pipe_conductance`,
  `hydraulics.pipe_friction_drop`
- **Assumptions**: steady (no heat capacity or transit time), constant properties, uniform U
  and ambient, no separate fitting losses. The legacy `heat_transfer.pipe_temperature_change`
  is its first-order expansion and is not used because it overshoots ambient for NTU > 1.
- **Validity**: relative roughness 1e-6 to 1e-2, Re up to 1e8. `|elevation_change| > length`
  raises `ValidationError`; a negative outlet pressure, free gas and reverse flow raise
  `PhysicsError`. Zero flow keeps the static head and exchanges no heat.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Pipe, energy_balance

pipe = Pipe().update_params(
    length="1500 m", inner_diameter="0.125 m", elevation_change="12 m", heat_transfer_coefficient="0.8 W/m2/K"
)
supply = gm.Stream(flow="40 m3/h", T="80 C", p="6 bar")
result = pipe(fluid_in=supply, ambient_temperature="10 C")
assert round(result.outputs.get("pressure_drop", unit="bar"), 3) == 2.134
assert round(result.outputs.heat_loss) == 32821
assert energy_balance(pipe, result)["relative_residual"] < 1e-12
```

### Valve

Control valve; isenthalpic, so the temperature is unchanged.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters**: `flow_coefficient` (`FlowCoefficient`, > 0, required): rated Kv in SI
  m3/s/Pa^0.5, a catalogue value as `"63 m3/h/bar^0.5"`; `characteristic`
  (`"linear"` or `"equal_percentage"`, default `"equal_percentage"`) and `rangeability`
  (`Ratio`, > 1, default 50), both typical for globe control valves (Emerson, Control Valve
  Handbook, 5th ed., 2017).
- **Controls**: `opening` (`Fraction`).
- **Outputs**: `pressure_drop`, `effective_flow_coefficient` (0 when closed).
- **Model**: IEC 60534-2-1:2011 non-choked turbulent liquid flow, `dp = (rho / 1000) (q /
  Kv_eff)^2` with `q = m_dot / rho`; inherent characteristic (IEC 60534-2-4) with `Phi_0 = 1/R`:
  linear `Phi_0 + (1 - Phi_0) h`, equal percentage `R^(h - 1)`; `Kv_eff = Phi(h) Kv` for
  `h > 0` and 0 at `h = 0`.
- **Physics**: `hydraulics.valve_flow_coefficient`, `hydraulics.valve_pressure_drop`
- **Assumptions**: no choked flow or cavitation (check the outlet against the vapour pressure),
  no installed characteristic or Reynolds correction, constant density; the throttling
  temperature rise (about 0.024 K per bar of water) is neglected.
- **Validity**: flow through a closed valve, a drop larger than the inlet pressure, free gas or
  reverse flow raise `PhysicsError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Valve

valve = Valve().update_params(flow_coefficient="63 m3/h/bar^0.5")
result = valve(fluid_in=gm.Stream(flow="40 m3/h", T="80 C", p="6 bar"), opening=0.7)
assert round(result.outputs.get("pressure_drop", unit="bar"), 3) == 4.215
kv = gm.units.convert(result.outputs.effective_flow_coefficient, "m3/s/Pa^0.5", "m3/h/bar^0.5")
assert round(kv, 2) == 19.48
```

### Splitter

Ideal tee that divides a feed into two branches.

- **Ports**: `fluid_in` -> `branch1_out`, `branch2_out`.
- **Controls**: `split_fraction` (`Fraction`): share of the mass flow sent to `branch2_out`.
- **Parameters, boundaries, states, outputs**: none; read the branch flows from the outlets,
  for example `Output.of(self.splitter.branch2_out.field("m_dot"))` in a composite.
- **Model**: `m_second = x m_feed`, `m_first = m_feed - m_second`, both at feed T, p and fluid.
- **Physics**: `separation.split_flow`
- **Assumptions**: no tee loss or heat exchange; the commanded split stands for the balancing
  valves or branch resistances that set it; no hydraulic network solution.
- **Validity**: reverse flow raises `PhysicsError` (a reversed splitter is a `Mixer`).
- **Energy audit**: closed (`m - x m` may round by one ulp).

```python
import gemini as gm
from gemini.modules import Splitter

branches = Splitter()(fluid_in=gm.Stream(m_dot=10, T="80 C", p="6 bar"), split_fraction=0.3)
assert branches.outlets.branch2_out.m_dot == 3.0 and branches.outlets.branch1_out.m_dot == 7.0
```

### Mixer

Adiabatic junction mixing two streams of the same fluid.

- **Ports**: `branch1_in`, `branch2_in` -> `fluid_out`.
- **Outputs**: `fluid_out_T`, `pressure_imbalance` (`|p_1 - p_2|`, the pressure discarded).
- **Model**: `m = m_1 + m_2`, `T = (m_1 cp_1 T_1 + m_2 cp_2 T_2) / (m_1 cp_1 + m_2 cp_2)`,
  `p = min(p_1, p_2)`. A junction has one pressure: in the real network the higher branch is
  throttled by its own resistance, which a sequential model cannot represent, and the lower
  pressure never creates pressure energy. A large `pressure_imbalance` flags unbalanced
  upstream branches.
- **Physics**: `heat_transfer.mixed_temperature`
- **Validity**: different fluids raise `ValidationError`; reverse flow raises
  `PhysicsError`; zero total flow gives the mean inlet temperature, which carries no
  energy.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Mixer

hot = gm.Stream(flow="40 m3/h", T="80 C", p="6 bar")
cold = gm.Stream(flow="10 m3/h", T="40 C", p="5.5 bar")
mixed = Mixer()(branch1_in=hot, branch2_in=cold)
assert round(mixed.outputs.mixed_out_T - 273.15, 6) == 72.0
assert mixed.outlets.fluid_out.p == 5.5e5 and mixed.outputs.pressure_imbalance == 5e4
```

### GasGrid

Fuel source of a burner without co-produced gas: `grid.fluid_out` to `boiler.fuel_in`.

- **Ports**: `fluid_out` (gas), no inlet.
- **Parameters**: `composition` (mole fractions, default `gas.GRID_COMPOSITION`, a published grid
  analysis).
- **Model**: the outlet carries no flow at normal conditions and marks that the burner may draw grid
  gas: purchased gas enters no stream, the burner reports it.
- **Energy audit**: closed.

### GasMakeup

In-line between a degasser and a burner: `fluid_in` -> `fluid_out` (gas), with `composition` as `GasGrid`.
The stream passes unchanged but for the mark that the burner may draw grid gas, so it shows the grid
connection on the flowsheet and moves no gas. **Energy audit**: closed.

### PressurizationTank

Pressure-maintenance (expansion) vessel that holds a closed circuit at its pressure setpoint
(EN 12828:2012+A1:2014; VDI 4708-1:2012).

- **Ports**: `fluid_in` -> `fluid_out`.
- **Controls**: `pressure_setpoint` (`Pressure`, > 0).
- **Outputs**: `pressure_correction`: setpoint minus inlet pressure; positive is pressure the
  station adds, negative pressure it relieves. A persistent large value flags a loop pressure
  profile that does not match the design.
- **Model**: the outlet leaves at `pressure_setpoint` with the inlet flow, temperature and
  fluid. Stateless by decision: at hourly or 15-minute steps the vessel holds its setpoint, and
  a water-volume state would change the vessel level but no circuit pressure or temperature.
- **Physics**: none.
- **Assumptions**: make-up and spill flows and the station's pump electricity are not
  modelled. Any flow direction is accepted.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import PressurizationTank

circuit = gm.Stream(m_dot=10, T="70 C", p="5.5 bar")
held = PressurizationTank()(fluid_in=circuit, pressure_setpoint="3 bar")
assert held.outlets.fluid_out.p == 3e5
assert held.outputs.get("pressure_correction", unit="bar") == -2.5
```

## Treatment

### Filter

Filter with a quadratic clean-filter pressure loss and a clogging diagnostic.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters**: `nominal_pressure_drop` (default 1600 Pa) at `nominal_mass_flow` (default 149 m3/h of brine
  at 1068 kg/m3 = 44.2 kg/s), both from the example plant; `clogging_pressure_drop` (default 0.5 bar).
- **Outputs**: `pressure_drop` (soft sensor).
- **Model**: `pressure_drop = nominal_pressure_drop (m_dot / nominal_mass_flow)^2`.
- **Physics**: `diagnostics.performance_ratio`, `diagnostics.remaining_margin`,
  `hydraulics.quadratic_pressure_drop`
- **Health**: alarm when the measured `pressure_drop` exceeds `clogging_pressure_drop`.
- **Assumptions**: solids loading and particle capture are not modelled. The quadratic law
  also scales reverse flow.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Filter

brine = gm.Fluid(density=1068)
result = Filter()(fluid_in=gm.Stream(flow="149 m3/h", T="80 C", p="5 bar", fluid=brine))
assert round(result.outputs.get("pressure_drop", unit="bar"), 9) == 0.016
```

### Degasser

Separates a share of the free gas carried by the brine and applies the vessel pressure.

- **Ports**: `fluid_in` -> `liquid_out`, `gas_out`.
- **Parameters**: `outlet_pressure` (`Pressure | None`, default `None`: use
  `nominal_pressure_drop`), `nominal_pressure_drop` (default 14 900 Pa, Sep_Pin/Sep_Pout of the
  example plant), `heat_transfer_coefficient` (default 0, read only by the legacy import and
  export), `separation_efficiency` (`Fraction`, default 0;
  no industry-typical value, set it from design data or a measured gas flow).
- **Outputs**: `gas_mass_flow`, `pressure_drop` (soft sensors).
- **Model**: with `eta = separation_efficiency` and `x = inlet.fluid.gas_mass_fraction`:
  `gas.m_dot = eta x m_dot`, `liquid.m_dot = m_dot - gas.m_dot`, liquid gas fraction
  `(1 - eta) x / (1 - eta x)`; both outlets at `outlet_pressure` (or `p_in - nominal_pressure_drop`) and the inlet
  temperature. The default `eta = 0` reproduces the former liquid-only model exactly.
- **Physics**: `separation.degasser_split`
- **Assumptions**: isothermal, no exsolution of dissolved gas, no latent or expansion heat, a
  lumped efficiency (no residence time, level or Henry's law). The `gas` stream carries a
  `kind="gas"` fluid with the inlet's `gas_composition`, at the vessel pressure, and the liquid's
  `cp_l`; an inlet without a composition gives it the liquid's fluid, whose property snapshot does
  not describe the gas. Reverse flow scales both outlets.
- **Energy audit**: closed (every stream is valued at `cp_l`, an audit convention for the gas).

```python
import gemini as gm
from gemini.modules import Degasser

brine = gm.Fluid(gas_mass_fraction=0.002)
degassed = Degasser().update_params(separation_efficiency=0.95)(
    fluid_in=gm.Stream(flow="40 kg/s", T="80 C", p="5 bar", fluid=brine)
)
assert round(degassed.outputs.gas_mass_flow, 12) == 0.076
assert degassed.outputs.pressure_drop == 14900
```

### Blowdown

Continuous blowdown: bleeds a commanded share of a circuit's flow to drain to limit dissolved
and suspended solids (ASME 1994, consensus on boiler water chemistry; ASHRAE Handbook, HVAC
Systems and Equipment, "Cooling Towers").

- **Ports**: `fluid_in` -> `fluid_out`, `waste_out`.
- **Controls**: `blowdown_fraction` (`Fraction`, required): share of the feed sent to drain;
  for make-up `M` at `C` cycles of concentration it is `M / C`.
- **Outputs**: `blowdown_mass_flow`. No `heat_loss`: the drained stream carries its enthalpy
  out of the plant through its port.
- **Model**: `waste_out.m_dot = f m_dot`, `fluid_out.m_dot = m_dot - f m_dot`, both at
  feed T, p and fluid.
- **Physics**: `separation.split_flow`
- **Assumptions and validity**: ideal split, no valve loss or flash; reverse flow raises
  `PhysicsError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Blowdown

bled = Blowdown()(fluid_in=gm.Stream(m_dot=40, T="80 C", p="5 bar"), blowdown_fraction=0.01)
assert bled.outputs.blowdown_mass_flow == 0.4 and bled.outlets.fluid_out.m_dot == 39.6
```

### Desander

Hydrocyclone sand separator ahead of heat exchangers and injection.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters** (all required, design specific): `separation_efficiency` (`Fraction`, lumped
  removal share of the sand mass), `nominal_pressure_drop` (`PressureDifference`, >= 0, of the order of
  1 bar) at `nominal_mass_flow` (`MassFlow`, > 0).
- **Boundaries**: `sand_concentration` (`MassConcentration`, kg of sand per m3 of liquid,
  accepted as `"20 mg/l"` or `"20 g/m3"`).
- **Outputs**: `pressure_drop`, `sand_removal_rate` (soft sensors),
  `residual_sand_concentration`.
- **Model**: `Q = m_dot (1 - x_gas) / rho`, `sand_removal_rate = eta c Q`, residual `(1 - eta)
  c`, `pressure_drop = nominal_pressure_drop (m_dot / nominal_mass_flow)^2`.
- **Physics**: `fluid.liquid_volume_flow`, `hydraulics.quadratic_pressure_drop`,
  `separation.cyclone_sand`
- **Assumptions**: one constant efficiency lumps the grade-efficiency curve (Svarovsky 2000,
  *Solid-Liquid Separation*, 4th ed., "Hydrocyclones"); streams carry no solids, so the sand is
  only reported.
- **Validity**: reverse flow or a loss above the inlet pressure raise `PhysicsError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Desander

desander = Desander().update_params(
    separation_efficiency=0.9, nominal_pressure_drop="1 bar", nominal_mass_flow="45 kg/s"
)
result = desander(fluid_in=gm.Stream(m_dot=45, T="80 C", p="5 bar"), sand_concentration="20 mg/l")
assert round(result.outputs.sand_removal_rate, 9) == 0.00081
assert result.outputs.get("pressure_drop", unit="bar") == 1.0
```

### InhibitorDosing

Scale or corrosion inhibitor injection proportional to the treated flow.

- **Ports**: `fluid_in` -> `fluid_out` (stream unchanged).
- **Parameters**: `product_concentration` (`Fraction`, > 0, required): active share of the
  commercial product.
- **Controls**: `dose` (`Fraction`): product mass per treated mass, accepted as `"10 ppm"`;
  typical geothermal scale-inhibitor doses are a few to some tens of ppm (Gallup 2009,
  *Geothermics* 38, 326-334).
- **Outputs**: `product_mass_flow = dose m_dot`, `active_mass_flow = product_concentration
  product_mass_flow`.
- **Physics**: `separation.dosing_flows`
- **Assumptions**: the dosed mass is not added to the stream (it is below flowmeter
  resolution, and adding it would need a product inlet), so the neglected mass is
  `product_mass_flow`, a relative error equal to `dose`. Pump power, quill loss and cost are not
  modelled; multiply `product_mass_flow` by the product price. Reverse flow raises
  `PhysicsError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import InhibitorDosing

dosing = InhibitorDosing().update_params(product_concentration=0.3)
result = dosing(fluid_in=gm.Stream(m_dot=40, T="80 C", p="5 bar"), dose="10 ppm")
assert round(result.outputs.product_mass_flow, 12) == 4e-4
assert round(result.outputs.active_mass_flow, 12) == 1.2e-4
```

### Vent

Vent stack or flare releasing separated non-condensable gas, with CO2 and methane emissions.

- **Ports**: `fluid_in` -> `fluid_out`: the gas as released at the stack or flare tip, upstream of
  combustion, so mass and energy leave the plant through a port.
- **Parameters**: `mode` (`"vent"` or `"flare"`, required), `co2_mass_fraction` (`Fraction`,
  required, from a gas analysis), `methane_mass_fraction` (`Fraction`, default 0, the
  combustible share treated as methane), `heating_value` (`SpecificEnthalpy`, default
  50.0 MJ/kg, methane LHV from the NIST Chemistry WebBook), `combustion_efficiency`
  (`Efficiency`, default 0.98, US EPA AP-42, 5th ed., section 13.5).
- **Outputs**: `vented_mass_flow`, `co2_emission`, `methane_emission` (`MassFlow`), `fuel`,
  `heat_loss` (zero when venting).
- **Model**: burnt methane `m_b = eta_c x_CH4 m` when flaring; `co2_emission = x_CO2 m + m_b
  M_CO2 / M_CH4`; `methane_emission = x_CH4 m - m_b`; `fuel = heat_loss = m_b heating_value`.
- **Physics**: `combustion.flare_emissions`
- **Assumptions and validity**: H2S and other combustibles are not burnt; the inert rest
  passes. `co2_mass_fraction + methane_mass_fraction > 1` raises `ValidationError`; reverse
  flow raises `PhysicsError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Vent

vent = Vent().update_params(mode="flare", co2_mass_fraction=0.85, methane_mass_fraction=0.1)
flared = vent(fluid_in=gm.Stream(m_dot=0.076, T="80 C", p="4.85 bar"))
assert round(flared.outputs.co2_emission, 6) == 0.085032
assert round(flared.outputs.get("heat_loss", unit="kW"), 1) == 372.4
```

### Flare

Burns the gas that reaches it; the gas leaves the plant here.

- **Ports**: `fluid_in` (gas), no outlet.
- **Parameters**: `combustion_efficiency` (default 0.98, US EPA AP-42 section 13.5).
- **Outputs**: `burned_mass_flow`, `co2_emission`, `methane_emission` (kg/s).
- **Model**: from the composition of the stream, `co2_emission = m (x_CO2 + eta f_CO2)` with
  `f_CO2` the CO2 complete combustion forms per kg of gas, `methane_emission = m x_CH4 (1 - eta)`.
- **Physics**: `combustion.burnt_gas_emissions`, `gas.mass_fraction`, `gas.combustion_co2`
- **Assumptions**: a stream without a composition emits nothing. A `Vent` with `mode="flare"` burns
  by mass-fraction parameters; both end in the stoichiometry of `combustion`.
- **Energy audit**: closed; the sensible enthalpy of the gas leaves through `burned_mass_flow`.

## Exchangers

### HeatExchanger

Two-stream effectiveness-NTU heat exchanger with fouling diagnostics.

- **Ports**: `hot_in`, `cold_in` -> `hot_out`, `cold_out`.
- **Parameters**: `thermal_conductance` (`ThermalConductance`, calibratable, required), `arrangement`
  (`"counterflow"` or `"parallel"`, default counterflow), `hot_nominal_pressure_drop`, `cold_nominal_pressure_drop`
  (>= 0, required) at `hot_nominal_mass_flow`, `cold_nominal_mass_flow` (> 0, required),
  `fouling_threshold` (`Fraction`, default 0.15).
- **Outputs**: `duty`, `effectiveness` (soft sensors), `transfer_units`, `log_mean_temperature_difference`, `hot_out_T`,
  `cold_out_T`, `hot_pressure_drop`, `cold_pressure_drop`, `approach_temperature`.
- **Model**: `C_min`, `C_max` from `m_dot cp`; `NTU = UA / C_min`; `heat_transfer.exchanger_balance` takes the effectiveness of the arrangement;
  `duty = eps C_min (T_h,in - T_c,in)`; each side loses `nominal_pressure_drop (m_dot / nominal_mass_flow)^2`.
  A stopped stream transfers nothing.
- **Physics**: `diagnostics.below_limit`, `diagnostics.bounded_score`,
  `diagnostics.performance_ratio`, `heat_transfer.apparent_conductance`,
  `heat_transfer.exchanger_balance`, `heat_transfer.lmtd`, `heat_transfer.terminal_differences`,
  `hydraulics.quadratic_pressure_drop`
- **Health**: apparent UA from measured temperatures (`heat_transfer.apparent_conductance`; the
  fit is `gm.analysis.estimate_conductance`), alarm below `1 - fouling_threshold` of the design UA.
- **Validity**: a hot inlet below the cold inlet or negative flow raise `PhysicsError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import HeatExchanger

exchanger = HeatExchanger().update_params(
    thermal_conductance=5e5, hot_nominal_pressure_drop="0.2 bar", cold_nominal_pressure_drop="0.2 bar",
    hot_nominal_mass_flow=40, cold_nominal_mass_flow=40,
)
result = exchanger(
    hot_in=gm.Stream(m_dot=40, T="80 C", p="5 bar"),
    cold_in=gm.Stream(m_dot=40, T="40 C", p="5 bar"),
)
assert round(result.outputs.effectiveness, 4) == 0.7477
assert round(result.outputs.hot_pressure_drop, 6) == 20000
```

### Cooler

Dry or wet (evaporative) closed-circuit cooler rejecting heat to ambient air.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters**: `cooler_type` (`"dry"` or `"wet"`), `capacity` (`Power`, > 0), `approach`
  (`TemperatureDifference`, >= 0; typically 5 to 15 K dry and 3 to 8 K wet, ASHRAE Handbook,
  HVAC Systems and Equipment), `specific_fan_power` (`Ratio`, W of fan per W rejected), all
  required; `latent_heat` (default 2.43 MJ/kg, water at about 30 degC, IAPWS-IF97).
- **Controls**: `temperature_setpoint` (outlet).
- **Boundaries**: `ambient_temperature` (dry bulb, required), `wet_bulb_temperature`
  (`Temperature | None`, default `None`).
- **Outputs**: `duty`, `fluid_out_T`, `electricity` (fan), `heat_loss`, `evaporation_rate`
  (0 for dry), `is_capped`.
- **Model**: target `max(T_set, T_ref + approach)` with `T_ref` the dry bulb (dry) or wet bulb
  (wet); `duty = min(m_dot cp max(0, T_in - target), capacity)`; `electricity = sfp duty`;
  `heat_loss = duty + electricity`; `evaporation_rate = duty / latent_heat` (wet).
- **Physics**: `heat_transfer.fan_power`, `heat_transfer.setpoint_duty`,
  `heat_transfer.temperature_change`, `psychrometrics.evaporation_rate`
- **Assumptions**: closed circuit (the process stream keeps its mass); the evaporation rate is
  an upper bound (all heat taken as latent; 80 to 90 % in practice); fixed approach at every
  load; fan power proportional to duty; ambient about -20 to 45 degC.
- **Validity**: a wet cooler without a wet bulb raises `ValidationError`; a wet bulb above
  the dry bulb raises `PhysicsError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import Cooler

cooler = Cooler().update_params(
    cooler_type="wet", capacity="2 MW", approach=4, specific_fan_power=0.01
)
result = cooler(
    fluid_in=gm.Stream(flow="20 kg/s", T="40 C", p="3 bar"), temperature_setpoint="20 C",
    ambient_temperature="30 C", wet_bulb_temperature="22 C",
)
assert round(result.outputs.outlet_T - 273.15, 9) == 26.0
assert round(result.outputs.evaporation_rate, 3) == 0.486
```

## Heating

### HeatPump

Electric vapour-compression heat pump; in `cooling` mode it is an electric chiller.

- **Ports**: `source_in` -> `source_out` (evaporator, cooled), `sink_in` -> `sink_out`
  (condenser, heated).
- **Parameters**:
  - `mode` (`"heating"` or `"cooling"`, required), `capacity` (`Power`, > 0, required): cap on
    the useful duty.
  - `cop_model` (`"carnot"` or `"lorenz"`, default `"carnot"`): Lorenz is heating only.
  - `carnot_fraction` (`Efficiency`, default 0.5): Arpagaus et al. (2018), Energy 152,
    985-1010, report 0.4 to 0.6.
  - `lorenz_fraction` (`Efficiency`, default 0.5, the upstream GEMINI default): fraction of
    the Lorenz COP, used by `cop_model="lorenz"`.
  - `minimum_temperature_lift` (`TemperatureDifference`, > 0, default 10 K): floor of the lift
    in the COP, an engineering bound (not a literature value); set it to the smallest lift in
    the machine data.
  - `minimum_part_load` (`Fraction`, default 0): below this share of capacity the machine is off
    for the step.
  - `minimum_source_outlet_temperature` (`Temperature | None`, default `None`): lowest source
    outlet, for example freeze or scaling protection of the evaporator (upstream GEMINI
    `Ts_in_minimum`).
- **Controls**: `temperature_setpoint`: sink outlet when heating, source outlet when cooling.
- **Outputs**: `cop` (`None` when off), `useful_duty`, `evaporator_duty`, `condenser_duty`,
  `electricity`, `temperature_lift`, `is_capped` (limited by capacity or by the minimum source
  outlet), `is_running`,
  `source_out_T`, `sink_out_T`.
- **Model**: requested duty `C |T_in - T_set|` on the controlled circuit, then
  `refrigeration.part_load_duty`; `COP = eta T_sink_out / max(lift, L)` when heating and
  `eta T_source_out / max(lift, L)` when cooling, at the outlet temperatures. Because
  `Q_sink = Q_source + electricity`, the uncontrolled outlet is linear in itself and is solved in
  closed form (see the class docstring). Either circuit stopped means off.
  With `cop_model="lorenz"` the heating COP is `eta_L T_h / max(T_h - T_s, L)` with `T_h`, `T_s`
  the log-mean temperatures of the sink and source glides (`refrigeration.lorenz_cop_heating`,
  Lorenz 1894); the source outlet is then found by `brentq` between `T_in - Q / C` and `T_in`.
  `cop_model="lorenz"` with `mode="cooling"` raises `ValidationError`.
- **Physics**: `heat_transfer.heat_rate`, `heat_transfer.setpoint_duty`,
  `heat_transfer.temperature_change`, `refrigeration.carnot_cooling_sink_outlet`,
  `refrigeration.carnot_fraction_cop_cooling`, `refrigeration.carnot_fraction_cop_heating`,
  `refrigeration.carnot_heating_source_outlet`, `refrigeration.cooling_condenser_duty`,
  `refrigeration.cooling_minimum_sink_rate`, `refrigeration.heating_cop_minimum_source`,
  `refrigeration.heating_evaporator_duty`, `refrigeration.lorenz_fraction_cop_heating`,
  `refrigeration.lorenz_source_surplus`, `refrigeration.part_load_duty`,
  `refrigeration.source_limit_shortfall`
- **Minimum source outlet**: when heating would cool the source below
  `minimum_source_outlet_temperature`, the duty is reduced (`brentq` on `Q (1 - 1/COP) = C_source
  (T_in - T_min)`) so the source leaves at the minimum and the sink outlet drops; a source inlet at
  or below the minimum leaves the machine off. In cooling mode a setpoint below the minimum is
  raised to it.
- **Validity**: lifts of about 10 to 80 K. A heating COP of 1 or less (source inlet at or below
  `(1 - eta) T_sink_out`) and a cooling sink too small to reject the heat raise
  `PhysicsError`. Outlets are not checked against freezing. Constant Carnot fraction, no
  cycling or casing losses.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import HeatPump

heat_pump = HeatPump().update_params(mode="heating", capacity="2 MW", carnot_fraction=0.5)
result = heat_pump(
    source_in=gm.Stream(flow="20 kg/s", T="27 C", p="3 bar"),
    sink_in=gm.Stream(flow="10 kg/s", T="47 C", p="3 bar"),
    temperature_setpoint="67 C",
)
assert round(result.outputs.cop, 4) == 3.6015 and round(result.outputs.electricity) == 234202

water = gm.Fluid(kind="water", density=1000, specific_heat=4181)
lorenz = HeatPump().update_params(mode="heating", capacity="10 MW", cop_model="lorenz")
result = lorenz(
    source_in=gm.Stream(flow="20 m3/h", T="40 C", p="3 bar", fluid=water),
    sink_in=gm.Stream(flow="10 m3/h", T="30 C", p="3 bar", fluid=water),
    temperature_setpoint="80 C",
)
assert round(result.outputs.cop, 4) == 6.531 and round(result.outputs.electricity) == 88913
```

### Boiler

Auxiliary gas boiler heating a stream to a setpoint, burning co-produced gas first.

- **Ports**: `fluid_in` -> `fluid_out` (water); `fuel_in` -> `gas_out` (gas).
- **Parameters** (all required): `capacity` (`Power`, > 0), `efficiency` (`Efficiency`).
- **Controls**: `temperature_setpoint` (`Temperature`).
- **Outputs**: `duty`, `fuel_or_power`, `fluid_out_T`, `is_capped`, `heat_loss` (conversion loss), `fuel`
  (total), `fuel_coproduced`, `fuel_purchased`, `burned_mass_flow` (co-produced gas burned),
  `co2_emission` (kg/s, formed and carried, of everything burned).
- **Model**: `duty = min(m_dot cp max(0, T_set - T_in), limit)`, `fuel = duty / efficiency`,
  `heat_loss = fuel - duty`. With `F = fuel_in.m_dot LHV`: `fuel_coproduced = min(fuel, F)`,
  `fuel_purchased = fuel - fuel_coproduced`; `gas_out` is `fuel_in` less what was burned. `limit` is
  the `capacity`, and `min(capacity, F efficiency)` on a stream no `GasMakeup` or `GasGrid` marked.
- **Physics**: `energy.input_power`, `energy.output_power`, `heat_transfer.setpoint_duty`,
  `heat_transfer.temperature_change`, `combustion.fuel_power`, `combustion.fuel_split`,
  `combustion.emission_rate`, `gas.emission_per_energy`
- **Validity**: negative flow raises `PhysicsError`.
- **Energy audit**: closed; purchased gas enters no stream, so it is in `fuel` and not in
  `mass_balance`, and the burned co-produced gas leaves through `burned_mass_flow`.

```python
import gemini as gm
from gemini.modules import Boiler, GasGrid

boiler = Boiler().update_params(capacity="1 MW", efficiency=0.9)
result = boiler(
    fluid_in=gm.Stream(flow="10 kg/s", T="60 C", p="3 bar"),
    fuel_in=GasGrid()().outlets.fluid_out,
    temperature_setpoint="80 C",
)
assert round(result.outputs.duty) == 843480 and round(result.outputs.fuel) == 937200
```

### ElectricBoiler

The water side of `Boiler` without gas ports: `electricity = fuel_or_power = duty / efficiency`. It
has `electricity` and no `fuel` outputs. **Energy audit**: closed.

### CHP

Burns as `Boiler` does: `fuel_in` -> `gas_out`, with `fuel_coproduced`, `fuel_purchased`,
`burned_mass_flow` and `co2_emission`; on a stream without the grid mark the gas limits the load.

Gas-engine combined heat and power unit heating a water circuit.

- **Ports**: `fluid_in` -> `fluid_out` (water); `fuel_in` -> `gas_out` (gas).
- **Parameters**: `electric_capacity` (`Power`, > 0), `electric_efficiency`,
  `thermal_efficiency` (`Efficiency`, full load, LHV; typical gas engines 0.35 to 0.44 and 0.40
  to 0.50), `maximum_outlet_temperature` (`Temperature`), all required;
  `no_load_fuel_fraction` (`Fraction`, < 1, default 0; 0.05 to 0.15 reproduces the half-load
  efficiency drop of a lean-burn engine).
- **Controls**: `load_fraction` (`Fraction`, 0 is off).
- **Outputs**: `fuel`, `electricity_generated`, `heat_recovered`, `dumped_heat`, `heat_loss`,
  `fluid_out_T`.
- **Model**: Willans line (Heywood 1988) `F = (P_cap / eta_el) (f0 + (1 - f0) L)` for L > 0;
  `P = L P_cap`; `heat_recovered = min(eta_th F, m_dot cp (T_max - T_in))`; the rest of the
  engine heat is `dumped_heat`; `heat_loss = F - P - heat_recovered`.
- **Physics**: `combustion.engine_energy_flows`, `combustion.willans_fuel_input`,
  `heat_transfer.setpoint_duty`, `heat_transfer.temperature_change`
- **Validity**: `electric_efficiency + thermal_efficiency > 1` raises `ValidationError`. No
  minimum stable load or start-up losses; with no water flow all engine heat is dumped.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import CHP

chp = CHP().update_params(
    electric_capacity="1 MW", electric_efficiency=0.4, thermal_efficiency=0.45,
    no_load_fuel_fraction=0.1, maximum_outlet_temperature="90 C",
)
result = chp(
    fluid_in=gm.Stream(flow="20 kg/s", T="60 C", p="3 bar"),
    fuel_in=gm.modules.GasGrid()().outlets.fluid_out,
    load_fraction=0.5,
)
assert round(result.outputs.fuel) == 1375000 and round(result.outputs.heat_recovered) == 618750
```

## Cooling

### AbsorptionUnit

Single-effect water/LiBr absorption chiller or heat pump driven by hot water.

- **Ports**: three circuits `generator_in`/`generator_out` (driving hot water, cooled),
  `chilled_in`/`chilled_out` (evaporator, cooled), `cooling_in`/`cooling_out` (absorber and
  condenser, heated).
- **Parameters**:
  - `mode` (`"chiller"` or `"heat_pump"`, required), `capacity` (`Power`, > 0, required): cap on
    the useful duty (evaporator duty, or absorber plus condenser heat).
  - `characteristic_slope` (`ThermalConductance` s, > 0), `minimum_driving_difference`
    (ddt_min), `rejection_coefficient` (a), `evaporator_coefficient` (r): required, fitted to
    the machine (ideal Duehring form a = 1 + B, r = B, B about 1.1 to 1.2).
  - `thermal_cop` (`Ratio`, > 0, default 0.7, Herold, Radermacher and Klein 2016).
  - `auxiliary_power_ratio` (`Ratio`, required, usually about 0.01): solution-pump electricity
    per watt of evaporator duty.
  - `minimum_driving_temperature` (default 353.15 K): below it at the generator inlet the unit
    is off.
- **Controls**: `temperature_setpoint`: chilled outlet (chiller) or cooling outlet (heat pump).
- **Outputs**: `cop`, `useful_duty`, `generator_duty`, `evaporator_duty`,
  `absorber_condenser_duty`, `electricity`, `driving_temperature_difference` (at the mean
  circuit temperatures), `is_capped` (short of the request for any reason), the three
  `<port>_out_T`.
- **Model**: characteristic equation `Q_E = s (ddt - ddt_min)`, `ddt = t_G - a t_AC + r t_E`
  at the mean circuit temperatures in degC (Hellmann, Schweigler and Ziegler 1999; Kuehn and
  Ziegler 2005), solved in closed form from the inlets
  (`refrigeration.sorption_evaporator_capacity`); delivered `Q_E` is the least of that, the
  request and the capacity; `Q_G = Q_E / thermal_cop`, `electricity = aux Q_E`, `Q_AC = Q_G +
  Q_E + electricity`.
- **Physics**: `heat_transfer.mean_temperature`, `heat_transfer.setpoint_duty`,
  `heat_transfer.temperature_change`, `refrigeration.characteristic_temperature_difference`,
  `refrigeration.coefficient_of_performance`, `refrigeration.sorption_delivered_duty`,
  `refrigeration.sorption_duties`, `refrigeration.sorption_evaporator_capacity`,
  `refrigeration.sorption_rejection_ratio`
- **Validity**: driving water about 70 to 120 degC, cooling water 20 to 40 degC, chilled water
  above 4 degC, flows near the rated flows of the fit. Constant COP, no crystallisation limit.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import AbsorptionUnit

chiller = AbsorptionUnit().update_params(
    mode="chiller", capacity="300 kW", characteristic_slope=20000, minimum_driving_difference=10,
    rejection_coefficient=2.2, evaporator_coefficient=1.2, auxiliary_power_ratio=0.01,
)
result = chiller(
    generator_in=gm.Stream(flow="10 kg/s", T="88 C", p="3 bar"),
    chilled_in=gm.Stream(flow="10 kg/s", T="12 C", p="3 bar"),
    cooling_in=gm.Stream(flow="25 kg/s", T="30 C", p="3 bar"),
    temperature_setpoint="6 C",
)
assert round(result.outputs.evaporator_duty) == 247643 and result.outputs.is_capped
```

### AdsorptionChiller

Silica-gel/water adsorption chiller driven by hot water of 55 to 90 degC; a chiller only.

- **Ports**: the three circuits of `AbsorptionUnit` (the cooling circuit serves the adsorbing
  bed and the condenser).
- **Parameters**: `capacity` (cap on the evaporator duty), the four fitted characteristic
  coefficients and `auxiliary_power_ratio` (pumps, valves, controls), all required;
  `thermal_cop` (default 0.55; Wang and Oliveira 2006, Prog. Energy Combust. Sci. 32,
  424-458, report 0.5 to 0.6); `minimum_driving_temperature` (default 328.15 K, off below it);
  `maximum_driving_temperature` (default 363.15 K).
- **Controls**: `temperature_setpoint` (chilled outlet).
- **Outputs**: `cop`, `generator_duty`, `evaporator_duty`, `adsorber_condenser_duty`,
  `electricity`, `driving_temperature_difference`, `is_capped`, the three `<port>_out_T`.
- **Model**: the closed-form characteristic equation of `AbsorptionUnit` with the adsorption
  machine's own coefficients; cycle-averaged duties, which suit steps much longer than the
  batch cycle.
- **Physics**: `heat_transfer.mean_temperature`, `heat_transfer.setpoint_duty`,
  `heat_transfer.temperature_change`, `refrigeration.characteristic_temperature_difference`,
  `refrigeration.coefficient_of_performance`, `refrigeration.sorption_delivered_duty`,
  `refrigeration.sorption_duties`, `refrigeration.sorption_evaporator_capacity`
- **Validity**: a driving temperature above the maximum raises `PhysicsError`; a minimum
  at or above the maximum raises `ValidationError`. Cooling water 20 to 35 degC, chilled
  water above 5 degC.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import AdsorptionChiller

chiller = AdsorptionChiller().update_params(
    capacity="100 kW", characteristic_slope=2000, minimum_driving_difference=5,
    rejection_coefficient=2.0, evaporator_coefficient=1.0, auxiliary_power_ratio=0.02,
)
result = chiller(
    generator_in=gm.Stream(flow="5 kg/s", T="70 C", p="3 bar"),
    chilled_in=gm.Stream(flow="5 kg/s", T="18 C", p="3 bar"),
    cooling_in=gm.Stream(flow="10 kg/s", T="27 C", p="3 bar"),
    temperature_setpoint="12 C",
)
assert round(result.outputs.evaporator_duty) == 45733 and round(result.outputs.cop, 9) == 0.55
```

## Subsurface

Ground and aquifer heat that enters a circuit is `heat_absorbed` and heat given to them is
`heat_loss`: the ground is the plant's environment.

### ProductionReservoir and InjectionReservoir

The aquifer supplying the production well and the one receiving the injected brine. They are
open boundaries: `mass_balance` and `energy_balance` count the production rate as a source and
the injected stream as a sink.

- **Ports**: `ProductionReservoir` emits `sandface`; `InjectionReservoir` takes `sandface`.
- **Parameters**: `pressure` (calibratable), `temperature`, `permeability`, `aquifer_thickness`
  (> 0), `drainage_radius` (0 leaves the radial diagnostics unavailable), `top_depth`,
  `wellbore_radius` (> 0), all required; `productivity_index` (required by the production
  reservoir) and `injectivity_index` (required by the injection reservoir), both
  `ProductivityIndex | None` in m3/s/Pa, calibratable; `skin` (default 0, calibratable);
  `decline_threshold` (default 0.15); `role` (fixed by the class).
- **Controls**: `ProductionReservoir.production_rate` (`MassFlow`, >= 0).
- **Outputs**: `bottomhole_pressure` (soft sensor), `drawdown` (production), `overpressure`
  (injection), `flow_pressure_drop`, `skin_pressure_drop`, `radial_bottomhole_pressure` (`None` without a drainage
  radius), `hydrostatic_pressure_drop`.
- **Model**: linear IPR `p_bh = p_res - Q / PI` (production) and `p_bh = p_res + Q / II`
  (injection); radial Darcy diagnostics through `hydraulics.radial_pressure_drops`.
- **Physics**: `diagnostics.below_limit`, `diagnostics.bounded_score`,
  `diagnostics.performance_ratio`, `fluid.volume_flow`, `hydraulics.hydrostatic_dp`,
  `hydraulics.injectivity_index`, `hydraulics.injectivity_pressure`,
  `hydraulics.productivity_index`, `hydraulics.productivity_pressure`,
  `hydraulics.radial_pressure_drops`
- **Health**: alarm when the measured index falls below `1 - decline_threshold` of design.
- **Helpers**: `ProductionReservoir.sandface_stream(production_rate)` and
  `InjectionReservoir.required_pressure(sandface)` evaluate the IPR without a call; `forward` and
  the outputs use them, and so does the [nodal analysis](#nodal-well-analysis).
- **Energy audit**: open boundaries, residual zero by construction.

```python
import gemini as gm
from gemini.modules import ProductionReservoir

reservoir = ProductionReservoir().update_params(
    pressure="200 bar", temperature="80 C", permeability=1e-12, aquifer_thickness="50 m",
    drainage_radius="500 m", top_depth="2000 m", productivity_index=20 / 3600 / 1e5,
    wellbore_radius=0.1,
)
source = reservoir(production_rate="40 kg/s")
assert round(source.outputs.drawdown / 1e5, 6) == 7.2
```

### ThermalDecline

Production temperature decline of a balanced doublet once the cooled region around the
injector reaches the producer; placed between a `ProductionReservoir` sandface and the well.

- **Ports**: `fluid_in` (reservoir stream at the reservoir temperature) -> `fluid_out`.
- **Parameters** (all required site data): `well_spacing` (L), `aquifer_thickness` (H),
  `porosity` (in (0, 1)), `rock_volumetric_heat_capacity` ((rho c)_r). The fluid (rho c)_w
  comes from the inlet stream.
- **Boundaries**: `injection_temperature`.
- **States**: `injected_volume` (`Volume`, default 0), advanced by `V + Q dt` (exact for a
  constant flow).
- **Outputs**: `breakthrough_time` (`None` at zero flow), `temperature_drop`, `fluid_out_T`.
- **Model**: `(rho c)_a = phi (rho c)_w + (1 - phi) (rho c)_r`; breakthrough volume
  `V_B = pi L^2 H (rho c)_a / (3 (rho c)_w)` (Gringarten and Sauty 1975, J. Geophys. Res.
  80(35), 4956-4962); the dipole streamline at angle theta arrives cold when `V / V_B = 3 (sin
  theta - theta cos theta) / sin^3 theta`, so the cold share `f = theta / pi`
  (`ground.doublet_cold_fraction`) gives `outlet_T = T_in - f (T_in - T_inj)`; f = 1/2 at
  `V = 3 V_B`.
- **Physics**: `fluid.volume_flow`, `ground.aquifer_volumetric_heat_capacity`,
  `ground.doublet_breakthrough_time`, `ground.doublet_breakthrough_volume`,
  `ground.doublet_temperature_drop`, `ground.injected_volume`
- **Assumptions**: homogeneous confined aquifer, fully penetrating wells, no regional flow,
  piston displacement with local equilibrium, no recharge from cap and base rock (an upper
  bound of the decline), the current injection temperature for all injected water.
- **Energy audit**: deliberately not closed: the drop corrects the open aquifer boundary, so
  the residual is `m_dot cp (T_in - outlet_T)`, not a heat loss. Mass closes.

```python
import gemini as gm
from gemini.modules import ThermalDecline

decline = ThermalDecline().update_params(
    well_spacing="1000 m", aquifer_thickness="50 m", porosity=0.2,
    rock_volumetric_heat_capacity="2.5 MJ/m3/K",
)
decline.injection_temperature = "40 degC"
produced = gm.Stream(flow="180 m3/h", T="80 C", p="200 bar")
state, result = decline.step({"injected_volume": 1.2e8}, 3600, {"fluid_in": produced})
assert round(result.outputs.breakthrough_time / (365.25 * 86400), 2) == 22.37
assert round(result.outputs.temperature_drop, 2) == 20.98
```

### BoreholeField

Shallow closed-loop borehole field (ground-source heat pump field or BTES) with a lumped mean
ground temperature.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters** (all required): `borehole_count` (N), `borehole_depth` (H), `borehole_radius`
  (r_b, typically 0.055 to 0.075 m), `borehole_spacing` (s, square cells),
  `borehole_resistance` (`LinearThermalResistance`, calibratable), `ground_conductivity`
  (calibratable), `ground_volumetric_heat_capacity`, `undisturbed_ground_temperature` (T_u).
- **States**: `ground_temperature_change` (theta, default 0) of the field volume `N s^2 H`.
- **Outputs**: `heat_extraction_rate` (signed, positive from the ground), `fluid_mean_temperature`,
  `ground_temperature`, `fluid_out_T`, `heat_absorbed`, `heat_loss`.
- **Model**: cell radius `r_e = s / sqrt(pi)` and steady-flux resistance R_sf
  (`ground.steady_flux_resistance`, Hellstrom 1991); `UA = N H / (R_b + R_sf)`,
  `eps = 1 - exp(-UA / (m_dot cp))`, `Q = eps m_dot cp (T_g - T_in)`; the field exchanges with
  the undisturbed ground through `UA_s = 2 pi k H / ln(4H/D)`
  (`ground.vertical_cylinder_conductance`, Incropera table 4.1) with the plan diameter
  `D = 2 sqrt(N s^2 / pi)`; `C dtheta/dt = -Q - UA_s theta` is solved exactly for a constant
  inlet.
- **Physics**: `ground.borehole_field_capacity`, `ground.borehole_field_surroundings_conductance`,
  `ground.borehole_field_temperature_change`, `ground.borehole_loop_conductance`,
  `heat_transfer.heat_rate`, `heat_transfer.mean_temperature`, `heat_transfer.signed_parts`,
  `heat_transfer.temperature_change`
- **Assumptions and validity**: a simplification of g-functions (Eskilson 1987): long-term
  balance, depletion and recovery, but not the short-term borehole response or field
  interaction; suits monthly to seasonal behaviour (peak-hour temperatures are optimistic).
  A cell radius at or below r_b or `ln(4H/D) < 1` raises `ValidationError`.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import BoreholeField

field = BoreholeField().update_params(
    borehole_count=10, borehole_depth="150 m", borehole_radius=0.075, borehole_spacing="6 m",
    borehole_resistance=0.1, ground_conductivity=2.0,
    ground_volumetric_heat_capacity="2.2 MJ/m3/K", undisturbed_ground_temperature="10 C",
)
state, result = field.step(None, 30 * 86400, {"fluid_in": gm.Stream(m_dot=3, T="0 C", p="3 bar")})
assert round(result.outputs.heat_extraction_rate) == 36906
assert round(state["ground_temperature_change"], 3) == -0.769
```

### DownholeHeatExchanger

Deep coaxial closed-loop heat exchanger in a linear geothermal gradient (steady).

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters** (all required): `borehole_depth`, `surface_temperature`, `geothermal_gradient`
  (`TemperatureGradient`, accepts `"30 K/km"`), `ground_conductivity` (calibratable),
  `ground_diffusivity`, `borehole_radius`, `borehole_resistance` (calibratable),
  `operating_time` (`Duration`, seconds).
- **Outputs**: `heat_extraction_rate` (signed), `fluid_out_T`, `heat_absorbed`, `heat_loss`.
- **Model**: the fluid flows down the annulus and returns through an insulated centre pipe;
  `R = R_b + f(t) / (2 pi k)` with Ramey's `f(t) = ln(2 sqrt(alpha t) / r_b) - gamma/2`
  (Ramey 1962, J. Pet. Technol. 14(4), 427-435); Ramey's steady profile with `A = m_dot cp R`
  gives `outlet_T = T(depth)`.
- **Physics**: `ground.ramey_fluid_temperature`, `ground.ramey_relaxation_length`,
  `ground.ramey_rock_resistance`, `heat_transfer.heat_rate`, `heat_transfer.signed_parts`
- **Validity**: `alpha t / r_b^2 >= 25`, typically a few days of operation, else
  `ValidationError`. Steady state, no load history, perfectly insulated return pipe.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import DownholeHeatExchanger

exchanger = DownholeHeatExchanger().update_params(
    borehole_depth="2500 m", surface_temperature="10 degC", geothermal_gradient="30 K/km",
    ground_conductivity=2.5, ground_diffusivity=1e-6, borehole_radius=0.1,
    borehole_resistance=0.05, operating_time=3.15e7,
)
result = exchanger(fluid_in=gm.Stream(m_dot=5, T="30 C", p="3 bar"))
assert round(result.outputs.outlet_T - 273.15, 2) == 35.92
```

## Wells

### ProductionWell and InjectionWell

Wells traversing a geothermal `PipePath` with the original GEMINI DPDT equations,
Swamee–Jain friction, Beggs–Brill two-phase flow and explicit heat loss
(`hydraulics.pipe_path_profile`).

- **Ports**: `ProductionWell` `bottom_in` -> `wellhead_out`; `InjectionWell` `wellhead` -> `bottom`.
- **Parameters**: `pipe_path` (`geometry.PipePath`, required), `soil_temperature` (required),
  `heat_transfer_coefficient` (default 10 W/m2/K, calibratable), `correction_factors` (affine pressure
  correction, default `(1, 0)`, calibratable), `friction_correlation` (`"darcy_weisbach"`),
  `two_phase_friction_correlation` (`"BeggsBrill"`). The production well adds `segment` (`"full"`,
  `"below_esp"`, `"above_esp"`, default full) and `esp_depth` (default `None`).
- **Outputs**: wellhead (production) or bottomhole (injection) pressure and temperature,
  `friction_pressure_drop`, `gravity_pressure_drop`, `section_pressure`, `section_temperature`, `heat_loss`.
- **Model**: see [physics.md](physics.md) and [refactor-notes.md](refactor-notes.md); the
  injection traversal uses the legacy negative flow internally, while its ports keep the
  incoming sign. Helpers: `intake_conditions`, `wellhead_from_discharge`,
  `discharge_from_wellhead`, `corrosion_profile` (mm/year), `erosion_check`.
- **Physics**: `fluid.heat_capacity_rate`, `heat_transfer.heat_rate`,
  `hydraulics.affine_correction`, `hydraulics.corrosion_profile`, `hydraulics.erosion_check`,
  `hydraulics.pipe_path_profile`
- **Energy audit**: closed; `heat_loss` is signed here (negative when the soil heats the brine).

```python
import math

import gemini as gm
from gemini.modules import ProductionWell
from gemini.physics.geometry import PipePath, PipeSection

vertical = PipeSection(length=1500, inclination=math.pi / 2, inner_diameter=0.2, roughness=2e-5)
path = PipePath(sections=[vertical])
well = ProductionWell().update_params(pipe_path=path, soil_temperature="40 C")
result = well(bottom_in=gm.Stream(m_dot=40, T="80 C", p="180 bar"))
assert round(result.outputs.gravity_pressure_drop / 1e5, 2) == 147.15
assert round(result.outputs.heat_loss) == 376991
```

## Storage

### ThermalStorage

Fully mixed hot or chilled water tank with a charge and a discharge circuit.

- **Ports**: `charge_in` -> `charge_out`, `discharge_in` -> `discharge_out`.
- **Parameters**: `service` (`"hot"` or `"chilled"`, the sign of the reported energies),
  `volume` (> 0), `heat_loss_conductance` (UA to ambient), `reference_temperature` (zero of
  `stored_energy`), all required; `charge_effectiveness`, `discharge_effectiveness`
  (`Fraction`, default 1, a direct connection).
- **Boundaries**: `ambient_temperature`.
- **States**: `temperature` (default 293.15 K).
- **Outputs**: `tank_temperature` (start of step), `stored_energy`, `charge_duty`,
  `discharge_duty` (negative when the circuit works against the service),
  `heat_accumulation` (signed), `heat_loss`, `heat_absorbed`.
- **Model**: tank content `module.fluid`, `C = rho cp V`; circuit `i` transfers `Q_i = e_i C_i
  (T_i,in - T)` and leaves at `T_i,in - e_i (T_i,in - T)`; `Q_amb = UA (T - T_amb)`;
  `C dT/dt = Q_c + Q_d - Q_amb` (Duffie and Beckman 2013, section 8.3) solved exactly over `dt`
  for constant inlets; outlets and outputs use the start-of-step temperature.
- **Physics**: `heat_transfer.effectiveness_outlet_temperature`, `heat_transfer.heat_rate`,
  `heat_transfer.signed_parts`, `storage.circuit_conductance`, `storage.tank_capacity`,
  `storage.tank_relaxation`, `storage.tank_service_report`
- **Assumptions**: no stratification (a stratified tank delivers hotter water), constant
  properties and effectiveness, inlets constant within a step.
- **Energy audit**: closed with the stored-heat term: `heat_accumulation` is the rate of
  increase of the tank's heat.

```python
import gemini as gm
from gemini.modules import ThermalStorage

tank = ThermalStorage().update_params(
    service="hot", volume="20 m3", heat_loss_conductance="15 W/K", reference_temperature="40 C"
)
tank.ambient_temperature = "15 C"
charge = gm.Stream(flow="10 m3/h", T="80 C", p="3 bar")
discharge = gm.Stream(flow="5 m3/h", T="45 C", p="3 bar")
state = {"temperature": gm.units.convert(60, "degC", "K")}
for _ in range(4):
    state, result = tank.step(state, 900, {"charge_in": charge, "discharge_in": discharge})
assert round(state["temperature"] - 273.15, 3) == 64.375
```

### IceStorage

Lumped ice-on-coil or encapsulated ice store on one glycol circuit, for state-of-charge
tracking.

- **Ports**: `fluid_in` -> `fluid_out` (glycol).
- **Parameters**: `water_mass` (`Mass`, > 0), `thermal_conductance` (coil, > 0), both required; `latent_heat`
  (default 333.55 kJ/kg; IAPWS R10-06 gives 333.44 at the triple point),
  `freezing_temperature` (default 273.15 K), `water_specific_heat` (default 4219.9 J/kg/K,
  IAPWS-95 at 0.01 degC), `ice_specific_heat` (default 2096.8 J/kg/K, IAPWS R10-06).
- **States**: `ice_fraction` (default 0) and `temperature` (default 273.15 K): at the freezing
  temperature while partly frozen, above it only with no ice, below it only fully frozen;
  anything else raises `ValidationError`.
- **Outputs**: `stored_cold = M L x`, `duty` (heat from the glycol into the store; negative
  while charging), `fluid_out_T`, `is_full`, `is_empty`.
- **Model**: `e = 1 - exp(-UA / (m_dot cp))` against a uniform store; `duty = e C (T_in - T)`;
  an exact piecewise enthalpy integration crosses at most three segments (sensible liquid,
  latent, sensible ice) per step.
- **Physics**: `heat_transfer.ambient_effectiveness`,
  `heat_transfer.effectiveness_outlet_temperature`, `heat_transfer.heat_rate`,
  `storage.circuit_conductance`, `storage.ice_advance`, `storage.ice_stored_cold`
- **Assumptions**: constant coil UA (real UA falls as ice thickens; ASHRAE Handbook, HVAC
  Applications, Thermal Storage), no supercooling, perfectly insulated.
- **Energy audit**: the store declares no `heat_accumulation`, so the residual equals `duty`
  (the rate of increase of its internal energy, tested). Mass closes.

```python
import gemini as gm
from gemini.modules import IceStorage
from gemini.types import GLYCOL_30

store = IceStorage().update_params(water_mass="50 t", thermal_conductance=20000)
glycol = gm.Stream(flow="8 kg/s", T="-5 C", p="3 bar", fluid=GLYCOL_30)
state = None
for _ in range(8):
    state, result = store.step(state, 3600, {"fluid_in": glycol})
assert round(state["ice_fraction"], 4) == 0.1269 and not result.outputs.is_full
```

### AquiferStorage

Aquifer thermal energy storage (ATES) well pair with a warm and a cold store. Ground heat is counted
as in [Subsurface](#subsurface).

- **Ports**: `injection_in` -> `production_out`: the balanced pair produces the injected mass
  flow, pressure and fluid at the temperature of the store produced from (the aquifer
  temperature when idle). Well hydraulics belong to well modules.
- **Parameters**: `aquifer_temperature`, `aquifer_thickness` (H), `porosity`,
  `rock_volumetric_heat_capacity`, `ground_conductivity` (calibratable as an effective value),
  all required; `storage_period` (`Duration`, default 182.625 days, one season).
- **Controls**: `mode`: `"charge"` (produce from cold, inject into warm), `"discharge"`
  (produce from warm, inject into cold), `"idle"` (requires zero flow).
- **States** (all default 0): `warm_volume`, `cold_volume`, `warm_temperature_change`,
  `cold_temperature_change` (theta = T - T_aq), `charged_heat`, `recovered_heat`.
- **Outputs**: `stored_energy` (cold store counts negative), `production_out_T`,
  `recovery_efficiency` (`None` until heat was charged), `warm_temperature`,
  `cold_temperature`, `heat_loss`, `heat_absorbed`.
- **Model**: fully mixed stores of excess heat `(rho c)_w V theta` in a cylinder of height H;
  losses `UA = 2 k A / sqrt(pi alpha t_p)` over the envelope `A = 2 pi R (R + H)`
  (`ground.cylinder_store_conductance`, Carslaw and Jaeger 1959; Bloemendal and Hartog 2018,
  Geothermics 71, 306-319). A step mixes the injected volume, removes the produced volume
  (an empty store produces native water), then decays each store exactly at its end volume
  (operator splitting, first order in `dt` with flow).
- **Physics**: `fluid.volume_flow`, `ground.aquifer_stored_energy`, `ground.injected_volume`,
  `ground.mix_store`, `ground.store_conductance`, `ground.store_relaxation`, `ground.stored_heat`,
  `ground.thermal_recovery`, `heat_transfer.heat_rate`, `heat_transfer.signed_parts`
- **Assumptions and validity**: no regional flow, dispersion or buoyancy (stores below about
  30 degC), no well interaction, a mixed store instead of a thermal fringe, a conduction layer
  thin against R and H. Negative flow, or flow in idle mode, raise `PhysicsError`.
- **Energy audit**: deliberately not closed per call: the residual equals the rate of change of
  `stored_energy`. Mass closes.

```python
import gemini as gm
from gemini.modules import AquiferStorage

ates = AquiferStorage().update_params(
    aquifer_temperature="11 degC", aquifer_thickness="30 m", porosity=0.3,
    rock_volumetric_heat_capacity="2 MJ/m3/K", ground_conductivity=2.5,
)
ates.mode = "charge"
state = None
for hour in range(24 * 90):
    inlets = {"injection_in": gm.Stream(flow="100 m3/h", T="18 C", p="3 bar")}
    state, result = ates.step(state, 3600, inlets)
assert round(result.outputs.get("stored_energy", unit="kWh") / 1e6, 2) == 1.58
```

## Control

### PIDController

Discrete PID controller with output limits and clamping anti-windup. It has no fluid ports; a
parent plant calls it once per step in `forward` and uses `result.outputs.command`, so such a
parent cannot run under `gm.no_outputs()`.

- **Parameters**: `proportional_gain` (> 0), `minimum_output`, `maximum_output` (`minimum_output <
  maximum_output`, else `ValidationError`), `direction` (`"direct"` or `"reverse"`), all
  required; `integral_time` (`Duration | None`, default `None` for P or PD), `derivative_time`
  (default 0). Times are SI seconds; text such as `"15 min"` converts.
- **Controls**: `setpoint`. **Boundaries**: `measurement` (both `Dimensionless`).
- **States**: `integral` (default 0), `previous_error`, `previous_step` (default `None`).
- **Outputs**: `error`, `command`, `is_saturated` (the command was clamped).
- **Model**: `e = setpoint - measurement` for `"reverse"` (a heating valve), the opposite for
  `"direct"`; `u = clamp(K e + I + D)` with `D = K Td (e - e_prev) / h_prev` and
  `I += K h / Ti e` (Astrom and Hagglund 2006, *Advanced PID Control*, chapter 3). The command
  uses start-of-step states (a one-step lag of the integral). The integral is frozen while the
  unclamped command is at or beyond a limit and the error drives it further. A plain call
  returns the proportional command only.
- **Physics**: `control.anti_windup_increment`, `control.pid_command`, `control.pid_derivative`,
  `control.pid_error`, `control.pid_integral_increment`
- **Energy audit**: not applicable (no streams, no energy outputs).

```python
from gemini.modules import PIDController

pid = PIDController().update_params(
    proportional_gain=0.05, integral_time=600, minimum_output=0, maximum_output=1, direction="reverse"
)
pid.setpoint = 70.0
state = None
for measured in (60.0, 62.0, 65.0):
    pid.measurement = measured
    state, result = pid.step(state, 900, {})
assert result.outputs.command == 1.0
assert state == {"integral": 0.75, "previous_error": 5.0, "previous_step": 900.0}
```

## Power

### ORC

Binary organic Rankine cycle plant heated by brine, with an air-cooled condenser.

- **Ports**: `fluid_in` -> `fluid_out`.
- **Parameters** (all required): `minimum_brine_outlet_temperature`, `pinch` (>= 0),
  `carnot_fraction` (`Efficiency`; operating plants about 0.3 to 0.6, DiPippo 2004),
  `condenser_approach` (>= 0), `parasitic_fraction` (`Fraction`, < 1), `capacity` (gross).
- **Boundaries**: `ambient_temperature` (condenser air).
- **Outputs**: `heat_input`, `gross_power`, `parasitic_power`, `electricity_generated` (net),
  `condenser_duty`, `heat_loss` (condenser duty plus parasitic power), `thermal_efficiency`
  (`None` without heat input), `condensing_temperature`, `fluid_out_T`, `is_capped`.
- **Model**: `T_c = T_amb + approach`; design outlet `T_out = max(T_min, T_c + pinch)`;
  working-fluid temperatures `T_a = T_in - pinch`, `T_b = T_out - pinch`; Lorenz work `W_rev =
  Q (1 - T_c ln(T_a/T_b) / (T_a - T_b))`; gross `= fraction W_rev` (DiPippo 2007, Geothermics 36,
  276-285); above `capacity` part of the brine bypasses and mixes adiabatically.
- **Physics**: `heat_transfer.effectiveness_outlet_temperature`, `heat_transfer.heat_rate`,
  `power_cycles.cycle_design`, `power_cycles.plant_balance`
- **Assumptions and validity**: single-phase brine, constant efficiency at part load, bypass
  control. The parasitic load is supplied from the generator, so it is `parasitic_power`, not
  `electricity`. An inlet no hotter than `T_out` produces nothing.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import ORC

orc = ORC().update_params(
    minimum_brine_outlet_temperature="70 degC", pinch=5, carnot_fraction=0.5,
    condenser_approach=15, parasitic_fraction=0.15, capacity="5 MW",
)
result = orc(fluid_in=gm.Stream(m_dot=100, T="150 degC", p="10 bar"), ambient_temperature="15 degC")
assert round(result.outputs.get("electricity_generated", unit="MW"), 3) == 2.801
assert result.outlets.fluid_out.T == 343.15
```

### Separator

Two-phase flash separator for liquid-dominated reservoirs (DiPippo 2016, *Geothermal Power
Plants*, 4th ed., section 5.2).

- **Ports**: `fluid_in` (pressurised liquid) -> `liquid_out` (saturated brine), `gas` (dry saturated
  steam, fluid `STEAM`).
- **Controls**: `pressure_setpoint` (> 0), the separator pressure.
- **Outputs**: `steam_fraction`, `steam_mass_flow`, `saturation_temperature`.
- **Model**: `h_in` from IF97 region 1 at `max(p_in, p_sat(T_in))` and `T_in`; `x = (h_in -
  h_f) / h_fg` at the setpoint (`steam.flash_fraction`, zero when subcooled); both outlets at
  the setpoint and `T_sat` (a subcooled liquid keeps its temperature).
- **Physics**: `steam.flash_state`
- **Assumptions and validity**: pure-water properties, perfect separation, adiabatic vessel;
  the inlet temperature is that of the liquid before flashing. Inlet 273.15 K to 623.15 K,
  setpoint 611.213 Pa to 16.529 MPa. Reverse flow, a steam inlet or a setpoint above the inlet
  pressure raise `PhysicsError`.
- **Energy audit**: closed in IF97 enthalpies, `m h_in = m_g h_g + m_l h_f` (tested);
  `energy_balance` cannot represent latent heat, so its residual is not meaningful. Mass
  closes.

```python
import gemini as gm
from gemini.modules import Separator

geofluid = gm.Stream(m_dot=100, T="250 degC", p="40 bar")
separated = Separator()(fluid_in=geofluid, pressure_setpoint="6 bar")
assert round(separated.outputs.steam_fraction, 4) == 0.1991
assert separated.outlets.gas_out.fluid.kind == "steam"
```

### FlashTurbine

Single-flash condensing steam turbine with generator and condenser.

- **Ports**: `fluid_in` (dry saturated steam, fluid kind `"steam"`) -> `fluid_out` (condensate,
  `WATER` at the condenser saturation state).
- **Parameters**: `isentropic_efficiency` (default 0.85, DiPippo 2016), `baumann_factor`
  (`Ratio`, default 1, the classical Baumann rule), `condenser_pressure` (> 0, required),
  `generator_efficiency` (required).
- **Outputs**: `gross_power`, `electricity_generated`, `condenser_duty`, `heat_loss`
  (condenser duty plus generator loss), `exhaust_quality`.
- **Model**: saturated steam at the inlet pressure (its temperature is not used); isentropic
  exhaust from `s_g(p_in)`; Baumann wet efficiency `eta = eta_d (1 - a (1 - x_out) / 2)` solved
  in closed form (`steam.baumann_expansion`; Baumann 1921); `gross = m (h_in - h_out)`;
  `condenser_duty = m (h_out - h_f(p_cond))`.
- **Physics**: `steam.baumann_expansion`, `steam.saturation_properties`, `steam.turbine_balance`
- **Validity**: pressures within 611.213 Pa to 16.529 MPa, a wet exhaust. A non-steam inlet,
  reverse flow, an inlet at or below the condenser pressure or a dry exhaust raise
  `PhysicsError`. No non-condensable gases or gland losses.
- **Energy audit**: closed in IF97 enthalpies (tested); `energy_balance` is not valid across
  the phase change. Mass closes.

```python
import gemini as gm
from gemini.modules import FlashTurbine, Separator

geofluid = gm.Stream(m_dot=100, T="250 degC", p="40 bar")
separated = Separator()(fluid_in=geofluid, pressure_setpoint="6 bar")
turbine = FlashTurbine().update_params(condenser_pressure="0.1 bar", generator_efficiency=0.98)
expanded = turbine(fluid_in=separated.outlets.gas_out)
assert round(expanded.outputs.get("electricity_generated", unit="MW"), 3) == 9.532
assert round(expanded.outputs.exhaust_quality, 4) == 0.8678
```

### GridConnection

Electricity exchange of a plant with the public grid.

- **Ports**: none.
- **Parameters**: `import_limit`, `export_limit` (`Power | None`, default `None` = unlimited),
  `import_price`, `export_price` (`MoneyPerEnergy`, required).
- **Boundaries**: `consumption`, `generation` (`Power`, >= 0), passed by the parent plant.
- **Outputs**: `net_import`, `net_export`, `unserved_consumption`, `curtailed_generation`,
  `is_import_limited`, `is_export_limited`, `cost_rate` (`MoneyRate`, negative is revenue).
- **Model**: import `max(0, consumption - generation)` and export `max(0, generation -
  consumption)`, each capped by its limit; `cost_rate = p_import import - p_export export`.
- **Physics**: `electricity.net_exchange`
- **Energy audit**: not applicable: it declares none of the audited energy outputs, so plant
  electricity is not counted twice.

```python
from gemini.modules import GridConnection

grid = GridConnection().update_params(
    import_price="0.2 currency/kWh", export_price="0.08 currency/kWh", export_limit="5 MW"
)
out = grid(consumption="0.4 MW", generation="9.5 MW").outputs
assert out.net_export == 5e6 and out.is_export_limited
assert round(out.get("cost_rate", unit="currency/h"), 9) == -400
```

## Demand

### HeatConsumer

Space or process heat demand on a hydronic circuit; the return temperature follows from the
delivered heat at the imposed flow.

- **Ports**: `supply_in` -> `return_out`.
- **Parameters**: `minimum_return_temperature` (required): the lowest temperature the emitters
  can cool the water to.
- **Boundaries**: `heat_demand` (`Power`, >= 0).
- **Outputs**: `heat_supplied`, `unmet_demand`, `return_out_T`, `temperature_difference`,
  `is_unmet`.
- **Model**: `Q = min(heat_demand, m_dot cp max(0, T_supply - T_min))`, `T_return = T_supply -
  Q / (m_dot cp)` (ASHRAE Handbook, HVAC Systems and Equipment 2020, chapter 13).
- **Physics**: `heat_transfer.setpoint_duty`, `heat_transfer.temperature_change`
- **Assumptions**: steady, no emitter characteristic beyond the return floor, no pressure drop;
  a supply colder than the floor delivers nothing.
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import HeatConsumer

consumer = HeatConsumer().update_params(minimum_return_temperature="40 degC")
supply = gm.Stream(flow="7.2 m3/h", T="70 degC", p="3 bar")
result = consumer(supply_in=supply, heat_demand="100 kW")
assert round(result.outputs.get("return_out_T", unit="degC"), 2) == 58.14
```

### CoolingConsumer

Building or process cooling demand on a chilled-water circuit, with a sensible and a latent load
and a dew-point test.

- **Ports**: `supply_in` -> `return_out` (condensate drains on the air side).
- **Parameters** (required): `maximum_return_temperature`, `dew_point_margin` (>= 0, the coil
  surface approach; coil specific, so no default).
- **Boundaries**: `sensible_cooling_demand`, `latent_cooling_demand` (`Power`, >= 0),
  `indoor_temperature`, `indoor_relative_humidity` (`Fraction`, > 0).
- **Outputs**: `heat_absorbed`, `unmet_sensible`, `unmet_latent`, `dew_point`, `return_out_T`,
  `is_unmet`.
- **Model**: `T_limit = min(T_max, T_indoor)`; `Q_available = m_dot cp max(0, T_limit -
  T_supply)`; the sensible load is served first; the latent load only when `T_supply <= T_dew -
  margin` (`psychrometrics.dew_point`; ASHRAE Handbook, HVAC Systems and Equipment 2020,
  chapter 23).
- **Physics**: `heat_transfer.sensible_latent_loads`, `heat_transfer.setpoint_duty`,
  `heat_transfer.temperature_change`, `psychrometrics.dew_point`
- **Validity**: indoor air 173.15 K to 473.15 K, relative humidity in (0, 1].
- **Energy audit**: closed.

```python
import gemini as gm
from gemini.modules import CoolingConsumer

building = CoolingConsumer().update_params(
    maximum_return_temperature="16 degC", dew_point_margin="3 K"
)
result = building(
    supply_in=gm.Stream(flow="7.2 m3/h", T="7 degC", p="3 bar"),
    sensible_cooling_demand="50 kW", latent_cooling_demand="10 kW",
    indoor_temperature="24 degC", indoor_relative_humidity=0.5,
)
assert round(result.outputs.get("dew_point", unit="degC"), 2) == 12.95
assert result.outputs.heat_absorbed == 60000 and not result.outputs.is_unmet
```

## Plants

`Doublet`, `DoubletHeatPlant`, `MultiWellPlant` and `DistrictNetwork` are plants built from a spec
(`gm.plants.names()` lists them with the others); `HeatingSubstation`, `CoolingSubstation` and
`ATESPlant` stay `Module` subclasses because a loop closed inside one call, or a `mode` that selects
which children run, is not wiring alone.

### Doublet

Reusable production and reinjection limbs of a geothermal doublet (`gm.plants.get("Doublet")`).
A plant built from a spec: `plants/specs/Doublet.json`, no handwritten class.

- **Children**: `reservoir` (`ProductionReservoir`), `well` (`ProductionWell` below the ESP),
  `esp` (`ESP`), `riser` (`ProductionWell` above the ESP), `injector` (`InjectionWell`),
  `sink` (`InjectionReservoir`).
- **Ports**: `return_in` -> `supply_out`.
- **Outputs**: `electricity` and `heat_loss` (automatic sums over the leaves).
- **Model**: the connections list the injection limb first, so the plan injects `return_in`
  through injector and sink, then produces through reservoir, lower well, ESP and riser, the
  order of the class it replaced. Inside `DoubletHeatPlant` the doublet is *opened* (the surface
  equipment connects `supply_out` to `return_in`), so its limbs are steps of the parent plant
  and are recorded as `doublet.reservoir`, ... (see [native-engine.md](native-engine.md),
  section 14).
- **Energy audit**: the sum of its leaves; the residual is the ESP's unresolved power.

```python
import gemini as gm

doublet = gm.Plant.load("examples/shared/doublet_heat/plant.json").doublet
doublet.set_inputs({"reservoir.production_rate": "42.4 kg/s", "esp.frequency": "55.5 Hz"})
result = doublet(return_in=gm.Stream(m_dot=40, T="45 C", p="20 bar", fluid=doublet.fluid))
assert round(result.outlets.supply_out.T - 273.15, 2) == 72.54
assert gm.modules.mass_balance(doublet, result)["residual"] == 0
```

`flow` is the liquid volume flow of the production reservoir and `brine_cooling` the production
minus the injection temperature, the outputs the limits of a doublet read.

#### A doublet from its depth

`gm.modules.get("Doublet")` is the class `gm.plants.Doublet`, the same spec with design parameters.

```python
plant.add("Doublet", name="d0", params={
    "depth": "2500 m", "gradient": "30 K/km", "surface_temperature": "12 degC",
    "permeability": "200 mD", "thickness": "100 m", "well_diameter": "0.244 m"})
plant.d0.fluid = gm.Fluid(density="1030 kg/m3", viscosity="0.4 mPa*s")
```

`set_params` derives through the pattern of [modules.md](modules.md#a-composite-that-sets-its-childrens-values):

| From | Derived |
| --- | --- |
| `depth`, `gradient`, `surface_temperature` | `temperature` of both reservoirs at the midpoint (`ground.geotherm_temperature`), hydrostatic `pressure` from the fluid density (`hydraulics.hydrostatic_pressure`), `soil_temperature` of the wells at half depth |
| and `permeability`, `thickness`, `well_diameter` | `productivity_index`, `injectivity_index` (`hydraulics.radial_index`, with the fluid viscosity, `drainage_radius`, the wellbore radius and the reservoir's `skin`), `permeability`, `aquifer_thickness`, `top_depth`, `drainage_radius`, `wellbore_radius`, the vertical `pipe_path` of the wells (`geometry.vertical_path`, commercial steel) |
| and `nominal_flow`, `pump_efficiency`, `nominal_wellhead_pressure` | `esp.setting_depth`, `esp_depth` and `segment` of `well` and `riser` (`hydraulics.pump_setting_depth`), and a one-stage ESP of constant head (`hydraulics.design_pump_head`, `pumps.constant_head_curves`) |

`drainage_radius` defaults to `ground.DOUBLET_WELL_SPACING`, 1000 m. Every derived value can be
overridden in the same call, by a child name such as `reservoir.pressure` or `well.pipe_path`, and
stays explicit. `esp.frequency` remains a control; the pump head is the design head at
`ESP_REFERENCE_FREQUENCY`. The old way, setting every child value directly, keeps working. Setting
`fluid` gives it to every child and derives again.

### MultiWellPlant

Purpose: geothermal well field with N production limbs mixed into one supply and M injection
limbs fed from one return. A spec plant of variable size: `gm.plants.from_template("MultiWellPlant",
{"producers": 3, "injectors": 2})` returns the plant of that size; the file
`plants/specs/MultiWellPlant.json` is the default size (2 and 1) and equals the output of
`multi_well_spec` in `plants/generators.py`.

- Structure: `producers` (default 2) `ModuleList` of `ModuleDict(reservoir=ProductionReservoir,
  well=ProductionWell, esp=ESP, riser=ProductionWell)`; `mixers` (`producers - 1` `Mixer`s);
  `splitters` (`injectors - 1` `Splitter`s); `injectors` (default 1) `ModuleList` of
  `ModuleDict(well=InjectionWell, sink=InjectionReservoir)`. Paths like
  `producers.0.esp.frequency`, `injectors.1.sink...`. Fewer than one producer or injector
  raises `ValidationError` from the generator and `ValidationError` from `from_template`.
- Ports: `return_in` -> `supply_out`.
- Parameters, controls, boundaries, states: none of its own (children's: `production_rate` per
  reservoir, `frequency` per ESP, `split_fraction` per splitter).
- Outputs: `electricity`, `heat_loss` (automatic sums), `supply_out_T` (`Output.of` the last
  mixer's `fluid_out_T`, or the single riser's `wellhead_temperature`).
- Model: each limb is traversed like the production limb of `Doublet`. N-way mixing is a cascade
  of two-way mixers, the running mix entering `branch1_in`; capacity-rate weighting is associative,
  so the cascade gives `sum(m_i cp_i T_i) / sum(m_i cp_i)` at the lowest wellhead pressure. The
  return is split by a cascade: splitter i sends its `split_fraction` of the flow reaching it to
  injector i, the last injector takes the rest, so injector i receives `f_i prod_{j<i}(1 - f_j)`
  (equal shares: `f_i = 1 / (M - i)`). The connections are listed so that the plan calls every
  production limb, the mixers, then each splitter before its injection limb.
- Assumptions: as in `Doublet`, the return boundary is independent of production within a call;
  splitters stand for chokes or the injection-pump allocation; no field hydraulics.
- Validity: that of the reservoirs, wells and ESPs; all limbs must deliver the same fluid
  (`Mixer` raises `ValidationError` otherwise).

```python
import gemini as gm

doublet = gm.Plant.load("examples/shared/doublet_heat/plant.json").doublet
field = gm.plants.from_template("MultiWellPlant", {"producers": 2, "injectors": 2})
for limb, rate in zip(field.producers, (40.0, 30.0)):
    for name in ("reservoir", "well", "esp", "riser"):
        getattr(limb, name).load_state_dict(getattr(doublet, name).state_dict())
    limb.set_inputs({"reservoir.production_rate": rate, "esp.frequency": "50 Hz"})
for limb in field.injectors:
    limb.well.load_state_dict(doublet.injector.state_dict())
    limb.sink.load_state_dict(doublet.sink.state_dict())
field.splitters[0].split_fraction = 0.5
returned = gm.Stream(flow=70, T=330, p=5e6, fluid=field.producers[0].riser.fluid)
result = field(return_in=returned)
print(result.outlets.supply_out.m_dot, result.outputs.supply_out_T)  # 70.0 344.23 K
```

### HeatingSubstation

Purpose: indirect district-heating substation (Frederiksen and Werner 2013, *District Heating
and Cooling*).

- Children: `valve` (`Valve`, network side), `heat_exchanger` (network on `hot_in`, building on
  `cold_in`), `consumer` (`HeatConsumer`).
- Ports: `supply_in` -> `return_out`.
- Parameters: `building_flow` (`MassFlow`, > 0, required), `building_pressure` (`Pressure`,
  > 0, required); the building fluid is the substation's `fluid`. No defaults: both are design
  data of the building circuit.
- Controls / boundaries: the children's (`valve.opening`, `consumer.heat_demand`).
- States: none.
- Outputs: `duty` (exchanger), `heat_supplied` (total), `unmet_demand`, `is_unmet`,
  `building_supply_temperature`, `building_return_temperature`, `network_out_T`, `valve_pressure_drop`.
- Model: the building loop (exchanger cold side -> consumer -> back) closes within one call:
  `close_loop` finds the building return temperature that one pass reproduces, starting at
  `min(consumer.minimum_return_temperature, T_network)`, clamped to at most the network
  temperature after the valve; then valve, exchanger and consumer are called once. With the
  demand met, `eps C_min (T_network - T_return) = Q`; beyond the exchanger's reach the return
  sits at the consumer's floor and the rest is `unmet_demand`. The valve only throttles: the
  network flow is imposed by `supply_in`, the valve reports the drop at its opening.
- Assumptions: building pump and hydraulics not modelled (no building-pump electricity); the
  converged consumer return and the stream fed back to the exchanger differ by at most 1e-9 K
  and appear as a boundary pair in the audit's `in`/`out` (the residual is unaffected).
- Validity: the children's; forward flow; a stopped network or building circuit transfers no
  heat. First-law closed (`relative_residual < 1e-12`), mass residual 0.

```python
import gemini as gm
from gemini.modules import HeatingSubstation, energy_balance

substation = HeatingSubstation().update_params(building_flow=3.0, building_pressure="3 bar")
substation.valve.update_params(flow_coefficient="20 m3/h/bar^0.5")
substation.heat_exchanger.update_params(
    thermal_conductance=2e4, hot_nominal_pressure_drop="0.2 bar", cold_nominal_pressure_drop="0.2 bar",
    hot_nominal_mass_flow=2, cold_nominal_mass_flow=3,
)
substation.consumer.update_params(minimum_return_temperature="30 degC")
substation.set_inputs({"valve.opening": 0.8, "consumer.heat_demand": "150 kW"})
result = substation(supply_in=gm.Stream(flow=2.0, T="75 degC", p="6 bar"))
print(result.outputs.heat_supplied, result.outputs.building_return_temperature)  # 150000.0 325.44 K
assert energy_balance(substation, result)["relative_residual"] < 1e-12
```

### CoolingSubstation

Purpose: indirect district-cooling energy transfer station (ASHRAE 2013, *District Cooling
Guide*).

- Children: `valve` (network side), `heat_exchanger` (building on `hot_in`, network on
  `cold_in`), `consumer` (`CoolingConsumer`).
- Ports: `supply_in` -> `return_out`.
- Parameters: `building_flow`, `building_pressure` (required, as above).
- Controls / boundaries: the children's (`valve.opening`, the consumer's sensible and latent
  demand, indoor temperature and relative humidity).
- Outputs: `duty`, `heat_absorbed` (total), `unmet_sensible`, `unmet_latent`, `is_unmet`,
  `dew_point`, `building_supply_temperature`, `building_return_temperature`, `network_out_T`,
  `valve_pressure_drop`.
- Model: as the heating substation with the roles of the exchanger sides swapped. The iteration
  starts at the consumer's return limit `min(maximum_return_temperature, indoor_temperature)`
  (or the network temperature, if warmer) and is clamped to at least the network temperature.
  The building supply temperature that reaches the consumer decides its dew-point test.
- Limitation: the consumer's dew-point test is on/off, so near the threshold the loop can lack
  a steady state (meeting the latent load warms the supply above the threshold, dropping it
  cools it below). The iteration then raises `PhysicsError`; with the test configuration
  (latent 50 kW) a band of about 2 K of network temperature (280.6 to 282.4 K) fails. A partial
  dehumidification model in `CoolingConsumer` would remove the band (open question).
- First-law closed, mass residual 0.

```python
import gemini as gm
from gemini.modules import CoolingSubstation

substation = CoolingSubstation().update_params(building_flow=4.0, building_pressure="3 bar")
substation.valve.update_params(flow_coefficient="20 m3/h/bar^0.5")
substation.heat_exchanger.update_params(
    thermal_conductance=3e4, hot_nominal_pressure_drop="0.2 bar", cold_nominal_pressure_drop="0.2 bar",
    hot_nominal_mass_flow=4, cold_nominal_mass_flow=3,
)
substation.consumer.update_params(maximum_return_temperature="18 degC", dew_point_margin=1.0)
substation.set_inputs({
    "valve.opening": 1.0,
    "consumer.sensible_cooling_demand": "60 kW",
    "consumer.latent_cooling_demand": "10 kW",
    "consumer.indoor_temperature": "24 degC",
    "consumer.indoor_relative_humidity": 0.5,
})
out = substation(supply_in=gm.Stream(flow=3.0, T="6 degC", p="6 bar")).outputs
print(out.heat_absorbed, out.unmet_latent)  # 70000.0 0.0
```

### DistrictNetwork

Purpose: two-pipe district heating or cooling network with parallel substations. A spec plant of
variable size: `gm.plants.from_template("DistrictNetwork", {"consumers": 3, "service": "cooling"})`;
the file `plants/specs/DistrictNetwork.json` is the default size (2 heating consumers) and equals
`district_network_spec()` in `plants/generators.py`.

- Structure: `pump` (`CentrifugalPump`, network circulation), `supply_pipe` (`Pipe`),
  `splitters` (`consumers - 1`), `substations` (`consumers` `HeatingSubstation`s for
  `service="heating"`, `CoolingSubstation`s for `"cooling"`), `mixers` (`consumers - 1`),
  `return_pipe` (`Pipe`). An unknown service or `consumers < 1` raises `ValidationError` from the generator and
  `ValidationError` from `from_template`.
  `HeatingSubstation` and `CoolingSubstation` stay handwritten composites: each closes its building
  loop inside one call.
- Ports: `supply_in` -> `return_out`.
- Parameters, controls, boundaries, states: none of its own.
- Outputs: `heat_supplied` (heating networks only: a cooling network has no leaf declaring
  it), `heat_absorbed`, `heat_loss`, `electricity` (totals), `return_out_T`.
- Model: flow order pump -> supply pipe -> splitter cascade -> substations -> mixer cascade ->
  return pipe. Cascades as in `MultiWellPlant` (substation i receives `f_i prod_{j<i}(1-f_j)`,
  equal shares with `f_i = 1 / (N - i)`); splitters stand for balancing valves and branch
  resistances, the network hydraulics are not solved. Pipes lump distribution losses or gains.
- Balance: every child is closed in its own terms; the sensible audit's residual is the pump's
  `hydraulic_power` (flow work dissipated by pipe and valve drops without a modelled
  temperature rise). Mass residual 0.

```python
import gemini as gm
from gemini.modules import energy_balance

network = gm.plants.from_template("DistrictNetwork", {"consumers": 2, "service": "heating"})
network.pump.update_params(
    head_coefficients=[4e5, 0.0, -1e9], rated_frequency="50 Hz", best_efficiency=0.75,
    best_efficiency_flow=0.004, motor_efficiency=0.9,
)
network.pump.frequency = "50 Hz"
for pipe in (network.supply_pipe, network.return_pipe):
    pipe.update_params(length=500, inner_diameter=0.1, elevation_change=0, heat_transfer_coefficient=1.0)
    pipe.ambient_temperature = "10 degC"
network.splitters[0].split_fraction = 0.5
for substation in network.substations:
    substation.update_params(building_flow=3.0, building_pressure="3 bar")
    substation.valve.update_params(flow_coefficient="20 m3/h/bar^0.5")
    substation.heat_exchanger.update_params(
        thermal_conductance=2e4, hot_nominal_pressure_drop="0.2 bar", cold_nominal_pressure_drop="0.2 bar",
        hot_nominal_mass_flow=2, cold_nominal_mass_flow=3,
    )
    substation.consumer.update_params(minimum_return_temperature="30 degC")
    substation.set_inputs({"valve.opening": 0.8, "consumer.heat_demand": "150 kW"})
result = network(supply_in=gm.Stream(flow=4.0, T="75 degC", p="6 bar"))
print(result.outputs.heat_supplied, result.outputs.return_out_T)  # 300000.0 329.36 K
audit = energy_balance(network, result)
print(audit["residual"], result.children["pump"].outputs.hydraulic_power)  # 1536.0 1536.0
```

### ATESPlant

Purpose: seasonal low-temperature ATES plant with free cooling and a heat pump (Fleuchaus et
al. 2018, Renewable and Sustainable Energy Reviews 94, 861-876; Bloemendal and Hartog 2018,
Geothermics 71, 306-319).

- Children: `storage` (`AquiferStorage`), `pump` (`CentrifugalPump`, well pump),
  `heat_exchanger`, `heat_pump` (`HeatPump`, configure `mode="heating"`).
- Ports: `return_in` -> `supply_out`.
- Parameters: `groundwater_pressure` (`Pressure`, > 0, required).
- Controls: `groundwater_flow` (`MassFlow`, >= 0, required); season via `storage.mode`.
- States: through the storage (`Module.step` steps it, also nested in a parent).
- Outputs: `electricity`, `heat_loss`, `heat_absorbed`, `heat_accumulation` (totals),
  `stored_energy`, `production_out_T`, `recovery_efficiency` (from the storage).
- Topology by `storage.mode`: `"charge"` (summer): cold-well groundwater -> pump -> exchanger
  cold side (building water on the hot side is cooled) -> warm well; heat pump not called.
  `"discharge"` (winter): warm-well groundwater -> pump -> heat pump evaporator -> cold well;
  the condenser heats `return_in` to the heat pump's setpoint; exchanger not called (the
  winter source-circuit exchanger is lumped into the evaporator). `"idle"`: charge topology at
  zero groundwater flow.
- Groundwater loop: `AquiferStorage` produces at the start-of-step temperature of its source
  store, independent of the injected water. The plant reads the new public
  `storage.production_temperature()`, builds the produced stream (`groundwater_flow`,
  `groundwater_pressure`, storage fluid), passes it through pump and exchanger or heat pump and
  calls the storage once with the result, re-pressurised to `groundwater_pressure` (the storage
  passes pressure through and well hydraulics are not modelled, so the pump head minus the
  exchanger drop is what the unmodelled wells and aquifer consume). The storage's
  `production_out` then equals the stream fed to the pump.
- Balance: residual = pump `hydraulic_power` (flow work outside the sensible audit); mass 0.
- Validity: the children's; in charge and idle the building water must be at least as warm as
  the groundwater (exchanger hot side).

```python
import gemini as gm
from gemini.modules import ATESPlant

plant = ATESPlant().update_params(groundwater_pressure="3 bar")
plant.storage.update_params(
    aquifer_temperature="11 degC", aquifer_thickness=30, porosity=0.3,
    rock_volumetric_heat_capacity=2.0e6, ground_conductivity=2.5,
)
plant.pump.update_params(
    head_coefficients=[3e5, 0.0, -1e8], rated_frequency="50 Hz", best_efficiency=0.7,
    best_efficiency_flow=0.03, motor_efficiency=0.9,
)
plant.heat_exchanger.update_params(
    thermal_conductance=1e6, hot_nominal_pressure_drop="0.3 bar", cold_nominal_pressure_drop="0.3 bar",
    hot_nominal_mass_flow=40, cold_nominal_mass_flow=30,
)
plant.heat_pump.update_params(mode="heating", capacity="2 MW")
plant.set_inputs({
    "groundwater_flow": 30.0, "storage.mode": "charge",
    "pump.frequency": "50 Hz", "heat_pump.temperature_setpoint": "40 degC",
})
summer = gm.Stream(flow=40.0, T="17 degC", p="3 bar")
state, result = plant.step(None, 3600, {"return_in": summer})
state, result = plant.step(state, 3600, {"return_in": summer})
print(result.outlets.supply_out.T, result.outputs.stored_energy)  # 285.84 K 2.62e9 J
plant.storage.mode = "discharge"
state, result = plant.step(state, 3600, {"return_in": summer.with_(T=303.15)})
print(result.outputs.production_out_T, result.outlets.supply_out.T)  # 289.91 K 313.15 K
```

### Loop closure inside one call

A composite with an internal closed circuit (the building loop of a substation) finds the
circulated temperature first with `close_loop(update, start, path, lower, upper)` from
`gemini/modules/plants/loops.py`: Wegstein's accelerated substitution (Wegstein 1958,
"Accelerating convergence of iterative processes", Communications of the ACM 1(6), 9-13),
tolerance 1e-9 K, at most 50 passes, then `PhysicsError`. Each trial pass evaluates the
stateless children with `Module.trial_outlets(inlets)`, which no running call records, and the
composite then calls every child once with the converged inlets. A loop through a stateful leaf
whose outlet depends only on its state (the ATES groundwater loop) reads the child's states first
with `Module.start_states()` (`AquiferStorage.production_temperature()` uses it).

### Nodal well analysis

`gemini.modules.plants.nodal` (module import only, not in `gm.plants`) finds the operating
point at which well and reservoir agree, ported from the upstream GEMINI simulator
(`nodal_solver`, `well_flow`). Each function evaluates the plant's own modules with
`ProductionReservoir.sandface_stream`, `InjectionReservoir.required_pressure` and
`Module.trial_outlets`, so no running call records a trial, and solves with
`scipy.optimize.brentq`. Call it before the plant call and apply the result as a command.

- `solve_production_rate(reservoir, well, wellhead_pressure, rates, esp=None, riser=None)`:
  the rate [kg/s] whose sandface stream, lifted through `well` (below the ESP), `esp` and
  `riser`, arrives at `wellhead_pressure` [Pa]; without an ESP `well` is the full well.
- `solve_injection_rate(well, sink, wellhead, rates)`: the rate at which the injection well's
  bottom pressure equals `sink.required_pressure`, for the wellhead stream's pressure.
- `solve_injection_pressure(well, sink, wellhead, pressures)`: the wellhead pressure an
  injection pump must deliver for the stream's rate, or `None` when the pressure at `low`
  (pass the pump suction) already suffices. `None` means no pump: command the `InjectionPump`
  to its suction pressure, which draws zero electricity. Upstream returned the bracket floor.

Brackets are required: `(low, high)` must lie inside the well model's domain (very small rates
can cool the stream below 0 K through the heat loss, very large ones drive the traversed
pressure below zero) and give residuals of opposite sign; otherwise `PhysicsError` names
the trial value or both residuals. On the upstream doublet-A configuration (2400 m producer,
10-stage ESP at 650 m, 3 bar wellhead) the solve gives 135.8666 m3/h at 69 Hz (upstream
135.9258, -0.044 %) and 174406.5 W ESP shaft power at 65 Hz (upstream 174444.7, -0.022 %); the
3100 m injector needs no pump (`None`, upstream 0.001 bar).

`examples/shared/nodal_doublet/plant.py` (`NodalDoublet`) wraps both solves in a handwritten
doublet: `produce()` solves the rate for its `wellhead_pressure` boundary, `inject(stream)` sets
the injection pump to the solved pressure, or to its suction pressure when the solve returns
`None`. `examples/plants/simulate/02_parallel_heat_exchangers.py` uses it with three parallel
exchangers (upstream `parallel_hex_plant`: 125.10 m3/h at 10 bar, the measured 125 m3/h the
upstream index was fitted to; injection 54.86 bar where upstream computes 44.47 bar, because
upstream adds the injector's 5.20 bar friction instead of subtracting it, see
[refactor-notes.md](refactor-notes.md#upstream-development-port)); the example therefore also
recalibrates the injectivity to 2.8430 m3/h/bar, which restores 44.47 bar.
`examples/plants/simulate/03_boiler_chp_secondary.py` (upstream `doublet_plant`) adds a boiler and
a CHP on the secondary side and reports `emissions`; its 3100 m injector needs no pump, so the
injection pump draws zero electricity.

```python
from gemini.modules import ESP, ProductionReservoir, ProductionWell
from gemini.modules.plants import nodal
from gemini.physics.geometry import build_path

path = build_path([dict(MD=d, TVD=d, ID=0.15, roughness=0.01) for d in (0, 300, 400, 600, 2400)])
reservoir = ProductionReservoir().update_params(
    pressure="250 bar", temperature="80 C", permeability=1e-12, aquifer_thickness=100,
    drainage_radius=0, top_depth=2400, productivity_index=10 / 3.6e8, wellbore_radius=0.1,
)
well, riser = (
    ProductionWell().update_params(
        pipe_path=path, soil_temperature="20 C", segment=segment, esp_depth=650
    )
    for segment in ("below_esp", "above_esp")
)
esp = ESP().update_params(
    stage_count=10,
    head_coefficients=[83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21],
    power_coefficients=[10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
)
esp.frequency = "69 Hz"
rate = nodal.solve_production_rate(reservoir, well, 3e5, (5, 60), esp=esp, riser=riser)
assert round(rate * 3.6, 4) == 135.8666
reservoir.production_rate = rate
```

### Heating and cooling template

`heating_cooling` (`gm.plants.from_template("heating_cooling", parameters)`, file
`plants/templates/heating_cooling.json`) is the Challenge 2 plant: one integrated heating and
cooling spec whose units switch on and off. It is a plain template: no value ships, every size is a
`null` default, and the physics is that of the modules below.

- **Wiring.** Brine: `doublet` (`Doublet`) -> `degasser` -> `filters.hot` -> `heat_exchanger` ->
  [`heat_pump`, source side] -> `filters.cold` -> `injection_pump` -> back to the doublet (opened,
  as in `DoubletHeatPlant`). Hot water, in series: `heating_return_pipe` -> `heat_exchanger` (cold
  side) -> [`heat_pump`, sink side] -> [`peak_boiler`] -> [`absorption_chiller`, generator] ->
  [`adsorption_chiller`, generator] -> `heating_supply_pipe` -> `heating_consumer`. Chilled water,
  in series: `cooling_return_pipe` -> [`absorption_chiller`] -> [`adsorption_chiller`] ->
  [`compression_chiller`, a `HeatPump` in cooling mode] -> `cooling_supply_pipe` ->
  `cooling_consumer`. Brackets are optional units.
- **Ports.** Plant inlets: `heating_return_in`, `cooling_return_in` and the heat-rejection circuits
  `absorption_cooling_in`, `adsorption_cooling_in`, `compression_rejection_in` (each goes with its
  chiller). Plant outlets: `heating_return_out`, `cooling_return_out`, `gas` and the three
  rejection outlets. The outputs are the automatic sums (`electricity`, `fuel`, `heat_loss`,
  `heat_supplied`, `heat_absorbed`).
- **Parameters.** `<unit>.enabled` for `heat_pump`, `peak_boiler`, `absorption_chiller`,
  `adsorption_chiller`, `compression_chiller` and `cooling_loop` (the chillers, the cooling pipes
  and the cooling consumer together); sizes `heat_exchanger.thermal_conductance`, the chiller, heat pump and boiler
  capacities, `peak_boiler.efficiency`; length, diameter, elevation change and
  `heat_transfer_coefficient` of the four network pipes; the consumers' return temperatures. Other values are set
  with `plant.set_params` after `from_template`.
- **Presets.** `heating_only` (boiler and heating consumer), `heating_absorption_cooling`,
  `heating_heat_pump_compression_cooling` and `heating_full_cooling` (all three chillers) are the
  template filled with the switches off that name them (`tests/unit/modules/plants/
  test_templating.py` keeps them equal), as plain specs with the size parameters of what remains.
- **Run check.** `tests/integration/test_heating_cooling.py` (slow tier) runs two simulate ticks
  of every preset and of the full template with units off, with the stated assumptions in
  `tests/fixtures/heating_cooling.py`: the `doublet_heat` example values for the brine side, the
  examples of this document for the other modules, 48.95 kg/s of 21.7 degC heating return, boiler
  setpoint 85 degC. The sorption chillers need a driving temperature of at least 80 degC
  (absorption) and at most 90 degC (adsorption) in this series order.
- **Left out.** Hot and cold storage (`ThermalStorage`, `IceStorage`) and every closed return loop
  need a `kind: "state"` connection (the tank couples its charge and discharge circuits through its
  state, so a tank on both circuits of one chain is a loop), and running such a plant raises
  `NotImplementedYet` until scan exists. Heat-rejection loops through a `Cooler` are loops too, so
  they are plant ports here. `CHP` is not wired; it would sit beside `peak_boiler`.
