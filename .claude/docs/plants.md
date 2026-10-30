# Building plants

A plant can be built three ways, and there is one representation. A built plant is a normal
composite `Module`: `describe()`, the automatic output sums, `gm.simulate`, `gm.replay` and
`gm.live` work on it unchanged, on every backend, because its `forward` runs the modules in
connection order and is traced like any other module. A plant has no run method of its own: run
it with `results = gm.simulate(plant, profile)`. How it is computed is in
[native-engine.md](native-engine.md#14-the-plant-builder-and-the-plant-spec).

## Level 1: the builder

```python
import gemini as gm

plant = gm.Plant("Doublet")
plant.add("InjectionWell", name="injector")
plant.add("InjectionReservoir", name="sink")
plant.add("ProductionReservoir", name="reservoir")
plant.add("ProductionWell", name="well")
plant.add("ESP", name="esp")
plant.add("ProductionWell", name="riser")
plant.connect("injector", "sink")
plant.connect("reservoir", "well")
plant.connect("well", "esp")
plant.connect("esp", "riser")
plant.connect("return_in", "injector.wellhead")
plant.connect("riser.wellhead", "supply_out")
print(plant.summary())
print(plant.validate())
```

`add(kind, name=None, params=None)` takes a registry name or a class and one dict of parameters,
the dict `set_params` takes: unit strings accepted, dotted names for a composite
(`params={"reservoir.temperature": "87 degC"}`). `connect`
takes a handle, `"path.port"` or a module path. A module path picks the only free port of a fitting
stream type; a port without a stream type fits anything. If several pairs fit, a `ValidationError`
with code `ambiguous_port` lists them. A bare word that names no module is a plant port, as in
`return_in` above. Only `connect` wires modules; there is no call syntax.

## Level 2: the spec

The same plant as JSON. This is the stored plant file, the input of geomind's `build_plant`
(`gm.plants.spec_schema()` is its schema), and what the backend stores unchanged.

```json
{"format": 2, "name": "Doublet",
 "modules": {"reservoir": {"type": "ProductionReservoir", "params": {}},
             "well": {"type": "ProductionWell", "params": {}},
             "esp": {"type": "ESP", "params": {}},
             "riser": {"type": "ProductionWell", "params": {}},
             "injector": {"type": "InjectionWell", "params": {}},
             "sink": {"type": "InjectionReservoir", "params": {}}},
 "connections": [{"source": "injector.bottom", "target": "sink.sandface"},
                 {"source": "reservoir.sandface", "target": "well.bottom"},
                 {"source": "well.wellhead", "target": "esp.suction"},
                 {"source": "esp.discharge", "target": "riser.bottom"}],
 "inlets": {"return_in": "injector.wellhead"},
 "outlets": {"supply_out": "riser.wellhead"},
 "bindings": {}, "param_history": {}}
```

```python
problems = gm.plants.validate(spec)   # every problem at once, paths such as connections[1].target
plant = gm.plants.from_spec(spec)
assert plant.to_spec() == spec
```

| Key | Always | Meaning |
| --- | --- | --- |
| `format` | yes | 2 |
| `name` | yes | plant name; `module.name` is its snake case |
| `modules` | yes | `{id: {type, params}}`; a group is `{type: "ModuleDict", modules: {...}}` |
| `connections` | yes | `[{source, target, kind?}]`, ends are `"path.port"` |
| `bindings` | yes | `{path: {name: column}}`, flat; see [bindings](#parameters-by-date-and-bindings) |
| `param_history` | yes | `{path: [{valid_from, params}]}`; one undated entry is the same as `params` and is not written |
| `inlets`, `outlets` | no | `{plant port: "path.port"}` |
| `outputs` | no | `{name: {"of": "path.output", "field"?}, {"sum": name} or {"ratio": [a, b]}}` |
| `fluids`, `boundary` | no | `{path: {...}}`, the fluid and the stored assumptions of a module |
| `type`, `params` | no | root of a handwritten module: its registry name and flat dotted values |

- `type` is a registry name. It may name a registered plant, whose parameters are then dotted
  (`"esp.stage_count"`), so templates can contain sub-plants.
- `ModuleDict` and `ModuleList` are groups: they hold children and have no wiring of their own.
  Connections reach through a group (`filters.hot.outlet`) but never into a plant child:
  `doublet.supply_out` is right, `doublet.esp.discharge` is an error.
- An inlet has one source and an outlet feeds one inlet (`port_in_use`). Splitting and mixing are
  `Splitter` and `Mixer`.
- A port no connection uses is a plant port, named in `inlets` / `outlets` or else
  `<path with underscores>_<port>`.
- Without `outputs` a plant has the automatic sum of each energy output its leaves declare.
- The order of connections sets the order of the calls where the wiring leaves it open, which is
  what a composite's float sum depends on. The key order of a dictionary carries no meaning for
  numbers.
- The round trip `to_spec(from_spec(x)) == x` is exact, unit strings included: a stated value stays
  as written while it equals the current one. The backend digests sorted-key JSON.

### Loops

A connection with `"kind": "state"` closes a loop and reads the value of the previous step. A cycle
without one is `loop_without_state`. State connections are valid in the spec, the schema and
validation; **running such a plant raises `NotImplementedYet`** until scan exists, because a first
step has no previous value.

A plant child in a cycle with other modules, with no cycle among the leaves, is opened: its children
are called directly by the parent, as `DoubletHeatPlant` does with its `doublet`, and its own outputs
are not computed.

### Files and migration

`plant.save(path)` and `gm.Plant.load(path)` read and write the spec. `gm.plants.migrate(old)`
converts every older stored format, and `scripts/migrate_plants.py` runs it over files. Loading an
old file without it raises `ValidationError` with code `old_format`, naming `gm.plants.migrate`.

## Level 3: subclassing

`Module` with `forward` is for leaf modules and special cases: see [modules.md](modules.md). The
shipped special cases are those whose forward does more than wiring and cannot become wiring
without changing numbers:

- `HeatingSubstation`, `CoolingSubstation`: a closed building loop solved inside one call by
  `loops.close_loop`, not a previous-step `state` connection.
- `ATESPlant`: the storage's `mode` selects which children are called, and the plant reads the
  storage's start-of-step temperature.
- `NodalDoublet` in `examples/shared/nodal_doublet/`, not registered: each call solves a rate with
  `brentq`.

They are in the registry (`gm.plants.names()`), so a spec can use them as a `type`.

## Registered plants and templates

`gm.plants.names()` lists them, `gm.plants.get(name)` gives a plant without values and
`gm.plants.example(name)` one with real values. Specs live in `gemini/modules/plants/specs/`,
example values in `specs/examples/` and templates in `plants/templates/`; a new
`specs/<Name>.json` is registered by its file name.

`gm.plants.from_template(name, parameters)` fills a template:

- `MultiWellPlant` and `DistrictNetwork` take sizes: `{"producers": 3, "injectors": 2}`,
  `{"consumers": 3, "service": "cooling"}`.
- `heating_cooling` is the integrated heating-and-cooling plant, with sizes as parameters.
  `"<unit>.enabled": false` removes an optional unit and closes the gap, when the spec is filled,
  so the result is a plain spec with no switch at run time. Its presets are
  `heating_only`, `heating_absorption_cooling`, `heating_heat_pump_compression_cooling` and
  `heating_full_cooling`. Hot and cold storage wait for scan: a tank in one chain is a loop.

A template file has `title`, `description`, `purpose`, `parameters`, `optional`, and `spec` or
`generator`.

## Parameters by date and bindings

```python
plant.set_params("doublet.esp", {"stage_count": 14}, valid_from="2025-01-01")
plant.params_at("doublet.esp", time="2024-06-01")
plant.param_history("doublet.esp")
plant.bindable("doublet.esp")
plant.set_bindings("doublet.esp", {"frequency": "esp_hz"})
plant.set_bindings("doublet.esp", {"frequency": {"column": "esp_rpm", "unit": "rpm"}})
plant.set_bindings("doublet.esp", {"suction.p": {"column": "p_in", "unit": "bar"}})
```

`set_bindings(path, bindings)` replaces the bindings of a module. A key is a declaration name: a
control, boundary, measured output or state, which are unique within a module, or `port.field` of
an inlet. A value is a column name, whose unit comes from the run input's metadata or else the
declaration's SI unit, or `{column, unit}`. A name declared twice would raise `ValidationError`
naming the clash; no shipped module has one. The plant file holds the same flat form and reads only
that form: a section such as `controls` is an unknown name. `gm.plants.migrate` converts format 1.
