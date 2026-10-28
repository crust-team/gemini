"""Print all discovered module schemas as JSON."""

import json

from gemini.core.engine.registry import list_modules

print(json.dumps(list_modules(), indent=2))
