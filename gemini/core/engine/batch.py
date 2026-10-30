"""Batch evaluation of the replay twins through the computation graph.

``Batch.compute`` runs before the commit loop of ``Engine._run``. For every twin and every
stretch of ticks that share one parameter snapshot it evaluates the twin once on arrays over the
rows that can be evaluated, and keeps the results of the rows it **claims**: the rows with every
observation present, no failed check or break node reaching an output and only finite values (NaN
only for a declared ``X | None`` output). The commit loop then takes a claimed row from the batch
instead of calling the module; every other row, and every row of a twin the graph cannot carry
(stateful, untraceable, float32), runs on the plain path at its own tick, which raises the exact
error, skip or result of an untraced replay. The reason a twin has no claims is kept in
``Batch.reasons``, by twin path.

Claimed rows hold plain Python ``float``, ``bool`` and ``None`` values and a ``ModuleResult``
without ``children`` or ``call_records``. The inputs a claimed row applies to its twin
(``module.set_inputs`` on the plain path) are applied at once when the run has callbacks, else
once at the end, for the last tick that applied them. The marked observer hooks of a twin
(``EventLog``) are replayed for each claimed row in the commit loop, in today's order.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from gemini import backends
from gemini.core.engine.step import VOLUMETRIC_UNITS, is_volumetric_mass_flow
from gemini.core.physics import units
from gemini.core.types import Fluid, Stream
from gemini.core.types.ports import Ports
from gemini.core.types.results import ModuleResult, Values
from gemini.errors import TraceError
from gemini.graph.interpreter import Interpreter
from gemini.graph.node import STREAM_FIELDS
from gemini.graph.runner import graph_feeds, replay_row

FIELDS = tuple(name for name, _ in STREAM_FIELDS)
"""The fields of an inlet stream, in the order the graph names them."""


class Batch:
    """The precomputed rows of the replay twins of one run, and what they could not carry."""

    def __init__(self, times, eager):
        """Index the ticks of the run; ``eager`` applies claimed inputs per tick (callbacks)."""
        self.positions = {at: index for index, at in enumerate(times)}
        self.eager = eager
        self.claims = {}
        self.reasons = {}
        self.pending = {}
        self.modules = {}

    @classmethod
    def compute(cls, plan, plant, aligned, cache, eager):
        """Evaluate every twin of ``plan`` over ``aligned`` rows; leave the plan and plant as found.

        The parameters of the plant are restored afterwards, because dated snapshots apply
        only the values they list; the commit loop applies them again from the first tick.
        """
        batch = cls(aligned.times, eager)
        aligned = _Table(aligned)
        entries = plan.entries
        nested = [path for path, *_ in entries if _has_twin_below(path, entries)]
        if nested:
            reason = "a twin below another twin: composite twins run tick by tick"
            batch.reasons = {path: reason for path, *_ in entries}
            return batch
        saved = [
            (parameter, parameter.value)
            for module in plant.modules()
            for parameter in module._parameters.values()
        ]
        try:
            for entry in entries:
                batch._twin(entry, plan, plant, aligned, cache)
        finally:
            for parameter, value in saved:
                parameter.value = value
        return batch

    def claim(self, path, module, at):
        """Return ``(result, measured)`` of a claimed row, applying its inputs, else ``None``."""
        claims = self.claims.get(path)
        index = self.positions.get(at)
        if claims is None or index is None or not claims.claimed[index]:
            return None
        applied = claims.applied(index)
        if self.eager:
            module.set_inputs(applied)
        else:
            self.pending[path] = applied
        return claims.result(index, applied), claims.measured(index)

    def persisted(self, path):
        """Forget the inputs a claimed row left pending: a later plain tick persisted its own."""
        self.pending.pop(path, None)

    def flush(self):
        """Persist the inputs of the last claimed tick of every twin that has not been replaced."""
        pending, self.pending = self.pending, {}
        for path, applied in pending.items():
            self.modules[path].set_inputs(applied)

    def _twin(self, entry, plan, plant, aligned, cache):
        path, module = entry[0], entry[1]
        try:
            claims = _Twin(entry, plan, plant, aligned, cache).claims()
        except TraceError as error:
            self.reasons[path] = str(error)
            return
        self.claims[path] = claims
        self.modules[path] = module


def _has_twin_below(path, entries):
    return bool(path) and any(other.startswith(path + ".") for other, *_ in entries)


@dataclass
class Claims:
    """The claimed rows of one twin: ``claimed`` flags and one Python list per value.

    ``columns`` maps ``("inlets" | "outlets", port, field)``, ``("outputs" | "applied" |
    "measured", name)`` to a list as long as the run; ``outputs`` is the recording order of the
    outputs and ``applied`` and ``measured`` list the bound controls and measured names.
    """

    module: object
    graph: object
    claimed: list
    columns: dict
    fluids: dict
    base_inputs: dict
    outputs: list = field(default_factory=list)
    applied_names: list = field(default_factory=list)
    measured_names: list = field(default_factory=list)

    def __post_init__(self):
        """Group the columns by row once, so that a claimed row is a tuple lookup."""
        size = len(self.claimed)
        columns = self.columns
        self._outputs = _rows([columns["outputs", name] for name in self.outputs], size)
        self._applied = _rows([columns["applied", name] for name in self.applied_names], size)
        self._measured = _rows([columns["measured", name] for name in self.measured_names], size)
        outlet_fluids = self.graph.outlet_fluids if self.graph is not None else {}
        self._streams = {
            (section, port): _rows([columns[section, port, name] for name in FIELDS], size)
            for section, ports in (("inlets", self.fluids), ("outlets", outlet_fluids))
            for port in ports
        }
        template = dict.fromkeys(self.module._controls | self.module._boundaries)
        self._inputs = template | self.base_inputs
        self._declarations = dict(self.module._outputs)

    def applied(self, index):
        """Return the controls and boundaries the data set on this tick."""
        return dict(zip(self.applied_names, self._applied[index]))

    def measured(self, index):
        """Return the measured values of this tick, in SI."""
        return dict(zip(self.measured_names, self._measured[index]))

    def result(self, index, applied):
        """Return the ``ModuleResult`` of a claimed row and replay the twin's observer hooks."""
        module = self.module
        outputs = dict(zip(self.outputs, self._outputs[index]))
        inlets = self._ports("inlets", self.fluids, index)
        outlets = self._ports("outlets", self.graph.outlet_fluids, index)
        inputs = self._inputs.copy()
        inputs.update(applied)
        if self.graph.observers or self.graph.pre_observers:
            replay_row(self.graph, module, inlets, outlets, inputs, outputs)
        return ModuleResult(
            outputs=Values._trusted(outputs, self._declarations),
            outlets=outlets,
            inlets=inlets,
            inputs=inputs,
            is_leaf=module.is_leaf,
        )

    def _ports(self, section, fluids, index):
        streams = {
            port: Stream._trusted(*self._streams[section, port][index], fluid)
            for port, fluid in fluids.items()
        }
        return Ports._trusted(streams, self.module.path)


