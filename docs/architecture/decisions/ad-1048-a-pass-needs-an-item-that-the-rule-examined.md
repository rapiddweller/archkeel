# AD-1048 A PASS needs an item that the rule examined

Status: accepted. It amends [AD-428](ad-428-the-interface-import-verdict-needs-a-known-binding-and-publication-proof.md).

A false PASS is the worst defect. A rule that names nothing the scan saw has nothing to examine,
so its PASS is empty. This change closes three such cases and one real hole (#1965).

## Decision

Each rule below is UNKNOWN, with the stated reason, when its subject is absent.

1. `external_dependency_scope`: some import of a selected module must name the dependency.
   Reason: "the named package matches no import". The scan gives the import root, so a
   distribution name (`PyYAML` for `import yaml`) or a typo (`requestz`) is UNKNOWN. The contract
   has no field that maps a distribution to an import name, so the core does not guess one.
2. `forbidden_dependency` with `target_symbol`: an import of the target must name the symbol, or
   a module-level symbol of this name must be declared in a target module. Reason: "the target
   symbol is named by no import and declared in no target module". A typo (`gg` for `g`) is UNKNOWN.
   A symbol that exists and is not used still PASSes.
3. `interface_boundary`: at least one component must declare `public`. AD-428 skips a target
   without `public`, so with none declared the rule examined nothing. Reason: "no component
   declares a public interface". This is the smallest change that keeps the design of AD-428: the
   skip stays, and the verdict states that it is vacuous. A contract with one `public` entry
   keeps its verdict.
4. Python: a code object that a function hands out by a literal name is an import door (#1965).
   `f.__code__ = f.__code__.replace(co_names=...)` makes `import json` import another module.
   The attributes `__code__`, `f_code`, `gi_code`, `cr_code` and `ag_code` give `dynamic_import`,
   unless a scalar field is read at once (`f.__code__.co_name`, `co_filename`, `co_argcount`, and
   the like). The strings of these names are door strings, so `getattr(f, "__code__")` and
   `setattr(f, "__code__", c)` give the same gap. `co_consts` and `co_names` are not scalar
   fields: they can hold a nested code object.

## Rejected

- A table that maps `PyYAML` to `yaml`: the contract does not state it, and a wrong entry gives
  a PASS.
- A `vacuous` flag next to PASS for case 3: a reader can miss a flag, and a PASS must stand alone.
- A door for `__defaults__`, `__closure__` and `__globals__` writes. They hand in values, and a
  module object has to come from an import that the scan already sees. `__globals__` is a door
  already. The write of a code object is the hole.

## Limits

- Case 1 and 2 give UNKNOWN for a rule that is true and unused. This is the price of evidence.
- The `target_symbol` proof reads the names of the symbol facts and the imports. It does not read
  names that a macro or a star import adds; a star import was UNKNOWN before (AD-668).
- Computed names are open: `getattr(f, '__co' + 'de__')`, `f.__getattribute__(...)`, a variable
  name and a `dir()` filter still give PASS (#1967; `docs/known-limits.md`). The owner decides.
- The 17 `external_dependency_scope` rules of the native self-check keep PASS: an import names
  each of their packages.
- A code object that code outside the scan roots rewrites is outside the scan (the premise).

## Checks

`tests/test_cli_vacuous_pass.py` plants each case and its control. `tests/test_cli_python_code_door.py`
runs five plants under CPython 3.12 (each imports `app.lib`) and three controls (each leaves it
unloaded). `native/model/src/edges_tests.rs`, `native/eval/src/external_tests.rs` and
`native/python/src/survey/hazards_inert_tests.rs` test the core. `tests/test_oracle_guard.py`
and `tests/oracle_support.py` make an oracle test fail, not skip, in CI, and fail a run in which
a selected oracle ran no test. `tests/test_collector_false_pass_hardening.py` plants violations
in TypeScript (node), Dart (`dart analyze`, `dart run`) and Rust (`cargo check`): none is PASS.
The native self-check keeps 89 PASS and 3 UNKNOWN; two pinned gaps are gone (18,391 remain).
The fixture `H-typescript` has no import of `@shop/transport`: its rule `EXTERNAL-SHOP` is now
UNKNOWN, and `fixtures/matrix.json` pins 8 PASS and 2 UNKNOWN.
