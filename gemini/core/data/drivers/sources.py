"""Read-only dataset adapters around the existing remote connectors."""

import os

import pandas as pd

from gemini.core.types.bindings import utc


class InfluxSource:
    """Read a plant/asset selection with token credentials referenced by environment name."""

    def __init__(self, url, token, org, bucket, tags):
        """Retain nonsecret connection settings and explicit selection tags."""
        from gemini.core.data.drivers.influxdb_driver import InfluxdbDriver

        self.driver = InfluxdbDriver()
        self.options = dict(url=url, org=org, bucket=bucket)
        self.token_env, self.tags = token, tags
        if set(tags) != {"plant_name", "asset_name"}:
            raise ValueError("Influx tags require plant_name and asset_name")

    def connect(self):
        """Resolve credentials only when connecting; never serialize their values."""
        from influxdb_client import InfluxDBClient

        self.driver.parameters = self.options
        self.driver.conn = InfluxDBClient(
            **{k: v for k, v in self.options.items() if k != "bucket"},
            token=os.environ[self.token_env]
        )
        self.names = self.driver.get_tagnames(self.tags["plant_name"])[0]

    def _bound(self, method, pick):
        times = []
        for name in self.names:
            _, values = getattr(self.driver, method)(
                self.tags["plant_name"], self.tags["asset_name"], name
            )
            times.extend(utc(t) for t in values)
        return pick(times) if times else None

    @property
    def start(self):
        """Return the earliest selected field timestamp."""
        return self._bound("get_first_data", min)

    @property
    def end(self):
        """Return the latest selected field timestamp."""
        return self._bound("get_last_data", max)

    @property
    def native_step(self):
        """Leave irregular remote cadence unspecified; callers may select an explicit step."""
        return None

    def read(self, start, end, columns=None):
        """Read selected fields independently, then align on their union of UTC timestamps."""
        series = {}
        for name in self.names if columns is None else columns:
            values, times = self.driver.read_data(
                self.tags["plant_name"],
                self.tags["asset_name"],
                name,
                utc(start).isoformat(),
                utc(end).isoformat(),
            )
            series[name] = pd.Series(values, index=pd.to_datetime(times, utc=True))
        return pd.DataFrame(series).sort_index().loc[utc(start) : utc(end)]


class AvevaSource:
    """Read AVEVA's interpolated streams on an explicitly bounded cadence."""

    def __init__(self, parameters, streams, start, end, step, secret_env):
        """Retain the selected stream mapping and nonsecret service parameters."""
        from gemini.core.data.drivers.avevadb_driver import AvevaDriver

        self.driver = AvevaDriver()
        self.parameters, self.streams, self.secret_env = parameters, streams, secret_env
        self.start, self.end = utc(start), utc(end)
        self.native_step = pd.Timedelta(step).to_pytimedelta()
        if self.native_step.total_seconds() <= 0:
            raise ValueError("AVEVA step must be positive")
        self.names = tuple(streams)

    def connect(self):
        """Connect using an environment-provided client secret."""
        self.driver.update_parameters(
            self.parameters | {"client_secret": os.environ[self.secret_env]}
        )
        self.driver.connect()

    def read(self, start, end, columns=None):
        """Read each named stream using the existing connector's bounded pagination."""
        series = {}
        for name in self.names if columns is None else columns:
            values, times = self.driver.read_data(
                self.streams[name],
                utc(start).isoformat(),
                utc(end).isoformat(),
                self.native_step.total_seconds(),
            )
            series[name] = pd.Series(values, index=pd.to_datetime(times, utc=True))
        return pd.DataFrame(series).sort_index().loc[utc(start) : utc(end)]
