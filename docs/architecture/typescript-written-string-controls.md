# Native written-string controls in TypeScript and JavaScript

Part of #542. This first increment observes written syntax and advertises only PARTIAL support.

- parse.py alone owns Tree-sitter and its canonical _node_kind decoder. It reuses the existing walk, source Span and named-scope inventory.
- syntax.py owns frozen StringComparison(span: Span, scope: str | None) and the immutable Syntax.string_comparisons tuple. Parser nodes never cross that port.
- collect.py owns canonical ForbiddenConstructKind.STRING_LITERAL_COMPARE production, stable source-bound identities and evidence.
- profiles.py preserves the legacy optional_sections field and its atomic symbols/calls/references/bindings receipt, including positional construction and dataclasses.replace. A keyword-only additional_optional_section_groups field adds the separate construct receipt. Derived optional_section_groups and all_optional_sections views serve codec consumers without storing a second inventory.
- Core authenticates the actual seven-section TypeScript form and its exact PARTIAL capability tuple. Legacy import/UML receipts remain readable and cannot advertise construct authority.

The measured syntax is ==, ===, != and !== with a directly written string operand, and switch case values. Escaped strings remain written literals; plain templates are accepted only when all named children are known fragments/escapes. Simple nested parentheses may contain comments. Known TypeScript as, satisfies and non-null expression wrappers preserve a written literal; the expression child alone contributes evidence, and literal types never become value proof. Unknown or repaired wrappers remain unproven. The participating literal's original Span gives nested comparisons distinct stable identities and retains UTF-16 evidence coordinates.

Anonymous callbacks and IIFEs receive no fabricated names. A containing named scope is reused when one exists; the source module owns the occurrence otherwise. This is lexical ownership, not a runtime invocation or call-target claim.

Known occurrences can cause trace-valid FAIL under an independently authored forbidden_construct rule. An empty inventory remains UNKNOWN. Unknown comparison grammar, dynamic templates and parse repairs cannot prove absence. Existing unknown parents remain traversable.

There is no imported/constant/alias/mutation/closure value propagation, type-checker inference or compiler/runtime authority. .includes, startsWith/endsWith and array/tuple membership require later explicitly scoped capabilities. Recognizing known value-preserving wrappers does not add imported value or nominal-erasure inference. JavaScript `in` checks property presence, rather than array membership. No browser-wide guard is enabled.

Native JavaScript file selection uses existing allowJs/checkJs semantics; explicit allowJs=false wins. checkJs inclusion does not establish deep JSDoc type/member Target evidence. TypeScript 5.9.3 remains the pinned compiler reference.

Independent Target intent names the lexical API and pins its Span/scope/tuple fields. Real source-widening mutations must fail against unchanged intent.
