# Frozen inputs

Data that tests read as input. No test compares the output of a collector with these files.

- `typescript/*.json.gz`: replies of the TypeScript collector (protocol 3.0.0). Tests of the store, facts,
  model, eval, report and core decode them as realistic input, and two tests walk the folder.
- `typescript/validation.json`: the validation table that these replies carry (AD-688). The same tests read it.
  A new table does not change this file: the old replies keep their old table, so the consumers keep
  reading an older version.
- `typescript/sources/`: small TypeScript projects. `tests/test_collector_native_ts_resolution.py`
  checks the edges that TypeScript defines for them (AD-1263).
- `mounted-receipt/interface-plants.json`: planted mounted-receipt cases for `test_cli_core_interface_receipt.py`.

The whole-reply equality with a recording of an earlier collector (AD-343) is deleted (AD-1263).
