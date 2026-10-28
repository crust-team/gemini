"""Abstract database reader organizing internal/external data flows.

Coordinates reading from an external source and writing into the framework's
internal time-series database (InfluxDB by default), including tag
registration and time handling.
"""

import logging
import os
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import pytz

from gemini.core.data.connector.influxdb_driver import InfluxdbDriver

tz_ams = pytz.timezone("Europe/Amsterdam")

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


class DatabaseReaderAbstract(ABC):
    """Abstract base class for database readers."""

    def __init__(self):
        """Initialize database reader."""
        self.category = None
        self.internal_db_driver = InfluxdbDriver()
        self.external_db_driver = None

        self.tags = []
        self.parameters = dict()
        self.delta_t = 900
        self.logger = logger

    def update_parameters(self, parameters):
        """Update reader parameters."""
        for key, value in parameters.items():
            self.parameters[key] = value

        self.delta_t = self.parameters[self.category]["interval"]

        self.set_internal_db_parameters()
        self.set_external_db_parameters()

    def set_internal_db_parameters(self):
        """Set internal database parameters."""
        influxdb_param = {
            "url": os.getenv("INFLUXDB_URL"),
            "org": os.getenv("INFLUXDB_ORG"),
            "username": os.getenv("INFLUXDB_USERNAME"),
            "password": os.getenv("INFLUXDB_PASSWORD"),
            "bucket": os.getenv("INFLUXDB_BUCKET"),
        }

        self.internal_db_driver.update_parameters(influxdb_param)

    @abstractmethod
    def set_external_db_parameters(self):
        """Set external database parameters."""
        pass

    def connect(self):
        """Connect to databases."""
        self.internal_db_driver.connect()
        self.external_db_driver.connect()

    def disconnect(self):
        """Disconnect from databases."""
        self.internal_db_driver.disconnect()
        self.external_db_driver.disconnect()

    def register_tags(self, config):
        """Register configured measured columns for each equipment module."""
        self.tags = []
        for name, bound in config.bindings.items():
            fields = dict(bound.inputs) | dict(bound.measured)
            for port, bindings in bound.streams.items():
                fields.update({f"{port}.{key}": value for key, value in bindings.items()})
            for key, binding in fields.items():
                self.tags.append(
                    {
                        "plant_name": config.name,
                        "asset_name": name,
                        "internal_tagname": key + ".measured",
                        "external_tagname": binding.column,
                    }
                )

    def get_current_time_str(self):
        """Get current time as string."""
        current_time_datetime = self.round_minutes(datetime.utcnow(), "down", self.delta_t / 60)
        current_time_str = current_time_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

        return current_time_str

    def write_internal_database(self, plant_name, asset_name, internal_tagname, time, result):
        """Write data to internal database."""
        self.internal_db_driver.write_data(plant_name, asset_name, internal_tagname, time, result)

    def read_internal_database(
        self, plant_name, asset_name, internal_tagname, starttime_str, endtime_str, timestep=None
    ):
        """Read data from internal database."""
        if timestep is None:
            timestep = self.delta_t

        result, time = self.internal_db_driver.read_data(
            plant_name, asset_name, internal_tagname, starttime_str, endtime_str, timestep
        )

        return result, time

    def read_external_database(self, external_tagname, starttime_str, endtime_str, timestep=None):
        """Read data from external database."""
        if timestep is None:
            timestep = self.delta_t

        result, time = self.external_db_driver.read_data(
            external_tagname, starttime_str, endtime_str, timestep
        )

        return result, time

    def get_internal_database_last_time_str(self, plant_name, asset_name, tagname):
        """Get last time from internal database."""
        _, timestamps = self.internal_db_driver.get_last_data(plant_name, asset_name, tagname)

        if timestamps:
            lasttime_str = timestamps[0]
        else:
            lasttime_datetime = datetime.strptime(
                self.parameters["start_time"], "%Y-%m-%d %H:%M:%S"
            )
            lasttime_datetime = tz_ams.localize(lasttime_datetime)
            lasttime_str = lasttime_datetime.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return lasttime_str

    def delete(self, plant_name):
        """Delete plant data from database."""
        self.internal_db_driver.delete_database_all(plant_name)

    def import_raw_data(self):
        """Import raw data from external to internal database."""
        endtime_str = self.get_current_time_str()

        for tag in self.tags:
            if tag["external_tagname"] == "":
                continue

            starttime_str = self.get_internal_database_last_time_str(
                tag["plant_name"], tag["asset_name"], tag["internal_tagname"]
            )

            if not (starttime_str == endtime_str):
                try:
                    self.logger.info(
                        "Reading "
                        + tag["external_tagname"]
                        + " from "
                        + starttime_str
                        + " to "
                        + endtime_str
                    )

                    result, time = self.read_external_database(
                        tag["external_tagname"], starttime_str, endtime_str
                    )

                    self.logger.info(
                        "Writing : "
                        + tag["internal_tagname"]
                        + " of "
                        + tag["asset_name"]
                        + " from "
                        + starttime_str
                        + " to "
                        + endtime_str
                    )

                    self.write_internal_database(
                        tag["plant_name"], tag["asset_name"], tag["internal_tagname"], time, result
                    )
                except Exception:
                    self.logger.error(
                        "ERROR in module "
                        + self.__class__.__name__
                        + " : "
                        + traceback.format_exc()
                    )

    @staticmethod
    def round_minutes(dt, direction, resolution):
        """Round datetime to specified resolution."""
        new_minute = (dt.minute // resolution + (1 if direction == "up" else 0)) * resolution

        return dt + timedelta(
            minutes=new_minute - dt.minute, seconds=-dt.second, microseconds=-dt.microsecond
        )
