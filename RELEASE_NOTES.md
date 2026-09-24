# Archkeel 0.7.0 — Dart layers and targets you can hold

0.7.0 adds a Dart profile and turns four report-only observations into contract targets. What
Archkeel cannot decide stays `UNKNOWN` or is refused with exit 2; it never reads PASS.

## Highlights

- **Dart and Flutter import graphs.** `[scan] language = "dart"` checks a package's layers from
  its directive headers, with no Dart SDK and no new dependency. Rules that need types are
  refused with exit 2. On `flutter/samples` the edges match the official Dart parser: 433 of 433
  in `compass_app`, 1,183 of 1,183 across 35 packages (AD-97).
- **Module cycles can be a target.** `no_component_cycles` takes `level: "module"` and a
  `components` scope. A violation names the members and the imports that close the cycle. A
  cycle that shrinks inside a baselined one counts as progress, not new debt. A package cycle
  says whether a module cycle backs it or whether it is only a roll-up artifact (AD-98).
- **Facade and coupling budgets.** `facade_budgets` and `coupling_budgets` set a target for a
  facade's exported names or a component pair's imported names. The baseline records the
  accepted names, so a new name fails by name and freed room cannot be reused silently (AD-99).
- **Unresolved calls are named.** A `calls_unresolved` rise in `check` or
  `validate --against <ref>` lists the added and removed call sites. `report --only calls` lists
  every unresolved and partially resolved call with its component (AD-100).
- **Tests can be a second scope.** `--config` selects a second configuration at the same root,
  for example a test contract next to the product one. Results name the roots they read, so a
  green product scan no longer suggests that tests were checked (AD-101).
- **Constants JSON cannot hold no longer stop the analyzer.** A module-level `bytes`, `complex`
  or `...` constant, a `str` with a lone surrogate, a huge `int` or a non-finite `float` is
  recorded without its value, so packages such as pytest and pygments scan; such a constant
  proves no `Literal` member (AD-102).

## Compatibility

- Analyzer version moves from `0.47.0` to `0.51.0`. Earlier observations are not comparable.
- The baseline writer moves to schema `1.3.0` for keyed budget names; the reader still accepts
  `1.0.0` to `1.2.0`.
- Contract schema stays `2.1.0`. New fields and declarations are optional; existing contracts
  keep their canonical bytes and amendment digests.
- Result JSON gains keys that are `null` when unused: `scan_roots`, `interface_budgets`,
  `unresolved_call_changes`, `unresolved_call_note` and `filtered_calls`.
- The Dart profile refuses `symbol_placement`, `boundary_types`, `forbidden_construct`,
  `context_roots`, facade and coupling budgets, budgets on scalars it does not measure, and
  `report --only calls` with exit 2 `rule_unsupported_by_profile`.

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

## Self-observation

Archkeel parses 71 of 71 source files with 100% AST coverage. It resolves 5,358 of 6,675 calls,
partially resolves 815 and leaves 502 unresolved: 80.27% call-resolution coverage. The self-check
reports 0 known violations, holds its own modules acyclic and pins six coupling budgets;
`declared_rules` stays `UNKNOWN` because 18 positions remain undecided.

# Archkeel 0.6.0 — Deterministic evidence stays explicit

0.6.0 narrows what Archkeel claims. Distinct possible origins stay `UNKNOWN`; multiple paths to
one exact origin remain decidable. Verdict and measured coverage stay separate.

## Highlights

- **Selected measurements can be protected.** A contract may select from five existing
  deterministic scalars. Any drift fails. Reductions can be written back; new or increased debt
  requires explicit `--accept-new` when updating an existing baseline (AD-77, AD-89).
- **Compatibility shims are declared.** `declarations.compat` binds an old module to one exact
  target and a permanent or migration lifetime. The shim stays import-only and product code may
  not depend on it (AD-87).
