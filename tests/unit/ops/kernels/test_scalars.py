"""The scope mode that the ops read."""

from gemini.ops import kernels


def test_the_scope_mode_is_none_outside_a_scope():
    """Outside an eager scope there is no mode."""
    assert kernels.scope_mode() is None
    assert {kernels.WRAP, kernels.PLAIN} == {"wrap", "plain"}
