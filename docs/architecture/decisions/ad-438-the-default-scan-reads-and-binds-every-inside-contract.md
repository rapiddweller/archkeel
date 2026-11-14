# AD-438 The default scan reads and binds every inside contract

**Status.** Proposed. Part of #880. It extends AD-422 and AD-432.

**Decision.**
1. The default shell no longer requests `root_only`. `validate` and `report` use the existing
   bounded tree reader in `native/core/src/scan.rs`. The explicit low-level option stays supported.
2. Keep the mount semantics of AD-366 and AD-385. References are root-relative, not parent-relative.
   Keep each mount's source domain, scoped IDs, shared coverage gaps and existing PASS makers.
3. The scan frame adds `self_test.collect.contract_files`: each read contract reference and its
   raw-byte SHA-256, including the root. Compute it from the bytes passed to the one engine path.
   `Ruling::frame` remains the only maker of frame bytes. No rule or proof changes.
4. `core_binding.py` owns request binding, moved from `core_frame.py` to stay below 500 lines.
   It reads the config location, file bytes and metadata, never contract rules or source facts.
   The closed shell inventory adds this module for that task.
5. The shell requires the file map for a collected frame and checks the root entry against the
   existing root digest. It reads at most 1,024 nested files and 64 MiB of nested bytes.
   Reject unsafe paths, links in any nested path, missing files and digest differences.
6. Record the local request start time before the core exchange. Reject a nested file whose
   modification or metadata-change time is later. Compare identity and times across the binding read.
   Thus an ordinary write before the core read refuses too, not only a write after that read.
7. Keep all core bounds: 1,024 inside files, 64 MiB of nested bytes, 900 mount levels and 901 rounds.
   Keep the survey, snapshot, store, path and tree checks. Missing and malformed files, cycles,
   unsafe references and linked files give a named gap or refusal, never an incomplete PASS.
8. Keep named model gaps, including mounted `layer_order`, scoped dependency proofs and UML targets.
   Do not replace them with success or add new tree semantics.

**Reason.** The default request refused trees that the core can already read and decide.
The measured 26-project set lost 20 definite FAIL project verdicts behind collection refusal.
A root-only digest cannot bind a frame after a nested-only edit.

**Rejected.** Removing only `root_only`: old frames could survive nested edits.
Parsing mounts in Python: that creates a second contract reader. A second verdict or PASS maker.
A new tree digest algorithm: per-file hashes use the existing raw-byte digest and expose each input.

**Limits.** This is not an atomic filesystem snapshot. Keep inputs unchanged during a run.
The early-write check trusts filesystem change times and the local wall clock, as recorded at exchange.
Clock rollback and filesystems without reliable change times need an immutable snapshot service.
The binary remains trusted for a complete file list and for its rule rows, as in AD-432.
Git configuration and stale-binary limits of AD-422 stay. No new language or rule kind is ported.

**Tests.** `tests/test_cli_core_inside_trees.py` uses the release core and the default shell.
It covers two mount levels, PASS, nested FAIL, root FAIL and UNKNOWN with text/JSON exit agreement.
It plants unsafe, outside, linked, cyclic, absent, malformed and oversized mounts.
It changes only a nested file before and after the core read, and replays an old PASS after an edit.
The root bytes, HEAD and dirty state remain unchanged in the replay.
`tests/test_ir_owners.py` checks the shell inventory. Existing native tree tests check the semantics.
