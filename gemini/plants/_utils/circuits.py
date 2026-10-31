"""Where a stream goes through a plant: outlet to inlet, and through a module on its circuit."""

from gemini._utils.strings import join_path
from gemini.plants._utils.plan import split_end


def _is_common_side(port):
    """Return whether ``port`` belongs to the one circuit of a module, or to one of its branches."""
    return port.startswith(("fluid_", "branch"))


def outlets_after(module, inlet):
    """Return the stream outlets of ``module`` on the circuit of ``inlet``.

    An inlet goes on through the outlet of its role (``hot_in``, ``hot_out``); otherwise a module
    of one circuit, a mixer or a splitter included, goes on through ``fluid_out`` or its branches.
    An inlet with neither, such as ``supply_in`` of a grid, ends the circuit.
    """
    outlets = [name for name, port in module.outlets().items() if port.carries_stream]
    same = f"{inlet.removesuffix('_in')}_out"
    if same in outlets:
        return [same]
    return [name for name in outlets if _is_common_side(name)] if _is_common_side(inlet) else []


def feeds(plant, outlet):
    """Return the paths of the modules the outlet ``"path.port"`` reaches, nearest first."""
    found, waiting = [], [outlet]
    while waiting:
        target = plant.target_of(waiting.pop(0))
        if target is None or target in found:
            continue
        path, port = split_end(target)
        found.append(target)
        following = outlets_after(plant.get_submodule(path), port)
        waiting += [join_path(path, name) for name in following]
    return list(dict.fromkeys(split_end(target)[0] for target in found))
