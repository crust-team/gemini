"""Every parameter, output and port name follows ``.claude/docs/glossary.md``."""

import re

import pytest

import gemini as gm
from tests.fixtures import ROOT

GLOSSARY = (ROOT / ".claude/docs/glossary.md").read_text()
SECTIONS = ("parameters", "controls", "boundaries", "state", "outputs", "inlets", "outlets")
RETIRED = set(re.findall(r"^\| `(\w+)` \| `\w+` \|$", GLOSSARY, re.MULTILINE))
VOCABULARY = set(GLOSSARY.split("```text")[1].split("```")[0].split())


def declared_names(name):
    """Return the module's own parameter, control, boundary, state, output and port names."""
    described = gm.modules.get(name)().describe()
    return {key for section in SECTIONS for key in described[section] if "." not in key}


def words(name):
    """Return the words of a name; the suffix ``_T`` of a port temperature is not a word."""
    return re.sub(r"_T$", "", name).split("_")


@pytest.mark.parametrize("name", gm.modules.names())
def test_every_declared_name_follows_the_glossary(name):
    """No name is retired and each word of a name is in the vocabulary."""
    names = declared_names(name)
    assert names & RETIRED == set()
    assert {word for key in names for word in words(key)} - VOCABULARY == set()


@pytest.mark.parametrize("name", gm.modules.names())
def test_a_port_temperature_names_a_port(name):
    """The suffix ``_T`` belongs to an output named after a port of the module or of a child."""
    described = gm.modules.get(name)().describe()
    kinds = set(described["children"].values()) & set(gm.modules.names())
    children = [gm.modules.get(kind)().describe() for kind in kinds]
    ports = {
        port
        for item in [described, *children]
        for port in item["inlets"].keys() | item["outlets"].keys()
    }
    suffixed = [key for key in described["outputs"] if key.endswith("_T") and "." not in key]
    assert {key.removesuffix("_T") for key in suffixed} <= ports


def test_the_lists_are_read():
    """The glossary parser finds both lists."""
    assert "ua" in RETIRED and "temperature" in VOCABULARY