def _rows(columns, size):
    """Return one tuple per row of the given columns; no column gives empty tuples."""
    return list(zip(*columns)) if columns else [()] * size


class _Table:
    """The aligned samples with their columns converted to float once, on first use."""

    def __init__(self, aligned):
        self.times = aligned.times
        self._columns = aligned.columns
        self._numbers = {}

    def numbers(self, column):
        """Return a column as floats; what ``float()`` refuses (text, ``None``) is NaN."""
        if column not in self._numbers:
            self._numbers[column] = _floats(self._columns[column])
        return self._numbers[column]


def _floats(values):
    if values.dtype.kind == "f":
        return values
    numbers = np.full(len(values), np.nan)
    for index, value in enumerate(values):
        try:
            numbers[index] = float(value)
        except (TypeError, ValueError):
            continue
    return numbers


class _Twin:
    """The batch evaluation of one twin: columns, stretches, graph run and claimed rows."""

    def __init__(self, entry, plan, plant, aligned, cache):
        self.path, self.module, self.bound, self.defaults = entry
        self.plan, self.plant, self.aligned, self.cache = plan, plant, aligned, cache
        self.rows = len(aligned.times)
        self.indices, self.chunks = [], {}
        self.graph = None
        self.fluids = {}

    def claims(self):
        """Evaluate every stretch and return the ``Claims`` of the twin."""
        module = self.module
        if module.stateful:
            raise TraceError(f"{module.path}: stateful twin runs tick by tick")
        if set(self.bound.inlets) != set(module._inlets):
            raise TraceError(f"{module.path}: every inlet needs a binding to be evaluated")
        for start, stop in self.plan.parameter_stretches(self.aligned.times):
            self.plant.apply_params_at(self.aligned.times[start])
            self._stretch(start, stop)
        return self._assembled()

    def _stretch(self, start, stop):
        """Evaluate the candidate rows of ``[start, stop)`` and keep the claimed ones."""
        columns = _Columns(self, start, stop)
        selected = np.flatnonzero(columns.candidate)
        if not selected.size:
            return
        graph = self.cache.graph(self.module, columns.fluids)
        self.graph, self.fluids = graph, columns.fluids
        streams = {
            port: Stream._trusted(
                fluid=columns.fluids[port], **{n: columns.inlets[port, n][selected] for n in FIELDS}
            )
            for port in self.module._inlets
        }
        inputs = {name: values[selected] for name, values in columns.applied.items()}
        feeds = graph_feeds(graph, self.module, streams, inputs)
        with np.errstate(all="ignore"):
            outputs, failed = Interpreter(graph, backends.get("numpy")).evaluate(feeds)
        values, claimed = _graph_values(graph, self.module, outputs, failed, len(selected))
        self._keep(start + selected[claimed], columns, selected[claimed], values, claimed)

    def _keep(self, rows, columns, selected, values, claimed):
        self.indices.append(rows)
        for key, array in values.items():
            self.chunks.setdefault(key, []).append(array[claimed])
        for (port, name), array in columns.inlets.items():
            self.chunks.setdefault(("inlets", port, name), []).append(array[selected])
        for section, group in (("applied", columns.applied), ("measured", columns.measured)):
            for name, array in group.items():
                self.chunks.setdefault((section, name), []).append(array[selected])

    def _assembled(self):
        """Scatter the kept chunks into full-length Python lists and build the ``Claims``."""
        module = self.module
        rows = np.concatenate(self.indices) if self.indices else np.empty(0, dtype=int)
        claimed = np.zeros(self.rows, dtype=bool)
        claimed[rows] = True
        values = {key: self._scatter(key, chunks, rows) for key, chunks in self.chunks.items()}
        base = {
            name: module._input_value(name)
            for name in module.inputs(recurse=False)
            if name not in self.bound.controls and name not in self.bound.boundaries
        }
        return Claims(
            module,
            self.graph,
            claimed.tolist(),
            values,
            self.fluids,
            base,
            outputs=_output_names(self.graph) if self.graph is not None else [],
            applied_names=list(self.bound.controls | self.bound.boundaries),
            measured_names=list(self.bound.measured),
        )

    def _scatter(self, key, chunks, rows):
        kept = np.concatenate(chunks)
        full = np.zeros((self.rows,) + kept.shape[1:], dtype=kept.dtype)
        if kept.dtype.kind == "f":
            full[:] = np.nan
        full[rows] = kept
        column = full.tolist()
        if key[0] == "outputs" and self.module._outputs[key[1]].accepts_none():
            return [None if _is_nan(value) else value for value in column]
        return column


