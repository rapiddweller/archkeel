# AD-10 The report draws component flow as intent against observation

Render component flow from the canonical observation in a self-contained offline report. Keep
deterministic packaged scripts and a table fallback. Observed edges carry import counts; violating
edges carry rule IDs and distinct styling.

The view must not invent conformance from a declaration. Proof:
[test_html_report.py](../../../tests/test_html_report.py) and
[test_determinism.py](../../../tests/test_determinism.py).
