# AD-37 A receiver whose type is statically obvious resolves the stdlib method it calls

Resolve receivers only from proven static bindings and a closed literal-method table. Conflicting
bindings invalidate resolution for the function; do not guess control flow or inspect runtime
objects. Annotations may provide partial evidence.

[AD-40](ad-40-a-call-whose-callee-the-import-binding-proves-or-whose.md) extends the table to known
call results. Unlisted behavior remains unresolved. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).

A populated, literal-only class whose sole base is proven to be the standard library's
`enum.StrEnum` can supply a requested inherited string-method target. Native class and
module identities must be unique, header and body must exclude transformations, and existing
member-escape checks must exclude class or provider mutation. A same-named enum member blocks
that method. Keep the canonical class identity; this is not a general enum-to-string conversion.
Annotations still supply only partial evidence, and unsupported annotation shapes keep their
existing fallback. Proof: [native StrEnum collector cases](../../../tests/test_python_strenum_methods.py).
