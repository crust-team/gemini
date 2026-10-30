"""Doublet with three parallel heat exchangers and nodal-solved production and injection.

The port of the upstream GEMINI simulator's ``parallel_hex_plant`` example. The producer, an
18-stage ESP at 550 m in a deviated well, is solved for its rate at the measured 10 bar
wellhead pressure; the brine passes a degasser and a filter, is divided 50/30/20 over three
counterflow heat exchangers, remixed, filtered again and injected, with the injection pump set
to the wellhead pressure the injector needs (nodal analysis). The secondary water, 125.1 m3/h
at 20 degC, is divided in the same shares and remixed after the exchangers.

Well, reservoir, ESP and exchanger data are the upstream example's. The reservoir temperature,
80 degC, is this example's assumption: upstream fixes the wellhead temperature at 77 degC
instead of producing from a reservoir temperature. Degasser and filters use the refactored
models' plant-calibrated defaults.

Upstream fitted the injectivity index, 2.3 m3/h/bar, to a wellhead pressure of 44.47 bar at
125.1 m3/h with a well traversal that adds the injector's friction instead of subtracting it.
With the correct sign that index needs 54.86 bar, so the example recalibrates it from the same
point: the 44.47 bar wellhead stream is traversed down the injector and
``InjectionReservoir.injectivity_from_measurements`` gives Q / (p_bh - p_res), about
2.84 m3/h/bar. The plant runs with both indices.

Run from the repository root:
PYTHONPATH=. python examples/plants/simulate/02_parallel_heat_exchangers.py
"""

import gemini as gm
from examples.shared.nodal_doublet import NodalDoublet
from gemini.modules import HeatExchanger, Mixer, ModuleList, Splitter, energy_balance
from gemini.modules.treatment import Degasser, Filter
from gemini.physics.geometry import build_path
from gemini.types import (
    Duty,
    Electricity,
    Inlet,
    Outlet,
    Output,
    Stream,
)

SHARES = (0.5, 0.3, 0.2)
"""Shares of the primary and the secondary flow sent to each heat exchanger."""

CONDUCTANCES = (6010, 3606, 2404)
"""Upstream heat-transfer conductance UA [W/K] of each heat exchanger."""

PRODUCER_SURVEY = [
    (0, 0, 0.1778),
    (400, 400, 0.1778),
    (550, 550, 0.1778),
    (700, 700, 0.1778),
    (904, 900, 0.273),
    (1062, 1050, 0.273),
    (1243, 1200, 0.273),
    (1348, 1300, 0.273),
    (1634, 1500, 0.273),
    (2152, 1900, 0.273),
]
"""Upstream producer survey stations: MD [m], TVD [m], inner diameter [m]."""

INJECTOR_SURVEY = [
    (0, 0, 0.1616964),
    (148, 148, 0.1616964),
    (1097, 1034, 0.25273),
    (2109, 1742, 0.1616964),
    (2327, 1883, 0.0995668),
]
"""Upstream injector survey stations: MD [m], TVD [m], inner diameter [m]."""

UPSTREAM_INJECTIVITY = 2.3 / 3.6e8
"""Upstream injectivity index [m3/s/Pa]: 2.3 m3/h/bar, fitted with the friction sign reversed."""

FITTED_INJECTION = gm.Stream(flow="125.1 m3/h", T="70 degC", p="44.47 bar")
"""Injector wellhead point upstream fitted its injectivity to (the temperature does not enter
the constant-property traversal)."""


