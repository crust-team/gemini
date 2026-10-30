"""The eager physics scope: ``@ops.physics`` and the scope a module call enters.

A direct call of a module or a physics function is eager: the same ``forward`` and the same ops
as the graph, evaluated on the Python backend. One mechanism makes plain operators safe there:

- **Entering the outermost scope** enters ``np.errstate(all="ignore")`` and gives a function called
  on plain Python floats its arguments as ``np.float64`` (exact ``float`` only: ints, ``None``,
  strings, arrays and traced values pass through). ``np.float64`` has the arithmetic of ``float``
  but ``/`` by zero, an invalid ``**`` and an overflow give ``inf`` or ``nan`` silently, like the
  NumPy and graph backends. Arrays or traced values among the arguments leave the scope unwrapped
  (an ``np.float64`` scalar would promote a float32 array), and so does a module whose
  ``Module._scalar_mode`` is ``PLAIN`` (the ESP under float32 precision, the one quirk).
- **Nested scopes** only wrap the exact floats among their own arguments (a literal ``0.0``) and
  catch a failing check; the cost is a ``ContextVar`` read and a scan of the arguments.
- **Leaving the outermost scope** returns plain Python scalars on every backend: ``float`` for
  ``np.float64``, ``bool`` for ``np.bool_``, recursively through tuples, lists, dicts and frozen
  dataclasses, and raises the error of a ``Failed`` found anywhere in the result.
- **A failing check** (``ops.check`` on concrete scalars) raises a marked error; ``physics``
  returns ``Failed(error)`` for it at each function boundary (see ``gemini.ops.failed``).
  Outside any scope the caller sees the real error. A failing check on an eager array raises at
  once, for its first failing row, and is never turned into a ``Failed``.
- **In a trace** (``tracing(graph)``) a physics function keeps the checks recorded directly in it
  and guards every traced value it returns with them, so the graph attaches an error to the
  results of the function exactly as the eager ``Failed`` does. A check recorded outside any
  physics function is certain: it guards every graph output, as it raises at once when eager.

Do not put ``repr`` of a physical value in a message (``np.float64(1.0)``), and note that
``round(np.float64, n)`` is NumPy's rounding: use ``ops.round``.
"""

import dataclasses
from contextvars import ContextVar
from functools import wraps

import numpy as np

from gemini.backends import PLAIN, WRAP
from gemini.backends.scalars import scope_mode, scope_variable
from gemini.errors import TraceError
from gemini.ops.dispatch import Symbolic
from gemini.ops.failed import Failed, is_marked
from gemini.utils.context import ContextSetting

_PASS = frozenset({np.float64, int, bool, str, type(None), np.bool_})
_ATOMIC = frozenset({float, int, bool, str, type(None), np.ndarray})
_CONVERT = {np.float64: float, np.bool_: bool}


_traced = ContextVar("gemini_traced_graph", default=None)


def tracing(graph):
    """Select ``graph`` as the one that physics functions record their checks in."""
    return ContextSetting(_traced, lambda current: graph)


def _scalar(value):
    return np.float64(value) if type(value) is float else value


def _wrapped_keywords(kwargs):
    """Return ``kwargs`` with exact floats as ``np.float64``, itself when it holds none."""
    for value in kwargs.values():
        if type(value) is float:
            return {name: _scalar(item) for name, item in kwargs.items()}
    return kwargs


def wrap(value):
    """Return ``value`` for the scope: an exact ``float`` as ``np.float64``; lists, tuples too."""
    kind = type(value)
    if kind is float:
        return np.float64(value)
    if kind is list or kind is tuple:
        return kind(wrap(item) for item in value)
    return value


