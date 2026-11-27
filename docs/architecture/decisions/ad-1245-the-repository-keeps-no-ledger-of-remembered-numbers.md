# AD-1245 The repository keeps no ledger of remembered numbers

**Status.** Accepted. Owner decision 2026-11-27. It supersedes the ledger gates of AD-327, AD-584, AD-314 (the size ledger) and AD-756 (the clone gate).

**Reason.** A ledger stores the number that a tool measured once. A change that moves the number must also edit the ledger. The tool then checks the edit, not the behaviour. No ledger below stopped a product failure. The Rust compiler, clippy, the contract of ArchKeel and the tests of real behaviour check the same code with evidence.

**Decision.** Remove one ledger in each pull request: the JSON file, the tool, its tests, the Make and precheck targets, the workflow steps and the references in the docs.

| Ledger | Protected | Still covered by |
|---|---|---|
| Clone baseline (`native/clone_baseline.json`, `tools/rust_clones.py`, `tools/rust_inert.py`, `tests/test_rust_clones.py`) | No new copy of a block of Rust code | None (owner decision). Duplicate code is tracked in #1390 |
| Table overlap (`tests/table_overlap_expected.json`, `tests/test_table_overlap.py`) | Two literal tables that share most names | None (owner decision). #1390 |
| Size and length (`tests/file_size_baseline.json`, `tools/file_size.py`, the size asserts) | Size limits of files, functions and decisions | `make self-check` prints the file sizes (AD-1088). No rule fails on size |
| Suppressions, conventions, textual callers (`native/suppressions.json`, `test_native_conventions.py`, `test_native_targets_have_callers.py`) | Count and reason of Rust `allow`, header and naming, a textual caller for each target | Clippy and the build. None for the text rules (owner decision) |
| API ledger (`native/api_baseline.json`, `tools/rust_api.py`) | Every public name, member and signature | The compiler, the contract rules for the interface and for unused public names, the integration tests |

**Not changed.** The area floors, the base comparison of `make self-check`, and the fixture matrix.

**Done.**
- Clone baseline: this pull request.
