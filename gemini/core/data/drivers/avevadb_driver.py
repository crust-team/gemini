"""AVEVA Data Hub connector implementation."""

import math
from datetime import datetime

import adh_sample_library_preview as dbconn
import pandas as pd

from gemini.core.data.drivers.database_driver_abstract import DatabaseDriverAbstract


class AvevaDriver(DatabaseDriverAbstract):
    """Database connector based on AVEVA Data Hub APIs."""

    def __init__(self):
        """Establish connection to AVEVA database."""
        super().__init__()

    def connect(self):
        """Connect to AVEVA database."""
        self.conn = dbconn.ADHClient(
            api_version=self.parameters["api_version"],
            url=self.parameters["url"],
            tenant=self.parameters["tenant"],
            client_id=self.parameters["client_id"],
            client_secret=self.parameters["client_secret"],
        )

    def read_data(self, stream_id, start_time, end_time, interval):
        """Read data from AVEVA database."""
        url = "/".join(
            [
                self.parameters["url"],
                "api",
                self.parameters["api_version"],
                "Tenants",
                self.parameters["tenant"],
                "Namespaces",
                self.parameters["namespace_id"],
                "Streams",
                "",
            ]
        )

        Nsize = 500

        start_time_datetime = datetime.fromisoformat(start_time)
        end_time_datetime = datetime.fromisoformat(end_time)

        start_time_unix = int(start_time_datetime.timestamp())
        end_time_unix = int(end_time_datetime.timestamp())

        length_intervals = round((end_time_unix - start_time_unix) / interval) + 1

        stream_data_dfs = None
        remaining = length_intervals
        for ii in range(math.ceil(length_intervals / Nsize)):
            start_index_unix = start_time_unix + ii * Nsize * interval

            start_index = datetime.utcfromtimestamp(start_index_unix).strftime("%Y-%m-%dT%H:%M:%SZ")
            if remaining > Nsize:
                end_index_unix = start_time_unix + ((ii + 1) * Nsize - 1) * interval
                end_index = datetime.utcfromtimestamp(end_index_unix).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                end_index_unix = end_time_unix
                end_index = datetime.utcfromtimestamp(end_index_unix).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(start_index + " to " + end_index)
            stream_interval = round((end_index_unix - start_index_unix) / interval) + 1

            stream_data = self.conn.Streams.getRangeValuesInterpolatedUrl(
                url=url + stream_id,
                start=start_index,
                end=end_index,
                count=stream_interval,
                value_class=None,
            )

            stream_data_df = pd.DataFrame(stream_data)
            time_col = "Timestamp" if "Timestamp" in stream_data_df.columns else "Time"
            stream_data_df["Timestamp"] = (
                pd.to_datetime(stream_data_df[time_col], utc=True, format="mixed")
                .round("min")
                .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            stream_data_df = stream_data_df.set_index("Timestamp")

            value_col = "Value" if "Value" in stream_data_df.columns else "Double64"
            if stream_data_df.columns.to_list().__contains__(value_col):
                stream_data_df = stream_data_df.loc[:, [value_col]]
                stream_data_df.columns = [stream_id]
                stream_data_df[stream_id] = stream_data_df[stream_id].astype(float)
            else:
                stream_data_df[stream_id] = None

            stream_data_dfs = pd.concat([stream_data_dfs, stream_data_df])

            remaining = remaining - Nsize

        results = stream_data_dfs[stream_id].to_list()
        timestamps = stream_data_dfs.index.values.tolist()

        return results, timestamps

    def get_tagnames(self, tagname_keyword):
        """Get tagnames from a keyword."""
        streams = self.conn.Streams.getStreams(
            self.parameters["namespace_id"], query=tagname_keyword + "*", count=10000
        )

        streams_records = [s.toDictionary() for s in streams]

        tagnames = []
        tag_desc = []
        for tag in streams_records:
            tagnames.append(tag["Id"])
            tag_desc.append(tag["Description"])

        return tagnames, tag_desc

    def write_data(self):
        """Write data to AVEVA database (not implemented)."""
        return
