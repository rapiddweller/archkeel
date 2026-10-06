# AD-30 A declared owner is worth nothing until something can contradict it

The Class D `repeated logic` claim checks `spot_owners`. Every function and method
symbol carries a body `shape`: an exact hash of AST node types in walk order,
excluding names, literal values and docstrings. A structural twin outside a
knowledge owner is a candidate when another twin sits inside it.

Use exact hashes, accepting missed near-matches. Histogram similarity under a
floating-point threshold would add platform-dependent comparison to deterministic
reports ([AD-7](ad-07-determinism-is-measured-not-assumed.md)) and risk false candidates
([AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md)). Shape belongs
on `symbols`, not in a new artifact-breaking section
([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).

The collector records every shape; the derivation ignores shapes below ten nodes.
Across 431 self functions, nineteen shapes repeated. Three groups below ten nodes
were language boilerplate: eight paired `visit_FunctionDef` and
`visit_AsyncFunctionDef` implementations, and two zero-node `Protocol` methods.
Above ten, repetitions included collector methods, rule parsers and a field reader
later consolidated into `ir.model.text_value`.

Check: the shop owns order arithmetic in `shop.model`; the tour's copy of
`Order.total` in `shop.app` is a 29-node candidate.
