"""Every numeric equipment contract needs units or an explicit justified exception."""

from gemini.core.engine.registry import list_modules

ALLOWLIST = {
    ("esp", "params", "head_coeff"): "Mixed-order polynomial in ft/stage vs bbl/day.",
    ("esp", "params", "power_coeff"): "Mixed-order polynomial in bhp/stage vs bbl/day.",
    ("injectionpump", "params", "head_coeff"): "Mixed-order US-basis polynomial.",
    ("injectionpump", "params", "power_coeff"): "Mixed-order US-basis polynomial.",
    ("degasser", "params", "heat_transfer_coeff"): "Unused legacy metadata; dimension unknown.",
}


def numeric_without_unit(schema):
    """Inspect unions and containers without mistaking literal strings for numbers."""
    if schema.get("type") in ("number", "integer"):
        return not (schema.get("unit") and schema.get("quantity"))
    children = schema.get("anyOf", []) + schema.get("prefixItems", [])
    if "items" in schema:
        children.append(schema["items"])
    return any(numeric_without_unit(child) for child in children)


def test_registered_fields():
    """Scan every registered contract and fail on newly introduced untyped numbers."""
    for module in list_modules():
        for contract in ("params", "inputs", "outputs"):
            for name, field in module[contract].get("properties", {}).items():
                if (module["name"], contract, name) not in ALLOWLIST:
                    assert not numeric_without_unit(field), (module["name"], contract, name)
