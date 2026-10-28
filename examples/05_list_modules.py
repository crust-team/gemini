"""Print the public equipment and plant contracts as JSON."""

import json

import gemini as gm

classes = [getattr(gm.modules, name) for name in gm.modules.__all__]
print(
    json.dumps(
        [
            cls.schema()
            for cls in classes
            if isinstance(cls, type)
            and issubclass(cls, gm.modules.Module)
            and cls not in (gm.modules.Module, gm.modules.Sequential)
        ],
        indent=2,
    )
)
