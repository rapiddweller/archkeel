---
name: archkeel
description: Use when defining or reviewing the architecture of a repository, or when checking an Archkeel repository before submitting code ("does this change break the architecture?", "check the contract").
---

# Archkeel

Archkeel is a deterministic architecture checker. A native collector observes the code, the Rust
core evaluates a declared contract of components and rules against that observation, and the
verdict is PASS, FAIL or UNKNOWN. UNKNOWN is not PASS. Nothing is enforced by convention alone.

## What this line serves

The Rust core decides `validate` and `report`. There is no Python fallback. In a source checkout,
run `make core` to build the core binary first.

- `archkeel validate [--root PATH] [--config PATH] [--json | --text]` checks the contract.
  PASS exits 0, FAIL exits 1, UNKNOWN and a refusal exit 2.
- `archkeel report` prints the same frame with the same exit codes. Add `--topology` for the bounded
  topology. `--output PATH` writes one static HTML page; `--output PATH --format json` writes the
  frame instead: `archkeel report --output report.json --format json`. Without `--output`, the
  format option is refused. No file is written by default. The parent of `PATH` must exist.
- `archkeel skill install claude` or `archkeel skill install codex` writes this skill file.
- `archkeel init` drafts `archkeel.toml` and a contract from the folder layout (Python packages, a
  Cargo workspace, a package.json workspace). `validate` and `report` do it by themselves when
  `archkeel.toml` is missing, and never replace a file (`--no-init` or `ARCHKEEL_NO_INIT=1` writes
  nothing). Every decision in the draft is a `TODO`: the first verdict is UNKNOWN and lists them. Ask
  the owner for each decision; never fill one in alone. The walk is in `docs/onboarding.md`.

`check`, `explore`, `guide`, `story`, `view` and `studio` are refused with exit 2 and the
reason `not available on this development line`. Release 4.0.1 has `check`; no release
has the other four. Saved reports, `architecture.json`, amendments, `--component` and
`--write-graph` are refused by option name. A refusal is not a result: never report PASS after one,
and never run a refused command in a loop. Tell the owner and use release 4.0.1 when they need it.

## Which projects get a verdict

Rust and TypeScript projects: each rule kind that the core has ported is decided; a rule kind without a port is UNKNOWN.
Python and Dart projects: the rules that read the import graph are decided, and both decide `interface_boundary` (AD-504; Dart from the bound names of each import, AD-749, held by a `target_symbol` rule); a Dart cycle rule has its receipt from the package map of the survey (AD-800), and every other rule of both is UNKNOWN.

Do not report PASS for a supported subset of a project. Per-language limits are in
[known limits](https://github.com/rapiddweller/archkeel/blob/main/docs/known-limits.md).

## Configuration and contract

`archkeel.toml` names one scan. The [schema](https://github.com/rapiddweller/archkeel/blob/main/schema/archkeel.schema.json)
defines it:

```toml
[scan]
roots = ["src"]
namespace = "app"
language = "typescript"
contract = "architecture-contract.json"
```

`language` is `rust`, `typescript`, `python` or `dart`; a missing value selects `python`. The
contract lists components, `requires` entries and rules. Rule kinds and selectors are in the
[rule catalog](https://github.com/rapiddweller/archkeel/blob/main/docs/rules.md) and the
[reference](https://github.com/rapiddweller/archkeel/blob/main/docs/reference.md).
A component may name a contract of its own with `inside`; the core reads each mount.

The architect owns the target. Never write a rationale or choose an allowed dependency yourself:
ask, and write the architect's own words with `decided_by: "architect"`. Mark what you decided
without them `decided_by: "agent"`. Never treat an observed import as permission.

## Daily loop

1. Run `archkeel validate --json` before you submit a change. Read `status` and `frame.rules`
   (each rule id with its state), not only the exit code.
2. On FAIL, fix the code so the rule passes. Never weaken or delete a rule to make a violation
   disappear, unless the owner of the component approves the change of the contract.
3. On UNKNOWN, read the gaps and the rules that are UNKNOWN. Name them to the owner. Do not
   present UNKNOWN as PASS.
4. For a picture, run `archkeel report --topology --output report.html` and open the page.

## Exit codes

The [reference](https://github.com/rapiddweller/archkeel/blob/main/docs/reference.md) has the
per-command exit table. `--json` prints JSON also in a terminal; `--text` prints text also without one.
