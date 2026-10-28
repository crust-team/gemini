"""Module discovery tests."""

from gemini.core.modules.catalogue import get


def test_known_module_is_discoverable():
    """Equipment discovery retains the stable ESP name."""
    assert get("esp").name == "esp"
