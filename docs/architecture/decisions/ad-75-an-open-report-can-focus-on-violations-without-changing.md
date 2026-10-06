# AD-75 An open report can focus on violations without changing evidence

Keep AD-60's CLI filters. An unfiltered HTML report with violations adds local
`Violations only`, hiding communication, measurements, coverage, structure and
claims. Decisions, verdicts, failures, unknowns, the full violation table, inventory
and reproduction metadata remain visible.

The control enables Component flow's independent `Violating edges only` filter,
which reads existing `FlowEdge.state == violation`. Counts describe edges at the
current level. Non-edge violations stay in the table; an empty graph directs
readers there rather than implying a clean report.

Controls change only the open page, preserving results, totals, exits and canonical
bytes. They appear only after scripts run; no-JavaScript readers see everything.
Disabling focus restores the report and graph.

Reviewers should not need a CLI rerun to isolate findings in an open offline report.
Browser rule/component facets would duplicate CLI selector validation. Hiding
unknowns or verdicts would imply certainty the evidence does not support.
Check: HTML, flow and report-filter tests, JavaScript syntax and the release browser
pass over tour, non-edge and UNKNOWN-only reports.
