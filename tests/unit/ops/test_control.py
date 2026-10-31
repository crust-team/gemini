"""``scan`` is defined as an op kind but has no implementation yet."""

from gemini.ops import kernels, registry


def test_scan_is_registered_without_a_backend_implementation():
    """The op exists for graph passes; no backend evaluates it."""
    assert registry.get("scan").kind == "scan"
    assert not hasattr(kernels.get("numpy"), "scan")
