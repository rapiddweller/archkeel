# AD-634 Each collector states the effect of its gaps

**Status.** Proposed. Part of #880, closes #1321. It extends AD-564 (the model holds a rule only with a gap whose effect meets what the rule reads).

**Reason.** On a real project 78 coverage gaps held all 479 rules: no gap stated an effect, so each one left the whole scope unknown. AD-564 lets a gap state its effect; this record states it for each gap kind that a collector can bound, and adds the one effect that a file gap needs.

**Decision.**
1. `GapEffect::Layout { modules }`: the file and the place in the layout (`L`) of each module are not proven; its code is read. It holds `root_layout` when the module is below the root, and `complete_assignment` when the module is below the source (`layout::check`, `assignment::check` read only these names). No other rule reads `L`: the receipts of `complete_requires`, `interface_boundary` and the cycle rules check the scan roots in the core (`roots.covers`, `roots.under`). The run fails with any gap, also a layout gap.
2. An unresolved import is named by a gap with an effect only when that effect leaves the code of its source unknown (`modules` of the source, or `every_module`): the same site, or a gap that cites each evidence of the import. An effect on the edges alone does not name it, because the import can bind or re-export a name. Each other unresolved import keeps the whole scope unknown, as before.
3. The effect of each gap kind. The strict owner decision of AD-564 holds: a site that can run code that the scan cannot see states `every_module`.

| Collector | Gap | Effect | Why |
|---|---|---|---|
| Python | `dynamic_import`, `import_system_change` | `every_module` | unseen code (AD-564) |
| Python | `project_module_not_found`, `relative_import_beyond_top` | `every_module` | the import fails, or loads a file that the scan does not see: unseen code |
| Python | `star_import`, `reexport_ambiguity` | `modules` of the source | AD-564 |
| Python | `module_outside_layout` | `layout` of the module | the survey read the module; its top package lies above the scan root |
| Python | each other kind (`duplicate_module`, `stub_or_compiled_module`, a parse failure, ...) | none | the module is not in the reply, or its code is not read |
| TypeScript | a computed key that can write any global | `every_module` | no module proves that a free standard name is the standard one; the files stay known |
| TypeScript | each other kind | none | an unresolved module or an augmentation can change a module that the gap does not name |
| Dart | `Workspace`, `PathDependency`, `PackageConfig` | `every_module` | a `package:` URI of any library can name another file; the files below the roots and their names stay known |
| Dart | a directive (`TargetMissing`, `TargetNotSelected`, `TargetOutside`, `UnsupportedUri`, `UriNotLiteral`), `Mirrors`, `Isolate` | `modules` of the library of the site | Dart code cannot change another library; an isolate shares no library with its spawner |
| Dart | a part, `NestedPackage`, `TargetUnparsed`, `ParseBudget` | none | the gap can put code or a file in a library that it does not name |
| Rust | a pair gap | none (AD-384 scopes it to one pair) | |
| Rust | a module gap | none | some module gaps change other crates: an exported macro expands where it is called |

**Why it is sound.** AD-564 shows that a PASS on the written facts is a PASS on the true facts when each effect names all that its gap can change (duty 4). Each row above names that set or names none. A kind without an effect keeps the behaviour from before.

**Measured** (main `78aa72472` before, this change after; rules PASS/FAIL/UNKNOWN):

| Project | Before | After | What holds the other rules |
|---|---|---|---|
| pydantic v2.14.3 (5 rules) | 0/0/5 | 1/0/4 | 55 `every_module` and 108 `modules` gaps hold the 3 forbidden rules and `REQUIRES` |
| graphql-js v16.15.0 (8 rules) | 0/0/8 | 1/0/7 | 2 `every_module` gaps (a computed key) hold the forbidden rules and `REQUIRES` |
| bazel_worker (4 rules) | 0/0/4 | 1/0/3 | the `workspace` key of `pubspec.yaml` (`every_module`) |
| path (2 rules), FastAPI 0.163.0 | PASS | PASS | no gap |
| self system run | PASS | PASS | no gap |

**Rejected.**
- A Rust module-gap effect by its reason text: the reasons are prose, and some of them change other crates. Closed codes for the Rust concerns come first.
- `edges` for an unresolved project import: the import can load unseen code.

**Tests.** `gap_effects_tests.rs`, `gap_class_tests.rs`, `imports_effect_tests.rs` (model); `gap_effect_tests.rs` (eval: the layout effect holds the rules of the files and no other rule); `effects_tests.rs`, `layout_tests.rs` (Python); `names_tests.rs` (Dart); `test_cli_python_gap_effects.py`, `test_cli_native_python_imports.py`, `test_cli_gap_effects_languages.py` (CLI plants: a gap in the read set keeps UNKNOWN, a gap outside lets the rule decide, a seen violation stays FAIL beside a gap).
