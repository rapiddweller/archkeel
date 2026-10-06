# AD-157: Filtered JSON carries source locations

Filtered violation JSON adds source `locations` from recorded evidence.
Line zero means file-only; missing evidence yields an empty list. Canonical records
remain unchanged.

Apply filtering after baseline comparison. `--only violations` retains FAIL and
UNKNOWN assessments; facets alone retain all assessments. Verdicts, totals,
measurements and exits remain global. Required locations and changed filtering
semantics form a breaking result-schema change, separate from Core and observation
formats.

[Agent-result proof](../../../tests/test_report_agent_json.py).
