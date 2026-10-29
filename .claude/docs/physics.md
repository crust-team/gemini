# Core physics rules

`gemini/core/physics` contains reusable correlations: unit conversions, constants, fluid
properties, geometry, hydraulics, heat transfer, pumps, chemistry, corrosion and erosion, and for
the equipment catalogue ([equipment.md](equipment.md)) gas compression, refrigeration cycles,
IAPWS-IF97 steam, ground heat transport and psychrometrics (sections below, the original GEMINI
correlations first).

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

## Fluid properties

`fluid.py` holds the constant-property snapshot `FluidProperties` and `core/types/fluid.py` the
immutable `Fluid` that selects it (the inherited GEMINI `PVTConstantSTP` model, property model
`constant_stp`). Pressure and temperature do not change any property: `Fluid.properties(p, T)`
returns one cached snapshot per complete `Fluid` value.

- Defaults (water near standard conditions): `rho_l` = 1000 kg/m3, `rho_g` = 1.976 kg/m3,
  `gmf` = 0, `mu_l` = 0.001 Pa s, `mu_g` = 21.29e-6 Pa s, `cp_l` = 4217.4 J/kg/K, `cp_g` =
  819 J/kg/K, `k_l` = 1.6 W/m/K, `k_g` = 0.0147 W/m/K, `sigma` = 0.0728 N/m.
- `density` = `1 / (gmf / rho_g + (1 - gmf) / rho_l)` [kg/m3], the homogeneous mixture density
  from the gas mass fraction `gmf`.
- `kind` is `brine` (default), `water`, `glycol_water` or `steam`. `glycol_water` replaces the
  liquid values by DOWFROST HD, 30 % propylene glycol by volume at 40 degC: `rho_l` = 1029.85,
  `cp_l` = 3841, `k_l` = 0.4622, `mu_l` = 0.0016295 (SI). `liquid_density`, `liquid_viscosity`,
  `specific_heat` and `thermal_conductivity` override the four liquid values after that.
- `corrosion_inputs(p, T)` = `co2_partial_pressure = w_CO2 rho_l / M_CO2 / henry_constant(T)`
  [Pa] and `ionic_strength = salinity rho_l` [kg/m3], with `M_CO2` = 0.04401 kg/mol: the
  dissolved CO2 mass fraction becomes a concentration and the Henry law (Chemistry) is inverted.

Salinity, CO2 and free gas are mass fractions; glycol is a volume fraction. Brine density and
viscosity are not inferred from salinity: supply the overrides. A `steam` fluid carries the
liquid-water snapshot, not vapour properties (use `steam.py`). Mass fractions summing above one,
a glycol fraction on another kind, or a glycol fraction other than 0.3 raise a pydantic
`ValueError`, not `PhysicsRangeError`; `gmf` must lie in [0, 1) and properties must be positive.

## Hydraulics

`hydraulics.py` marches pressure and temperature along a `PipePath` of `PipeSection`s (length
[m], inclination [rad], inner diameter [m], roughness [m]). Inclination is measured from
horizontal, positive when descending in surface-to-bottom order. Friction and gravity drops are
signed so that the pressure rises by both when flowing down and falls by both when flowing up.

- `darcy_weisbach_dp(u, rho, theta, mu, D, K, L)` = friction `f rho L / D |u| u / 2` and
  gravity `rho g L sin(theta)` [Pa], with `Re = |u| rho D / mu` and the Swamee and Jain (1976)
  friction factor `f = 0.25 / log10(K / (3.7 D) + 5.74 / Re^0.9)^2`; `g` = 9.81 m/s2. Zero
  velocity gives zero friction.
