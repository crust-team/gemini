# Legacy bridge

`gemini.core.legacy` is the only old-format boundary and is publicly available as `gm.legacy`.
`read_project`/`write_project` handle raw diagram and `.param` files through typed
`GeminiProject` models. `read_csv`/`write_csv` handle semicolon data and old timestamps. Parsed
projects write the same values after JSON whitespace normalisation; auxiliary files are copied
byte-for-byte.

`to_plant(project, plant, nodes=None)` fills an existing handwritten plant with converted SI
parameters, dated histories, fluids, bindings, and explicit assumptions. `to_dataset` renames
tag columns and converts values to SI. `from_plant` writes through an old template without
inventing fields. `results_to_frame` maps predicted measured outputs back to old tag units, and
`check_wiring` compares observed stream identities with the old diagram.

Type, property, port, tag, and old-node path tables live in `core/legacy/tables.py` and the
private loader. New engine/modules/examples contain no old naming or conversion logic. The
bridge example is the only example that reads old files.

Converted control columns use their owning leaf path. The shared doublet therefore uses
`doublet.reservoir.production_rate`, `doublet.esp.frequency`, and
`injection_pump.pressure_setpoint`, without duplicate plant-level control columns.
