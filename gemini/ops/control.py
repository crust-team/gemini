"""``scan``: time stepping with a carried state; defined only, with no backend implementation.

A ``scan(step, initial_state, inputs)`` node will carry the states of a stateful module (or a
time integral) from row to row. Until a backend implements it, tracing a stateful module is a
graph break and the module runs tick by tick.
"""

from gemini.ops.registry import register

register("scan", "scan", 3)
