# AD-188 Enum literals have their own UML kind

Distinguish `enum_literal` from attributes, with one enumeration owner and no
operation modifiers. Reuse conservative recorded enum members; do not guess
unsupported assignments or runtime members. Physical field identities remain intact.

Partial coverage cannot prove completeness. Unsupported fields/bindings are not
known wrong kinds, while a known operation contradicts a required literal.
Older graph formats remain readable but cannot carry new literal vocabulary;
combined targets retain the newest declared format.

[Enum proof](../../../tests/test_enum_graph.py).
