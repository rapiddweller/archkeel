# AD-390 The native Dart declaration layer keeps the Python records

**Status.** Accepted. Epic #880, Dart slice 4b. It follows AD-387.
AD-388 is the highest number on Main and open PRs at the start. Reserve highest plus two.

**Decision.** Port declaration assembly, not discovery again. Compare the real
`_Collection._declarations` boundary with the same prepared files and constructor resolutions.
The test dump accepts typed syntax and typed parameter resolutions. These are layer inputs,
not a collector reply. The native parse already supplies syntax. Slice 4c supplies resolution.
The store still refuses Dart replies. No Python production file changes.

**Cut.** All ranges refer to `src/archkeel/analyzer/dart/collect.py` on `5f2d4511b`.
`_declarations` 290–296 (7); `_definition` 385–457 (73);
`_publish_definition` 459–501 (43); `_class_definition` 503–580 (78);
`_member` 582–654 (73); `_owner_definition` 656–664 (9);
`_member_parameters` 666–689 (24); `_attribute` 691–720 (30);
`_meta` 722–755 (34); `_parameters` 757–769 (13);
`_resolved_parameters` 771–782 (12); `_add_symbol` 784–788 (5);
`_record` 1417–1436 (20); `_inventory` 1450–1457 (8).
Total: 529 function lines, 34.4% of 1 538 lines. Shared evidence and gap helpers stay shared.

**Python rules and oddities, ported literally.**
1. Visit files by path, then definitions in syntax order. Publish methods before their class.
2. Keep a declaration identity made before the variable kind or accessor name changes.
3. Map interfaces, mixins and enums to class records. Keep their distinct class kinds.
4. An accessor adds `::getter` or `::setter` to its name, but not its top-level identity.
5. A setter with no return type returns `void`. A constructor returns its generic owner type.
6. A constructor uses the first matching owner definition, even with duplicate names.
7. Use resolved constructor parameters; mark super formals with their original source evidence.
8. Optional raw parameters with no default use `null`; resolved parameters keep their default.
9. Enum attributes are static constants with null values. Fields use initializers, not literals.
10. Keep empty inventories as complete. Unsupported extensions give a gap and no symbol.
11. The last symbol of a qualified name wins the name index. Keep every symbol in the list.
12. A function scope ends at the next definition start, or the source byte length.
    A method scope uses the first matching owner's whole span.

**Stricter cases, a closed list.** `DeclarationWorkLimit` stops the whole layer above
16 777 216 work units. No partial symbols or indices escape. Charge input bytes, scans,
copies and sort comparisons before the work. `DeclarationInputGap` stops duplicate paths,
inconsistent enum arrays and missing or repeated constructor resolutions. Never guess a formal.
Each stop gives a named gap. These are internal layer limits, not new resolver behavior.

**Remaining work, at most three slices.**
1. 4c ports `resolve.py` (2 013 lines): URI and part ownership, name and site binding,
   constructors and inherited formals. It supplies the prepared files and parameter resolutions.
2. 4d ports the remaining collection: imports, bases, sites, duplicate checks, language
   overrides, inventory completion, coverage and the final reply. It connects this layer.
3. 5 compares the complete reply, closes the Windows snapshot race of AD-369, then enables Dart.

**Rejected.** Port discovery and pubspec reads again: AD-365 already owns them. Guess constructor
types from syntax: redirects and super formals need the resolver. Enable a partial Dart reply:
missing records could give a false PASS. Copy Python logic into the parity tool: call the function.

**Limits and tests.** `tools/dart_declarations_parity.py` compares canonical bytes of all layer
outputs. `tests/test_collector_native_dart_declarations.py` checks hostile inputs, exact work,
bounded generated input and named stops. Filesystem parity checks exercise discovery separately.
Fault injection runs only in a throwaway worktree. Tests do not claim full Dart reply parity.
