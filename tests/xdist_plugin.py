"""Early pytest-xdist configuration."""


def pytest_addoption(parser):
    """Add the committed real-data selection before xdist chooses workers."""
    parser.addoption(
        "--dataset",
        choices=("fast", "slow"),
        default="fast",
        help="committed e2e dataset: fast July month (default) or slow full year",
    )