class ParallelExchangerPlant(gm.modules.Module):
    """Nodal doublet whose brine heats one secondary network through three parallel exchangers."""

    def __init__(self):
        """Build the plant; the tees are cascades of two-way splitters and mixers."""
        super().__init__()

        # Modules
        self.doublet = NodalDoublet()
        self.degasser = Degasser()
        self.inlet_filter = Filter()
        self.primary_splitters = ModuleList(Splitter() for _ in SHARES[1:])
        self.secondary_splitters = ModuleList(Splitter() for _ in SHARES[1:])
        self.heat_exchangers = ModuleList(HeatExchanger() for _ in SHARES)
        self.primary_mixers = ModuleList(Mixer() for _ in SHARES[1:])
        self.secondary_mixers = ModuleList(Mixer() for _ in SHARES[1:])
        self.outlet_filter = Filter()

        # Inlets
        self.secondary_in = Inlet(Stream)

        # Outputs
        self.production_rate = Output.of(self.doublet.riser.wellhead.field("m_dot"))
        self.injection_pressure = Output.of(self.doublet.injection_pump.discharge_pressure)
        self.injection_pump_electricity = Output.of(self.doublet.injection_pump.electricity)
        self.duty = Output(Duty)
        self.electricity = Output(Electricity)
        self.secondary_out_T = Output.of(self.secondary_mixers[len(SHARES) - 2].mixed_out_T)

        # Outlets
        self.secondary_out = Outlet(Stream)

    def forward(self, inlets):
        """Produce and treat the brine, exchange in parallel, remix and inject it."""

        # Modules
        supply = self.doublet.produce()
        degassed = self.degasser(inlet=supply)
        filtered = self.inlet_filter(inlet=degassed.outlets.liquid)
        primaries = divide(self.primary_splitters, filtered.outlets.outlet)
        secondaries = divide(self.secondary_splitters, inlets.secondary_in)
        exchanged = [
            exchanger(hot_in=hot, cold_in=cold)
            for exchanger, hot, cold in zip(self.heat_exchangers, primaries, secondaries)
        ]
        cooled = combine(self.primary_mixers, [each.outlets.hot_out for each in exchanged])
        returned = self.outlet_filter(inlet=cooled)
        self.doublet.inject(returned.outlets.outlet)

        # Outlets
        secondary_out = combine(
            self.secondary_mixers, [each.outlets.cold_out for each in exchanged]
        )

        outlets = dict(secondary_out=secondary_out)
        return outlets


def divide(splitters, stream):
    """Return the branches of a splitter cascade: each splitter sends its share to a branch."""
    branches = []
    for splitter in splitters:
        split = splitter(feed_in=stream)
        branches.append(split.outlets.second_out)
        stream = split.outlets.first_out
    return branches + [stream]


def combine(mixers, streams):
    """Return the stream a mixer cascade makes of ``streams``, the running mix entering first."""
    mixed = streams[0]
    for mixer, stream in zip(mixers, streams[1:]):
        mixed = mixer(first_in=mixed, second_in=stream).outlets.mixed_out
    return mixed


def survey_path(stations):
    """Return the well path of upstream survey stations with 2e-5 m roughness."""
    rows = [dict(MD=md, TVD=tvd, ID=bore, roughness=2e-5) for md, tvd, bore in stations]
    return build_path(rows)


