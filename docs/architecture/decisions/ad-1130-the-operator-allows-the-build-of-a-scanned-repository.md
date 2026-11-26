# AD-1130: The operator allows the build of a scanned repository

Status: accepted. Amends AD-1047. Closes #2054. The larger redesign stays in #1999.

## Why

`[scan] rust_type_reach = true` in the archkeel.toml of the scanned repository made the core run the pinned driver
and nine `cargo check` configurations on that repository. Cargo runs the `build.rs` and the procedural macros of
the repository. `--offline` is no sandbox. A repository cannot give operator trust to itself, so a scan of an
untrusted repository could run code from that repository.

## Decision

1. The trust boundary: the setting of the repository only asks for compilation. The operator allows it with
   one switch, the environment variable `ARCHKEEL_ALLOW_BUILD=1`. Any other value, or no value, does not allow it.
2. The name lives in one constant, `ALLOW_BUILD` in `native/collect/src/lib.rs`. The core reads it from its own
   process environment. It reads no file of the repository, and no file of the repository can set it.
3. Without the permission the core starts no cargo command. It writes the descriptor with the cause
   `type reach not allowed by the operator`. The worker keeps every trait-impl, destructor and receiver gap and
   names this cause. No PASS changes and the receipt names no `rust_type_reach` premise.
4. The sealed Cargo run clears its environment and keeps four names (`KEPT_ENV`). The switch is not one of them,
   so a build script cannot read it. A unit test pins this.
5. ArchKeel's own self runs set the switch in one place: the Makefile line for `self-validate-native`, `self-validate-system`
   and `report-gallery`. `make self-check`, `make pr-gate`, `make ci-check` and the base-commit run of the gate reach
   `self-validate-native`, so they inherit it. No workflow and no archkeel.toml sets it. A test checks this.

## Effect

The change only removes facts when the operator did not allow them, so it can hold a verdict and cannot enable a
PASS. An operator who relied on the setting alone sets `ARCHKEEL_ALLOW_BUILD=1` and gets the old behavior.

## Not done yet

- With the permission the build still runs in the process of the operator, with no sandbox. The operator-built
  bundle with a digest in the request (#1999) is the real answer.
- `cargo metadata --no-deps` runs for every Rust scan. It reads manifests only and runs no build script.
