# Issue 617 implementation report

The source-ownership rule has closed `retired` and `confined` selectors for symbols, parameters, owners, canonical value owners, and roles. Python collection reuses canonical references and declaration anchors; it records exact read/write/delete/definition sites, bounded dictionary callable and direct lambda transfers, parameter defaults, and two-term `parameter or value` fallbacks. Unsupported or ambiguous expression forms remain `UNKNOWN`. Default and fallback owners are derived from admitted source declarations, not matched by spelling, and the receipt proof is replayed for saved reports.

Core validates canonical selector identities, declaration and evidence links, complete local definition anchors (including unread conditional locals), annotation/value reference context, and physical module membership for root and mounted scopes. Removed source-role claims invalidate saved receipts. Observation 2.1 remains a frozen historical schema; this branch uses provisional contract 3.8 and observation 2.2 floors, which the parent will reconcile to the integrated stack versions 3.12 and 2.7. Command result 9 keeps its top-level shape and extends the nested observation union.

Verification completed:

- `UV_CACHE_DIR=/workspace/.cache/uv UV_PYTHON_INSTALL_DIR=/workspace/.python make lint` — passed (full configured Ruff format and lint checks).
- `UV_CACHE_DIR=/workspace/.cache/uv UV_PYTHON_INSTALL_DIR=/workspace/.python make typecheck` — passed (mypy, 156 source files).
- `UV_CACHE_DIR=/workspace/.cache/uv UV_PYTHON_INSTALL_DIR=/workspace/.python uv run --locked pytest -q tests/test_source_ownership_policy.py tests/test_source_graph.py tests/test_result_schema.py` — 147 passed. Covers selectors, aliases/shadowing, read/write/delete, exact defaults/fallbacks, missing canonical owners, unknown/unread definitions, annotations including local `AnnAssign`, dictionary/lambda transfers, tampered/stale receipts, saved replay, mounted-scope isolation, schemas, and the result-schema demo matrix.
- `UV_CACHE_DIR=/workspace/.cache/uv UV_PYTHON_INSTALL_DIR=/workspace/.python uv run --locked pytest -q 'tests/test_architecture_demo.py::test_target_hierarchy_demo_reports_declared_targets[target-hierarchy-positive]'` — 1 passed; this verifies the previously failing Atlas target hierarchy path.
- `git diff --check` — passed.

No code-debt or interface-budget allowances were added. The selector is intentionally limited to its explicit expression grammar; unsupported dynamic expressions remain unknown rather than being promoted by textual similarity.
