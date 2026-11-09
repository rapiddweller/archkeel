# AD-339 The host computes each per-run result once

**Decision.** One `report` or `explore` run must not compute the same result twice from the same
in-memory object. The output of the command does not change. Five changes make this true.

1. `IdentityMemo` (`ir/identity_memo.py`) keeps a value for one live object, by identity. The
   entry ends with its owner. An equal copy is another input and computes again. `Observation`
   gets a weak-reference slot for this. Three results use it: `validated_member_inventory_proof`,
   `replayed_dependency_binding_id` and `architecture_report`.
2. `run_report_with_observation` returns the observation behind the bytes as a third value, as
   `run_explore` does. The CLI gives it to `render_architecture_pages`. The command no longer
   decodes its own `architecture.json`. `run_report` keeps its signature (AD-303) and calls it.
3. `package_digest` and the bundled page assets (`render/page_assets.py`) use `functools.cache`.
   The installed bytes do not change in a process.
4. `_observe` and `assemble_observation` share one `ContractInput` (`check/contract_tree.py`).
   They read the root contract and its inside contracts once, not twice.
5. `dependency_binding_id` moves to `ir/dependency_binding.py`, and `report.py` hands its filter
   helpers to `check/report_filter.py`, so the legacy files do not grow (AD-314).

**Reason.** The audit of 2026-11-09 (issue #880) counted the repeats. The TypeScript demo
`nest-realworld-project` hashed one 1.57 MB binding 10 times, and one `repr` 13 times.

**Rejected.**
- A module cache keyed by data or by path. A long-lived server would grow with its inputs.
- One shared tree for the UML phase. `assemble_uml` reads the contract from disk to check it
  against the observed contract. Two tests pin this, so that phase reads again.
- Carrying the inventory replay across `dataclasses.replace`. The UML phases build three
  observation objects, so three replays stay. The caller would assert that the bound parts did not change.
- A memo for `module_exploration`. It costs 0.17 s for two calls on `excalidraw`.

**Limit.** AD-229 replay of a saved observation is a new object, so it recomputes. A memo returns
an immutable value, never a shared mutable one. The memo does not see a change on disk.

**Check.**
- `tests/test_identity_memo.py`: one object computes once; an equal copy computes again; the entry ends with its owner.
- `tests/test_compute_once_per_run.py`: counts of real computations in one `report` run.
- `architecture.json` differs from the old output only in `analyzer.code_digest`. HTML is byte-identical.
