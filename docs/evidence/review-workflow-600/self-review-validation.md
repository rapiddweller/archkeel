# Self-review: `src/archkeel/check/validation` only (#600, acceptance 5)

Scope: one subtree, not an assessment of ArchKeel. A fresh reviewer (Sonnet) used only
`skills/archkeel/SKILL.md`, the repository's contracts and `docs/architecture/` on a clean
clone of 5ff933c. CLI: `validate --baseline architecture-baseline.json` exit 0, all rules
PASS; none of the findings below is encoded as a rule.

| # | Finding | Decision | Verified |
|---|---|---|---|
| F1 | `references._provenance` omits `measurement_budgets` and UML provenance that `ir.codec_inside.contract_provenance_paths` covers; a missing budget provenance file surfaces as a generic `contract.invalid` with the config path, not `reference.provenance` with a pointer | simplify: one provenance enumerator | code read in this session; behavior by the reviewer's probe |
| F2 | `rationale_diagnostics` runs on the root contract only; a placeholder rationale in a mounted contract passes. No current mount is affected | simplify: run over root and mounts, as responsibilities already do; architect confirms intent | code read in this session (`observation.py:123`); behavior by the reviewer's probe |
| F3 | `validation/__init__.py` re-exports 60 names; 40 have no importer | delete dead re-exports; repoint tests to submodules | reviewer's script |
| F4 | interface lifecycle loop duplicated in `public_api.py` and `inside.py` with identical diagnostic text | simplify: one per-component function | reviewer |
| F5 | repository-path safety reader written in several places under `check/` | architect decision: one owner in `check/declarations` | reviewer, partly out of scope |
| F6 | `__init__.py` mixes the public facade with the `--against`/widening subsystem (~600 lines) | architect decision; moving it touches path-bound contract rules | reviewer |
| F7 | `public_api.py` holds four responsibilities; 13 underscore names are its real internal API | simplify: split by responsibility, no new cycle | reviewer |
| F8 | shared operations (`inspect_observation`, `observe_revision`) live in command peers, which `TARGET-WORKFLOWS` forbids in prose but no rule enforces | architect decision on the owner | reviewer |
| F9 | `config.language == "python"` and a `"public"/"planned"` string selector where typed values exist | simplify the two typed cases; keep record-kind strings until `ir` types them | reviewer |

Kept with rationale: the eight flat diagnostic modules (one family each; subpackages would
be single-child wrappers), `rationale.py`, `diagnostics.py`, `closed_world.py`, `graphs.py`.

The method held on real code: tool facts and judgment stayed apart, findings carry
locations and decisions, and two behavior-level defects were found by probes rather
than inferred. F1–F9 are not fixed here; they are follow-up work.
