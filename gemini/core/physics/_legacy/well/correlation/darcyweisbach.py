"""Compatibility entry point for the migrated hydraulic correlation."""

from gemini.core.physics.hydraulics import darcy_weisbach_dp


class DarcyWeisbach:
    """Legacy static correlation interface."""

    calculate_dp = staticmethod(darcy_weisbach_dp)
