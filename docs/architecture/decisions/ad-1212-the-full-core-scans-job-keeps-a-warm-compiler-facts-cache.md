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
3. The Full `core scans` job restores and saves the facts cache (`ARCHKEEL_FACTS_CACHE`). The key is the
   hash of `native/**` and the driver sources. A restore key with the same prefix is allowed.
4. With a cache from the environment the test copies to a fixed path. The work directory is named after
   the manifest path, so a random path would never hit.

## Why a restore key is safe

The facts cache checks its inputs. The driver binary directory carries the toolchain and the driver
hash. The work directory carries the same two and a hash of the manifest path. A marker holds the hash
of `Cargo.lock` and the member roots; a difference wipes the directory. Cargo checks the fingerprint of
each unit. A stale entry costs time and never changes a result. Cold and warm frames were equal.

## Measured

Local, 18 cores: cold 136 s, warm 48 s. Cold needs 640 s of CPU. The work directory is 6.6 GB, 2.5 GB
compressed. The CI numbers are in the PR.

## Limit

The repository cache budget is 10 GB and is already full. This entry adds 2.5 GB.

## Rejected

- Raise the core timeout: a budget is not a way to get green.
- Change the core so a scan without facts treats drawn edges as unproven: a stale edge next to an
  unrelated gap could pass.

## Checks

`tests/test_cli_native_core_scan_rust.py`, `tests/test_make_gate.py` (workflow wiring).
