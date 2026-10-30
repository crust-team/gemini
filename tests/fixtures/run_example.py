"""Run an example script under the backend named by ``GEMINI_EXAMPLE_BACKEND``.

``python tests/fixtures/run_example.py <script>`` enters ``gemini.backends.settings`` with that
backend for the whole script and runs it as ``__main__`` with ``runpy``, so an example needs no
setting of its own. An ``Engine`` applies its own ``backend`` to each run, so the script also
makes that backend the default of ``Engine(plant, backend=...)`` and of the run functions, which
pass theirs to the engine. The backend parity test of the examples is its only user.
"""

import os
import runpy
import sys

import gemini as gm
from gemini import backends


def _set_default_backend(function, backend):
    """Make ``backend`` the default of the ``backend`` argument of ``function``."""
    code = function.__code__
    optional = code.co_varnames[code.co_argcount - len(function.__defaults__) : code.co_argcount]
    defaults = list(function.__defaults__)
    defaults[optional.index("backend")] = backend
    function.__defaults__ = tuple(defaults)


def main():
    """Run ``sys.argv[1]`` as a script under the backend of the environment variable."""
    script = sys.argv[1]
    sys.argv[:] = [script]
    backend = os.environ["GEMINI_EXAMPLE_BACKEND"]
    for function in (gm.Engine.__init__, gm.simulate, gm.replay, gm.live):
        _set_default_backend(function, backend)
    with backends.settings(backend=backend):
        runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
