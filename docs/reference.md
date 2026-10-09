# Archkeel reference

Use `archkeel <command> --help` for exact options. [Onboarding](onboarding.md)
sets up policy; [target-first](target-first.md) maintains it.

## Compatibility in 1.x

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

SourceFacts 2.0.0 and ArchitectureIR 2.0.0 persist `runtime.requirement_state`; Core
observation 0.74.0 emits it. Delta 2.0.0 and command-result 6.0.0 carry the new runtime
shape. New readers accept SourceFacts 1.0.0 and supported legacy observations/deltas
without this field. Old strict consumers require an upgrade; pin collectors, CLI and
schemas together. A new Core request names protocol 2.0.0; collectors must support it.

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
JSON null means unavailable/inapplicable; an empty list means measured empty.
Pin CLI and [command schema](../schema/command-result.schema.json) together.
Ignore unknown result properties; required fields and enum meanings remain strict.
Schema shape validation proves neither authenticity nor conformance.
`report`/`check --output` also write `.report.html`/`.check.html` companions.

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

Saved queries read recorded evidence without rescanning, verifying current files
or writing artifacts. `--input` cannot combine with `--root`, `--config`,
`--baseline` or `--output`. Unknown/ambiguous selectors exit 2.
See the [projection schema](../schema/architecture-command.schema.json).

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
