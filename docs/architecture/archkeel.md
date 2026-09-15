# Archkeel architecture

[The contract](../../architecture-contract.json) owns component boundaries. Within-component
imports remain allowed. Every cross-component pair is either observed or forbidden.

## Layers

| Layer | Components | Responsibility |
|---|---|---|
| Core | `ir`, `check` | Stable evidence values and deterministic policy evaluation |
| Adapters | `analyzer`, `host` | Python source observations and GitLab host records |
| Edge | `cli`, `render`, `accept` | Composition, presentation and accepted-state entry points |

The CLI is the composition root. It selects concrete analyzer and host adapters, invokes the
core, writes artifacts and delegates HTML and terminal projection to `render`. Core modules
never select adapters or write presentation files.

Third-party imports are confined by `external_dependency_scope` rules: `packaging` to the
analyzer runtime gate, `rich` to `archkeel.render.terminal` and `rich_argparse` to `archkeel.cli`.

The analyzer may import only `archkeel.ir.model` and `archkeel.ir.codec`. This keeps raw AST
records inside the analyzer and exposes typed `ObservationResult` values at its boundary.

## Decisions

Each decision names its reason and the check that holds it. Code follows the decision; a change
to a decision is recorded here before the code changes.

**AD-1 Analyzer modules are flat and single-purpose.** `archkeel/analyzer/embedded/` holds only
top-level modules, one responsibility each:

| Module | Responsibility |
|---|---|
| `scanner` | Discover and parse sources, run the collectors, return `ScanResult` |
| `source` | Parsed modules, module names, evidence locations |
| `imports` | Import bindings and `__all__` exports |
| `symbols` | Classes, functions and their signatures |
| `calls` | Call sites and their resolution |
| `typing_signals` | Weak typing signals such as `Any`, `object` and `type: ignore` |
| `constructs` | Statement constructs: assert statements and broad except handlers |
| `dependencies` | Package and module topology, dependency edges, cycles, declared paths and component scopes |
| `contexts` | Context and state evidence |
| `violations` | Contract rule evaluation |
| `graph` | Graph algorithms: components, ranks, transitive paths |
| `records` | Record envelope, stable ids, analyzer version and digest |
| `contract` | Contract loading and declarations |
| `report` | Observation assembly |

Reason: `analyzer_code_digest` hashes top-level `*.py` files, so code in a subpackage would
change analyzer behavior without changing the digest. Check: `tests/test_analyzer.py`.

**AD-2 JSON has one type.** Decoded or emitted JSON is `RawJson`; untrusted input is narrowed with
`isinstance` at the boundary. Analyzer records are `RawRecord` and `RawEvidence`; their per-kind
payload is `RecordData`, the analyzer's single declared `Any`. The other `Any` positions are the
named `CoveragePayload` and the places where those records enter canonical encoding, each with a
one-line reason. Check: `mypy --strict` and the typing measurements in `fixtures/D-self/`.

**AD-3 The analyzer digest decides comparability; the version names it.** Two observations are
comparable only with equal `analyzer.code_digest`. `ANALYZER_VERSION` is the human label: its minor
number rises when the same input yields different records, such as new rule kinds or signals.
Check: `check/delta.py` compares digests; the version is reviewed with the D-self fixture.

**AD-4 Module length alone does not justify a split.** A split needs a responsibility seam. The
analyzer's public IR API is exactly `ir.model` and `ir.codec`, so splitting either is a contract
change. Check: `tests/test_self.py`.

**AD-5 Invariants live where values are built.** A value whose fields depend on each other
checks that dependency in `__post_init__`, for example `ObservationResult` (no diagnostics means
a complete observation) and `RatchetObservations` (measurements exist exactly when the status
is `SUPPORTED`). Consumers narrow with ordinary control flow. Reason: `assert` disappears
under `python -O` and hides the invariant from its owner. Check: the `CONSTRUCT-NO-ASSERT`
rule in `architecture-contract.json`.

**AD-6 A function has one responsibility.** A function longer than 80 lines, counted from `def`
to its last line with nested functions included, needs a named reason. Reasons live in
`ALLOWED_LONG_FUNCTIONS` in `tests/test_repository_hygiene.py`, keyed `path::qualified.name`. A
helper with one caller must name a real phase; splitting for length alone is not allowed.
Reason: 80 lines is what a reviewer can hold at once, and an explicit list keeps declarative
functions visible instead of exempting them silently. Check: the test fails on an unlisted long
function and on a listed function that is no longer long, so the list only shrinks.

**AD-7 Determinism is measured, not assumed.** The inputs of one observation are source bytes at a
commit, contract bytes, the installed Archkeel (analyzer and checker digests), `archkeel.toml`,
the Python version and the repository directory name. Everything else is environment, and the
emitted bytes must not depend on it. Three `report` runs on two clones with different parent
paths, working directories, `PYTHONHASHSEED`, `TZ` and `LC_ALL`, plus one verbatim repeat, must
produce byte-identical `architecture.json`, HTML report and stdout JSON without normalization. A
field that would need normalization is a violation of this decision, not a probe adjustment.
Reason: determinism is Archkeel's core promise, so it needs evidence like any other claim. Limit:
equal bytes on one machine and Python build do not prove equality across Python versions,
operating systems or inputs the probe does not vary. Check: `tests/test_determinism.py`, proven
by an unsorted record subject list and an absolute source path, each of which fails it.

**AD-8 Statement constructs are Class A rules.** `forbidden_construct` gains the constructs
`assert` and `broad_except` and an optional `allowed_sources` list with prefix scope, as in
`external_dependency_scope`. A broad handler is a bare `except:` or one that catches `Exception` or
`BaseException`, alone, in a tuple or as `builtins.Exception`; `except Exception: raise` counts,
because re-raising is intent and belongs to review, while a justified boundary is named in
`allowed_sources`. Aliases and shadowed names are blind spots. The records live in their own
`constructs` section, not in `typing_signals`, because every typing signal counts as a typing
position in the regression checks. Contract `schema_version` stays 2.0.0: a wider enum and an
optional key make no valid contract invalid, and older Archkeel versions fail closed with exit 2.
Reason: both constructs are facts of one observation, so a person should not have to judge them.
Check: one violation probe per construct in `tests/test_analyzer.py`, and Archkeel's own contract
forbids both with the CLI error boundary as the single allowed broad handler.

## Allowed dependencies

| Edge | Reason |
|---|---|
| `cli` → `accept` | Dispatch the acceptance command from the composition root. |
| `cli` → `analyzer` | Supply the concrete source analyzer to report and check workflows. |
| `cli` → `check` | Invoke deterministic report and check services. |
| `cli` → `host` | Supply the concrete host-record loader to checks. |
| `cli` → `render` | Project typed results and write presentation artifacts. |
| `accept` → `ir` | Return typed command results through shared IR values. |
| `analyzer` → `ir` | Publish observations through the common model and codec boundary. |
| `check` → `ir` | Compare observations and return typed results. |
| `host` → `ir` | Construct validated host-record values. |
| `render` → `ir` | Render typed evidence without importing policy implementations. |

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    cli --> accept
    cli --> analyzer
    cli --> check
    cli --> host
    cli --> render
    accept --> ir
    analyzer --> ir
    check --> ir
    host --> ir
    render --> ir
```
