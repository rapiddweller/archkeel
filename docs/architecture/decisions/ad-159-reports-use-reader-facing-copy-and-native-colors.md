# AD-159: Reports use reader-facing copy and native colors

Use plain report labels and system light/dark colors, retaining identifiers,
verdicts, provenance and handoff contents. Wrap code on small screens; wide evidence
tables scroll independently. Put guidance beside the decision, not in empty failures.

Display a valid Python project name, falling back to namespace. Unreadable metadata
cannot change a verdict. Rule help lists assessment IDs even without findings.
This changes presentation only, with no new configuration or IR field.

[Report proof](../../../tests/test_html_report.py).
