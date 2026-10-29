"""Context-local settings usable as ``with`` blocks and as function decorators."""

from functools import wraps


class ContextSetting:
    """Set a context variable for a ``with`` block or a decorated call, then restore it.

    ``update(current)`` computes the new value from the current one each time the setting is
    entered, so a decorator applies the change to the settings of every call rather than freezing
    them when the function was decorated. Entries nest: leaving a block restores exactly the value
    that was current when it was entered. Values live in a ``contextvars.ContextVar``, so threads
    and asyncio tasks each see their own settings.
    """

    def __init__(self, variable, update):
        """Remember the context variable and the function computing its value on entry."""
        self._variable = variable
        self._update = update
        self._tokens = []

    def __enter__(self):
        """Apply the setting until the matching ``__exit__``."""
        value = self._update(self._variable.get())
        self._tokens.append(self._variable.set(value))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Restore the value that was current on entry; exceptions propagate."""
        self._variable.reset(self._tokens.pop())

    def __call__(self, function):
        """Decorate a function so each call runs inside a fresh copy of this setting."""

        @wraps(function)
        def wrapper(*args, **kwargs):
            with ContextSetting(self._variable, self._update):
                return function(*args, **kwargs)

        return wrapper
