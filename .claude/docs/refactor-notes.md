# Numerical decisions retained from the package migration

3. EVERY NOTE(refactor), WITH FINAL SOURCE LOCATIONS

gemini/components/pumps/esp.py:89
    old monitoring modules evaluate NumPy float32 coefficients and arithmetic.

gemini/components/pumps/esp.py:114
    original efficiency was percent; this API divides by 100, without clipping.

gemini/components/pumps/esp.py:133
    correction_factor belongs to inferred VLP discharge, not theoretical head.

gemini/components/pumps/esp.py:187
    old calibration fitted affine VLP correction, not polynomial coefficients. Preserve that algorithm separately; this method fits the requested six coefficients.

gemini/components/pumps/esp.py:205
    old plotting normalises flow by f/60; old calculate_output does not.

gemini/components/subsurface/injectionwell.py:65
    legacy injection DPDT uses negative flow; retain that sign convention.

gemini/components/subsurface/reservoir.py:80
    injection example radius=0 made log(radius/rw)=-inf; expose unavailable radial diagnostics as None.

gemini/core/engine/twin_modules/esp_vlp.py:37
    old IPR combined flow [m3/s] with PI labelled [m3/h/bar]. Preserve that dashboard result here; the public reservoir mapper uses correct SI.

gemini/core/engine/twin_modules/esp_vlp.py:45
    old outlet correction always used the first ESP parameter snapshot.

gemini/core/physics/corrosion.py:1496
    NORSOK retains exact-temperature pH branches and fallback 7.

gemini/core/physics/erosion.py:395
    particle mass flow equals total fluid mass flow; no solids fraction.

gemini/core/physics/erosion.py:396
    OKA documents particle diameter as mm; retain it despite dpref=326.

gemini/core/physics/erosion.py:397
    DNV's uppercase comparison to 'titanium' remains unreachable, as before.

gemini/core/physics/geometry.py:223
    example roughness 2e-5 is metres, despite DPDT's old mm comment.

gemini/core/physics/hydraulics.py:350
    DPDT's zero-flow branch suppresses gravity as well as friction.

gemini/core/physics/hydraulics.py:358
    preserve gmf/rho_g/area; the old formula does not use m_g.

gemini/core/plant/param_mapping.py:137
    no legacy calculation establishes this coefficient's meaning or unit.

gemini/core/plant/param_mapping.py:159
    100000 is plausible UA, but it is not calibrated to the example CSV. Nominal pressure drops and mass rates must be supplied to predict hydraulic losses.

gemini/core/plant/param_mapping.py:183
    old ESP intake omitted an entire interval crossing esp_depth (550–700 m).

gemini/core/plant/param_mapping.py:185
    old inferred discharge uses one vertical tubing section above the ESP.

tests/components/heat/test_heatexchanger.py:22
    CSV implies rho*cp=4.410 MJ/m3/K, unlike default water's 4.2174. Density 1050 kg/m3 with the retained cp=4217.4 predicts duty within 0.5%.

Additional preserved behavior: the path marcher retains its 0.001 Pa pressure
floor. ConstantWater retains original defaults and override keys. The unchanged
phase-0 fixture contains 25 cases, including an extra nonzero-power ESP case that
checks efficiency despite the sample pump's all-zero power coefficients.

4. IMPLEMENTATION DECISIONS

- Static reservoir ports use two public subclasses and a private shared base in one
  reservoir.py. Shared well calculations live in core physics; wells share only
  minimal glue and never import each other.
- Runtime unit classes live in core/plant/units. They retain plant/link/tag identity;
  twin_modules adapts their time-series inputs to components obtained via registry.
  Registry discovery was introduced when the engine first needed it, then audited
  in phase 7. Obsolete model bases were removed with the last legacy callers in
  phase 6 rather than leaving a broken transitional commit.
- ESP compute retains raw-flow polynomial evaluation. The plotting helper retains
  the original frequency-normalised flow. The requested six-coefficient fit is
  provided separately from fit_head_correction, which preserves the actual old
  affine VLP calibration. The public API defaults to float64; legacy twins select
  float32 arithmetic and the original conversion/cast order for dashboard parity.
- Old dashboard IPR units, section selection, first-snapshot correction and signed
  injection flows stay in compatibility adapters. Public mappers use correct SI.
  Injection corrosion diagnostics use the same negative flow as injection compute.
- A production well compute traverses its passive full path; callers that model an
  internal ESP use intake_conditions and wellhead_from_discharge explicitly, as
  demonstrated by the doublet example. No implicit pump or network solver is added.
- Stream.with_ revalidates updates instead of using unchecked model_copy, preventing
  negative absolute pressures or invalid temperatures from bypassing validation.
- The original injection example has drainage_radius=0. Undefined radial diagnostics
  return None with a NOTE instead of leaking -inf; IPR and monitoring outputs remain
  available. This deliberate representational change does not alter golden values.
- Empty placeholder Params retain empty/default schemas. Tests cover unexpected
  values/ports; a missing-field or numeric-range test cannot apply to a model with
  no required/numeric fields. compute raises NotImplementedError as requested.
- WIMS integration, remaining wall thickness, linear time-to-minimum, annular flow
  area and API velocity comparison are reusable functions without pandas/UI plumbing.
  Signed wall loss and original special-value handling are retained.
- register_fluid configures a named factory before computation. The doublet example
  uses a consistent 1068 kg/m3 named brine for all streams; default water/brine models
  cannot be overwritten. Calculations do not mutate the registry or their inputs.
- Heat-exchanger UA uses the existing coefficient as a provisional conductance;
  its magnitude is plausible but it is not calibrated to the sample measurements.
  Missing nominal hydraulics default to zero pressure loss and 1 kg/s references;
  measured validation supplies explicit nominal pressure/mass-flow values.
- The CSV heat duty implies rho*cp about 4.410 MJ/m3/K. Validation documents an assumed
  density of 1050 kg/m3 with retained cp=4217.4 J/kg/K. Fitted UA reproduces the first
  five rows within 0.5 K and 2% duty; hot pressure drop is between 10 and 20 kPa.
  The density assumption is explicit, not an independently measured fluid property.
- HeatExchanger.ua_from_measurements uses mean hot/cold duty divided by LMTD and
  rejects more than 5% energy imbalance. Fouling alarm defaults to a 15% UA decline.
- CSVMemoryReader is an optional offline adapter with in-memory writes. It exercises
  all eight original monitoring tags, repeat-step watermarks and missing-suction
  behavior without InfluxDB. Existing service-backed setup remains the default.
- API documentation was rebuilt with autosummary/autodoc. Workflows inline validation
  commands and publish documentation only on main. Old import paths are intentionally
  removed. Distribution version stays 1.0.3; the migration is recorded as Unreleased.

