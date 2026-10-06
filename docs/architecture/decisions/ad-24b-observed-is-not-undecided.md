# AD-24b Observed is not undecided

At component level, `undecided` means a decision is owed under
[AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md).
Inside a component, validation demands no pair decision. An edge without a rule
is `observed`, with a neutral color and no verdict. A scoped rule still makes a
violated pair red, including `sibling_isolation`.

Using the undecided warning color had made 90 inner edges look like open decisions,
although this repository had none. Check: `open_decisions` contains no inner pair;
the tour's peer import stays red.
