# AD-11 Every checkable item has a catalogued demo

`fixtures/F-architecture/` is a clean five-component repository with a closed
contract, `public` interfaces, a marked Mermaid graph and every Class A rule kind.
`validate` and `report` are clean.

`fixtures/architecture_demo.py` catalogs variants as repository-relative file
replacements with exact expected violations and diagnostic codes. Flat modules
group variants by rule family. The default `tour` fires every violatable Class A
kind. `allowed_dependency` is exempt: it records permission and cannot be violated.

Regression and protocol demos compare the clean baseline with a violating candidate.
They assert typed exit codes, verdicts and regressed measurements or delta dimensions,
never `failures` prose. Undemonstrable items such as `coverage_failures` are marked
as tested only. The generated `docs/architecture-demo.md` table must match the catalog.

A user should see each rule fire in a readable repository. Check:
`tests/test_architecture_demo.py` enumerates kinds, constructs, codes and measurements;
it rejects missing entries, unexpected findings, a dirty clean sample or incomplete
`tour` coverage.
