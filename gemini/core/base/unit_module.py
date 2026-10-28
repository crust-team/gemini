"""Abstract module interface for unit components.

Defines the contract for unit modules that link inputs/outputs to the
framework database and update model parameters over time windows.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


class UnitModuleAbstract(ABC):
    """Abstract base class for unit modules."""

    def __init__(self, unit):
        """Initialize unit module."""
        self.logger = logger
        self.unit = unit
        self.loop = None
        self.tags = {
            "input": {"measured": {}, "filtered": {}, "calculated": {}},
            "output": {"measured": {}, "filtered": {}, "calculated": {}},
        }

    def link(self):
        """Link module inputs and outputs."""
        self.logger.error("Module %s did not implement a link method", self.__class__.__name__)

    def init(self, loop):
        """Initialize module with loop."""
        self.loop = loop

    def link_input(self, unit, category, tagname):
        """Link input tag to module."""
        reference = unit.tags[category][tagname]

        self.tags["input"][category][tagname] = {
            "external_name": reference,
            "internal_name": tagname + "." + category,
            "unit_name": unit.name,
        }

    def link_output(self, unit, category, tagname):
        """Link output tag to module."""
        reference = unit.tags[category][tagname]

        self.tags["output"][category][tagname] = {
            "external_name": reference,
            "internal_name": tagname + "." + category,
            "unit_name": unit.name,
        }

    def get_output_last_data_time(self, tagname):
        """Get last data time for output tag."""
        _, tag_meta = self._find_tag_meta("output", tagname)

        time_str = self.unit.plant.database.get_internal_database_last_time_str(
            self.unit.plant.name,
            tag_meta["unit_name"],
            tag_meta["internal_name"],
        )

        return time_str

    def get_input_data(self, tagname):
        """Get input data for tag."""
        _, tag_meta = self._find_tag_meta("input", tagname)

        result, time = self.unit.plant.database.read_internal_database(
            self.unit.plant.name,
            tag_meta["unit_name"],
            tag_meta["internal_name"],
            self.loop.start_time,
            self.loop.end_time,
            self.loop.timestep,
        )

        return time, result

    def write_output_data(self, tagname, time, result):
        """Write output data for tag."""
        _, tag_meta = self._find_tag_meta("output", tagname)

        self.unit.plant.database.write_internal_database(
            self.unit.plant.name,
            tag_meta["unit_name"],
            tag_meta["internal_name"],
            time,
            result,
        )

    def get_parameter_index(self, unit, timestamps):
        """Get parameter index for given timestamp."""
        timestamps_unix = datetime.fromisoformat(timestamps).timestamp()

        timestamps_parameters_unix = [
            datetime.strptime(timestamp_parameter, "%Y-%m-%d %H:%M:%S").timestamp()
            for timestamp_parameter in unit.parameters["timestamps"]
        ]

        index = np.argwhere(np.array(timestamps_parameters_unix) <= timestamps_unix).max()

        return index

    def _find_tag_meta(self, io_type, tagname):
        """Resolve tag metadata from linked input/output tags."""
        for category, tag_map in self.tags[io_type].items():
            if tagname in tag_map:
                return category, tag_map[tagname]

        raise KeyError(f"Tag '{tagname}' is not linked in {io_type} tags.")

    @abstractmethod
    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        pass
