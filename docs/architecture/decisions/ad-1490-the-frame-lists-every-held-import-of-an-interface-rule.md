# AD-1490 The frame lists every held import of an interface rule

**Status.** Accepted. Builds on AD-1210 and AD-1220. Closes #2244.

**Decision.** `explain.holds.rules[RULE].interface.imports` lists every held import of an
interface rule, each with its source, target, name, cause and evidence ids, and
`interface.places` lists every place that a cause names, with its count, largest first. The
hold keeps at most 50,000 imports. A rule over that bound says so: `imports_truncated` is true.
The page (HTML) does not carry the list; it keeps its summary. The JSON frame is the complete record.

**Reason.** A team that must fix or declare each held import could see 20 of 804 on EE. The cap
hid the sites. `--all` did not lift it.

**Measured** on EE `560d5c7ef`: `EE-INTERFACE-BOUNDARY` 804 held, 804 listed; nine rules list more than
20. The frame grows from about 8.7 MB to 10.6 MB. The HTML page does not carry the list.

**Limit.** No verdict changes. The text output still shows the first causes (`--all` lists them).

**Tests.** `test_cli_report_explain.py` holds a plant with 25 held imports that are all listed.
`causes_tests.rs` checks that a hold keeps all 30 of 30.
