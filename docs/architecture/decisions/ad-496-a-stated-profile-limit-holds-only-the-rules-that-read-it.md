# AD-496 A stated profile limit holds only the rules that read it

**Status.** Proposed. Part of #880. It amends item 3 of AD-426 and item 6 of AD-468.

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

No other rule kind reads a symbol, `public` or `through` fact. `pair_gaps` reads only whether a
`requires` entry has a `through` list, and that is a contract fact.

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

**Rejected.**
- A hand table of rule kinds beside the evaluator. It can become stale without a test failure.
- Undecided positions for each import. A rule without a matching import would pass, and the
  collector writes `symbols_known: true` although it states that it reads no symbol.
- Keep a hold in `Scope::run`. `run_complete` needs every rule PASS, so no test can reach it.

**Limits.** G-dart goes from 0/0/10 to 9/0/1 and H-uml-dart from 0/0/4 to 1/0/3. One new PASS
has no PASS in 4.0.1: G-dart `COMPONENT-NO-CYCLES` (4.0.1: UNKNOWN). 4.0.1 proves a cycle scope only
for a profile with project import closure or for Python. The core gives the Dart receipt by the
layout of AD-468 item 5. The profile limit hid that difference before. No other fixture row changes.

**Tests.** `tests/test_cli_native_stated_limits.py` (release core and default CLI: each feature
and reader gives UNKNOWN on its reader and PASS on each edge rule; a forbidden edge stays FAIL; a
symbol `public` entry without a reader holds no rule). `native/model/src/limits_tests.rs`.
