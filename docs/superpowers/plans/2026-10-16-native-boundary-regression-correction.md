# Native boundary regression correction — issue #542

Base: `5933ffbbfd588ac96e36748de937cb1f6e739655` (Graph + contract version). Grammar remains frozen at `d48e36f623a15734a7569e946646cdeaae030b88` during this correction.

1. Reproduce the Dependency API Target and typed-control failures against actual `7b2a14de58eb18be716c8eadef5c43928ec464a5` and `5933ffbbfd588ac96e36748de937cb1f6e739655`; print real report diagnostics before the test helper asserts exit 0. Identify the actual fixture/owner boundary that changed.
2. Repair only the diagnosed native fixture dependency/scope, keeping independently authored Target declarations and source mutation checks unchanged. No weakened verdicts, allowances or budgets.
3. Verify the layer/report-version intent and unchanged UML UNKNOWN identities against the nominal owner and existing unchanged nested definitions. Diagnose actual repeated logic before selecting a bounded source correction; do not disguise duplication by syntax.
4. Run all affected tests, native source mutations, Ruff, strict mypy, hygiene and strict actual own baseline. Record precise causal evidence and remaining inherited full-suite failures. Freeze a small correction carrier for Root's independent Astra review and targeted propagation.
