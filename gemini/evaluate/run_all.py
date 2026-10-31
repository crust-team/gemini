"""All checks of a finished run together."""

from gemini._utils.jsonable import to_plain
from gemini.evaluate.bounds import bounds
from gemini.evaluate.constraints import constraints
from gemini.evaluate.energy_balance import energy_balance
from gemini.evaluate.mass_balance import mass_balance


def run_all(plant, problem, results):
    """Run the energy ledger, the mass ledger, the bounds and the constraints on a finished run.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``.
    problem : Problem
        The problem of the run; its constraints are checked.
    results : Results
        A finished run.

    Returns
    -------
    dict
        Plain JSON ``{passed, checks}``: ``checks`` lists the results of ``energy_balance``,
        ``mass_balance`` and ``bounds``, then those of ``constraints`` (each
        ``{name, passed, value, limit}``), and ``passed`` is ``False`` if any check failed,
        ``True`` if none failed and at least one passed, and ``None`` if none could judge.
    """
    checks = [
        energy_balance(plant, problem, results),
        mass_balance(plant, problem, results),
        bounds(plant, problem, results),
        *constraints(plant, problem, results),
    ]
    return to_plain({"passed": _verdict([item["passed"] for item in checks]), "checks": checks})


def _verdict(verdicts):
    """Return ``False`` if any verdict failed, else ``True`` if any passed, else ``None``."""
    if False in verdicts:
        return False
    return True if True in verdicts else None
