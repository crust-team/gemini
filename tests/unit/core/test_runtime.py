"""Context-local runtime settings."""

from concurrent.futures import ThreadPoolExecutor

import gemini as gm


def test_settings_restore_and_context_isolation():
    """Temporary settings restore and separate copied thread contexts."""
    assert gm.runtime.get_precision() == "float64"
    with gm.runtime.settings(precision="float32", display_units="field"):
        assert gm.runtime.get_precision() == "float32"
        assert gm.runtime.get_display_units() == "field"
    assert gm.runtime.get_precision() == "float64"
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: gm.runtime.get_precision(), range(2)))
    assert values == ["float64", "float64"]


def test_state_round_trip():
    """Serializable runtime state restores all global settings."""
    before = gm.runtime.state()
    gm.runtime.set_display_units("field")
    gm.runtime.load_state(before)
    assert gm.runtime.state() == before