- **Decision evidence is semantic evidence.** Direction roles used by validation are protected
  from drift rather than treated as neutral metadata (AD-78, AD-90).
- **Facade ambiguity means distinct origins.** Several aliases to one exact origin are decidable.
  Distinct possible origins remain `UNKNOWN` (AD-84).
- **Nested `Any` does not erase a known owner.** Only an untyped, unresolved or top-level `Any`
  owner makes private access `UNKNOWN` (AD-91).
- **Root layout fails at the contract boundary.** The root itself, nested descendants and entries
  under another root are invalid `allowed_children`; validation returns exit 2 before analysis
  (AD-86).

## Compatibility

- Analyzer version moves from `0.32.0` to `0.41.0`. Earlier observations are not comparable.
- The baseline writer moves from schema `1.0.0` to `1.2.0`; the reader still accepts `1.0.0` and
  `1.1.0`.
- Updating an existing baseline requires `--accept-new` for new or increased debt.
- Contract schema stays `2.1.0`. New declarations and rules are optional.

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

## Self-observation

Archkeel parses 66 of 66 source files with 100% AST coverage. It resolves 4,479 of 5,597 calls,
partially resolves 621 and leaves 497 unresolved: 80.03% call-resolution coverage. The current
self-check reports 0 known violations and `declared_rules: UNKNOWN`; coverage remains visible
instead of being folded into PASS.

# Archkeel 0.5.1 — Violations take focus

0.5.1 shortens the path from a full architecture report to the evidence that needs action.

- **Focus an open report on violations.** `Violations only` hides secondary detail while keeping
  the verdict, failures, known unknowns, violation rows and complete evidence access visible.
- **Show only violated graph edges.** Component flow can hide conforming, undecided and observed
  edges at the current level. An empty graph says that no violated edge exists there and points
  back to the full violations table; it never claims that the report is clean.
- **Evidence is unchanged.** Both controls are reversible browser views. They do not change the
  result, totals, exit code or canonical `architecture.json`, and the full report remains usable
  without JavaScript (AD-75).

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

# Archkeel 0.5.0 — A rule says how much it decided

0.4.0 gave a component a list of what it requires and a contract for what is inside it. 0.5.0
turns to what a rule is allowed to claim. A rule that inspected a boundary it could not read used
to be silent, and silence read as PASS. It now says how many positions it saw, how many it
decided, and why the rest were undecidable — and the run's verdict carries that word instead of
rounding it down to "no violation found".

The same question, asked of Archkeel's own promise to the outside, produced a second strand:
`archkeel.api` is now a declared surface whose every promised name and every type from a scanned
module that the analyzer can resolve is checked by the tool itself.

## Highlights

- **UNKNOWN is a verdict a run can report.** `declared_rules` reads UNKNOWN when a declared rule
  left a position it could not read, PASS when everything the contract governs was decided, FAIL
  when something was proven wrong. A violation still outranks an unknown. Exit codes and
  diagnostics do not move: this reports, it does not gate (AD-67, AD-72).
- **A type no component owns stays visible without making the verdict UNKNOWN.** `pathlib.Path`
  and `datetime.datetime` cross facades everywhere and no `public` list can answer for them, so
  they remain counted as `external_type` in the undecidable breakdown but do not change
  `declared_rules`. Otherwise PASS would be unreachable for any repository whose facade takes a
  `Path` (AD-72).
- **`archkeel.api` is the declared external contract.** One call, `load_violations`, with the two
  types it hands out declared beside it. `ir` performs no I/O, and no internal model crosses the
  boundary (AD-64, AD-70).
- **Every promised name and every resolvable exposed type from a scanned module is checked.** A
  `public_api` entry naming a module that does not exist, or a name absent from that module's own
  `__all__`, is `api_surface.missing`. Every type the shared annotation walk resolves from a
  declared entry's signature must itself be declared — including signatures reached through a
  re-export. Dotted names, mappings, nested subscripts, unions and forward-reference strings
  remain outside that walk (AD-66, AD-71, AD-73).
