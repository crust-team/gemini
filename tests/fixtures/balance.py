"""The plant balance of a run or a call, for every test of a shipped plant."""

import gemini as gm


def assert_plant_closes(plant, run):
    """Assert that mass and energy close for every module and the root; return the checks.

    A building block has no demand, so the balance is read without a problem.
    """
    checks = gm.evaluate.plant_balance(plant, None, run)
    assert [check for check in checks if check["passed"] is not True] == []
    return checks
