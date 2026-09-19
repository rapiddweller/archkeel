# Archkeel reference

Exact rules behind the [README](../README.md). Code is the source of truth; this file explains it.

## Configuration

[schema/archkeel.schema.json](../schema/archkeel.schema.json) defines `archkeel.toml`.
Only `[scan]` with required `roots`, `namespace` and `contract` is accepted.
Paths are relative to the repository root. Scan roots are directories, not globs.
The architecture schemas live once under `schema/`; builds include them as package data.

## Analyzer and runtime

The Python analyzer is bundled under `archkeel.analyzer`. `report` and `check`
need no source checkout or private package. The analyzer runs in an isolated
subprocess and returns a typed observation at the analyzer boundary.
D-self verifies the bundled analyzer digest recorded in `fixtures/D-self/provenance.json`.

The analyzer records `python_version` separately from its digest. Missing or incompatible
`pyproject.toml` runtime requirements produce `runtime_mismatch`; AST parse errors only
use `parse_error` after a compatible runtime check. Git snapshots carry their own project metadata.
Delta comparison requires the same known full Python version; otherwise `incomparable_runtime`
returns exit 2. Historical observations without runtime provenance remain readable, not comparable.

The observation carries a `references` section beside `calls`: every use of a scanned symbol
that is not a call, such as a function put into a table, passed as an argument or read as a
property, with the symbols it resolves to (AD-26). Call metrics stay untouched, because coverage
counts the `calls` section alone. An observation written before a section existed no longer
decodes and fails closed with the missing section named (AD-3).

The checker hashes its installed Python package separately from the analyzer digest.
Delta schema 1.3.0 and expectation schema 1.2.0 bind `checker_digest`;
the evaluator verifies the running package.
Underscore-private imports belong to the Python decoded-IR profile in `check/python_profile.py`.

## Git predicate

`check` reads `architecture-accepted.json` from B and reobserves its accepted commit M.
B must be a lock-only child of M and the fetched accepted branch tip. E must be a
child of B changing only the expectation file, an ancestor of H, and present on the
fetched candidate branch. H must preserve the lock, configuration, contract and expectation.
The expectation binds B and the lock digest. The lock binds configuration, checker
and accepted observation digests, raw measurements and an opaque `approval_ref`.

## Host records

The GitLab adapter reads MR diff versions with `glab` using `CI_PROJECT_ID`,
`CI_MERGE_REQUEST_IID` and exact `CI_COMMIT_SHA == H`. It maps `head_commit_sha`
and host `created_at` into `(sha, event, timestamp)` records. Both E and H need
records; missing evidence is `UNKNOWN`, exit 2. E publication must precede the
first H submission. Commit author dates are not evidence.

`--host-records /trusted/records.json` replays records with exactly `sha`, `event`
(`expectation_published` or `candidate_submitted`) and timezone-aware `timestamp`.
CI owns record authenticity, fetched remote refs, branch protection and lock signing;
the core checks SHA binding and order. A local replay does not prove host authenticity.
The A/B/C fixtures use real local Git repositories and simulated host records and CI locks.

## Results

JSON results separate `observation_complete`, `declared_rules` and
`expectation_fulfilled`. `report` uses `n/a` for expectations. Exit codes: 0 for
complete report/successful check, 1 for a rejected check, 2 for unverifiable inputs.
Every exit 2 includes a Diagnostic with `kind`, `subject`, `unknown_claim` and a
one-line `remedy`. Partial analyzer observations retain their typed coverage and
are persisted by `report`. Invalid locks are never replaced with empty state.
IR JSON decoding and encoding belongs to `ir/codec.py`; core models are frozen dataclasses.
`report` and `check --output` write `<output-stem>.report.html` and `<output-stem>.check.html`. The suffix separates commands; the stem separates runs.
The `report` headline follows its verdicts, not the exit code alone: exit 0 with `declared_rules: FAIL` renders a FAIL headline, because `report` records violations without gating and `check` is the gate.
Without `--source` and `--namespace`, `init` scans the only top-level Python package under `src/`, or under the root when there is no `src/`; when several sit side by side it scans the one whose name matches `pyproject.toml`'s `[project] name` in wheel file-name form (runs of `-`, `_` and `.` become `_`, compared case-insensitively), and otherwise exits 2 with `scope_empty`, naming the packages it found and the name it compared (AD-47).
`init --json` and `validate --json` add `open_decisions`, heaviest observed pair first, each with its `allowed_dependency` and `forbidden_dependency` option rule (AD-15). `validate` and `report` add `agent_decisions` as `[agent, total]` rules (AD-16). `init --json` also adds `draft_sizes`, one `{label, modules, inner_edges}` entry per drafted component, from the same aggregation `report`'s structure metrics use (AD-38); the terminal names whichever one uniquely leads by modules, or that none does.
`validate --write-graph` rewrites the edges of the one marked component graph from the contract
and the observed imports before it validates, sorted the way `init` writes them (AD-46). The rest
of the page stays as it was, and so do the block's diagram declaration, such as a `flowchart LR`,
and its `%%` comments, ahead of the edges; a block without a declaration gets `graph TD`. It
writes only a page that changes and names it in `artifact`; with no marked graph or with several
it writes nothing, and `graph.count` remains. A block holding any other line, such as a
`subgraph`, a labeled edge or a `classDef`, is not rewritten: `graph.drift` remains, and its
remedy names the line and asks for the edges to be edited by hand. The page is read and written
as UTF-8 with `\n` line endings. The demo rows `validation-graph-drift-write-graph` and
`validation-graph-drift-subgraph` show both remedies on the shop sample, whose own page is already
in the form the command writes.

