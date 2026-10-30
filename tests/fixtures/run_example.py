"""Run an example script under the backend named by ``GEMINI_EXAMPLE_BACKEND``.

``python tests/fixtures/run_example.py <script>`` enters ``gemini.backends.settings`` with that
backend for the whole script and runs it as ``__main__`` with ``runpy``, so an example needs no
setting of its own. An ``Engine`` applies its own ``backend`` to each run, so the script also
makes that backend the default of ``Engine(plant, backend=...)``. The backend parity test of the
examples is its only user.
"""

import os
import runpy
import sys

from gemini import Engine, backends


def main():
    """Run ``sys.argv[1]`` as a script under the backend of the environment variable."""
    script = sys.argv[1]
    sys.argv[:] = [script]
    backend = os.environ["GEMINI_EXAMPLE_BACKEND"]
    _, *other_defaults = Engine.__init__.__defaults__
    Engine.__init__.__defaults__ = (backend, *other_defaults)
    with backends.settings(backend=backend):
        runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
