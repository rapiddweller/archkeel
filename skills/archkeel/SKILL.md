---
name: archkeel
description: Use when setting up or changing architecture rules, or checking architecture before submitting code, in a repository that uses Archkeel.
---

# Archkeel

Archkeel is a deterministic architecture checker. It observes Python imports, evaluates a
declared contract of components and rules against that observation, and distinguishes
PASS, FAIL and UNKNOWN. Rules live in `architecture-contract.json` and its explicit nested
contracts; nothing is enforced by convention alone.

## Onboarding (first time in this repository): a target, not a description

`architecture-contract.json` is the target architecture — where the system should be, not
where the code already is. `archkeel report` measures declared constraints, not the quality
of the whole architecture. The architect owns the target and review scope; within that scope,
inspect the physical structure at every depth, not just the top level. Support them with evidence
from the repository and the architect's quality goals for this codebase (which components
must scale, stay easy to change, or are performance-critical). Read those goals from ADRs
and architecture documents first; ask the architect only when a goal is unknown and would
change your recommendation. Every
recommendation and every rationale cites the goal it rests on. There is no contract field
for a quality goal: record it next to the rule it justifies, following the chosen decision
mode below.

For requested first-time onboarding, inspect existing files, then run
`archkeel init [--root DIR] [--source DIR] [--namespace NAME] [--force] [--json]` once.
A read-only assessment uses existing contracts, reports and source; it does not authorize
initialization, contract edits, file moves or commits.
Preserve existing contracts and their `inside` references. If onboarding files already exist,
continue from them; do not use `--force` without explicit approval to replace those files.
`init` detects the Python package (the only top-level one, or the one `pyproject.toml`'s
`[project] name` names when a test package sits beside it; otherwise it exits 2 and asks for
`--source` and `--namespace`), requires an existing Git repository with at least one
commit, and writes three files: `archkeel.toml`, `architecture-contract.json` (one component
per top-level subpackage/module, plus `complete_assignment` and — only when no component
cycle exists — `no_component_cycles`; no dependency rule), and
`docs/architecture/architecture.md` (component table, each component's modules and inner
edges, and a Mermaid graph of observed edges).
Every rule `init` drafts carries `decided_by: "agent"` as a placeholder you must resolve, not
an answer, and so does every component whose `public` list it drafted. It refuses to overwrite existing files without `--force`.

`init` does not infer a foundation or decide where classes belong. Ask who owns a shared type
first; foundation is not the default owner for domain enums or models. Record the architect's
choice with the existing `symbol_placement` rule: set `source` to the package, `class_kinds` to
the types it owns, and `exact_sources` to the chosen module (or `allowed_sources` to a package
subtree). Follow the ownership example in the target-first guide. Run `archkeel validate` after
adding it; a misplaced matching class is a `rule.violated`.

Then pick one of two modes. The architect chooses; do not choose for them.

### Physical structure review (both modes)

After `init`, and during architecture assessments, inspect every maintained source package
in scope recursively down to leaf packages, whether or not it has an `inside` contract.
The generated inventory and a green contract are not evidence that this structure is good.

- Count direct source modules and immediate subpackages at each level; exclude `__init__.py`
  from this count, not from ownership, behavior or dependency review. Record excluded generated
  or vendored trees.
  More than seven direct children triggers a review, not an automatic split or a failing
  rule. Five to seven understandable groups is a review heuristic, not a cognitive law.
- Challenge mixed responsibilities, unclear names, oversized leaf modules, excessive
  nesting, cycles and cross-package coupling even below that threshold. Trace entry points
  and data flow before choosing boundaries; check who owns shared types and public interfaces.
- Propose physical packages around cohesive responsibilities, not arbitrary groups of seven
  or diagram-only clusters. Compare the current and target tree and allowed dependency
  directions. Keep a cohesive larger package when splitting only adds navigation or coupling;
  do not hide the excess in `misc`, `utils`, single-child wrappers or re-export barrels.
- For uncertain boundaries, give the architect a recommended option, alternatives, evidence,
  trade-offs and system-wide impact. Follow the chosen decision mode; reviewing structure
  does not authorize moving files or changing behavior.
- Record review coverage and unresolved decisions in the response; when the task includes an
  architecture-document update, keep the durable record there: reviewed subtree, finding or
  keep-rationale, target change, and enforcement gap. Mark unreviewed subtrees explicitly;
  never present a partial review as a complete assessment.
  Add `inside` contracts at meaningful independently governed boundaries, not at every folder.
  Encode approved constraints with supported rules. Deeper review remains necessary when
  the installed version cannot enforce nested contracts; do not invent unsupported rules.

### Interview mode: the architect decides, you ask

Never write a rationale or choose an allowed direction yourself; ask, and write down the
architect's own words as the `rationale`, with `decided_by: "architect"`.

