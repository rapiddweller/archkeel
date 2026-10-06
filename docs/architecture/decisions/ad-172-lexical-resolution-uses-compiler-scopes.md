# AD-172 Lexical resolution uses compiler scopes

Use Python `symtable` with AST evidence as the shared call/reference scope index.
Parameters and assignments shadow outer names before their sites; headers and the
first comprehension iterator use enclosing scope. Class namespaces are not method
closures.

Ambiguous scopes, conditional imports and unknown receivers retain candidates or
UNKNOWN. Reading a recorded module binding proves a reference, not callability.
Core's conservative rule view remains transient and cannot replace the definition
inventory.

[Scope proof](../../../tests/test_lexical_resolution.py).
