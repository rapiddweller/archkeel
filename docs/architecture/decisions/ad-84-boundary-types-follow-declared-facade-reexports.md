# AD-84 `boundary_types` follows declared facade re-exports and one field level

`boundary_types` resolves declared facade re-exports through typed import facts.
Check annotations at definitions; report the facade module/binding. Aliases sharing
one exact origin count once; distinct origins are ambiguous UNKNOWN.

Check declared request/result fields one level deep. Deeper models and unresolved
positions remain UNKNOWN. Public methods, `__init__` and special methods such as
`__call__` use the same facade proof; omit receivers by method kind. Unknown custom
bases remain UNKNOWN rather than guessing MROs. Overloads define the callable surface,
so do not separately count broad implementation signatures.

This keeps boundary ownership separate from implementation location without a
recursive resolver, name heuristics or runtime reflection. The self render facade
retains `Badge` and `VerdictRow` as intentional `Summary` fields; analyzer JSON
helpers are implementation imports. No baseline hides findings.

Analyzer version rises to 0.40.0; contract schema stays unchanged.
Checks: `tests/test_boundary_types_facades.py`, demo tests and self-observation.
