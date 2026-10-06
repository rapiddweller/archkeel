# AD-56 A public entry the scan never saw is missing, and planned exempts target work

An absent public module is missing; a scanned but unused entry is unused. Symbol entries are judged
by module presence, so an absent symbol in an existing module is not proven missing.

`planned` records target work until imports or facade signatures reach it
([AD-79](ad-79-planned-entry-is-target-work-until-reached.md)). Keep entries in one list;
disjointness was intended but not enforced. Proof:
[test_validation.py](../../../tests/test_validation.py).
