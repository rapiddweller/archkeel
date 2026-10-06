# AD-205 Class binding proofs use their AST owner

Bind definition-site proofs to the ParsedModule owning the exact AST node.
Qualified names can collide across modules, packages and repeated definitions.
Preserve the selected-node inventory.

Reuse module Global-name and bound-name indexes to avoid unnecessary subtree scans.
Wildcard imports disable absence proof. Keep local UNKNOWN and every validation
boundary; add no cross-run cache. Full-report timing measures observation, evaluation
and rendering; report errors or budget overruns fail.

[Owner proof](../../../tests/test_definition_source_owners.py) and
[reuse proof](../../../tests/test_binding_proof_reuse.py).
[Timing proof](../../../tests/test_report_timing.py).
