# AD-361 The report payload is columnar and derives from records only

**Status.** Accepted (owner, 2026-11-11). Part of #880 (report v2 data). The renderer is not part of it.

**Decision.**
1. `schema/report-2.0.schema.json` is the contract between the producers of the report v2 payload
   and its readers: the page, and the host that prints the head (`run`, `summary`, `rules`, `gaps`,
   the node 0 rows of `measures`). The payload IS the `Report` frame of the Rust core: WP6 slice 0d
   builds its frame from this schema. The `HostRules` frame of the WP6-0 design is superseded.
2. Tables are columnar: each cell is a row id, a code, a count or an id into one string table.
   -1 means absent. A list per row is a flat array and an end column (`via`, `violation_*`).
3. Inputs: the record sections of `architecture.json`, the contract as recorded there, and the
   Decision of the evaluator: the status, per rule the verdict, the reason code and the undecided
   positions (AD-92), the Target flag, the observation verdict and the diagnostics. The producer
   copies the Decision and decides no verdict.
4. Status rule, checked on every payload: (1) no Target: UNKNOWN; (2) a violation row: FAIL,
   unless the observation is incomplete and a diagnostic `runtime_mismatch`,
   `incomparable_runtime` or `contract_invalid` revokes the proofs; (3) an incomplete observation:
   UNKNOWN; (4) a rule with an undecided position or an UNKNOWN verdict: UNKNOWN; (5) else PASS.
5. Each status other than PASS has a row: FAIL a violation row; no Target an unknowns row of
   source `run`; an incomplete observation a diagnostic or record row; UNKNOWN at least one
   unknowns row or rule row. `rules[].violations` equals the violation rows that cite the rule.
   A rule with verdict FAIL has at least one violation row that cites it; a payload that breaks
   this is refused (lead decision L-23, AD-371).
6. Target and actual: `permissions` holds the decision of `report --only architecture` per pair of
   sibling components (allowed, forbidden, undecided). An edge carries the permission of its pair
   as `target` (declared, forbidden, undeclared). An allowed pair without an import is a component
   edge with zero sites. Every cycle record is a finding; a package cycle that no module cycle
   backs is `context` and `run.not_ranked` counts it.
7. No silent absence. A measured value without budget or baseline names `G-BUDGETS`. A relation
   that the payload does not carry is in `run.not_carried` (calls, references, implements, uses
   type, fields, signatures, code lines, contract lines). `G-CONTRACT-LINES` blocks the edge links
   to the contract; a hub names the gap of its empty declared block (`G-PUBLIC-API`, `G-ROLES`).
8. A budget comes only from an evaluated root rule (`complete_assignment`, `complete_requires`).
9. Canonical bytes: keys in the order of `required`, optional `fields` and `params` after
   `carriers`; no whitespace; UTF-8; a string escapes only `"`, `\` and U+0000 to U+001F, as
   `\b \f \n \r \t` or `\u00xx` with lowercase hex; no Unicode normalisation; the row orders of
   the schema; one trailing newline. `decl` is the first evidence line without leading and
   trailing ASCII spaces and tabs, cut at 72 code points.
10. Versions: the schema accepts every 2.x payload. A code list is only appended within a major
    version and has no maximum. A reader shows a code beyond its own list as unknown, never as
    clean. A removed or renamed field is a new major version.
11. The oracle producer is `archkeel.report.payload`. It imports no other Archkeel package, never
    builds an Observation, never reads `transitive_paths`, calls or references, and fails above
    8 MB. `python -m archkeel.report.payload <architecture.json> --result <result.json>` writes
    `<stem>.report-v2.json`; the current report does not change.

**Problem.** The Rust core must write this payload byte for byte, and the owner rule is that no
UNKNOWN or deviation is folded into a count that reads as clean.

**Rejected.** (a) Rows of objects: twice the bytes. (b) Gap and measure texts in the payload:
duplicated sentences in Rust. (c) Re-derive verdicts from receipts: a second evaluator. (d) A
rule-row-only frame (HostRules): the status was not reproducible from it. (e) Closed maxima per
code list: a 2.1 payload would fail the 2.0 schema.

**Limit.** `architecture.json` records no excluded files (`G-EXCLUDED`) and no contract lines.
Inside components get modules by `exact_modules`, then by the longest package. `trend` is empty
until CI keeps measure points (`G-TREND`). A diagnostic text comes from the host.

**Dual run.** The payload becomes the owned section set `report-v2` of AD-360 in a later PR.

**Tests.** `tests/test_report_schema.py`.
