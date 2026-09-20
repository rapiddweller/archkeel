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
complete report/successful check, 1 for a rejected check or a `validate --baseline` run whose
baseline no longer matches the code, 2 for unverifiable inputs.
Every exit 2 includes a Diagnostic with `kind`, `subject`, `unknown_claim` and a
one-line `remedy`. Partial analyzer observations retain their typed coverage and
are persisted by `report`. Invalid locks are never replaced with empty state.
IR JSON decoding and encoding belongs to `ir/codec.py`; core models are frozen dataclasses.
`report` and `check --output` write `<output-stem>.report.html` and `<output-stem>.check.html`. The suffix separates commands; the stem separates runs.
The `report` headline follows its verdicts, not the exit code alone: exit 0 with `declared_rules: FAIL` renders a FAIL headline, because `report` records violations without gating and `check` is the gate.
Without `--source` and `--namespace`, `init` scans the only top-level Python package under `src/`, or under the root when there is no `src/`; when several sit side by side it scans the one whose name matches `pyproject.toml`'s `[project] name` in wheel file-name form (runs of `-`, `_` and `.` become `_`, compared case-insensitively), and otherwise exits 2 with `scope_empty`, naming the packages it found and the name it compared (AD-47).
`init --json` and `validate --json` add `open_decisions`, heaviest observed pair first, each with its `allowed_dependency` and `forbidden_dependency` option rule (AD-15). `validate` and `report` add `agent_decisions` as `[agent, total]` decisions: one rule declaration, one `requires` entry or one declared `public` list each, at either level, and one nobody attributed counts in the total alone (AD-16, AD-50), and `violations_by_rule` as `[rule, count]` pairs with `violations_by_component_pair` as `[source, target, count]` triples, heaviest first (AD-51); a violation that crosses no component pair, such as a construct or a cycle, appears only in the first. `init --json` also adds `draft_sizes`, one `{label, modules, inner_edges}` entry per drafted component, from the same aggregation `report`'s structure metrics use (AD-38); the terminal names whichever one uniquely leads by modules, or that none does.
`validate --write-graph` rewrites the edges of the one marked component graph, `<!--
archkeel-component-graph -->`, from the observed imports, and, where a page also carries `<!--
archkeel-target-graph -->`, that marked target graph from `target_component_edges`: every pair a
`requires` entry or an `allowed_dependency` rule permits (AD-57). Both are sorted the way `init`
writes them (AD-46), and each is rewritten independently: a page may carry either marker, both, or
neither, and only markers actually present are checked or written. The rest of the page stays as
it was, and so do a rewritten block's diagram declaration, such as a `flowchart LR`, and its `%%`
comments, ahead of the edges; a block without a declaration gets `graph TD`. It writes only a page
that changes and names it in `artifact`; the observed marker still requires exactly one across the
contract's provenance documents, or `graph.count` remains, while the target marker is silent when
absent and `graph.count` only if it appears more than once. A block holding any other line, such as
a `subgraph`, a labeled edge or a `classDef`, is not rewritten: `graph.drift` remains for that
marker, and its remedy names the line and asks for the edges to be edited by hand; the diagnostic's
subject always names which marker, for example `docs/architecture/shop.md (target graph)`. The page
is read and written as UTF-8 with `\n` line endings. The demo rows `validation-graph-drift-write-graph`
and `validation-graph-drift-subgraph` show both remedies for the observed marker on the shop sample,
whose own page draws both graphs and (today) has them agree; `validation-target-graph-drift-write-graph`
and `validation-target-graph-drift-subgraph` show the same two remedies isolated to the target marker,
with the observed marker still passing.

`validate --baseline <file>` holds the run against a file of known violations, for a contract
that states the target architecture and so is violated by the code that has yet to reach it
(AD-52). Each entry names one violation by fingerprint — the rule ids it cites and its sorted
`subjects`, the modules, construct owner or cycle members it is about — with the number of
violations sharing it. No position enters a fingerprint, so an unrelated edit above a violating
line leaves it alone, while the `VIO-` id in `architecture.json` still moves. Counts must match
the observation exactly: a higher one is reported as `new violation`, a lower one as `resolved
violation`, both in `failures` with exit 1, so the budget only shrinks. A run whose baseline is
exactly right exits 0 with `declared_rules: FAIL`. Only `rule.violated` is answered this way;
every other diagnostic still exits 2, as does a baseline that cannot be read
(`baseline.invalid`). `--write-baseline` writes the observed violations to that same path,
indented and sorted for review, and writes nothing from a run that exited 2. `validate` with no
`--baseline` behaves exactly as before. The file's shape is
`schema/violation-baseline.schema.json`:

```json
{
  "schema_version": "1.0.0",
  "violations": [
    {
      "count": 2,
      "rules": ["CONSTRUCT-NO-DYNAMIC"],
      "subjects": ["shop.model.probe.read"]
    }
  ]
}
```

