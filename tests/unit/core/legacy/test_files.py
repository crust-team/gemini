"""Small synthetic old-format parser tests."""

import json

import pandas as pd

import gemini as gm


def test_project_and_csv_round_trip(tmp_path):
    """Raw old values survive JSON normalisation and semicolon CSV conversion."""
    node_id = "node-1"
    diagram = {
        "cells": [
            {
                "id": node_id,
                "type": "devs.Model",
                "properties": {"name": "pump", "type": "esp"},
                "ports": {"items": [{"id": "in"}, {"id": "out"}]},
            }
        ]
    }
    parameter = {
        "id": node_id,
        "name": "pump",
        "type": "esp",
        "parameters": {"property": {"stages": [10]}, "timestamps": ["2024-01-01"]},
        "tagnames": {
            "measured": {"flow": ["Q"]},
            "filtered": {},
            "calculated": {},
        },
    }
    (tmp_path / "diagram.json").write_text(json.dumps(diagram))
    (tmp_path / "pump.param").write_text(json.dumps(parameter))
    project = gm.legacy.read_project(tmp_path)
    assert project.nodes[node_id].ports == ["in", "out"]
    out = tmp_path / "out"
    gm.legacy.write_project(project, out)
    assert gm.legacy.read_project(out).params == project.params
    frame = pd.DataFrame({"Timestamp": pd.to_datetime(["2024-01-01"]), "Q": [1.5]})
    gm.legacy.write_csv(frame, tmp_path / "old.csv")
    assert gm.legacy.read_csv(tmp_path / "old.csv").Q.iloc[0] == 1.5
