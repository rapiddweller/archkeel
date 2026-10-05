# AD-203 Native map list values use proven coordinates

Issue #353: `dict[str, list[object]]` needs an exact depth-2 value permission.
The existing mapping occurrence retains the leaf depth proved by typed SourceFacts and builtin
bindings. Direct `object` values keep depth 1. Exact symbol, position, complete annotation, one
alias-free mapping and one opaque occurrence remain required; the outer map needs its own entry.

Shadowed bindings, aliases, multiple leaves and unsupported value shapes gain no permission.
Sibling findings, UNKNOWNs and AD-188 field ambiguity guards remain checked. The existing FACT
writer records accepted opacity and decision provenance; type closure remains unproven.

No new selector or wire schema. Core semantics advance to 0.73.0 under AD-3.
Checks: `tests/test_boundary_type_native_map_lists.py`, existing opaque-map and nullable-field tests.
