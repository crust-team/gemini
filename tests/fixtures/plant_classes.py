"""A class per shipped spec plant, so tests written for module classes run on every plant."""

from gemini.modules.plants import Plant, library


def spec_plant_class(name):
    """Return a ``Plant`` subclass that builds the shipped spec ``name`` when constructed."""

    def initialize(self):
        """Add the modules, wiring and outputs of the shipped spec."""
        Plant.__init__(self, name)
        library.fill(self, name)

    return type(name, (Plant,), {"__init__": initialize, "__doc__": f"The shipped plant {name}."})


def spec_plant_classes():
    """Return the classes of every plant that ships as a spec file, sorted by name."""
    return tuple(spec_plant_class(path.stem) for path in sorted(library.SPECS.glob("*.json")))