def plain(value):
    """Return ``value`` as plain Python scalars; raise the error of any ``Failed`` inside it."""
    kind = type(value)
    if kind in _ATOMIC:
        return value
    converter = _CONVERT.get(kind)
    if converter is not None:
        return converter(value)
    if isinstance(value, Failed):
        raise value.error
    if kind is list or kind is tuple:
        return kind(plain(item) for item in value)
    if kind is dict:
        return {key: plain(item) for key, item in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain_dataclass(value)
    return value


def _plain_dataclass(value):
    """Return the dataclass ``value`` with plain fields, itself when nothing changes."""
    changes = {}
    for field in dataclasses.fields(value):
        item = getattr(value, field.name)
        converted = plain(item)
        if converted is not item:
            changes[field.name] = converted
    return dataclasses.replace(value, **changes) if changes else value


def _wrapped(values):
    """Return ``values`` with exact floats as ``np.float64``; ``None`` if any is array or traced.

    ``values`` is a sequence; ``None`` also stands for "leave the call unwrapped".
    """
    converted = []
    for value in values:
        kind = type(value)
        if kind is float:
            converted.append(np.float64(value))
            continue
        if kind not in _PASS and (kind is np.ndarray or isinstance(value, Symbolic)):
            return None
        converted.append(value)
    return converted


def _wrapped_call(args, kwargs):
    """Return ``(args, kwargs, wrapped)`` with exact floats wrapped; unchanged for arrays."""
    positional = _wrapped(args)
    named = _wrapped(kwargs.values())
    if positional is None or named is None:
        return args, kwargs, False
    return tuple(positional), dict(zip(kwargs, named)), True


class Scope:
    """Context manager entering the eager scope for a call that asks for ``mode``.

    ``arrays`` says that the call holds arrays or traced values, which leaves it unwrapped. The
    first entry also opens ``np.errstate``. Every entry sets the mode of the scope for its own
    duration and restores the previous one on exit, so a module that wants ``PLAIN`` inside a
    wrapping composite behaves as it did before. After ``__enter__``, ``wrapping`` tells whether
    this call wraps scalars and ``outermost`` whether it opened the scope.
    """

    __slots__ = ("mode", "arrays", "wrapping", "outermost", "_token", "_errstate")

    def __init__(self, mode=WRAP, arrays=False):
        """Prepare a scope asking for ``mode``; arrays or traced values force ``PLAIN``."""
        self.mode = PLAIN if arrays else mode
        self.wrapping = self.mode is WRAP
        self.outermost = False

    def __enter__(self):
        """Enter the scope, opening ``np.errstate`` if none is running."""
        self.outermost = scope_mode() is None
        if self.outermost:
            self._errstate = np.errstate(all="ignore")
            self._errstate.__enter__()
        self._token = scope_variable.set(self.mode)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Restore the mode that was running, and leave ``np.errstate`` if this entry opened it."""
        scope_variable.reset(self._token)
        if self.outermost:
            self._errstate.__exit__(exc_type, exc_value, traceback)


def physics(function):
    """Decorate a public function of ``core/physics`` so it is safe with plain operators.

    The outermost call opens the scope (silent NumPy arithmetic, ``np.float64`` arguments, plain
    scalars and ``Failed`` handling on return); a nested call wraps its own exact floats and
    returns ``Failed`` where a ``check`` failed.
    """

    @wraps(function)
    def wrapper(*args, **kwargs):
        mode = scope_mode()
        if mode is None:
            return _outermost(function, args, kwargs)
        if mode is WRAP:
            for value in args:
                if type(value) is float:
                    args = tuple([_scalar(item) for item in args])
                    break
            if kwargs:
                kwargs = _wrapped_keywords(kwargs)
        try:
            return function(*args, **kwargs) if mode is WRAP else _framed(function, args, kwargs)
        except Exception as error:
            if not is_marked(error):
                raise
            return Failed(error)

    return wrapper


def _outermost(function, args, kwargs):
    """Run ``function`` in a new scope and return its result as plain scalars."""
    wrapped_args, wrapped_kwargs, wrapping = _wrapped_call(args, kwargs)
    with Scope(arrays=not wrapping) as scope:
        if scope.wrapping:
            args, kwargs = wrapped_args, wrapped_kwargs
        return plain(_framed(function, args, kwargs))


def _framed(function, args, kwargs):
    """Call ``function``; in a trace, guard its traced results with the checks it recorded."""
    graph = _traced.get()
    if graph is None:
        return function(*args, **kwargs)
    start = graph.open_frame()
    try:
        result = function(*args, **kwargs)
    except Exception as error:
        graph.abandon_frame()
        if is_marked(error):
            raise TraceError(
                f"{function.__name__}: a check failed on constant values: {error}"
            ) from error
        raise
    return graph.close_frame(result, start)
