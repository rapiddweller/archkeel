# AD-288 A component card shows its label and its first responsibility

**Status.** Accepted. Issue #792, epic #783. Builds on AD-285 and AD-286.

**Decision.**
1. A component card in the Explorer shows the component `label` and one line: the first entry
   of `responsibilities`. The line comes from the contract, so it is author text.
2. Details lists all responsibilities. This was already true and does not change.
3. A component with no responsibility shows no line. The card shows no placeholder such as
   "Not declared". This also applies to each card of `archkeel explore` (AD-285).
4. The `label` is an identifier: `requires`, `--component`, nested scopes and the page graph
   use it. The card shows it as is. No display-name field is added.
5. The snapshot keeps `responsibilities` as a sorted list. So "first" is the first entry in
   that order, not the order in the contract file.

**Reason.** A reader must see what a component is for without a click. Each explore card showed
"Not declared", and that text is noise when nothing can be declared. A card with all
responsibilities on one line was cut at 126 characters in the middle of a sentence.

**Rejected.**
- The first line of the package docstring as observed text in explore. In the EE data, 2 of 7
  top-level components and 47 of 90 nested components have one. No carrier exists: the
  source facts schema closes the `file` object, so the line needs a source facts schema
  change. The first-run text comes from the agent instead: it writes `responsibilities` into
  the contract. Revisit this if the agent text costs too much.
- A display-name field: it would be a second name for one thing, and published schemas change.
- The text of all responsibilities on the card: the card has room for one sentence.

**Limits.**
- Author order is not kept. To show one entry first, keep the list to one entry, or keep the
  author order in the snapshot (a change of the snapshot content; not in this decision).
- Details of an explore component still shows "Explicitly empty" under "Responsibility".
- The tooltip still joins all responsibilities.

**Checks.**
- `tests/test_report_first_screen.py`: `test_a_card_shows_the_label_and_the_first_responsibility_only`
  replays the demo row `showcase-card-first-responsibility`;
  `test_a_card_without_a_responsibility_shows_no_placeholder`.
- `tests/test_explore.py`: `test_an_explore_card_shows_its_label_and_no_placeholder`.
- The Chromium tests run at 800x600 and locally (`make report-browser-tests`).
