# AD-79 A planned entry is target work until code reaches it

A built but unreached `planned` entry remains target work. Cross-component imports
or declared facade signatures reaching it trigger `interface.planned_built`, asking
to move the same entry from planned to public.

For `boundary_types`, an exact planned module is a subject before its file exists.
This avoids premature `rule_without_subjects` UNKNOWN without creating a public
interface or observation entry. Scopes without matching planned entries still fail closed.

`--against` treats an exact same-component planned-to-public move as narrowing.
Other public additions and planned removals remain widenings, using set comparison
and the existing fail-closed field check.

Existing lists and facts express the lifecycle; no new state machine is needed.
Analyzer version rises to 0.34.0 because planned entries affect coverage.
Checks: validation, analyzer and widening tests plus `validation-interface-planned-built`.
