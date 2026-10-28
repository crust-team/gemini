"""Main execution module organizing pre/model/post processors per loop."""

from gemini.core.engine.loop import Loop


class MainModule:
    """Coordinates reading data and executing all unit modules per category."""

    def __init__(self, plant):
        """Initialize main module with plant."""
        self.plant = plant
        self.modules = {}
        self.loop = {}

        self.modules["preprocessor"] = plant.find_modules("preprocessor")
        self.modules["model"] = plant.find_modules("model")
        self.modules["postprocessor"] = plant.find_modules("postprocessor")

        self.loop["filtered"] = self._build_loop("filtered")
        self.loop["calculated"] = self._build_loop("calculated")

    def step(self):
        """Execute one simulation step."""
        # self.plant.database.delete(self.plant.name)
        self.plant.database.import_raw_data()

        self._run_modules("preprocessor", self.loop["filtered"])
        self._run_modules("model", self.loop["calculated"])
        self._run_modules("postprocessor", self.loop["calculated"])

    def _build_loop(self, category):
        """Create and initialize a loop instance for the requested category."""
        loop = Loop()
        end_time = self.plant.database.get_current_time_str()
        timestep = self.plant.parameters["database"][category]["interval"]
        # start time will be set inside the module based on the latest available calculated value
        loop.initialize(end_time=end_time, timestep=timestep)
        return loop

    def _run_modules(self, module_category, loop):
        """Run all modules in a category with consistent logging."""
        for module in self.modules[module_category]:
            module.logger.info(
                f"Timestamps: {loop.end_time}. Running {module_category} "
                f"module: {module.__class__.__name__}"
            )
            module.step(loop)
