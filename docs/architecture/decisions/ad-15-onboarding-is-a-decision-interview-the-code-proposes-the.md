# AD-15 Onboarding is a decision interview: the code proposes, the architect decides

`init` proposes components and `public` interfaces from observed code, then
returns open decisions ordered by import-site count. It writes no dependency rule:
code shows facts, not intent. Every ordered component pair needs exactly one
`allowed_dependency` or `forbidden_dependency` rule with the architect's reason.

One `ir` function derives undecided pairs from projected decisions and observed
edges. Validation and reports, including later rendering from `architecture.json`,
share it. `decision.open` replaces `closed_world.missing` and reports whether the
pair is observed and its import-site count. JSON from `init` and `validate` includes
each option's exact rule, leaving only the reason to the architect. Reports use the
same derivation to draw undecided observed edges.

The skill interviews the architect, heaviest edges first: multiple-choice questions
with custom answers, one decision for a component's unobserved pairs, and sourced
hypotheses from docs. The agent never answers its own questions.

Contract 2.1.0 replaces 2.0.0 without a decode path; breaking changes were allowed
before 1.0. Previously `init` declared the observed graph's complement, making the
first report pass by construction. The internal service's documented intent instead
failed 7 observed edges at 200 import sites.

Check: `init` drafts no dependency rules; each undecided pair emits `decision.open`;
a forbidden observed edge fails the first report. The self-contract and shop sample
decide every pair.
