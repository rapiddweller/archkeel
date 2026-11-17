# AD-754 The gate builds its core with a fast profile

**Status.** Accepted. Part of #880 (lead request of 2026-11-17). Visible change: the core of the PR gate and of the main tier is not the LTO build; the shipped build is unchanged.

**Reason.** A PR that changes `native/` took 4:17 to 5:34 against a gate of 3:00. Measured on #1537 (run 44043163637): set-up 0:45, core build 2:28, static checks, self-check and tests 1:54, cache save 0:16. Cargo rebuilds every workspace crate after a checkout (the mtimes are new), and the release profile (`lto = true`, `codegen-units = 1`) makes that rebuild the longest step.

**Decision.**
1. `ARCHKEEL_CORE_PROFILE=gate` makes `make core` build with `CARGO_PROFILE_RELEASE_LTO=false` and `CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16`. The PR gate and the main tier set it. The verdicts of the core do not depend on LTO. The wheel build, the nightly Full run, the Pages build and a plain `make core` keep the release profile of `native/Cargo.toml`.
2. The cache keys carry `gate` (`rust-gate-main-...`, `core-gate-...`), so a gate target never mixes with a release target.
3. The PR gate runs `make ci-pr-static` beside the core build (it needs no core) and checks its result in the next step; `SKIP_STATIC=1` keeps it from running twice.

**Rejected.** `sccache` (a second cache service, and the GitHub backend is being retired); restoring file mtimes to keep crates fresh (a stale crate would pass for a changed one); building only the touched crates (the core links all of them).

**Tests.** `tests/test_core_cache.py`.
