# AD-524 A leading `types` directive is a type-only edge to its package

**Status.** Accepted. Part of #880. Closes #686. It extends AD-274 rule 3 and AD-353.

**Problem.** `/// <reference types="vite/client" />` makes the compiler read the type package
`vite`, so the file depends on it as `import type "vite/client"` does. AD-274 observed the name as
a `types` entry and made no edge, so a rule on `vite` could PASS for a file that uses it. 4.0.1
gave UNKNOWN for each such directive (a gap, no edge), so the core was the less strict one.

**Decision.** One reader (`jsdoc::types_directive`, `concerns::type_directives`) and one step in
`imports.rs` (`type_directives`) turn a directive into a type-only reference of the form
`import_type`, at the place of the comment. The edge exists only when all of these hold:
1. The directive is before the first statement (a comment or a hashbang may come before it),
   in a TypeScript or a JavaScript file. A directive after code is ignored, as the compiler does.
2. The tag is `reference`, in any letter case (tsc lowercases it), and `types` is its only
   attribute. A second attribute (`resolution-mode`, `lib`, `path`) leaves the form as it was.
3. The name is plain: not empty, no leading `.` or `/`, no space, no backslash. A relative name stays
   the concern of AD-353.
4. The file has no syntax error and no `typeRoots` entry inside the project (AD-354).
5. The resolver, which reads `node_modules`, proves the name. The edge names the package. A name
   that the resolver maps to a project file (`paths`, `baseUrl`) gives the gap "Unobserved
   triple-slash reference: name", as a type root does. A name that is not proven (no package
   installed, a package that only `@types/<name>` holds, a builtin, an unknown module format, a
   blocked option) gives no edge and no gap, as before.

**Reason.** An edge needs a proof, so each unproven form keeps its old result. The compiler also
resolves the name by its own type lookup (`@types` first), which the resolver does not model, so
the resolver is asked for a hit in `node_modules` only.

**Not done.** A gap for a name that is not installed (the issue asked for it): the same project
would then change its result with the install state of a machine (AD-274). A lookup in
`@types/<name>`. A `path` or `lib` form. `resolution-mode`.

**Price.** Result against `main`: a leading directive with an installed package turns PASS into
FAIL for a rule that forbids the package, and a name that maps to a project file turns PASS into
UNKNOWN. Nothing else moves: the 151 corpus cases keep all 1172 verdicts and the fixture matrix
keeps its results. 4.0.1 against the core on 18 plants: the core is never PASS where 4.0.1 is
FAIL; it is FAIL where 4.0.1 is UNKNOWN (installed package), and PASS where 4.0.1 is UNKNOWN for
a package that is not installed (AD-274, unchanged).

**Mutation rows** (`tests/test_cli_native_ts_reference_types.py`). Without the position rule,
`after-code` turns FAIL. Without the single-attribute rule, `extra-attribute` turns FAIL. Without
the gap for a project file, `name-that-paths-maps-to-the-project` turns PASS. With an edge for it,
that plant turns PASS too.

**Tests.** `tests/test_cli_native_ts_reference_types.py` (8 edges, 7 silent, 4 gaps),
`native/typescript/src/jsdoc_tests.rs`.
