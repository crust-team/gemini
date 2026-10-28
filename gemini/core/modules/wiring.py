"""Observe actual stream identities and compare explicit plant wiring with GEMINI diagrams."""

import json
from pathlib import Path

from gemini.core.config.gemini_loader import GEMINI_PORTS, TYPES
from gemini.core.modules.plants.geothermal_example import GeothermalExamplePlant
from gemini.core.types import Stream


def trace_wiring(plant, inputs, streams_in=None):
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
                for port, stream in result.streams.items():
                    if isinstance(stream, Stream):
                        retained.append(stream)
                        producers[id(stream)] = (path, port)

            handles.extend(
                (module.register_forward_pre_hook(before), module.register_forward_hook(after))
            )
        plant(inputs, streams_in)
    finally:
        for handle in handles:
            handle.remove()
    return edges


def check_against_diagram(traced, diagram_json, node_map):
    """Return missing/extra links, expanding the example's explicitly declared buried riser.

    Diagram nodes must have `properties.name` and `properties.type`. Node maps use
    .param stems. No diagram edge constructs or changes the evaluated plant.
    """
    if isinstance(diagram_json, (str, Path)):
        diagram_json = json.loads(Path(diagram_json).read_text())
    nodes = {
        cell["id"]: cell["properties"]
        for cell in diagram_json["cells"]
        if cell["type"] == "devs.Model"
    }
    links = [cell for cell in diagram_json["cells"] if cell["type"] == "devs.Link"]
    incoming = {link["target"]["id"] for link in links}
    expected, errors = set(), []
    expansions = (
        GeothermalExamplePlant.DIAGRAM_EXPANSIONS
        if node_map == GeothermalExamplePlant.GEMINI_NODES
        else {}
    )
    for link in links:
        try:
            endpoints = []
            for side in ("source", "target"):
                endpoint = link[side]
                node = nodes[endpoint["id"]]
                kind = TYPES.get(node["type"], node["type"])
                if kind == "reservoir":
                    kind = (
                        "injection_reservoir"
                        if endpoint["id"] in incoming
                        else "production_reservoir"
                    )
                endpoints.append((node_map[node["name"]], GEMINI_PORTS[kind][endpoint["port"]]))
            source, target = endpoints
            if source in expansions:
                path, inlet, outlet = expansions[source]
                expected.add((*source, path, inlet))
                source = (path, outlet)
            expected.add((*source, *target))
        except KeyError as exc:
            errors.append(f"Unmapped diagram endpoint: {exc}")
    errors.extend(f"Missing connection: {edge}" for edge in sorted(expected - traced))
    errors.extend(f"Unexpected connection: {edge}" for edge in sorted(traced - expected))
    return errors
