"""All checks of a finished run together."""

from gemini.checks.balances import energy_balance, mass_balance
from gemini.checks.bounds import bounds
from gemini.utils.jsonable import to_plain


def run_all(plant, results):
    """Run the energy ledger, the mass ledger and the bounds check on a finished run.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``.
    results : Results
        A finished run.

    Returns
    -------
    dict
        Plain JSON ``{passed, checks}``: ``checks`` lists the results of ``energy_balance``,
        ``mass_balance`` and ``bounds`` (each ``{name, passed, value, tolerance}``), and
        ``passed`` is ``False`` if any check failed, ``True`` if none failed and at least one
        passed, and ``None`` if none could judge.
    """
    checks = [energy_balance(results), mass_balance(results), bounds(plant, results)]
    return to_plain({"passed": _verdict([item["passed"] for item in checks]), "checks": checks})


def _verdict(verdicts):
    """Return ``False`` if any verdict failed, else ``True`` if any passed, else ``None``."""
    if False in verdicts:
        return False
    return True if True in verdicts else None