- `beggs_brill_dp(us_g, us_l, ...)`: two-phase friction and gravity drops (Beggs and Brill 1973,
  as in Shoham 2006, p. 59). The regime and holdup use the US basis (ft/s, lbm/ft3, dyne/cm,
  ft, `g` = 32.17405 ft/s2). With no-slip holdup `lambda = us_l / (us_g + us_l)`, liquid
  velocity number `N_Lv = 1.938 us_l (rho_l / sigma)^0.25` and `Fr = u_m^2 / (g D)`, the
  boundaries are `L1 = 316 lambda^0.302`, `L2 = 0.0009252 lambda^-2.4684`, `L3 = 0.10
  lambda^-1.4516` and `L4 = 0.5 lambda^-6.738`.
- Horizontal holdup `a lambda^b / Fr^c` with `(a, b, c)` = (0.98, 0.4846, 0.0868) segregated,
  (0.845, 0.5351, 0.0173) intermittent, (1.065, 0.5824, 0.0609) distributed; inclined holdup
  `H_l = H_0 psi` with `psi = 1 + C (sin 1.8 theta - 0.333 sin^3 1.8 theta)` and `C = max(0,
  (1 - lambda) ln(d lambda^e N_Lv^f Fr^h))`. Downhill flow uses (4.7, -0.3692, 0.1244, -0.5056)
  in every regime; uphill segregated (0.011, -3.768, 3.539, -1.614), uphill intermittent (2.96,
  0.305, -0.4473, 0.0978), uphill distributed `psi = 1`. The transition regime blends the
  segregated and intermittent holdups with `A = (L3 - Fr) / (L3 - L2)`; `H_l` is clamped to
  [0, 1].
- Friction: `y = lambda / H_l^2`, `s = ln(2.2 y - 1.2)` for `1 < y < 1.2`, otherwise `s = ln y /
  (-0.0523 + 3.182 ln y - 0.8725 (ln y)^2 + 0.01853 (ln y)^4)`; the multiplier is `exp(s)`. The
  no-slip mixture `rho_m`, `mu_m` give `Re = u_m rho_m D / mu_m`, `f_n = (-0.8685 ln((1.964
  ln Re - 3.8215) / Re + K / (3.71 D)))^-2`, friction `0.5 rho_m u_m |u_m| f_n exp(s) L / D`
  and gravity `(H_l rho_l + (1 - H_l) rho_g) g L sin(theta)` [Pa]. The SI terms use inputs
  converted to the US basis and back, which changes the last bits and is kept for the goldens.
- `pipe_path_profile(path, stream, fluid, direction, u_value, T_ambient)` takes each section
  from `Fluid.properties`: `Q = m_dot / density`, `us_l = (1 - gmf) m / rho_l / A` and, with
  `A = pi D^2 / 4`, Darcy-Weisbach when the gas mass flow is zero, otherwise Beggs-Brill with
  `us_g = gmf / rho_g / A`; the gas velocity keeps the original form, which ignores the flow
  rate. Pressures are floored at 0.001 Pa. `direction` is `up` or `down`; zero flow gives zero
  drops (gravity too). The marched outlet is uncorrected; the affine correction
  `p = a p_out + b` belongs to the `Well` module.
- `geometry.build_path(trajectory, tally)` makes one section per trajectory interval:
  `sin(theta) = delta_TVD / delta_MD`, rounded to 0.01 degree as in WIMS, with the diameter and
  roughness of the interval's end point, split at tally joints (a tally interval covering the
  piece midpoint overrides them). Example roughness 2e-5 is metres.

Beggs-Brill needs a nonzero liquid and mixture velocity and a positive holdup after clamping,
and a point inside the regime map; otherwise `PhysicsRangeError`. `build_path` raises it for
fewer than two points, nonincreasing MD or `|delta TVD| > delta MD`; unsupported correlation
names or a direction other than `up` or `down` raise `UnknownCorrelationError`.

## Reservoir inflow

The reservoir modules (`modules/subsurface/reservoir.py`) combine a linear inflow relation with
the radial Darcy terms of `hydraulics.py` (Akin 2019); volume flow `Q` is at reservoir
conditions, `Q = m_dot / rho_l`.

