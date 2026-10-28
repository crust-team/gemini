"""Abstract database driver interface used by the framework."""

from abc import ABC, abstractmethod


class DatabaseDriverAbstract(ABC):
    """Abstract base class for database drivers (connect/read/write)."""

    def __init__(self):
        """Initialize database driver."""
        self.conn = None
        self.parameters = dict()

    def update_parameters(self, parameters):
        """Update driver parameters."""
        for key, value in parameters.items():
            self.parameters[key] = value

    def disconnect(self):
        """Disconnect from database."""
        self.conn = None

    @abstractmethod
    def connect(self):
        """Connect to database."""
        return

    @abstractmethod
    def read_data(self):
        """Read data from database."""
        return

    @abstractmethod
    def write_data(self):
        """Write data to database."""
        return
