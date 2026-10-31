"""Nodes label themselves and record the physics line that created them."""

import sys

from gemini.compiler.graph.node import Node, caller_source


def test_label_names_inputs():
    """Inputs show their name next to their index."""
    assert Node(3, "input", "input", name="frequency").label() == "%3<frequency>"
    assert Node(4, "add", "elementwise").label() == "%4"


def test_caller_source_is_the_calling_line_outside_the_tracing_packages():
    """The source is this test file and the line of the call."""
    source, line = caller_source(), sys._getframe().f_lineno
    assert source == f"{__file__}:{line}"
