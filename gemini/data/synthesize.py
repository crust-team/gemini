"""A demand profile synthesised from a few figures: a placeholder until it is built."""

from gemini.errors import NotImplementedYet


def synthesize(heating, cooling, start, step, length=None, season=None, seed=None):
    """Return a demand profile made from yearly figures, in the run-input format of ``from_csv``.

    Parameters
    ----------
    heating, cooling : str or float
        The peak power of each demand, such as ``"30 MW"``; ``None`` leaves that quantity out.
    start : str or datetime
        The first timestamp; naive is UTC.
    step : str or float
        The duration between values, such as ``"1 h"`` or ``"1 d"``, or seconds.
    length : int, optional
        The number of rows; one year by default.
    season : dict, optional
        The shape of the year, such as the day of the heating peak and of the cooling peak.
    seed : int, optional
        Seed of the noise, for the same profile every time.

    Returns
    -------
    DataFrame
        As ``gm.data.from_csv``.

    Raises
    ------
    NotImplementedYet
        Always: the synthesis is not built yet.
    """
    raise NotImplementedYet("data.synthesize")
