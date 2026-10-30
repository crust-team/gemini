"""The scope mode that the ops read."""

from gemini import backends


def test_the_scope_mode_is_none_outside_a_scope():
    """Outside an eager scope there is no mode."""
    assert backends.scope_mode() is None
    assert {backends.WRAP, backends.PLAIN} == {"wrap", "plain"}
