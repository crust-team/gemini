"""Compatibility entry point for the migrated hydraulic correlation."""

from gemini.core.physics.hydraulics import beggs_brill_dp


class BeggsBrill:
    """Legacy static correlation interface."""

    calculate_dp = staticmethod(beggs_brill_dp)
