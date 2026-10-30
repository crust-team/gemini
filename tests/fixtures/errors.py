"""Check an error by its class and its code."""

from contextlib import contextmanager

import pytest


@contextmanager
def raises(error, code, match=None):
    """Expect ``error`` with ``code``; the block gets the ``ExceptionInfo`` of ``pytest.raises``."""
    with pytest.raises(error, match=match) as caught:
        yield caught
    assert caught.value.code == code