def _is_nan(value):
    return isinstance(value, float) and math.isnan(value)


class _Columns:
    """The SI columns of one twin over one stretch, and which of its rows can be evaluated."""

    def __init__(self, twin, start, stop):
        self.twin, self.start, self.stop = twin, start, stop
        module, bound = twin.module, twin.bound
        self.candidate = np.ones(stop - start, dtype=bool)
        self.applied = self._inputs()
        self.inlets, self.fluids = {}, {}
        for port, fields in bound.inlets.items():
            self._inlet(port, fields)
        outputs = module.outputs(recurse=False)
        self.measured = {
            name: self._column(binding, outputs.get(name))
            for name, binding in bound.measured.items()
        }

    def _raw(self, binding):
        """Return the column as floats over the stretch, clearing the rows that are not finite."""
        numbers = self.twin.aligned.numbers(binding.column)[self.start : self.stop]
        self.candidate &= np.isfinite(numbers)
        return numbers

    def _column(self, binding, declaration=None):
        """Return a bound column in SI as ``units.to_si`` computes one value."""
        quantity = declaration.quantity if declaration is not None else None
        scale, offset = units.si_conversion(binding.unit, quantity)
        return self._raw(binding) * scale + offset

    def _inputs(self):
        """Return the SI columns of the controls and boundaries; volume flows become mass flows."""
        module, bound = self.twin.module, self.twin.bound
        declarations = module.inputs(recurse=False)
        values = {
            name: self._column(binding, declarations.get(name))
            for group in (bound.controls, bound.boundaries)
            for name, binding in group.items()
        }
        for name, binding in (bound.controls | bound.boundaries).items():
            if is_volumetric_mass_flow(module, name, binding):
                properties = module.fluid.properties(module.pressure, module.temperature)
                values[name] *= properties.density
        return values

    def _inlet(self, port, fields):
        """Add the SI columns of one inlet port over its defaults and mark invalid streams."""
        module, defaults = self.twin.module, self.twin.defaults.get(port, {})
        if not set(fields) <= set(FIELDS) or not set(defaults) <= {*FIELDS, "fluid"}:
            raise TraceError(f"{module.path}: inlet {port!r} has fields the batch cannot build")
        values = {name: float(value) for name, value in defaults.items() if name != "fluid"}
        values.update({name: self._column(binding) for name, binding in fields.items()})
        missing = [name for name in FIELDS if name not in values]
        if missing:
            raise TraceError(f"{module.path}: inlet {port!r} lacks {', '.join(missing)}")
        fluid = Fluid.model_validate(defaults.get("fluid", module.fluid))
        if "m_dot" in fields and fields["m_dot"].unit in VOLUMETRIC_UNITS:
            values["m_dot"] = values["m_dot"] * fluid.properties(values["p"], values["T"]).density
        size = self.stop - self.start
        for name in FIELDS:
            self.inlets[port, name] = np.broadcast_to(np.asarray(values[name], dtype=float), size)
        self.fluids[port] = fluid
        self.candidate &= _valid_stream(*(self.inlets[port, name] for name in FIELDS))


