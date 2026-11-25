# Migrate an architecture gate from ArchKeel 4.0.1 to 5.0

This guide is for the architecture gates of EE and CE. It lists the old command or import, the new
command, and the JSON key to read. Each fact is measured on the 5.0 line at commit `7a10dbb27`, or
it is linked to a merged pull request or decision record. Each command in the block
[Commands the guide runs](#commands-the-guide-runs) is run by `tests/test_doc_migration_guide.py`.

## 1. What changes

- The Python engine is gone. The modules `archkeel.analyzer`, `archkeel.check` and `archkeel.ir`
  are not in 5.0 (measured: `importlib.util.find_spec` finds none of them).
- The Rust core decides each run ([AD-432](architecture/decisions/ad-432-the-rust-core-is-the-only-decision-path.md)).
  The command line prints its frame. Read the JSON.
- `check` and `report --input` are refused with exit 2 ([#2020](https://github.com/rapiddweller/archkeel/pull/2020)).
- Exit codes: `0` is PASS. `1` is FAIL, or a baseline that differs. `2` is UNKNOWN, or a gap.
  UNKNOWN never exits 0.

## 2. Old command or import, new command, JSON key

| Old (4.0.1) | New (5.0) | JSON key to read |
|---|---|---|
| `archkeel report --output architecture.json --json` | `archkeel report --json` (prints the frame) | `status`, `exit_code`, `frame` |
| `archkeel report --input architecture.json --only architecture --full --json` | refused. Use `archkeel report --json`. | `frame.rules`, `frame.gaps` |
| `archkeel validate --baseline known-violations.json --json` | the same command | `baseline.state`, `baseline.exit_code` |
| `archkeel validate --write-baseline known-violations.json` | the same command. It writes schema 1.4.0. | file keys `unknowns`, `budgets`, `violations` |
| `archkeel report --output architecture.html` | the same command (HTML is the default format) | none. The page is the output. |
| `archkeel --version` | the same command | none |
| EE `script/architecture`: `archkeel.analyzer.python.collect.PythonProviderCollector`, `archkeel.check.report.run_report`, `archkeel.check.validation.run_validate`, `archkeel.render.html.render_architecture_html` | a subprocess: `archkeel validate --json`, then `archkeel report --output FILE` | `status`, `exit_code` |

Use a subprocess for the gate. Do not import a Python module of ArchKeel. Section 1 gives the reason.

### Old JSON keys of the CE gate

The CE gate of 4.0.1 read these keys of `validation.json` and `completion.json`
(`tests_ce/architecture/completion_gate.py`). The 5.0 key is listed in the second column.

| 4.0.1 key | 5.0 key | Note |
|---|---|---|
| `exit_code` | `exit_code` | Top level of the document. |
| `diagnostics` (list) | `frame.gaps`, each with `kind`, `reason`, `subject` | Each gap has one kind. |
| `measurements.scalars` | `frame.measures` | Keys of the 5.0 counters: `calls_unresolved`, `typing_positions`, `untyped_private_accesses`. |
| `architecture_projection.contract_digest` | `frame.contract_digest` | The digest of the contract. |
| `recorded_unknowns` | `baseline.accepted_unknowns` (a count), and the file key `unknowns` (a list) | An accepted UNKNOWN is in the file. |
| `report_filter`, `filtered_violations` | none | `--only` is refused. Read `frame.rules` and `frame.violations`. |

The 5.0 keys above are the keys that the test `tests/test_cli_consumer_frame.py` pins
([#2015](https://github.com/rapiddweller/archkeel/pull/2015)).

## 3. Measured collector

The core measures calls and typing. A run prints these counters in `frame.measures`:
`calls_total`, `calls_resolved`, `calls_partial`, `calls_builtin`, `calls_external`,
`calls_unresolved`, `unresolved_self`, `unresolved_attribute`, `unresolved_name`,
`unresolved_dynamic`, `typing_positions`, `untyped_private_accesses`.

A budget that the run does not measure gives the gap `budget.unmeasured`, exit 2
([AD-1090](architecture/decisions/ad-1090-baseline-1-4-0-compares-the-three-call-and-type-budgets.md)).

## 4. Accepted-unproven list (baseline `unknowns`)

1. Write the file once. Review the diff before you commit it:
   `archkeel validate --write-baseline known-violations.json`.
2. Compare with the file on each run:
   `archkeel validate --baseline known-violations.json --json`.
   The key `baseline.state` reads one of: `written`, `current`, `drift`, `invalid`, `not_compared`, `not_written`.
3. A file of schema 1.0.0 to 1.3.0 accepts no UNKNOWN. The run gives the gap `baseline.older_schema`.
   Write the file again with the command of step 1.

Each entry of `unknowns` has `kind`, `subject`, `reason` and a `count`. There is no line number and no
evidence id, so an unrelated edit does not change an entry.

## 5. Budgets (baseline 1.4.0)

Declare a budget in the contract, under `declarations.measurement_budgets`. Each entry has a `name`
and a `provenance`. The names are `cycle_edges`, `private_crossings`, `typing_positions`,
`calls_unresolved`, `untyped_private_accesses` and `unknown_positions`. The schema is
`schema/architecture-contract-3.22.schema.json`.

The file holds one value for each budget in its `budgets` object. These rows are measured:

| Case | Row in `baseline.new` | State | Exit |
|---|---|---|---|
| The run value is above the file value | `budget.exceeded` | `drift` | 1 |
| The contract declares the budget, and the file has no value | `budget.unknown` | `drift` | 1 |
| The run does not measure the budget | gap `budget.unmeasured` | not measured here | 2 |

A row has the keys `kind`, `subject` (the budget name), `run` and `file`.
A file of schema 1.0.0 to 1.3.0 gives the gap `baseline.budget_of_older_schema` for each of its three
call and type budgets. Write the file again
([AD-1090](architecture/decisions/ad-1090-baseline-1-4-0-compares-the-three-call-and-type-budgets.md)).

## 6. HTML report

`archkeel report --output architecture.html` writes one HTML page. It prints one line. The exit code
is the exit code of the run: 2 when UNKNOWN stays open. Without `--output`, no file is written.
Use `--format json` with `--output` to write the JSON frame to a file.

## 7. Steps for the CE gate

1. Run `archkeel validate --write-baseline known-violations.json`. Review the diff.
2. Replace each `report --input ... --only architecture --full` line with `archkeel report --json`.
3. Replace each `report --output ... --json` line with `archkeel report --json`, or with
   `archkeel report --output architecture.html` for the page.
4. Read the keys of section 2 in the gate script.

## Commands the guide runs

The test runs each line of the next block in a new fixture folder, in the order of the lines. The
comment is the exit code that the line must give.

```migration-check
archkeel --version                                          # exit 0
archkeel validate --json                                    # exit 2
archkeel validate --write-baseline known-violations.json    # exit 2
archkeel validate --baseline known-violations.json --json   # exit 2
archkeel report --json                                      # exit 2
archkeel report --output architecture.html                  # exit 2
archkeel report --output architecture.json --format json    # exit 2
archkeel report --input architecture.json --only architecture --full --json  # exit 2
```
