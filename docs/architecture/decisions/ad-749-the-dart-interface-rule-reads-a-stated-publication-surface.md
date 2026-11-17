# AD-749 The Dart interface rule reads a stated publication surface

**Status.** Proposed. Part of #880, closes #1536. It amends AD-468 (the Dart survey makes no interface
statement) and AD-500 (which feature holds which rule).

**Reason.** G-dart `INTERFACE-BOUNDARY` was PASS in 4.0.1 and UNKNOWN in 5.0 ("incomplete
publication surface"): the Dart survey wrote no name of an import. Stating `interface_boundary`
alone does not help: `limits::stated_hold` holds each interface rule with a `public` symbol entry
while `dependency_symbols` is `Unsupported` (AD-500). The survey cannot state `dependency_symbols`:
a directive without `show` binds names that no record lists, and no reader of that feature has a
proof for such a record. A `Supported` statement would release each reader.

**What reads what.**

| Statement | Reader | What it needs from each import |
|---|---|---|
| `dependency_symbols` | `direction::forbidden` (`target_symbol`), `direction::crossings` (`through` symbol port) | every name that the import gives |
| `publication_surface` (new) | `interface::assess`, `interface::interface_publications` | each bound name with the first hop of its route, or no name (it binds every name of its target); whether the route is complete; each name that a re-export publishes outside the package |

**Decision.**
1. `ProfileLimits` (now `facts/src/envelope/limits.rs`) gets `publication_surface`. The store refuses
   it without a `Supported` interface statement. TypeScript, Python and Rust state `Unsupported`.
2. `limits::stated_hold`: with a stated surface, a `public` symbol entry no longer holds an
   interface rule. A `target_symbol` rule still holds it: `interface_crossings` drops each import
   that such a rule rejects, and that verdict reads the names of every dependency.
3. Dart (`import_survey/binding.rs`) states `interface_boundary` and `publication_surface`, and keeps
   `dependency_symbols` `Unsupported`:
   - The combinators apply in their order (`show` keeps, `hide` removes). Each name that remains
     gives one record: symbol, binding, route `<target>.<name>`, `symbols_known`.
   - No `show`, or each `show` name hidden again: one record without a name and with
     `symbols_known` false, as 4.0.1 writes it. It binds every name of the target.
   - A route is complete only when the target is a selected local library, and neither the library
     nor a part of it has an `export`.
   - An `export` in a library below `lib/` and not below `lib/src/` states `published_as` (the name,
     or `*`). Only such a library can be imported from another package (the `dart.dev` package
     layout), so AD-608 judges what it publishes.
4. `interface::assess`: with a stated surface, a record without a name and without known names is
   judged by the 4.0.1 rule AD-97: PASS when `public` lists the module; FAIL only when no name of
   it can be public (no `module:name` entry and a complete route); else a gap. For every other
   profile such a record stays an unread binding (AD-428).
5. A file with a syntax error has no module (`Kind::Unknown`), so a `show` list that the parse reads
   only in part never gives a record.
6. A record without a name keeps its id. A named record adds the name to its id. The pinned edge
   sets do not change; G-dart has 24 records on its 22 edges.

**Kept gaps.**
- A route through an `export` is not followed (plant `facade-route-open`, truly FAIL).
- An `export` without `show` publishes `*`, which AD-608 cannot judge (plant `publication-glob`).
- Each reader of `dependency_symbols` stays held, and so does an interface rule next to a
  `target_symbol` rule (plant `target-symbol-holds`).
- An import without `show` of a module with a `module:name` entry, or of a library that re-exports,
  is UNKNOWN as in 4.0.1 (plants `whole-named-entry`, `whole-through-export`).
- `show A hide A` binds no name, but it is written as a whole namespace (as in 4.0.1).

**Plants.** `tests/test_cli_native_dart_interface.py`. `dart analyze` (Dart 3.12) reports no issue
for each plant. The exception is `hide-then-show`, which has two style warnings, and a use of the
hidden name there is an error. PASS: `show-public`, `hide-then-show`, `whole-listed`,
`facade-listed`, `publication-in-src`. FAIL: `show-secret`, `show-both`, `prefix-secret`,
`deferred-secret`, `whole-unlisted`, `publication-unlisted`. Before this change,
`interface::receipt` refused each Dart interface rule, so each plant was UNKNOWN.

**Undo.** State the Dart `publication_surface` and `interface_boundary` as `Unsupported` in
`import_survey/reply.rs`. Each Dart interface rule is then UNKNOWN again.
