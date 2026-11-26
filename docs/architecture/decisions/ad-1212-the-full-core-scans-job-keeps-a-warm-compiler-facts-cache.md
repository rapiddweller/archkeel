# AD-1212: The Full core scans job keeps a warm compiler facts cache

Status: accepted. Closes #2127.

## Why

`docs/architecture/native.md` draws the component edges that the compiler proves (AD-1136). Only a scan
with compiler facts observes them. `test_the_core_scans_its_own_workspace_with_no_shell_reply` scanned a
copy without facts, so the core reported `graph.drift` for three drawn edges.

With facts on, a cold cache took more than the 600 s that the core allows (Full run 45893796950). Two
more defects hid the problem: the copy lacked the files that `native/` includes from outside
(`schema/`, the driver in `tools/rustc-facts`), so `cargo check` of the copy failed.

## Decision

1. `copy_native` copies the tracked files outside `native/` that `native/` needs.
2. The test turns the facts on in its copy. The assertion is unchanged.
3. The test file `test_cli_native_core_scan_rust.py` and the two fast scan test files form the area
   `native self scan`, with its own Full job. That job restores and saves the facts cache
   (`ARCHKEEL_FACTS_CACHE`). The key is the hash of `native/**` and the driver sources. A restore key with
   the same prefix is allowed. Before the save, the job deletes the `incremental` directories.
4. With a cache from the environment the test copies to a fixed path. The work directory is named after
   the manifest path, so a random path would never hit.

## Why a restore key is safe

The facts cache checks its inputs. The driver binary directory carries the toolchain and the driver
hash. The work directory carries the same two and a hash of the manifest path. A marker holds the hash
of `Cargo.lock` and the member roots; a difference wipes the directory. Cargo checks the fingerprint of
each unit. A stale entry costs time and never changes a result. Cold and warm frames were equal.

## Measured

Local, 18 cores, fresh file times: cold 137 s and 640 s of CPU; warm with the cache 103 s and 349 s of CPU.
The work directory is 6.9 GB. 70 % of it is `incremental` data, which cargo cannot reuse after a fresh
checkout. Without it the entry is 2.1 GB, 562 MB compressed (2.5 GB with it). The CI numbers are in the PR.

## Limit

The repository cache budget is 10 GB. The other caches use 8.0 GB, so the 0.56 GB entry fits. The entry
changes with the native tree: GitHub removes an entry after 7 days without access.

## Rejected

- Cache the full work directory: 2.5 GB, over the repository budget.
- Raise the core timeout: a budget is not a way to get green.
- Change the core so a scan without facts treats drawn edges as unproven: a stale edge next to an
  unrelated gap could pass.

## Checks

`tests/test_cli_native_core_scan_rust.py`, `tests/test_make_gate.py` (workflow wiring).
