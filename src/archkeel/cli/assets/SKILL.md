---
name: archkeel
description: Use when setting up or changing architecture rules, or checking architecture before submitting code, in a repository that uses Archkeel.
---

# Archkeel

Archkeel is a deterministic architecture checker. It observes Python imports, evaluates a
declared contract of components and rules against that observation, and reports PASS/FAIL
per rule. Rules are declared once in `architecture-contract.json`; nothing is enforced by
convention alone.

## Onboarding (first time in this repository): a target, not a description

`architecture-contract.json` is the target architecture — where the system should be, not
where the code already is. `archkeel report` measures the code's distance from that target
as violations. The architect owns the target and chooses how deep to review it today; you
support them with best practice, evidence from the repository, and the architect's quality
goals for this codebase (which components must scale, stay easy to change, or are
performance-critical). Read those goals from ADRs and architecture documents first; ask the
architect only when a goal is unknown and would change your recommendation. Every
recommendation and every rationale you write cites the goal it rests on. There is no
contract field for a quality goal: it lives in the rationale, in your own words, next to the
rule it justifies.

Run `archkeel init [--root DIR] [--source DIR] [--namespace NAME] [--force] [--json]` once,
first. It detects the Python package, requires an existing Git repository with at least one
commit, and writes three files: `archkeel.toml`, `architecture-contract.json` (one component
per top-level subpackage/module, plus `complete_assignment` and — only when no component
cycle exists — `no_component_cycles`; no dependency rule), and
`docs/architecture/architecture.md` (component table and Mermaid graph of observed edges).
Every rule `init` drafts carries `decided_by: "agent"` as a placeholder you must resolve, not
an answer. It refuses to overwrite existing files without `--force`.

Then pick one of two modes. The architect chooses; do not choose for them.

### Interview mode: the architect decides, you ask

Never write a rationale or pick allow/forbid yourself; ask, and write down the architect's
own words as the `rationale`, with `decided_by: "architect"`.

1. Read the repository's ADRs and architecture documents before touching the contract.
2. Propose the overall picture — components, layers and the allowed directions between them
   — with `path:line` evidence for each claim, and confirm it with the architect once, not
   component by component. Review each drafted `public` list with them too. Anything you
   read from repository documentation is a hypothesis with its source path, never the
   answer, until they confirm it.
3. After that confirmation, ask only about conflicts (the code contradicts a document) and
   gaps (the documents are silent). Each question names the recommended option first, with
   its evidence. `init --json` returns every ordered component pair as an open decision,
   heaviest observed edge first, each carrying `source`, `target`, `observed`,
   `import_sites` and `options`: the exact `allowed_dependency` and `forbidden_dependency`
   rule for that pair, missing only the `rationale` (`validate --json` carries the same open
   decisions). Batch everything consistent with the confirmed picture into one confirmation
   instead of asking pair by pair; never hand-build a rule id, write the chosen option
   object verbatim except for `rationale` and `decided_by`.
4. When the architect chooses against your recommendation, ask why before writing the rule.
   Always ask when the choice contradicts a document, an earlier decision in this interview,
   or the code you observed. Write their answer as the `rationale`.
5. Run `archkeel validate --json` and read its diagnostics by `code`, never by parsing
   message text: a `decision.open` means step 3 is not finished for that pair; a
   `decision.conflict` or `closed_world.duplicate` means the pair has more than one
   decision, keep exactly one; a `rationale.placeholder` or `rationale.repeated` needs the
   architect's real reason.
6. When the architect delegates a choice ("whatever is consistent" or similar), derive it
   only from their earlier decisions in this interview, never from your own judgment. Label
   the rationale agent-derived in your summary to the architect and list it for them to
   confirm before it counts as decided.

### Auto mode: the agent decides every open decision

1. Decide every open decision yourself, in this evidence order: documents first, then the
   layer principles the architect already confirmed or the documents state, then your own
   judgment, labeled as judgment in the rationale.
2. Never treat an observed edge as permission: code importing across a boundary today is not
   evidence the boundary should allow it.
3. Write every rule you decide with `decided_by: "agent"`.
4. End with a summary of your decisions grouped by evidence basis (document, layer
   principle, judgment) and name the lowest-confidence decisions first, for the architect to
   review.

A later interview on an auto-mode contract asks the architect only about rules with
`decided_by: "agent"`; an `architect`-decided rule is already closed and is not reopened.

### Ending onboarding, either mode

The interview (or the auto-mode pass) ends when `validate --json` reports no
`decision.open`, `decision.conflict`, `rationale.placeholder`, `rationale.repeated` or
`closed_world.duplicate` diagnostic — not when the command exits 0. A `rule.violated` or
`closed_world.observed_forbidden` diagnostic is the architecture's own finding, not an
onboarding step: the code still uses an edge just decided against. Show it to the architect
with `archkeel report`. They resolve it by changing the code or by a new explicit decision
(for example allowing the edge instead); the agent never resolves it by editing or deleting
the rule, and never loops `validate --json` waiting for exit 0.

Once it ends, run `archkeel report` and commit the three generated files (`archkeel.toml`,
`architecture-contract.json`, `docs/architecture/architecture.md`). A remaining
`rule.violated` or `closed_world.observed_forbidden` is follow-up code work, tracked
separately from onboarding, not a reason to hold the commit.

## Daily loop

- Run `archkeel report --json` before submitting any change. A rule violation does not
  change the exit code; read the `declared_rules` verdict. Exit 2 means the evidence is
  incomplete; fix the diagnostic before trusting any verdict.
- If a rule fails, fix the code so the rule passes.
- Never weaken or delete a rule just to make a violation disappear, unless the component
  owner explicitly approves the change to the contract. A silently loosened rule hides the
  next real violation.
- `validate --json` and `report --json` report `agent_decisions` as `[agent, total]`; a
  nonzero first value means an auto-mode contract still awaits an architect interview on
  those rules.

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
