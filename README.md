# ArchKeel

<p align="center">
  <img src="docs/assets/archkeel-hero.png" alt="ArchKeel: deterministic architecture checks. PASS, FAIL or UNKNOWN." width="100%">
</p>

**See what your code really does. Check it against what you decided.**

[![CI](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml/badge.svg)](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml)
[![core self-check](https://img.shields.io/endpoint?url=https://rapiddweller.github.io/archkeel/self/core-badge.json&labelColor=141414)](https://rapiddweller.github.io/archkeel/self/core.html)
[![shell self-check](https://img.shields.io/endpoint?url=https://rapiddweller.github.io/archkeel/self/shell-badge.json&labelColor=141414)](https://rapiddweller.github.io/archkeel/self/shell.html)
![verdict: PASS, FAIL or UNKNOWN](https://img.shields.io/badge/verdict-PASS%20%C2%B7%20FAIL%20%C2%B7%20UNKNOWN-46bfd0?labelColor=141414)
![no LLM in the verdict](https://img.shields.io/badge/LLM%20in%20the%20verdict-none-e8805d?labelColor=141414)

![engine: Rust](https://img.shields.io/badge/engine-Rust-e8805d?labelColor=141414)
![checks Rust and TypeScript](https://img.shields.io/badge/checks-Rust%20%C2%B7%20TypeScript-46bfd0?labelColor=141414)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757?labelColor=141414)](#claude-code)
[![Codex plugin](https://img.shields.io/badge/Codex-plugin-8A8A8A?labelColor=141414)](#codex)
[![MIT](https://img.shields.io/badge/license-MIT-a8a8ab?labelColor=141414)](https://github.com/rapiddweller/archkeel/blob/main/LICENSE)

**See it live.** ArchKeel checks itself, and these reports follow the current `main`:
[the product, two parts](https://rapiddweller.github.io/archkeel/) ·
[the Rust core](https://rapiddweller.github.io/archkeel/self/core.html) ·
[the Python shell](https://rapiddweller.github.io/archkeel/self/shell.html) ·
[the fixture showcase](https://rapiddweller.github.io/archkeel/showcase/index.html).
The self reports show each FAIL and each UNKNOWN row as it is. Each one has its cause pinned in the repository.
The showcase has Python, Dart and TypeScript projects; the Rust core is the first self report. Every showcase row is UNKNOWN today: most name a gap in the contract checks, and some name a rule kind that the core does not read yet.

[Install](#install) · [Quick start](#quick-start) · [Why](#why-archkeel) · [Compared](#archkeel-floorplan-or-understand-anything) · [Features](#features) · [FAQ](#faq)

ArchKeel reads your code: the parts, the imports between them and the evidence for each. You or
your coding agent declare the boundaries you want. ArchKeel checks the code against them and
reports forbidden imports, misplaced types and gaps in the analysis, with source evidence.

The checks run on your machine and use no LLM. The agent explains and proposes; ArchKeel measures and enforces.

## Why ArchKeel?

You, or your coding agent, built a lot of code. Do you know the architecture it really has?
Tests tell you the behavior still works. They do not tell you that `render` now imports `store`,
or that a call became harder to resolve. Asking the agent "is the architecture still fine?" gets
you an opinion.

ArchKeel was built to understand the architecture that was really implemented, and to turn it
into one you choose:

1. **Measure.** Static analysis resolves imports. Each fact keeps its evidence: the record and the
   source line. What the analysis cannot resolve is counted, not hidden.
2. **Challenge.** You and your agent discuss the weak spots: violations, cycles, components that
   hold too much. The agent proposes. Its text stays a claim until the code proves it.
3. **Define and enforce.** You decide the target architecture. Existing imports are evidence, not
   permission. The contract becomes rules. A rule passes only with complete evidence; missing
   evidence is `UNKNOWN`, never a quiet `PASS`.

## ArchKeel, Floorplan or Understand Anything?

All three turn code into something you can see. They answer different questions, and they get
their facts in different ways.

| | **ArchKeel** | **[Floorplan](https://github.com/haydenschmitty/floorplan)** | **[Understand Anything](https://github.com/Egonex-AI/Understand-Anything)** |
|---|---|---|---|
| **Question** | How does our code work, which architecture do we want, and does the code keep to it? | How does the app I built work, and what should I worry about? | How does this large codebase work, down to the functions? |
| **Where the facts come from** | Native static analysis of Rust and TypeScript, with evidence records and source lines | Scripts scan files, imports and web requests by pattern matching ("not a compiler", in its docs); the AI names and describes the parts | Deterministic scripts plus a multi-agent LLM pipeline that builds the knowledge graph |
| **What is unknown** | Counted and shown as `UNKNOWN` | Missed links can be added by asking the AI | Relationships can come from LLM judgment |
| **Role of the LLM** | Explains and proposes. No part of a check or verdict uses it | Writes the architecture description and the names | Summarizes, finds relationships, writes tours |
| **What you end with** | A declared contract with rules and verdicts, and an exit code for CI | A map, a health check, recent work | A knowledge graph, layers, guided tours |
| **Runs in** | Claude Code, Codex, any shell, CI | Claude Code, Codex | Claude Code, Codex and more |

Understand Anything teaches the story behind a codebase. ArchKeel measures the architecture you actually have and holds it to the one you choose.

Pick **ArchKeel** to turn what the code does into an architecture you can enforce. Pick **Floorplan**
or **Understand Anything** to learn a codebase quickly and in plain words. They combine well: learn
first, then declare what you want to keep.

## Features

- **Evidence on every edge.** Every import count comes from the code. Each import keeps its
  evidence record and source line. No model estimates a number.
- **PASS, FAIL, UNKNOWN.** A rule passes only with complete evidence. A gap in the analysis shows
  as `UNKNOWN`.
- **Made for coding agents.** A skill for Claude Code and Codex, and JSON results with a typed
  status.

## State of `main`

Issue [#880](https://github.com/rapiddweller/archkeel/issues/880). The Rust core `archkeel-core`
is the only engine. The Python engine is deleted.

- `archkeel validate` and `archkeel report` run through the core, as text or JSON.
  PASS exits 0, FAIL exits 1, UNKNOWN and a refusal exit 2.
- **Rust and TypeScript projects** are supported, and the import rules of Python and Dart projects.
- `check`, `init`, `explore`, `guide`, `story`, `view` and `studio` give a typed refusal with exit 2.
  Interactive reports, `architecture.json`, baselines and focused reports are not available.
- `report --output PATH` writes one static HTML page; `--format json` writes the core frame instead.
  `report --topology` adds a bounded topology section to the frame.
- The [reports of the current `main`](https://rapiddweller.github.io/archkeel/) show what the core says
  for ArchKeel itself and for each project of `fixtures/`, refusals included.
- No release carries the core binary yet. The release workflow builds the platform wheels with the
  core (AD-476), but the last release is 4.0.1. Run `main` from a source checkout after `make core`.
  A package without the core refuses each run with `core_binary_not_found`. There is no Python fallback.
- Release 4.0.1 has `check`, `init` and full reports for Python, Dart and TypeScript projects.
  No release has Studio or `explore`. See the [state of `main`](docs/reference.md#state-of-main).

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
archkeel report --output report.html  # one static page; the parent must exist
```

`validate` and `report` need an `archkeel.toml` with `language = "rust"` or `"typescript"` (or
`"python"` or `"dart"` for import rules) and a contract. `init`, which drafts a contract, is in release 4.0.1 and not on `main`.

Read the verdicts: on `main`, `report` has the exit codes of `validate`.
`archkeel --help` lists the commands and options. See the [reference](docs/reference.md).

## FAQ

**Does ArchKeel use an LLM to check my code?** No. Checks are deterministic static analysis and run
locally. The agent in your harness explains and proposes; its text is a claim, never a proof.

**Does ArchKeel change my repository?** `validate` and `report` write nothing by default.
`report --output PATH` replaces the named regular file atomically. `skill install` writes one skill file.

**Does a clean graph mean a good design?** No. `PASS` means the required rules have complete evidence
and no decided violation. It does not prove runtime behavior or the quality of a design decision.

**Which languages?** Rust and TypeScript on main, and the import rules of Python (AD-450) and Dart
(AD-468) projects. Use archkeel 4.0.1 for the other Python and Dart rules.


## Scope and limits

ArchKeel observes static Rust and TypeScript source in configured roots through native collectors.
Python and Dart projects get PASS or FAIL only for rules that read the import graph.
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
make self-validate        # the core checks native/ and the Python shell against their pinned results
make report-gallery       # build the reports that the site shows, in test-artifacts/gallery
```

ArchKeel checks its own Rust source (`native/archkeel.toml`) and its own Python shell
(`docs/architecture/shell.toml`) with `make self-validate`. Each rule row is pinned with its cause
in `native/expected-gaps.json` and `docs/architecture/target/shell-expected.json`.
The [live reports](https://rapiddweller.github.io/archkeel/) show both results.
See [CONTRIBUTING.md](https://github.com/rapiddweller/archkeel/blob/main/CONTRIBUTING.md).

MIT © 2026 Rapiddweller Asia Co., Ltd. Maintained by [Alexander Kell](https://github.com/ake2l).