def _valid_stream(m_dot, T, p):
    """Return the rows for which ``Stream(m_dot, T, p)`` is valid: finite, ``T > 0``, ``p >= 0``."""
    return np.isfinite(m_dot) & np.isfinite(T) & (T > 0) & np.isfinite(p) & (p >= 0)


def _output_names(graph):
    """Return the output names in recording order; the items of a list are one name."""
    names = {}
    for key in graph.outputs:
        if key.startswith("outputs."):
            names[_vector_base(graph, key.removeprefix("outputs."))] = None
    return list(names)


def _vector_base(graph, name):
    """Return the name of the list an item ``name[index]`` belongs to, else ``name``."""
    base = name.rpartition("[")[0]
    return base if f"outputs.{base}" in graph.vectors else name


def _graph_values(graph, module, outputs, failed, size):
    """Return the typed value arrays by key and the mask of the rows that can be claimed."""
    arrays = {key: _array(outputs[key], size) for key in graph.outputs}
    claimed = np.ones(size, dtype=bool) if failed is None else ~np.broadcast_to(failed, (size,))
    nullable = {name for name, declaration in module._outputs.items() if declaration.accepts_none()}
    values = {}
    for name in _output_names(graph):
        array, finite = _output_array(graph, arrays, name)
        declaration = module._outputs[name]
        values["outputs", name] = _typed(array, declaration)
        claimed &= finite | (name in nullable) & _nan_only(array)
    for port in module._outlets:
        for name in FIELDS:
            array = arrays[f"outlets.{port}.{name}"]
            values["outlets", port, name] = array
            claimed &= np.isfinite(array)
    return values, claimed


def _output_array(graph, arrays, name):
    """Return the array of one output (rows, or rows by items for a list) and its finiteness."""
    if f"outputs.{name}" in graph.vectors:
        count = graph.vectors[f"outputs.{name}"]
        array = np.stack([arrays[f"outputs.{name}[{index}]"] for index in range(count)], axis=1)
        return array, np.isfinite(array).all(axis=1)
    array = arrays[f"outputs.{name}"]
    return array, np.isfinite(array)


def _nan_only(array):
    """Return the rows whose value is NaN and not infinite, vector rows needing every item."""
    isnan = np.isnan(array.astype(float))
    return isnan if isnan.ndim == 1 else isnan.all(axis=1)


def _array(value, size):
    """Return one graph output as an array over the rows; a literal ``None`` is NaN."""
    array = np.asarray(np.nan if value is None else value)
    return np.broadcast_to(array, (size,))


def _typed(array, declaration):
    """Return ``array`` with the dtype the declared kind has on the plain path."""
    kind = declaration.value_type()
    if kind == "number":
        return array.astype(float)
    if kind == "boolean":
        return array.astype(bool)
    if kind == "integer":
        return array.astype(np.int64)
    return array
