"""Observe actual stream identities through a handwritten module tree."""

from gemini.types import Stream


def trace_wiring(plant, inputs):
    """Execute one step, recording leaf-to-leaf Stream transfers through removable hooks.

    Returns ``(producer path, port, consumer path, port)`` edges. Strong references to every
    produced stream are kept while tracing so Python cannot reuse object identities. Composite
    passthrough ports do not overwrite leaf producers. Leaf passthroughs DO become producers,
    making restrictions visible even when they reuse a stream. Forward hooks only run while
    outputs are enabled, so do not trace inside ``no_outputs()``.
    """
    producers, retained, edges, handles = {}, [], set(), []
    try:
        for path, module in plant.named_modules():
            if not module.is_leaf:
                continue
            handles.append(module.register_forward_pre_hook(_consumer(path, producers, edges)))
            handles.append(module.register_forward_hook(_producer(path, producers, retained)))
        plant(inputs)
    finally:
        for handle in handles:
            handle.remove()
    return edges


def _consumer(path, producers, edges):
    """Return a pre-hook recording an edge for every inlet some leaf produced."""

    def before(module, inlets):
        for port, stream in inlets.items():
            if isinstance(stream, Stream) and id(stream) in producers:
                edges.add((*producers[id(stream)], path, port))

    return before


def _producer(path, producers, retained):
    """Return a forward hook remembering which leaf port produced each outlet stream."""

    def after(module, inlets, outlets):
        for port, stream in outlets.items():
            if isinstance(stream, Stream):
                retained.append(stream)
                producers[id(stream)] = (path, port)

    return after
