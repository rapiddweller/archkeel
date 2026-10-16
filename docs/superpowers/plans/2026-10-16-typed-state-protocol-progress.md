# SDD ledger — plan: docs/superpowers/plans/2026-10-16-typed-state-protocol.md

Pre-flight: one task; shared contract/Makefile updates are supplied to the parent for sequential integration.
Ruling: Remote isolated branch and hosted Actions replace local worktree/scripts because executor cannot fork; no production behavior depends on this adaptation.
Ruling: Keep the existing public state_facts module scope; add owned enum types without creating a parallel API facade. Private codec event tag remains internal.
Task 1 RED: run 38930727279, 9 failed and 40 passed. Nominal type/value assertions, absent authored Target and native guards failed as expected.
Task 1 in progress: implement nominal controls and enum parsing, then verify the actual native own budget.

Task 1 targeted verification complete: 8916d144c4c17fa6d6fee60250d834679d8f7db9, hosted run 38931522890. 115 native/wire/state/collection tests and 11 hygiene checks passed; Ruff clean and mypy clean across 138 source files. Native own validation exit 0, no diagnostics/failures, unknown_positions 65, calls_unresolved 919 and violations 0.
Ruling: The former dependency-only codec test now explicitly checks scope noninterference, not a permanent parser exception; expanded #542 migration stages are pending until each owner is migrated. Cost if wrong: documentation could overstate protected scope, so the state codec has separate native negative controls.
Normal v2 amendment binds policy b56f35345d71344674517d21bbc238172dfea8936252f37df9861827351c5c50 to c15e68a4c5519591dc9e0af4d5c38495ac3f57397ead5a7bc61021af875a04a7 without changing baseline c7345d5fbcfd8083fe3a618d23a806dea1eee1c1083aa3e163d59b5e260fa2ed.
Pending parent integration: full combined suite, fresh independent Astra review and required PR CI before merge. No claim of completed repository-wide #542 migration.
