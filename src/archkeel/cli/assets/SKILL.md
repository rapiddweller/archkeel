---
name: archkeel
description: Use when setting up or changing architecture rules, or checking architecture before submitting code, in a repository that uses Archkeel.
---

# Archkeel

Archkeel is a deterministic architecture checker. It observes Python imports, evaluates a
declared contract of components and rules against that observation, and reports PASS/FAIL
per rule. Rules are declared once in `architecture-contract.json`; nothing is enforced by
convention alone.

## Onboarding (first time in this repository)

1. Run `archkeel init [--root DIR] [--source DIR] [--namespace NAME] [--force] [--json]`.
   It detects the Python package, requires an existing Git repository with at least one
   commit, and writes three files: `archkeel.toml`, `architecture-contract.json` (one
   component per top-level subpackage/module, a `forbidden_dependency` rule for every
   component pair with no import today, plus `complete_assignment` and — only when no
   component cycle exists — `no_component_cycles`), and
   `docs/architecture/architecture.md` (component table and Mermaid graph of observed
   edges). It refuses to overwrite existing files without `--force`.
2. Every generated rule rationale is a placeholder starting with `TODO:`. Run
   `archkeel validate --json` and read its diagnostics; each one carries a JSON Pointer
   (e.g. `/rules/3/rationale`) naming exactly what to fix.
3. Replace every `TODO:` rationale with the real architectural reason for that rule. Do
   not invent a reason you do not know — ask the component owner.
4. Check every edge in the Mermaid graph of `docs/architecture/architecture.md` with the
   owner. Observed edges are allowed; the contract must forbid every other component pair,
   so do not delete a generated `forbidden_dependency` rule. An unintended edge is a code
   change: remove the import, then add the `forbidden_dependency` rule for that pair.
5. Rerun `archkeel validate --json` until it exits 0.
6. Run `archkeel report` to produce evidence, then commit the three generated files
   (`archkeel.toml`, `architecture-contract.json`, `docs/architecture/architecture.md`).

## Daily loop

- Run `archkeel report --json` before submitting any change. A rule violation does not
  change the exit code; read the `declared_rules` verdict. Exit 2 means the evidence is
  incomplete; fix the diagnostic before trusting any verdict.
- If a rule fails, fix the code so the rule passes.
- Never weaken or delete a rule just to make a violation disappear, unless the component
  owner explicitly approves the change to the contract. A silently loosened rule hides the
  next real violation.

## Rule catalog (summary)

Class A rules are deterministic PASS/FAIL, evaluated from one observation:
`forbidden_dependency`, `forbidden_construct`, `external_dependency_scope`,
`complete_assignment`, `no_component_cycles`. `closed_world` — every component pair is
observed or forbidden — is an implicit Contract 2.0 invariant, not a rule you declare.
Class B regression checks compare an accepted observation with a candidate. Class C declarations
(capabilities, public API, context roots, owners) are recorded and reported, not enforced.
Class D review claims are planned and not yet implemented.

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
