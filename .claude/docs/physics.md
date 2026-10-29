# Core physics rules

`gemini/core/physics` contains reusable correlations: unit conversions, constants, fluid
properties, geometry, hydraulics, heat transfer, pumps, chemistry, corrosion and erosion, and for
the equipment catalogue ([equipment.md](equipment.md)) gas compression, refrigeration cycles,
IAPWS-IF97 steam, ground heat transport and psychrometrics (sections below).

- Use plain typed functions and SI inputs/outputs; small structured return models are allowed.
- State dimensions, reference formulas and assumptions in docstrings.
- Keep correlation-specific US or laboratory bases explicit at the formula boundary.
- `units._UNITS` is the single table of public data units (SI unit, scale, offset). A declared
  difference quantity converts by scale only, so `"5 degC"` as a temperature difference is 5 K.
- Do not perform database I/O, logging or mutate global state during calculations.
- `Fluid` definitions in `core.types.fluid` own immutable overrides and cache their
  `FluidProperties` snapshot; physics must not import types at runtime (`hydraulics` imports
  `Stream` and `Fluid` for type checking only).
- Do not hide undefined diagnostics as valid numbers. The receiving aquifer's unconfigured
  drainage radius leaves radial estimates unavailable while its pressure-flow model works.
- Inputs outside a correlation's domain raise `gm.errors.PhysicsRangeError` instead of dividing
  by zero or returning NaN: zero flow or CO2 pressure where a correlation divides by them or
  takes their logarithm, a negative flow that gives a complex corrosion or erosion rate, NORSOK
  underflow near 360 °C, and a zero liquid superficial velocity in Beggs–Brill. Unsupported
  model names raise `UnknownCorrelationError` and missing chemistry raises
  `MissingChemistryError`.
- The Beggs–Brill flow-regime map follows Beggs and Brill as revised by Brill and Beggs, with
  boundaries at no-slip holdup λ = 0.01 and λ = 0.4. A no-slip holdup of exactly 0.4 takes the
  upper range (intermittent for L3 < Fr <= L4, distributed for Fr > L4); it formerly matched no
  regime and divided by zero. Two-phase reverse flow uses the mirrored friction of forward flow.
- Preserve original numerical cases in `tests/fixtures/golden_values.json`, checked by
  `tests/unit/test_golden.py` and the physics unit tests. Intentional changes require a
  `NOTE(refactor):` sentence in the docstring and measured or physical evidence; see
  [refactor-notes.md](refactor-notes.md).

## Compression

`compression.py` holds ideal-gas adiabatic compression (GPSA Engineering Data Book, 14th ed.
2017, Section 13; compressibility factor Z = 1, constant `k = cp/cv`), used by `GasCompressor`:

- `isentropic_outlet_temperature(T_1, r, k)` = `T_1 r^((k-1)/k)` [K];
- `stage_outlet_temperature(T_1, r, k, eta_s)` = `T_1 + (T_2s - T_1) / eta_s` [K]: every loss
  of an adiabatic stage heats the gas;
- `specific_compression_work(T_1, r, k, cp, eta_s, stages)` = `N cp (T_2 - T_1)` [J/kg] for `N`
  equal stages at ratio `r^(1/N)` with intercooling to `T_1`, the minimum-work split.

A pressure ratio below one (expansion) or non-finite, a nonpositive or non-finite inlet
temperature, `k <= 1`, an efficiency outside (0, 1], a nonpositive `cp` or fewer than one stage
raise `PhysicsRangeError`. Valid for near-ideal gases and stage ratios up to about 4.

## Refrigeration

`refrigeration.py` holds the heat pump, chiller and sorption-machine relations of `HeatPump`,
`AbsorptionUnit` and `AdsorptionChiller`. Inputs and outputs are SI (K, W, W/K); NaN and
out-of-domain inputs raise `PhysicsRangeError`.

- `carnot_cop_heating(sink, source, minimum_lift=0)` = `T_sink / max(T_sink - T_source,
  minimum_lift)` and `carnot_cop_cooling(...)` = `T_source / max(...)`. Nonpositive
  temperatures and a nonpositive floored lift are rejected; for one lift, heating COP = cooling
  COP + 1.
