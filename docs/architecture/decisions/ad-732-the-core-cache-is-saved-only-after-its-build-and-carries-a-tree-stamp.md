# AD-732 The core cache is saved only after its build and carries a tree stamp

**Status.** Accepted. Part of #880, #1451 (S4). Visible change: a PR whose lint fails or whose run is cancelled no longer saves a core for its native tree.

**Reason.** The PR gate saved `core-<native hash>` with `if: always()`. When lint failed before `make core`, or the run was cancelled during the build, the restored `native/target` still held the release core of main, and that old binary was saved under the hash of the PR tree. The next push (a Python-only fix) hit the cache and ran the pins of the PR against the old core. `ci.yml` had the same `if: always()`.

**Decision.**
1. `make core` runs in its own step `id: build` before the gate, with `ARCHKEEL_NATIVE_TREE` set to the native tree hash.
2. With that variable, `make core` reuses `native/target/release/archkeel-core` only when `archkeel-core.tree` next to it holds the same hash. Otherwise it removes the stamp, builds, and writes the stamp only after the build succeeded.
3. The core is saved (binary and stamp, under `core-<os>-<hash>`) only when `steps.build.outcome == 'success'`, in `pr-gate.yml` and in `ci.yml`.

**Rejected.** Hashing the binary after the fact (it cannot tell which tree built it); dropping the cache (the PR gate would rebuild the core every time).

**Limit.** The stamp is a hash of the tree, not of the toolchain; the key of the cache holds the toolchain file.

**Tests.** `tests/test_make_gate.py`: `test_make_core_reuses_a_core_only_with_the_stamp_of_its_tree`, `test_a_core_is_saved_only_after_its_own_build_step_succeeded`.
