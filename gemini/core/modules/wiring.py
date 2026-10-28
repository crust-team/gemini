"""Observe actual stream identities through a handwritten module tree."""

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

            def before(module, controls, streams, path=path):
                for port, stream in streams.items():
                    if isinstance(stream, Stream) and id(stream) in producers:
                        source, source_port = producers[id(stream)]
                        edges.add((source, source_port, path, port))

            def after(module, controls, streams, result, path=path):
                for port, stream in result.outlets.items():
                    if isinstance(stream, Stream):
                        retained.append(stream)
                        producers[id(stream)] = (path, port)

            handles.extend(
                (module.register_forward_pre_hook(before), module.register_forward_hook(after))
            )
        plant(**inputs)
    finally:
        for handle in handles:
            handle.remove()
    return edges