- `log_mean_temperature(T_in, T_out)` = `(T_in - T_out) / ln(T_in / T_out)` (`T_in` when equal),
  the thermodynamic mean temperature of a sensible glide.
- `lorenz_cop_heating(sink_in, sink_out, source_in, source_out, minimum_lift=0)` = `T_h /
  max(T_h - T_s, minimum_lift)` with the log-mean sink and source temperatures (Lorenz 1894); it
  equals the Carnot COP when both glides vanish.
- `characteristic_temperature_difference(t_G, t_AC, t_E, a, r)` = `t_G - a t_AC + r t_E`,
  evaluated in degC from kelvin inputs: the published fits (Hellmann, Schweigler and Ziegler
  1999; Kuehn and Ziegler 2005) use Celsius, and the two bases agree only in the ideal Duehring
  form `1 - a + r = 0`.
- `characteristic_sensitivity(C_G, C_AC, C_E, Q_G/Q_E, Q_AC/Q_E, a, r)` = `k`, the drop of the
  mean-temperature ddt per watt of evaporator duty; `inf` when a circuit is stopped.
- `characteristic_evaporator_duty(ddt_in, ddt_min, s, k)` = `max(0, s (ddt_in - ddt_min) / (1 +
  s k))`, the closed-form solution of `Q_E = s (ddt_mean - ddt_min)`.
- `sorption_evaporator_capacity(...)` combines the three for a machine with a constant thermal
  COP and an auxiliary-electricity ratio: the largest evaporator duty at the circuit inlets.
- `part_load_duty(requested, capacity, minimum_part_load)` = `min(requested, capacity)`, or 0
  below `minimum_part_load * capacity`: the machine is off for the step rather than cycling
  (EN 14825 describes the cycling alternative with a degradation coefficient).

## Steam

`steam.py` holds the exact IAPWS-IF97 equations for water and steam in SI units (Pa, K, J/kg,
J/kg/K), not fits, used by `Separator` and `FlashTurbine`:

- `saturation_pressure(T)` (eq. 30, 273.15 K to 647.096 K) and `saturation_temperature(p)`
  (eq. 31, 611.213 Pa to 22.064 MPa);
- `liquid_enthalpy(p, T)`, `liquid_entropy(p, T)`: region 1 (273.15 K to 623.15 K,
  `p_sat(T) <= p <= 100 MPa`);
- `vapour_enthalpy(p, T)`, `vapour_entropy(p, T)`: region 2 (`0 < p <= p_sat(T)` up to
  623.15 K, `p <= b23_pressure(T)` up to 863.15 K, `p <= 100 MPa` up to 1073.15 K);
- `saturation_properties(p)` returns a frozen `SaturationProperties` (`pressure`,
  `temperature`, `liquid_enthalpy`, `vapour_enthalpy`, `liquid_entropy`, `vapour_entropy`,
  and the properties `evaporation_enthalpy` and `evaporation_entropy`) for 611.213 Pa to
  16.529 MPa; region 3 is not implemented, so saturated states above 623.15 K raise;
- `flash_fraction(h, p)` = `(h - h_f) / h_fg`, zero when subcooled; an enthalpy at or above
  saturated vapour raises;
- `baumann_expansion(p_in, p_out, eta_dry, a)`: dry saturated steam expanded into the wet
  region with the Baumann rule `eta = eta_dry (1 - a (1 - x_mean))`, solved in closed form and
  returned as a frozen `Expansion`; a dry exhaust raises.

The unit tests reproduce the IF97 verification tables 5, 15, 35 and 36 to a relative 1e-8 and
the IF97 steam tables at 0.1 MPa and 1 MPa. States on the saturation line pass the region checks
within a relative pressure tolerance of 1e-9. Properties are those of pure water; salts and
non-condensable gases are not represented. Sources: IAPWS-R7-97(2012); Wagner et al. (2000),
J. Eng. Gas Turbines Power 122, 150-182; DiPippo (2016), Geothermal Power Plants, 4th ed.

## Ground

