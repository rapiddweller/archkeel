# AD-79 A planned entry is target work until code reaches it

`planned` is a target-work marker, not a module-existence alarm. A scanned but unused planned
entry produces no `interface.planned_built`; a cross-component import or declared facade signature
reaching it does. That diagnostic asks for the exact lifecycle move: remove the entry from
`planned` and add the same entry to `public`.

`boundary_types` uses the same target-first meaning. The module named by an exact planned entry is
a rule subject before the file exists, so work in flight does not become `rule_without_subjects`
UNKNOWN. The entry is still absent from observation and does not make a public interface. A scope
with no matching planned entry remains unsubstantiated and fails closed.

`validate --against` treats an exact same-component move from `planned` to `public` as a narrowing.
Other public additions and planned removals remain widenings. The comparison is set-based and keeps
the existing fail-closed generic field check.

Reason: the old module-only test forced target-first work to become a diagnostic as soon as a file
was created, and boundary rules then called the same work an empty scope. Both signals were early.
The existing lists, scanner records and target-work representation already carry the required state;
no lifecycle enum or new state machine is justified.

The analyzer version rises to `0.34.0` because planned declarations now affect rule coverage.

Check: `tests/test_validation.py`, `tests/test_analyzer.py`, `tests/test_widening.py`, and the
`validation-interface-planned-built` demo row.
