# AD-37 A receiver whose type is statically obvious resolves the stdlib method it calls

Resolve receivers only from proven static bindings and a closed literal-method table. Conflicting
bindings invalidate resolution for the function; do not guess control flow or inspect runtime
objects. Annotations may provide partial evidence.

[AD-40](ad-40-a-call-whose-callee-the-import-binding-proves-or-whose.md) extends the table to known
call results. Unlisted behavior remains unresolved. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).
