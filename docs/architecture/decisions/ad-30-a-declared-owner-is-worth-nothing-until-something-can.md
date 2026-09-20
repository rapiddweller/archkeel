# AD-30 A declared owner is worth nothing until something can contradict it

`spot_owners` has
been a class-C declaration since the first contract: the architect names who owns a piece of
knowledge, the analyzer records it, and nothing ever looked. The claim `repeated logic` gives it a
reader. Its signal is a `shape` on every function and method symbol: the node types of the body in
walk order, hashed, with names and literal values dropped, so a copy survives renaming. Two
functions with one shape are structural twins, and the claim names those that sit outside an owner
whose twin sits inside it.

The shape is an exact digest rather than a similarity score. The prior art compares
thirty-dimension node histograms by Jensen-Shannon divergence under a float threshold, which would
put a platform-dependent comparison inside a report that must stay byte-identical ([AD-7](ad-07-determinism-is-measured-not-assumed.md)), and buys
a cloud of near-matches where [AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md) already warns that wrong candidates teach readers to skip the
section. An exact hash finds only true twins, and that is the trade this claim accepts. It lives
as a field on `symbols`, not as a new section, because a shape is a property of a declaration and
an added field breaks no older artifact, while an added section does ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)). The size below which a
shape says nothing is decided in the derivation, not in the collector: the signal records every
shape, the claim decides what is too common to mean anything. Ten nodes, measured. Across 431
functions Archkeel shares nineteen shapes, and the three groups below ten nodes are shapes the
language forces rather than copies: eight functions are the
`visit_FunctionDef`/`visit_AsyncFunctionDef` pair that `ast.NodeVisitor` makes every collector
write twice, and a pair of empty `Protocol` methods measures zero. A docstring is not part of the
shape, for the reason `body_is_empty` already ignores it — one sentence of prose must not disguise
a copy. Above the threshold every group is a real repetition, several of them owed to this
repository's own agent: two collectors whose `__init__` and `visit_ClassDef` match line for line,
two rule parsers that differ only in the kind they name, and one record-field reader standing three
times in `ir`, since merged into `ir.model.text_value`. A claim that names its author is working,
and what it names gets fixed. Check: the shop sample declares
`shop.model` the owner of order arithmetic, and the tour places a copy of `Order.total` in
`shop.app`, which the claim names at 29 nodes.

