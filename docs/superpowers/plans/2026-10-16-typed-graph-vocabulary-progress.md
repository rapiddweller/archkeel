# SDD ledger — plan: docs/superpowers/plans/2026-10-16-typed-graph-vocabulary.md

Pre-flight: graph source depends on collector-owned Language and member/role enums; shared contract arrays must preserve the independent State slice.
Ruling: Keep graph control types in the existing architecture_graph owner; identical model.RuleVerdict remains its alias, while completion/comparability/declaration domains stay separate. Cost if wrong: consumers could conflate proof states; type identity and wire controls guard this distinction.
Ruling: Valid legacy graph constructor strings normalize in frozen post-init hooks; actual producers and codec decisions use enums. Cost if wrong: old callers could behave differently, covered by existing graph regressions and direct-construction controls.
Ruling: Guard only genuinely migrated whole modules. Unrelated raw source-profile and evidence-record grammar remains pending, not exempt. Cost if wrong: scope claims could hide residual control, so documentation lists unprotected adapters explicitly.
Task 1 RED: run38933772715,31 failed/3 passed; nominal API, parser conversion, fixed Target and guards were absent while historical schema controls passed.
Task 1 implementation in progress: graph owner, codec, source/Target builders and UML comparison updated; compiler/native verification follows on exact collector predecessor.
