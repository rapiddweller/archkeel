# AD-1410: A bin that names the default main file is the main binary of a package without a library

Status: accepted. Closes #1952. Amends AD-784 and the module names of the Rust collector.

## Why

The Rust collector names the root of a crate `<namespace>.<package>` when it is the library, or the binary that has the
name of the package. Any other binary is `<namespace>.<package>.bin_<name>`. The `fd` project has the package `fd-find`
and `[[bin]] name = "fd" path = "src/main.rs"`. The collector named its modules `fd.fd_find.bin_fd.walk`. The draft of
`archkeel init` names them `fd.fd_find.walk` (it reads `src/main.rs` as the crate root). No component owned a module:
21 violations of `ASSIGNMENT-COMPLETE`, and the first verdict was FAIL, not UNKNOWN. The manifest also had two targets
for one file: the named bin and the default binary of the package.

## Decision

1. A `[[bin]]` whose path is `src/main.rs` replaces the default binary target. Cargo does the same.
2. In a package without a library one binary is the main one: the binary with the name of the package, else the binary
   of `src/main.rs`. Its module is `<namespace>.<package>`, and it is the primary root that other crates reach. Another
   binary is `bin_<name>`, so two roots never get one module name (a duplicate file id refuses the project).
3. A bin with another path stays `bin_<name>`. A package with a library keeps the library as the main target and names
   a bin of `src/main.rs` with another name `bin_<name>`.

The draft needs no change: it names the modules by the folder of the root file, as before.

## Counter-examples (`native/rust/src/crates_tests.rs`, `tests/test_cli_init_rust_named_bin.py`)

- The `fd` shape: a package `my-tool` with `[[bin]] name = "tool"` and `src/main.rs`. Before: 3 `ASSIGNMENT-COMPLETE`
  violations and FAIL. After: no violation, UNKNOWN, exit 2 (open decisions of the draft).
- A package `app` with `[[bin]] name = "tool" path = "src/main.rs"` and `src/bin/app.rs`: `app` is `ns.app`, `tool` is
  `ns.app.bin_tool` (unit test).
- A package with `src/lib.rs` and `[[bin]] name = "tool" path = "src/main.rs"`: the modules stay `my_app` and
  `my_app.bin_tool`.
- A package with a library, `src/main.rs` and no `[[bin]]`: unchanged (`bin_my_app`).

## Not done

- The real `fd` crate still has one FAIL on the first run: `COMPONENT-NO-CYCLES`. The code has a real cycle
  (`config.rs` uses `exec::CommandSet`, `exec/job.rs` uses `config::Config`). The onboarding page documents this FAIL.
- A module name of a crate with a `[[bin]]` of `src/main.rs` changes. A contract that names `bin_<name>` of such a
  crate must change.
