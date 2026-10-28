"""CSV-backed offline reader with an in-memory output store for engine runs."""

from pathlib import Path

import pandas as pd

from gemini.core.data.connector.csv_driver import CSVDriver


class CSVMemoryReader:
    """Implement the engine reader contract without an InfluxDB service."""

    def __init__(self, path: str | Path, *, end_time: str | None = None):
        """Load measured CSV data; optionally stop at a specific UTC timestamp."""
        self.driver = CSVDriver()
        self.driver.update_parameters({"url": str(path)})
        self.driver.connect()
        if self.driver.df.empty:
            raise ValueError("CSV engine input contains no rows")
        self.end_time = end_time or self.driver.df.index[-1]
        self.tags = {}
        self.outputs = {}
        self.parameters = {}

    def update_parameters(self, parameters):
        """Store the existing plant time-window configuration."""
        self.parameters = dict(parameters)

    def connect(self):
        """Keep the already loaded CSV available for engine reads."""

    def disconnect(self):
        """Release the CSV driver connection."""
        self.driver.disconnect()

    def register_tags(self, units):
        """Map configured internal measured tags to CSV column names."""
        for unit in units:
            for tag, external in unit.tags["measured"].items():
                self.tags[(unit.name, tag + ".measured")] = external[-1]

    def import_raw_data(self):
        """Use the CSV already loaded at construction, without external writes."""

    def get_current_time_str(self):
        """Return the offline run's UTC end time."""
        return self.end_time

    def get_internal_database_last_time_str(self, plant_name, asset_name, tagname):
        """Return the last calculated timestamp or the CSV's initial sample."""
        saved = self.outputs.get((asset_name, tagname), {})
        return max(saved) if saved else self.driver.df.index[0]

    def read_internal_database(self, plant_name, asset_name, tagname, start, end, timestep=None):
        """Read an aligned UTC grid, returning None for absent measurements."""
        step = timestep or self.parameters["measured"]["interval"]
        times = (
            pd.date_range(start, end, freq=pd.Timedelta(seconds=step))
            .strftime("%Y-%m-%dT%H:%M:%SZ")
            .tolist()
        )
        if tagname.endswith(".measured"):
            column = self.tags.get((asset_name, tagname))
            series = (
                self.driver.df[column]
                if column in self.driver.df.columns
                else pd.Series(dtype=float)
            )
        else:
            series = pd.Series(self.outputs.get((asset_name, tagname), {}), dtype=float)
        values = series.reindex(times).tolist()
        return [None if pd.isna(v) else v for v in values], times

    def write_internal_database(self, plant_name, asset_name, tagname, times, values):
        """Store calculated outputs in memory, matching the InfluxDB float conversion."""
        target = self.outputs.setdefault((asset_name, tagname), {})
        target.update(
            {time: None if value is None else float(value) for time, value in zip(times, values)}
        )
