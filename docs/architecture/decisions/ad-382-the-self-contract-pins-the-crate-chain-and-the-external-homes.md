# AD-382 The self-contract pins the crate chain and the external homes

**Status.** Accepted. It adds to AD-335 and AD-357 for epic #880, issue #1073 and #1075.

**Problem.** `make self-validate-native` pinned 10 rules to UNKNOWN. A planted `requires`
entry `eval -> report` plus a `use` gave no FAIL, because `complete_requires` allows what
`requires` lists. A new external crate, `std::fs` in a core crate, a language name in `report`
and a swap of one public item for another also gave no FAIL. #1075 holds the measurement.

**Decision.**
1. The core chain is core -> report -> eval -> model -> contract, store and facts. Ten
   `forbidden_dependency` rules forbid eval -> report, model -> eval, model -> report,
   contract -> model, eval, report and core, and model, eval and report -> core. They fail also
   when a `requires` entry allows the edge. `report -> eval` is allowed: the report seam adds it.
2. Each external crate has a stated home. `NATIVE-EXTERNAL-COMPLETE` (`complete_external_scope`)
   fails on an import of a crate that no rule names. Ten new `external_dependency_scope` rules
   name the homes of today: `toml` and `ruff_text_size` only in their modules of the Python
   collector, `proc_macro2` only next to `syn`, and the other crates by crate. No TOML parser is
   in model, eval, report or core.
3. These rules stay tests until a Rust rule kind can say them (`tests/native_rules_support.py`):
   - (a) System access of model, eval, report and core: a path or a `use` of `std::fs`, `env`,
     `net`, `process` and `os`, of `std::io::{stdin, stdout, stderr}` and of
     `std::time::{SystemTime, Instant}`, also as `::std`, in a `use` group, under an alias of
     `std` or of the module; and each call of a file method of `Path` (`exists`, `try_exists`,
     `is_file`, `is_dir`, `is_symlink`, `metadata`, `symlink_metadata`, `read_dir`, `read_link`,
     `canonicalize`), by method name. The pin is the core binary: `std::env`, `std::process`,
     `std::io::stdin` and `std::io::stdout` in `core/src/main.rs`, one each. A contract rule
     cannot say it: `dependency` must be a crate name, and `std` gives 340 hits.
   - (b) No language name in model, eval, report and core, subdirectories and comments included.
     The doc comments of `report` name the Python checker and the Rust core. The pin holds
     these six names exactly. No Rust rule kind reads an identifier or a comment.
   - (c) Each declared `requires` follows one crate order. A base crate requires only a base
     crate of a lower level (facts, pytext, build, dart-grammar < snapshot, wire, store). The
     contract crate requires nothing. A chain crate requires a base crate or a lower chain crate.
     Nothing requires the core or model-barrier. A collector requires only base crates. No crate
     requires a collector of another crate. A crate outside the order fails. A
     `forbidden_dependency` that names a collector or a base crate keeps 27 to 65 more pair gaps
     (AD-357 point 5), so this test holds those directions until #1075 item 1.
   - (d) `tools/rust_api.py` lists each public part of a library by kind, module and name, with
     the signature of a `fn`, public fields with their type, and variants
     (`native/api_baseline.json`). A swap and a changed signature fail. Run
     `python tools/rust_api.py --write`, then name each changed line in the PR.
4. Each rule and test fails on a planted violation in a copy of `native/`. The contract rules
   share two self-check runs (`tests/test_native_self_contract.py`, about 40 s, in
   `make native-check` only): each chain rule in two code forms and with a matching `requires`.
5. The forbidden rules name `eval`, `model`, `core` and `contract`, so the host keeps four
   pair gaps that it dropped before. `native/expected-gaps.json` pins them exactly.
6. The gate line of `tools/native_expected.py` prints the counts (PASS, FAIL, UNKNOWN, pinned
   gaps, violations) and the file:line of the first findings; a pinned gap is a multiset member.

**Rejected.** (a) `layer_order` for the chain: it reads only `requires`, needs schema 2.3.0 and
keeps every pair gap (110). (b) A forbidden rule for each pair, also for collectors: 53 rules,
110 gaps. (c) A component for each file of `native/python`: about 9 500 lines; `module_layers`
is #1075 item 6. (d) `dependency: "std"`: every crate uses `std`.

**Limit.** Test (a) is a text scan. It does not see a system access through another crate, a
method on a value whose type it does not name (except the listed `Path` methods), a macro
(`eprintln!`, `include_str!`) or an io trait method; an own method with a listed name is a hit
that a pin must name. The API list cannot tell two `pub fn` of one name in two `impl` blocks of
one file apart. AD-389 moves `Module` below `survey` and holds the Python collection spine with
forbidden-direction rules. A trait impl in a third module stays a silent miss (AD-357). The facade
semantics of an import-level check: a user depends on the module that it names, not on the type
flow. So a method on a value that a factory of an allowed module returns gives no edge and no
gap, and a `pub use` through an allowed module is not followed to its origin (ts-dump can name
`crate::collect::Alias` of `crate::resolve::Resolver` without a `requires` of ts-resolve). "B
reaches a type of A only through facade C" needs the interface rule kinds of #1075 (product gaps).

**Tests.** `tests/test_native_self_contract.py`, `tests/test_native_self_rules.py`,
`tests/test_native_core.py` (language names), `tests/test_rust_api.py`,
`tests/test_native_contract_rules.py`, `tests/test_native_expected_gaps.py`.
