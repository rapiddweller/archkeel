# AD-594 The architecture picture has three views: As-Is, Target and Diff

**Status.** Proposed. Part of #880. It extends points 6 and 9 of AD-496 and the section of AD-464.

**Decision.**
1. The architecture picture of the report page has three views. **As-Is** shows the components and
   the dependencies that the scan observed. **Target** shows the structure that the contract
   declares: the components, their `layer`, each `layer_order`, each `requires` and the number of
   public surfaces. **Diff** shows where the two differ.
2. Diff has three marks. An observed dependency against a rule is a violation and links to its
   block. A pair that a gap holds is not decided and links to the causes. A declared requirement
   without an observed import is information and no verdict. One pair shows one mark: violation
   before held pair before requirement without import.
3. The page decides nothing (AD-496 point 9). Each mark is a row of the frame: a violated place
   (`explain.rules`), a held pair of an UNKNOWN rule (`explain.holds`), a requirement with
   `imports: 0` (`topology.requires`).
4. The core states the declared structure in `topology`, as data: `components[*].layer`,
   `components[*].public`, the list `requires` with `source`, `target` and `imports`, and the list
   `layers` with `rule` and `layers`. `imports` counts the resolved edges from the source into the
   target, with the components below each side, before a budget cuts a list. The budgets are
   20,000 requirements and 4,096 layer orders. The fields are additive; the section stays version 1.
5. The picture is drawn one time. Each mark names the views that show it (`rp-a`, `rp-t`, `rp-d`),
   and the style sheet shows the marks of the selected view. The map and the matrix use the same
   pairs and the same marks.
6. The switch is three radio inputs and their labels. The page has no new script and no new
   resource; the policy of AD-496 point 2 does not change. As-Is is the first view. Print shows the selected view.
7. The limit of AD-496 point 6 counts the pairs of all views: a map shows at most 12 components and
   at most 30 pairs, observed or declared. A larger picture is the matrix.

**Reason.** A reader compares what the code does with what the contract declares. One drawing with
marks keeps the three views consistent, and a frame field keeps the decision in the core.

**Rejected.** A script that builds each view: the page has one admitted script, and a second
drawing path can show a different picture. Three drawings in the page: three times the bytes for
the same boxes. A difference that the page computes from edges and rules: it is a second decision
of `complete_requires`. The removed Explorer (`flow.js`, #1131, #1273): it does not come back.

**Limits.** Target does not draw a dependency that a rule forbids, and it does not draw `through`.
Diff does not mark an observed dependency that no requirement declares when no rule fails on it.
The layers are a line of text and not the columns of the map. The frame names at most 20 held
pairs for a rule; the page states the two numbers when it shows fewer. The page shows at most five
layer orders and nine rows for each group of the Diff list.

**Tests.** `native/report/src/html_views_tests.rs` (the section of a small frame with a violation,
a held pair and a requirement without import against `native/report/testdata/views.html`; the marks
of each view). `native/core/src/topology_declared_tests.rs` (the count of `imports`, the roll-up to the parent).
`tests/test_cli_report_topology_declared.py` (the rows of a real run; forged rows are refused).
