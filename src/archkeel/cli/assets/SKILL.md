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
first. It detects the Python package (the only top-level one, or the one `pyproject.toml`'s
`[project] name` names when a test package sits beside it; otherwise it exits 2 and asks for
`--source` and `--namespace`), requires an existing Git repository with at least one
commit, and writes three files: `archkeel.toml`, `architecture-contract.json` (one component
per top-level subpackage/module, plus `complete_assignment` and — only when no component
cycle exists — `no_component_cycles`; no dependency rule), and
`docs/architecture/architecture.md` (component table, each component's modules and inner
edges, and a Mermaid graph of observed edges).
Every rule `init` drafts carries `decided_by: "agent"` as a placeholder you must resolve, not
an answer, and so does every component whose `public` list it drafted. It refuses to overwrite existing files without `--force`.

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
   architect's real reason. A `graph.drift` is no decision: after you merged or renamed
   components the marked graph in the architecture page is stale, so run
   `archkeel validate --write-graph` instead of editing it by hand; it rewrites only that
   graph's edges. When the remedy says the graph holds structure the command does not rewrite
   (a `subgraph`, a labeled edge, a style), edit those edges by hand instead.
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
3. Write every rule you decide with `decided_by: "agent"`, and mark a component whose
   `public` list or `requires` edges you decided the same way: `decided_by` on the component
   covers its `public` list and every `requires` entry that carries none of its own, and one
   entry may override it (AD-50).
4. End with a summary of your decisions grouped by evidence basis (document, layer
   principle, judgment) and name the lowest-confidence decisions first, for the architect to
   review.

A later interview on an auto-mode contract asks the architect only about rules, entries and
components with `decided_by: "agent"`; an `architect`-decided one is already closed and is not
reopened.

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

Where that follow-up is long — a contract that states the target architecture the code has
yet to reach — freeze the known violations instead of weakening the contract:

```bash
archkeel validate --baseline known-violations.json --write-baseline   # once, then review it
archkeel validate --baseline known-violations.json                    # the CI gate
```

The gate fails (exit 1) on a violation the file does not state, and on one it states that
nobody violates any more — so the budget only shrinks, and the file is rewritten in the same
change that shrinks it. Never add a new violation to the baseline to make a run pass: that is
the architect's decision, not the agent's (AD-52).

## Daily loop

- Run `archkeel report --json` before submitting any change. A rule violation does not
  change the exit code; read the `declared_rules` verdict. Exit 2 means the evidence is
  incomplete; fix the diagnostic before trusting any verdict.
- On a large repository, `report --only violations --rule <id> --component <label> --json`
  narrows the review surface to a slice you can actually read: `--only violations` drops
  component flow, communication, claims and structure from the HTML page; `--rule` and
  `--component` narrow the violations table further and combine as an intersection.
  `--component` matches either side of a crossing, source or target. This changes only what is
  shown - `declared_rules`, the violation counts and the exit code stay computed from every
  violation - and a filtered `--json` result says so in its own `report_filter` field, so never
  read a filtered `filtered_violations` count as the repository's total; read the unfiltered
  `violations` measurement for that. A `--rule` or `--component` you misspelled is a named exit
  2, not a silently empty page.
- If a rule fails, fix the code so the rule passes.
- Never weaken or delete a rule just to make a violation disappear, unless the component
  owner explicitly approves the change to the contract. A silently loosened rule hides the
  next real violation.
- `validate --json` and `report --json` report `agent_decisions` as `[agent, total]`, counting
  one rule declaration, one `requires` entry and one declared `public` list alike; a nonzero
  first value means an auto-mode contract still awaits an architect interview on those
  decisions.
- The same two commands report `claims`, the Class D review claims. They never change a
  verdict or an exit code; bring a nonzero count to the architect as reading work, and never
  delete code because a claim named it.

## A second level: the inside of a component

A component may name a contract of its own, which becomes a second level of the same
architecture (AD-20, AD-34). Opening one is the architect's decision, never yours. The
`component larger than its level` claim is evidence that a component holds more than the whole
top level does; it is a reason to ask, not permission to split.

Once the architect decides:

