"""Removable hook registrations and fixed hook signatures."""

from gemini.utils.hooks import RemovableHandle, has_signature


def test_handles_keep_order_and_remove_once():
    """Hooks run in registration order and a second ``remove`` is harmless."""
    hooks = {}
    first = RemovableHandle(hooks, "first")
    RemovableHandle(hooks, "second")
    RemovableHandle(hooks, "first")
    assert list(hooks.values()) == ["first", "second", "first"]
    first.remove()
    first.remove()
    assert list(hooks.values()) == ["second", "first"]


def test_has_signature_requires_exact_positional_names():
    """Only the exact required positional parameter names match."""

    def exact(module, inlets):
        return None

    def defaulted(module, inlets=None):
        return None

    def keyword(module, *, inlets):
        return None

    assert has_signature(exact, ("module", "inlets"))
    assert not has_signature(exact, ("module", "inlets", "outlets"))
    assert not has_signature(defaulted, ("module", "inlets"))
    assert not has_signature(keyword, ("module", "inlets"))
    assert not has_signature(lambda *args: None, ("module", "inlets"))
