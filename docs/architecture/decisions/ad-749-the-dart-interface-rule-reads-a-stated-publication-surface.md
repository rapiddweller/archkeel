# AD-749 The Dart interface rule reads a stated publication surface

**Status.** Proposed. Part of #880, closes #1536. It amends AD-468 (the Dart survey makes no interface
statement) and AD-500 (which feature holds which rule).

**Reason.** In 4.0.1 the G-dart rule `INTERFACE-BOUNDARY` was PASS. In 5.0 it was UNKNOWN:
"incomplete scope: interface_boundary: incomplete publication surface". The Dart survey stated
`interface_boundary` and `dependency_symbols` as `Unsupported` and wrote no name of an import.

A first fix stated `interface_boundary` as `Supported`. The safe plant then stayed UNKNOWN, because
`limits::stated_hold` holds each interface rule that reads a `public` symbol entry while
`dependency_symbols` is `Unsupported` (AD-500). The survey cannot state `dependency_symbols` as
`Supported`: a directive without `show` binds names that no record lists, and no reader of that
feature has a proof for such a record. A `Supported` statement would release each of them, so a
missed proof would give a false PASS.

**What reads what.** These are the two features, split by their readers:

| Statement | Reader | What it needs from each import |
|---|---|---|
| `dependency_symbols` | `direction::forbidden` (`target_symbol`), `direction::crossings` (`through` symbol port) | every name that the import gives |
| `publication_surface` (new) | `interface::assess`, `interface::interface_publications` | each name that it binds with the first hop of its route, or else no name (it binds every name of its target); whether each route is complete; each name that a re-export publishes outside the package |

`interface::assess` already judges each import by its own record. An unread binding, `*`, or an
open route that the component does not list is a named gap. So the interface rule does not need
the names of every dependency. It needs only the binding of each import that crosses.

**Decision.**
1. `ProfileLimits` gets a third statement, `publication_surface`. The store refuses it without a
   `Supported` interface statement. TypeScript, Python and Rust state it as `Unsupported`, so their
   behavior does not change.
2. `limits::stated_hold`: with `publication_surface` `Supported`, a `public` symbol entry no longer
   holds an interface rule. A `target_symbol` rule still holds it: `interface_crossings` drops each
   import that such a rule rejects, and that verdict reads the names of every dependency. If the
   rule stayed UNKNOWN while it dropped the import, the interface rule could pass a crossing it
   never judged.
3. The Dart survey states `interface_boundary` and `publication_surface` as `Supported` and keeps
   `dependency_symbols` `Unsupported` (`import_survey/binding.rs`):
   - The combinators apply in their order. `show` keeps only its names and `hide` removes its names.
     Each name that remains gives one record. It has the symbol, the binding, the route
     `<target>.<name>`, and `symbols_known`.
   - No `show`, or each `show` name hidden again: one record without a name, with `symbols_known`
     false, as 4.0.1 writes it. It binds every name of its target, and the survey reads no use.
   - The route is complete only when the target is a selected local library, and neither it nor one
     of its parts has an `export`. This holds for a named record and for a record without a name.
     Any other first hop that `public` does not list is a gap, not a FAIL, because a later hop
     through an `export` may be listed.
   - An `export` in a library below `lib/` and not below `lib/src/` states `published_as`, with the
     name or `*` (the package layout of `dart.dev`). Another package can import only such a library.
     So AD-608 judges each name that it publishes. An `export` in `lib/src/`, `test/` or `bin/`
     publishes nothing outside the package.
4. `interface::assess`: with a stated publication surface, a record without a name and without
   known names is judged by the 4.0.1 rule AD-97. It is PASS when `public` lists the module. It is
   FAIL only when no name of the module can be public: no `module:name` entry, and a complete
   route, so no re-export can pass on a public name of another module. Any other case is a gap.
   For every other profile such a record stays an unread binding (AD-428).
5. A file with a syntax error has no module (`Kind::Unknown`), so a `show` list that the parse reads
   only in part never gives a record.
6. The record of a whole namespace keeps its id. A named record adds the name to its id. The pinned
   edge sets of the fixtures do not change. G-dart has 24 records on its 22 edges.

**Kept gaps.**
- A route through an `export` is not followed: a first hop that is not listed gives UNKNOWN
  (plant `facade-route-open`; the true verdict there is FAIL).
- An `export` without `show` publishes `*`. AD-608 cannot judge it, so the rule is UNKNOWN (plant
  `publication-glob`).
- Every rule that reads `dependency_symbols` stays held for Dart: `target_symbol`, a `through`
  symbol port, and an interface rule next to a `target_symbol` rule (plant `target-symbol-holds`).
- An import without `show` of a module with a `module:name` entry is UNKNOWN (plant
  `whole-named-entry`), and so is one of a library that re-exports (plant `whole-through-export`),
  as in 4.0.1. `show` is the precise form.
- `show A hide A` binds no name, but it is written as a whole namespace (as in 4.0.1). `dart analyze`
  warns about it.

**Plants.** These are in `tests/test_cli_native_dart_interface.py`. `dart analyze` (Dart 3.12)
accepts each one. `hide-then-show` has two style warnings, and a use of the hidden name in that
plant is an error, so the order rule is the rule of the language. The safe plant `show-public` is
PASS, and the unsafe plants `show-secret`, `show-both`, `prefix-secret`, `deferred-secret`,
`whole-unlisted` and `publication-unlisted` are FAIL. Before this change, `interface::receipt`
refused each Dart interface rule (stated `Unsupported`), so each plant was UNKNOWN.

**Undo.** Set the Dart `publication_surface` and `interface_boundary` back to `Unsupported` in
`import_survey/reply.rs`. The records keep their names, and every interface rule is UNKNOWN again.
