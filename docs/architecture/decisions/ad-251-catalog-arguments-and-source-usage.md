# AD-251: Catalog membership and source reads use canonical declarations

Catalog policy selects source declaration owners instead of copying values into Target contracts. `catalog_argument` binds a selected call's explicit argument to its formal parameter and checks exact string literals against unique parsed enum string values. Enum member expressions resolve through the existing canonical attribute-reference facts. Dynamic values, incomplete call identity, ambiguous declarations and missing catalogs remain UNKNOWN.

`catalog_use` checks each selected enum member, or one named member, for a real value or attribute reference in its declared source scope. Definitions, annotations, comments and docstrings do not count. `TYPE_CHECKING` reads count as syntactic reads. Exact and prefix scopes are explicit. Overlay selectors name separate enum declaration owners; arbitrary literal exceptions and project imports are not supported.

A complete eligible Python source scope with no selected read violates the rule. Missing, empty, partial or unsupported scopes remain UNKNOWN. Known argument violations remain visible with UNKNOWN facts. Receipts include selected catalog owners, call facts, reference facts, the contract and source identities. Runtime use, control-flow reachability, arbitrary constant propagation and dynamic catalog projection are outside this decision.

The focused synthetic tests cover string membership, enum references and no-use counterprobes. Full #613/#617 dependent alias and source-role checks remain pending the parent stack rebase.
