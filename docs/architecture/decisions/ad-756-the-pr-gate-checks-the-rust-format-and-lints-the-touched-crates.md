# AD-756 The PR gate checks the Rust format and lints the touched crates

**Status.** Accepted. Part of #880 (lead request of 2026-11-17). Visible change: a PR that changes `native/` fails the gate on an unformatted file or a clippy warning.

**Reason.** #1548 merged `native/typescript/src/script_host_tests.rs` without rustfmt through a green PR gate, and the main tier went red. The PR gate ran no Rust check at all: `cargo fmt --check` and `clippy -D warnings` ran only in `make native-check` of the main tier.

**Decision.** `make pr-native-lint` runs in the PR gate after the core build. `tools/native_touched.py` reads the diff: no change in `native/` runs nothing; a change in `native/` runs `cargo fmt --all -- --check` (about 2 s, the whole workspace); a change in a crate also runs `cargo clippy --locked --all-targets -p <crate> ... -- -D warnings` for the touched crates only; a change of `Cargo.toml`, `Cargo.lock`, the toolchain or `clippy.toml` lints the whole workspace; a pin or data file under `native/` runs the format check alone. The main tier keeps its full `make native-check`.

**Rejected.** Clippy of the whole workspace in every native PR (it would take the gate over its budget); running `native-check` in the gate.

**Tests.** `tests/test_native_touched.py`: the selection, and the Make recipe against a stub `cargo` (nothing when native/ is unchanged, fmt then clippy, fmt alone for a pin, an unformatted file stops before clippy).
