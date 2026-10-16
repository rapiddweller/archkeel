# Pairwise call evidence for declared SPOT owners — issue #542

Base: `5d38b66ade5ce0fa4c3ce2f2523712b7454aa987` (product source exactly `5933ffbbfd588ac96e36748de937cb1f6e739655`). Grammar remains frozen.

The structural shape deliberately drops names and literal values. Five enum normalizers therefore share shape `59e615828c9fc471` (18 nodes), although their existing resolved call targets name different canonical enum declarations. This is evidence for refining an advisory review candidate, not proof about runtime behavior or constructor return types.

1. Preserve Source shape production, hashes, historical facts, SPOT owners and thresholds unchanged. Read only existing observation call records.
2. Add native RED controls before production changes: the same converter and an import alias remain candidates; different canonical owners do not; genuine arithmetic remains a candidate; missing, ambiguous, truncated or incomplete call evidence preserves the original candidate; multiple inside functions choose the first still-compatible function. Remove different records on both sides with the same reduced per-scope count to exercise the global collection completeness check.
3. In IR only, index calls by exact source definition identity, require unique sortable evidence positions and fully resolved single untruncated targets, and compare equally sized call sequences pairwise. Do not refine incomplete observations or record counts. Reuse the existing nominal resolution owner; no new resolver, type-result proof, whitelist, cast or normalization framework.
4. Run the complete duplication tests, strict own report and unchanged native ratchets. Compare actual unresolved/partially-resolved call identities and boundary UNKNOWN IDs to the actual predecessor. Run Ruff, strict mypy and hygiene. No allowances or budget increases.
5. Freeze the small carrier and record exact evidence for independent final Astra review. No grammar expansion in this carrier.

## Prior feasibility evidence

[Read-only run 38961039567](https://github.com/rapiddweller/archkeel/actions/runs/38961039567), unchanged product `5933`: all five normalizers have exactly two resolved single-target, nontruncated call records, exact source-definition IDs and line/column evidence. The setter target is identical, while the enum callee identity differs. Constructor-result status remains partially resolved and is not used to justify the refinement.

## Completed native RED / GREEN evidence

- [Initial RED 38962138500](https://github.com/rapiddweller/archkeel/actions/runs/38962138500), job 117179569006: **3 failed, 16 passed**. The distinct converter was wrongly named as copied logic, the first inside function was selected blindly, and the own repository exposed four mechanically identical normalizers. Genuine arithmetic, the same converter/import alias and the conservative missing/ambiguous controls already passed.
- [Caller-metadata RED 38963442861](https://github.com/rapiddweller/archkeel/actions/runs/38963442861), job 117183952539: missing bilateral `source_scope` failed; missing `source_definition_id` already preserved the candidate. The correction is a global fallback on absent caller-scope metadata, not reverse evidence matching.
- Independent Astra review exposed nested body scopes: [RED 38965015443](https://github.com/rapiddweller/archkeel/actions/runs/38965015443), job 117189221271: **all three real-scanner cases failed** (comprehension, lambda and nested function). Their inner unknown calls had real child scopes; the outer resolved enum calls could wrongly remove the candidate. The five-line correction records actual scopes and retains the original candidate whenever a function has calls under any child scope, using the existing `in_scope` operation.
- The first strict native run found one additional unresolved call caused by reusing `rows` as both typed accumulator and iteration binding. Naming the accumulator `bucket` makes the two responsibilities explicit and improves that one call to PARTIAL without changing observer authority.

[Final run 38965241454](https://github.com/rapiddweller/archkeel/actions/runs/38965241454), production source `cb4f197d20c178d5c42abffc869e16b0e320cb49`:

- Job 117189985789: **24 native behavior tests pass**, including arithmetic, same/aliased converter, distinct owner, multiple inside functions, bilateral missing records/metadata, and all three nested scopes.
- Job 117189985731: Ruff formatting/checks pass (464 files), strict mypy passes (139 source files), all 11 hygiene tests pass.
- Job 117189985404: actual predecessor and final reports compare **no added, removed or changed boundary type UNKNOWN IDs/records**, **no new unresolved call identities**, and equal shapes/node counts for **1,950 unchanged-source functions**. Strict own validation exits **0**, with no failures/diagnostics: **918 unresolved, 58 UNKNOWN, 52 typing positions, 0 violations**. Budgets and policy remain unchanged.

## Explicit limits and cost

The actual PARTIAL inventory grows **2,471 → 2,484**: `_call_target:record.data.get` ×4; `_resolved_calls:observation.records` ×2, `symbol.data.get` ×1, `record.data.get` ×2, `bucket.append` ×1 and `grouped.items` ×1; `_repetitions:calls.get` ×2. These are new metadata/index operations whose receivers the existing observer conservatively leaves partially resolved. They remain fully visible in the final log. No wrapper, alias, observer extension or allowance hides them; no zero-PARTIAL or runtime-type claim is made.

Against the actual predecessor, production is confined to `ir/duplication.py`: **+120/-12 (net 108 lines)**. Three private helpers decode one canonical resolution value, index conservatively validated existing records and compare complete call sequences. Most added lines reject incomplete or ambiguous evidence; there is no new class, resolver, type-result framework, constructor whitelist or schema vocabulary. The 317 test lines build real source fixtures and exercise 21 new behavior controls, rather than committing historical JSON payloads.

Source producer, wire/schema code, shape algorithm, SPOT declarations/thresholds, authored Targets, receipts and budgets are unchanged. Existing profile-owned symbol classification still uses the canonical `FUNCTION_KINDS` owner, as the original shape reader does. This correction does not claim a whole-module string-control migration or expand the paused contract grammar scope.

The frozen product blob for `src/archkeel/ir/duplication.py` is `3d0c969c691727310fd0c88c82aef18daea5cb71`; subsequent evidence-only plan updates leave it unchanged. Ready for final independent Astra review and Root's targeted integration.