- **`boundary_types` reads a declared facade, not a naming convention.** Only a function the
  component's own `public` list covers is inspected, and a resolved type is a violation only when
  no component declares it. One walk of an annotation answers both the rule and the reachability
  reading, so the two cannot drift (AD-58, AD-63, AD-69).
- **Ambiguous bindings stay UNKNOWN instead of depending on record order.** A name claimed by
  distinct class or import bindings, or shared by a class or import and a function — including
  through an ambiguous re-export chain — is counted as `ambiguous_binding`; repeating the same
  import target remains one binding (AD-74).
- **A violation has a name, and a baseline may hold the ones already there.** `validate
  --baseline` rejects new or resolved baseline drift, `--write-baseline` records today's debt,
  and `--against` with an amendment binding exact digests fails a widening that nobody approved
  (AD-52, AD-61).
- **Twelve prohibitions became one permission.** A `requires` entry may name the modules it goes
  through, so a component opens a narrow door instead of the contract listing every closed one
  (AD-42).
- **The decision record is one file per decision**, indexed in document order, held to a length,
  and every `AD-NN` reference in any tracked text file must name a record that exists (AD-55).

## Breaking changes

- **Analyzer version 0.32.0.** Observations written by an earlier analyzer are not comparable;
  `delta` refuses them rather than comparing across versions (AD-3).
- **Successful runs can now report `declared_rules: UNKNOWN`.** The value already existed, but a
  consumer that equated exit 0 with PASS must now handle it. Exit codes are unchanged (AD-72).
- **A `public_api` entry is now checked.** A contract naming a module the scan never saw, or a
  name its module's `__all__` excludes, fails `validate` where it used to pass silently.
- **Contract `schema_version` stays 2.1.0.** Every field added in this range is optional and no
  new rule kind makes a valid 0.4.x contract invalid (AD-8).

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

## Self-observation

Archkeel's own contract holds 7 components and 9 `requires` entries under one `complete_requires`
rule, 16 rules in total, none decided by the agent. The analyzer measured its own source at 0.4.1
and at this release:

| Measurement | 0.4.1 | 0.5.0 | Explanation |
|---|---:|---:|---|
| Source files | 61 | 66 | The external API, the baseline and widening derivations, type fan-in |
| Contract rules | 25 | 16 | Twelve prohibitions became one `requires` entry with `through` (AD-42) |
| Components | 6 | 7 | `api`, the declared external surface (AD-64) |
| Violations | 0 | 0 | Now including `boundary_types` against the analyzer's own facades |
| Unresolved calls | 703 / 3982 | 426 / 4886 | A receiver whose type is statically obvious now resolves its stdlib method (AD-37, AD-40) |

The unresolved ratio fell from 17.65% to 8.72% while the analyzed call count grew by 904. Two runs
of `archkeel report` on the same commit write a byte-identical `architecture.json`.

# Archkeel 0.4.1 — PyPI links resolve outside the repository

0.4.1 changed no analyzer or contract behavior. The built PyPI description rewrites every local
README image and documentation link, and verifies that each rewritten asset exists. Its
self-observation is therefore unchanged from 0.4.0.

# Archkeel 0.4.0 — A component names what it needs, and what is inside it

0.3.0 made every ordered component pair a decision. That is n·(n-1) rules, and the cost is not the
top level but the next one: a second level on `check` drafted 132 of them. 0.4.0 replaces the
enumeration with a list. A component names the components it requires, and absence forbids the
rest; Archkeel's own contract fell from 46 rules deciding 30 pairs to 25 rules and 8 entries. On
that footing a component can describe its inside in a contract of its own, and the tool records it,
judges it, draws it and carries it through `check`.

## Highlights

