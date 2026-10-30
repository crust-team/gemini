"""Which ports a connection joins: the lookups and rules of ``Plant.connect``."""

from gemini.errors import UnknownNameError, ValidationError
from gemini.modules.module import Module
from gemini.modules.plants.plan import is_group, members, split_end
from gemini.types.declarations import Declaration
from gemini.utils.strings import close_matches, did_you_mean, join_names, join_path

SIDE_OF = {"source": "outlets", "target": "inlets"}


def _compatible(first, second):
    return first.stream is None or second.stream is None or first.stream == second.stream


def _describe_end(candidate):
    path, port, declaration = candidate
    return f"{join_path(path, port)} [{declaration.stream or 'any'}]"


class PortResolver:
    """Methods of ``Plant`` that find, check and name ports (needs its ``_connections``)."""

    def _is_port_name(self, value):
        return isinstance(value, str) and "." not in value and self._find_submodule(value) is None

    def _name_port(self, side, name, end, explicit):
        field = "target" if side == "inlets" else "source"
        candidates = self._candidates(end, field, explicit)
        if len(candidates) != 1:
            raise self._ambiguous(list(map(_describe_end, candidates)), field)
        if name in self._listed[side] or name in self._children:
            raise ValidationError(
                f"{name}: plant port name is already taken", path="", code="invalid_connection"
            )
        path, port, _ = candidates[0]
        self._listed[side][name] = (path, port)
        self._refresh()

    def _candidates(self, value, field, explicit):
        side = SIDE_OF[field]
        path, port = self._locate(value, field, explicit)
        declared = getattr(self.get_module(path), side)()
        if port is not None:
            return [self._checked(path, port, declared, side, field)]
        free = [
            (path, name, item)
            for name, item in declared.items()
            if not self._in_use(path, name, side)
        ]
        if not free:
            code = "port_in_use" if declared else "unknown_port"
            raise ValidationError(f"{path}: no free {side[:-1]} to connect", path=field, code=code)
        return free

    def _checked(self, path, port, declared, side, field):
        if port not in declared:
            raise ValidationError(
                f"{join_path(path, port)}: not an {side[:-1]}; valid: {join_names(declared)}"
                f"{did_you_mean(port, declared)}",
                path=field,
                code="unknown_port",
                suggestions=close_matches(port, declared),
            )
        if self._in_use(path, port, side):
            raise ValidationError(
                f"{join_path(path, port)}: {side[:-1]} is already connected",
                path=field,
                code="port_in_use",
            )
        return path, port, declared[port]

    def _in_use(self, path, port, side):
        key = "source" if side == "outlets" else "target"
        used = {split_end(item[key]) for item in self._connections}
        return (path, port) in used | set(self._listed[side].values())

    def _locate(self, value, field, explicit):
        path, port = self._parse(value, field)
        module = self._find_submodule(path)
        if module is None:
            paths = [item for item, _ in members(self)]
            raise UnknownNameError(
                f"{value!r}: no module {path!r}{did_you_mean(path, paths)}",
                path=field,
                suggestions=close_matches(path, paths),
            )
        self._check_reach(path, field)
        if port is None and explicit:
            free = [f"{path}.{name}" for name in getattr(module, SIDE_OF[field])()]
            raise ValidationError(
                f"{value!r}: name a port, one of {join_names(free)}",
                path=field,
                code="invalid_connection",
                suggestions=free,
            )
        return path, port

    def _parse(self, value, field):
        if isinstance(value, Declaration):
            return self._descendant_path(value.owner) or "", value.name
        if isinstance(value, Module):
            return self._descendant_path(value) or "", None
        if not isinstance(value, str):
            raise ValidationError(
                f"{value!r}: expected a module, a port or 'path.port'", path=field
            )
        if value and self._find_submodule(value) is not None:
            return value, None
        path, _, port = value.rpartition(".")
        return path, port or None

    def _check_reach(self, path, field):
        parts = path.split(".")
        module = self
        for index, part in enumerate(parts):
            if index and not is_group(module):
                prefix = ".".join(parts[:index])
                raise ValidationError(
                    f"{path}: reaches into {prefix!r}; use its own ports, one of "
                    f"{join_names(list(module.inlets()) + list(module.outlets()))}",
                    path=field,
                    code="invalid_connection",
                )
            module = module._children[part]
        if is_group(module):
            raise ValidationError(
                f"{path}: a group has no ports", path=field, code="invalid_connection"
            )

    def _choose(self, first, second):
        pairs = [(a, b) for a in first for b in second if _compatible(a[2], b[2])]
        if len(pairs) == 1:
            return pairs[0]
        if not pairs:
            raise ValidationError(
                f"stream mismatch: {', '.join(map(_describe_end, first))} to "
                f"{', '.join(map(_describe_end, second))}",
                path="target",
                code="stream_mismatch",
            )
        raise self._ambiguous([" -> ".join(map(_describe_end, pair)) for pair in pairs], "target")

    def _ambiguous(self, listed, field):
        return ValidationError(
            f"ambiguous port: {len(listed)} candidates: {'; '.join(listed)}",
            path=field,
            code="ambiguous_port",
            suggestions=listed,
        )

    def _port_map(self, side):
        """Return the plant's ``inlets`` or ``outlets`` as ``{name: (path, port)}``.

        Ports named in the plant come first, then every free port of a child, named
        ``<path with underscores>_<port>``.
        """
        result = dict(self._listed[side])
        for path, module in members(self):
            for port in getattr(module, side)():
                if not self._in_use(path, port, side):
                    result[f"{path.replace('.', '_')}_{port}"] = (path, port)
        return result
