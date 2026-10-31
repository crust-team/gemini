"""All checks of a finished run together."""

from gemini._utils.jsonable import to_plain
from gemini.evaluate.balances import energy_balance, mass_balance
from gemini.evaluate.bounds import bounds
from gemini.evaluate.operating import operating_time


def run_all(plant, results, duration=None):
    """Run the energy ledger, the mass ledger and the bounds check on a finished run.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``.
    results : Results
        A finished run.
    duration : str or float, optional
        The time each doublet has to run, as for ``operating_time``; given, it joins the checks.

    Returns
    -------
    dict
        Plain JSON ``{passed, checks}``: ``checks`` lists the results of ``energy_balance``,
        ``mass_balance`` and ``bounds``, then those of ``operating_time`` when ``duration`` is given
        (each ``{name, passed, value, limit}``), and
        ``passed`` is ``False`` if any check failed, ``True`` if none failed and at least one
        passed, and ``None`` if none could judge.
    """
    checks = [energy_balance(results), mass_balance(results), bounds(plant, results)]
    if duration is not None:
        checks += operating_time(plant, results, duration)
    return to_plain({"passed": _verdict([item["passed"] for item in checks]), "checks": checks})


def _verdict(verdicts):
    """Return ``False`` if any verdict failed, else ``True`` if any passed, else ``None``."""
    if False in verdicts:
        return False
    return True if True in verdicts else None
