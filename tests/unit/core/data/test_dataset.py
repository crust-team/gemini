"""In-memory Dataset constructor and UTC tests."""

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import gemini as gm


def test_constructors_fingerprint_bounds_and_types():
    """Every constructor normalises the same values to one stable representation."""
    time = pd.date_range("2024-01-01", periods=4, freq="15min", tz="UTC")
    values = np.array([[1, "ok"], [2, "ok"], [3, "warn"], [4, "ok"]], dtype=object)
    frame = pd.DataFrame(values, columns=["value", "status"])
    frame.insert(0, "time", time)
    datasets = [
        gm.Dataset.from_frame(frame, time_column="time", units={"value": "W"}),
        gm.Dataset.from_dict(
            {"value": [1, 2, 3, 4], "status": ["ok", "ok", "warn", "ok"]},
            time,
            units={"value": "W"},
        ),
        gm.Dataset.from_records(frame.to_dict("records"), "time", units={"value": "W"}),
        gm.Dataset.from_numpy(time, values, ["value", "status"], units={"value": "W"}),
    ]
    assert len({dataset.fingerprint() for dataset in datasets}) == 1
    data = datasets[0]
    assert data.native_step == timedelta(minutes=15)
    assert len(data.read(time[1], time[2])) == 2
    assert len(data.window(time[1], time[2])) == 2
    assert len(data.after(time[1])) == 2
    assert data.to_frame().status.iloc[2] == "warn"


def test_timezones_duplicates_profiles_and_validation():
    """Naive times use the requested zone and duplicate timestamps fail clearly."""
    frame = pd.DataFrame({"time": ["2024-01-01 00:00", "2024-01-01 01:00"], "x": [1, 2]})
    data = gm.Dataset.from_frame(frame, "time", tz="Europe/Oslo")
    assert data.start.hour == 23 and data.start.day == 31
    with pytest.raises(gm.errors.DatasetError, match="timestamp = 2023-12-31T23:00:00"):
        gm.Dataset.from_dict({"x": [1, 2]}, [data.start, data.start])
    clock = gm.Clock.days(2027, 1, 1)
    profiles = gm.Dataset.from_profiles(
        {"flow": gm.Profile.constant(150, unit="m3/h", clock=clock)}
    )
    assert profiles.columns["flow"].unit == "m3/s"
    assert profiles.to_frame().flow.iloc[0] == pytest.approx(150 / 3600)


def test_offset_timestamps_across_daylight_saving_switches_load_as_utc():
    """Exported local timestamps change their UTC offset at DST switches (bug E-engine-002)."""
    frame = pd.DataFrame(
        {
            "time": [
                "2024-03-31T01:00:00+01:00",
                "2024-03-31T03:00:00+02:00",
                "2024-10-27T02:00:00+02:00",
                "2024-10-27T02:00:00+01:00",
            ],
            "x": [1.0, 2.0, 3.0, 4.0],
        }
    )
    data = gm.Dataset.from_frame(frame, "time", tz="Europe/Oslo")
    hours = [t.strftime("%Y-%m-%d %H:%M") for t in data.to_frame().index]
    assert hours == ["2024-03-31 00:00", "2024-03-31 01:00", "2024-10-27 00:00", "2024-10-27 01:00"]


def test_dict_and_numpy_constructors_accept_string_time_axes():
    """Bug E-engine-010: ISO strings failed in from_dict/from_numpy but worked in from_records."""
    time = ["2024-01-01 01:00", "2024-01-01 02:00"]
    by_dict = gm.Dataset.from_dict({"x": [1.0, 2.0]}, time, tz="Europe/Oslo")
    by_numpy = gm.Dataset.from_numpy(time, [[1.0], [2.0]], ["x"], tz="Europe/Oslo")
    assert by_dict.fingerprint() == by_numpy.fingerprint()
    assert by_dict.start.hour == 0


def test_invalid_tables_name_the_offending_values():
    """Construction and reads report the bad value and suggest a close column name."""
    time = pd.date_range("2024-01-01", periods=2, freq="1h", tz="UTC")
    with pytest.raises(gm.errors.DatasetError, match="frame = list"):
        gm.Dataset([1, 2])
    with pytest.raises(gm.errors.DatasetError, match="unit metadata columns = flwo.*'flow'"):
        gm.Dataset.from_dict({"flow": [1, 2]}, time, units={"flwo": "W"})
    with pytest.raises(gm.errors.DatasetError, match=r"shape = \(2, 1\); expected \(rows, 2\)"):
        gm.Dataset.from_numpy(time, [[1], [2]], ["a", "b"])
    with pytest.raises(gm.errors.DatasetError, match="time_column = 'tim'.*'time'"):
        gm.Dataset.from_frame(pd.DataFrame({"time": time, "x": [1, 2]}), "tim")
    data = gm.Dataset.from_dict({"flow": [1, 2]}, time, units={"flow": "m3/h"})
    with pytest.raises(gm.errors.DatasetError, match="columns = flwo; .*'flow'"):
        data.read(columns=["flwo"])
    assert data.unit("flow", "kg/s") == "m3/h" and data.unit("other", "kg/s") == "kg/s"


def test_core_data_has_no_file_or_network_readers():
    """The runtime data package stays an in-memory boundary."""
    root = Path(gm.__file__).parent / "core/data"
    source = "\n".join(path.read_text() for path in root.glob("*.py"))
    for forbidden in ("read_csv", "requests", "influx", "aveva", "sqlalchemy"):
        assert forbidden not in source.lower()
