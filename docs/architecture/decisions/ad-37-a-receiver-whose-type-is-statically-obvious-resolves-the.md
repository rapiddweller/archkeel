# AD-37 A receiver whose type is statically obvious resolves the stdlib method it calls

Resolve receivers only from proven static bindings and a closed literal-method table. Conflicting
bindings invalidate resolution for the function; do not guess control flow or inspect runtime
objects. An unshadowed builtin class name may use the same table for partial evidence; a lexical
binding takes precedence. Annotations may provide partial evidence.

External standard-library annotations require a proven import binding. Optional unions remain
unresolved without narrowing evidence.

[AD-40](ad-40-a-call-whose-callee-the-import-binding-proves-or-whose.md) extends the table to known
call results. The closed method tables include `bytes.decode`, `bytes.hex`, `bytes.rstrip` and
`hmac.HMAC.digest`. Unlisted behavior remains unresolved. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py),
[test_typed_python_receivers.py](../../../tests/test_typed_python_receivers.py).