1. Read the repository's ADRs and architecture documents before touching the contract.
2. Propose the overall picture — components, layers and the allowed directions between them
   — with `path:line` evidence for each claim, and confirm it with the architect once, not
   component by component. Review each drafted `public` list with them too. Anything you
   read from repository documentation is a hypothesis with its source path, never the
   answer, until they confirm it.
3. After that confirmation, ask only about conflicts (the code contradicts a document) and
   gaps (the documents are silent). Each question names the recommended option first, with
   its evidence. `init --json` returns every ordered component pair as an open decision,
   heaviest observed edge first, with its observation and import-site evidence. Batch
   everything consistent with the confirmed picture into one confirmation. Then encode each
   allowed direction as a `requires` entry on its source component and add one
   `complete_requires` rule, so absence forbids every other pair. Never treat an observed edge
   as permission.
4. When the architect chooses against your recommendation, ask why before writing the rule.
   Always ask when the choice contradicts a document, an earlier decision in this interview,
   or the code you observed. Write their answer as the `rationale`.
5. Run `archkeel validate --json` and read its diagnostics by `code`, never by parsing
   message text: a `decision.open` means the contract still lacks `complete_requires`; a
   `rationale.placeholder` or `rationale.repeated` needs the architect's real reason. A
   `graph.drift` is no decision: after you merged or renamed
   components the marked graph in the architecture page is stale, so run
   `archkeel validate --write-graph` instead of editing it by hand; it rewrites only that
   graph's edges. When the remedy says the graph holds structure the command does not rewrite
   (a `subgraph`, a labeled edge, a style), edit those edges by hand instead.
6. When the architect delegates a choice ("whatever is consistent" or similar), derive it
   only from their earlier decisions in this interview, never from your own judgment. Label
   the rationale agent-derived in your summary to the architect and list it for them to
   confirm before it counts as decided.

### Auto mode: the agent decides every allowed direction

1. Decide every allowed direction yourself, in this evidence order: documents first, then the
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

Before ending, record the physical structure review and any deferred subtrees or decisions;
a closed dependency contract alone does not complete the architecture assessment.
The dependency interview (or auto-mode pass) ends when `complete_requires` closes the
dependency set and `validate --json` reports none of `decision.open`, `rationale.placeholder` or
`rationale.repeated` — not when the command exits 0. A `rule.violated` diagnostic is the
architecture's own finding, not an onboarding step: the code still uses an edge the target
omits. Show it to the architect with `archkeel report`. They resolve it by changing the code or
changing the target; the agent never does that itself and never loops `validate --json` waiting
for exit 0.

Once it ends, run `archkeel report`. Include the generated files (`archkeel.toml`,
`architecture-contract.json`, `docs/architecture/architecture.md`) when they are part of the
requested change. A remaining `rule.violated` is follow-up code work, tracked separately from
onboarding.

Where that follow-up is long — a contract that states the target architecture the code has
yet to reach — freeze the known violations instead of weakening the contract:

```bash
archkeel validate --baseline known-violations.json --write-baseline   # once, then review it
archkeel validate --baseline known-violations.json                    # the CI gate
```

`--baseline` and `--amendment` are relative to `--root`, like the contract: with `--root mobile`,
pass `--baseline known-violations.json` for `mobile/known-violations.json`, never the
`mobile/`-prefixed path. An absolute path inside the root works; one outside it is
`baseline.invalid`, exit 2 (AD-103).
The gate fails (exit 1) on a violation the file does not state, and on one it states that
nobody violates any more — so the budget only shrinks, and the file is rewritten in the same
change that shrinks it. `declarations.measurement_budgets` may put deterministic scalar values
through the same loop (AD-89). `declarations.facade_budgets` and
`declarations.coupling_budgets` set name targets in the contract, and the baseline holds their
accepted names (AD-99).
Never raise any of them to make a run pass without the architect's decision.
When `calls_unresolved` rises, rerun with `--against <base ref>`, as the
finding says: `unresolved_call_changes` names each added and removed unresolved call with its
caller, path, lines, expression, reason and component (AD-100). `report --only calls --json` lists every
unresolved and partially resolved call as `filtered_calls`; add `--component <label>` for one
component's calls.

