---
name: archkeel
description: Use when setting up or changing architecture rules, or checking architecture before submitting code, in a repository that uses Archkeel.
---

# Archkeel

Archkeel is a deterministic architecture checker. It observes Python imports, evaluates a
declared contract of components and rules against that observation, and reports PASS/FAIL
per rule. Rules are declared once in `architecture-contract.json`; nothing is enforced by
convention alone.

## Onboarding (first time in this repository): a decision interview

The code proposes, the architect decides. Never write a rationale or pick allow/forbid
yourself; ask, and write down the architect's own words.

1. Run `archkeel init [--root DIR] [--source DIR] [--namespace NAME] [--force] [--json]`.
   It detects the Python package, requires an existing Git repository with at least one
   commit, and writes three files: `archkeel.toml`, `architecture-contract.json` (one
   component per top-level subpackage/module, plus `complete_assignment` and — only when
   no component cycle exists — `no_component_cycles`; no dependency rule), and
   `docs/architecture/architecture.md` (component table and Mermaid graph of observed
   edges). It refuses to overwrite existing files without `--force`.
2. Confirm the drafted components with the architect as multiple choice: keep, merge,
   split, or something else. Review each drafted `public` list with them too. Anything you
   read from repository documentation is a hypothesis with its source path, never the
   answer.
3. `init --json` also returns every ordered component pair as an open decision, heaviest
   observed edge first, each carrying `source`, `target`, `observed`, `import_sites` and
   `options`: the exact `allowed_dependency` and `forbidden_dependency` rule for that pair,
   missing only the `rationale`. Work through them with the architect in that order: ask
   allow, forbid, or something else, with their reason in their own words, then write the
   chosen option object into `architecture-contract.json` verbatim except for `rationale`.
   Never hand-build a rule id. Once a component's shape is agreed, offer one decision for
   all of its remaining unobserved pairs at once.
4. Every generated rule rationale is a placeholder starting with `TODO:`. Run
   `archkeel validate --json` and read its diagnostics by `code`, never by parsing message
   text: a `decision.open` means step 3 is not finished for that pair (`validate --json`
   carries the same open decisions as `init --json`); a `decision.conflict` or
   `closed_world.duplicate` means the pair has more than one decision, keep exactly one;
   a `rationale.placeholder` or `rationale.repeated` needs the architect's real reason.
5. The interview ends when `validate --json` reports no `decision.open`,
   `decision.conflict`, `rationale.placeholder`, `rationale.repeated` or
   `closed_world.duplicate` diagnostic — not when the command exits 0. A `rule.violated`
   or `closed_world.observed_forbidden` diagnostic is the architecture's own finding, not
   an interview step: the code still uses an edge the architect just decided against. Show
   it to the architect with `archkeel report`. They resolve it by changing the code or by a
   new explicit decision (for example allowing the edge instead); the agent never resolves
   it by editing or deleting the rule, and never loops `validate --json` waiting for exit 0.
6. When the architect delegates a choice ("whatever is consistent" or similar), derive it
   only from their earlier decisions in this interview, never from your own judgment. Label
   the rationale agent-derived in your summary to the architect and list it for them to
   confirm before it counts as decided.
7. Once the interview ends, run `archkeel report` and commit the three generated files
   (`archkeel.toml`, `architecture-contract.json`, `docs/architecture/architecture.md`).
   A remaining `rule.violated` or `closed_world.observed_forbidden` is follow-up code work,
   tracked separately from onboarding, not a reason to hold the commit.

## Daily loop

- Run `archkeel report --json` before submitting any change. A rule violation does not
  change the exit code; read the `declared_rules` verdict. Exit 2 means the evidence is
  incomplete; fix the diagnostic before trusting any verdict.
- If a rule fails, fix the code so the rule passes.
- Never weaken or delete a rule just to make a violation disappear, unless the component
  owner explicitly approves the change to the contract. A silently loosened rule hides the
  next real violation.

## Rule catalog (summary)

Class A rules are deterministic PASS/FAIL, evaluated from one observation:
`forbidden_dependency`, `forbidden_construct`, `external_dependency_scope`,
`complete_assignment`, `no_component_cycles`. `allowed_dependency` adds no report
violation; it only decides that a component pair may depend. `closed_world` — every
ordered component pair is decided, once, by an `allowed_dependency` or a
`forbidden_dependency` rule — is an implicit Contract 2.1 invariant, not a rule you
declare. Class B regression checks compare an accepted observation with a candidate.
Class C declarations (capabilities, public API, context roots, owners) are recorded and
reported, not enforced. Class D review claims are planned and not yet implemented.

Full field reference and examples:
https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md

## Exit codes

- `init`: 0 draft written, 2 unverifiable (with a diagnostic).
- `validate`: 0 contract valid for this repository, 2 invalid (diagnostics with JSON
  Pointers).
- `report`: 0 observation complete (a rule violation is a FAIL verdict), 2 unverifiable.
- `skill install claude|codex`: 0 instructions written, 2 the target file could not be updated.
- `check`: 0 merge, 1 reject, 2 unverifiable.

## JSON output

Every command accepts `--json`. Prefer it when scripting or reading output
programmatically: `archkeel validate --json`, `archkeel init --json`, `archkeel report
--json`. Interactive terminals otherwise get a Rich-formatted summary instead of raw JSON.
