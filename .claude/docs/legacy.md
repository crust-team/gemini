# Legacy bridge

`gemini.utils.legacy` is the only old-format boundary. It is internal: the one public entry is
`gm.plants.convert_legacy(folder)`, and everything else on this page is imported from
`gemini.utils.legacy`.
`read_project(folder)`/`write_project(project, folder)` handle raw diagram and `.param` files
through typed `GeminiProject` models; the in-memory project, including edits to it, is what the
conversion reads. `read_csv`/`write_csv` handle semicolon data and old timestamps
(`%Y-%m-%d %H:%M:%S`, or ISO 8601 when reading). Parsed projects write the same values after
JSON whitespace normalisation, keeping each `.param` file's tag-name order; auxiliary files are
copied byte-for-byte. Malformed or unconvertible files raise `gm.errors.ValidationError`.

`to_plant(project, plant)` fills an existing handwritten plant with converted SI parameters,
dated histories, fluids, bindings and explicit assumptions (`plant.boundary`), and returns it.
Old fields it cannot map are listed in one `GeminiWarning`. `to_dataset(project, frame)` renames
tag columns and converts values to SI; old timestamps are taken as UTC wall time.
`from_plant(plant, template)` writes through an old template without inventing fields.
`results_to_frame(results, project)` maps predicted measured outputs back to old tag units, and
`check_wiring(plant, project)` compares observed stream identities with the old diagram. It runs
one step on a copy of the plant with its assumed root inputs and `tables.TRACE_CONTROLS`, so the
caller's plant is not changed, and returns an empty list when the wiring matches.

`gm.plants.convert_legacy(folder)` returns the format 2 spec of an old project folder: it reads the
folder with `read_project`, fills `DoubletHeatPlant` (`gm.plants.get`) with `to_plant` and writes
`to_spec()`. The folder holds `diagram.json`, one `.param` file per diagram node and any other file
(the data CSV, `well_trajectory.csv`, `plant.conf`), which is read as-is and not converted; the data
CSV is converted with `to_dataset`. On the example project the result equals
`examples/shared/doublet_heat/plant.json` exactly (`tests/unit/modules/plants/
test_legacy_project.py`). The function lives in `modules/plants/legacy_project.py` and imports
`gemini.utils.legacy` inside the function, because `gemini.utils.legacy` sits above `gemini.modules`.

The bridge maps exactly the example project: its ten old nodes (`tables.NODE_PATHS`), a project
folder with exactly one data CSV besides trajectory files, and its data columns and assumptions.
Any other node set is rejected rather than guessed. Type, property, port, tag and old-node path
tables, the deliberately unbound tags with their reasons (`IGNORED_TAGS`) and the property
converters live in `utils/legacy/tables.py`; `utils/legacy/_loader.py` interprets a parsed project
with them. New engine/modules/examples contain no old naming or conversion logic. The bridge
example is the only example that reads old files.

Converted control columns use their owning leaf path. The shared doublet therefore uses
`doublet.reservoir.production_rate`, `doublet.esp.frequency`, and
`injection_pump.pressure_setpoint`, without duplicate plant-level control columns.
