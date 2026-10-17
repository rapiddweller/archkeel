# Archkeel reference

Use `archkeel <command> --help` for exact options. [Onboarding](onboarding.md)
sets up policy; [target-first](target-first.md) maintains it.

<a id="compatibility-in-1x"></a>

## Compatibility

The documented CLI commands, options, exit-code meanings, configuration and
`archkeel.api` exports are the stable interface. Removing or incompatibly changing
them requires a new package major version. Internal Python modules, terminal text
and HTML structure are not integration interfaces.

Evidence and command JSON have their own schema versions. Incompatible changes to
the documented JSON formats or collector protocol also require a new package major
version. Adding a field that an existing supported decoder rejects is also incompatible;
collector validation remains strict. Pin CLI, collectors and schemas together for
reproducible integrations.
Schema readability does not guarantee comparable observations: analyzer corrections
and profile changes can require re-observing both revisions. Correctness fixes may
change findings without changing an interface.

The Dart collector migration in 1.1.0 is an explicit exception: legacy
`archkeel-dart-directives` evidence is no longer accepted, and the existing schemas
add Dart `mixin` and `mixes_in` enum values. Upgrade strict consumers and re-observe
Dart snapshots; see the [1.1.0 upgrade notes](../RELEASE_NOTES.md#upgrade-from-100).

Stable does not mean complete language analysis. Unsupported or ambiguous evidence
stays UNKNOWN; language limits remain part of the documented result.

Version 3.0.1 introduces command-result schema 8 for confirmed FAIL alongside an
incomplete report. Strict consumers must update their schema; version 6/7 readers
remain supported. See the [3.0.1 upgrade notes](../RELEASE_NOTES.md#upgrade-from-200).

Version 4.0.0 expands the TypeScript profile with optional PARTIAL construct
evidence. The 3.0.1 Core/report reader rejects that receipt, even though SourceFacts
and protocol remain 3.0.0 and ArchitectureIR remains 2.0.0. Upgrade the package,
collectors and strict profile consumers together, then re-observe both comparison
revisions. Current readers retain legacy TypeScript receipts. See the
[4.0.0 upgrade notes](../RELEASE_NOTES.md#upgrade-from-301).

## Configuration

[The schema](../schema/archkeel.schema.json) defines `archkeel.toml`:

```toml
[scan]
roots = ["src"]
namespace = "app"
contract = "architecture-contract.json"
```

One run covers one namespace. Roots are repository-relative, nonoverlapping and
not globs. Optional `language` selects Python (default), Dart or TypeScript.
TypeScript also uses `tsconfig`; roots may be files or directories. Python/Dart
roots are directories. Inputs must exist inside `--root`.

`report` and `validate --config PATH` select a root-relative file. `check` uses
only `archkeel.toml`, bound by its accepted lock. Give separate scopes separate
report outputs. Default report JSON is `test-artifacts/architecture/architecture.json`.

Baseline/amendment paths resolve under `--root`, including writes, and must stay
inside it after symlink resolution. Output paths remain cwd-relative. No cwd
fallback resolves missing inputs.

Collectors run through a process port. Optional `collector_argv` supplies separate
arguments without a shell; on Windows use an executable and script, not a `.cmd`
shim. Every language defaults to its own collector inside this package, so TypeScript
needs no Node runtime. Runtime mismatch, malformed replies and incomplete evidence
cannot certify a scan. Legacy observations remain readable only under supported
schemas; missing required sections fail closed.

Collector stdout defaults to a finite 64 MiB limit. Large valid scopes may set
`collector_output_limit_bytes = 268435456` (256 MiB) in `[scan]`. The value must
be a positive integer; it changes transport capacity, not source scope or protocol
validation. Larger replies also require more memory to decode and assess. Existing
configurations retain the default; stderr and execution time remain bounded.
For a new setup, `archkeel init --collector-output-limit-bytes 268435456` uses that
limit for initialization and saves it in the generated config. `report`, `validate`
and `check` use the configured limit; `check` binds it to the accepted config like
the other scan inputs. See [AD-224](architecture/decisions/ad-224-configurable-collector-output-limit.md).

SourceFacts 3.0.0 adds neutral list type syntax for explicit callback arguments.
Readers retain byte-compatible 1.0.0/2.0.0 packets; those versions reject the new
list vocabulary, including nested shapes. Runtime `requirement_state` remains
required from SourceFacts 2.0.0 onward. ArchitectureIR/Delta stay 2.0.0;
command-result uses 8.0.0. New requests name protocol 3.0.0; pin collectors,
Core and strict schemas together. See [AD-223](architecture/decisions/ad-223-explicit-callable-boundaries.md).


## Results

Read `observation_complete`, `declared_rules` and `expectation_fulfilled` separately.
Rule PASS needs completed scope evaluation and sufficient evidence; permission
rows are DECLARATION. Known violations remain FAIL alongside UNKNOWNs. Report
expectations are n/a. Filtering and baseline display do not change canonical facts.

### Exit codes

| Command | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `check` | Accepted | Rejected | Input/evidence unverifiable |
| `validate` | Validation accepted | Baseline/budget/widening rejected | Validation diagnostics |
| `report` | Observation complete; read verdicts | — | Input/evidence unverifiable |
| `init` | Draft written | — | Draft unavailable |
| `skill install` | Instructions written | — | Target could not be updated |

Exit 0 is not architecture approval. Exit 2 carries diagnostics with `kind`,
`subject`, `unknown_claim` and `remedy`; inspected evidence may remain available.

For components explicitly marked `decided_by: "architect"`, validation emits
`responsibility.missing` when the responsibilities list has no substantive entry.
Empty lists keep their existing diagnostic. Whole-entry `TODO`, `TBD` and
`placeholder` markers also count as absent: matching ignores case and surrounding
whitespace and permits a single trailing colon, such as `TODO:`. No other text is
treated as a marker. A substantive entry, including prose such as "Handle TODO
items" or "Placeholder resolution", keeps the list valid even alongside markers.
This applies to root and mounted contracts; diagnostics name the component and
carry its contract path and `/components/<index>/responsibilities` pointer.
Otherwise valid architect contracts containing only these markers now exit 2
instead of 0. Agent drafts and components without explicit architect attribution
remain accepted; rule verdicts and rationale validation are unchanged.

JSON null means unavailable/inapplicable; an empty list means measured empty.
Pin CLI and [command schema](../schema/command-result-8.0.schema.json) together.
Version 8 retains version 6/7 readers and permits an incomplete report to preserve
a traceable FAIL assessment while coverage stays UNKNOWN/FAIL; it cannot claim PASS.
Ignore unknown result properties; required fields and enum meanings remain strict.
Schema shape validation proves neither authenticity nor conformance.
`report`/`check --output` also write `.report.html`/`.check.html` companions.

`validate --json` includes every open ordered component pair by default. For a smaller
review result, use `validate --compact-open-decisions --json`: it lists observed undecided
crossings, `open_decision_count` reports the exact total, and `open_decisions_complete` is
true only when every open pair is listed. Omitted pairs remain undecided; an empty compact
list does not close a positive total. Both modes keep verdicts, UNKNOWN evidence and
diagnostics unchanged. Summaries are `null` when validation cannot derive them.
`init --json` uses the same summary fields and defaults to observed crossings; `init --full`
retrieves every pair on the initial draft.

`validate --write-graph` updates eligible marked provenance graphs from observed
imports or Target permissions. Exactly one observed marker is required; Target
is optional. Subgraphs, labels and styles require manual editing.

## Focused agent reports

```bash
archkeel report --only architecture --json
archkeel report --input test-artifacts/architecture/architecture.json --only architecture --json
```

The compact Core projection keeps top-level intent and reduces nested components
to identity, parent, responsibility, layer and finding count. Select an exact ID
or scope with `--component` for that component's contract. Global verdicts,
coverage, UNKNOWNs and baseline comparisons remain visible. Compact JSON omits
`filtered_violations`, reports the selected-scope `filtered_violation_count`
(`null` when unavailable), and sets `violation_details_included` to `false`.

```bash
archkeel report --input architecture.json --only architecture --full --json
```

`--full` restores `permission_rules`, `policy_context` and complete violation records;
it also works with live reports and `--component`. Full JSON includes the selected
`filtered_violations` array, including `[]` when the measured count is zero, and sets
`violation_details_included` to `true`; unavailable rows remain `null` with a null count
and `false`. `--only violations` queries full finding rows directly. Assignment findings
name candidate `owners` (or `none`) and `remedy`. Observed imports never establish permission.

Full JSON also includes `recorded_unknowns`: complete original UNKNOWN records,
including IDs, references and nested data. This inventory stays global with
`--component`; grouped projection uncertainty remains separate. `[]` means
inspected empty, `null` means unavailable. Full output uses schema 2.0.0;
compact stays 1.0.0 without this field. The published legacy schemas stay unchanged.

Saved queries read recorded evidence without rescanning, verifying current files
or writing artifacts. `--input` cannot combine with `--root`, `--config`,
`--baseline` or `--output`. Unknown/ambiguous selectors exit 2.
See the [full schema](../schema/architecture-command-2.0.schema.json) and
[legacy schema](../schema/architecture-command.schema.json).

## Narrowing a report

`--only violations` shows findings; `--rule ID` and `--component LABEL` intersect.
Inside rule IDs retain their scoped prefix. Violation-only component filters also
accept authenticated nested IDs/scopes; ordinary facets retain top-level behavior.
A valid empty selection succeeds. Rule assessments follow the selected scope;
`--only violations` keeps FAIL and UNKNOWN assessments. Filters preserve global
verdicts, totals and canonical bytes; locations refer to the analyzed snapshot,
not current remote files.

`--only calls` lists unresolved/partially resolved calls. Component filtering keeps
calls made by that component; `--rule` is refused. Unmeasured call profiles exit 2
rather than returning a misleading empty list. Browser focus changes only the view.
An empty graph can still have non-edge violations.

## Baselines and widening

`validate --baseline FILE` requires exact violation/budget debt. New and resolved
debt exit 1. Initial or resolved-only writes use `--write-baseline`; increased debt
needs explicit `--accept-new`. Exit 2 writes nothing. `report --baseline FILE` is
read-only and never discovers a baseline automatically. Resolved debt needs proof
that its old subjects were still evaluated, not merely removed from policy.

`--against REF` compares contracts and optional baselines. Widening fails unless
`--amendment FILE` binds the exact policy pair. Approved changes can write that
file using `--write-amendment --decided-by NAME --rationale REASON`. Introduced or
moved contracts require approval. Unreadable history exits 2. See
[baseline](../schema/violation-baseline.schema.json) and
[amendment](../schema/contract-amendment.schema.json) formats.

## Reading a report's violations

The supported external API is:

<!-- archkeel-public-api -->
```json
[
  "archkeel.api:ViolationFingerprint",
  "archkeel.api:ViolationRow",
  "archkeel.api:load_violations"
]
```

`load_violations` returns typed rows. Missing kind-specific fields are None.
Fingerprints use rules/subjects, surviving line moves; evidence IDs remain separate.
Columnar encoding and `ir` internals are private. The former codec load path is
removed; use:

```python
from pathlib import Path

from archkeel.api import load_violations

rows = [
    (row.fingerprint, row.source_component, row.target_component)
    for row in load_violations(Path("architecture.json"))
]
```

## Regression checks

Measured counts and shares must each hold; a better percentage cannot hide a worse
count. Coverage, schema, scope, producer/runtime, checker and contract identities
must be comparable. Python needs the same known full runtime version.
Unavailable measurements remain null/n/a and cannot satisfy
budgets. Legacy zero/null call sentinels remain readable as unmeasured.
Existing UNKNOWN stays UNKNOWN on a passing revision check.

Empty `selected_changes` declares no semantic change. Nonempty selections cannot
waive regression guardrails; added dependencies must be declared. See
[expectation tests](../tests/test_expectation.py) and
[regression implementation](../src/archkeel/check/ratchets.py).

## Git predicate

The protocol is M → B → E → H: accepted source, lock-only commit, expectation-only
commit, candidate. Fetched refs, ancestry and unchanged bound inputs are required.
E must be published before H submission; commit dates prove no host ordering.
Trusted host receipts are required. Local/synthetic replays do not prove authenticity;
GitHub event history alone cannot prove first publication. [Protocol tests](../tests/test_git_lock.py)
and [host evidence boundaries](architecture/archkeel.md#host-evidence) define supported evidence.

Plugins reuse the CLI skill. See [plugin instructions](../plugins/archkeel/README.md)
for installation; listing and publication remain separate acceptance steps.
