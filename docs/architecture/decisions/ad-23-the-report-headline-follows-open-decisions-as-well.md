# AD-23 Open decisions remain visible context

Open component pairs are a decision worklist, not failures of declared rules. Reports must
distinguish undecided intent from violations and missing evidence. Show FAIL and UNKNOWN first
without changing deterministic JSON order or claiming that open architecture is conformant.

Proof: [test_terminal.py](../../../tests/test_terminal.py) and
[test_html_report.py](../../../tests/test_html_report.py).
