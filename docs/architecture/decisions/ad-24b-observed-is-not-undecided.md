# AD-24b Observed is not undecided

At component level `undecided` means a decision is owed:
`validate` reports the pair and the report can fail on it ([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)). Inside a component none is
owed, and validate demands none, so an inner edge that no rule names is `observed` and carries its
own neutral colour. Sharing the warning colour of `undecided` made this repository's 90 inner
edges look like 90 open decisions, of which it has zero. The state is a rendering distinction with
no verdict behind it: a rule scoped below a component still turns its pair into a violation, which
is what makes `sibling_isolation` visible at all. Check: `open_decisions` names no inner pair,
while the tour's peer import stays red.