- **A second level that runs end to end.** A component names the contract describing its inside;
  the observation records it, `ir` derives it, the same rule code judges it, the flow view opens
  the component into its sub-components and then into their modules, and a `check` snapshot
  carries both contracts so the lock stays verifiable (AD-20, AD-33, AD-34, AD-36).
- **`requires` instead of pair-by-pair prohibitions.** `complete_requires` makes the list
  checkable: a cross-component import no entry covers is a violation naming the importing module.
  Absence decides, so no pair is ever open where the rule is in force (AD-32).
- **The flow view opens.** Components, then the modules inside one, then the symbols inside one
  module. Every edge is drawn at one width with its import sites written on it, carries its
  direction and its verdict, and can be dragged, tapped or reached by keyboard (AD-10, AD-24).
- **Four review claims, counted where the command answers.** Symbols nothing references, bindings
  nobody reads, logic repeated outside its declared owner, and a component holding more than the
  whole level holds. Claims, never verdicts: no exit code depends on them. The terminal prints the
  counts and `--json` carries them, so an agent sees a claim without opening the page
  (AD-26, AD-30, AD-33, AD-35).
- **New rule kinds.** `sibling_isolation` isolates a set of peers with one rule instead of n·(n-1)
  prohibitions (AD-25); `complete_external_scope` fails a dependency no rule declares (AD-28);
  `any_annotation` (AD-27) and `placeholder_body` (AD-29) join the forbidden constructs.
- **A two-level sample you can run.** `make demo-onboarding` replays the whole loop on
  `fixtures/F-architecture` in about a second, one real command per step, from what `init` drafts
  to what the gate says when an agent crosses a boundary inside the level. A test holds every
  printed number, and the README figure, to what the commands answer.

## Breaking changes

- **Analyzer version 0.18.0.** Observations written by an earlier analyzer are not comparable, and
  `delta` refuses them rather than comparing across versions (AD-3).
- **A report whose target is still undecided reads FAIL.** It used to pass on an empty target, which
  reported a contract nobody had finished as a clean one (AD-23).
- **An inside's rules are recorded as `<component>:<rule id>`**, and its findings name them there.
  Only a contract that declares `inside` is affected; the id inside that contract file is
  unchanged (AD-36).
- **`ExpectationResult.passed` is removed.** Read `failures` instead: it answered the same question
  and no shipped command asked it.
- **Contract `schema_version` stays 2.1.0.** `requires` and `inside` are optional properties and a
  new rule kind makes no valid contract invalid, so a 0.3.0 contract needs no migration (AD-8).

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

## Self-observation

Archkeel's own contract is a decided target: 6 components, 8 `requires` entries and one
`complete_requires` rule where 30 pair rules used to stand, 25 rules in total, none decided by the
agent. `check` describes its inside in a contract of its own, with 3 sub-components whose
crossings carry 21, 6 and 2 import sites. The analyzer measured its own source at 0.3.0 and at
this release:

| Measurement | 0.3.0 | 0.4.0 | Explanation |
|---|---:|---:|---|
| Source files | 53 | 61 | Levels, claims, structure metrics and the duplication and binding collectors |
| Contract rules | 46 | 25 | 30 pair decisions became 8 `requires` entries under one rule (AD-32) |
| Violations | 0 | 0 | Now including `complete_requires` at both levels |
| `getattr` calls | 0 | 0 | Still forbidden everywhere |
| Typing positions | 46 | 48 | Two added with the level derivation; the 0.3.0 narrowing holds |
| Unresolved calls | 630 / 3303 | 703 / 3982 | New calls in the levels, claims and flow modules |

The unresolved ratio fell from 19.07% to 17.65%. Two runs of `archkeel report` on the same commit
write a byte-identical `architecture.json`.

# Archkeel 0.3.0 — The architect owns the target

Archkeel 0.3.0 turns onboarding into decisions about a target architecture. `init` proposes
components and interfaces but never decides a dependency; the architect decides every component
pair, directly or by reviewing what an agent decided, and the report draws where the code departs
from that target.

