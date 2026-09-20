# AD-23 The report headline follows open decisions as well

A `report` whose contract still has
open decisions must not read PASS: the headline names them, the way [AD-14](ad-14-the-report-headline-follows-its-verdicts-never-the-exit.md) makes it name violated
rules. Reason: on a freshly drafted second level, `report` exited 0 with zero violations and said
nothing about 132 undecided pairs, so a contract that decides nothing looked finished. Check: a
render test for a report whose contract leaves one pair undecided.

