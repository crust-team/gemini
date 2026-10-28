"""The single user entrypoint for GEMINI projects and portable plant JSON."""

from pathlib import Path
from gemini.core.config.build import build_plant, load_config
from gemini.core.config.gemini_loader import load_gemini


def load_plant(path):
    """Load a project folder or saved plant JSON with its complete sensor bindings."""
    path = Path(path)
    return build_plant(load_gemini(path) if path.is_dir() else load_config(path))
