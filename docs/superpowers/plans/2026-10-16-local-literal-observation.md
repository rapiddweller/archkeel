# Local literal observation: bounded extension of issue #542

The independent CLI mutation `flag = "--json"; return flag in value` exposes a documented coverage limit of the existing observer, rather than a regression of its module-only scalar support.

## Responsibility

Extend syntax classification only. Reuse the compiler lexical owner and its existing binding sites. A supported name must have exactly one direct literal str/bytes assignment at the top level of the same function, before its use. Parameters, reassignment, conditional writes, use before assignment, closures, global/nonlocal writes, destructuring and computed values remain unproved. This adds no call/type/namespace authority and no general value propagation.

## Sequence and gates

1. Commit this plan and native actual-source positive/negative controls; capture expected RED.
2. Add one small predicate in the existing construct observer; no resolver or public API change.
3. Run controls, existing observer/binding regressions, Ruff, mypy and own native contract. Preserve all ceilings and report actual positions.
4. Replay the independent CLI mutation, independent final Astra review, required CI and full integration regression before merging.

No raw-data serialization changes, new allowance, historical JSON fixture or duplicated vocabulary.

## Verification

Native RED: run38947529056,8 expected failures and10 conservative accepted controls. GREEN on production56236a2: run38948768215/job117134521927,485 tests, Ruff and strict mypy138, exact predecessor validation againstff4 exit0 with918 unresolved/52 typing/58 UNKNOWN/0violations. No baseline or policy changed. The independent CLI permanent mutation is replayed by its author. Final inherited Wire browser assertions were verified in Chromium run38949400359 (3cases); only that test and documentation change after the GREEN production source.
