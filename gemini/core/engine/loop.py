"""Loop helper to manage time windows and step counts for module execution."""

import datetime
import math


class Loop:
    """Encapsulates start time, end time, timestep, and computed step count."""

    def __init__(self):
        """Initialize simulation loop."""
        self.start_time = None
        self.end_time = None
        self.timestep = None
        self.n_step = None

    def initialize(self, start_time=None, end_time=None, timestep=None):
        """Initialize loop with start time, end time, and timestep."""
        self.start_time = start_time
        self.end_time = end_time
        self.timestep = timestep

    def compute_n_simulation(self):
        """Compute number of simulation steps."""
        starttime_datetime = datetime.datetime.fromisoformat(self.start_time)
        endtime_datetime = datetime.datetime.fromisoformat(self.end_time)

        self.n_step = math.floor(
            (endtime_datetime - starttime_datetime).total_seconds() / self.timestep
        )
