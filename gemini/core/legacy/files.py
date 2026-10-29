"""Faithful raw I/O for the old GEMINI project and semicolon CSV formats."""

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from gemini.utils.files import read_json, write_json


class GeminiNode(BaseModel):
    """One old diagram model node."""

    model_config = ConfigDict(extra="forbid")
    id: str
    type: str
    name: str
    ports: list[str] = Field(default_factory=list)


class GeminiLink(BaseModel):
    """One directed old diagram connection."""

    model_config = ConfigDict(extra="forbid")
    source: str
    source_port: str
    target: str
    target_port: str


class GeminiParam(BaseModel):
    """Raw dated old property values and optional documented unit."""

    model_config = ConfigDict(extra="forbid")
    values: list[Any]
    timestamps: list[datetime | None]
    unit: str | None = None


class GeminiTags(BaseModel):
    """Old tag names grouped by their source/destination kind."""

    model_config = ConfigDict(extra="forbid")
    measured: dict[str, str] = Field(default_factory=dict)
    filtered: dict[str, str] = Field(default_factory=dict)
    calculated: dict[str, str] = Field(default_factory=dict)


class GeminiProject(BaseModel):
    """Typed old project plus private raw material for lossless round trips."""

    model_config = ConfigDict(extra="forbid")
    nodes: dict[str, GeminiNode]
    links: list[GeminiLink]
    params: dict[str, dict[str, GeminiParam]]
    tags: dict[str, GeminiTags]
    _folder: Path | None = PrivateAttr(default=None)
    _diagram: dict | None = PrivateAttr(default=None)
    _param_files: dict[str, dict] = PrivateAttr(default_factory=dict)
    _auxiliary: dict[str, bytes] = PrivateAttr(default_factory=dict)


def _one_tag(values):
    populated = [str(value) for value in values if value]
    if len(set(populated)) > 1:
        raise ValueError(f"time-varying tag columns are unsupported: {populated!r}")
    return populated[0] if populated else ""


