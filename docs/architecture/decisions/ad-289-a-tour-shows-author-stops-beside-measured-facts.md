# AD-289 A tour shows author stops beside measured facts

**Status.** Accepted. Issue #792, epic #783. Builds on AD-284 and AD-287. Amends AD-287 item 3.

**Decision.**
1. A view spec can list `stops`: an ordered tour for the first contact with a codebase
   ("start here, then here"). A stop has `node`, and an optional `title` and `note`. Both are
   author text.
2. A stop names a node of `nodes`, with the node rules of AD-284: after `explore`, use module
   nodes. A stop claims no relation, so it takes no `kind` and no `claim`. A `status`,
   `evidence` or fact field makes the spec invalid, as for every other reference.
3. `stops` needs `schema_version` `1.1.0`; `1.0.0` rejects it. A `1.0.0` spec stays valid and
   gets the same statuses; its result adds `"stops": []`. The contract gates `key_alias_body`
   by its minor version in the same way.
4. `view check` gives each stop the node status and reason of AD-284 and `facts`, measured from
   the snapshot only:

   | Fact | Meaning |
   |---|---|
   | `modules` | The observed modules the node holds: 1 for a module. |
   | `imports_out`, `imports_in` | Distinct module pairs of resolved imports that cross the node boundary, with each `ViewEvidence` (record id, evidence id, line). |
   | `gap` (of each) | The reason the snapshot cannot see each import: the count is then a lower bound. |
   | `violations`, `unknowns` | The records of these snapshot sections with a subject or fact in the node: record id, kind, title. |

   `facts` is null when the node is `unknown` or `missing`, or the snapshot is another one. A
   stop adds no status and does not change the exit code. A stop is never a proof.
5. The result stays one JSON document. `view show` embeds it in `view-check-data`.
6. Explorer: a "Tour" button beside "Checked flow". The tour draws the checked flow scene,
   marks the card of the stop and centres it. The Details panel shows "Stop n of N", the
   title, an "Author ✎" block and a "Measured" block, apart. The Measured block gives counts
   and record ids and never says PASS. Previous and Next, ArrowLeft and ArrowRight move; Esc
   goes back to the checked flow.
7. URL: `tour=<n>` opens stop n. A page with stops and no `view`, `flow` or `tour` parameter
   opens the tour at stop 1, because the first contact comes before a flow. `flow=1` still
   opens the flow. This amends AD-287 item 3.

**Reason.** A newcomer needs an order to read the code in. An agent writes that order well, but
its text has no authority. Facts beside each stop let the reader check the stop at once.

**Rejected.**
- A tour file or a second JSON format: the view spec and its check already hold the nodes.
- A `kind` on a stop, or an edge between two stops: a tour is a reading order. A step makes
  that claim, and the check proves it.
- Facts in the spec: the spec cannot state proof (AD-284).
- A new renderer or JavaScript file: the tour reuses the scene of the checked flow.
- Hub ranks of the report findings as a fact: a rank compares modules, it does not measure one.

**Limits.**
- A finding touches a stop only by a module or symbol subject. A package subject, such as the
  root-wide dynamic call limit, touches no stop.
- `imports_in` is a lower bound when any other module has an import gap.
- A stop on a large component lists each import site, so the page grows with it.
- A stop order is author text: it is not runtime order.

**Checks.** `tests/test_cli_view.py` (`test_a_stop_*`); `test_view_spec_schema_matches_its_dataclasses`
in `tests/test_schema_drift.py`; `tests/test_report_tour.py` (Chromium at 800x600, local until
Full runs it); demo row `protocol-view-tour` checks `fixtures/F-architecture-view/first-contact-tour.json`.
