"""The outputs of a built plant: sums, copies of one module's value and ratios, from the spec."""

from gemini.errors import ValidationError
from gemini.modules.balance import ENERGY_INPUTS, ENERGY_OUTPUTS
from gemini.types.declarations import Output
from gemini.types.quantities import TemperatureDifference
from gemini.utils.strings import close_matches, did_you_mean, join_names

ENERGY = ENERGY_INPUTS + ENERGY_OUTPUTS
KEYS = ("of", "sum", "ratio", "difference")


def declare_automatic(plant):
    """Declare the sum of each energy output that some descendant leaf declares."""
    leaves = plant._descendant_leaves()
    for name in ENERGY:
        kinds = [leaf._outputs[name].kind for leaf in leaves if name in leaf._outputs]
        if kinds:
            plant._register_declaration(name, Output(kinds[0]))


def _unknown(subject, name, valid):
    return ValidationError(
        f"{subject}: unknown name {name!r}; valid: {join_names(valid)}{did_you_mean(name, valid)}",
        suggestions=close_matches(name, valid),
        code="unknown_name",
    )


def _target(plant, spec):
    path, _, local = spec["of"].rpartition(".")
    module = plant._find_submodule(path) if path else None
    if module is None:
        paths = [item for item, _ in plant.named_modules() if item]
        raise ValidationError(
            f"of = {spec['of']!r}: no module {path!r}{did_you_mean(path, paths)}",
            path="of",
            suggestions=close_matches(path, paths),
            code="unknown_name",
        )
    if "field" in spec:
        if local not in module._outlets:
            raise _unknown("of", local, module._outlets)
        return module._outlets[local].field(spec["field"])
    if local not in module._outputs:
        raise _unknown("of", local, module._outputs)
    return module._outputs[local]


def _summed(plant, spec):
    name = spec["sum"]
    declarations = [
        leaf._outputs[name] for leaf in plant._descendant_leaves() if name in leaf._outputs
    ]
    if not declarations:
        names = sorted({n for leaf in plant._descendant_leaves() for n in leaf._outputs})
        raise _unknown("sum", name, names)
    if not declarations[0].additive:
        raise ValidationError(f"sum = {name!r}: not an additive output", path="sum")
    return Output(declarations[0].kind)


def _ratio(plant, spec):
    names = spec["ratio"]
    for name in names:
        if name not in plant._outputs:
            raise _unknown("ratio", name, plant._outputs)
    return Output.ratio(*(plant._outputs[name] for name in names))


def _difference(plant, spec):
    names = spec["difference"]
    for name in names:
        if name not in plant._outputs:
            raise _unknown("difference", name, plant._outputs)
    return Output.difference(
        *(plant._outputs[name] for name in names), TemperatureDifference | None
    )


def declare_output(plant, name, spec):
    """Declare output ``name`` from a spec entry.

    The entry is ``{"of": path}``, ``{"sum": name}``, ``{"ratio": [a, b]}`` or
    ``{"difference": [a, b]}``, the temperature difference of two outputs.
    """
    given = [key for key in KEYS if key in spec]
    if len(given) != 1:
        raise ValidationError(
            f"{name}: keys = {sorted(spec)}; expected exactly one of {join_names(KEYS)}",
            path="",
            code="invalid_format",
        )
    builders = {"of": lambda: Output.of(_target(plant, spec)), "sum": lambda: _summed(plant, spec)}
    builders["ratio"] = lambda: _ratio(plant, spec)
    builders["difference"] = lambda: _difference(plant, spec)
    if name in plant._children:
        raise ValidationError(f"{name}: an output cannot share the name of a module", path="")
    plant._register_declaration(name, builders[given[0]]())


def ordered(specs):
    """Return ``(name, spec)`` in given order, a ratio after the outputs it divides."""
    result, waiting = [], []

    def ready(item):
        operands = item[1].get("ratio", ()) or item[1].get("difference", ())
        return all(operand in {name for name, _ in result} for operand in operands)

    for item in specs.items():
        waiting.append(item)
        while any(ready(candidate) for candidate in waiting):
            first = next(candidate for candidate in waiting if ready(candidate))
            waiting.remove(first)
            result.append(first)
    return result + waiting
