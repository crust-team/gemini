"""The plant balance of a run or a call, for every test of a shipped plant."""

import gemini as gm


def assert_plant_closes(plant, run):
    """Assert that mass and energy close for every module and the root; return the checks."""
    checks = gm.checks.plant_balance(plant, run)
    assert [check for check in checks if check["passed"] is not True] == []
    return checks
