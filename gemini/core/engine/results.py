"""Per-module time-series results with structured columns and export helpers."""

import pandas as pd


class Results:
    """Collect outputs and explicit health availability at each timestep."""

    def __init__(self):
        """Start an independent result table and skip counter."""
        self._rows = []
        self._times = []
        self.skip_counts = {}

    def append(self, at, results):
        """Append a mapping of module paths to (ModuleResult, Health) pairs."""
        row = {}
        for path, (result, health) in results.items():
            row.update({(path, key): value for key, value in result.outputs.model_dump().items()})
            if health is not None:
                values = health.model_dump()
                metrics = values.pop("metrics")
                row.update({(path, "health_" + key): value for key, value in values.items()})
                row.update(
                    {(path, "health_metric_" + key): value for key, value in metrics.items()}
                )
        self._times.append(at)
        self._rows.append(row)

    def __len__(self):
        """Return the number of timesteps, including entirely skipped rows."""
        return len(self._times)

    def to_frame(self):
        """Return a DataFrame with (module_path, field) MultiIndex columns."""
        frame = pd.DataFrame(self._rows, index=pd.Index(self._times, name="timestamp"))
        frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["module_path", "field"])
        return frame

    def save_csv(self, path):
        """Write a CSV with two column-header rows."""
        self.to_frame().to_csv(path)

    def save_parquet(self, path):
        """Write Parquet using the pandas-installed engine."""
        self.to_frame().to_parquet(path)
