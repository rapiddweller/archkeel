# AD-133: Type-ignore allowances bind one occurrence

Allow one `type: ignore` only when qualified owner, line,
`ast.unparse` statement and trimmed tag all match. Broader exemptions
permit unrelated constructs. Shared-line statements cannot match; unambiguous
multiline calls can.

Source shifts fail closed. New or changed permissions require ordinary widening
approval. Legacy selectors remain compatible and absent allowances preserve digests.
Other suppressions and constructs remain forbidden; duplicate or unknown fields are
invalid. Matched facts retain source and decision provenance.

[Exact-suppression proof](../../../tests/test_exact_type_ignore.py).
