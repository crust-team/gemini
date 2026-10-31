"""Text and data views of a plant's wiring."""

from gemini.modules.plants._utils.plan import members, split_end


def connection_list(plant):
    """Return the plant's connections as ``[{source, target, kind, type}]``.

    ``kind`` is the label of the labelled end, ``None`` when both ends take anything.
    """
    result = []
    for item in plant._connections:
        (spath, sport), (tpath, tport) = split_end(item["source"]), split_end(item["target"])
        first = plant.get_module(spath).outlets()[sport]
        second = plant.get_module(tpath).inlets()[tport]
        result.append(
            {
                "source": item["source"],
                "target": item["target"],
                "kind": first.kind or second.kind,
                "type": item.get("type"),
            }
        )
    return result


def summary(plant):
    """Return a text table of the modules: type, category, inbound connections, parameters."""
    sources = {}
    for item in plant._connections:
        path, port = split_end(item["target"])
        sources.setdefault(path, []).append(f"{port} <- {item['source']}")
    rows = [("Module", "Type", "Category", "Connected to", "Parameters")]
    for path, module in members(plant):
        count = len(list(module.parameters()))
        rows.append(
            (
                path,
                module._type_label,
                module.category or "",
                ", ".join(sources.get(path, [])),
                str(count),
            )
        )
    widths = [max(len(row[column]) for row in rows) for column in range(5)]
    lines = [f"Plant: {plant.name}"] + [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows
    ]
    total = sum(len(list(module.parameters())) for _, module in members(plant))
    return "\n".join(lines + [f"Total parameters: {total}"])
