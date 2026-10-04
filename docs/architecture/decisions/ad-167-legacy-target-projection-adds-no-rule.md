# AD-167 Legacy Target projection adds no rule

Contract 2.1 and 2.2 component and physical declarations use the existing Target
graph producers even when `declarations.uml` is absent.

Core authenticates the contract digest, component metadata, permissions, module
inventories and layout rules. A single `architecture_target` declaration retains
their record IDs and mounted levels. It does not copy their contents or source
facts. `ir.target_records` projects those references into `ArchitectureGraph`;
the result equals the independently compiled contract graph.
Set-like component metadata uses the canonical record order. Sorting does not
change authored contract bytes or their digest.

`architecture_target` is declaration metadata, not a rule. It adds no assessment,
violation or UNKNOWN receipt. Existing rules retain evaluation ownership.
Explicit UML intent keeps its `uml_target` rule and comparison. Authentication
rejects forged descriptors, owner metadata and unexpected Target IDs.

An incomplete inside contract retains the report's existing diagnostic. It cannot
publish a complete Target graph. Reassembly is idempotent.
Protocol fixtures prepare accepted and planned observations through the existing
Core workflow. Lock verification stays strict; a raw adapter result is not the
canonical observation a check verifies.

This step establishes the legacy graph boundary. Global API declarations and
replacement of the legacy browser projections remain open. The language adapter
and process protocol from PR #277 stay unchanged.

Proof: `tests/test_target_graph.py`; `tests/test_uml_evaluation.py`.
