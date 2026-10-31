"""Design-year demand profiles in the run-input format.

``names()`` lists the profiles, ``get(name)`` returns one as a pandas DataFrame with a UTC index and
one column per quantity, ready for ``Engine.simulate``, ``demand()`` both in one frame, and
``profile_schema()`` is the JSON Schema of the profile file. The demand files are in
``inputs/hackathon/`` of a source checkout: ``get`` raises ``inputs_missing`` without them.
"""

from .library import demand, get, names
from .schema import profile_schema

__all__ = ["names", "get", "demand", "profile_schema"]
