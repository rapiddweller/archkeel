# Native boundary regression correction — issue #542

Base: `5933ffbbfd588ac96e36748de937cb1f6e739655` (Graph + contract version). Grammar remains frozen at `d48e36f623a15734a7569e946646cdeaae030b88` during this correction.

1. Reproduce the Dependency API Target and typed-control failures against actual `7b2a14de58eb18be716c8eadef5c43928ec464a5` and `5933ffbbfd588ac96e36748de937cb1f6e739655`; print real report diagnostics before the test helper asserts exit 0. Identify the actual fixture/owner boundary that changed.
2. Repair only the diagnosed native fixture dependency/scope, keeping independently authored Target declarations and source mutation checks unchanged. No weakened verdicts, allowances or budgets.
3. Verify the layer/report-version intent and unchanged UML UNKNOWN identities against the nominal owner and existing unchanged nested definitions. Diagnose actual repeated logic before selecting a bounded source correction; do not disguise duplication by syntax.
4. Run all affected tests, native source mutations, Ruff, strict mypy, hygiene and strict actual own baseline. Record precise causal evidence and remaining inherited full-suite failures. Freeze a small correction carrier for Root's independent Astra review and targeted propagation.


## Completed fixture/intent correction

The actual pre-Graph/version predecessor `7b2a14de58eb18be716c8eadef5c43928ec464a5` passes all 19 selected controls; actual `5933ffbbfd588ac96e36748de937cb1f6e739655` fails 16, including 13 Dependency cases. [Causal run 38958033454](https://github.com/rapiddweller/archkeel/actions/runs/38958033454) reports `rule_without_subjects` for unrelated `TARGET-CONTRACT-VERSION-BOUNDARY-TYPES`: the bounded Dependency fixture copied every IR boundary rule while materializing only Dependency source. The correction retains the global interface rule and selects boundary rules for the actual Dependency source. Authored Target entities and native mutation assertions are unchanged.

The layer intent now asserts the nominal `ReportSchemaVersion` field and its authored enum owner. The existing render API UNKNOWN remains `UNKNOWN-BOUNDARY-TYPE-POSITION-44758a1d61ff7682`, with the same position and all eight incomplete UML scopes. Closing `RuleVerdict` exposes the existing `result.diagnostics.kind` leaf. The actual runner proves AST equality of `Diagnostic`, `DiagnosticKind` and `RunResult.diagnostics` against the predecessor; counts and limits remain 58 UNKNOWN and 918 unresolved calls.

[Final run 38960198879](https://github.com/rapiddweller/archkeel/actions/runs/38960198879), source `0106b6a4eaac165f86c217bee5d61f454cacc267`: **71 tests pass** across the complete Dependency API, typed-control, layer and protocol-Target modules, including real source mutations under unchanged Targets. The actual bounded-fixture CLI exits 0 with no diagnostics. Ruff checks and formatting pass (463 files), strict mypy passes (139 source files), and all 11 repository hygiene controls pass. No production, Target, policy, receipt, allowance or budget change belongs to this correction.

The separate duplication question is still under diagnosis. [Counterexample run 38959573981](https://github.com/rapiddweller/archkeel/actions/runs/38959573981) preserves the genuine arithmetic-copy positive, but proves the existing 18-node structural shape is identical for both the same enum converter and a different canonical enum converter. The shape algorithm remains unchanged. Before selecting any correction, inspect whether existing resolved Calls facts can conservatively distinguish corresponding call identities; missing or ambiguous evidence must retain the structural candidate. Grammar remains frozen during this review.
