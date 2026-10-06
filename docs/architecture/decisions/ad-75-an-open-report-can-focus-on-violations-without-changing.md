# AD-75 An open report can focus on violations without changing evidence

An open HTML report may hide non-finding views locally without changing evidence. Keep decisions,
verdicts, failures, UNKNOWN, violation tables and reproduction metadata visible. An independent
graph filter uses recorded violating-edge state; non-edge findings remain in the table.

No-JavaScript readers see the complete report. Empty graph results must not imply conformance.
Proof: [test_html_report.py](../../../tests/test_html_report.py).
