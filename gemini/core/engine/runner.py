"""Explicit plant runner without import-time environment configuration."""

from gemini.core.engine.mainmodule import MainModule
from gemini.core.plant.loader import setup


class App:
    """Runner that boots a plant and executes one step."""

    def __init__(self, project_path, plant_name):
        """Initialize application with project path and plant name."""
        self.project_path = project_path
        self.plant_name = plant_name

    def boot(self):
        """Initialize plant and main module from configuration."""
        self.plant = setup(self.project_path, self.plant_name)

        self.mainmodule = MainModule(self.plant)

    def step(self):
        """Execute one processing step across all modules."""
        self.mainmodule.step()

    def quit(self):
        """Disconnect from databases and cleanup."""
        # disconnect database
        self.plant.database.disconnect()
