# Execution ledger — plan: docs/superpowers/plans/2026-10-16-typed-component-contract.md

User instruction: implement #540–#542, independent final Astra review, then merge.

## Dependency and consistency check

| Task/interface | Produces / consumes | Decision |
| --- | --- | --- |
| 1 → 2 | Shared selector enums, fields and signatures / authored Target | Stable API; Target is written independently, never copied from observed records. |
| 1 → 3 | Migrated dependency policy / source-scoped native construct guard | Guard the complete new policy module, without broad legacy exemptions. |
| 2 → 3 | Native source fixture and typed boundary / guard mutations | Reuse one fixture; keep production types, contract intent and syntax controls distinct. |
| Task 1 | Compatibility versus named immutable results | Preserve unpacking through typed iteration. |
| Task 2 | Native proof versus incomplete member inventory | Keep Target member scopes open; missing proof stays UNKNOWN. |
| Task 3 | Protected scope versus repository syntax count | Document the exact guarantee and remaining vocabularies; do not call 1,662 observations defects. |

## Implementation decisions

Ruling: `ir.dependency` owns pure dependency vocabulary and selection rather than
adding more behavior to `ir.model`. The existing model remains a compatibility
facade. This makes a real component API boundary enforceable; the cost is one
small module and explicit named ports.

Ruling: use frozen dataclasses with named fields and typed compatibility iteration.
This preserves existing tuple unpacking while keeping the returned source/target
selection clear. The cost is compatibility iteration methods; no parallel matcher
or runtime conversion layer is introduced.

Ruling: isolated remote GitHub branches and hosted tests replace local worktrees.
The execution environment cannot fork reliably. Product PRs exclude temporary
verification workflows; hosted exact-head required checks remain merge gates.

## Task 1: shared dependency selection (#540)

- PR https://github.com/rapiddweller/archkeel/pull/543
- Head 0e8299ebcfe84e3b40db3471f49f9a7998aa6c1d, base 63437df6734275850838ba1026b276c2f930bf2f.
- RED https://github.com/rapiddweller/archkeel/actions/runs/38916663618: 15 failed / 34 passed, including the real-label discrepancy.
- GREEN https://github.com/rapiddweller/archkeel/actions/runs/38919941195: 271 focused tests, mypy, lint, hygiene and native baseline.
- Standard digest-bound policy amendment https://github.com/rapiddweller/archkeel/actions/runs/38920080238 passed, unchanged baseline.
- Fresh independent Astra review approved all 21 files at the exact PR head; required CI pending.

## Task 2: intended API contract (#541)

- Independent 34-entity Target, narrow boundary_types and real source mutation controls implemented.
- Native controls reject field/parameter widening, untyped selection and property results, and undeclared helper import; missing method proof stays UNKNOWN.
- Expanded regressions passed; two full-repository alias proof UNKNOWN positions under investigation. No budget increase or suppression.
- Individual final Astra review not dispatched until that finding is resolved.

## Task 3: typed control policy (#542)

- RED https://github.com/rapiddweller/archkeel/actions/runs/38920544087 confirms all eight missing-policy controls fail.
- GREEN https://github.com/rapiddweller/archkeel/actions/runs/38920907662: 15 native guard/API controls pass.
- Literal equality, membership, match and Final-string disguises each produce trace-valid violations.
- Enums and module-name data pass; codec wire comparisons remain observed outside protected policy.
- Full own observation proves guard PASS and no string control in the protected module.
- Native guard reuses the existing analyzer/evaluator; no new lint engine or blanket exemption.

## Outstanding gates

Resolve the two alias proof UNKNOWN positions, create separate final #541/#542 PRs,
run required CI and a combined full suite, obtain fresh individual and holistic
Astra review, then merge in dependency order and verify issue closure.
