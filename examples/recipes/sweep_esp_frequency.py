"""Compare one simulated day at three ESP frequencies.

Shows ``gm.Clock.days``, ``gm.Profile.constant``, ``gm.Dataset.from_profiles``, ``gm.simulate`` and
``gm.checks.plant_balance``. Below about 52 Hz this pump cannot lift the produced brine to the
surface and every step fails with a negative pressure, so the sweep starts at 55 Hz.

Run with ``python examples/recipes/sweep_esp_frequency.py``.
"""

from pathlib import Path

import gemini as gm

PLANT = Path(__file__).resolve().parents[2] / "datasets/doublet_heat/plant.json"
FREQUENCIES = ("55 Hz", "60 Hz", "65 Hz")
DAY = gm.Clock.days(2027, 1, 1, days=1)


def inputs(frequency):
    """Return a day of constant production at one pump frequency."""
    value, unit = gm.units.parse(frequency)
    profiles = {
        "doublet.reservoir.production_rate": gm.Profile.constant(150, unit="m3/h", clock=DAY),
        "doublet.esp.frequency": gm.Profile.constant(value, unit=unit, clock=DAY),
        "injection_pump.pressure_setpoint": gm.Profile.constant(51.5, unit="bar", clock=DAY),
    }
    return gm.Dataset.from_profiles(profiles)


def main():
    """Simulate each frequency and print the energy of each module that has one."""
    plant = gm.Plant.load(PLANT)
    for frequency in FREQUENCIES:
        results = gm.simulate(plant, inputs(frequency), clock=DAY)
        closed = all(check["passed"] for check in gm.checks.plant_balance(plant, results))
        print(f"{frequency}: {len(results.errors())} failed rows, balance closes: {closed}")
        for (module, port), row in results.to_frame(table="energy").iterrows():
            if row["energy_MWh"] > 0:
                print(f"  {module + ' ' + port:<26} {row['energy_MWh']:8.3f} MWh")


if __name__ == "__main__":
    main()
