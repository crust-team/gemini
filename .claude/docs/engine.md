# Engine

`Engine.simulate(plant, dataset, clock)` calls the handwritten plant with assumed root-bound
inputs. `Engine.replay(plant, dataset, clock=None, start=None, end=None, only=None)` evaluates
each selected equipment module on its own measured boundary. `Engine.live(plant, dataset,
checkpoint, step=None, now=None, sink=None)` evaluates the same measured twins only for new
available ticks. Calls always finish: there is no infinite loop, scheduler or sleep in the engine.
Celery or another external scheduler decides when to call live again.

| PyTorch concept | GEMINI responsibility |
| --- | --- |
| Model / nn.Module | Plant Module owning bindings and dated parameters |
| Dataset | Raw time-indexed source and unit metadata |
| Sampler / DataLoader | Chunked Loader aligning samples to clock ticks |
| Loop time axis | Engine-owned Clock |
| Inference and callbacks | Shared finite Engine loop |
| Lightning checkpoint | Engine save/load/resume |
| Training and optimizer | optim.calibrate calling public Engine.replay |

One private `_run` loop owns sampling, callback ordering, state, error policy, results and the
last completed timestamp. A binding plan resolves modules, unit metadata and dated transitions once per run. Historical
snapshot lists and bindings are fixed during a run; direct parameter updates remain available
as explicit overrides. Restart a run to change its historical schedule or bindings.
`step.py` contains measured-boundary and chained evaluations; files are split by responsibility,
not by mode. Fluid properties already use a cached constant-property model and immutable values.

`Clock.days/year` describe complete local calendar periods; UTC conversion retains 23/25-hour
DST days. `Clock.range` has inclusive bounds. Steps accept timedeltas or strings such as `15min`
and `1h`. `Clock.from_data` uses actual observations unless a regular step is specified. `dt(t)`
is the interval to the next tick; the terminal interval is the specified or median step.
`after(t)` preserves the terminal duration. Live clocks are finite `(position, now]` schedules
anchored to source start; live never extrapolates beyond the latest available observation.

Stateful measured twins use sensor-bound state as the state supplied to `module.step`; the
measured state remains authoritative for that tick. Without state bindings, the returned state
is integrated and retained. Simulation calls the plant's explicit stepping schedule when any
module is stateful. State must be JSON-compatible; custom typed-state restoration belongs to
its module's step contract. Custom plant classes must implement their own child state schedule.

Callbacks run in registration order: run-start, step-start, committed step-end, run-end.
`on_error` observes a checkpoint-consistent boundary. KeyboardInterrupt/SystemExit-like
interruptions propagate even under `on_error="record"`; ordinary model errors may be recorded
per module while other twins continue. `EventLog` records JSON lines and supports arbitrary
agent prompt/answer/token payloads. `Progress` logs every N steps; `AlarmCollector` collects
alarms; `AutoCheckpoint(path, every=100)` or `every="1h"` saves at completed boundaries.
See [12_checkpoint_resume.py](../../examples/12_checkpoint_resume.py).

## Checkpoints

`engine.save_checkpoint(path)` works before a run after assigning `engine.plant`, from callbacks
between steps, and after completion. A mid-equipment hook cannot save a partial step. The JSON
manifest contains version 1, full plant design, module states, exact finite clock, last completed
tick, dataset descriptor, result-file reference, creation time, selected modules and error policy.
No executable objects or credentials are pickled. `Engine.load_checkpoint(path)` returns a fresh
engine with a public `plant`; `resume()` appends strictly subsequent ticks. An exhausted run
returns its stored results unchanged.

Results use an immutable sibling generation, `<checkpoint>.results.<generation>.parquet|csv`,
plus JSON integration metadata. These files are written and flushed before an atomic manifest
rename. The previous generation is removed only after successful publication. Generation names
are deliberate: replacing a fixed result filename first could pair new results with an old
manifest after a crash. A failed publication may leave an unreferenced generation, which may be
removed manually. This guarantees coherent files after interrupted writes, not concurrent writers
to one checkpoint or protection against disk corruption.

`live(checkpoint=...)` restores existing live state, runs only new available ticks, and checkpoints
at completion. Its return value contains just new rows; `engine.results` and the saved checkpoint
contain cumulative results. A repeated `now` produces zero rows. The checkpoint commits before
optional sink delivery; use an idempotent timestamp-keyed sink. There is no distributed exactly-once
transaction with external sinks, and late-arriving samples at/before the committed watermark are
not reprocessed. To backfill late data, explicitly replay that window.
