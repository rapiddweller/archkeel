# AD-60 report --only, --rule and --component narrow what a rendered report shows, never what it judged

`report --only violations` hides flow, communication, claims and structure.
`--rule <id>` and `--component <label>` narrow the violation table independently;
together they intersect. Components match either side of an import crossing.

`select_violations` derives one selection from typed rows (AD-54), shared by HTML,
terminal and JSON. Filtered results carry `report_filter` and `filtered_violations`;
unfiltered results carry null. A shared summary announces `N of TOTAL` shown,
including an HTML `data-report-filter="true"` marker.

Canonical `architecture.json` bytes, verdicts, exit code and full counts remain
unchanged (AD-51). The complete inventory and unfiltered artifact link stay visible.
Unknown rule/component selectors produce uncoded `filter_unknown`, exit 2.
Validate selectors against all declared rule ids and top-level components,
so a declared selector with zero violations yields an empty success.
Inside rules use their existing `<component>:<rule id>` identity (AD-36).

Issue #7 involved 452 modules and 25,223 evidence rows. Use the existing violation
derivation rather than add rule-kind or level facets. Typed rows have only top-level
owners (AD-34); deeper filtering would require a new ownership model.
Limits: constructs, unassigned modules and cycles without a component pair never
match component filters. Other views are hidden, not independently filtered.

The feature is not a cataloged rule/code (AD-11); the catalog's `filter_unknown`
row points to dedicated tests. `tests/test_report_filter.py` covers selectors,
intersection, both crossing sides, unchanged artifact/counts/verdicts, unknown and
zero-violation selectors, HTML/terminal announcements and CLI JSON. Self validation
covered the declared `select_violations` interface.