- Production: `p_bh = p_res - Q / PI` [Pa], `PI` the productivity index [m3/s/Pa].
- Injection: `p_bh = p_res + Q / II` [Pa], `II` the injectivity index [m3/s/Pa] and `Q` the
  absolute volume flow of the arriving stream.
- `productivity_from_measurements` = `Q / (p_res - p_bh)` and `injectivity_from_measurements`
  = `Q / (p_bh - p_res)`; equal pressures raise `PhysicsRangeError`.
- `estimate_pressure(Q_i, p_bh,i)` fits `p_bh / Q = p_res (1 / Q) + b` by least squares: the
  slope is the reservoir pressure and the second return value is the R-squared of the fit.
- `radial_pressure_drops(Q, mu, k, h, r_e, r_w, S)` = flow drop `Q mu ln(r_e / r_w) / (2 pi k
  h)` and skin drop `Q mu S / (2 pi k h)` [Pa]; the radial bottomhole pressure is `p_res +
  flow drop + skin drop`.
- `hydrostatic_dp(rho, height)` = `rho g height` [Pa] with `g` = 9.81 m/s2; the reservoir
  reports it for `rho_l` and the top depth.

A nonpositive `k`, `h`, `r_e` or `r_w` raises `PhysicsRangeError`; `estimate_pressure` needs at
least two finite, nonzero, varying samples (`InsufficientDataError`). Both indices default to
`None` and a missing one raises `ConfigurationError`. The linear relations take the viscosity
and density only through the flow; `mu_l` and `rho_l` come from the reservoir fluid with its
`liquid_density` and `liquid_viscosity` overrides.

## Pumps

`pumps.py` holds the TNO R11363 (2022) polynomial curves of an electrical submersible pump on
the historical US basis, used by `ESP`. The coefficients are ascending powers `c_i` of the flow
`q` in bbl/day, fitted at the catalogue frequency `ESP_REFERENCE_FREQUENCY` = 60 Hz, one pump
stage:

- `head(Q, f, N, c)` = `N (f / 60)^2 sum(c_i q^i) * 2988.30167` [Pa]; the coefficients give ft
  of head and `2988.30167` Pa/ft converts it.
- `power(Q, f, N, c)` = `N (f / 60)^3 sum(c_i q^i) * 745.7` [W]; the coefficients give bhp and
  `745.7` W/bhp converts it.
- `q = Q * 543439.650564` bbl/day for a flow `Q` in m3/s. Head follows the square and power the
  cube of the frequency ratio (affinity laws).
- `ESP.efficiency_function(Q, H, P)` = `(q / 135773) (H / P) (745.7 / 2988.30167)` [-], a
  fraction, and 0 when `P < 0.1` W (it is in `modules/pumps/esp.py`).

The polynomials are only valid inside the flow range of the manufacturer curve; the functions
do not check it and raise nothing. Any number of coefficients is accepted.

## Chemistry

`chemistry.py` holds the Henry-law CO2 partition of GEMINI water-analysis workflows, which
supplies the CO2 partial pressure for the corrosion correlations. Temperatures are in K,
pressures in Pa and concentrations in mol/m3:

- `henry_constant(T)` = `0.01 * 0.0385 exp(2400 (1 / T - 1 / 293.15))` [mol/m3/Pa]: 0.0385
  mol/l/bar at 293.15 K, the factor 0.01 converting to SI.
- `co2_solubility_liquid(x, T, p)` = `x K_H(T) p` [mol/m3], the dissolved CO2 of a gas of mole
  fraction `x` at pressure `p`.
- `co2_solubility_gas(x, GWR, rho_gas, M_gas)` = `x GWR rho_gas / M_gas` [mol/m3] for a standard
  gas-water volume ratio `GWR`, standard gas density [kg/m3] and molar mass [kg/mol].
- `co2_partial_pressure(...)` = `(C_liquid(T_sample, p_gas) + C_gas) / K_H(T_system)` [Pa]: the
  CO2 of the sample, dissolved and in gas, is repartitioned by Henry's law at the system
  temperature.

