# ArchKeel

> **State of `main` (issue [#880](https://github.com/rapiddweller/archkeel/issues/880)).**
> The Rust core `archkeel-core` is the only engine. The Python engine is deleted.
>
> - `archkeel validate` and `archkeel report` run through the core, as text or JSON.
>   PASS exits 0, FAIL exits 1, UNKNOWN and a refusal exit 2.
> - Only **Rust and TypeScript projects** are supported. Python and Dart profiles give exit 2.
> - `check`, `init`, `explore`, `guide`, `story`, `view` and `studio` give a typed refusal with exit 2.
>   HTML reports, `architecture.json`, baselines and focused reports are not available.
> - No release carries the core binary yet. Run `main` from a source checkout after `make core`.
>   A package without the core refuses each run with `core_binary_not_found`. There is no Python fallback.
> - Sections with the mark **Not on `main`** describe the engine before this change.
>   Release 4.0.1 has `check`, `init` and full reports for Python, Dart and TypeScript projects.
>   No release has Studio or `explore`.

**See what your code really does. Check it against what you decided.**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-5EEAD4?labelColor=141414)
[![CI](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml/badge.svg)](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/archkeel)](https://pypi.org/project/archkeel/)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757?labelColor=141414)](#claude-code)
[![Codex plugin](https://img.shields.io/badge/Codex-plugin-8A8A8A?labelColor=141414)](#codex)
[![MIT](https://img.shields.io/badge/license-MIT-C5F82A?labelColor=141414)](https://github.com/rapiddweller/archkeel/blob/main/LICENSE)

[Install](#install) · [Quick start](#quick-start) · [Why](#why-archkeel) · [Compared](#archkeel-floorplan-or-understand-anything) · [Features](#features) · [Live demo](https://rapiddweller.github.io/archkeel/demos/) · [FAQ](#faq)

<p>
  <img src="docs/assets/archkeel-hero.png" alt="ArchKeel: see what your code really does, check it against what you decided. ArchKeel's own architecture, simplified: cli requires studio, render, analyzer and check, which share the ir component. PASS, 126 rules, 0 UNKNOWN." width="1000">
</p>

ArchKeel reads your code and shows how it is built: the parts, the imports between them and the
evidence for each. You or your coding agent then declare the boundaries you want. ArchKeel checks
the code against them and reports forbidden imports, misplaced types and gaps in the analysis, with
source evidence for review.

The checks run on your machine and use no LLM. The agent explains and proposes; ArchKeel measures and enforces.

## Why ArchKeel?

You, or your coding agent, built a lot of code. Do you know the architecture it really has?
Tests tell you the behavior still works. They do not tell you that `render` now imports `store`,
or that a call became harder to resolve. Asking the agent "is the architecture still fine?" gets
you an opinion.

ArchKeel was built to understand the architecture that was really implemented, and to turn it
into one you choose:

```text
 Understand   Show     Measure    Challenge       Define          Enforce
 what was     it as a  it with    weak spots and  the target      every change
 built        map      evidence   violations      architecture    in CI
```

1. **Understand and show.** Static analysis resolves imports and calls. Studio and the Explorer
   draw the as-built architecture: components, hubs, cycles, with a guided tour (not on `main`).
2. **Measure.** Each fact keeps its evidence: the record and the source line. What the analysis
   cannot resolve is counted, not hidden.
3. **Challenge.** You and your agent discuss the weak spots: violations, cycles, components that
   hold too much. The agent proposes. Its text stays a claim until the code proves it.
4. **Define and enforce.** You decide the target architecture. Existing imports are evidence, not
   permission. The contract becomes rules. A rule passes only with complete evidence; missing
   evidence is `UNKNOWN`, never a quiet `PASS`. CI rejects the change that crosses a boundary.

## ArchKeel, Floorplan or Understand Anything?

All three turn code into something you can see. They answer different questions, and they get
their facts in different ways.

| | **ArchKeel** | **[Floorplan](https://github.com/haydenschmitty/floorplan)** | **[Understand Anything](https://github.com/Egonex-AI/Understand-Anything)** |
|---|---|---|---|
| **Question** | How does our code work, which architecture do we want, and does the code keep to it? | How does the app I built work, and what should I worry about? | How does this large codebase work, down to the functions? |
| **Where the facts come from** | Native static analysis of Rust and TypeScript, with evidence records and source lines | Scripts scan files, imports and web requests by pattern matching ("not a compiler", in its docs); the AI names and describes the parts | Deterministic scripts plus a multi-agent LLM pipeline that builds the knowledge graph |
| **What is unknown** | Counted and shown as `UNKNOWN` | Missed links can be added by asking the AI | Relationships can come from LLM judgment |
| **Role of the LLM** | Explains and proposes. No part of a check or verdict uses it | Writes the architecture description and the names | Summarizes, finds relationships, writes tours |
| **What you end with** | A declared contract with rules, verdicts, Target and Diff views, a baseline, a CI gate | A map, a health check, recent work | A knowledge graph, layers, guided tours |
| **Runs in** | Claude Code, Codex, any shell, CI | Claude Code, Codex | Claude Code, Codex and more |

Understand Anything teaches the story behind a codebase. ArchKeel measures the architecture you actually have and holds it to the one you choose.

Pick **ArchKeel** to turn what the code does into an architecture you can enforce. Pick **Floorplan**
or **Understand Anything** to learn a codebase quickly and in plain words. They combine well: learn
first, then declare what you want to keep.

## Features

<table>
<tr>
<td width="50%" valign="top">

**🗺️ Studio, a local web app** (not on `main`)<br>
`archkeel studio` serves the map on `127.0.0.1` with a token for each run. It writes nothing
into your repository and works offline.

</td>
<td width="50%" valign="top">

**🔎 Evidence on every edge**<br>
Every import count comes from the code. Each import keeps its evidence record and source line.
No model estimates a number.

</td>
</tr>
<tr>
<td valign="top">

**🧭 A tour from measured facts**<br>
A tour walks the code in order ("start here, then here"). The author writes the title and note of a stop. The
numbers beside it are measured and shown apart.

</td>
<td valign="top">

**🎯 As-Is, Target and Diff**<br>
Compare the observed code with the declared architecture. Cycles, violations and hubs stay visible.

</td>
</tr>
<tr>
<td valign="top">

**🚦 PASS, FAIL, UNKNOWN**<br>
A rule passes only with complete evidence. A gap in the analysis shows as `UNKNOWN`.

</td>
<td valign="top">

**🤖 Made for coding agents**<br>
A skill for Claude Code and Codex, and JSON results with a typed status. Focused reports and the
check of a submitted change are not on `main`.

</td>
</tr>
</table>

## Install

ArchKeel needs Python 3.11+ and a Git repository with at least one commit.

```bash
ARCHKEEL_BUNDLE_NATIVE=1 uv tool install git+https://github.com/rapiddweller/archkeel
archkeel --version
```

This builds the current `main` with its core binary. The build needs `cargo` and `cargo-auditable`,
and it refuses without the variable, because a package without the core refuses each run.
`uv tool install archkeel` installs release 4.0.1 from PyPI, which has the Python engine.
You can also run `main` from a source checkout:

```bash
git clone https://github.com/rapiddweller/archkeel.git
cd archkeel
make core                                         # build archkeel-core with cargo
uv run archkeel validate --root /path/to/project  # the project needs archkeel.toml and a contract
```

### Claude Code

```bash
claude plugin marketplace add rapiddweller/archkeel
claude plugin install archkeel@archkeel
```

### Codex

```bash
codex plugin marketplace add rapiddweller/archkeel
codex plugin add archkeel@archkeel
```

No plugin? `archkeel skill install claude` (or `codex`) writes the same instructions into your repository.
The plugin needs the CLI above; it adds the agent skill.

## Quick start

```bash
archkeel validate        # check the contract: exit 0, 1 or 2
archkeel report --text   # the same frame of the core as a report
```

`validate` and `report` need an `archkeel.toml` with `language = "rust"` or `"typescript"` and a
contract. `init`, which drafts a contract, is in release 4.0.1 and not on `main`.

Start with the [first-hour guide](docs/getting-started.md) or the [onboarding guide](docs/onboarding.md).
Both guides describe the engine before this change. Read the verdicts: on `main`, `report` has
the exit codes of `validate`. `archkeel --help` lists the commands and options.
See the [exit codes](docs/reference.md#exit-codes).

## Where Studio is going

> **Target picture.** These images are design targets for ArchKeel Studio, not shipped features.
> Studio is not on `main` ([AD-432](docs/architecture/decisions/ad-432-the-rust-core-is-the-only-decision-path.md)); its design is in ([AD-290](docs/architecture/decisions/ad-290-archkeel-studio-is-a-local-web-application.md)).
> The work is tracked in [#822](https://github.com/rapiddweller/archkeel/issues/822).

The goal: an architect opens Studio and understands what the agent built. Every fact is measured.
The agent writes only the words, and ArchKeel checks each claim.

<p>
  <img src="docs/assets/studio-target/explore-chat-map.jpg" alt="Target: the component map as a dependency graph with call counts on the lines" width="1000">
</p>

**Map.** Components as a graph. A line is the number of calls between two components; dotted means mostly partial (a claim).

<p>
  <img src="docs/assets/studio-target/explore-chat-lens.jpg" alt="Target: the explore lens with a structure tree, module plates and an agent chat" width="1000">
</p>

**Explore with the agent.** A lens around one function, a structure tree and a location bar so you always know where you are, and a chat that separates what ArchKeel observed, what the agent claims and what is only proposed.

<p>
  <img src="docs/assets/studio-target/story-lanes-status-step9.jpg" alt="Target: a story of archkeel check with lanes, a route line and a status on every step" width="1000">
</p>

**Stories.** A flow plays through the real architecture. Each step is proven, a claim or unknown. The same grammar scales to a large system: [a story of 27 steps over a 1,185-module codebase](docs/assets/studio-target/ee-story-process-boundary.jpg), with the process boundary and the external systems it touches.

## See it in action

<p>
  <img src="docs/assets/archkeel-self-check.png" alt="ArchKeel's report of its own code: 126 rules PASS, 0 UNKNOWN, findings with source lines, and the Target view with component responsibilities" width="1000">
</p>

**Not on `main`.** This is the HTML report of the engine before this change, on its own Python
code: 126 rules `PASS`, 0 `UNKNOWN`, every finding with its source line, and the declared Target
with the responsibility of each component. On `main`, ArchKeel checks its Rust code with the core.
[Open the live report](https://rapiddweller.github.io/archkeel/architecture.report.html?content=components&view=target&theme=dark).

<p>
  <img src="docs/assets/archkeel-compass-target.png" alt="ArchQ Explorer embedded in the report: Compass Flutter Target with components, responsibilities and declared dependencies" width="1000">
</p>

The static report was the artifact for CI and Pages: one offline file, the same Explorer.
The published pages are the last ones; `main` does not publish new ones.
[Explore Compass Flutter's declared architecture](https://rapiddweller.github.io/archkeel/demos/uml-compass-project/architecture.report.html?content=components&view=target&theme=dark),
see [ArchKeel's current Main report](https://rapiddweller.github.io/archkeel/), or browse the
[Python, Dart and TypeScript demo reports](https://rapiddweller.github.io/archkeel/demos/) with UML PASS, FAIL and UNKNOWN examples.

The gallery leads with three complete source projects: [Compass booking](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c) (111 Dart files), [Python RealWorld](https://github.com/nsidnev/fastapi-realworld-example-app/tree/029eb7781c60d5f563ee8990a0cbfb79b244538c) (72 Python modules), and [Nest RealWorld](https://github.com/mikro-orm/nestjs-realworld-example-app/tree/a6818d84b6a019cf2df4ef391dc87cea7d02c6a9) (41 prepared TypeScript inputs). Each links its authored Target, baseline and three source-only variants. Coverage, rule findings and UML results remain separate.

## Review the evidence

<p>
  <img src="docs/assets/archkeel-python-module-target.png" alt="ArchQ Explorer in fullscreen: Python RealWorld Target with nested article, comment and tag modules" width="1000">
</p>

**Not on `main`:** the HTML report, the Explorer and the focused reports (`--only`, `--input`).

Fullscreen Explorer: drill down to Python RealWorld's article, comment and tag modules.
[Explore this Target](https://rapiddweller.github.io/archkeel/demos/uml-python-realworld-project/architecture.report.html?scope=Product%20and%20wire%20contracts%3Acontracts-publishing&content=modules&view=target&theme=dark).
Target shows declared intent; cross-scope relationships remain counted separately.

Use the report to inspect findings and source locations, then explore the components.
Filters narrow the view without changing the verdicts.

```bash
archkeel report --only violations --component store
archkeel report --only calls --component store
```

Agents start with a focused architecture summary, then query the recorded snapshot:

```bash
archkeel report --only architecture --json
archkeel report --input test-artifacts/architecture/architecture.json --only architecture --json
```

Use `--component` with an id or scope from the summary, and `--only violations` for findings.
Saved queries do not rescan or change the repository. See [focused agent reports](docs/reference.md#focused-agent-reports).

ArchQ Explorer shows **As-Is** (observed code), **Target** (declared architecture),
and **Diff** (their differences). These are views of one snapshot, not two revisions.
It opens inside the report. **Fullscreen** expands the same Explorer;
**Restore** keeps your selection and zoom. Search (`Ctrl/⌘+K`), Health check,
Objects and perspectives help navigate the recorded evidence.
Folders help navigation; they do not establish ownership or runtime behavior.

The fact sheet summarizes boundary permissions until you select a scope. Its complete
audit remains available on demand. Health check builds the import matrix when opened;
Structure overview shows neutral component measurements without size-based recommendations.

`PASS` means the required rules have complete evidence and no decided violation.
`UNKNOWN` means evidence is missing. A rule can fail and still have undecided positions.
A clean graph does not prove a good design.

Dart and TypeScript rules use complete evidence for their own scopes. An unrelated
resolution gap can coexist with a proven rule PASS; a confirmed violation remains FAIL
alongside incomplete observation. Strict JSON consumers should use command-result
schema 9. Current Python observations require an explicit call-binding proof or null
for every call. See the [compatibility policy](docs/reference.md#compatibility)
before upgrading collectors or saved-report consumers.

## Keep a target the code has not reached

**Not on `main`:** baselines are in release 4.0.1. `main` refuses these options with exit 2.

Record existing violations, review the file, then reject new ones in CI:

```bash
archkeel validate --baseline known-violations.json --write-baseline
archkeel validate --baseline known-violations.json
```

Known violations remain `FAIL`. After fixing them, rewrite the baseline in the same change.
New or increased violations require explicit `--accept-new`; do not use it to hide a regression.
See the [target-first guide](docs/target-first.md) for the full workflow.

## FAQ

**Does ArchKeel use an LLM to check my code?** No. Checks are deterministic static analysis and run
locally. The agent in your harness explains and proposes; its text is a claim, never a proof.

**Does ArchKeel change my repository?** `validate` and `report` write nothing. `skill install`
writes one skill file.

**Does a clean graph mean a good design?** No. `PASS` means the required rules have complete evidence
and no decided violation. It does not prove runtime behavior or the quality of a design decision.

**Which languages?** Rust and TypeScript on main. Use archkeel 4.0.1 for Python and Dart projects.


## Scope and limits

ArchKeel observes static Rust and TypeScript source in configured roots through native collectors.
Python and Dart profiles give exit 2 before collection. They do not produce a partial result.
TypeScript records lexical UML declarations and statically bound relationships;
ambiguous bindings and unsupported constructs remain UNKNOWN. TypeScript roots may name files or directories.
ArchKeel does not prove runtime behavior, performance, or the quality of every design decision.
Separate test trees need their own scan and contract.

Exit meanings are defined [per command](docs/reference.md#exit-codes).

Read the [docs](docs/README.md).

## Development

The shell needs Python 3.11+. The core needs a Rust toolchain: `make core` builds
`native/target/release/archkeel-core`, and the shell finds it in the checkout.
Without the core binary, each run refuses with exit 2. There is no Python fallback.

```bash
make check                # lint, types, browser code check, tests
make gate                 # also build and isolated installs
make native-check         # Rust format, lints, tests, and the self-check
make self-validate-native # the core checks native/ against its pinned result
```

ArchKeel checks its Rust source with `make self-validate-native`: 63 rules PASS, 1 FAIL and
19 UNKNOWN, each pinned in `native/expected-gaps.json` with its cause.
See [CONTRIBUTING.md](https://github.com/rapiddweller/archkeel/blob/main/CONTRIBUTING.md).

MIT © 2026 Rapiddweller Asia Co., Ltd. Maintained by [Alexander Kell](https://github.com/ake2l).
