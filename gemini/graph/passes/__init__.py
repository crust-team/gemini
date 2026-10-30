"""Graph passes: rewrites of a traced ``Graph`` that keep its results and its errors."""

from gemini.graph.passes.cse import eliminate_common_subexpressions

__all__ = ["eliminate_common_subexpressions"]