The functions apply no range checks; a nonpositive temperature is outside the model.

## Corrosion

`corrosion.py` holds the NORSOK M-506 and de Waard-Lotz CO2 corrosion correlations, DLM (Milliams
1991) and DLD (Dugstad 1995), through the SI boundary `co2_corrosion_rate(model, ...)` with
`model` `NORSOK`, `DLM` or `DLD`. Inside, the correlations keep their published basis (degC,
bar, NORSOK water flow in m3/day, viscosity in cP, bicarbonate in mg/l, ionic strength in g/l).
Rates are in mm/year, the explicit literature-unit exception of the package.

- Fugacity: `f = 10^(p (0.0031 - 1.4 / T)) p_CO2` [bar] with `p` the total pressure, capped at
  250 bar, and `T` in K. `p_CO2` is `co2_partial_pressure` [Pa], else `co2_fraction * p`.
- Scale factor `F = min(10^(2400 / T - e log10 f - 6.7), 1)` for `T >= 2400 / (6.7 + 0.6 log10 f)`,
  otherwise 1, with `e` = 0.6 (DLM) or 0.44 (DLD).
- DLM = `10^(5.8 - 1710 / T + 0.67 log10 f) F` [mm/year]; it ignores the flow.
- DLD = `F / (1 / CR_r + 1 / CR_m)` with `CR_r = 10^(4.93 - 1119 / T + 0.58 log10 f)` and
  `CR_m = 2.45 u^0.8 / D^0.2 f`, `u` the velocity from the flow and the diameter.
- NORSOK = `A K_t f^0.62 (tau / 19)^(0.146 + 0.0324 log10 f) f(pH)`. `K_t` interpolates
  linearly in degC over 5, 15, 20, 40, 60, 80, 90, 120, 150 with 0.42, 1.59, 4.762, 8.927,
  10.695, 9.949, 6.250, 7.770, 5.203 and takes the end values outside. The wall shear stress
  is `tau = rho f_w u^2 / 2` with `f_w = 0.001375 (1 + (20000 K / D + 10^6 mu / (u D rho))^0.33)`
  (`mu` in Pa s, `K` roughness).
- `pH` solves the carbonate charge balance for `[H+]` by Newton's method (start 10^-3.5, or
  10^-2.9 above 20 bar CO2; tolerance 1e-6 relative; at most 100 steps and then the last
  iterate without a warning), with equilibrium constants that depend on degF, psi and mol/l
  (bicarbonate molar mass 61.2 g/mol, NaCl 58.44 g/mol); the pH is rounded to 0.01. A
  nonpositive root gives pH 99.99.
- `f(pH)` has piecewise formulas only at the exactly tabulated temperatures 5, 15, 20, 40, 60,
  80, 90, 120 and 150 degC and for pH 3.5 to 6.5; elsewhere it is 7, so the rate jumps between
  40.000 and 40.001 degC. The 5 degC first segment keeps `2.0676 + 0.2309 pH` where the other
  temperatures use `- 0.2309`. Both are retained numerical decisions of the goldens.
- Defaults: `water_density` 1000 kg/m3, `water_viscosity` 0.001 Pa s, `diameter` 0.1 m,
  `roughness` 5e-5 m, `bicarb_concentration` 0.268 kg/m3, `ionic_strength` 71 kg/m3. With
  `fitted=True` the constants (`A`, `B`, `C`, `D`; NORSOK only `A`, the rate scale) can be
  replaced through `coefficients`.
- Wall loss: `wall_loss(rates, durations)` = `cumsum(rate * dt / year)` [mm] with a 365.25-day
  year; `remaining_wall_thickness(r_o, r_i, loss)` = `r_o - (r_i + loss)`; and
  `time_to_minimum_wall(t, t_min, rate)` = `(t - t_min) / rate` [s], 0 at or below the minimum,
  infinity for a nonpositive or nonfinite rate and NaN for missing values.

