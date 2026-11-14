# AD-496 A stated profile limit holds only the rules that read it

**Status.** Proposed. Part of #880. It amends item 3 of AD-426, items 5 and 6 of AD-468, and AD-454.

**Reason.** The linked collector can state `dependency_symbols` or `interface_boundary` as
`Unsupported` (Python in AD-450, Dart in AD-468). AD-426 turned each such statement into a
certain profile limit, and a profile limit is a coverage failure of the run: each rule of the run
was UNKNOWN. A symbol or interface fact cannot change a rule that reads only module-level import
edges. G-dart gave 0 PASS, and the released 4.0.1 gives 9.

**Which rule reads which feature.** This comes from the code that reads each fact:

| Feature | Reader | Rules that it holds |
|---|---|---|
| `dependency_symbols` | `direction::forbidden` reads `target_symbol` | the `forbidden_dependency` rule with a `target_symbol` |
| `dependency_symbols` | `direction::crossings` reads each `through` port with a symbol | each `complete_requires` rule |
| `dependency_symbols` | `interface::assess` reads each `public` entry with a symbol; `interface_crossings` reads the verdicts of each `target_symbol` rule | each `interface_boundary` rule |
| `interface_boundary` | `interface::receipt` | each `interface_boundary` rule |

No other rule kind reads a symbol, `public` or `through` fact (`pair_gaps` reads only the contract).

**Decision.**
1. A stated `Unsupported` feature is no longer a limit of the run (`limits.rs`).
2. `limits::reads` states for each rule kind what it reads besides the module-level edges. Its
   match has no catch-all arm, so a new rule kind does not compile until it states what it reads.
   `rule_limits` and `limits::symbol_reader` both read it. `Scope::complete` holds a rule with a
   symbol reader when the collector states `dependency_symbols` as `Unsupported`. The cause is the
   same `ProfileLimit` with the subject of the selector.
3. `interface::receipt` already refuses an `interface_boundary` rule without a `Supported` statement,
   on the evaluation path of that rule. It is the only check for this feature.
4. A missing statement (a wire reply) and a `Supported` statement keep their AD-426 behavior.
   The other profile limits (undecided kinds, constructs, declarations) stay limits of the run.
5. `Scope::complete`, `Scope::pass_run` and `ModelTree::pass_run` stay the only PASS proofs.
   `run_complete` still needs a PASS of each rule, so a held rule holds the run status.

**Why each feature can be per rule.** Neither feature can hide a module-level edge. The Python
survey writes one import record for each binding, and it resolves the target module from the file
set and not from the symbol statement. A Dart `show` or `hide` list does not change the imported
URI. A re-export route is not an import edge in the core or in 4.0.1. So a rule that reads edges
sees the same edges with or without these features.

**A second local package (review finding B1).** A cycle a -> b -> o -> a through
`package:other/o.dart` gave `COMPONENT-NO-CYCLES` PASS (4.0.1: UNKNOWN). The survey read the keys of
`pubspec.yaml` line by line, so a quoted, flow, explicit (`?`) or escaped `path` key and a quoted
`workspace` or `resolution` key were no gap. A `pubspec.yaml` above a scan root was never read.
6. The workspace has no YAML parser, so `package.rs` reads words. Without a backslash, the text of a
   YAML scalar is in the file as it is, and a folded line break gives a space. So each word `path`,
   `workspace` or `resolution` outside a comment line is a gap, and a backslash is a gap.
7. Each package file in a directory above a scan root is a gap (`DartNestedPackage`).
8. `Profile::cycle_scope` is `Unproved` for Dart, so a Dart cycle rule has no receipt. A proof that
   releases it: the survey resolves each `package:` URI from a complete package map that it reads
   (each `pubspec.yaml` of the project with its path and workspace members), with a plant for each
   YAML form of a local package. `docs/known-limits.md` names this limit.

**Rejected.**
- A hand table of rule kinds beside the evaluator. It can become stale without a test failure.
- Undecided positions for each import. A rule without a matching import would pass, and the
  collector writes `symbols_known: true` although it states that it reads no symbol.
- Keep a hold in `Scope::run`. `run_complete` needs every rule PASS, so no test can reach it.

**Limits.** G-dart 0/0/10 -> 8/0/2 and H-uml-dart 0/0/5 -> 4/0/1 (4.0.1: 9/0/1 and 5/0/0).
M-review-workflow (Python) 0/0/12 -> 6/0/6 (4.0.1: 12 PASS). Each new PASS is PASS in 4.0.1. One
behavior change has no 4.0.1 PASS: a TypeScript reply without `script-globals-v1` states
`dependency_symbols` as unsupported, and 4.0.1 holds each rule of that run. The core now holds only
the rules that read a symbol selector; the same plant without the selector is PASS in 4.0.1 too.
A word in a `pubspec.yaml` value or description gives a gap without need.

**Tests.** `tests/test_cli_native_stated_limits.py` (Python and TypeScript plants of each feature
and reader), `tests/test_cli_native_dart_packages.py` (the eight YAML forms, a package file above a
scan root, the held cycle rule), `native/model/src/limits_tests.rs`, `package.rs` unit tests.
