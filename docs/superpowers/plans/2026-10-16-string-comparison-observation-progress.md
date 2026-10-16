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
- [x] Reproduce shared multi-target initializer mutation and middle-comparator escape with real native sources.
- [x] Exclude Assign nodes with multiple targets; accept named collection loads only as the final comparator of a final In/NotIn operation.
- [x] Preserve named In/NotIn positives, lexical shadowing and rebinding negatives.
- [x] Run native source/binding safety regressions, Ruff, Mypy, hygiene and the unchanged 65/919 baseline.

- Review RED 38934148617: exactly 4 failed / 28 passed; both shared-initializer forms and both middle-comparator roles produced false literal observations.
- Review GREEN 38934322536, candidate 3004d14e332c78b8388ad6bae140cc1123513fe7: 431 native collector/source-binding/hygiene tests passed, Ruff passed, Mypy passed for 132 source files.
- Native validation exit 0 with no diagnostics/failures; 65 unknown positions / 919 unresolved calls / 0 violations. No budget, allowance, compiler proof or State API changed.
- The exported formatter patch is applied to the product test file; the product source was already unchanged by formatting.

Ruling: reject multi-target Assign nodes instead of adding an alias graph — chained initializers can expose a container through another name or attribute — shared initializers remain conservatively unclassified even if no later mutation is visible.

Ruling: require a named collection load to be the final comparator under a final In/NotIn operator — a middle comparator also supplies the next comparison's left operand — ordinary named In and NotIn detection remains covered by native positive controls.

## Literal membership needle expansion

- Base 95f514d362eef18cdd07fec50de1b7f46e94545c preserves the Astra-approved collection-role fix, State and the full-suite test-only corrections.
- AD48 originally covered literal collections and AD80 adds existing local scalar binding evidence. The expanded parser/protocol requirement also needs the literal scalar as a membership needle.
- [x] Reproduce literal/bytes/local-scalar left needles with native trace-valid failures; keep enum/data-variable/shadow/import controls accepted.
- [x] Extend only the In/NotIn branch through existing scalar(left); retain collection-side role restrictions and all binding limits.
- [x] Run collector/source-binding/State regressions, Ruff/Mypy/hygiene and the unchanged 65/919 native baseline; report any newly exposed protected protocol sites.

- Needle RED 38936689361: 10 expected failures / 40 passed; nine real needle forms and the old literal-in-text exclusion exposed missing observations.
- Needle GREEN 38936967356, candidate 2825b514e90c4afad7f2433b87bf61116ef06c3c: 496 collector, State, source/binding and hygiene tests passed; Ruff passed; Mypy passed for 132 source files.
- Native validation exit 0, no diagnostics/failures: 65 unknown positions / 919 unresolved calls / 0 violations. The stronger observer exposes no newly failing protected State site.
- The formatter changed only the new native test formatting; that exported patch is applied to the product file. Product source and legacy test changes were already unchanged by formatting.

Ruling: membership can have a literal vocabulary on either side — a literal or already supported module/class scalar needle is sufficient syntax evidence — reusing scalar(left) adds no runtime type or namespace inference and preserves collection-side alias/role exclusions.

Ruling: enum members and arbitrary data variables stay unclassified as literal needles; explicit enum value extraction uses the existing scalar proof, while imported arbitrary values remain unsupported — native controls distinguish these boundaries — this does not claim a universal semantic string ban.

## Frozen Enum value evidence review scope

- Base 61404f1cf9e8579929119be093c3676075754661.
- [x] Native RED for extra bases, construction/access hooks, class metaclass/decorator transformation, IntEnum conversion and namespace ignore; preserve plain Enum and StrEnum positives.
- [ ] Admit only a single directly proven Enum/StrEnum base, no class keywords/decorators, and ordinary literal member declarations. Reuse existing static member inventory rather than MRO/runtime inference.
- [ ] Preserve nominal enum-member controls and all alias/collection restrictions; run native source/binding/State safety, Ruff/Mypy/hygiene and 65/919 baseline.

- Enum review RED 38938809344: exactly 9 failed / 51 passed. Ordinary Enum/StrEnum positives and the existing own-value-property exclusion passed; each newly reported transformation produced the expected false observation before the fix.
