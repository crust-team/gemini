"""CSV connector implementation."""

import pandas as pd

from gemini.core.data.drivers.database_driver_abstract import DatabaseDriverAbstract


class CSVDriver(DatabaseDriverAbstract):
    """Database connector based on CSV."""

    def __init__(self):
        """Establish connection to CSV database."""
        self.parameters = dict()
        self.df = pd.DataFrame()

    def update_parameters(self, parameters):
        """Update driver parameters."""
        for key, value in parameters.items():
            self.parameters[key] = value

    def connect(self):
        """Connect to CSV database."""
        if self.parameters["url"] == "":
            return

        self.df = pd.read_csv(self.parameters["url"], delimiter=";")

        self.df["Timestamp"] = (
            pd.to_datetime(self.df["Timestamp"], utc=True, format="mixed")
            .round("min")
            .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        self.df = self.df.set_index("Timestamp")

    def disconnect(self):
        """Disconnect from the CSV database."""
        return

    def read_data(self, external_tagname, start_time, end_time, interval):
        """Read data from CSV database."""
        results = []
        timestamps = []

        if external_tagname in list(self.df.columns):
            results = self.df[external_tagname].values.tolist()
            timestamps = self.df.index.values.tolist()

        return results, timestamps

    def write_data(self):
        """Write data to CSV database."""
        return
