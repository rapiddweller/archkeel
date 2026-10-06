# AD-33 A component's inside is a level, not a list of pairs

Remove unreleased `complete_inner_decisions`, replacing [AD-31](ad-31-deciding-inside-a-component-is-optin-and-only-for-pairs.md)'s
pair enumeration with an inside contract and `requires`
([AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md)).
Tags stopped at 0.3.0; no outside contract could carry the removed kind. Preserve
its observed-pairs principle: `analyzer` had 46 observed pairs versus 420 possible.

The original inside design used its own scope, contract, components and `requires`,
with matching `public` at both levels ([AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)).
This became affordable: `check` drafted 12 children with 23 requirements instead of
132 pairs; `ir` drafted 13 with 15 requirements instead of 156 pairs
([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)).

Report an inside larger than the top level by module count or inner-edge count.
Both come from one observation ([AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md));
a hypothetical child draft needs another scan and measures directory cuts instead.
Depth stays optional: the report supplies size evidence; the architect chooses a level.

Original measurements (modules, edges): `analyzer` 21/47, `check` 13/23 and `ir`
15/22 exceeded the top level's 6/8; `cli` 4/3, `render` 5/3 and `host` 2/0 did not.
Check: no removed kind in schema or model; only the first three receive the claim.
