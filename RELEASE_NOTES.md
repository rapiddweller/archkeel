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
