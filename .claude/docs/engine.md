# Engine

`Engine.simulate(plant, dataset, clock)` evaluates handwritten plant wiring from root-bound
assumptions. `Engine.replay(plant, dataset, clock=None, start=None, end=None, only=None)` evaluates
equipment twins on measured boundaries. `Engine.live(plant, dataset, checkpoint, step=None,
now=None, sink=None)` evaluates only newly supplied timestamps. All calls are finite; scheduling,
sleeping, and fetching new data belong to the caller.

| PyTorch | GEMINI |
| --- | --- |
| `nn.Module` | plant `Module` owning design and bindings |
| `TensorDataset` | in-memory `Dataset` |
| sampler/data loader | `Loader` aligned to engine `Clock` |
| inference/callback loop | one private `Engine._run` |
| Lightning checkpoint | `save_checkpoint`, `load_checkpoint`, `resume` |
| optimizer | `optim.calibrate` calling `Engine.replay` |

`Clock.days`, `year`, and `range` create fixed schedules; `from_data` uses observations or a
regular grid. Durations accept timedeltas and strings such as `15min`. `dt(t)` returns seconds
to the next tick and a declared/median terminal interval.

One binding plan is compiled per run. Simulation validates every leaf control/boundary path
before the first step, applies each step's values with `plant.set_inputs`, then calls the plant
with root inlets only. Replay applies each bound module's controls and boundaries before calling
it with only measured inlets. Replay also applies dated parameters at each transition, converts
raw units at the boundary, and skips only the module missing a required observation.
State bound to a sensor is authoritative for that tick; otherwise `module.step` integrates the
previous state. Callback order is run-start, step-start, committed step-end, run-end; errors see
a checkpoint-consistent boundary.

## Checkpoints

The version-1 JSON manifest stores the importable plant class, `plant.to_dict()`, module states,
finite clock, completed position, original dataset fingerprint, selected paths, error policy,
and sibling filenames. Results and unfinished replay/simulation rows are written first, then the
manifest is atomically replaced. Remaining rows use JSON-encoded CSV cells to preserve exact
float bits. A checkpoint never depends on the file or service that originally supplied data.

Live checkpoints intentionally store no input rows: each external call supplies its new data.
Rows at or before the committed watermark are ignored; repeated/overlapping calls therefore
process each tick once. The checkpoint commits before an optional sink, so sinks should upsert by
timestamp. There is no distributed transaction with an external sink.
