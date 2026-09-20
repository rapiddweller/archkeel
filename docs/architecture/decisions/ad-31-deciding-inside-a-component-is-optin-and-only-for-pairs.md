# AD-31 Deciding inside a component is opt-in, and only for pairs that exist

Superseded by
[AD-33](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md); the rule kind it introduced never left this repository. [AD-24](ad-24-the-report-opens-a-component-without-requiring-a-decision.md) leaves the
inside of a component undecided by design, which is right until an architect wants to govern it.
`complete_inner_decisions` names one component and demands that every observed module pair inside
it be decided; without the rule nothing changes, so no repository inherits the work by upgrading.
The expected set is the pairs the analyzer observed, never the product of the modules: `analyzer`
holds 21 modules, so the product is 420 pairs and the observation is 46. A pair nobody imports
needs no decision, and demanding 374 of them would bury the 46 that matter. Inside the rule's
component an undecided pair becomes `undecided` rather than `observed` ([AD-24b](ad-24b-observed-is-not-undecided.md)), because there a
decision is owed again. `init` writes neither the opt-in rule nor the pairs it opens: [AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md) holds
here too, and an opt-in the draft hands out is no longer one. The architect adds the rule, and
`validate` then lists the pairs inside that component the same way it lists the pairs between
components, from the same derivation in `ir`.
Check: five of Archkeel's six components hold 90 observed inner pairs between them, no contract
opts in, and `validate` reports no inner decision.

