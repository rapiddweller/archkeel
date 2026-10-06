# AD-59 A type crossing many component boundaries is a review claim, not a verdict

`ir.type_fanin` derives the fifth Class D claim, `cross-component type fan-in`
(AD-26), from imports and function/method annotation symbols. Count each crossing
function once per ordered component pair, then name raw annotation strings crossing
at least two distinct pairs, most-crossed first. Missing either section means
UNKNOWN with no candidates.

Issue #9 sought widely passed context types. Import-site counts would inflate
repeated use across one pair; formatted interface strings would require parsing
annotations back out of presentation text. Read raw facts instead.

The shop named `Order` and `str` at two pairs. Self analysis named 23 candidates,
led by builtins and JSON boundaries; `Observation` and `RunResult` crossed three
pairs each. A shared IR legitimately crosses widely. Interpretation belongs to
the architect, never a verdict.

Limits: unrelated types with the same annotation spelling merge; unexpandable
re-export chains are invisible. No analyzer version change is needed for this
pure derivation. Checks: `tests/test_type_fanin.py` covers missing signals,
two-pair candidates and shared self types; `class-d-type-fanin` demonstrates it.
