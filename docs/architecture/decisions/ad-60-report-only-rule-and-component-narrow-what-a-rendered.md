# AD-60 report --only, --rule and --component narrow what a rendered report shows, never what it judged

Report selectors narrow presentation, preserving canonical evidence, verdicts, exits and full
totals. Rule and component selectors intersect; components match either crossing side. Unknown
selectors exit two, while declared selectors with no violations succeed empty.

Pairless constructs and cycles cannot match component filters. One typed selection serves every
renderer. Proof: [test_report_filter.py](../../../tests/test_report_filter.py).
