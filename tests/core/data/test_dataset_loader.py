"""Raw sources, UTC semantics, sampler alignment and bounded reads."""

from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

import gemini as gm
from gemini.core.data.loader import Loader
from gemini.core.engine.clock import LiveClock

DATA = Path(__file__).parents[3] / "datasets/geothermal_doublet"


def test_csv_frame_profile_driver_and_reopen(tmp_path):
    """All offline constructors retain units, flags, bounds and exact source values."""
    csv = gm.Dataset.from_csv(DATA / "geothermal_example_dataset.csv")
    assert len(csv) == 17280 and csv.native_step == timedelta(minutes=15)
    assert csv.read(csv.start, csv.start).esp_status.iloc[0] == "Normal"
    driver = gm.Dataset.from_csv_driver(DATA)
    assert driver.latest_time() == csv.end
    pd.testing.assert_frame_equal(driver.read(csv.start, csv.end), csv.read(csv.start, csv.end))
    path = tmp_path / "local.csv"
    path.write_text("Timestamp;T\n2024-01-01 00:00;10\n2024-01-01 01:00;20\n")
    local = gm.Dataset.from_csv(path, tz="Europe/Oslo", units={"T": "degC"})
    assert local.start.hour == 23 and local.start.day == 31
    clock = gm.Clock.days(2027, 1, 1)
    profiles = gm.Dataset.from_profiles(
        {"flow": gm.Profile.constant(150, unit="m3/h", clock=clock)}
    )
    assert profiles.columns["flow"].unit == "m3/s"
    assert profiles.read(profiles.start, profiles.start).flow.iloc[0] == 150 / 3600
    for source in (local, csv, driver, profiles, csv.window(csv.start, csv.start)):
        restored = gm.Dataset.reopen(source.describe())
        pd.testing.assert_frame_equal(
            restored.read(source.start, source.end), source.read(source.start, source.end)
        )
    assert len(csv.window(csv.start, csv.start)) == 1
    with pytest.raises(ValueError, match="unique"):
        gm.Dataset.from_frame(pd.DataFrame({"x": [1, 2]}, index=[csv.start] * 2))


def test_mean_previous_exact_gaps_and_chunk_boundaries():
    """Hourly means match hand calculation; chunk overlaps neither omit nor duplicate rows."""
    index = pd.date_range("2024-01-01", periods=12, freq="15min", tz="UTC")
    source = gm.Dataset.from_frame(
        pd.DataFrame({"v": range(12), "status": ["Normal"] * 12}, index=index)
    )
    clock = gm.Clock.range(index[0], index[-1], "1h")
    whole = list(Loader(source, clock, align="mean"))
    chunked = list(Loader(source, clock, align="mean", chunk=timedelta(hours=1)))
    assert whole == chunked
    assert [s.row["v"] for s in whole] == [1.5, 5.5, 9.5]
    assert [s.row["status"] for s in whole] == ["Normal"] * 3
    for align in ("exact", "previous"):
        assert list(Loader(source, clock, align=align)) == list(
            Loader(source, clock, align=align, chunk=timedelta(minutes=30))
        )
    sparse = gm.Dataset.from_frame(source.frame.drop(index[1:8]))
    ticks = gm.Clock.range(index[0], index[-1], "15min")
    rows = list(Loader(sparse, ticks, max_gap=timedelta(minutes=30)))
    assert rows[2].row["v"] == 0
    assert rows[3].gap and rows[3].missing == ("v", "status")
    assert rows[8].row["v"] == 8
    with pytest.raises(ValueError, match="absent_a, absent_b"):
        Loader(source, clock, columns=["absent_b", "absent_a"])


def test_clock_irregular_dst_descriptions_and_empty():
    """Preserve elapsed intervals, terminal duration and calendar boundaries."""
    frame = pd.DataFrame(
        {"x": [1, 2, 3]},
        index=pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T00:15Z", "2024-01-01T01:00Z"]),
    )
    clock = gm.Clock.from_data(gm.Dataset.from_frame(frame))
    assert [clock.dt(t) for t in clock] == [900, 2700, 1800]
    assert clock.after(list(clock)[0]).dt(list(clock)[-1]) == 1800
    assert list(gm.Clock.reopen(clock.describe())) == list(clock)
    assert len(gm.Clock.days(2024, 3, 31, tz="Europe/Oslo")) == 23
    assert len(gm.Clock.year(2024)) == 366 * 24
    assert (
        len(LiveClock("2024-01-01T01:00Z", "2024-01-01T02:05Z", "15min", start="2024-01-01")) == 4
    )
    assert len(gm.Clock.from_data(gm.Dataset.from_frame(frame.iloc[:0]))) == 0
    with pytest.raises(ValueError, match="positive"):
        gm.Clock.days(2024, 1, 1, step="0s")


def test_remote_constructors_without_services(monkeypatch):
    """Adapters resolve environment credentials without leaking them into descriptors."""
    from gemini.core.data.drivers import sources

    class Remote:
        """Fake remote transport implementing the dataset adapter contract."""

        def __init__(self, **options):
            """Capture safe options."""
            self.options = options
            self.names = ("x",)
            self.start = pd.Timestamp("2024-01-01", tz="UTC").to_pydatetime()
            self.end = self.start + timedelta(hours=1)
            self.native_step = timedelta(hours=1)

        def connect(self):
            """Resolve no real service in unit tests."""

        def read(self, start, end, columns=None):
            """Return two known raw samples."""
            return pd.DataFrame(
                {"x": [1, 2]}, index=pd.date_range(self.start, periods=2, freq="1h")
            ).loc[start:end, list(columns) if columns is not None else slice(None)]

    monkeypatch.setattr(sources, "InfluxSource", Remote)
    monkeypatch.setattr(sources, "AvevaSource", Remote)
    influx = gm.Dataset.from_influx(
        "http://local", "INFLUXDB_TOKEN", "org", "bucket", {"plant_name": "p", "asset_name": "a"}
    )
    aveva = gm.Dataset.from_aveva(
        {"url": "http://local"}, {"x": "stream"}, "2024-01-01", "2024-01-02"
    )
    for source in (influx, aveva):
        assert len(source) == 2
        restored = gm.Dataset.reopen(source.describe())
        pd.testing.assert_frame_equal(
            restored.read(source.start, source.end), source.read(source.start, source.end)
        )
    with pytest.raises(ValueError, match="secret_env"):
        gm.Dataset.from_aveva({"client_secret": "do-not-store"}, {}, "2024-01-01", "2024-01-02")
