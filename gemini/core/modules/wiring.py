"""Observe actual stream identities through a handwritten module tree."""

import inspect

from gemini.core.types import Stream


def trace_wiring(plant, inputs):
    """Execute one step, recording leaf-to-leaf Stream transfers through removable hooks.

    Keep strong references while tracing so Python cannot reuse object identities.
    Composite passthrough ports do not overwrite leaf producers. Leaf passthroughs
    DO become producers, making restrictions visible even when they reuse a stream.
    """
    producers, retained, edges, handles = {}, [], set(), []
    try:
        for path, module in plant.named_modules():
            if module._children:
                continue

            def before(module, path=path):
                for port, stream in module._current_inlets().items():
                    if isinstance(stream, Stream) and id(stream) in producers:
                        source, source_port = producers[id(stream)]
                        edges.add((source, source_port, path, port))

            def make_after(path, outlet_names):
                def after(module, **outlets):
                    for port, stream in outlets.items():
                        if isinstance(stream, Stream):
                            retained.append(stream)
                            producers[id(stream)] = (path, port)

                after.__signature__ = inspect.Signature(
                    [inspect.Parameter("module", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
                    + [
                        inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                        for name in outlet_names
                    ]
                )
                return after

            after = make_after(path, module.outlets())

            handles.extend(
                (module.register_forward_pre_hook(before), module.register_forward_hook(after))
            )
        plant(**inputs)
    finally:
        for handle in handles:
            handle.remove()
    return edges
