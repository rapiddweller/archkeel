# AD-498 The report page is short and has no dump of the frame

**Status.** Proposed. Part of #880. It extends AD-496 and replaces the old parts that its point 5 kept.

**Decision.**
1. The page has no Counts, Rules, Gaps, Unsupported, Request identity or Tool part. It has no JSON text
   and no `<pre>` block. The verdict, the next steps, the picture and the violated places stay.
2. A footer of one line names the run: core digest, commit, contract digest, and the command for the
   rows. The identity of the run, with the digest of each bound contract file, is folded below it
   (AD-440 point 8 stays true). The page has no date and no path of the machine: a frame holds
   none, and equal runs give equal pages.
3. A link inside the page has its target. A component has no block yet, so its name is text, in the
   map, in the matrix and in the path of a violation. The ids of the violation blocks (`x1`, `x2`, ...),
   `violations`, `arch` and `next` do not change.
4. A matrix of more than 12 components is folded below a one-line summary.
5. A violated cycle shows the file first and the module id in the `title`. Equal `file:line`
   places show once with their number (`x3`). The caption says how many members the cycle has, how
   many steps the shown path has, and where the last step returns. The line of the rule does not list
   "all components" for a cycle rule.
6. Under the verdict, one line names the three largest causes of the UNKNOWN rules with their rule
   counts (from `explain.holds`). The next step says how many causes hold the UNKNOWN rules.
7. Word budget: the visible text of the core self page, without closed folds, is under 6,000
   characters. It was 83,356 and 46,862 px high; it is 5,203 and about 3,900 px.

**Reason.** The live page was a dump: 9,300 px of a rule table whose cells broke letter by letter,
31,000 px of JSON, and 55 links that led nowhere. A report for people answers: what is the
verdict, where, and why.

**Rejected.** A shorter dump: a reader still sees JSON. A link to a block that does not exist.

**Limits.** The rules that hold, the causes as cards, the drill-down from a component and the
exceptions as the first picture follow in a later record. Until then, a rule that holds is not named.

**Tests.** `tests/test_cli_report_page.py` (the word budget and the absence of JSON on the core self
page and four dogfood pages, every link has its target). `native/report/src/html_tests.rs` (equal
places, the causes line, links, the cycle caption).
