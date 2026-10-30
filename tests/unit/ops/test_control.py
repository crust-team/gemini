"""``scan`` is defined as an op kind but has no implementation yet."""

from gemini import backends
from gemini.ops import registry


def test_scan_is_registered_without_a_backend_implementation():
    """The op exists for graph passes; no backend evaluates it."""
    assert registry.get("scan").kind == "scan"
    assert not hasattr(backends.get("numpy"), "scan")