## Highlights

- **Component flow in the HTML report.** Component cards, edges weighted by import sites, violated
  edges with the rule they break, undecided edges in their own state, a legend and the heaviest
  connections. Offline, no external library, derived from `architecture.json` alone.
- **Onboarding as a decision interview.** Every ordered component pair must be decided once, by an
  `allowed_dependency` or a `forbidden_dependency` rule with a rationale. `init --json` and
  `validate --json` list the open decisions heaviest first, each with the exact rule to choose.
- **Two agent modes.** The packaged skill runs an interview (read ADRs and documents, recommend,
  ask only about conflicts and gaps, ask why on a deviation) or auto mode (the agent decides from
  documents, then principles, then labeled judgment). Every rule records `decided_by`, and reports
  count the agent decisions the architect has not reviewed.
- **Decided means enforced, and counted once.** A `forbidden_dependency` between two components
  applies to every package of both, and an import it rejects is not counted again as an interface
  violation (AD-18).
- **Measured on a real service.** A 13-component internal service was onboarded by interview and,
  blind, in auto mode: 156 pair decisions each, first reports FAIL with 162 and 199 violations, and
  the agent matched 140 of the architect's 156 decisions before review. Anonymized evidence and the
  findings that did not work are in `docs/evidence/internal-service/`.

## Breaking changes

- **Contract 2.1.0.** Adds `allowed_dependency` and a required `decided_by` on every rule. A 2.0.0
  contract no longer decodes; decide each component pair and set `decided_by`.
- **Validation codes.** `decision.open` replaces `closed_world.missing`; `decision.conflict` is new.
  An observed import no longer counts as a decision.
- **`init` output.** `init` writes no dependency rule and returns `open_decisions`.
- **`accept` removed.** The placeholder command, which always exited 2, is gone until acceptance is
  implemented.
- **Analyzer version 0.10.0.** Observations from earlier analyzers are not comparable.

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

## Self-observation

Archkeel's own contract is a decided target: 6 components, each of the 30 ordered component pairs
decided by the architect, 46 rules in total, none decided by the agent. Component responsibilities
name the quality goal each boundary protects (AD-17). The analyzer measured its own source at
0.2.0 and at this release:

| Measurement | 0.2.0 | 0.3.0 | Explanation |
|---|---:|---:|---|
| Source files | 43 | 53 | Scanner split into single-purpose collectors; decisions, interfaces and flow view added; `accept` removed |
| Violations | 0 | 0 | Now including `allowed_dependency`, `interface_boundary` and every open decision |
| `getattr` calls | 0 | 0 | Still forbidden everywhere |
| Typing positions | 187 | 46 | Analyzer records share one typed envelope and codec JSON is narrowed at the boundary (AD-2) |
| Unresolved calls | 593 / 2830 | 630 / 3303 | New calls in the decisions, interface and flow view modules |

The unresolved ratio fell from 20.95% to 19.07%. Two runs of `archkeel report` on the same commit
write a byte-identical `architecture.json`.

# Archkeel 0.2.0 — Deterministic onboarding

Archkeel 0.2.0 lets a coding agent set up the architecture contract and keeps every decision
it cannot make visible as a validation diagnostic.

## Highlights

- `archkeel init` observes the only top-level package and drafts `archkeel.toml`, a closed
  Contract 2.0 and `docs/architecture/architecture.md`. On Archkeel itself it reproduces the
  hand-written component rules pair for pair.
- `archkeel validate` checks contract structure, package and provenance references, closed-world
  coverage, rule rationales and the marked component graph. Every diagnostic names a JSON
  Pointer, so the output is the onboarding worklist.
