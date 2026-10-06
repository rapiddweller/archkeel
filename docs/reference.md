# Archkeel reference

Exact rules behind the [README](../README.md). Code is the source of truth; this file explains it.

Report HTML follows the system light/dark theme. Python report/check headings use a valid
`[project].name`; missing or invalid names and other languages use the configured namespace.
The title does not change verdicts or repository evidence.

## Configuration

[schema/archkeel.schema.json](../schema/archkeel.schema.json) defines `archkeel.toml`.
Only `[scan]` with required `roots`, `namespace` and `contract` is accepted, plus the optional
`language`: `"python"` (the default when absent, so an existing file keeps its digest), `"dart"`,
or `"typescript"`. For Dart, `namespace` is the pubspec `name` and `roots` is normally `["lib"]`; a
`pubspec.yaml` whose `name:` differs from `namespace` is `parse_error` (AD-97). TypeScript roots
may be files or directories; Python and Dart roots are directories. Roots are repository-relative
and cannot overlap or use glob syntax.

`tsconfig` is valid only for TypeScript. If omitted, the parser selects `tsconfig.json`; runtime
loading checks that the file exists inside the repository. `collector_argv` optionally overrides
the collector command as a non-empty array of non-empty argument strings. Arguments stay separate
and no shell parses them. On Windows, use an executable plus script path instead of a `.cmd` shim.
Runtime loading checks that roots and `tsconfig` exist and stay inside the repository.

The architecture schemas live once under `schema/`; builds include them as package data.

`report` and `validate` read `archkeel.toml` at `--root`, or the file `--config` names relative
to it. One file holds one namespace, so a test tree beside the product is a second scope with its
own file, contract and run, such as `archkeel validate --config archkeel-tests.toml`; the
product's file and contract stay as they are (AD-101). Each result records the `scan_roots` it
read, and its scan-complete reason names them, so a pass says what it covered. `check` reads
`archkeel.toml` only, because its accepted lock binds one configuration digest. `report` writes
`test-artifacts/architecture/architecture.json` whatever `--config` names, so a second scope's
report takes its own `--output`, such as `test-artifacts/tests/architecture.json`; without it
the test report replaces the product report.

`validate` reads a relative `--baseline` or `--amendment`, and writes it with `--write-baseline`
or `--write-amendment`, relative to `--root` as well; an absolute path is used as it is. A path
that resolves outside the root, by `..`, an absolute path or a symlink, is `baseline.invalid` or
`amendment.invalid`, exit 2, read or write (AD-103). A second code base in `mobile/` is checked
from the repository root with `archkeel validate --root mobile --baseline
architecture-baseline.json`, which reads `mobile/architecture-baseline.json`. The root-prefixed
`mobile/architecture-baseline.json` names no file there and is `baseline.invalid`, naming both
paths; it never falls back to the working directory. `report --output` and `check --output` name
where an artifact goes, not an input, and stay relative to the working directory.

## Analyzer and runtime

The Python analyzer is bundled under `archkeel.analyzer`. `report` and `check`
need no source checkout or private package. The analyzer runs in an isolated
subprocess and returns a typed observation at the analyzer boundary.
D-self verifies the checker and complete observation against two saved digests in
`fixtures/D-self/provenance.json`; only Git HEAD/dirty are normalized.

Optional [`make rule-yield`](rule-yield.md) measures pinned rule findings and warm
evaluator replays. Missing pass evidence remains unavailable; timings are outside IR.

Rule selectors and construct behavior are in the [rule catalog](rules.md).

Collectors emit `runtime: {name, version, required}`. Core checks the actual runtime
against comparator ranges such as `>=3.11,<4`; `||` separates alternatives. Missing,
malformed or incompatible requirements produce `runtime_mismatch`. Python reads
`requires-python`; the bundled Dart directive parser runs on Python, not a Dart SDK.
`python_version` remains a compatibility field. AST parse errors only
use `parse_error` after a compatible runtime check. Git snapshots carry their own project metadata.
Delta comparison requires the same known full Python version; otherwise `incomparable_runtime`
returns exit 2. Historical observations without runtime provenance remain readable, not comparable.

Dart observations identify the bundled directive parser and the actual Python interpreter that
runs it. Comparison requires equal, known runtime and producer identities. No Dart SDK is used.
Producer identity uses its name and source digest; a distribution version label is metadata.
Different Dart file paths sharing one legacy module name leave target association UNKNOWN.
Snapshots copy selected Git blobs byte for byte, including resolver metadata; `export-ignore`
and `export-subst` cannot omit or rewrite them (AD-147). `make demo-snapshot-check` runs committed Python
and Dart comment-only checks against local bare origins with supplied host records.


