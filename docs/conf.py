"""Build the installed GEMINI package API reference."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
project = "GEMINI"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]
autosummary_generate = True
html_theme = "sphinx_rtd_theme"
exclude_patterns = ["_build"]
