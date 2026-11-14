# AD-466 The core checks contract hygiene and binds each provenance file

**Status.** Proposed. Part of #880. It extends AD-432 and AD-438.

**Decision.**
1. On a scan request, the core reads each repository path that a contract of the tree cites as
   provenance. It uses the reader of the inside contracts: no path outside the root, no link out
   of the root, only regular files. A link inside the root reads its target, as release 4.0.1 does.
2. `self_test.collect.contract_files` adds each document that the core read, with its raw-byte
   SHA-256. The shell rehashes it as it rehashes an inside contract, so a change after the run
   refuses the replay. The documents share the bounds of the inside contracts: 1,024 nested files
   and 64 MiB of nested bytes.
3. A cited path that the core cannot read refuses the whole contract (`reference.provenance`,
   exit 2). A root document that is not UTF-8 refuses the contract too.
4. The core ports these checks of release 4.0.1. Each defect is a row with `Reason::Hygiene` and
   the code of the release: `graph.count`, `graph.drift` (both markers), `reference.namespace`,
   `reference.public_owner`, `reference.public_underscore`, `reference.package_unscanned`,
   `closed_world.observed_forbidden`, `closed_world.duplicate`, `decision.conflict`,
   `decision.open`, `rationale.placeholder`, `rationale.repeated`, `responsibility.missing` and
   `api_surface.missing`.
5. A family that applies and that no check ports is a row with `Unsupported::Hygiene`: the
   interface lifecycle checks (`interface.*`) for a contract with an `interface_boundary` rule, and
   `compatibility.invalid` for `declarations.compat`.
6. A row only holds back a PASS through `Named`. `Ruling::frame` stays the only maker of frame
   bytes, and the PASS makers do not change. The checks are in new core modules (`hygiene*.rs`,
   `provenance.rs`). The contract crate exports `provenance_paths`. No crate edge is new.

**Reason.** A measured comparison with release 4.0.1 found one run-level hole: a deleted
provenance file or a stale marked graph gave exit 2 in 4.0.1 and PASS with exit 0 on `main`.
The frame did not bind the provenance documents, so a document change could not refuse a replay.

**Rejected.** A refusal for each run with a marked graph: release 4.0.1 requires one component
graph, so no project could pass. A gap for the whole family: the same effect. Checks in the shell: the
shell decides nothing (AD-432). A JSON walk of the raw contract bytes: the namespace walk reads the
canonical form of the typed contract, so the contract crate stays the only reader.

**Limits.**
- Only the scan request reads the repository. The dual-run and check requests have no documents
  and no hygiene rows; the shell sends neither.
- `api_surface.missing` has no exposed-type part: no collector of the core writes those type facts.
- `inside.*`, `budget.*` and `--write-graph` are not ported.
- `reference.namespace` exempts no library name. A profile that forbids a library outside the
  namespace (`dart.io` in 4.0.1) needs that exemption when it is ported.
- The self contract gave one finding: the marked graph of `docs/architecture/native.md` was stale.
  The page now draws the observed edges. The self rows stay 63 PASS, 1 FAIL and 19 UNKNOWN.
- Test fixtures without a marked graph or with a missing cited file now give UNKNOWN. Release
  4.0.1 rejects each of them too. The fixtures that a test needs to pass now carry a graph.
  `fixtures/F-typescript-story` stays UNKNOWN; its pinned gap is now the `graph.count` row.

**Tests.** `tests/test_cli_core_contract_hygiene.py` sends one plant for each code through the
release core and the default shell, and replays a frame after a page change (exit 2). The core
unit tests `hygiene_tests.rs`, `hygiene_graph_tests.rs` and `hygiene_refs_tests.rs` check the
rules of the reference engine. The copied native workspace now carries its cited documents.
