# AD-528 A leading `types` directive is a type-only edge to its package, or a named gap

**Status.** Accepted. Part of #880. Closes #686. It extends AD-274 rule 3 and AD-353.

**Problem.** `/// <reference types="vite/client" />` makes the compiler read a type package, so the
file depends on it as `import type "vite/client"` does. AD-274 made no edge and no gap, so a rule
on the package could PASS for a file that uses it. 4.0.1 gave UNKNOWN for each such directive, so
the core was weaker than 4.0.1 (owner rule: stricter is allowed, weaker never).

**Decision.** `jsdoc::types_directive`, `concerns::type_directives` and `imports::type_directives`
turn each honored directive into a type-only reference (`import_type`) at the comment.
1. Honored: before the first statement (a comment or a hashbang may come first), in a TypeScript or
   JavaScript file; tag `reference` in any case and a `types` attribute in any case (tsc 5.9.3
   lists the package for `<REFERENCE types=…>`); `no-default-lib` makes it no types reference. A
   directive after code is ignored by the compiler and here: no edge, no gap.
2. The compiler reads `@types/<name>` first, then the package `name` (scoped `@s/p` is
   `@types/s__p`; checked with tsc 5.9.3 on `jest`, `node` and `@scope/pkg`). The resolver, which
   reads `node_modules`, proves the first one that is installed. The edge names that package.
3. Any other result is one gap, "Unresolved triple-slash types reference: name", with the line of
   the directive: no package installed, a name that reaches a project file (`paths`), a builtin
   without its `@types` package, an empty name or one with a space, a `resolution-mode`, an unknown
   module format, a blocked option. A relative name or a `typeRoots` entry in the project keeps the
   concern of AD-353 and AD-354, and a file with a syntax error keeps its gap.

**Reason.** An unproven directive must not read as complete. The proven edge already depends on
`node_modules`, so a gap for a package that is not installed adds no new install dependence.

**Not done.** `path` and `lib` forms (AD-353). Reading `typeRoots` outside `node_modules`.

**Price.** Against `main`: an installed package turns PASS into FAIL for a rule that forbids it, and
each unproven leading directive turns PASS into UNKNOWN. The golden reply `synthetic-esm-forms`
gains one gap and its evidence (`types="node"`), re-recorded with a reason. The 151 corpus cases
keep all 1172 verdicts; the fixture matrix and both architecture pins do not move. 4.0.1 against the core on
23 plants: no row is PASS in the core where 4.0.1 is FAIL or UNKNOWN for a leading directive; the
core is FAIL where 4.0.1 is UNKNOWN (an installed package) and where 4.0.1 missed the upper-case tag.

**Mutation rows** (`tests/test_cli_native_ts_reference_types.py`). Without the position rule,
`after-code` turns FAIL. Without the `@types` candidate, the three `@types` plants turn PASS.
Without the gap, six plants turn PASS (not installed, builtin, `resolution-mode`, space, empty
name, a name that `paths` maps to the project). Without the `resolution-mode` check in
`imports.rs`, nothing turns: `target()` gaps it too (a second guard).

**Tests.** `tests/test_cli_native_ts_reference_types.py` (11 edges, 3 silent, 9 gaps),
`native/typescript/src/jsdoc_tests.rs`.
