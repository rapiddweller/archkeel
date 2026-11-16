# AD-626: `init` drafts open decisions from the folder layout and decides nothing

## Context

A project without `archkeel.toml` had no way forward (#1314). `validate` refused with
`collect: unsupported: config: cannot read archkeel.toml`, and `init` said "use release 4.0.1".
Release 4.0.1 drafted the files from observed imports with a large module (`check/onboarding.py`).
The shell decides nothing and reads no source (AD-432), so that design cannot return as it was.

## Decision

1. `archkeel init` is a command of the shell. It writes three files below the root and replaces
   none: `archkeel.toml`, `architecture-contract.json` and `docs/architecture/architecture.md`.
   If one of them exists, `init` refuses with `io_error` and writes nothing.
2. The draft reads the folder layout only: the one top-level Python package in `src/` (or in the
   root), and its subpackages. No source file is read, so `init` cannot give a wrong fact.
   A layout with no package or with several packages is refused with `invalid_input`; the message
   names the packages found and links `docs/onboarding.md`, where the files are written by hand.
3. Each subpackage is one component. The modules beside the subpackages are one component `root`,
   so that every module has an owner. The contract has two rules: `complete_assignment` and
   `no_component_cycles`.
4. Each decision is the word `TODO`: every responsibility (`decided_by: architect`) and every
   rationale. The core already reports them as open (`responsibility.missing`,
   `rationale.placeholder`). The cited document holds a component graph without edges, so the core
   reports `graph.drift` with the edges that it found. The first verdict is UNKNOWN, and its list
   is the list of decisions that the user makes. The draft never produces PASS.
5. A project without `[project].requires-python` gets one note from `init`: the core cannot prove
   the scan scope without it.
6. `validate` and `report` check that the configuration file exists before they start the core. A
   missing file is `invalid_input`, exit 2, and the message names `archkeel init` and the guide.
7. Rule `SHELL-NO-INIT-TO-FRAME` and the part `init` keep the draft apart from the verdict reader.

## Alternatives and limit

- Draft the dependencies from imports, as 4.0.1 did. That needs source facts, so the shell would
  need the core for it. The core's `graph.drift` already lists the found edges, so the user sees
  them at the first run. A later `init` that asks the core is possible.
- Python only. Rust, TypeScript and Dart layouts need a language rule for the namespace and the
  components (crate, directory, library). They stay manual with the example in the guide.
- One package only. A layout with several packages needs a choice of the user.
- The names of the draft (`root`, `COMP-*`) are not checked against a name that the user keeps.

## Checks

`tests/test_cli_init.py` walks a fresh plant with three subpackages: refusal that names `init`, the
draft, UNKNOWN with four open responsibilities, a second `init` that refuses, the decisions, PASS,
and an import against them, FAIL. The shell contract and its pinned rows hold the new part.
