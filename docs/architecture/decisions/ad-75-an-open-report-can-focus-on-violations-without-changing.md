# AD-75 An open report can focus on violations without changing evidence

`report --only violations`, `--rule` and `--component` keep AD-60's generation-time
semantics. An unfiltered HTML report additionally offers one local `Violations only` control
when it has violation rows. It hides component communication, measurements, coverage,
structure and review claims. The decision, verdicts, failures, known unknowns, full violation
table, ArchitectureIR inventory and reproduction metadata stay visible.

The report control also enables `Violating edges only` in Component flow. The flow control may
be used on its own and filters only edges whose existing `FlowEdge.state` is `violation`; it
does not derive violations again. Its labels say that counts and empty results apply to graph
edges at the current level. Symbol, construct and other non-edge violations remain in the table
and an empty filtered graph points there instead of claiming that the report is clean.

Both controls change only the open page. They do not change the `RunResult`, verdict, totals,
exit code or canonical `architecture.json`. The controls are hidden until their inline scripts
run, so a no-JavaScript reader gets the complete report. Switching the report focus off restores
the full report and its graph.

Reason: the complete report is evidence-rich by design, but that makes its negative findings
slow to isolate. Re-running the CLI is useful for automation and a stable shared artifact; it is
unnecessary friction when a reviewer already has the full offline page open.

Rejected: browser-side rule and component facets. The CLI already owns those exact filters, and
duplicating their validation and intersection rules in JavaScript would create a second source
of truth. Also rejected: hiding verdicts or unknowns. A focused view must not turn partial
evidence into apparent certainty.

Check: `tests/test_html_report.py::test_html_report_can_focus_an_open_report_on_violations`,
`tests/test_flow.py`, `tests/test_report_filter.py`, JavaScript syntax checks and the release
browser pass over the tour, a non-edge violation and an UNKNOWN-only report.