def configure_doublet(doublet):
    """Fill the upstream wells: 216 bar producer at 1.76 m3/h/bar, 180 bar injector at 2.3."""
    reservoir = dict(
        temperature="80 degC",
        permeability=1e-12,
        aquifer_thickness=100,
        drainage_radius=0,
        wellbore_radius=0.1,
    )
    doublet.reservoir.update_params(
        pressure="216 bar", productivity_index=1.76 / 3.6e8, top_depth=1900, **reservoir
    )
    producer = dict(
        pipe_path=survey_path(PRODUCER_SURVEY), soil_temperature="20 degC", esp_depth=550
    )
    doublet.well.update_params(segment="below_esp", **producer)
    doublet.riser.update_params(segment="above_esp", **producer)
    doublet.esp.update_params(
        stage_count=18,
        head_coefficients=[
            125.518426,
            -0.0020852856,
            2.28955651e-07,
            -1.45640214e-11,
            2.37859645e-16,
            -1.18258356e-21,
        ],
        power_coefficients=[10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
    )
    doublet.esp.frequency = "60 Hz"
    doublet.injection_pump.update_params(efficiency=0.8)
    doublet.injector.update_params(
        pipe_path=survey_path(INJECTOR_SURVEY), soil_temperature="20 degC"
    )
    doublet.sink.update_params(
        pressure="180 bar", injectivity_index=UPSTREAM_INJECTIVITY, top_depth=1883, **reservoir
    )
    doublet.update_params(production_rates=(5, 60), maximum_injection_pressure="500 bar")
    doublet.wellhead_pressure = "10 bar"


def recalibrated_injectivity(doublet):
    """Return the injectivity index [m3/s/Pa] that reproduces ``FITTED_INJECTION``.

    The wellhead stream is traversed down the injection well to its bottom pressure, then
    ``InjectionReservoir.injectivity_from_measurements`` gives Q / (p_bh - p_res) with the
    volume flow Q at the aquifer's fluid density.
    """
    bottom = doublet.injector(wellhead=FITTED_INJECTION).outlets.bottom
    flow = abs(bottom.m_dot) / doublet.sink.fluid.properties(bottom.p, bottom.T).rho_l
    return doublet.sink.injectivity_from_measurements(flow, bottom.p)


def configure_exchangers(plant):
    """Fill the exchangers (no pressure loss, as upstream) and the 50/30/20 split fractions."""
    for exchanger, ua, share in zip(plant.heat_exchangers, CONDUCTANCES, SHARES):
        exchanger.update_params(
            thermal_conductance=ua,
            hot_nominal_pressure_drop=0,
            cold_nominal_pressure_drop=0,
            hot_nominal_mass_flow=35 * share,
            cold_nominal_mass_flow=35 * share,
        )
    remaining = 1.0
    for index, share in enumerate(SHARES[:-1]):
        plant.primary_splitters[index].split_fraction = share / remaining
        plant.secondary_splitters[index].split_fraction = share / remaining
        remaining -= share


plant = ParallelExchangerPlant()
configure_doublet(plant.doublet)
configure_exchangers(plant)
secondary = gm.Stream(flow="125.1 m3/h", T="20 degC", p="3 bar", fluid=gm.Fluid(kind="water"))
upstream = plant(secondary_in=secondary).outputs
injectivity = recalibrated_injectivity(plant.doublet)
plant.doublet.sink.update_params(injectivity_index=injectivity)
result = plant(secondary_in=secondary)
out = result.outputs
print(f"Primary flow (nodal solve):  {out.production_rate / 1000 * 3600:.2f} m3/h")
for label, index, run in (
    ("upstream", UPSTREAM_INJECTIVITY, upstream),
    ("recalibrated", injectivity, out),
):
    print(
        f"Injectivity {label:<12}     {index * 3.6e8:.4f} m3/h/bar: injection "
        f"{run.get('injection_pressure', unit='bar'):.2f} bar, pump "
        f"{run.get('injection_pump_electricity', unit='kW'):.1f} kW"
    )
for index in range(len(SHARES)):
    exchanger = result.children[f"heat_exchangers.{index}"].outputs
    print(
        f"Exchanger {index + 1}:                 {exchanger.get('duty', unit='kW'):.1f} kW, "
        f"secondary out {exchanger.get('cold_out_T', unit='degC'):.2f} degC"
    )
print(f"Total duty:                  {out.get('duty', unit='kW'):.1f} kW")
print(f"Secondary outlet:            {out.get('secondary_out_T', unit='degC'):.2f} degC")
print(f"Electricity (ESP and pump):  {out.get('electricity', unit='MW'):.4f} MW")
print(f"Mass residual:               {gm.modules.mass_balance(plant, result)['residual']} kg/s")
assert energy_balance(plant, result)["relative_thermal_residual"] < 1e-9
assert abs(out.get("injection_pressure", unit="bar") - 44.47) < 0.05
