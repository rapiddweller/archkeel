# AD-468 Dart import rules use the bound import survey

**Status.** Proposed. Part of #880. It extends AD-406, AD-426, AD-450 and AD-454.

**Decision.**
1. `archkeel-collect` links `native/dart` and runs `typed_reply` in the process of the core.
   The request is 8.0.0 with the resolver `{"language": "dart"}`. `exclude_test_sources` is refused by name.
2. `collect` reads each input again: its bytes must have its digest, and the source digest must be
   the digest of the input listing. Else the run is refused (`python::reread`, shared with AD-450).
3. The store accepts a Dart reply only as the import survey: the sections `imports` and `unknowns`,
   no feature, no construct, coverage gaps equal to `unknowns`, a built-in target `dart.<library>`,
   an external target of one package that is not the namespace, no unresolved target, and import
   or export records without known symbols. Each selected file must be a module file, an owned
   part or the file of a gap.
4. A part is an owned file: `Facts.owned_files` (linked replies only) names its path, the module of
   its path and its owner. The store checks that the owner is a module and that the path module is not.
   The model makes the scope incomplete (`Cause::OwnedFileOwner`) when the components that claim
   the path module differ from those that claim the owner. This closes the open decision of AD-454.
5. Layout: a Dart module is the namespace and the path below its scan root, so the parent rule of
   `Layout::ProjectFiles` holds and `Scope::scan` can give the receipt. The scope label is `<root>/**`.
   A part counts as a parsed file; `pubspec.yaml` is a resolution input, not a read source.
6. The linked reply states that symbol selectors and `interface_boundary` are not supported (AD-426).
   Such a contract part is a profile limit, and a profile limit makes each rule of the run UNKNOWN.
7. Each gap of AD-454 is a coverage gap without a module. It makes the scope of the run incomplete:
   each rule is UNKNOWN, not only the rules of the component of the file. This is sound because a
   missing edge, part or package mapping can lie in any component, and no gap names a pair.
8. Targets are read by module scope (`TargetMarks::ByModule`), as 4.0.1 reads Dart imports.
9. `Scope::complete`, `Scope::pass_run` and `ModelTree::pass_run` stay the only PASS makers. The
   model, the evaluator and the report name no language.

| Fixture | Before | Core after (P/F/U) | First UNKNOWN cause | 4.0.1 |
|---|---|---|---|---|
| G-dart | refused | 0/0/10 | profile limit `INTERFACE-BOUNDARY` | 9 PASS, 1 UNKNOWN |
| H-uml-dart | refused | 0/0/4 | profile limit: symbol selector of `presentation` | 5 PASS |
| I-flutter-shop | refused | 1/0/5 | mounted `complete_requires`: a module has not one owner | 6 PASS, 1 UNKNOWN |
| J-compass | refused | 0/0/6 | `DartWorkspace`, `DartPathDependency` | exit 2 |

The UML target is not decided by the core (`uml_target`, no slice ports it). The mounted
`complete_requires` receipt and the interface and symbol rules of a Dart project are not decided either.

**Reason.** Dart projects had no verdict on the core. The import rules need only the import graph,
the module files, the part owners and the scan roots. Each case that can hide an edge is UNKNOWN.

**Rejected.** An exported macro for `provenance()` and `TEST_FEATURES`: the self-check cannot read
it and gives 0 PASS. `Provenance::native` is the shared helper; `env!` must expand in each crate.
A file fact for a part with the module of its owner: a module has one file. A gap for each part:
a part in the component of its library hides no edge.

**Limits.** The core trusts the linked collector for a complete file list (AD-406). This is not an
atomic snapshot: a file that changes during the scan refuses the run.

**Tests.** `tests/test_cli_native_dart_imports.py`: PASS, FAIL with file, a part in the component of
its library and in another one, each gap name of AD-454 and the refused test exclusion.
`native/collect/src/dart_tests.rs` plants changed digests and each refused store claim.
