# AD-510 The report page shows the exceptions first and folds the rest

**Status.** Proposed. Part of #880. It extends AD-498; its point 3 (a component has no block yet) and its Limits are done here.

**Decision.**
1. A cause of an UNKNOWN rule is one short sentence and a count. A long reason shows three examples and "+n more"; the whole text sits in the card of the cause. The verdict card keeps one line per cause without rule ids ("1 cause holds them", "2 causes hold them").
2. Under the verdict, the grouped cause cards hold the rule ids (at most five, "+n more"), the pairs and the gaps, in folds. A named gap such as a hygiene code has its own card.
3. Next step 1 links all violated places up to nine, else the first five and "+n more" to `#violations`.
4. A cycle block words its rule line from the level of its members: "no module cycles" for modules.
5. For more than 12 components, the first picture names the components with a violation or a gap (at most eight tiles), counts the others ("26 with gaps · 23 without an exception"), and lists the violated places one line each (at most nine). The matrix is folded.
6. The drill-down (component, module, file, import) exists only for a component with a violation or a gap. A component name links to its block only then. The first 24 have all tables; the others are one line.
7. The first two violated places are open; the others are folds with a one-line summary. The id `xN` stays, on the fold, so a link opens it.
8. A rule that holds is one count line per kind; the names are in a fold. The ids `violations`, `arch`, `next`, `x1…xN` do not change.
9. Word budget: visible text without closed folds is under 6,000 characters on each dogfood page.

**Reason.** The page answered "what is wrong" with a wall of nouns and ids. The reader wants the picture first and the words last.

**Rejected.** A block for each component: 55 blocks on the self page and no answer. A link to a component that has no block.

**Limits.** A gap is placed at its first subject module. More than 24 components with an exception show one line each. A closed fold prints only its summary, so print shows the first two violated places in full.

**Tests.** `tests/test_cli_report_page.py` (word budget, links, cause cards), `tests/test_cli_report_output.py` (every rule id is on the page), `native/report/src/html_tests.rs` and `html_blocks_tests.rs`.
