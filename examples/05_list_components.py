"""Print all discovered component schemas as JSON."""

import json

from gemini.core.engine.registry import list_components

print(json.dumps(list_components(), indent=2))