`capabilities.constructs` lists `{name, status}` entries: `decided`, `partial` or
`unsupported`. A declared unsupported or absent construct returns exit 2. Partial
support adds counted rule UNKNOWNs even when no construct candidate was collected.
The analyzer digest hashes code; distribution versions remain labels.

The observation carries a `references` section beside `calls`: every use of a scanned symbol
that is not a call, such as a function put into a table, passed as an argument or read as a
property, with the symbols it resolves to (AD-26). Call metrics stay untouched, because coverage
counts the `calls` section alone.

`facade_types` on symbol records names the resolved types in declared functions, public
methods of published classes, and proven direct inherited generic methods (AD-65, AD-121).
`validate` reads these same dotted `module.Name` origins for unused-entry checks. Private
methods and unpublished classes do not count. Ambiguous inherited candidates stay separate.
Inherited boundary violations keep their raw `annotation` and stable identity; their title and
`resolved_types` name the concrete `module:Name` origins already proven by the signature walk,
including reached model fields (AD-137). Ambiguous substitutions remain UNKNOWN.
An observation written before a section existed no longer
decodes and fails closed with the missing section named (AD-3).

Facade annotation/re-export limits are in
[the rule catalog](rules.md#class-a-deterministic-rules) and
[known limits](known-limits.md#a-facade-type-position-is-not-always-decidable).

The checker hashes its installed Python package separately from the analyzer digest.
Delta schema 1.4.0 and expectation schema 1.2.0 bind `checker_digest`;
the evaluator verifies the running package.
Underscore-private imports belong to the Python decoded-IR profile in `check/python_profile.py`.

[`root_layout` and compatibility shims](rules.md#class-a-deterministic-rules)
retain their contract rules. `declarations.compat` records migration work in IR/HTML;
permanent shims do not add remaining-work counts.

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
CI supplies authenticated records, fetched refs and accepted locks; repository policy
controls branch protection. The core checks SHA binding and order. A local replay does not
prove host authenticity.
The A/B/C fixtures use real local Git repositories and simulated host records and CI locks.

GitHub PR CI adds a **report-only** job. `make github-pr-report REPOSITORY=owner/name
PULL_REQUEST=7 BASE=<full-sha> HEAD=<full-sha> OUTPUT=result.json` uses configured `gh` on
`github.com` to read the PR and its head repository's recent events. The API base/head must
equal the immutable run inputs, and the base must target that repository's `main`.
The output includes the existing check JSON and HTML, raw API sidecars and a `.github.json`
binding with their SHA-256 digests. Push observations validate repository, event ID, full
SHA-40 `head` and `before`, full `ref` and host `created_at`; duplicate IDs or invalid data are refused.

These observations **cannot prove first publication**. The [Events API](https://docs.github.com/en/rest/activity/events)
retains at most 300 events for 30 days and can lag 30 seconds to 6 hours. A missing event or
apparently complete page cannot establish absence of an earlier push. GitHub's
[`Commit.pushedDate`](https://docs.github.com/en/graphql/reference/commits) was removed on
2023-07-01; author/committer dates and PR `updated_at` are not publication evidence.
The tool returns exit 2 with UNKNOWN order, no comparison or measurements, and no host-source
certification. It never feeds partial events into `--host-records`. A missing or invalid accepted
lock at the exact base is a separate diagnostic; the tool creates no replacement.
CI uploads these artifacts without blocking PRs.

AD-143 adds a scoped causal mode: an authenticated original opened(E) receipt and
authoritative H in the same PR prove E precedes every H submission. It emits
`host_source: github_initial_pr_head` and receipt provenance, without inventing an H
timestamp. The normal timestamp mode remains strict. Missing or untrusted receipt,
baseline, producer origin or comparable digests stays UNKNOWN.

Run the reader from an **approved immutable Archkeel checkout**, with its matching
pinned checker. CE or another consumer owns the two collector YAMLs, not a vendored
reader. Candidate-controlled PR CI cannot authenticate its own reader origin.
The complete sole-job list and reviewed worker at B prove producer origin; run,
attempt, jobs and artifact sidecars retain the evidence without claiming caller SHA.

```bash
make -C <approved-archkeel> github-pr-report ROOT=<consumer> REPOSITORY=owner/name \
  PULL_REQUEST=7 BASE=<B> HEAD=<H> INITIAL_RUN=<opened-run-id> \
  EXPECTATION_COMMIT=<E> EXPECTED=expectation.json EXPECTED_DIGEST=<sha256> OUTPUT=result.json
```

A real forward check still needs an approved CI-owned accepted main B and a retained
authentic receipt. The collector executes no candidate code. Public repository
activation is owner-managed: GitHub's [default event policy](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
currently evaluates `pull_request_target` restrictions and starts enforcement on 2026-11-02.
No repository or organization setting is changed by this tool.

`make demo-github OUTPUT=<directory>` uses real local Git and simulated GitHub
receipts: opened(E) passes; opened(H), reopened, wrong-run, tampered and incomparable
controls stay UNKNOWN. Its existing reversed-timestamp protocol still fails.

## Results

`report` adds `rule_assessments`: one row per declared rule with status, violation and
undecided counts, evaluation evidence, rationale, decision owner and provenance. PASS needs
a completed evaluator receipt for the observed scope. Missing receipts or undecided positions
remain UNKNOWN; a rule with violations stays FAIL while retaining its undecided count.
`allowed_dependency` is a permission, labelled DECLARATION rather than PASS. These per-rule
rows do not count a multi-rule UNKNOWN twice globally. Any UNKNOWN non-declaration rule makes
the aggregate UNKNOWN; a known violation remains FAIL. The report headline reads NOT CHECKED.
Cycle-scope completeness currently requires recursive Python scans;
module-cycle proof needs the whole
namespace. Smaller scans, explicit `source_paths`, and Dart cannot prove that completeness,
but observed violations still produce FAIL.

Components own modules through recursive `packages` and optional exact dotted names in
`exact_modules` (AD-128). Exact names may stand alone and never include descendants. Every observed
module must have exactly one owning component; competing selectors do not have precedence.
Omitted and empty `exact_modules` preserve legacy contract serialization and digests.
Open pairs involving exact selectors retain every selector in JSON; Archkeel does not generate
automatic rule suggestions for them. An unqualified rule between uniquely declared package
endpoints still decides a mixed package/exact pair. Submodule and `target_symbol` rules remain
partial; exact-only pairs stay open under member rules unless `complete_requires` applies.

`report --baseline known-violations.json` optionally adds a read-only comparison. The path
resolves inside `--root`; no baseline is discovered automatically or rewritten. Fingerprint
counts identify known, new, reduced and resolved debt without inventing identity for repeated
occurrences. Resolved counts require complete evaluation of the old subjects under the current
rule and zero undecided positions. Removing a rule or narrowing its scope cannot resolve debt
that is no longer checked. Cycle contraction also requires coverage of the old cycle's members.
Resolved means absent under current rules, not necessarily repaired code: baselines contain no
historical rule definitions. Use `validate --against` to check contract widening.
The baseline and report filters do not change canonical `architecture.json` bytes or gate
semantics. The diagram remains first; the rule and finding tables support search and filters.
Without JavaScript, the tables remain readable and inactive filter controls are hidden.

JSON results separate `observation_complete`, `declared_rules` and
`expectation_fulfilled`. `report` uses `n/a` for expectations.
For a complete, valid observation, `declared_rules` is FAIL with violations; otherwise UNKNOWN
with counted undecided positions or any UNKNOWN rule assessment; otherwise PASS ([AD-124](architecture/decisions/ad-124-rule-pass-requires-complete-scope-receipt.md)).

### Exit codes

| Command | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `check` | Accepted | Rejected | Input or evidence unverifiable |
| `validate` | Validation accepted | Baseline, budget or widening rejected | Validation diagnostics; inspected verdicts remain available |
| `report` | Observation complete; read rule verdict | — | Input or evidence unverifiable |
| `init` | Draft written | — | Draft unavailable; read diagnostic |
| `skill install` | Instructions written | — | Target file could not be updated |

Every exit 2 includes a Diagnostic with `kind`, `subject`, `unknown_claim` and a
one-line `remedy`. Partial analyzer observations retain their typed coverage and
are persisted by `report`. Invalid locks are never replaced with empty state.
IR JSON decoding and encoding belongs to `ir/codec.py`; core models are frozen dataclasses.

[`command-result.schema.json`](../schema/command-result.schema.json) describes the JSON
stdout of `check`, `validate` and `report` (AD-138). It is included under `archkeel/schema`
in installed packages. Its version is the `$id` suffix, currently `4.0.0`; command output
gains no version field. Pin the CLI and schema together. Register the bundled
`architecture-ir-common.schema.json`, `architecture-ir-decoded.schema.json`,
`architecture-ir-python-decoded.schema.json` and
`architecture-contract.schema.json` by
their `$id` for offline Draft 2020-12 validation. This schema excludes argument-parser,
`init` and `skill` results, and the separate canonical `architecture.json` artifact.
`null` means unavailable or inapplicable; `[]` means a measured empty list. Missing required
fields are invalid. Exit 2 requires diagnostics. Completed `validate` inspections retain their verdicts and
measurements; incomplete results retain UNKNOWN verdicts and null measurements.
A validation diagnostic rejects the contract even when inspected rules PASS. A report may
exit 0 with FAIL or UNKNOWN declared rules; consumers must read the verdicts.
[The small consumer fixture](../fixtures/consume_result.py) preserves that distinction.

Compatibility uses semantic versions for this schema: optional properties that older
consumers can ignore are additive (minor); removing or renaming a field, requiring a new
field, changing its type/nullability or meaning, or extending an enum is breaking (major).
Enum additions change what a consumer must handle. Corrections accepting the same payloads
are patch changes. Consumers must ignore unknown result properties; separately versioned
references retain their own constraints.
Schema validation checks shape, not source authenticity, count arithmetic or conformance.

`report` and `check --output` write `<output-stem>.report.html` and `<output-stem>.check.html`. The suffix separates commands; the stem separates runs.
Use validation with your existing baseline to gate changes; reports remain read-only.
Diff shows recorded imports through component ownership without requiring UML intent.
Its inspector limits findings to the selected subject or opened scope. Expand
**Global or unmapped findings** for evidence without a known graph subject (AD-200).

The report's declared-facade section measures export counts, re-exports, names defined in each
facade, unused re-exports, consumers per export and distinct exported names per component pair.
They do not assert that a barrel is complete (AD-88). `validate` measures
`declarations.facade_budgets` and `declarations.coupling_budgets` with the same values and
returns each as an `interface_budgets` entry: `budget`, `subject`, `pointer`, `max_names`,
`count`, `over_target`, `names`, `uncounted`, and, with `--baseline`, `new_names` and
`removed_names`.
A pair counts a name reached through a re-export chain. Without a baseline, a count over its
target is `budget.exceeded`; with one, only a new or removed name fails. A count the scan cannot
complete - a whole-module facade whose `__all__` is not one untouched non-empty literal, a
whole-module import of a facade module, a star import of a non-enumerated facade, or a name a
non-enumerated facade does not list - is `budget.unknown` at exit 2 (AD-99).
Without explicit Python scope, `init` selects the sole top-level package under
`src/` (or the root if no `src/`). Multiple packages require one match with normalized
`[project].name`: runs of `-`, `_`, `.` become `_`, case-insensitively. Otherwise
`scope_empty` names packages and the compared name (AD-47).

`init --json` adds open pairs, heaviest first, and `{label, modules, inner_edges}`
`draft_sizes`. Validation retains open pairs until `complete_requires` decides absence.
Validation/report results count agent-owned rule declarations, `requires` entries
and public lists at each level as `[agent, total]`; unattributed decisions count only
in total. `violations_by_rule` uses `[rule, count]` and `violations_by_component_pair`
uses `[source, target, count]`, heaviest first. Non-crossing violations appear only
in the first (AD-15, AD-16, AD-38, AD-50, AD-51).

`validate --write-graph` updates marked provenance diagrams from observed imports
(`<!--
archkeel-component-graph -->`) and permissions (`<!--
archkeel-target-graph -->`).
Each marker is checked/written independently. Provenance requires exactly one observed
marker; Target is optional and duplicate markers produce `graph.count`.

Sorted edge writing preserves the diagram declaration and leading `%%` comments;
missing declarations default to `graph TD`. Other lines such as subgraphs, labeled
edges or `classDef` prevent rewriting and keep `graph.drift` with a manual remedy.
Diagnostics name the affected marker. Only changed pages are written, listed in
`artifact`, as UTF-8 with `\n` line endings (AD-46, AD-57).
See [the catalog](architecture-demo.md) for observed/Target write and subgraph cases.

`validate --baseline <file>` compares known violation fingerprints and selected
measurements with current evidence (AD-52). Fingerprints contain sorted rule IDs
and subjects without positions; list ordering is irrelevant (AD-106). Counts must
match exactly: rises are `new violation`, falls `resolved violation`, both exit 1.
A strict subset of a baselined cycle is contracted debt, not a new cycle (AD-98).
`baseline_new` and `baseline_resolved` count changed fingerprints, not occurrences.

An exact baseline exits 0 even with `declared_rules: FAIL`. It answers only
`rule.violated`; other diagnostics retain exit 2. Unreadable/outside-root baselines
are `baseline.invalid`. Writes first compare existing files: resolved-only drift
and contracted cycles can be written, while new/increased fingerprints require
explicit `--accept-new`. Exit 2 writes nothing (AD-106).

`declarations.measurement_budgets` may select `cycle_edges`, `private_crossings`,
`typing_positions`, `calls_unresolved`, `untyped_private_accesses` and `unknown_positions`. Each
declaration carries provenance. A selected value must equal the baseline: a rise is new debt; a
fall must be written back. A contract selecting budgets without `--baseline`, or an incomplete measurement, exits 2.
The file stores values, not call sites, so without `--against` a `calls_unresolved` rise reads
`measurement budget exceeded in calls_unresolved: 7->8; validate --against <ref> names the call
sites` (AD-100).
Contracts without measurement budgets behave as before. A declared facade or coupling budget
needs no baseline, but with one the file holds its accepted names under `facade_names` or
`coupling_names`: a name outside them fails as a rise, a name gone as a fall (AD-99). The file's
shape is `schema/violation-baseline.schema.json`:

```json
{
  "schema_version": "1.3.0",
  "budgets": {
    "calls_unresolved": 12,
    "coupling_names": {"app -> model": ["shop.model.entities:Money", "shop.model.entities:Order"]},
    "cycle_edges": 0
  },
  "violations": [
    {
      "count": 2,
      "rules": ["CONSTRUCT-NO-DYNAMIC"],
      "subjects": ["shop.model.probe.read"]
    }
  ]
}
```

Directional violation entries may add sorted `roles` objects with `source` and `target`. Roles
do not change the fingerprint, but they are protected semantic evidence because validation may
use them. `validate --against` reports role-only drift. Baseline schemas `1.0.0` and `1.1.0`
remain readable.

For target-first cleanup, schema 1.1 roles can also prove that a resolved importer was the last
reach of one exact `public` module or symbol. `validate --baseline` then keeps the resolved
baseline failure and reports the required interface narrowing; it does not make unrelated or
unroled entries valid (AD-85).

`validate --against <ref>` compares the historical contract and optional baseline.
New permissions or removed restrictions widen; their reverse narrows (AD-61):

- New `allowed_dependency`, removed restriction rules, gained `allowed_sources`/
  `exact_sources`, relaxed `include_type_checking`, added `public`/`requires`, and
  added/removed components widen. `boundary_types` and `symbol_placement` are restrictions.
- Adding component `namespace` narrows; removing/changing it widens.
- Changing cycle `level` either way, adding a `components` scope or dropping its
  member widens; removing the scope or extending it narrows (AD-98).
- Padded violation counts, raised/removed measurement values, raised/removed name
  ceilings and expanded accepted names widen. Contracted cycles narrow. Adding
  measurement declarations narrows; removing them widens (AD-99).
- Only rule/`requires` rationale and provenance are neutral. Unclassified differences,
  including declarations and `$schema`, fail closed as widening.

A package rename is compared away first (AD-105): the
component packages that moved, such as `shop.render` to `shop.view`, propose a prefix
substitution. It holds when every prefix relation among the old contract's and baseline's
module names and the renamed prefixes survives it, when no module the scan reads or an import
reaches lies under an old prefix, whatever its file is called, and when the directory where the
scan's layout reads each old prefix holds no file at all, scanned or not, outside `__pycache__`;
a prefix that layout cannot place is no rename. Candidates go shortest first, and one whose renamed old contract the
parser refuses is skipped; with none left, the comparison stays field by field and an amendment
can accept it. Only the module and symbol fields `ir.model.module_references` lists are renamed;
ids, labels, kinds, `decided_by` and constructs never are, nor paths, so a moved `inside`
contract still compares as a changed `inside`. `reference.namespace` checks the same fields as
before, the entries of that list marked `held`. The old contract and baseline are then renamed
before the comparison, so a pure rename passes without an amendment and a widening beside it
fails alone. `renames` in the JSON result lists each old and new prefix (`[]` when none holds,
`null` when no revision was compared) and the terminal names them. Where no
rename holds, a gained `public` entry names the one lost entry of its kind and last name, when
no other gain matches it: `gained 'b.api.x' in place of 'a.api.x'`. The CLI pins the revision and
reads the exact selected `--config` there; missing or malformed history cannot authorize a rename.
Every Python rename candidate requires a complete historical layout scan, even when configured
roots and namespace are unchanged: physical layout can move within those roots. Changed-root Dart
renames are not supported; same-root Dart renames keep their existing behavior. A widening is
reported in `failures` with exit 1, exactly like `--baseline` drift,
unless `--amendment <path>` names a file binding this exact before/after contract digest pair,
each a SHA-256 of `ir.codec.contract_bytes`' canonical form via `ir.codec.contract_digest` - the
way the lock binds its own inputs - with free-text `decided_by` and `rationale`. An amendment
written for one change does not verify against a different one. `--write-amendment`, with
`--decided-by` and `--rationale`, writes that file instead of checking it. A missing or malformed
`--amendment` file, or one outside the root, is `amendment.invalid`, exit 2. A contract the `--against` revision does not
hold, a new scope's or one moved to a new path, is one widening, `contract introduced: <path>
does not exist at <ref>`. Its amendment's `before_digest` is `ir.codec.absent_contract_digest`,
the SHA-256 of a NUL, `no contract at ` and that repository path, so no contract digest equals it
and a record for one path does not verify the contract moved to another. A baseline the revision
still holds is compared as before; one it lacks too is not, so a baseline that arrives with its
contract adds no finding (AD-104). An `--against` revision Git cannot resolve, or a contract or
baseline there that is not a regular file or does not parse, is `against.invalid`, exit 2. A
missing or non-regular blob's message names its repository path, including a `--root` below the
top level, such as `mobile/architecture-contract.json`; a parse error names no path. When a run
fails and the observed
`calls_unresolved` budget value differs from an accepted one, `--against` also observes the code
at that revision, under that revision's own contract, and reports `unresolved_call_changes`; a
passing run pays for no second scan. Removed rows and rows in files the revision's snapshot
holds are always kept. An added row in a file the snapshot lacks is dropped when the file is
outside Git's view of the working tree under the scan roots (`git ls-files --cached --others
--exclude-standard`: ignored, or inside a submodule). Revision snapshots preserve tracked
source blobs even when archive attributes would omit them (AD-147).
`unresolved_call_note` says when rows were dropped, when nothing differs from the revision (the
accepted value does not match its code), and when nothing could be compared: a revision that
cannot be scanned, a Git listing with a non-UTF-8 file name, or call records that do not add up
(AD-100). `validate` without `--against` is unchanged. The
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

## Focused agent reports

`archkeel report --only architecture --json` returns the shared Core projection:

- `architecture_projection.components`: ownership, responsibilities, public API, required
  permissions and observed use. Use each component's `id` or `scope` with `--component`.
- The projection's `permission_rules` and `policy_context`: governing rules and peer boundaries.
  Permission is conditional; observed imports do not establish permission.
- `filtered_violations`: finding ids and source locations. The shared remedy is
  `architecture_projection.violation_remedy`. Global verdicts, coverage and UNKNOWN reasons
  remain visible when a component is selected.

When a live report uses `--baseline`, the focused JSON keeps `baseline_path` and
`baseline_comparisons`, including known, new and resolved fingerprint counts. These
comparisons remain global when findings are filtered.

The [command schema](../schema/architecture-command.schema.json) defines abbreviated
selectors, reason indices and grouped UNKNOWN counts. The HTML fact sheets use the same
Core projection.

After one scan, query the saved packet without collecting source again:

```bash
archkeel report --input test-artifacts/architecture/architecture.json --only architecture --json
archkeel report --input test-artifacts/architecture/architecture.json --only violations --json
```

Add `--component` to focus on an exact native id or scope. `--rule` further narrows
violations as an intersection. Unknown or ambiguous selectors exit 2 with a diagnostic.
Saved queries read recorded evidence; they do not verify current files or write artifacts.
`--input` cannot be combined with `--root`, `--config`, `--baseline` or `--output`.

## Narrowing a report

`report --only violations` shows only the declared-rule violations table, hiding component
flow, component communication, review claims and size and coupling, so a large repository's
page stays a small review surface; `--rule <id>` and `--component <label>` each narrow that
table further and combine as an intersection. `--component` matches a violation whose crossing
touches it on either side, source or target, since an import violation crosses two components
(AD-60). All three read the same on `--json`: `report_filter` names the flags that produced the
run and `filtered_violations` carries the selected records with `locations: [{path, line}]`
from the same recorded evidence as the HTML handoff (AD-157). Line `0` means file-only evidence;
`[]` means no source evidence is attached to that violation. Locations name the analyzed snapshot.
Both fields read `null` on an unfiltered run. Under `--only violations`, `rule_assessments`
keeps FAIL and UNKNOWN rows; PASS and DECLARATION rows are omitted. Rule/component facets alone
retain every assessment.
None of the three changes what was judged: `architecture.json`, `declared_rules`,
`violations_by_rule`, `violations_by_component_pair`, the `violations` measurement and the exit
code all keep reading every violation, filtered or not. A filtered result still announces
itself: the HTML decision banner carries `data-report-filter="true"` and a `Filtered (...): N of
TOTAL violation(s) shown.` sentence, and the terminal prints the same sentence in its own panel.
`--rule` matches a fingerprint's rule id exactly, top-level or the `<component>:<rule id>` an
inside declares (AD-36). With `--only violations`, `--component` also accepts native ids
and nested scopes, selecting findings associated with their authenticated Core subjects.
Top-level labels retain source-or-target crossing behavior (AD-34, AD-54). Component
facets without `--only violations` and call filters retain their existing top-level scope.
An unknown rule/component or an ambiguous native selector is `filter_unknown`, exit 2;
a declared scope with no selected findings is valid and empty.

`report --only calls` lists every unresolved and partially resolved call instead: `--json`
carries them as `filtered_calls`, one row each with `status`, `caller`, `path`, `line`,
`expression`, `reason` and owning `component` (`null` when no component or several own the
calling module), sorted by path, line, caller and expression. The rows come from the
observation's own call records and add up to `coverage.calls_unresolved` plus
`calls_partially_resolved`. `--component` keeps the calls its modules make; `--rule` is exit 2,
since a call cites no rule. The HTML page shows the same rows as one table in place of the
violations table and hides what `--only violations` hides; the terminal prints only the
`Filtered (only calls): N unresolved or partially resolved call(s) listed.` sentence. Without
`--only calls` the field reads `null`, like `filtered_violations` (AD-100). The Dart profile
measures no calls (AD-97), so `--only calls` on a Dart scan is exit 2
`rule_unsupported_by_profile` rather than an empty list, and `check` leaves
`unresolved_call_changes` `null` there.

Findings include links and copyable evidence with all cited excerpts, the analyzed commit,
source digest and contract binding. Links reveal collapsed records and reset local filters.
Without JavaScript, expand the evidence and copy the text manually. Source locations refer
to the analyzed snapshot, including its dirty-state digest, rather than the latest remote file.

An unfiltered HTML page with violations also has a local `Violations only` control (AD-75). It
keeps the verdicts, failures, known unknowns, violations and complete evidence access visible
while hiding secondary report detail. The Component flow control narrows only graph edges at the
current level; a symbol or construct violation can therefore leave that graph empty while the
violation table remains non-empty. These controls change the open page only. They never change
the command result or `architecture.json`, and without JavaScript the full report stays visible.

## Reading a report's violations

`archkeel.api` is the declared external contract (AD-64): the one supported way to read
`architecture.json` outside this repository, for a CI gate that wants named fields rather than
the columnar, string-interned file on disk. Its whole promise is declared in
`architecture-contract.json`'s `declarations.public_api` (AD-66). The documented names stay
machine-readable:

<!-- archkeel-public-api -->
```json
[
  "archkeel.api:ViolationFingerprint",
  "archkeel.api:ViolationRow",
  "archkeel.api:load_violations"
]
```

They are mirrored by `__all__` and checked against a scanned module the same way a missing
`public` entry is (`api_surface.missing`). `load_violations(path)` reads the file and returns one typed `ViolationRow` per violation.
For each promised name, validation requires the scanned module and, when present and non-empty,
membership in its literal `__all__`; an empty `__all__` is not inspected. Without an inspected
export list, a name with no scanned top-level class or function is `UNKNOWN`, not a pass. For an
unambiguous class or function, every type the shared annotation walk can resolve in its parameters,
return or public fields must also be named in `public_api`. Fields include a proven local base
chain, preserving overrides and bare named generic substitutions (AD-131). Private fields,
implementation methods and known framework bases are excluded. Unresolved or ambiguous
inheritance, multiple-base precedence and unsupported substitutions retain `api_surface_limit`
UNKNOWN with source evidence. Builtins and external types are not package promises.
The facade reads files and delegates decoding/derivation to `ir`; `ir` performs no I/O
(AD-17, AD-64). A row carries `fingerprint`, `source_module`, `target_module`, `symbol`,
`source_component`, `target_component` and `evidence_ids` instead of a positional record. A field a violation kind
does not carry, such as a forbidden construct's `source_module`, is `None`, never a guessed
value.

```python
from pathlib import Path

from archkeel.api import load_violations

rows = [
    (row.fingerprint, row.source_component, row.target_component)
    for row in load_violations(Path("architecture.json"))
]
```

`row.fingerprint` is AD-52's `(rules, subjects)` pair, the stable key that survives an edit
that moves the violating line without changing what the violation is; a stored baseline or a
CI gate keys on it, not on the record `id` in `architecture.json`, which moves with the line.
`archkeel.api` is the supported external surface. Columnar encoding and `ir`
internals are private. The former `archkeel.ir.codec.load_observation` entry is
removed; use `load_violations`. `ViolationFingerprint` is public because rows expose
it (AD-64, AD-70).

## Regression checks

Regression checks add these scalars to the existing record counts and fingerprint checks:

| Guardrail | Scalar in the Python decoded-IR profile |
| --- | --- |
| No new violations | Violation records |
| No new cycles | Internal SCC edges, summed across observed levels |
| No new private crossings | Confirmed private cross-package imports |
| No new typing signals | Missing boundary annotation positions; other signals count once |
| No new unknowns | Unresolved calls; unknown record counts and fingerprints remain checked |
| No new undecided positions | `unknown_positions`: what the scan left undecided (AD-92) |
| Coverage must pass | Scan failure records; any incomplete scan is unverifiable |

The delta keeps raw counts and fractions. Every measured ceiling must hold independently;
conflicting count/share directions reject (AD-136). This is a conservative change limit,
not an architecture score. Coverage must be complete; schema, scope, analyzer and contract
must match. Existing UNKNOWNs remain UNKNOWN on a passing revision check.

Delta 1.4 coverage PASS covers every dimension the active profile measures.
Dart and TypeScript leave API, private and typing comparisons UNKNOWN with null counts.
Those dimensions cannot be selected in an expectation. Missing supported evidence still
refuses the comparison. Delta 1.3 remains readable; limited profiles must be reobserved
before using scoped comparison.
Equal empty or unknown analyzer/contract identities cannot establish coverage.
Selecting a changed source UNKNOWN cannot waive its mandatory regression guardrail.
Moving existing UNKNOWN evidence without changing its meaning remains selectable.

The Python measurement profile also carries `untyped_private_accesses`, the count of
`private_attribute_access_limit` UNKNOWN records. Older measurement payloads without that
scalar read as zero. This signal is not a private-crossing proof.

`unknown_positions` counts the `unknowns` records the scan left undecided. Three standing
disclaimers count 0: `dynamic_call_limit` and `context_alias_limit` fire on every run, and
`private_attribute_access_limit` has the scalar above. A record that is also a coverage failure
counts 0, a `boundary_type_limit` counts its undecided positions except `external_type`
(AD-67), and every other kind counts its `data.undecided` integer, or 1 without one. A kind a
new analyzer profile adds therefore counts. Its role in the aggregate verdict is described
under [report results](#results). Older measurement payloads without the scalar read as zero (AD-92).

`calls_total` follows the analyzer's call measurement: null when unavailable, otherwise zero or a positive
integer. Decoding older measurements with total zero and null `calls_unresolved` normalizes
the total to null. Schema 2.0.0 accepts that legacy pair; schema 1.0.0 cannot read fresh null
totals. Total and unresolved count availability must agree; inconsistent pairs are invalid.
Fresh accepted locks use 2.0.0. Lock 1.0.0 and Delta 1.2/1.3 retain integer totals on the wire;
their legacy zero/null pairs still decode. The profile-aware Delta 1.4.0 carries null totals.
Re-emitting a legacy delta retains its zero sentinel and version.
Reports show n/a and call budgets refuse unavailable signals.
With `U = calls_unresolved` and `T = calls_total`,
checks require `U_candidate <= U_accepted` and, when both totals exceed zero,
`U_candidate * T_accepted <= U_accepted * T_candidate`. No rounded percentages are used.
Zero or null total means `resolution: n/a`; measured absolute counts still compare.
A profile's unmeasured call count also leaves its share `n/a`, never PASS.
Missing or inconsistent measurements produce `UNKNOWN`; regressions return failures.

`check` also names the calls behind the count. `unresolved_call_changes` holds one row per
unresolved call whose count differs between the two observations: `change` (`added` or
`removed`), `caller`, `expression`, `reason`, owning `component`, `path`, `lines`, `before` and
`after`. A row is keyed by file, caller and expression, not by line, so moved code is no change;
identical expressions in one caller form one row whose `lines` name them all, and a removed row
names the older revision's lines. The JSON lists every row; the terminal lists at most five under
the failures, and none on a passing run. The field reads `null` in a result that compared no two
revisions' calls. Where a comparison leaves rows unnamed (call records that do not add up, a
revision that cannot be scanned, added calls in files the working tree alone holds, nothing that
differs from the revision), `unresolved_call_note` says why, in the result and under the
terminal's failures; the verdict never changes (AD-100).

The JSON field `ratchets` and Python identifiers such as `compare_ratchets` keep their
existing names for compatibility. Human-readable messages use "regression check".
Historical evidence and reproduction commands retain the names from their pinned commits.

## Fixtures

`make fixtures` reproduces A, B and C from `fixtures/A-dispatch`, `fixtures/B-posthoc` and
`fixtures/C-valid`. `fixtures/F-architecture` is the shop sample behind the demo catalog (AD-11).
It carries two levels: the top contract at its root, and the one `COMP-STORE` names for its inside
at `shop/store/architecture-contract.json` (AD-20).

The catalog also exercises inside rules with a clean and a violating `eval` example.
Deleting the inside contract leaves the known root violation visible, reports incomplete
evidence and prevents baseline or graph writes (AD-110).

Every ordered component pair in the shop fixture is decided by one `allowed_dependency` or
`forbidden_dependency` rule (AD-15). D-self also checks that all observed modules have declared
components and that analyzer imports stay within the declared IR API.

## Dependencies

Runtime: `packaging` parses PEP 440 `requires-python` ranges; stdlib has no equivalent.
`rich` renders the terminal view in `archkeel.render.terminal`, and `rich-argparse` formats
`--help` in `archkeel.cli`. `external_dependency_scope` rules in the contract confine all three
imports to exactly those modules through `exact_sources`, so no submodule of `archkeel.cli`
inherits `rich-argparse` (AD-49); JSON results never depend on them.
Build: Hatchling packages the root schemas; `hatch-vcs` derives versions from Git tags.
`hatch-fancy-pypi-readme` resolves README asset and documentation links in distribution metadata.
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

README asset paths and documentation links stay relative in source; PyPI metadata uses
absolute URLs. The build does not rewrite the source README.
