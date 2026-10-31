"""Context-local settings used as blocks and as decorators."""

import threading
from contextvars import ContextVar

import pytest

from gemini._utils.context import ContextSetting

LEVEL = ContextVar("level", default=0)


def deeper():
    """Return a setting that raises the level by one on entry."""
    return ContextSetting(LEVEL, lambda current: current + 1)


def test_blocks_nest_and_restore_after_errors():
    """Leaving a block restores the value current on entry, even after an exception."""
    with deeper():
        with deeper():
            assert LEVEL.get() == 2
        assert LEVEL.get() == 1
        with pytest.raises(RuntimeError):
            with deeper():
                raise RuntimeError("boom")
        assert LEVEL.get() == 1
    assert LEVEL.get() == 0


def test_one_instance_can_be_entered_recursively():
    """The same object can be re-entered while it is active."""
    setting = deeper()
    with setting:
        with setting:
            assert LEVEL.get() == 2
    assert LEVEL.get() == 0


def test_decorator_computes_the_value_on_each_call():
    """A decorated function sees the change applied to the settings current at its call."""

    @deeper()
    def level():
        return LEVEL.get()

    assert level() == 1
    with deeper():
        assert level() == 2
    assert LEVEL.get() == 0
    assert level.__name__ == "level"


def test_threads_do_not_share_settings():
    """A setting entered in one thread is invisible in another."""
    seen = []
    with deeper():
        thread = threading.Thread(target=lambda: seen.append(LEVEL.get()))
        thread.start()
        thread.join()
    assert seen == [0]
