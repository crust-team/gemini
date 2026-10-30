"""Removable hook registrations and fixed hook signatures."""

from functools import partial

from gemini.utils.hooks import RemovableHandle, has_signature, is_observer, observer


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


def test_observer_marks_functions_and_partials():
    """A marked function, a marked partial and a partial of a marked function are observers."""

    def read(module, inlets):
        return None

    assert not is_observer(read)
    assert not is_observer(partial(read))
    assert observer(read) is read and is_observer(read)
    assert is_observer(partial(read))
    assert is_observer(observer(partial(lambda module, inlets: None)))
