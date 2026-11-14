# ArchKeel

<p>
  <img src="docs/assets/archkeel-mark.svg" alt="ArchKeel" width="96">
</p>

> **State of `main` (issue [#880](https://github.com/rapiddweller/archkeel/issues/880)).**
> The Rust core `archkeel-core` is the only engine. The Python engine is deleted.
>
> - `archkeel validate` and `archkeel report` run through the core, as text or JSON.
>   PASS exits 0, FAIL exits 1, UNKNOWN and a refusal exit 2.
> - Only **Rust and TypeScript projects** are supported. Python and Dart profiles give exit 2.
> - `check`, `init`, `explore`, `guide`, `story`, `view` and `studio` give a typed refusal with exit 2.
>   Interactive reports, `architecture.json`, baselines and focused reports are not available.
> - `report --output PATH` writes one static HTML page; `--format json` writes the core frame instead.
> - No package carries the core binary yet. Run `main` from a source checkout after `make core`.
>   An installed package refuses each run with `core_binary_not_found`. There is no Python fallback.
> - Release 4.0.1 has `check`, `init` and full reports for Python, Dart and TypeScript projects.
>   No release has Studio or `explore`. See the [state of `main`](docs/reference.md#state-of-main).

**See what your code really does. Check it against what you decided.**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-5EEAD4?labelColor=141414)
[![CI](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml/badge.svg)](https://github.com/rapiddweller/archkeel/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/archkeel)](https://pypi.org/project/archkeel/)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757?labelColor=141414)](#claude-code)
[![Codex plugin](https://img.shields.io/badge/Codex-plugin-8A8A8A?labelColor=141414)](#codex)
[![MIT](https://img.shields.io/badge/license-MIT-C5F82A?labelColor=141414)](https://github.com/rapiddweller/archkeel/blob/main/LICENSE)

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

## Install

ArchKeel needs Python 3.11+ and a Git repository with at least one commit.

```bash
uv tool install git+https://github.com/rapiddweller/archkeel
archkeel --version
```

This installs the current `main` without the core binary, so each run refuses with exit 2.
`uv tool install archkeel` installs release 4.0.1 from PyPI, which has the Python engine.
To run `main`, use a source checkout:

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

`validate` and `report` need an `archkeel.toml` with `language = "rust"` or `"typescript"` and a
contract. `init`, which drafts a contract, is in release 4.0.1 and not on `main`.

Read the verdicts: on `main`, `report` has the exit codes of `validate`.
`archkeel --help` lists the commands and options. See the [reference](docs/reference.md).

## FAQ

**Does ArchKeel use an LLM to check my code?** No. Checks are deterministic static analysis and run
locally. The agent in your harness explains and proposes; its text is a claim, never a proof.

**Does ArchKeel change my repository?** `validate` and `report` write nothing by default.
`report --output PATH` replaces the named regular file atomically. `skill install` writes one skill file.

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
