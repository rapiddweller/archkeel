# Issue #542 native comparison observation ledger

- Plan committed before tests on isolated fix/542-string-comparison-observation.
- Native RED 38930770707: 14 failed, 11 passed. Missing observations and module-constant shadowing false positives were reproduced.
- Enum-rebinding RED 38931576018: 1 failed, 1 passed. A reassigned stdlib import did not establish an enum base.
- Native GREEN 38932772193, commit fffb8ca8c26f4eb38f462666655e37afeb3a8e50: 426 focused collector, source/binding safety and repository-hygiene tests passed; Ruff passed; Mypy passed for 132 source files.
- Native validation exit 0, no diagnostics/failures; 65 unknown positions, 919 unresolved calls and 0 violations. No budget or allowance changed.
- The hosted formatter left all three Python files unchanged. The product commit excludes temporary verification workflows.
- The required PR test list includes the native comparison source controls. The parent integration owns full-suite and final independent Astra review.

Ruling: imported arbitrary runtime constants remain unclassified — cross-module namespace escape and runtime rebinding cannot be certified by this syntactic collector — a separate binding-proof design would be needed to expand this guarantee.

Ruling: reuse existing LexicalScopes only for name ownership — parameters, locals and reassigned imports must not acquire module-literal evidence — no compiler receipt, namespace saturation or native type proof changes.

Ruling: named mutable literal collections require membership-only visible loads — mutation and alias escape invalidate classification — some genuine vocabularies remain intentionally unclassified.

Ruling: inspect stdlib enum bases and member extraction through nominal AST Name/Attribute shapes — string splitting introduced two new unresolved calls and obscured the bounded supported API — removing that parsing restored the original 919 budget without inference changes.

## Astra review follow-up on PR548

- Review base: 36264ae3b40dbffd9943f88232efef6993fe785f, preserving the integrated State tree and Makefile checks.
- [ ] Reproduce shared multi-target initializer mutation and middle-comparator escape with real native sources.
- [ ] Exclude Assign nodes with multiple targets; accept named collection loads only as the final comparator of a final In/NotIn operation.
- [ ] Preserve named In/NotIn positives, lexical shadowing and rebinding negatives.
- [ ] Run native source/binding safety regressions, Ruff, Mypy, hygiene and the unchanged 65/919 baseline.
