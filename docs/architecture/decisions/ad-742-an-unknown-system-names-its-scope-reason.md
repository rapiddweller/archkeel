# AD-742 An UNKNOWN system names its scope reason

**Status.** Accepted. Part of #1451 (Wave 5, F19). Visible change.

**Context.** The system join (`native/core/src/system.rs`) wrote the scope of the system frame as
`complete` when no part had an open scope. A part can be UNKNOWN for a rule (the rule row is
UNKNOWN, with its reason in `explained`) while its scope is `complete`. The system frame then said
UNKNOWN and `scope: complete` at once, and the shell and the page had no scope reason to show.

**Decision.** The join types each part once (`PartFrame`: status, scope, first explaining row) and
derives the scope of the system in one function:
1. the reason of the first part with an open scope; else
2. when the system status is UNKNOWN, the first explaining row of a part that is not PASS (an
   UNKNOWN rule row, a rule without a decision, or a gap); else
3. `complete`.
A part that is UNKNOWN, or whose status is unreadable, without any explaining row refuses the
system (`system: the part <id> is UNKNOWN without an explaining row`). When the topology is asked
for, its gaps name the scope reason and its `complete` is false, because the shell reads an open
scope only with its reason among the gaps.

**Consequences.** An UNKNOWN system frame never says `complete`. The frame of one part is not
changed: its scope stays about the collection, and its rule rows carry the reasons. The exit code,
the status, the rules and the text of `validate --text` are the same.

**Undo.** Return the join to the first and the third step, and drop the refusal and the topology
gap. The test `an_unknown_system_never_says_that_its_scope_is_complete` then fails by design.

**Tests.** `an_unknown_system_never_says_that_its_scope_is_complete`,
`a_part_that_is_unknown_without_an_explaining_row_refuses_the_system`,
`the_topology_of_an_unknown_system_names_the_scope_reason_as_a_gap` (all in `system_tests.rs`;
the failing versions are the first commit of the pull request).