1. Draft the scope with `archkeel init --source <component path> --namespace <component
   package>`. Read the draft as an inventory, not as a proposal: it writes one component per
   module, so on Archkeel's own `check` it drafted 12 sub-components and 132 open decisions
   where the three layers the architect settled on need 6. The drafted table and `init
   --json`'s `draft_sizes` also carry each drafted component's modules and inner edges, so a
   large or well-connected child is visible before you group anything, not only after.
   Consolidate it into a few layers with the architect before deciding a single pair.
2. Point the outer component at the resulting contract with
   `"inside": "<repository-relative path>"`.
3. Decide the inside the way you decide the top level: a `requires` list per sub-component and
   one `complete_requires` rule, so absence forbids there too (AD-32).

`validate` then holds the two levels to each other, and you read its diagnostics by `code`:

- `inside.public_mismatch` — the component's `public` above and the public surface of the
  inside must be the same list. Declare it once and repeat it in both contracts.
- `inside.forbidden_import` — the inside grants an edge the level above forbids the component,
  by a rule or by absence under `requires`. Remove the grant, or change the decision above.
- `contract.invalid` at `/components/<n>/inside` — the file is missing, outside the repository,
  or does not parse on its own.

`report` evaluates `complete_requires` a second time against the inside, over the imports the
outer scan already collected, so a crossing between two sub-components that no `requires` entry
covers is a violation like any other, and the flow view opens that component into its
sub-components before its modules. Such a finding names the rule as `<component>:<rule id>`,
for example `store:STORE-REQUIRES-COMPLETE`: the id you will find in the inside contract is the
part after the colon, and the part before it is the component that names that contract. Fix it
in the inside contract, never by adding a rule above.

Three limits hold today: the inside has no `archkeel.toml`, so it cannot be validated as a
level of its own; of its rules only `complete_requires` is evaluated, and an
`external_dependency_scope` declared inside is not compared with the level above; and only one
level down is recorded, so an inside declared within an inside is not read.

## Rule catalog (summary)

Class A rules are deterministic PASS/FAIL, evaluated from one observation:
`forbidden_dependency`, `forbidden_construct`, `external_dependency_scope`,
`complete_assignment`, `no_component_cycles`. `allowed_dependency` adds no report
violation; it only decides that a component pair may depend. `closed_world` — every
ordered component pair is decided, once, by an `allowed_dependency` or a
`forbidden_dependency` rule — is an implicit Contract 2.1 invariant, not a rule you
declare. `forbidden_construct` and `external_dependency_scope` exempt by prefix in
`allowed_sources` and by exact name in `exact_sources`; a package root such as `pkg` goes in
`exact_sources`, because as a prefix it exempts the whole package (AD-49). Class B
regression checks compare an accepted observation with a candidate.
Class C declarations (capabilities, public API, context roots, owners) are recorded and
reported, not enforced. Class D review claims are derived and never enforced: `report` and
`validate` count them in the terminal and under `claims` in `--json`, and the HTML report
lists the candidates. A claim is a reading task, not a verdict; it never changes an exit code,
and `null` for a claim means its signal was missing, which is not the same as finding nothing.

Full field reference and examples:
https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md

## Exit codes

- `init`: 0 draft written, 2 not checked (with a diagnostic).
- `validate`: 0 contract valid for this repository, 2 invalid (diagnostics with JSON
  Pointers). With `--baseline <file>` also 1: a violation the file does not state, or one it
  states that nobody violates any more, each named in `failures` (AD-52).
- `report`: 0 observation complete (a rule violation is a FAIL verdict), 2 not checked.
- `skill install claude|codex`: 0 instructions written, 2 the target file could not be updated.
- `check`: 0 merge, 1 reject, 2 not checked. Its expectation's `selected_changes` may be `[]`
  when a candidate is not meant to change anything architectural, such as a pure refactor. That
  declares absence, not "nothing to report": `check` then fails on any semantic change the
  candidate actually produced, in any dimension, not only the six guardrail ones. Declare `[]`
  only when you mean it; naming the real changes remains the default (AD-39). A non-empty
  declaration still lets an undeclared change through in most dimensions, except
  `dependency_edges`: name every new edge you add, or `check` fails on the one you left out
  (AD-44).

## JSON output

Every command accepts `--json`. Prefer it when scripting or reading output
programmatically: `archkeel validate --json`, `archkeel init --json`, `archkeel report
--json`. Interactive terminals otherwise get a Rich-formatted summary instead of raw JSON.