`selected_changes` may be `[]`, declaring that the candidate has no semantic change at all
(AD-39). Under that declaration `evaluate_expectation` fails on any entry in the delta's
`semantic_changes`, in any of the eight delta dimensions, not only the six fixed guardrail ones,
naming the dimension, the change kind and the fingerprint. A non-empty `selected_changes` keeps its
existing meaning: a dimension it does not name and that is not a fixed guardrail dimension is still
not checked, so an undeclared change there passes without producing any failure text. Five of the
six guardrail dimensions (`violations`, `cycles`, `private_crossings`, `typing_signals`,
`unknowns`) fail on any added entry whether declared or not; the sixth, `dependency_edges`, fails
only on an added entry `selected_changes` never named, since a declared new edge is ordinary
architecture growth, not a regression (AD-44).

## Regression checks

Regression checks add these scalars to the existing record counts and fingerprint checks:

| Guardrail | Scalar in the Python decoded-IR profile |
| --- | --- |
| No new violations | Violation records |
| No new cycles | Internal SCC edges, summed across observed levels |
| No new private crossings | Private cross-package import records |
| No new typing signals | Missing boundary annotation positions; other signals count once |
| No new unknowns | Unresolved calls; unknown record counts and fingerprints remain checked |
| Coverage must pass | Scan failure records; any incomplete scan is unverifiable |

The delta stores raw measurements for the accepted observation and candidate.
Schema, scope, analyzer and contract must match.

`calls_total` is the analyzer's `calls_analyzed`. With `U = calls_unresolved` and `T = calls_total`,
checks require `U_candidate <= U_accepted` and, when both totals exceed zero,
`U_candidate * T_accepted <= U_accepted * T_candidate`. No rounded percentages are used.
Zero total means `resolution: n/a`; the absolute regression check still applies.
Missing or inconsistent measurements produce `UNKNOWN`; regressions return failures.

The JSON field `ratchets` and Python identifiers such as `compare_ratchets` keep their
existing names for compatibility. Human-readable messages use "regression check".
Historical evidence and reproduction commands retain the names from their pinned commits.

## Fixtures

`make fixtures` reproduces A, B and C from `fixtures/A-dispatch`, `fixtures/B-posthoc` and
`fixtures/C-valid`. `fixtures/F-architecture` is the shop sample behind the demo catalog (AD-11).
It carries two levels: the top contract at its root, and the one `COMP-STORE` names for its inside
at `shop/store/architecture-contract.json` (AD-20).

Every ordered component pair is decided by one `allowed_dependency` or `forbidden_dependency`
rule (AD-15). D-self also checks that
all observed modules have declared components, that new IR modules receive explicit
analyzer prohibitions, and that analyzer imports stay within the declared IR API.

## Dependencies

Runtime: `packaging` parses PEP 440 `requires-python` ranges; stdlib has no equivalent.
`rich` renders the terminal view in `archkeel.render.terminal`, and `rich-argparse` formats
`--help` in `archkeel.cli`. `external_dependency_scope` rules in the contract confine all three
imports to exactly those modules through `exact_sources`, so no submodule of `archkeel.cli`
inherits `rich-argparse` (AD-49); JSON results never depend on them.
Build: Hatchling packages the root schemas; `hatch-vcs` derives versions from Git tags.
`hatch-fancy-pypi-readme` rewrites the local hero path only in distribution metadata.
Development: Ruff (lint/format), MyPy (strict),
Pytest. `make build` uses Twine only to validate distribution metadata.
The runtime fixture in `make check` requires Python 3.11 and 3.12.

## Release

GitHub Actions runs the complete check and smoke-tests both built distributions.
Version tags such as `0.1.0` or `v0.1.0` build version `0.1.0` and publish
through PyPI Trusted Publishing. The `pypi` GitHub environment and matching
PyPI publisher must be configured before pushing the first release tag.

## Release versions

Versions come from Git tags. A clean checkout of `1.2.3` or `v1.2.3` builds
version `1.2.3`; commits after the tag produce development versions. Release
builds need the Git history and tags. No fixed fallback version is configured.

The README keeps its relative hero path for local previews. PyPI metadata uses
an absolute image URL; the build does not rewrite the source README.
