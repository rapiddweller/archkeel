# Execution ledger — typed component contract

User instruction: address #540–#542, independent final Astra review, then merge.

## Responsibilities and choices

- Pure `ir.dependency` owns selector vocabulary and matching. Codecs convert raw protocol values; Core owns verdicts; reports prepare and consume shared selection.
- Frozen named selections retain typed compatibility iteration. Legacy model ownership aliases and helper signatures remain compatible.
- Nominal `DependencyOwner(identity, modules)` uses the shared `ModuleSelection`, rather than another package/exact representation. One model adapter preserves legacy tuple order and duplicates. Identity is an opaque caller key.
- Native observation could not prove the former generic alias at two new API positions. A broader compiler alias-proof experiment was rejected after independent Astra found an unproven namespace-rebinding assumption. No analyzer experiment is included. The actual API now uses nominal composition, and both positions are proven in fresh repository observation. Baseline and budgets are unchanged.
- Remote isolated branches and hosted tests replace local worktrees because the execution environment cannot fork. Product PRs contain no temporary verification workflows.
- The independent Target fixes intent, never copies observation. Missing method evidence remains UNKNOWN. The string policy guards the complete migrated module without claiming all 1,662 repository syntax observations are defects or migrated.

## Separate changes and evidence

| Issue | PR / exact reviewed head | Verification |
| --- | --- | --- |
| #540 | #543 / 1202e35361e68dea6bf01d6a3d94875c648a9899 | RED selector regression; nominal RED 38926327471; 299 focused tests, mypy, lint, hygiene and native baseline GREEN 38926585338. Independent Astra approved. |
| #541 | #545 / f2c81208518c7c18b295bd617258b800c26714be | 38 independent declarations preserve 244 earlier declarations. Eight native tests, fixed-contract source mutations and fresh self-observation, format, mypy and actual baseline GREEN 38927490279. Independent Astra approved. |
| #542 | #546 / a82fe0ee484e0b84f28159eed5b8cf5272767ea9 | Existing native analyzer/evaluator guard. Equality, membership, match and Final-string negative controls; enums, name data and observed codec wire controls. Earlier native RED/GREEN 38920544087/38920907662. Independent Astra approved. |

Both exact v2 amendments pass native validation in run 38927057989.
Unchanged own measurements: 65 unknown positions, 919 unresolved calls, zero violations.

## Remaining gates

Required PR CI 38927682241 / 38927795971 / 38927921444 and combined clean-tree
full suite/native validation 38928014179 are running. Fresh independent holistic
Astra review is running. Merge in dependency order only after green gates,
refresh later branch ancestry against Main with unchanged trees, and verify issue closure.

A separately created issue #544 appeared during execution. Read-only current-Main
analysis is in progress; it is not part of the already scoped three-PR review.