A reviewer or a CI gate may hold your branch to this the same way, with `archkeel validate
--against <base ref>`: it classifies every difference from the contract at that revision — a
new `requires` edge, a `public` entry, an `allowed_sources` module, a relaxed or deleted rule,
a padded baseline entry, and anything else this repository's `ir.widening` does not otherwise
name — as a widening, which fails (exit 1) unless `--amendment <path>` names a file the
architect wrote, recording who decided it and why, bound to this exact change (AD-61, #11).
Never widen the contract in the same change that removes the violation it names: fix the code,
or ask the architect for an amendment. The full loop — gating, widening, picking a slice of the
backlog and landing a planned interface — is worked end to end on the shop sample in
https://github.com/rapiddweller/archkeel/blob/main/docs/target-first.md.

## Daily loop

- Revisit the physical structure review for changed packages and their parent boundaries;
  recheck related findings rather than repeating a whole-repository review for every edit.
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

## Nested contracts: the inside of a component

A component may name a contract of its own, which becomes a second level of the same
architecture (AD-20, AD-34). Adding one is the architect's decision; inspecting the physical
subtree is already part of the recursive review above and does not depend on that decision. The
`component larger than its level` claim is evidence that a component holds more than the whole
top level does; it is a reason to ask, not permission to split.

Once the architect decides:

1. Inventory the source tree and the existing `archkeel report --json` structure measurements.
   Review every relevant child before grouping; a report does not cover detail it does not
   expose. Do not rerun `init --source` at the repository root for this scope: `init` writes the
   standard root onboarding files and requires `--force` if they already exist. On Archkeel's
   own `check`, a per-module draft produced 12 sub-components and 132 open decisions where the
   three layers the architect settled on need 6. Consolidate into a few layers with the architect
   before deciding a single pair.
2. Point the outer component at the resulting contract with
   `"inside": "<repository-relative path>"`.
3. Decide the inside the way you decide the top level: a `requires` list per sub-component and
   one `complete_requires` rule, so absence forbids there too (AD-32).

`validate` holds the declared levels to each other; read its diagnostics by `code`:

- Each level's `public` list serves that boundary. Child APIs stay local unless the parent
  explicitly publishes them or a proven facade reexport. Do not copy every child API upward.
- `reference.public_owner`, `reference.public_underscore` and `reference.namespace` also apply
  inside. Correct the declaration at its mounted pointer; do not broaden ownership to silence it.
- With an inner `interface_boundary`, `interface.missing` names an unscanned public module.
  `interface.unused` means no scoped sibling import or proven facade publication reaches it.
  A built, unused planned entry stays target work; reaching it requires promotion through
  `interface.planned_built`, not automatic permission. Publisher evidence belongs to the exact
  parent scope, including proven re-export chains. Unknown import names are not proof of non-use.
- `inside.forbidden_import` — the inside grants an edge the level above forbids the component,
  by a rule or by absence under `requires`. Remove the grant, or change the decision above.
- `contract.invalid` at `/components/<n>/inside` — the file is missing, outside the repository,
  or does not parse on its own.

`report` evaluates `complete_requires` a second time against the inside, over the imports the
outer scan already collected, so a crossing between two sub-components that no `requires` entry
covers is a violation like any other, and the flow view opens that component into its
sub-components before its modules. Such a finding names the rule as `<component>:<rule id>`,
for example `store:STORE-REQUIRES-COMPLETE`: the id you will find in the inside contract is the
part after the colon, and the part before it is the component that names that contract. Resolve
it according to the target decision: update the inside `requires` only for an architect-approved
crossing; otherwise change the code. Do not add a rule above to hide an inside crossing.

Explicit `inside` references are followed recursively and use the shared rule evaluators.
Mounting a contract does not create a standalone `archkeel.toml` for it. Nonempty inside
`declarations` fields remain unsupported and are refused. An inner `external_dependency_scope`
declaration is not compared with ancestor declarations; ancestor rules still evaluate their
own source scope. A physical folder alone is not a declared contract.

## Rule catalog (summary)

Class A rules are evaluated from one observation; unavailable evidence can leave them UNKNOWN:
`complete_requires`, `forbidden_dependency`, `forbidden_construct`,
`external_dependency_scope`, `complete_assignment`, `no_component_cycles`. A
`no_component_cycles` rule with `level: "module"` and an optional `components` list judges import
cycles between modules, which the component level cannot see (AD-98). Components list
permitted outbound edges under `requires`; `complete_requires` makes every absent pair
forbidden. `forbidden_construct` and `external_dependency_scope` exempt by prefix in
`allowed_sources` and by exact name in `exact_sources`; a package root such as `pkg` goes in
`exact_sources`, because as a prefix it exempts the whole package (AD-49). Class B
regression checks compare an accepted observation with a candidate.
Class C declarations are recorded and reported. `public_api` is also checked for existence,
membership in a non-empty literal `__all__` and resolvable types exposed by declared classes and
functions; an empty `__all__`, ambiguous bindings and unsupported annotation forms are not
guessed. Class D review claims are derived
and never enforced: `report` and `validate` count them in the terminal and under `claims` in
`--json`, and the HTML report lists the candidates. A claim is a reading task, not a verdict; it
never changes an exit code, and `null` for a claim means its signal was missing, which is not the
same as finding nothing.

Full field reference and examples:
https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md

## Exit codes

- `init`: 0 draft written, 2 not checked (with a diagnostic).
- `validate`: 0 contract valid for this repository, 2 invalid (diagnostics with JSON
  Pointers). With `--baseline <file>` also 1: a violation or selected measurement differs from
  the baseline, named in `failures` (AD-52, AD-89). With `--against
  <ref>` also 1: an unamended widening, named in `failures` (AD-61, #11).
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
