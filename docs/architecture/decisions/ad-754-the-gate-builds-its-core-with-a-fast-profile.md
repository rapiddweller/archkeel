# AD-754 The gate builds its core with a fast profile

**Status.** Accepted. Part of #880 (lead request of 2026-11-17). Visible change: the core of the PR gate and of the main tier is not the LTO build; the shipped build is unchanged.

**Reason.** A PR that changes `native/` took 4:17 to 5:34 against a gate of 3:00. Measured on #1537 (run 44043163637): set-up 0:45, core build 2:28, static checks, self-check and tests 1:54, cache save 0:16. Cargo rebuilds every workspace crate after a checkout (the mtimes are new), and the release profile (`lto = true`, `codegen-units = 1`) makes that rebuild the longest step.

**Decision.**
1. `ARCHKEEL_CORE_PROFILE=gate` makes `make core` build with `CARGO_PROFILE_RELEASE_LTO=false`, `CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16` and `CARGO_PROFILE_RELEASE_OPT_LEVEL=1`. The PR gate and the main tier set it. The verdicts of the core do not depend on LTO. The wheel build, the nightly Full run, the Pages build and a plain `make core` keep the release profile of `native/Cargo.toml`.
2. The cache keys carry `gate` (`rust-gate-main-...`, `core-gate-...`), so a gate target never mixes with a release target.
3. The PR gate runs `make ci-pr-static` beside the core build (it needs no core) and checks its result in the next step; `SKIP_STATIC=1` keeps it from running twice.

**Rejected.** `sccache` (a second cache service, and the GitHub backend is being retired); restoring file mtimes to keep crates fresh (a stale crate would pass for a changed one); building only the touched crates (the core links all of them).

**Tests.** `tests/test_core_cache.py`.

**Measured.** A native PR on a warm cache: before 5:34 (core build 2:28); with the gate profile, the static and Rust lint beside the build and the cache of main kept warm by `pages.yml`: probe on `native/core` 3:17 (core build 1:33, tests 0:39), probe on `native/python` 4:22 (core build 1:30, tests 1:51; 0:46 of the test set were two heavy files, now in the main tier). Opt-level 1 and the two files go in the second step; its numbers are in the pull request.