- `archkeel skill install claude|codex` installs one packaged instruction source for coding
  agents; [docs/onboarding.md](https://github.com/rapiddweller/archkeel/blob/main/docs/onboarding.md)
  contains the prompt to hand over.
- The class-A rule catalog is enforced: `forbidden_dependency`, `forbidden_construct`,
  `external_dependency_scope`, `complete_assignment` and `no_component_cycles`, each proven by
  a violation test. See [docs/rules.md](https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md).
- Terminals get a Rich summary with the decision sentence of the HTML report, verdicts,
  regression checks and diagnostics. Every command has `--help` with examples and exit codes,
  and `--json`.
- `schema/architecture-contract.schema.json` describes Contract 2.0; tests keep it equal to the
  parser verdict on a valid and invalid corpus.

## Breaking changes

- **Contract 2.0.0.** Class-C fields move under `declarations`. A 1.1.0 contract returns exit
  `2` with a migration remedy; follow
  [Migrating from 1.1.0](https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md#migrating-from-1-1-0).
- **Terminal output.** When stdout is a terminal, `report`, `check` and `validate` print the
  summary. Pipes still receive JSON; pass `--json` to get JSON in a terminal.
- **Dependencies.** `rich` and `rich-argparse` are new runtime dependencies. Contract rules
  confine them to `archkeel.render.terminal` and `archkeel.cli`.
- **Diagnostics.** The new kind `existing_files` reports that `init` would overwrite files.

## Install

```bash
uvx archkeel --help
pip install --upgrade archkeel
```

## Self-observation

Archkeel's analyzer measured its own source at `0ffd413` and at this release:

| Measurement | 0ffd413 | 0.2.0 | Explanation |
|---|---:|---:|---|
| Source files | 38 | 43 | Onboarding, terminal view, skill, summary and rule evaluation modules |
| Violations | 0 | 0 | Now including construct, dependency-scope, assignment and cycle rules |
| `getattr` calls | 14 | 0 | Replaced by explicit types |
| Typing positions | 180 | 187 | +14 raw record annotations in the new rule evaluation module |
| Unresolved calls | 507 / 2547 | 593 / 2830 | New calls into Rich, argparse and standard-library values |

The unresolved ratio rose from 19.91% to 20.95% only in new modules; existing modules such as
the scanner, report and validation resolve more calls than before.

# Archkeel 0.1.0

Archkeel adds deterministic architecture evidence to AI-assisted code review.
It checks whether a repository remains observable, follows its architecture
contract, and matches a change declaration published before submission.

## Highlights

- Run as a standalone Python package with the bundled analyzer.
- Define scan roots, namespace, and contract in `archkeel.toml`.
- Generate canonical `architecture.json` evidence with `archkeel report`.
- Review the same evidence in a self-contained `interactive.html` report.
- Compare accepted and candidate commits with `archkeel check`.
- Detect forbidden imports, cycles, private crossings, typing regressions,
  unresolved-call regressions, coverage loss, and changed finding fingerprints.
- Keep scan completeness, contract compliance, and expectation fulfillment as
  three separate verdicts.
- Return stable exit codes: `0` for pass, `1` for rejection, and `2` when the
  result cannot be verified.
- Validate declaration order from supplied host records or GitLab merge-request
  evidence.

## Install

Archkeel requires Python 3.11 or newer.

```bash
python -m pip install archkeel==0.1.0
archkeel --help
```

## Quick start

Add `archkeel.toml` to the repository:

```toml
[scan]
roots = ["src/example"]
namespace = "example"
contract = "architecture-contract.json"
```

Generate architecture evidence:

```bash
archkeel report --root . --output architecture.json
```

The command writes `architecture.json` and a portable `interactive.html` review
surface beside it.

## Current scope

- Python repositories are supported.
- `report` and `check` are available.
- `accept` is a placeholder and returns exit `2`.
- GitHub is used for distribution and CI; declaration-order retrieval currently
  has a GitLab adapter. Portable host records can be supplied explicitly.

See the [README](https://github.com/rapiddweller/archkeel) for the full protocol,
configuration, check command, and report preview.