A CO2 partial pressure of zero, a zero flow for NORSOK and DLD, a negative flow (complex rate)
and equilibrium-constant underflow near 360 degC raise `PhysicsRangeError`; neither
`co2_fraction` nor `co2_partial_pressure` raises `MissingChemistryError`; another model name
raises `UnknownCorrelationError`.

## Erosion

`erosion.py` holds the DNV RP O501, Oka (2005) and E/CRC Tulsa solid-particle erosion rates and
the API RP 14E velocity limit. `erosion_rate(model, ...)` is the SI boundary (flow in m3/s,
angle in rad, hardness in Pa, particle diameter in m) and returns mm/year, the explicit
literature-unit exception of the package. Inside, the flow is in m3/h, the angle in degrees and
radians as each formula needs, the hardness in GPa and the Oka particle diameter in mm.

- Shared terms: the particle mass flow equals the total fluid mass flow (no solids fraction),
  `m_p = Q rho_f`; the velocity is `U = m_p / (rho_f A)`, `A = pi D^2 / 4`, and the impacted
  area is `A_t = A / sin(alpha)`.
- DNV = `Y m_p K U^n F(alpha) / (rho_pipe A_t)` with `Y = 1000 * 365.25 * 86400` mm/year per
  m/s and `F` the seventh-order polynomial of `alpha` [rad] `alpha (9.37 + alpha (-42.295 +
  alpha (110.864 + alpha (-175.804 + alpha (170.137 + alpha (-98.398 + alpha (31.211 - 4.17
  alpha)))))))`. `(K, n, rho_pipe)` is (2e-9, 2.6, 7800) for `steel`, (0.3e-9, 3.6, 1800) for
  `grp/epoxy` and (0.6e-9, 3.6, 1800) for `grp/vinyl ester` (case-insensitive).
- Oka = `year m_p / A_t E` with `A_t` in mm2 and `E = K Hv^k1 (U / U_ref)^k2(Hv) (d_p / d_ref)^k3`
  [mm3/kg], `Hv` in GPa and `d_p` in mm. For `SIO2`, `SIC`, `GLASS`: `U_ref` = 104, 99, 100 m/s;
  `d_ref` = 326, 326, 200; `k1` = -0.12, -0.05, -0.16; `k2` = `2.3 Hv^0.038`, `3 Hv^0.085`,
  2.1; `k3` = 0.19; `K` = 65, 45, 27.
- Tulsa = `Y E_r m_p / (rho_pipe A_t)` with `E_r = 2.17e-7 H_b^-0.59 F_s U^2.41 F(alpha)`,
  `F(alpha) = 5.4 alpha - 10.11 alpha^2 + 10.93 alpha^3 - 6.33 alpha^4 + 1.42 alpha^5` and the
  Brinell hardness `H_b = 0.95057 Hv / 0.009807 - 0.03743` from the Vickers hardness in GPa.
- Defaults: `alpha` = pi/2, `material` `steel`, `hardness` 1e9 Pa, `particle_material` `SIO2`,
  `particle_diameter` 0.0001 m, `rho_pipe` 7800 kg/m3, `shape_factor` 0.5.
- `api_erosional_velocity(rho)` = `0.3048 / sqrt(0.0283 / 0.454) * 125 / sqrt(rho)` [m/s], the
  API RP 14E criterion with `C` = 125 and its imperial conversions;
  `api_velocity_comparison(u, limit)` returns the ratio `u / limit`, the margin `limit - u` and
  the flag `u > limit`.

Model names are case-insensitive (`DNV`, `DNVGL`, `OKA`, `TULSA`, `E/CRC Tulsa`, `ECRC`); `API`
is a velocity limit, not a rate. Unknown names, DNV materials (titanium is rejected) and Oka
particle materials raise `UnknownCorrelationError`. A zero impact angle, a negative flow (complex
rate) and a nonpositive density or API limit raise `PhysicsRangeError`.

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
