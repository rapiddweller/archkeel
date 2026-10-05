# AD-157: Filtered JSON carries source locations

`report`'s filtered violations add `locations: [{path, line}]` from the recorded evidence
used by the HTML handoff. Line `0` means file-only evidence; no attached evidence yields `[]`.
The projection wraps canonical records, which stay unchanged.

`--only violations` omits PASS and DECLARATION rule assessments, retaining FAIL and UNKNOWN.
Apply this after baseline comparison. Verdicts, totals, measurements and exit codes stay global.
Rule/component facets alone keep all assessments.

Command-result schema becomes `4.0.0`: locations are required and filtered assessment
semantics change. Core, observation, contract and profile versions stay unchanged. No release.

Checks: `tests/test_report_agent_json.py` covers CLI locations, schema negatives, size reduction,
FAIL/UNKNOWN, missing evidence, incomplete observations and unchanged baseline comparisons.