def read_project(folder):
    """Read and validate old diagram/.param files without interpreting physical values."""
    folder = Path(folder)
    diagram_path = folder / "diagram.json"
    try:
        diagram = read_json(diagram_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{diagram_path}: invalid old diagram JSON: {exc}") from exc
    nodes, links = {}, []
    for cell in diagram.get("cells", []):
        if cell.get("type") == "devs.Model":
            properties = cell.get("properties", {})
            node_id = cell.get("id")
            try:
                nodes[node_id] = GeminiNode(
                    id=node_id,
                    type=properties["type"],
                    name=properties["name"],
                    ports=[item["id"] for item in cell.get("ports", {}).get("items", [])],
                )
            except (KeyError, TypeError) as exc:
                raise ValueError(
                    f"{diagram_path}: malformed model node {node_id!r}: {exc}"
                ) from exc
        elif cell.get("type") == "devs.Link":
            try:
                links.append(
                    GeminiLink(
                        source=cell["source"]["id"],
                        source_port=cell["source"]["port"],
                        target=cell["target"]["id"],
                        target_port=cell["target"]["port"],
                    )
                )
            except KeyError as exc:
                raise ValueError(f"{diagram_path}: malformed link field {exc}") from exc

    params, tags, raw_files = {}, {}, {}
    for path in sorted(folder.glob("*.param")):
        try:
            raw = read_json(path)
            node_id = raw["id"]
            timestamps = raw["parameters"]["timestamps"]
            properties = raw["parameters"]["property"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"{path}: malformed old parameter file: {exc}") from exc
        if node_id not in nodes:
            raise ValueError(f"{path}: node id {node_id!r} is absent from diagram.json")
        parsed_times = [
            pd.Timestamp(value).to_pydatetime() if value else None for value in timestamps
        ]
        params[node_id] = {}
        for name, values in properties.items():
            values = values if isinstance(values, list) else [values]
            if len(values) != len(parsed_times):
                raise ValueError(
                    f"{path}: parameters.property.{name} has {len(values)} values for "
                    f"{len(parsed_times)} timestamps"
                )
            params[node_id][name] = GeminiParam(values=values, timestamps=parsed_times)
        raw_tags = raw.get("tagnames", {})
        tags[node_id] = GeminiTags(
            **{
                kind: {name: _one_tag(values) for name, values in raw_tags.get(kind, {}).items()}
                for kind in ("measured", "filtered", "calculated")
            }
        )
        raw_files[path.name] = raw
    if set(params) != set(nodes):
        missing = sorted(set(nodes) - set(params))
        extra = sorted(set(params) - set(nodes))
        raise ValueError(f"Old project node/.param mismatch: missing={missing}, extra={extra}")
    project = GeminiProject(nodes=nodes, links=links, params=params, tags=tags)
    project._folder = folder
    project._diagram = diagram
    project._param_files = raw_files
    for path in folder.iterdir():
        if path.is_file() and path.name not in raw_files and path.name != "diagram.json":
            project._auxiliary[path.name] = path.read_bytes()
    return project


def write_project(project, folder):
    """Write old project files; parsed projects retain values exactly after JSON normalisation."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    diagram = project._diagram
    param_files = deepcopy(project._param_files)
    if diagram is None:
        diagram = {"cells": []}
        for node in project.nodes.values():
            diagram["cells"].append(
                {
                    "id": node.id,
                    "type": "devs.Model",
                    "ports": {"items": [{"id": port} for port in node.ports]},
                    "properties": {"name": node.name, "type": node.type},
                }
            )
        for index, link in enumerate(project.links):
            diagram["cells"].append(
                {
                    "id": f"link-{index}",
                    "type": "devs.Link",
                    "source": {"id": link.source, "port": link.source_port},
                    "target": {"id": link.target, "port": link.target_port},
                }
            )
        param_files = {}
        for node_id, node in project.nodes.items():
            values = project.params[node_id]
            timestamps = next(iter(values.values())).timestamps if values else [None]
            count = len(timestamps)
            tags = project.tags.get(node_id, GeminiTags())
            param_files[node.name + ".param"] = {
                "id": node.id,
                "name": node.name,
                "type": node.type,
                "parameters": {
                    "property": {name: value.values for name, value in values.items()},
                    "timestamps": [
                        value.strftime("%Y-%m-%d %H:%M:%S") if value else None
                        for value in timestamps
                    ],
                },
                "tagnames": {
                    kind: {name: [column] * count for name, column in getattr(tags, kind).items()}
                    for kind in ("measured", "filtered", "calculated")
                }
                | {
                    "timestamps": [
                        value.strftime("%Y-%m-%d %H:%M:%S") if value else None
                        for value in timestamps
                    ]
                },
            }
    else:
        by_id = {raw["id"]: raw for raw in param_files.values()}
        for node_id, properties in project.params.items():
            raw = by_id[node_id]
            if not properties:
                # The typed old model has no place to retain a timestamp axis for an empty
                # property block, so keep the faithful raw file unchanged.
                continue
            timestamps = next(iter(properties.values())).timestamps if properties else []
            for value in properties.values():
                if value.timestamps != timestamps:
                    raise ValueError(f"{node_id}: old properties require one shared timestamp axis")
            formatted = [
                value.strftime("%Y-%m-%d %H:%M:%S") if value else None for value in timestamps
            ]
            raw["parameters"]["timestamps"] = formatted
            raw["parameters"]["property"] = {
                name: value.values for name, value in properties.items()
            }
            tags = project.tags.get(node_id, GeminiTags())
            raw["tagnames"] = {
                kind: {
                    name: [column] * len(timestamps) for name, column in getattr(tags, kind).items()
                }
                for kind in ("measured", "filtered", "calculated")
            } | {"timestamps": formatted}
    write_json(folder / "diagram.json", diagram, indent=4)
    for name, raw in param_files.items():
        write_json(folder / name, raw, indent=4)
    for name, value in project._auxiliary.items():
        (folder / name).write_bytes(value)


def read_csv(path):
    """Read an old semicolon CSV and parse its first timestamp-like column."""
    path = Path(path)
    try:
        frame = pd.read_csv(path, sep=";")
    except (OSError, pd.errors.ParserError) as exc:
        raise ValueError(f"{path}: invalid old CSV: {exc}") from exc
    if len(frame.columns):
        first = frame.columns[0]
        try:
            frame[first] = pd.to_datetime(frame[first], format="mixed")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}: invalid timestamp column {first!r}: {exc}") from exc
    return frame


def write_csv(frame, path):
    """Write the old semicolon CSV with its conventional timestamp representation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    if len(output.columns) and pd.api.types.is_datetime64_any_dtype(output.iloc[:, 0]):
        output.iloc[:, 0] = output.iloc[:, 0].dt.strftime("%Y-%m-%d %H:%M:%S")
    output.to_csv(path, sep=";", index=False)