`ground.py` holds ground and aquifer heat transport for the subsurface equipment. Out-of-domain
inputs (nonpositive sizes or properties, NaN, a negative volume ratio, a cell radius not above
the borehole radius, `ln(4L/D) < 1`, Ramey below `alpha t / r^2 = 25`) raise
`PhysicsRangeError`; modules convert geometry and time errors into `ConfigurationError`.

- `aquifer_volumetric_heat_capacity(phi, (rho c)_w, (rho c)_r)` = `phi (rho c)_w + (1 - phi)
  (rho c)_r`, assuming local thermal equilibrium (Bear 1972).
- `doublet_breakthrough_volume(L, H, (rho c)_a, (rho c)_w)` = `pi L^2 H (rho c)_a / (3 (rho
  c)_w)` (Gringarten and Sauty 1975), without confining-bed conduction or regional flow.
- `doublet_cold_fraction(V / V_B)`: the share `theta / pi` of the produced flow already swept by
  cold water, where theta solves `3 (sin theta - theta cos theta) / sin^3 theta = V / V_B`
  (dipole streamline travel times, checked against integrated streamlines); a Taylor series
  below 0.1 rad avoids cancellation. It is 0 up to breakthrough and 1/2 at `V = 3 V_B`.
- `cylinder_store_conductance(k, alpha, V, H, t_p)` = `2 k A / sqrt(pi alpha t_p)` over the
  envelope of a cylinder of volume V and height H: period-mean semi-infinite conduction
  (Carslaw and Jaeger 1959), valid while `sqrt(alpha t_p)` is small against the store.
- `vertical_cylinder_conductance(k, L, D)` = `2 pi k L / ln(4L/D)` (Incropera, table 4.1), for
  `L >> D`.
- `steady_flux_resistance(k, r_b, r_e)`: the exact uniform-sink annulus resistance, which
  reduces to `(ln(r_e/r_b) - 3/4) / (2 pi k)` (Hellstrom 1991) and is reached after about
  `r_e^2 / (4 alpha)`.
- `ramey_time_function(t, alpha, r)` = `ln(2 sqrt(alpha t) / r) - gamma / 2`, the line-source
  long-time asymptote (Ramey 1962), within about 1 % of `E1(r^2 / (4 alpha t)) / 2` for
  `alpha t / r^2 >= MIN_RAMEY_FOURIER = 25`.
- `ramey_fluid_temperature(T_in, T_top, G, z, A)`: Ramey's exact steady profile in a linear
  gradient with the relaxation length `A = m_dot cp R_total`.

## Psychrometrics

`psychrometrics.py` holds moist-air relations in SI (K, fraction, Pa) for an ideal mixture of
dry air and water vapour without the enhancement factor, used by `CoolingConsumer`:

- `saturation_pressure(T)`: Hyland and Wexler (1983), ASHRAE Handbook - Fundamentals (2017),
  chapter 1, equations 5 (over ice, -100 to 0 degC) and 6 (over water, 0 to 200 degC); within
  3e-4 relative of the ASHRAE table. Outside 173.15 K to 473.15 K or NaN raises.
- `dew_point(T, relative_humidity)`: inverts `saturation_pressure` with Brent's method (to
  1e-9 K), so the two are consistent by construction; below 0 degC it is the frost point.
  Relative humidity must be in (0, 1]; a dew point below -100 degC raises.
- `humidity_ratio(T, relative_humidity, p)` = `0.621945 p_w / (p - p_w)` (ASHRAE equations 20
  and 22); saturated values are about 0.4 % below the ASHRAE `W_s` column. `p <= p_w` raises.
- `wet_bulb_temperature(T, relative_humidity)`: Stull (2011), J. Appl. Meteor. Climatol. 50,
  2267-2269, fitted at 101.325 kPa; valid for -20 to 50 degC and relative humidity 0.05 to 0.99
  (error -1 to +0.65 K); inputs outside raise.

```python
from gemini.core.physics import psychrometrics

assert round(psychrometrics.saturation_pressure(293.15), 1) == 2338.8
assert round(psychrometrics.dew_point(297.15, 0.5) - 273.15, 2) == 12.95
assert round(psychrometrics.humidity_ratio(293.15, 0.5, 101325), 6) == 0.007262
```
