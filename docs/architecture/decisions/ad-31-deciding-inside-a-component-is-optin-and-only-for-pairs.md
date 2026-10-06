# AD-31 Deciding inside a component is opt-in, and only for pairs that exist

Superseded by [AD-33](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md);
`complete_inner_decisions` never left this repository.

The opt-in rule required decisions for observed module pairs inside one component,
leaving ordinary navigation unchanged ([AD-24](ad-24-the-report-opens-a-component-without-requiring-a-decision.md)).
It used observed pairs, not every possible pair: `analyzer` had 46 observed pairs
among 21 modules, versus 420 possible pairs. Undecided governed pairs used the
warning state ([AD-24b](ad-24b-observed-is-not-undecided.md)).

Only the architect added the rule. `init` wrote neither it nor pair decisions
([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)); `validate`
listed open inner pairs through the shared `ir` derivation.
Original check: five components had 90 observed inner pairs, but no contract opted
in and validation reported no inner decisions.
