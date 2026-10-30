"""Convert stored format 1 plant files to the format 2 spec, in place.

Usage::

    python scripts/migrate_plants.py examples/shared/doublet_heat/plant.json

A file that is already format 2 is left unchanged.
"""

import sys
from pathlib import Path

import gemini as gm
from gemini.utils.files import read_json, write_json


def migrate_file(path):
    """Rewrite one plant file as format 2 and return whether it changed."""
    old = read_json(path)
    spec = gm.plants.migrate(old)
    if spec == old:
        return False
    write_json(path, spec)
    return True


def main(argv=None):
    """Migrate every file named on the command line and print one line per file."""
    paths = sys.argv[1:] if argv is None else argv
    for path in map(Path, paths):
        print(f"{path}: {'migrated' if migrate_file(path) else 'already format 2'}")


if __name__ == "__main__":
    main()
