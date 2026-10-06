# AD-205 Class binding proofs use their AST owner

Definition-site proofs use the ParsedModule owning that exact AST node. A
qualified name can collide between a module, package, or repeated definition.
The existing selected-node inventory remains unchanged.

Each parsed module records its Global names once. A class subtree is walked only
when the queried name can occur in a Global statement in that owning module.
This guard preserves local proof and UNKNOWN; it adds no cross-run cache.
The existing bound-name inventory also proves an absent name without another
statement scan. Wildcard imports disable this absence proof.

A complete self report records wall time; exceeding its measured CI budget fails.
Report errors still fail. The budget measures observation, evaluation, and
rendering together; fact validation remains at every existing boundary.

Proof: `tests/test_definition_source_owners.py`, `tests/test_binding_proof_reuse.py`,
`tests/test_report_timing.py`.

`make report-timing` records a full Self report with a provisional 90 s wall budget.
CI uploads the timing receipt. The first Ubuntu run calibrates it; Mac timings do not.
