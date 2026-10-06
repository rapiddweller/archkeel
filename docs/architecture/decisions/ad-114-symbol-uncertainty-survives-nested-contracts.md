# AD-114 Symbol uncertainty survives nested contracts

A complete directive scan does not prove which names a Dart import uses. At the root,
symbol-dependent rules already preserve this uncertainty. Nested contracts lost it (#184).

Run the existing symbol-limit evaluator at each declared level, restricted to that level's
valid source modules. Keep the mounted rule IDs, import facts and source evidence. An invalid
child claim cannot pull foreign imports into the count.

An undecidable import stays UNKNOWN; an explicit forbidden name stays a violation. Both can
coexist, with FAIL as the overall rule verdict. A whole public module or an explicitly allowed
name remains decidable. Scan completeness is a separate result.

No new resolver, schema or language capability. Python imports already name their bindings.
The independent nested tests and the Dart catalog's nested variants exercise the correction.

The architect approved one added unresolved call:
`validate --against 0400d3d` identifies `unknowns.extend` in the shared evaluator. The call
budget moves 530 → 531 for that added source operation, not better detection or new rule
uncertainty. The resolver is unchanged; self-validation still has 41 UNKNOWN positions,
0 violations and 0 cycle edges. No violation exemption is added.
