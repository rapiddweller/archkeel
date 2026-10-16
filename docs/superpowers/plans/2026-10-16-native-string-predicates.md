# Native string predicate observation

Part of expanded #542. Parser and protocol values remain in scope.

The existing native string comparison observer does not record written prefix/suffix decisions. Add bounded actual-source negative controls for literal str/bytes, literal tuples, an unambiguous module constant and local Enum.value. Typed Enum arguments, data parameters, shadowed constants, computed values and unrelated calls remain negative controls.

After the corrected foundation passes its full regression gate, extend the existing visitor and lexical literal context directly. Own the two predicate names as one nominal syntax vocabulary at that existing owner; do not add a second AST traversal or infer receiver runtime types. These are written constructs, not semantic runtime proofs. Preserve span/evidence, existing equality/membership/match behavior and conservative dynamic limits.

The tests must fail before production changes. Verify native failures under unchanged policy, then relevant full observer tests, lint/mypy and exact call/UNKNOWN-site deltas without increasing budgets. Independent final Astra review and fresh combined tests gate merge. Subsequent TypeScript path-grammar conversion must use this actual guard, rather than merely renaming string constants.
