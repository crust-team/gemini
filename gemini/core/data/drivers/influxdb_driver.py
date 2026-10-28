"""InfluxDB connector used as the framework's internal time-series store."""

from datetime import datetime

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from gemini.core.data.drivers.database_driver_abstract import DatabaseDriverAbstract


class InfluxdbDriver(DatabaseDriverAbstract):
    """Time-series database connector for InfluxDB."""

    def __init__(self):
        """Establish connection to InfluxDB internal database."""
        super().__init__()

    def connect(self):
        """Connect to InfluxDB."""
        self.conn = InfluxDBClient(
            url=self.parameters["url"],
            org=self.parameters["org"],
            username=self.parameters["username"],
            password=self.parameters["password"],
        )

    def read_data(self, plant_name, asset_name, tag_name, start_time, end_time, aggregate=None):
        """Read data from internal database."""
        query_api = self.conn.query_api()

        start_time_unix = int(datetime.fromisoformat(start_time).timestamp() - 1)
        end_time_unix = int(datetime.fromisoformat(end_time).timestamp() + 1)

        if aggregate is None:
            query = (
                'from(bucket: "'
                + self.parameters["bucket"]
                + '")\
            |> range(start:'
                + str(start_time_unix)
                + ",stop:"
                + str(end_time_unix)
                + ')\
            |> filter(fn: (r) => r._measurement == "'
                + plant_name
                + '")\
            |> filter(fn: (r) => r._field == "'
                + tag_name
                + '")\
            |> filter(fn: (r) => r.asset_name == "'
                + asset_name
                + '")'
            )
        else:
            query = (
                'from(bucket: "'
                + self.parameters["bucket"]
                + '")\
            |> range(start:'
                + str(start_time_unix)
                + ",stop:"
                + str(end_time_unix)
                + ')\
            |> filter(fn: (r) => r._measurement == "'
                + plant_name
                + '")\
            |> filter(fn: (r) => r._field == "'
                + tag_name
                + '")\
            |> filter(fn: (r) => r.asset_name == "'
                + asset_name
                + '")\
            |> aggregateWindow(every:'
                + str(aggregate)
                + "s, fn: mean)"
            )

        query_result = query_api.query(org=self.parameters["org"], query=query)

        results = []
        timestamps = []

        for table in query_result:
            for record in table.records:
                results.append(record.get_value())
                timestamps.append(record.get_time().strftime("%Y-%m-%dT%H:%M:%SZ"))

        if aggregate:  # fixing aggregation timestamps and values
            timestamps = timestamps[:-1]
            results = results[1:]

        return results, timestamps

    def write_data(
        self,
        plant_name,
        asset_name,
        tag_name,
        time,
        value,
        write_option=SYNCHRONOUS,
        batch_size=5000,
    ):
        """Write data to internal database in batches."""
        if not isinstance(time, list):
            time = [time]
        if not isinstance(value, list):
            value = [value]

        write_api = self.conn.write_api(write_option)

        for start in range(0, len(value), batch_size):
            batch = [
                {
                    "measurement": plant_name,
                    "tags": {"asset_name": asset_name},
                    "fields": {tag_name: float(value[ii]) if value[ii] is not None else None},
                    "time": int(datetime.fromisoformat(time[ii]).timestamp()),
                }
                for ii in range(start, min(start + batch_size, len(value)))
            ]
            write_api.write(
                self.parameters["bucket"], self.parameters["org"], batch, write_precision="s"
            )

    def get_last_data(self, plant_name, asset_name, tag_name):
        """Get last data from database."""
        query_api = self.conn.query_api()

        query = (
            'from(bucket: "'
            + self.parameters["bucket"]
            + '")\
            |> range(start: 0)\
            |> filter(fn: (r) => r._measurement == "'
            + plant_name
            + '")\
            |> filter(fn: (r) => r._field == "'
            + tag_name
            + '")\
            |> filter(fn: (r) => r.asset_name == "'
            + asset_name
            + '")\
            |> last()'
        )

        query_result = query_api.query(org=self.parameters["org"], query=query)

        results = []
        timestamps = []

        for table in query_result:
            for record in table.records:
                results.append(record.get_value())
                timestamps.append(record.get_time().strftime("%Y-%m-%dT%H:%M:%SZ"))

        return results, timestamps

    def get_first_data(self, plant_name, asset_name, tag_name):
        """Get first data from database."""
        query_api = self.conn.query_api()

        query = (
            'from(bucket: "'
            + self.parameters["bucket"]
            + '")\
            |> range(start: 0)\
            |> filter(fn: (r) => r._measurement == "'
            + plant_name
            + '")\
            |> filter(fn: (r) => r._field == "'
            + tag_name
            + '")\
            |> filter(fn: (r) => r.asset_name == "'
            + asset_name
            + '")\
            |> first()'
        )

        query_result = query_api.query(org=self.parameters["org"], query=query)

        results = []
        timestamps = []

        for table in query_result:
            for record in table.records:
                results.append(record.get_value())
                timestamps.append(record.get_time().strftime("%Y-%m-%dT%H:%M:%SZ"))

        return results, timestamps

    def delete_database(self, plant_name, start, stop):
        """Delete measurement from internal database."""
        delete_api = self.conn.delete_api()
        delete_api.delete(
            start,
            stop,
            "_measurement=" + plant_name,
            bucket=self.parameters["bucket"],
            org=self.parameters["org"],
        )

    def delete_database_all(self, plant_name):
        """Delete measurement from internal database."""
        start = "1970-01-01T00:00:00Z"
        stop = "2100-01-01T00:00:00Z"
        delete_api = self.conn.delete_api()
        delete_api.delete(
            start,
            stop,
            "_measurement=" + plant_name,
            bucket=self.parameters["bucket"],
            org=self.parameters["org"],
        )

    def get_tagnames(self, plant_name):
        """Get unitnames and tagnames from database."""
        query_api = self.conn.query_api()

        query = (
            'import "influxdata/influxdb/schema"\n\n\
        schema.measurementTagValues(\
        bucket:"'
            + self.parameters["bucket"]
            + '", \
        measurement:"'
            + plant_name
            + '",\
        tag: "_field", )'
        )

        query_result = query_api.query(org=self.parameters["org"], query=query)

        tagnames = []
        tag_desc = []
        for table in query_result:
            for record in table.records:
                tagnames.append(record.get_value())

        return tagnames, tag_desc
