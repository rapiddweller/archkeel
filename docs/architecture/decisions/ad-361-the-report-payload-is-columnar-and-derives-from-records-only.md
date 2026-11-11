# AD-361 The report payload is columnar and derives from records only

**Status.** Accepted (owner, 2026-11-11). Part of #880 (report v2 data). The page renderer is not
part of it.

**Decision.**
1. `schema/report-2.0.schema.json` is the one contract between the producers of the report v2
   payload and its readers: the page, and the host that prints the summary from its head (`run`,
   `summary`, `rules`, `gaps` and the node 0 rows of `measures`).
2. The tables are columnar. Each cell is an integer: a row id, a code, a count, or an id into one
   string table that is unique and sorted by UTF-8 bytes. -1 means absent. A code is a position
   in a closed `x-codes` list; a new value is appended. The texts of measures and gaps are
   catalogues in the schema (`x-measures`, `x-gaps`); the payload holds no producer prose.
3. Canonical bytes: keys in the order of `required`, no whitespace, UTF-8, JSON escapes only where
   JSON requires them, the row orders of the schema, one trailing newline. Byte equality is a test.
4. No path record and no reachability pair. `nodes.parent` gives the component tree, the
   `package` column links a module to its package, and the page computes reachability and cycles
   from the direct `edges`.
5. The payload derives from the record sections of `architecture.json`, the contract as recorded
   there (`declarations`, `contract`), and the evaluator verdicts: the declared-rules status, one
   row per rule, and the Target flag. The producer copies each verdict and decides none. This is
   the `HostRules` input of the Rust core (WP6-0, section B).
6. Target and actual are typed rows. A module edge and a component edge carry `target`
   (no_target, declared, undeclared). A `requires` entry without an observed edge is a component
   edge with zero sites. A run without Target (explore, AD-285) has no contract in the payload, so
   each declaration measure is undeclared with `G-NO-CONTRACT`.
7. `run.not_carried` lists the relations that the payload does not carry yet (calls, references,
   implements, uses type, fields, signatures, code lines). The page shows them as "not collected
   yet".
8. A measure has a budget only when an evaluated root rule sets it (`complete_assignment`,
   `complete_requires`), and a verdict only with a budget. An unevaluated rule gives no verdict.
9. The Python oracle producer is `archkeel.report.payload`. It imports no other Archkeel package,
   never builds an Observation, and never reads `transitive_paths`, calls or references. It fails
   above `run.payload_budget.max_bytes` (8 MB) and never truncates in silence. The only cap is
   200 crossings per module edge, with a visible `omitted` count.
10. `python -m archkeel.report.payload <architecture.json> --result <result.json>` writes
    `<stem>.report-v2.json` next to the report. The current report does not change.

**Problem.** The old report re-derives graph views in the browser and reaches 52 MB. The Rust core
must write the same payload as its one `Report` frame, so the payload needs one exact byte form
and one oracle that does not depend on the Python `Observation`.

**Rejected.** (a) Rows of objects: twice the bytes, and key order is one more thing to match.
(b) Gap and measure texts in the payload: the Rust core would duplicate each sentence byte for
byte. (c) Re-derive rule verdicts from evaluator receipts: that is a second evaluator.
(d) A `--report-v2` flag on `archkeel report` now: it changes `cli/`, which the host PRs own.
(e) `measure_defs`, `contract_line` and `contract_ref` of the draft: no source fills them yet.

**Limit.** `G-EXCLUDED`: `architecture.json` does not record excluded files. Components of an
`inside` contract get modules by `exact_modules`, then by the longest package; a tie leaves the
module with the parent. `trend` is empty until CI keeps measure points (`G-TREND`). The payload
does not name its producer, so a byte difference names no side.

**Dual run.** The payload becomes one owned section set, `report-v2`, of the dual-run harness
(AD-360): the Python engine frame gets the bytes of this producer, each oracle keeps their digest
and the head, and `--sections report-v2` compares the bytes. That changes every oracle, so a
separate PR records them again.

**Tests.** `tests/test_report_schema.py`.
