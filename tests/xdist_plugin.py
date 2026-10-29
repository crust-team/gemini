"""Early pytest options, registered before xdist starts its workers."""


def pytest_addoption(parser):
    """Add the committed dataset and the test-profile selections."""
    parser.addoption(
        "--dataset",
        choices=("fast", "slow"),
        default="fast",
        help="committed e2e dataset: fast July month (default) or slow full year",
    )
    parser.addoption(
        "--profile",
        choices=("development", "release"),
        default="development",
        help="development (default, 300 s budget) or release (full suite, no budget)",
    )
