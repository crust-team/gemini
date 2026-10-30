"""Design-year demand profiles in the run-input format.

``names()`` lists the profiles, ``get(name)`` returns one as a pandas DataFrame with a UTC index and
one column per quantity, ready for ``Engine.simulate``, and ``profile_schema()`` is the JSON Schema
of the profile file. No demand data ships yet: ``get`` raises ``NotImplementedYet`` until the
hackathon inputs are added as ``profiles/data/<name>.json``.
"""

from .library import get, names
from .schema import profile_schema

__all__ = ["names", "get", "profile_schema"]