`validate --against <ref>` classifies every difference between the contract at that Git
revision and the one being validated - and, with `--baseline`, the baseline file there too - as
a widening (a new permission or a dropped restriction) or a narrowing, its harmless reverse
(AD-61, #11). Enumerated per rule kind and per component field: a new `allowed_dependency` rule,
a removed `forbidden_dependency`/`forbidden_construct`/`external_dependency_scope`/
`complete_assignment`/`complete_external_scope`/`complete_requires`/`no_component_cycles`/
`interface_boundary`/`sibling_isolation` rule, a gained `allowed_sources` or `exact_sources`
entry, `include_type_checking` relaxed from true to false, a gained component `public` or
`requires` entry, and a component added or removed, are each widening; every reverse is
narrowing. A padded baseline entry - a higher count or a new fingerprint - is a widening too,
compared the same way against the baseline file at `--against`. Only a rule's or a `requires`
entry's `rationale`, and every `provenance`, are neutral; any other difference - an unrecognised
rule kind's presence, a field no classifier names, `declarations`, `$schema` - fails closed as a
widening. A widening is reported in `failures` with exit 1, exactly like `--baseline` drift,
unless `--amendment <path>` names a file binding this exact before/after contract digest pair,
each a SHA-256 of `ir.codec.contract_bytes`' canonical form via `ir.codec.contract_digest` - the
way the lock binds its own inputs - with free-text `decided_by` and `rationale`. An amendment
written for one change does not verify against a different one. `--write-amendment`, with
`--decided-by` and `--rationale`, writes that file instead of checking it. A missing or malformed
`--amendment` file is `amendment.invalid`, exit 2; an `--against` revision or its contract that
cannot be read is `against.invalid`, exit 2. `validate` without `--against` is unchanged. The
file's shape is
[`schema/contract-amendment.schema.json`](https://github.com/rapiddweller/archkeel/blob/main/schema/contract-amendment.schema.json):

```json
{
  "schema_version": "1.0.0",
  "before_digest": "16c9c52202633a0fad7bd3e954ab03156d7d73b7f336d1f963b06ecfb3c20551",
  "after_digest": "f91beec8a28f71f4651000345fddaad2898ebcaa7ba7739b30ce9e6013d66c1c",
  "decided_by": "Jordan (architect)",
  "rationale": "Orders needs the sqlite exemption during the migration."
}
```

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

## Narrowing a report

`report --only violations` shows only the declared-rule violations table, hiding component
flow, component communication, review claims and size and coupling, so a large repository's
page stays a small review surface; `--rule <id>` and `--component <label>` each narrow that
table further and combine as an intersection. `--component` matches a violation whose crossing
touches it on either side, source or target, since an import violation crosses two components
(AD-60). All three read the same on `--json`: `report_filter` names the flags that produced the
run and `filtered_violations` carries the records they select, one `Record` per row exactly like
every other JSON section; both read `null` on an unfiltered run, the same way every other
optional `report` field reads `null` when it has nothing to carry.
None of the three changes what was judged: `architecture.json`, `declared_rules`,
`violations_by_rule`, `violations_by_component_pair`, the `violations` measurement and the exit
code all keep reading every violation, filtered or not. A filtered result still announces
itself: the HTML decision banner carries `data-report-filter="true"` and a `Filtered (...): N of
TOTAL violation(s) shown.` sentence, and the terminal prints the same sentence in its own panel.
`--rule` matches a fingerprint's rule id exactly, top-level or the `<component>:<rule id>` an
inside declares (AD-36); `--component` matches only a top-level component, since
`ViolationRow.source_component`/`target_component` always come from the top level
(AD-34, AD-54). A `--rule` or `--component` naming nothing the contract declares is
`filter_unknown`, exit 2, not a silently empty page: `--rule` validates against every declared
rule id, `--component` against every top-level component label, whether or not either has a
violation today.

## Reading a report's violations

`archkeel.api` is the declared external contract (AD-64): the one supported way to read
`architecture.json` outside this repository, for a CI gate that wants named fields rather than
the columnar, string-interned file on disk. Its whole promise is `__all__`, exactly
`ViolationRow`, `load_observation` and `violation_rows`. `load_observation(path)` reads the file
and returns the `Observation` that `ir.codec`'s `decode_json`, `decode_canonical_model` and
`parse_observation` would otherwise take three internal calls to build - `ir` itself performs no
I/O (AD-17), so the read lives in the facade, not in `ir.codec` as AD-54 first placed it.
`violation_rows(observation)` turns its `violations` section into one typed `ViolationRow` per
violation - `fingerprint`, `source_module`, `target_module`, `symbol`, `source_component`,
`target_component` and `evidence_ids` - instead of a positional record. A field a violation kind
does not carry, such as a forbidden construct's `source_module`, is `None`, never a guessed
value.

```python
from pathlib import Path

from archkeel.api import load_observation, violation_rows

observation = load_observation(Path("architecture.json"))
rows = [
    (row.fingerprint, row.source_component, row.target_component)
    for row in violation_rows(observation)
]
```

`row.fingerprint` is AD-52's `(rules, subjects)` pair, the stable key that survives an edit
that moves the violating line without changing what the violation is; a stored baseline or a
CI gate keys on it, not on the record `id` in `architecture.json`, which moves with the line.
Not promised: the columnar file format `decode_canonical_model` inflates, and the internals of
every `ir` module, `ir.baseline` and `ir.codec` included - `archkeel.api` is what stays stable
across an `ir` refactor, not a shorthand for importing `ir` directly. `architecture-contract.json`'s
`COMP-API` `requires` entry names *this* repository's own crossing into `ir` (AD-9, AD-32); it
says nothing about what an outside reader may use, which is `archkeel.api.__all__` alone (AD-64).
`archkeel.ir.codec.load_observation`, the pre-AD-64 path, is removed, not deprecated: the surface
was days old at 0.4.x, so there is one supported way in, never two.

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
The sdist's `only-include` carries what rebuilds the wheel, `src`, `schema` and the declared
`README.md`: the test suite needs a Git checkout it cannot have from a tarball, so distributors
rebuild it from the Git tag instead of receiving it half-working.

## Release versions

Versions come from Git tags. A clean checkout of `1.2.3` or `v1.2.3` builds
version `1.2.3`; commits after the tag produce development versions. Release
builds need the Git history and tags. No fixed fallback version is configured.

The README keeps its relative hero path for local previews. PyPI metadata uses
an absolute image URL; the build does not rewrite the source README.
