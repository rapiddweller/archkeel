# AD-280 Show CI checks as named steps

Keep the required CI and full-verification gates. Name jobs for the checks they run.
Show architecture, build, generated assets, report timing and diagrams as separate
Full verification steps. A dry-run test compares their commands with `make ci-check`.

The Python shards own saved-report tests. The report job owns renderer tests. A report
change selects both jobs. This avoids running the same selected tests twice.
Changes to demo verification select full verification.

Write the self-validation JSON to a local artifact. Show the rule status and diagnostic
count in the log; show the full JSON on failure. Demo steps show a short result and retain
the full result as an artifact. FAIL and UNKNOWN stay distinct.

Do not label the mixed Python suite as unit tests. It includes integration and CLI tests.
Do not reduce the Windows or Python compatibility checks. Reuse of demo reports for
Pages remains separate work because the gallery has additional validation.

Checks: `tests/test_make_gate.py`, `tests/test_ci_changes.py` and `tests/test_demo_ci.py`.
