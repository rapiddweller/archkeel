# AD-1150: A loader candidate in a lazy table keeps the proven edges of the others

Status: accepted. Amends AD-560 and AD-1096. Closes #2025.

## Why

A module-level `__getattr__` can import the entries of a table (AD-560). After AD-1096, the entry `pdb.main` is a
loader name. The survey then rejected the whole call, so the proven edge to `app.lib` in the same table was lost.
A rule that FAILed on main became UNKNOWN.

## Decision

1. `candidates` in `native/python/src/survey/lazy.rs` splits the candidates of a call. A candidate that is no
   module name still rejects the call. A candidate that is a hazard name is no edge, and it sets a flag.
2. The other candidates stay edges, as before.
3. When the flag is set, the call is not exempt. It stays the site `dynamic_import: import_module`, so the loader
   can reach more than the table names and the gap holds every rule that it can reach.

## Effect

A verdict can change from UNKNOWN to FAIL, never to PASS: the change only adds proven edges. A table with loader
candidates only has no edge and stays UNKNOWN.

## Not done yet

The gap names the call, not the loader candidate. The detail of the candidate is not in the gap text.
