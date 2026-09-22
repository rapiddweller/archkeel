# AD-84 `boundary_types` follows declared facade re-exports and one field level

`boundary_types` matches a declared facade entry through the analyzer's typed import facts. It
checks the function annotation at its definition, but reports the facade module and binding as
the subject. Multiple aliases or re-export paths are one occurrence when they resolve to the
same exact origin; only distinct possible origins are ambiguous and UNKNOWN.

For a declared request or result class, the rule checks directly declared fields once. A deeper
model, unresolved field or otherwise ambiguous position is UNKNOWN. The rule does not become a
recursive type resolver.

Reason: the public contract owns the boundary; the implementation owns the definition. One
direct field level catches the proven leak without inventing a second resolver.

Rejected: name heuristics, dynamic probing, reflection and a recursive type engine. They would
duplicate existing import/type facts and turn a bounded observation into guessed runtime shape.

Archkeel's own contract keeps `Badge` and `VerdictRow` in the render facade because they are
intentional fields of the returned `Summary`; the analyzer's JSON helpers are implementation
imports, not analyzer facade entries. No baseline hides these findings.

`ANALYZER_VERSION` rises to `0.40.0`; the architecture contract schema is unchanged. Check:
`tests/test_boundary_types_facades.py`, `tests/test_architecture_demo.py`, and the generated
self-observation.
