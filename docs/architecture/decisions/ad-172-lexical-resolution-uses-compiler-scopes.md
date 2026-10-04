# AD-172 Lexical resolution uses compiler scopes

Python uses `symtable` to identify local, global, nonlocal and free bindings.
AST sites provide source evidence. Calls and references share this scope index.

Parameters and assignments shadow outer names even before their source site.
Function headers and a comprehension's first iterator use their enclosing scope.
Class namespaces do not become method closure namespaces. Ambiguous tables,
conditional imports and unknown receiver types retain candidates or UNKNOWN.
Reads of indexed module values retain their binding. That proves a reference,
not a callable value. Conditional writes and rebinding keep uncertain references.

The adapter publishes facts. Core keeps the conditional rule-proof view; that
view is transient and never replaces the recorded definition inventory.
Main's inherited-method proofs and SourceFacts process boundary remain intact.

Proof: `tests/test_lexical_resolution.py`, `tests/test_conditional_definitions.py`,
`tests/test_local_inherited_methods.py`, `tests/test_inheritance_proof_transport.py`.
