# AD-32 A component names what it requires; what it does not name is forbidden

A component declares permitted dependencies in `requires`, beside its `public`
interface, with a reason per entry. Under `complete_requires`, a missing target is
forbidden; only a missing list is open. Without the rule, behavior is unchanged.
`init` writes neither rule nor list, preserving the architect's decision
([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md),
[AD-31](ad-31-deciding-inside-a-component-is-optin-and-only-for-pairs.md)).

Six self-components had 30 pair rules: 22 prohibitions and 8 permissions for 8
observed edges. A child `check` level would need 132 pair decisions
([AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)). `requires`
replaces that enumeration with permitted edges. Parent restrictions are the list's
complement when checking inside imports.

The 11 rules narrowing dependencies below component level remain, including module,
symbol and source restrictions. `decided_by` belongs to the rule, so counts measure
one decision instead of eight. This additive property and rule retain contract
2.1.0; older versions fail closed ([AD-8](ad-08-statement-constructs-are-class-a-rules.md)).

Checks: a shop `render` import of unrequired `model` yields one violation; the corpus
covers the rule and malformed entries; fresh `init` drafts no list. The self-contract
subsequently replaced its 30 pair rules with 8 entries, one `complete_requires` rule
and 25 total rules.

Observations retain each requirement's target, rationale, `through` list and
effective decider, so reports explain its permission. These fields raised
`ANALYZER_VERSION` from `0.53.0` to `0.54.0`; contract schema stayed unchanged
(AD-3, #163).
