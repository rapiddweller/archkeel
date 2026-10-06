# AD-14 The report headline follows its verdicts, never the exit code alone

Report headlines follow verdicts, not process exit codes. A complete report can exit zero while
showing violations. Incomplete evidence stays NOT CHECKED; validation distinguishes rejected
evidence from failed rules. Keep those distinctions visible before review context.

Proof: [test_terminal.py](../../../tests/test_terminal.py) and
[test_html_report.py](../../../tests/test_html_report.py).
