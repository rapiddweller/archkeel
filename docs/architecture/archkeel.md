# Archkeel architecture

[The contract](../../architecture-contract.json) owns component boundaries. Within-component
imports remain allowed. Every cross-component pair is either observed or forbidden.

## Layers

| Layer | Components | Responsibility | Quality goal (AD-17) |
|---|---|---|---|
| Core | `ir`, `check` | Stable evidence values and deterministic policy evaluation | Deterministic and stable |
| Adapters | `analyzer`, `host` | Python source observations and GitLab host records | `analyzer` isolated behind its digest; `host` replaceable |
| Edge | `cli`, `render` | Composition and presentation | `cli` a thin composition root; `render` replaceable |

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
| `receiver_types` | Hand-written stdlib method tables and static receiver-type detection (AD-37) |
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

**AD-9 Components declare their interface.** A component lists its interface in `public`: an
entry `pkg.module` makes every non-underscore top-level name of that module public, or its
`__all__` when present, and `pkg.module:Name` makes exactly one name public. The Class A rule
`interface_boundary` accepts a cross-component import only when it reaches a declared name of the
target component, directly or through its re-export chain; underscore names never qualify, and
`TYPE_CHECKING` imports count unless `include_type_checking` is false. When an
`interface_boundary` rule exists, validation reports a component with inbound imports but no
`public`, and a `public` entry that no other component uses.
`init` proposes a module entry when the module defines `__all__` or other components use at least
half of its public names, and symbol entries otherwise, so a module entry admits at most twice the
names in use. `declarations.public_api` stays valid but is superseded. The report derives a
communication table per component edge: the used names with their parameter and return
annotations, and `UNKNOWN` where an annotation is missing. Protocol conformance, labeled graphs
and new regression measures are out of scope. Reason: Archkeel already checks which components
talk; the interface states through what, so reaching into another component's internals requires
a visible contract change. Check: violation probes in `tests/test_analyzer.py`, drift tests in
`tests/test_validation.py`, Archkeel's own contract, and the measured profile in `docs/evidence/`.

**AD-11 Every checkable item has a catalogued demo.** `fixtures/F-architecture/` is a committed
five-component sample repository with a closed contract, `public` interfaces, a marked Mermaid
graph and every Class A rule kind declared; `validate` and `report` on it are clean. One catalog
in `fixtures/architecture_demo.py` lists named variants, each a mapping of repository-relative
files to new content applied over a copy of the clean tree, together with the exact violations and
diagnostic codes it must produce. The catalog opens with a showcase section: its `tour` variant
makes every Class A rule kind fire in one run and is the default demo view. Variants live in flat
modules grouped by rule family. Regression checks and the check protocol get demos of their own,
in which `check` compares the clean sample as accepted baseline with a violating candidate. A check
demo asserts typed results only: exit code, verdicts, and the measurement or delta dimension that
regressed; it never matches the prose in `failures`. Items that cannot be demonstrated, such as
`coverage_failures`, are marked as tested only, and the generated table in
`docs/architecture-demo.md` names each row's demo type and is compared with the catalog. Reason: a user must be able to see
each rule fire on one readable repository, not only in unit tests. Check:
`tests/test_architecture_demo.py` enumerates rule kinds, construct values, diagnostic codes and
regression measurements from code, and fails when one has no catalog entry, when a variant's
findings differ from the catalog, or when the clean sample reports anything.

**AD-12 Validation diagnostics carry a code.** Every `contract_invalid` diagnostic has a stable
`code` from one `DiagnosticCode` literal, such as `decision.open`, `interface.unused` or
`rule.violated`; the constructor rejects a `contract_invalid` diagnostic without one, and result
JSON emits the code next to the pointer. Diagnostics the analyzer reports before validation, such
as `rule_without_subjects`, keep their kind without a code, and a code no path can produce is
removed. Reason: sixteen different findings shared one kind and
differed only in prose, so tests and agents had to match free text. Check: the constructor, and
the catalog test in AD-11 compares codes instead of messages.

**AD-13 Mermaid diagrams are checked before GitHub renders them.** One tool extracts every fenced
Mermaid block in tracked Markdown; a repository test rejects node labels with unquoted characters
that break the parser, and CI renders every block with the official Mermaid command-line renderer
at one pinned version. Reason: GitHub showed a parse error instead of the onboarding flow, and no
local check noticed. Check: `tests/test_mermaid.py` and the CI render step.

**AD-14 The report headline follows its verdicts, never the exit code alone.** `report` exits 0
whenever its observation is complete, so the exit code cannot say whether rules hold. The terminal
and HTML headline come from one summary: NOT CHECKED on exit 2, FAIL when `declared_rules` is
FAIL, otherwise PASS; `check`, `validate` and `init` keep their headlines, and no exit code or
result field changes. Reason: the shop tour with 11 violations opened with a green PASS above a
failing rules verdict. Check: the render tests for report, check and init headlines.

**AD-10 The report draws component flow as intent against observation.** The HTML report of
`report` embeds an interactive flow view: component cards, observed edges drawn at one width and
labelled with the import sites crossing them, edges that break a rule drawn dashed with the rule
id, a threshold that hides weak edges, and an inspector for modules and interface names. It is
derived from the canonical observation alone, so the report stays one self-contained file; the
script is a packaged asset with no external library, and its data, ordering and output bytes are
deterministic. The existing communication table stays as
the fallback without script. Reason: on the internal service the graph showed the seven edges that
break its documented intent faster than any table, and a prototype on the shop sample did the same
for every rule kind. Width encoded the weight until two costs showed: an arrow head scales with the
line it ends, so a heavy edge grew a head that read as weight where it should read as direction,
and inside a component, where every edge is observed and the label spots are crowded, the number
that would have said so was the first thing dropped. Check: the HTML report tests,
`tests/test_determinism.py`, and the shop tour report drawing every violated edge; the one width
and the label on every edge are drawn by `flow.js` at runtime and measured on the self report, not
asserted by a test.

**AD-15 Onboarding is a decision interview: the code proposes, the architect decides.** Observed
code yields facts and questions, never intent. `init` proposes components and `public` interfaces
and returns a deterministic list of open decisions ordered by import sites; it writes no dependency
rule. Every ordered component pair must be decided exactly once in the contract: an
`allowed_dependency` rule or a `forbidden_dependency` rule, each with the architect's rationale.
One function in `ir` derives the undecided pairs from the observation alone, from the projected
dependency decisions and the observed component edges, so validation and the report, including a
report rendered later from `architecture.json`, share one derivation; `decision.open` replaces
`closed_world.missing` and names whether the pair is observed and at how many import sites. Each open
decision in the `init --json` and `validate --json` output carries the exact rule for every option,
so the id scheme has one owner and only the architect's reason is written by hand. The report draws
undecided observed edges as their own edge state from the same derivation. The skill makes the agent
an interviewer: it asks the architect multiple-choice questions with a custom answer, heaviest edges
first, offers a single decision for all unobserved pairs of a component, marks anything read from
documentation as a hypothesis with its source, and never answers itself. Contract 2.1.0 adds the rule
kind and replaces 2.0.0 without a decode path, because breaking changes are allowed before 1.0. Reason: `init`
wrote the complement of the observed graph, so the first report passed by construction, while rules
taken from the internal service's own architecture document made 7 observed edges fail at 200 import
sites. Check: `init` drafts no dependency rule, every undecided pair yields `decision.open`, a
forbidden observed edge is a violation on the first report, and Archkeel's own contract and the shop
sample decide every pair.

**AD-16 Onboarding defines a target architecture in two agent modes, and every decision records who
made it.** The contract is the target: its components, interfaces and decided dependencies state
where the system should be, and the report measures the code's distance from it as violations; it
never describes the code as it is. The architect owns that target; the agent supports the architect
with best practice, evidence from the repository and the stated quality goals, such as which
components must scale, which must stay easy to change and where performance matters, and asks the
architect for a goal whenever it is unknown and would change a recommendation. Quality goals live in
the recommendation and in the rule's rationale; the contract gains no field for them until a rule
evaluates one. The CLI stays deterministic and never decides a dependency. The packaged skill runs
onboarding in one of two modes. In interview mode the agent first reads the repository's ADRs and
architecture documents, proposes the overall picture (components, layers and allowed directions)
with its evidence, and asks the architect to confirm it once; afterwards it asks only where code and
documents disagree or the documents are silent, each question with a recommended option and its
source (`path:line`). When the architect chooses against the recommendation, the agent asks why
before writing the rule, always when the choice contradicts a document, an earlier decision or
observed code, and records that answer as the rationale. In auto mode the agent decides every open
decision itself, in this order of evidence: documents, then the layer principles the architect
confirmed or the documents state, and never "observed means allowed". Every rule carries
`decided_by`, `architect` or `agent`, so validation and the report count agent decisions that still
await the architect, and a later interview asks only those. The architect chooses the depth: auto
mode for a first target, interview mode for the conflicts they care about, and a later interview on
agent decisions. Reason: the architect is accountable for the architecture, and a recommendation
without the quality goals behind it cannot be judged; the first interview on the internal service
asked 20 rounds of unranked questions about 156 pairs and overwhelmed the architect, while an
agent-only draft without a marker made 122 agent rationales indistinguishable from intent. Check:
the contract schema requires `decided_by`, the report shows the number of agent decisions, the skill
asks why on every deviation from a recommendation, and an auto-mode run on the internal service is
compared pair by pair with the architect's 156 interview decisions.

**AD-17 Archkeel's own target names its quality goals, and `ir` holds pure derivations.** The
architect confirmed these goals for Archkeel: `ir` and `check` are deterministic and stable,
`analyzer` is isolated and changes independently behind its digest, `render` and `host` are
replaceable, and `cli` stays a thin composition root. The goals are written into each component's
responsibilities and into the reasons of the allowed dependencies. `ir` holds the shared evidence
model, its codecs and the pure derivations over them that more than one component needs, such as
interface edges and open decisions; a derivation in `ir` performs no I/O and imports nothing outside
`ir`. The placeholder `accept` command and component are removed until acceptance is implemented,
which leaves six components and 30 ordered pairs. `ir/codec.py` splits along its contract,
observation, delta, result and lock seams after 0.3.0, as its own decision, because the split
changes the analyzer's public IR. Reason: the self-observation at `7b2502a` showed a component whose
only command always exits 2 but carries 12 pair decisions, derivations in `ir` that its stated
responsibility did not cover, and a 1,278-line codec with five responsibilities. Check: the contract
has no `accept` component, every component responsibility names its quality goal, `validate` and
`report` on Archkeel stay clean, and D-self records six components.

**AD-18 A forbidden dependency supersedes the interface boundary on the same import.** An import
that already violates a `forbidden_dependency` rule is reported once, as that violation;
`interface_boundary` evaluates only imports that no forbidden rule rejects, because a forbidden edge
has no legitimate interface to reach. The `violations` measurement therefore counts each rejected
import once, and the analyzer version rises because the same input yields fewer records. Reason: on
the internal service most of the 149 interface violations were the same imports as the 148 forbidden
use-case-to-persistence imports, so the first report counted them twice and inflated its headline.
Check: a probe whose import breaks both rules yields exactly one violation, the forbidden
dependency; an import on an allowed pair that misses the declared interface still violates
`interface_boundary`; and the internal service evidence reports each import once.

**AD-19 Words for people are plain; identifiers for machines stay stable.** The verdict word on
exit 2 is `NOT CHECKED`, not `UNVERIFIABLE`, and its sentence says that nothing was checked and
what is missing. Each unknown verdict names the step that could not run. `decision.open` states in
one sentence how many import sites use the pair and that no rule decides it. Exit codes, verdict
values, diagnostic codes and every JSON key stay as they are, so scripts, the skill and the schema
do not move. Reason: on a first run the tool's opening sentences were "Required evidence is missing
or invalid; no pass decision was made" and "The component pair is not observed at 0 import site(s)
and is undecided", which a reader takes as a judgment about the code instead of a missing
precondition. Check: the render and validation tests assert the new sentences, while the result and
contract tests keep asserting the unchanged keys and codes. Two wording findings stay open and are
tracked in the roadmap: every validation panel is titled `contract_invalid` although its code is
specific, and the HTML report labels sections with internal vocabulary such as `ArchitectureIR`.

**AD-20 A level is its own contract, never a nesting inside one contract.** Depth is unlimited and
always optional: a component's inside is described by its own `archkeel.toml` with its own scan
scope and its own contract, and the component model gains no parent or child field. Levels are tied
together by four things only: a contract field that names the contract describing a component's
inside, one measured number reported upward for that component, two checks, namely that both
levels declare the same `public` interface for it and that nothing inside imports what the level
above forbids, and the record of a declared inside in the observation, so the report can draw the
inside without opening a second contract while rendering (AD-34). `init` never opens a second level by itself. Reason: a second level on `check` drafted
12 sub-components and asked for 132 decisions, four times the 30 pairs of the whole top level,
because closed-world coverage applies per level; nesting inside one contract would multiply that set
and would need a precedence rule between levels. The mechanics already work without a model change:
the same commands run on a scope of `src/archkeel/check`, where sibling components appear as external
packages. Check: the shop sample declares an inside for `store` and passes on both levels;
`inside.public_mismatch` and `inside.forbidden_import` are each catalogued with an overlay that
replaces that contract, a third row deletes it and reads `contract.invalid` at
`/components/1/inside`, and a test holds `init` to drafting no component carrying `inside`.
An `external_dependency_scope` declared inside is not yet compared against the level above.

**AD-21 Structure measurements are derivations, never gates.** `ir` derives, from modules and
module-level edges alone, the module count, inner edges, fan-in, fan-out and unresolved-call share
per component and per package; `report` shows them. No verdict, no rule and no exit code depends on
them, and the same holds for any number a view computes about its own drawing. Reason: the global
unresolved ratio hides a local blind spot. Across 50 self-reports since 0.2.0 the global ratio
improved four times while one component got worse, and the spread at 0.3.0 runs from 8.4% in `ir` to
41.8% in `cli` around a global 19.1%. Making such a number a gate would contradict the roadmap's own
exclusion of a total score and would invite refactoring for the sake of a figure. Check: the derived
numbers sum to the observation's totals, and `ir` stays free of I/O (AD-17).

**AD-22 The analyzer is a process port with a language profile.** The analyzer is chosen by
configuration and may be any executable that writes a canonical observation to stdout; the core
validates it against `schema/architecture-ir-common.schema.json` plus the profile of its language.
Language-specific constructs leave the contract's fixed enum and become capabilities the analyzer
declares, `python_version` becomes a general runtime field, and the Python core stays as it is.
Reason: the boundary already exists as the `Analyzer` protocol and as two schemas, one common and one
named a Python profile; only six places still assume Python, namely the import in the CLI, the
namespace pattern in the configuration, the `public` and dependency patterns in the schema, the
construct enum and the runtime gate. Comparability keeps hanging on the analyzer digest (AD-3), which
is per analyzer and needs no change. Check: a second analyzer produces a valid observation and its
own self-fixture, and contract validation rejects a construct the analyzer does not declare.

**AD-23 The report headline follows open decisions as well.** A `report` whose contract still has
open decisions must not read PASS: the headline names them, the way AD-14 makes it name violated
rules. Reason: on a freshly drafted second level, `report` exited 0 with zero violations and said
nothing about 132 undecided pairs, so a contract that decides nothing looked finished. Check: a
render test for a report whose contract leaves one pair undecided.

**AD-31 Deciding inside a component is opt-in, and only for pairs that exist.** Superseded by
AD-33; the rule kind it introduced never left this repository. AD-24 leaves the
inside of a component undecided by design, which is right until an architect wants to govern it.
`complete_inner_decisions` names one component and demands that every observed module pair inside
it be decided; without the rule nothing changes, so no repository inherits the work by upgrading.
The expected set is the pairs the analyzer observed, never the product of the modules: `analyzer`
holds 21 modules, so the product is 420 pairs and the observation is 46. A pair nobody imports
needs no decision, and demanding 374 of them would bury the 46 that matter. Inside the rule's
component an undecided pair becomes `undecided` rather than `observed` (AD-24b), because there a
decision is owed again. `init` writes neither the opt-in rule nor the pairs it opens: AD-15 holds
here too, and an opt-in the draft hands out is no longer one. The architect adds the rule, and
`validate` then lists the pairs inside that component the same way it lists the pairs between
components, from the same derivation in `ir`.
Check: five of Archkeel's six components hold 90 observed inner pairs between them, no contract
opts in, and `validate` reports no inner decision.

**AD-24b Observed is not undecided.** At component level `undecided` means a decision is owed:
`validate` reports the pair and the report can fail on it (AD-15). Inside a component none is
owed, and validate demands none, so an inner edge that no rule names is `observed` and carries its
own neutral colour. Sharing the warning colour of `undecided` made this repository's 90 inner
edges look like 90 open decisions, of which it has zero. The state is a rendering distinction with
no verdict behind it: a rule scoped below a component still turns its pair into a violation, which
is what makes `sibling_isolation` visible at all. Check: `open_decisions` names no inner pair,
while the tour's peer import stays red.

**AD-24a A module opens the same way, and its interface is what crosses its edge.** The third
level shows the functions and classes one module declares and the calls and references between
them, with methods listed inside the class that owns them rather than as cards of their own. What
counts as the module's external interface is the one genuinely new question here, and the answer is
already in the observation: the names other modules import from it, and the names it imports from
elsewhere. Neither is a decision, so no rule and no contract field appears; the level is read the
way the component level is read. Cards, edges and the selection model keep the shape `level()`
already returns, because layout, ranking, routing and the inspector all consume that shape and a
third level that invented its own would rewrite them. Check: opening `archkeel.ir.codec` shows 71
symbols and the 165 edges between them.

**AD-24 The report opens a component without requiring a decision.** The flow view may open a
component and show its modules and the imports between them, derived from the same observation and
from no contract field. Where the component declares no inside, nothing there is decided, so those
edges are drawn as observed, never as conforming; a declared inside is recorded in that same
observation and decides the pairs that cross its sub-components (AD-34). Reason: the data is already measured and never shown: 142 module edges, 74 of
them inside a single component, with full module names. Looking inside costs nothing, while deciding
inside is AD-20 and costs a contract of its own. Limit: a further step into a module can only use
`symbols` and `calls`, and about one call in five stays unresolved, so such a view would show
structure without proving relations. Check: the opened view renders from `architecture.json` alone.

**AD-25 Peers are isolated by one rule, not by n·(n-1) prohibitions.** The rule kind
`sibling_isolation` names a set of modules or packages as peers: they may reach shared modules and
may be reached from outside, but no member may import another member. Archkeel declares every one
of its analyzer collectors as such a set, and a hygiene test fails when a collector module exists
that the set does not name, because a peer nobody declared is a peer nobody isolates. Reason: AD-1 keeps the collectors flat and single-purpose behind
one orchestrator, and the measurement confirms the intended shape, with `records` imported twelve
times and importing nothing, `source` imported eight times, `scanner` importing ten modules, and no
import at all between two collectors. Nothing held that invariant, and expressing it with the
existing means would have taken 56 `forbidden_dependency` rules between eight peers. The kind is
general: plugins, adapters, feature slices and strategy implementations all share the constraint
that siblings communicate through shared foundations instead of through each other. Contract
`schema_version` stays 2.1.0, because a new rule kind makes no valid contract invalid and older
Archkeel versions fail closed (AD-8); the analyzer version rises because the same input can now
yield new records (AD-3). Check: a probe where one peer imports another yields exactly one
violation while an import of a shared module yields none, and Archkeel's own contract carries the
rule.

**AD-26 A quality claim is a signal, a derivation and a claim, and never guesses.** Every quality
claim has three parts: a signal the analyzer records and declares as a capability, a pure derivation
in `ir`, and a Class D claim the report shows without a verdict. When the signal is missing, the
derivation reports UNKNOWN and shows no candidates, the way regression measurements exist exactly
when the comparison is SUPPORTED (AD-5). Reason: deriving unreferenced symbols from call and import
records alone produced 41 candidates on Archkeel itself; after exempting dunder names, `__all__`
entries and methods of subclasses, 13 remained, and every one of them was wrong, because a function
used as a value (`_RULE_PARSERS`, `type=_sha`), a property read as an attribute and a consumer
outside the scan scope are all invisible to a call graph. The same run listed 8 modules nobody
imports, and all 8 were package `__init__` files, an entry point or a subprocess target. A claim
whose candidates are wrong every time teaches readers to skip the section, which costs more than the
missing claim. Check: a derivation without its signal returns UNKNOWN, and a probe whose function is
referenced only as a value yields no candidate. The claim set grows the same way: `unread
binding` is the second claim, and its signal is the `bindings` section, which records a parameter
or local no expression in its own function reads. That question is settled inside one scope, so
the claim is supported wherever the analyzer ran; what it cannot observe is how many bindings the
collector set aside, so it reports the functions it examined as its denominator instead of
inventing that number. On Archkeel itself it names nothing, because `ARG` and `RUF059` reject such
a binding at lint time: a claim that stays empty on a clean repository is working, not missing.

**AD-27 A type escape hatch is decided, not merely observed.** The analyzer has recorded `Any` in
an annotation as a typing signal since the first release, but no rule kind named it, so the
strongest way to hide what crosses a boundary was the one thing a contract could not forbid.
`any_annotation` therefore joins `ForbiddenConstructKind` and reuses the path `type_ignore`
already takes: a typing signal that `_construct_violations` reads exactly like an `assert`
statement, so no new machinery appears. Adding a kind to a rule kind leaves `schema_version` at
2.1.0 (AD-8). The escape hatch stays legitimate where a program decodes foreign data, so a
contract that needs it scopes it with `allowed_sources` and records why, rather than dropping the
rule. Check: the shop sample declares no `Any` and passes; the tour overlay declares one and
fails with `CONSTRUCT-NO-ANY`.

**AD-30 A declared owner is worth nothing until something can contradict it.** `spot_owners` has
been a class-C declaration since the first contract: the architect names who owns a piece of
knowledge, the analyzer records it, and nothing ever looked. The claim `repeated logic` gives it a
reader. Its signal is a `shape` on every function and method symbol: the node types of the body in
walk order, hashed, with names and literal values dropped, so a copy survives renaming. Two
functions with one shape are structural twins, and the claim names those that sit outside an owner
whose twin sits inside it.

The shape is an exact digest rather than a similarity score. The prior art compares
thirty-dimension node histograms by Jensen-Shannon divergence under a float threshold, which would
put a platform-dependent comparison inside a report that must stay byte-identical (AD-7), and buys
a cloud of near-matches where AD-26 already warns that wrong candidates teach readers to skip the
section. An exact hash finds only true twins, and that is the trade this claim accepts. It lives
as a field on `symbols`, not as a new section, because a shape is a property of a declaration and
an added field breaks no older artifact, while an added section does (AD-3). The size below which a
shape says nothing is decided in the derivation, not in the collector: the signal records every
shape, the claim decides what is too common to mean anything. Ten nodes, measured. Across 431
functions Archkeel shares nineteen shapes, and the three groups below ten nodes are shapes the
language forces rather than copies: eight functions are the
`visit_FunctionDef`/`visit_AsyncFunctionDef` pair that `ast.NodeVisitor` makes every collector
write twice, and a pair of empty `Protocol` methods measures zero. A docstring is not part of the
shape, for the reason `body_is_empty` already ignores it — one sentence of prose must not disguise
a copy. Above the threshold every group is a real repetition, several of them owed to this
repository's own agent: two collectors whose `__init__` and `visit_ClassDef` match line for line,
two rule parsers that differ only in the kind they name, and one record-field reader standing three
times in `ir`, since merged into `ir.model.text_value`. A claim that names its author is working,
and what it names gets fixed. Check: the shop sample declares
`shop.model` the owner of order arithmetic, and the tour places a copy of `Order.total` in
`shop.app`, which the claim names at 29 nodes.

**AD-29 A function that does nothing is a claim, not a stub.** An agent that writes a function
whose body is `pass`, `...` or a lone `raise NotImplementedError` has reported progress it did not
make, and every caller downstream is written against a promise. `placeholder_body` joins
`ForbiddenConstructKind` as one kind rather than three, because the three spellings state the same
thing and the spelling belongs in the record, not in the contract. Emptiness is legitimate exactly
where it is the interface: a method carrying `@abstractmethod` or `@overload`, and a method of a
class that has a base, where a protocol declares the shape and an override may deliberately do
nothing. The predicate that decides emptiness now lives in `source.py`, which both collectors
already import, instead of being written twice — collectors are peers that never import each other
(AD-25), and a third module for six lines would be machinery for its own sake. Check: Archkeel
declares the rule for itself and stays green, because its only two empty bodies are `Protocol`
methods; a probe with a bare `pass` fails.

**AD-28 An undeclared external dependency is a hole, not a detail.** `external_dependency_scope`
limits a dependency the contract already names, so nothing ever decided an import the contract
never mentions: a module importing `helpers`, or a package that does not exist at all, passed with
exit 0 and an empty diagnostic list. The rule kind `complete_external_scope` closes that world the
way `complete_assignment` closes it for modules — an import whose target is neither a scanned
module nor part of the standard library must be covered by an `external_dependency_scope` rule,
and is otherwise a violation naming the importing module. The standard library is recognised
through `sys.stdlib_module_names`, which ties the verdict to the Python version; that version is
already part of what makes an observation comparable (AD-3), so a report stays reproducible for a
given version while a version change can move a module in or out of the set. The alternative,
declaring every standard-library module in the contract, would add two hundred rules that record
no decision an architect ever made. Check: a probe importing an invented package fails, and the
shop sample, whose externals are declared, passes.

**AD-32 A component names what it requires; what it does not name is forbidden.** AD-15 makes every
ordered component pair a decision, so n components cost n·(n-1) rules: Archkeel's six components
carry exactly 30 of them, 22 prohibitions and 8 permissions, for the 8 edges the analyzer actually
observes. The cost is not this level but the next one. A second level on `check` drafted 12
sub-components and asked for 132 decisions (AD-20), four times the whole top level, which is why a
component's inside has never been described by its own contract: the file split is not blocked by
the split, it is blocked by the pair model. A component therefore declares `requires`, the
components it may import, beside the `public` it already offers, and each entry carries the
architect's reason. A pair absent from that list is decided, not open, forbidden by the same closed
world `complete_assignment` uses for modules; so the two lists compose the way AD-20 already
requires, one naming what crosses outward and one what crosses in. The rule kind `complete_requires`
makes the list checkable the way `interface_boundary` makes `public` checkable: a cross-component
import no `requires` entry covers is a violation naming the importing module, and without the rule
nothing changes: the rule is the gate, so no repository inherits this work by upgrading (AD-31).
Under the rule no pair is ever open, because absence decides; open means only that a component
named by the rule has no list at all. `init` writes neither the rule nor a list, because a list it
wrote would decide the pairs AD-15 reserves for the architect, so a freshly drafted contract is
unchanged. AD-20 ties two levels together partly by checking that nothing inside a component
imports what the level above forbids; under this decision that term is the complement of a
`requires` list rather than an enumeration of prohibitions, and AD-20 is to be built against that
reading. Archkeel's own 30 pair rules become 8 entries, one per
observed edge and no more, because its permissions and its observation already agree exactly.
Limit: `requires` speaks about components, so the 11 rules that narrow a pair below package level, a
forbidden target module or a `target_symbol` or `allowed_sources`, survive unchanged; and
`decided_by` moves from the edge to the rule, so the report counts one decision where it counted
eight. Contract `schema_version` stays 2.1.0, because `requires` is an optional property on a
component that forbids no existing one and a new rule kind makes no valid contract invalid, while
older Archkeel versions fail closed (AD-8). Check: a shop probe whose `render` component imports
`model` without requiring it yields exactly one violation, the contract corpus pins both the rule
and a malformed `requires` entry, and `init` on a fresh repository drafts no `requires` list.
Archkeel's own contract adopted the rule in a step of its own: it now carries the 8 entries above,
one `complete_requires` rule and 25 rules in total, where the 30 pair rules used to be.

**AD-33 A component's inside is a level, not a list of pairs.** AD-31 governed the inside by
demanding a decision for every observed module pair there, which is the enumerate-every-pair model
AD-32 abolished one level up. It is retired and `complete_inner_decisions` is removed rather than
deprecated, because it was drafted and released in no version: the tags stop at 0.3.0 and no
contract outside this repository can carry it. One thing survives it, and the log is the only place
that argument lives: the expected set is the pairs the analyzer observed, never the product of the
modules, since `analyzer` holds 21 modules whose product is 420 pairs against 46 observed ones.
`requires` inherits that principle. The inside is governed instead the way AD-20 already decided, by
its own scan scope and its own contract, with its own components, their own `requires`, and one
`public` both levels declare alike. That became affordable only with AD-32: a second level on
`check` drafts 12 sub-components, which is 132 ordered pairs under AD-15 but 23 `requires` entries,
and on `ir` 13 sub-components, 156 pairs against 15 entries. An inside can outgrow the whole top
level, which holds 6 components and 8 edges, so leaving it ungoverned by default hides the larger
half of the system. The report therefore names a component holding more modules than the contract
has components, or more edges among those modules than it has component edges. Both quantities are
already in the observation, which is what makes the trigger legal: AD-10 binds the view to one
observation, and what a second level *would* draft is not derivable from it, because drafting needs
a second scan at a narrower scope. Which of the two quantities is chosen does not matter, because
on this repository they agree on every component: `analyzer` at 21 and 47, `check` at 13 and 23 and
`ir` at 15 and 22 stand against 6 and 8, while `cli` at 4 and 3, `render` at 5 and 3 and `host` at
2 and 0 stay below. The draft-based reading would have called `analyzer` small on the strength of
3 drafted sub-components, which measures how a package happens to be cut rather than what it holds.
Depth itself stays optional (AD-20): the report states that an inside is large, and the architect
decides whether to open it, because naming a size is evidence while opening a level is intent.
Check: no schema or model carries `complete_inner_decisions`, and the report names `analyzer`,
`check` and `ir` as larger than the top level while staying silent about `cli`, `render` and `host`.

**AD-34 A declared inside is recorded, so the report draws it without reading a second contract.**
The observation carries a declared inside as a record kind of its own: one record per sub-component
with its packages, its `requires` and the `parent_id` of the component holding it, and the inside
contract's digest folded into the contract digest, so an edit inside changes what `delta` compares.
`ir` derives every inner verdict from those records alone, and the flow view opens a component that
declares an inside into its sub-components first and into its modules one level deeper, in the shape
`level()` already returns (AD-24a). A module no sub-component owns keeps a card of its own. No inner
pair is ever `undecided`: under `complete_requires` absence forbids (AD-32), so a crossing pair is
covered or violated, which leaves AD-24b standing as written. Reason: `check` declares three
sub-components, yet all 23 of its inner edges were drawn grey although the inside contract decides
14 of them, `entry` → `foundation` at 21 import sites, `entry` → `policy` at 6 and `policy` →
`foundation` at 2. Three cheaper ways to colour them were rejected. Reading the inside contract
while rendering breaks AD-10 and makes the picture depend on a file that need not be present.
Reusing the kind `component_responsibility` makes `check` and `entry` both claim every module below
`archkeel.check`, so `owner_of` finds two owners, returns `None`, and the five callers of
`component_owners` degrade in silence. Letting the state fall through to `conforms` the way the top
level does, violation else undecided else conforms, would make green mean unopposed rather than
covered, so a `foundation` → `entry` edge added later would still draw green; the verdict is derived,
never defaulted. Limit: one level down is recorded, so an inside declared within an inside is not
drawn and the report says nothing about it; a third level needs a pass of its own, and until it
exists a deeper contract is silently unused rather than silently wrong. Check: opening `check`
shows three sub-components, its three crossing edges carry
21, 6 and 2 and are green because `requires` names them, the 9 edges inside one sub-component stay
observed, `archkeel.check` appears owned by none, and `component_owners` still returns exactly the
six top-level components.

**AD-35 Every review claim is counted on the run result, so the terminal and the JSON name what
the page shows.** `ir.decisions` derives one count set from the observation, the four AD-26 and
AD-33 claims together, and `report` and `validate` carry it on `RunResult` beside `agent_decisions`
and `open_decisions`, which are already derived counts rather than evidence. The terminal prints one
line of counts, the HTML keeps its tables, and the result JSON gains the same counts, so an agent
reading the result sees a claim without parsing `architecture.json`. A claim stays a claim: no
verdict row, no exit code, no gate (AD-26). Reason: Archkeel named
`archkeel.check.expectation.load_expectation` unreferenced in its own report, and it was acted on
only after a hand-written script recomputed what the page already displayed; `validate` writes no
HTML at all, so there a claim had no surface whatsoever, and `report` shows it only to whoever opens
the file. Two cheaper ways were rejected. Carrying the observation itself on the result reads well
until `codec.result_payload` serializes `observation` whenever it is set, which grows
`archkeel report --json` from a few hundred bytes to the whole artifact. Printing the claim tables
in the terminal buries the three verdicts the command exists to deliver under four tables of
candidates. Limit: counts only, so the terminal never names a symbol; a named list reads like a
worklist, and the detail belongs where the evidence is. Consumers of the result JSON see one new
field, which no schema version announces because the result payload carries none. Check:
`archkeel report` on Archkeel prints 1 unreferenced, 3 oversized, 0 unread and 0 repeated, the
verdict table and the exit code are unchanged, and `archkeel validate --json` carries the same four
counts.

**AD-36 A rule the inside declares is recorded and carried, so the verdict it produces survives
every command.** Three things follow from it. An inside contract is renamed once as it is loaded,
each of its rules under `<parent>:<rule id>` the way a sub-component already is, so the projected
declaration, the violation and the id that violation is filed under are all built from the name
they will be read by, rather than corrected afterwards. A projected rule carries the
`parent_id` of the component holding it, and the derivations that decide *this* level's pairs,
`requires_declared` and `_decided_component_pairs`, skip a record that carries one, while
`agent_decisions` counts it: whose decision a rule is and which level it governs are two different
questions. And `declaration_paths` names each component's `inside`, so a `check` snapshot
materialises the contracts the lock was written over. A violated inside rule points at
`/components/<n>/inside` rather than at a `rules` array it is not in. Reason: the inside's verdict
was recorded and then silently lost, in two independent places.
`requires_violations` wrote `rule_ids: ["STORE-REQUIRES-COMPLETE"]` while the observation carried no
record under that id, so `trace_valid_violations` dropped the violation from the report and
`validate` answered `observation.incomplete` naming an internal record id instead of the import that
crossed the boundary: an inside whose rule fires reported less than an inside with no rule at all.
AD-34 claims that verdict reaches both the view and the exit code through the records every other
verdict travels in; it did not, and `check` never saw the level at all, because
`materialize_declarations` copied the contract and its provenance documents and nothing else, so
both snapshots observed the level above while the lock had been written over both and could never
be verified again. Neither showed, because the only declared inside in existence was Archkeel's own
`check`, which satisfies its `complete_requires` and whose lock no demo rebuilds. Four cheaper ways
were rejected. Projecting the inner rules under their bare ids renames nothing, but an inner rule
named like an outer one then becomes a duplicate record id, which fails the whole observation
instead of the contract that caused it. Renaming the ids on the records and the violations after
they are built leaves the one fact in two places to be kept in step, and the violation's own
`stable_id` still collides. Splitting the parent off the rule id where a derivation
needs to know the level decides behaviour from a name, which is what `parent_id` exists to avoid.
Letting `trace_valid_violations` accept a violation whose rule is missing would silence every broken
evidence chain, which is the only thing that check is for. Limit: every inner rule is recorded,
while only `complete_requires` is evaluated inside (AD-20), so a record can state a decision the
level does not yet enforce; projecting only the evaluated kind would hide the others from the reader
as well as from the gate. An inside contract's own provenance documents are still not carried, for
the same reason no command reads them. Check: the shop sample declares an inside for `store` whose
four sub-components cross at three edges, the catalogued `class-a-complete-requires-inside` row
drops one `requires` entry and reads three `rule.violated` findings under
`store:STORE-REQUIRES-COMPLETE` at `/components/1/inside`, `class-a-decision-open` still reports
its open pair with an inside declared, and every `check` protocol row verifies its lock over both
levels.

**AD-37 A receiver whose type is statically obvious resolves the stdlib method it calls.**
`resolve_name` recognises three sources for a method call `recv.method(...)`: a str or f-string
literal written directly at the call site; a local name every one of whose bindings in the
function's own scope agrees on a list/dict/set/str literal or an unshadowed
`list()`/`dict()`/`set()` constructor call (an annotation of the same type is not a disagreement);
and a parameter or local whose only binding, if any, is an annotation naming `list`, `dict`, `set`,
`frozenset`, `tuple`, `str` or `pathlib.Path`/`Path`, generic subscript included. A second,
differently typed or non-literal binding of the same name — a plain rebinding, a `for`/`with`
target, a walrus or an unpacked assignment — voids the name for the whole function rather than
picking a winner, because which binding a call site actually sees is exactly the control-flow
question this cut does not attempt to answer. Each type carries a hand-written table of its
public methods, copied from the documentation rather than read with `dir()`, because `dir()`
answers for whichever interpreter happens to run the analyzer and AD-7 requires the same source to
resolve the same way on every supported one. A literal proves its type outright, so it resolves; an
annotation is a declaration Python never checks at runtime, so it resolves only
`partially_resolved`, the same distinction `resolve_name` already draws between an indexed symbol
and a name that only matches one by tail. `_local_receiver_types` reads these bindings from the
function's own-scope walk that `bindings.py` already defines, moved to `source.own_scope` so both
read it instead of each re-deriving the same boundary: a nested function's own locals must never
leak into its enclosing scope's receiver map, and a second copy of that boundary is a second place
for it to drift. Reason: measured on Archkeel itself, 703 of 3,982 calls were unresolved (17.65%),
and classifying every one showed 621 of them (88%) were exactly this: `''.join`,
`diagnostics.append`, `items.extend`, `check.add_argument` and their like, stdlib container,
string, path and argparse methods on a receiver the source already states the type of.
`calls_unresolved` and `unresolved_ratio` are regression gates (`check/ratchets.py`), so this noise
moved the gate on every line the analyzer's own source added, never on a change to what it actually
calls. Three cheaper ways were rejected. Reading `dir(list)` at analyzer runtime answers correctly
today and wrongly on whatever Python version adds or removes a method next, which fails AD-7's
determinism requirement outright. Inferring a receiver's type from every assignment along every
control-flow path is the general problem a static call graph cannot solve in Python at all; a
function that assigns `items` a list on one branch and something else on another stays out of
scope, because this cut answers only the receiver a single, unconditional literal or a declared
annotation already commits to. Resolving a call result's own type, as in `Repository(root).save(...)`
or `hashlib.sha256().digest()`, needs a second, expression-level type inference and stays unresolved
with its existing reason, so a method invoked on a call result is never conflated with one invoked
on a name whose binding this function can point to. Limit: a receiver two attributes deep
(`self.items.append`), a subscript receiver, and a name reassigned across branches to conflicting
types stay unresolved exactly as before; the table names only methods present on every supported
Python, so nothing version-specific is guessed into it. `ANALYZER_VERSION` rises, because the same
input now yields different call records (AD-3). Check: `tests/test_analyzer.py` probes each
resolution source once, a call-result receiver once, a method absent from the table once, and a
name rebound outside the table's proof — a plain reassignment, and a `for` target — twice;
`tools/classify_unresolved.py` re-run on Archkeel's own live source falls from 703 unresolved calls
of 3,982 (17.65%) to 421 of 4,051 (10.39%).

**AD-38 A drafted component carries the size `structure_metrics` already measures, so the
architect sees what a per-child draft hides before deciding whether to consolidate.**
`draft_contract` maps every in-scope module to the child directory `init` would name a
component, the same grouping it already builds to name the components themselves, and
passes that grouping to `ir.structure.scope_metrics`: the aggregation `structure_metrics`
uses for a declared component, generalized to any caller-supplied scope so a draft measures
the same way a contract does once it exists. No second scan runs; the modules and edges were
already in the one observation `init` made (AD-10). The two numbers travel to the three
places an architect or agent reads a draft: the generated table gains Modules and Inner
edges columns next to each component, `init --json` gains `draft_sizes`, and the terminal
prints one line naming the drafted component whose module count uniquely leads, or that none
does. Reason: measured on this repository, `init --source src/archkeel/analyzer --namespace
archkeel.analyzer` drafts 3 components — `bridge`, `embedded`, `runtime` — while `embedded`
alone holds 18 of the scope's modules, a fact the three bare names do not carry; `init` on
`src/archkeel/ir` drafts 14 components and 182 open decisions; `init` on `src/archkeel/check`
drafts 12 components and 132 open decisions, where the architect settled on the 3 named in
`src/archkeel/check/architecture-contract.json`. An agent consolidating a draft into a few
sub-components had to reread the source tree to find which child was worth folding into
which; the draft itself said nothing about size. Two cheaper ways were rejected. Recomputing
size from the drafted contract once it is written asks `validate` or `report` to do it, but by
then the draft is already committed to a directory-per-component shape with no size signal to
question it against. Naming every drafted component's size in the terminal, the way the open
decisions list does for pairs, buries the one number worth reading under as many lines as
there are components; one line naming the largest keeps the summary the length of the other
onboarding lines. Limit: `init` still proposes one component per direct child directory, not
by import connectivity between modules; a large, well-connected child still becomes one
draft component and a directory split across two unrelated purposes still becomes two,
because grouping by directory is what makes the draft reproducible from names alone. Whether
a sub-root draft should instead group modules by which ones import each other, so a size
outlier could also be a cut point instead of only a number, is open. Check:
`tests/test_onboarding.py::test_init_drafts_component_sizes_and_names_the_largest`,
`tests/test_terminal.py::test_terminal_view_names_the_largest_drafted_component` and
`test_terminal_view_says_no_drafted_component_stands_out_on_a_tie`, and
`tests/test_self.py::test_self_contract_public_matches_drafted_proposal`, which still passes
with `draft_contract` returning a third value.
**AD-39 An empty `selected_changes` declares that nothing architectural changed.**
`parse_expectation` no longer rejects `"selected_changes": []`; it only requires a list, so the
field still means exactly what it always meant, a set of semantic changes the agent selects, and
an empty set is simply the smallest legal one. `evaluate_expectation` reads that emptiness as a
positive claim rather than an omission: with a non-empty declaration it keeps checking exactly what
it checked before, the named fingerprints against the observed delta plus the five fixed guardrail
dimensions (`violations`, `cycles`, `private_crossings`, `typing_signals`, `unknowns`) for
regressions and new entries; with an empty declaration it instead fails on every entry in
`delta_model.semantic_changes`, in any of the eight delta dimensions, naming the dimension, the
change kind and the fingerprint. The function was decomposed into six named phases,
`_require_matching_provenance`, `_require_dimension_counts`, `_index_semantic_changes`,
`_match_selected_changes`, `_guardrail_failures` and `_undeclared_change_failures`, so the new
branch reads as one call rather than more inline logic on top of an already-long function (AD-6).
Reason: the M → B → E → H protocol has no other way to submit a change with an empty semantic
delta. A candidate that adds one pure function to `src/archkeel/ir/digest.py`, calling nothing and
called by nothing, observably changes no dimension at all, yet `parse_expectation` answered
`selected_changes must be a non-empty list`: an agent required to declare every submission had no
legal declaration for a refactor that changes nothing. Two cheaper ways were rejected. A dedicated
boolean field such as `no_semantic_change: true` says the same thing a second way, and doing so
changes the required key set, so it costs a schema bump for no reading `selected_changes` does not
already give for free. Reusing the existing guardrail-only comparison for an empty list, so an
empty declaration silently meant "no fixed-dimension regression" the way a non-empty one already
does for its unselected dimensions, was rejected because it would make `selected_changes: []` a
standing exemption for every non-guardrail dimension, available to any candidate regardless of
what it actually changed, rather than the narrow claim "nothing changed" it is meant to be. Contract
`EXPECTATION_SCHEMA_VERSION` stays 1.2.0: the required field set is unchanged and a JSON array was
always a legal `selected_changes` value, so no previously valid expectation becomes invalid, while
an older checker already fails closed on the empty list with `selected_changes must be a
non-empty list` (AD-8) instead of silently accepting it under the old, narrower meaning. Limit: the
probe that motivated this decision also showed that a *non-empty* declaration still lets an
undeclared change in a dimension that is neither selected nor one of the five guardrail dimensions,
for example a new `dependency_edges` entry, pass with no failure at all; this decision closes the
equivalent question only for the empty-declaration case, where every dimension is now checked,
and AD-44 later closed the non-empty case for `dependency_edges` specifically. Check: `tests/test_expectation.py`'s
`test_empty_declaration_of_no_change_passes_against_an_empty_delta`,
`test_empty_declaration_fails_on_a_guardrail_dimension_change` and
`test_empty_declaration_fails_on_a_non_guardrail_dimension_change`, and the catalogued
`protocol-empty-declaration` row in `fixtures/demo_catalog_check.py`, whose comment-only overlay
produces a genuinely empty delta and passes every verdict.

**AD-40 A call whose callee the import binding proves, or whose receiver is already typed, types
its result from a documented table.** `resolve.call_result_type` reads two shapes. A constructor
call, `hashlib.sha256()`, `argparse.ArgumentParser(...)`, `Console(...)`, `Table(...)` or
`Path(...)`, is typed when its callee resolves through the module's import bindings to a name
`receiver_types._CONSTRUCTORS` lists, so a local class that happens to be called `Table` never
matches. A method call on a receiver that is already typed, `parser.add_subparsers(...)`,
`commands.add_parser(...)`, `path.relative_to(...)` or `digest.copy()`, is typed when
`receiver_types._METHOD_RETURNS` names the documented return type of that method. Both feed the
same two places AD-37 reads: a local bound to such a call enters `_local_receiver_types` with the
origin `documented`, and a call written directly as the receiver of another call,
`hashlib.sha256(payload).hexdigest()`, is typed at the call site the way a string literal already
is. A `documented` receiver resolves `partially_resolved`, never `resolved`: the import binding
proves which callable is named, but what it returns is what the documentation says, which Python
checks no more than it checks an annotation, so AD-37's line between what the language proves and
what a document states stays where it is. To let a chain type in one pass, `source.own_scope` now
walks statements in source order, which the two callers it had before never depended on.
Reason: after AD-37, the largest remaining unresolved groups on Archkeel's own source were method
calls on exactly these results, `digest.update` on a hash object, `add_argument` on the parsers
`add_parser` returns, `print` and `add_column` on Rich's console and table, and `as_posix` on the
`Path` a `relative_to` call returns; none of them is a receiver a literal or an annotation names,
so AD-37 could not reach them, and every one of them is a stdlib or declared-dependency method
the source already fully states. Two cheaper ways were rejected. Adding annotation names such as
`Table` or `Console` to AD-37's annotation table was rejected because an annotation is matched by
its bare spelling, and a project's own `Table` class would resolve to Rich's methods; the
constructor path goes through the import binding instead, which names the module it came from.
Typing from a callee's return annotation in the analysed source itself was rejected because that
is expression-level type inference over project code, the general problem AD-37 kept out of scope;
this decision stays with a closed table of documented library types. Limit: a chain types only
forward through one function's own scope, so a receiver that is later rebound is not retroactively
voided for a local already typed from it; a method whose return type the table does not name ends
the chain; and only the listed constructors and returns are known, so `hashlib.new` with a name
argument is typed while a hash constructed by any other route is not. `ANALYZER_VERSION` rises,
because the same input now yields different call records (AD-3). Check: `tests/test_analyzer.py`
probes a constructor-bound local, a call written as the receiver, the two-step argparse chain, and
a callee that is not an import binding; `archkeel report` on Archkeel's own source falls from
421 unresolved calls of 4,071 (10.34%) to 381 of 4,101 (9.29%), and what remains is outside this
table by construction: `_Parser` in `cli` subclasses `ArgumentParser` in project code,
`terminal.print_result` binds its console with `console or Console()`, and `path` in the
scanners is a `for` target.

**AD-41 Where `Any` may appear is a contract rule, not a test.** `CONSTRUCT-NO-ANY` forbids the
`any_annotation` construct across `archkeel` and exempts exactly the two owners AD-2 named, the
codec that decodes open JSON (`archkeel.ir.codec`) and the collectors that write it
(`archkeel.analyzer.embedded`); `tests/test_source_types.py` no longer greps the source for
`Any` with the same two exemptions hard-coded as path prefixes. Reason: the exemption list was
architecture knowledge held in a test, so `archkeel report` on this repository could pass while
the rule it did not know about failed in `pytest`, and a reader of the contract saw no decision
about `Any` at all; the analyzer already records every `Any` annotation as a typing signal and
`forbidden_construct` already evaluates that construct with `allowed_sources`, so the rule costs
no code. Rejected: keeping both, since two sources of one decision drift, and the regex
recognised three spellings while the analyzer recognises the annotation itself. Limit: the rule
matches `Any` in annotations, not the `object` escape hatch, which stays a ratchet signal (AD-2)
because `object` at a JSON boundary is the honest type, not an escape. Check: the rule passes on
the current source with zero violations, and moving one `dict[str, Any]` out of the two owners
is a `rule.violated` finding in `archkeel report`.

**AD-42 A `requires` entry may name the modules it goes through, and twelve prohibitions become
that one permission.** A `requires` entry gains an optional `through` list of module prefixes of
the required component; `complete_requires` then covers an import only when the imported module
falls under one of them, and an import of any other module of that component is the violation
it already was for a component never required at all. The analyzer's entry reads
`{"component": "ir", "through": ["archkeel.ir.model", "archkeel.ir.codec"]}`, which is AD-4
stated where the dependency is stated, and the twelve `DEP-ANALYZER-NO-IR-*` rules that said the
same thing one `ir` module at a time are gone. Reason: the twelve rules were a blocklist, so
each module `ir` gained since (`references` with AD-26, `levels` with AD-34) had to be remembered
by hand or was silently open to the analyzer, while `tests/test_self.py` held the real allowlist
as a test; the entry's own rationale already said "through the common model and codec boundary",
so the contract had the decision in prose and enforced its complement. Rejected: an
`allowed_targets` field on `forbidden_dependency` with `source: archkeel.analyzer, target:
archkeel.ir`, because a rule whose source and target are exact component packages decides the
pair (AD-15) in the analyzer's matcher, in `ir.decisions` and in `check.validation`, so all
three would need to learn that this one narrows instead of decides; `through` touches one
evaluation and changes no pair semantics, since absence still decides. Limit: `through` narrows
by module prefix, not by symbol, so `archkeel.ir.model` admits every name the module defines; a
prefix naming a module of a different component covers nothing, the same blind spot a `requires`
entry naming an unknown component has; and the projected declaration record still lists only the
required component, so the observation shows the edge but not its width. Check:
`tests/test_analyzer.py::test_a_requires_entry_covers_only_the_modules_it_goes_through`,
`tests/test_self.py::test_self_contract_covers_modules_and_analyzer_interface` reading the
allowlist from the contract instead of a constant, and `validate` naming an unknown `through`
module at `/components/<n>/requires/<m>/through/<k>`.

**AD-43 A candidate declares what it changed, not what the scanner counted or what every
module already carries.** Two cuts land together because both come from the same measurement.
First, the eight per-counter `coverage` records (`files_discovered`, `calls_resolved`, and the
rest) stop feeding `_compare_records`; `_delta_records` returns `()` for the `coverage`
dimension instead of calling the record-projection machinery, so `_coverage_records` and its
`Projection`/`EvidenceClass` plumbing are gone. `DeltaCoverage` already reads
`baseline.coverage.status`/`head.coverage.status` into one PASS/FAIL, and both full `Coverage`
records stay on the observations `report` renders from, so nothing a reviewer could read is
lost, only five mechanical `semantic_changes` entries that shifted by construction whenever any
file was added or removed. Second, `check/python_profile.py`'s `crossing_imports`, the one
function `delta.py` and `ratchets.py` both call to turn raw `imports` records into crossings,
drops `from __future__ import annotations` before it reaches either caller: a
`_LANGUAGE_BOILERPLATE_IMPORTS` set of `(target_module, symbol)` pairs, one entry today, marks
imports that name no project symbol on either side and that every module in a namespace already
carries. `ratchets.py`'s `private_crossings` scalar is untouched, because `annotations` is never
a private symbol. Reason: adding `src/archkeel/ir/labels.py`, two lines,
`from .digest import package_digest` and one function, on top of Archkeel's own accepted
observation measured 7 `semantic_changes` for a change with one informative fact, one
`dependency_edges` addition; the other six were the five coverage counters and the future
import, none of which said anything about `labels.py` itself (roadmap item 6). Rejected: emitting
one semantic change per `coverage` dimension only when its aggregate `status` flips, instead of
none at all, was rejected because `DeltaCoverage.status` already carries exactly that flip as a
typed field `evaluate_expectation` reads unconditionally, so a tenth declarable entry saying the
same thing would cost an agent a declaration for information the check already enforces without
one. Filtering `from __future__ import annotations` in the analyzer's `imports.py` collector
instead of in the checker's own profile was rejected because that is a fact about what the
source imports, true regardless of who reads it, and AD-3 ties any change to what the analyzer
records to `ANALYZER_VERSION`; every other reader of the `imports` section (`ratchets.py`, the
HTML report's component flow, `tools/interface_profile.py`) still needs the record, so only the
one place that turns a record into a declarable crossing should stop counting this one. Neither
cut touches the analyzer, so `ANALYZER_VERSION` is unchanged; `DELTA_SCHEMA_VERSION` rises to
1.3.0, because the same two observations now produce fewer `semantic_changes` than an older
checker would compute for them, and AD-8's fail-closed reading of a schema version is for a
reader that does not yet know a meaning changed, not only for one that would otherwise accept
something invalid. `EXPECTATION_SCHEMA_VERSION` stays 1.2.0: the expectation's required fields
and `SUPPORTED_DIMENSIONS` are unchanged, and `_require_matching_provenance` already binds every
expectation to `checker_digest == package_digest()`, the exact running package, before any
dimension is read, so no expectation is evaluated against a delta shape it was not written for.
Limit: the boilerplate set names one import by exact `(target_module, symbol)` pair, not a
pattern, so a second language-boilerplate import would need its own entry the way this one was
added. Check: `tests/test_delta.py::test_one_module_with_one_intra_component_import_is_one_semantic_change`
reproduces the `labels.py` shape and asserts exactly one `dependency_edges` addition;
`tests/test_delta_parity.py`'s golden digests moved with `DELTA_SCHEMA_VERSION`'s own bytes,
covering import records unaffected by either cut; `docs/roadmap.md` records 7 -> 1.

**AD-44 An undeclared added dependency edge is a guardrail failure, closing the AD-39
Limit.** `GUARDRAIL_DIMENSIONS` gains `dependency_edges`, a sixth entry, but its regression rule
is not the other five's: an edge count grows with any ordinary new import, so
`_COUNT_REGRESSION_DIMENSIONS` (`GUARDRAIL_DIMENSIONS` minus `dependency_edges`) is what
`_guardrail_failures` checks for aggregate growth, leaving `dependency_edges` out of that count
check entirely. What still fires for it is the existing added-fingerprint check every guardrail
dimension already has, now given one more filter: `_guardrail_failures` takes a `declared` set of
`(dimension, change, fingerprint)` identities built from `expectation.selected_changes`, and an
`added` `dependency_edges` fingerprint already in that set is no failure, the same way an added
cycle already accounted for by a contraction is no failure. Only `added` is checked, the same
kind every other guardrail's fingerprint check already limits itself to: a `removed` edge can
only narrow what a component depends on, never cross a boundary a rule forbids, so there is
nothing for it to violate. Reason: AD-39 recorded, as its own Limit, that a non-empty declaration
lets an undeclared change in a dimension that is neither selected nor a guardrail dimension pass
with no failure at all, naming `dependency_edges` as the example; that gap stayed open because
closing it the way the other five guardrails work would have made every declared new edge fail
too. Rejected: giving `dependency_edges` the same unconditional rule as the other five, so any
`added` fingerprint fails whether declared or not, was rejected because a new edge is not
inherently a regression the way a new violation, cycle, private crossing, typing signal or
unknown is; the M -> B -> E -> H protocol exists so an agent can name an intended new edge and
have it accepted, and an unconditional rule would foreclose that for the one dimension ordinary
declared growth touches most often. A ninth `GUARDRAIL_KEYS` boolean, `no_new_dependency_edges`,
mirroring `coverage_must_pass`, was rejected because `GUARDRAIL_KEYS` are fixed-true
acknowledgment flags with no fingerprint of their own, while this check has to compare each
added fingerprint against `selected_changes`, exactly the comparison the cycle-contraction filter
already performs; reusing that shape costs one clause, not a new required field, so
`EXPECTATION_SCHEMA_VERSION` stays 1.2.0. Limit: `dependency_edges` is the one guardrail
dimension whose `added` check a declaration can satisfy; every check-run row in the demo catalog
declares its whole observed delta, so none of them can show the undeclared case failing without a
scenario built to omit one, which no existing row does, so this Limit is documented instead of
demonstrated end to end. Check: `tests/test_expectation.py`'s
`test_undeclared_added_dependency_edge_fails_naming_it`,
`test_declared_added_dependency_edge_passes` and
`test_removed_dependency_edge_does_not_fail_undeclared`; the catalog's `class-b-guardrail-
dependency-edges` row and `fixtures/demo_catalog_check.py`/`demo_catalog_check_regressions.py`'s
updated `regressed_dimensions` show every protocol row still declares its own new edges and
still passes.

**AD-45 `analyzer` declares a three-part inside, the way `check` already does (AD-20).**
`src/archkeel/analyzer/architecture-contract.json` names `orchestration` (`bridge`, `runtime`,
`embedded/scanner.py`, `embedded/report.py`, `embedded/contract.py`), `collectors` (the ten
modules `COLLECTORS-ISOLATED` already names: `bindings`, `calls`, `constructs`, `contexts`,
`dependencies`, `imports`, `references`, `symbols`, `typing_signals`, `violations`) and
`foundation` (`records`, `source`, `resolve`, `receiver_types`, `graph`); the top-level
`analyzer` component points `inside` at it, and `REQUIRES-COMPLETE` is the inside's only rule,
exactly as `check`'s is. Reason: `init --source src/archkeel/analyzer --namespace
archkeel.analyzer` still drafts 3 components one per child path, `bridge`, `embedded` and
`runtime`, with `embedded` alone holding 19 of the scope's 22 modules and 46 of its inner edges
(AD-38); a fresh `archkeel report` on this repository observes 49 module edges with both ends
under `archkeel.analyzer`, and every one of them fits one of three shapes: `scanner` calling
each collector and reading `records`, `source` and `resolve` directly; each collector reading
only `records`, `source`, `resolve`, `receiver_types` or `graph` and never a sibling collector,
which is what `COLLECTORS-ISOLATED` already held; and `report` calling `contract`, `scanner` and,
once, `violations` directly, bypassing `scanner` for that one collector. That last edge is why
`orchestration` requires the whole `collectors` component rather than naming `scanner` as the
only caller: a `through` list naming just the modules `scanner` reaches would have made
`report`'s direct call to `violations` a `complete_requires` violation the layout does not
deserve. Two modules stay owned by neither sub-component: `archkeel.analyzer` (the port's
`observe`) and `archkeel.analyzer.embedded` (an empty `__init__.py`); a `packages` entry is a
dotted prefix (AD-42's `in_scope`), so naming either of these two package roots explicitly would
also claim every module below it, the same reason `check`'s own `archkeel.check` module is the
one AD-34 says no sub-component owns, doubled here because `embedded` nests one directory
deeper than `check`'s flat layout. `archkeel.analyzer`'s public surface, the module
`archkeel.analyzer` itself, is declared under `orchestration` regardless, since
`inside.public_mismatch` compares the two levels' `public` lists as sets, not against
`packages` ownership.
Two cheaper layouts were rejected. One component per direct child directory is what `init`
already drafts and is exactly what this decision replaces, since it hides `embedded`'s size
behind three bare names (AD-38). One component per collector was rejected because
`COLLECTORS-ISOLATED` already forbids the only edges that would distinguish ten single-module
components from each other; ten components each requiring only `foundation` say nothing that
grouping the ten under one `collectors` component, itself requiring `foundation` once, does not
already say, and it would multiply `REQUIRES-COMPLETE`'s bookkeeping by ten for no discovered
edge. Limit: `oversized_insides` (AD-33) compares a component's raw module and edge count
against the top level's own, not against whether it has a declared inside, so `analyzer` stays
one of the three `oversized_components` this repository reports before and after this decision,
the same way `check` never left that list once its own inside was declared. Check:
`tests/test_self.py` reads `analyzer`'s inside contract, its modules and its rule the way it
already reads `check`'s; `archkeel validate --root . --json` and `archkeel report --root .`
both pass with zero violations on the current source.

**AD-46 `validate --write-graph` regenerates the marked component graph after a contract edit.**
With the flag, `run_validate` replaces the edges of the one marked Mermaid graph among the
contract's provenance documents by `observed_component_edges` for the current contract, sorted by
`mermaid_edges`, the one formatter `init`'s `architecture_document` now calls too. It rewrites a
block only when every non-blank line is a diagram declaration (`graph` or `flowchart`), a `%%`
comment or a plain edge `_GRAPH_EDGE` reads: the declaration and the comments stay ahead of the
edges, a block without a declaration gets `init`'s `graph TD` on top, and everything outside the
block stays byte for byte. Any other line, a `subgraph`, a labeled edge `a -->|uses| b`, a
`classDef` or `linkStyle`, makes it write nothing: `graph.drift` stands, and its remedy names that
line and says to edit the edges by hand. Validation then reads the rewritten page, so a run whose
only finding was `graph.drift` exits 0. `run_validate` returns `(RunResult, files)` the way
`run_init` does, the CLI writes both through one loop and `artifact` names the page; a graph already
in that form is not written. `_marked_bodies` is now the one reader of where a marked block starts
and ends, used by `graph_diagnostics` and by the writer alike, so the two cannot disagree about
which block is the graph, and the `graph.drift` remedy names the command whenever the command can
act. Provenance documents are read as UTF-8 explicitly, since the page goes back out as UTF-8
whatever the locale is (AD-7).
Reason: `validate` demands a marked graph equal to the observed component edges, but only `init`
wrote one, so every later contract edit that merges, splits or renames a component left
`graph.drift` to be fixed by hand although `validate` already computes the exact edges it compares
against: issue #2, found onboarding `datamimic_ce` with 0.4.1, and the internal-service finding that
no command regenerates the graph after a component cut.
Rejected: `report --write-graph`, because `run_report` never parses the contract into an
`ArchitectureContract` or reads its provenance documents, it only receives the analyzer's
observation, and it writes evidence under `test-artifacts/`, not the repository's own pages;
`validate` holds the contract, the observation and the documents already. Regenerating the whole
block as `init` writes it, because both marked graphs in this repository, this page's and the shop
sample's, chose `flowchart LR`, and a regenerated block would silently redraw every page that is not
an `init` draft. Writing a marker into a page that has none, or picking one of several marked
graphs, because both guess which page the architect meant; `graph.count` already names either state.
A denylist of `subgraph` and labeled edges, rewriting around them, because Mermaid has more
statements bound to an edge's position or scope than those two (`linkStyle` counts edges by index,
`a --> b --> c` and `a --> b & c` chain them), and a reordering that misses one silently changes
what the diagram says; an allowlist of three line kinds fails closed on every statement it cannot
read, including the ones not thought of yet. Keeping a labeled edge and adding the plain one beside
it, because the graph would then draw the pair twice. Writing only when the edge set differs,
keeping a hand-ordered graph that already validates, because the output would then depend on the
page's history; one sorted form makes the command idempotent, and a second run writes nothing.
Limit: a styled graph, even one whose `classDef` or `style` lines depend on no edge position, is
left to a human, because the allowlist does not tell harmless statements from binding ones; comments
keep their order but move ahead of the edges, and blank lines inside the block are dropped. The page
is written with `\n` line endings, so a CRLF checkout sees every line change. The page is written
even when other diagnostics keep `validate` at exit 2, because the graph records observed imports,
not decisions.
Check: `tests/test_cli.py::test_validate_write_graph_regenerates_only_the_marked_graph` renames the
shop sample's `render` to `view` in the contract, sees exactly one `graph.drift` naming the command,
then exit 0 with the page byte-identical up to the marker, `flowchart LR` kept and the six edges
sorted, and a second run writing nothing;
`tests/test_validation.py::test_write_graph_writes_the_graph_init_writes` and
`::test_write_graph_changes_nothing_without_exactly_one_marked_graph` pin `init`'s form and the
zero-or-several case; `::test_write_graph_adds_the_declaration_a_block_lacks` gives a block holding
only a `%%` comment and an edge its `graph TD`, and
`::test_write_graph_leaves_a_block_it_cannot_read_to_the_architect` writes nothing for a `subgraph`,
a labeled edge or a `classDef` and names that line in the hand-edit remedy;
`tests/test_self.py::test_component_graph_matches_observed_edges` and the catalog's
`validation-graph-count` row still hold on the shared reader. This page's own graph was regenerated
with the command, which only sorted its eight edges.

**AD-47 `init` breaks a tie between top-level packages with `pyproject.toml`'s `[project] name`,
and with nothing else.** `detect_source` still takes the only top-level package under `src/`, or
under the root without `src/`, when there is exactly one. When there are several, it reads
`[project] name` from the root `pyproject.toml`, puts it in wheel file-name form (runs of `-`,
`_` and `.` become `_`, lowercased) and keeps the one package whose lowercased directory name
equals it. A missing or unreadable file, no declared name, or zero or two matching packages
still end in exit 2 with the same `scope_empty` diagnostic and `--source`/`--namespace` remedy;
its claim now also names the project name it compared, or `missing`. Reason: onboarding
`datamimic_ce` with 0.4.1 stopped at `found datamimic_ce, tests_ce` although its
`pyproject.toml` declares `name = "datamimic_ce"` (issue #3). A package beside its test package
is the common layout, and `[project] name` is PEP 621's one standard field, the name hatch,
poetry and flit already assume for the import package when no package list is declared.
Rejected: reading the build backends' own package declarations
(`[tool.setuptools] packages` and `packages.find`, `[tool.hatch.build.targets.wheel] packages`,
`[tool.poetry] packages`) was rejected because it is three dialects with their own glob,
`where` and `from` semantics, and the motivating repository declares only
`[tool.setuptools.packages.find] where = ["."]`, `exclude = ["tests_ce"]`, `namespaces = true`:
reproducing that answer means reimplementing setuptools' `find` discovery, where
`namespaces = true` also counts directories without `__init__.py`, for an answer
`[project] name` gives in one comparison. Excluding packages named `tests*` was rejected
because it guesses from a naming convention instead of reading a declaration: it misses `test/`
and `spec/`, widening it to `test*` would also drop real packages such as `testcontainers`,
and with two real packages beside a test package it would still choose by elimination, the
silent guess the `scope_empty` exit exists to prevent. Sharing `analyzer/runtime.py`'s
`pyproject.toml` read was rejected because `check` may not import an adapter, and the two
reads take different fields. Limit: a distribution named differently from its import package
(`scikit-learn` and `sklearn`), a name declared only under Poetry 1's `[tool.poetry]`, and a
`src/` directory holding no Python package beside a root-level one (a Rust crate, as in
DataMimic EE) still exit 2 and need `--source` and `--namespace`; a single package is taken
without comparing the name, as before. Check: `tests/test_onboarding.py`'s
`test_init_picks_the_package_the_project_is_named_after` (`src/archkeel` beside
`src/tests_pkg`, `name = "archkeel"`), `test_init_stays_ambiguous_when_no_package_matches_the_project_name`
(`src/archkeel_core` beside `src/tests_pkg`, exit 2 naming both packages and the compared name),
`test_detect_source_matches_the_project_name_in_wheel_file_name_form` (the issue's flat layout,
with `archkeel_core`, `Archkeel-Core` and `archkeel.core`),
`test_detect_source_fails_closed_without_a_readable_project_name` (no file, invalid TOML, no
`name`) and the unchanged `test_init_asks_for_the_source_when_the_package_is_ambiguous`.

**AD-48 Reflection that writes, and a value compared with a string literal, are decided, not
only reviewed.** `forbidden_construct` gains five constructs. `setattr`, `delattr` and `vars`
are calls matched as written, bare or as `builtins.<name>`; `dunder_dict` is any `x.__dict__`
read, write or delete. `string_literal_compare` is named for what it checks, syntactically, in
exactly three forms: a comparison where `==` or `!=` has a `str` literal on one side; an `in` or
`not in` test whose right operand is a non-empty tuple, list or set literal holding only `str`
literals; and a `match` statement with a `str` literal value pattern at any depth of any case
(`case "a":`, `case "a" | "b":`, `case ["go", x]:`). It records once per comparison node,
however long its chain, and once per `match` statement, not per case, with `form` naming
`compare`, `membership` or `match`, the way `placeholder_body` records its spelling (AD-29). It
records a comparison wherever it stands, in an `if` test, an assignment or a `return`, so the
name promises the syntax, not the intent: whether the compared value is a closed vocabulary an
`Enum`, `StrEnum` or `Literal` should declare is the architect's call, made with `source` and
`allowed_sources`, and precision comes from that scoping, not from the construct.
`if __name__ == "__main__":` is excluded: it is the interpreter's entry protocol, the only
spelling Python offers, and no enum can replace it, so counting it would turn every script into
an `allowed_sources` entry that decides nothing. All five are records in the `constructs`
section, collected by `constructs.py` under the owner scope that `allowed_sources` matches, and
`violations.py` maps them the way it maps `assert`. Archkeel's `CONSTRUCT-NO-DYNAMIC` now also
forbids `setattr`, `delattr`, `vars` and `dunder_dict`, with zero hits in its own source; the
shop sample gains `CONSTRUCT-NO-STRING-LITERAL-COMPARE` and one probe per new construct (AD-11).
`ANALYZER_VERSION` rises to 0.22.0 (AD-3); the contract's `schema_version` stays 2.1.0 (AD-27).
Reason: a "typed attributes only" rule could forbid the read side of reflection, `getattr` and
`hasattr`, but not the write side, and a closed vocabulary spelled as string literals could not
be forbidden in any scope (issue #8); `allowed_sources` already exempts the parsers and
user-string handlers that must compare strings. Rejected: routing `setattr`, `delattr` and
`vars` through the call-target table `getattr` uses, which makes them typing signals. Every
typing signal is a typing position and a `typing_signals` guardrail fingerprint, so any new
`setattr` in any checked candidate would fail `check` where no rule names it, a guardrail change
nobody decided; AD-8 kept `assert` and `broad_except` out of `typing_signals` for the same
reason, and `string_literal_compare` there would raise Archkeel's own 48 typing positions to 229.
Keeping the name issue #8 proposed, `string_dispatch`, and restricting it to comparisons that
choose a branch: the test of an `if`, `elif`, `while`, conditional expression or comprehension
`if`, directly or under `and`, `or` or `not`, plus `match` statements. Measured by position,
Archkeel's 181 hits hold 151 branch tests and `datamimic_ee`'s 424 hold 387, so the restriction
removes few records; weighting the per-position rates of a 16-hit sample (5 of 10 branch tests
and 1 of 6 other positions were a real closed vocabulary) moves the estimated share only from about
44% to about 50%, because the false positives lie in what is compared, not where.
It is also easy to step around: `return status == "ready"` in a predicate and
`is_ray = mode == "ray"` before `if is_ray:` would escape it while the same comparison in an `if`
would not, and branch position needs parent tracking the collector does not have. The architect
chose the name that states the syntax (review of pull request 22). One record per `case`,
because a ten-way `match` is one vocabulary and would otherwise weigh ten times a single `==`.
Excluding further idioms such as the empty string, because the definition stays syntactic and
scoping belongs to `allowed_sources`. Limit: matching is as written. `f = setattr; f(...)`,
`from builtins import setattr as s`, `object.__setattr__(...)` and `operator.attrgetter` are not
seen, and a module-local function named `setattr` or `vars` is reported, the alias and shadow
blind spots AD-8 names. `getattr` and `hasattr` stay typing signals, so the reflection family is
split across two sections: a new `getattr` moves the typing guardrail and a new `setattr` does
not. `string_literal_compare` cannot see what a type checker sees, so it reports three kinds of
false positive: foreign names, such as Python's own dunders and identifiers read from an AST
(`"__init__"`, `{"self", "cls"}`) or a driver string (`"mssql+pymssql"`); parsing at a trust
boundary, where JSON or user text is narrowed into a type (`value == "architect"` returning a
`Literal`); and a value already typed as a `Literal`, where strict mypy already rejects a typo as
a non-overlapping equality check. It also counts `name == ""`, and it does not see a named
constant set (`x in NAMES`), a dict-literal or `frozenset(...)` membership test, a literal on the
left of `in` (`"a" in text`), `str.startswith` or a dict used as a dispatch table.
`x.__dict__.__dict__` is one record, for the inner node, because both nodes start at one column
and would share one record id. Archkeel does not apply `string_literal_compare` to itself: its
source has 181 hits, 167 comparisons and 14 membership tests and no `match`, in 37 of its 62
modules, led by `check/delta.py` (31), `ir/codec.py` (19) and `render/summary.py` (17). They
compare record kinds and statuses read from JSON, which AD-2 keeps as `RawJson`, and Python names
read from the AST; the CLI's 10 are the only share an argument-parsing `allowed_sources` entry
would cover, and exempting the other 171 would widen the contract to pass rather than decide
anything. Check: `tests/test_analyzer.py::test_collect_constructs_detects_reflection_as_written`
and `::test_collect_constructs_detects_string_literal_compare_and_its_exclusions` (each positive
form, the main guard, the excluded forms, and unique record ids), and
`::test_class_a_rule_produces_one_traceable_violation` with a reflection rule and a
`string_literal_compare` rule whose `allowed_sources` exempts `sample.cli`;
`::test_exact_sources_scope_the_package_root_and_nothing_below_it` and
`::test_forbidden_construct_declaration_records_every_exemption` carry the new constructs through
AD-49's `exact_sources`, in the verdict and in the declaration record;
`tests/test_contract_model.py` accepts all five constructs in both the parser and the schema
through `tests/contracts/valid/forbidden-construct-scoped.json`, and rejects the unreleased name
`string_dispatch` in both through `tests/contracts/invalid/construct-renamed-string-dispatch.json`;
`tests/test_architecture_demo.py` runs the five new `class-a-construct-*` probes;
`archkeel validate --root . --json` passes with the widened `CONSTRUCT-NO-DYNAMIC`.

**AD-49 An allowance may name its module exactly, so a package root is scoped on its own.**
`external_dependency_scope` and `forbidden_construct` gain an optional `exact_sources` list
beside `allowed_sources`: an `allowed_sources` entry still allows its name and everything below
it, an `exact_sources` entry only the name itself, compared by equality where the prefix form
calls `in_scope`. For `external_dependency_scope` the name is the importing module; for
`forbidden_construct` it is the owner scope a construct is written in, a module, class or
function, so an exact entry exempts that scope's own body and not the scopes nested in it. An
`external_dependency_scope` rule needs one of the two lists non-empty, so `allowed_sources` is no
longer required on its own. A contract that never writes `exact_sources` parses, validates and
evaluates as before. The declaration record of both rule kinds carries `allowed_sources` and,
when it is non-empty, `exact_sources`, so the report shows every exemption a rule grants;
`forbidden_construct` recorded neither before, although both are evaluated. `ANALYZER_VERSION`
rises to 0.21.0 (AD-3): a contract may now yield records no earlier analyzer could, and every
`forbidden_construct` declaration gains `allowed_sources`. Archkeel's own contract narrows four
allowances to the exact form:
`EXTERNAL-RICH-ARGPARSE-CLI` (`archkeel.cli`, a package root with `config`, `skill` and
`__main__` below it), `EXTERNAL-RICH-TERMINAL` (`archkeel.render.terminal`),
`EXTERNAL-PACKAGING-RUNTIME` (`archkeel.analyzer.runtime`) and `CONSTRUCT-NO-BROAD-EXCEPT`
(`archkeel.cli.main`, whose one broad handler sits in `main`'s own body). `CONSTRUCT-NO-ANY`
keeps both prefixes: its `Any` owners are function scopes below `archkeel.ir.codec`, such as
`archkeel.ir.codec._raw_object:value`, and `archkeel.analyzer.embedded` is a package. Reason: a
package root is a prefix of every module in its package, so allowing a dependency the root
imports allowed it everywhere below; datamimic CE's `datamimic_ce/__init__.py` imports `dotenv`,
and `complete_external_scope` (AD-28) then forced exactly that over-broad entry. Archkeel had
the same gap: `archkeel.cli` allowed `rich_argparse` in `archkeel.cli.config` and
`archkeel.cli.skill`, though only `archkeel/cli/__init__.py` imports it. Rejected: an entry
syntax such as `"datamimic_ce:module"` inside `allowed_sources`, because every reader of the
list, both evaluations, `rule_scopes`, the namespace check in `validate`, the declaration record
and the schema, would have to parse one encoding out of a string, and `:` already separates a
module from a name in `public` entries and an owner from its parameter in typing-signal
records. Naming the list `allowed_modules`, as the issue proposed, because a `forbidden_construct`
owner is often a function, not a module, and one name should read the same in both rules. A
per-rule `exact: true` flag, because one rule could then not allow a root exactly and a subtree
by prefix, and two rules for one dependency each report the imports the other allows. Changing
what `allowed_sources` means, because every existing contract would change meaning without a
diagnostic. Matching a construct by the module its owner is written in, found as the owner's
longest scanned-module prefix, because that attribution is ambiguous where a function and a
submodule share a name, and a function's scope as a prefix already names it. An
`exact_sources` on `forbidden_dependency`, whose `allowed_sources` already match exactly, since
two fields would then hold one meaning. Keeping `ANALYZER_VERSION` at 0.20.0 because a contract
without `exact_sources` would have yielded unchanged records, because the version names what the
analyzer can record, not only what older contracts produce. Limit: `forbidden_dependency.allowed_sources` stays
exact under its old name, so the same word means exact there and prefix in the other two kinds;
and the rule-without-subjects check reads each non-empty list of an `external_dependency_scope`
as its own side with `in_scope`, so an exact entry naming a directory without an `__init__.py`
but with scanned modules below it counts as present. Check:
`tests/test_analyzer.py::test_exact_sources_scope_the_package_root_and_nothing_below_it`,
`tests/test_analyzer.py::test_forbidden_construct_declaration_records_every_exemption`,
`tests/test_validation.py::test_exact_source_outside_namespace_is_a_diagnostic`,
`tests/contracts/valid/exact-sources.json` and
`tests/contracts/invalid/external-scope-without-exact-sources.json` in
`tests/test_contract_model.py`'s corpus and round-trip tests, and
`archkeel validate --root . --json` passing on the four narrowed rules; importing
`rich_argparse` from `archkeel.cli.config` is now a `rule.violated` finding.

**AD-50 An edge and an interface record who decided them, and the agent-decision count counts
them.** A `requires` entry gains an optional `decided_by`, and a component gains one that covers
its `public` list and defaults every `requires` entry that names nobody of its own.
`agent_decisions` stops counting rules alone: one decision is now one rule declaration, one
`requires` entry or one declared `public` list, at either level (AD-34), and the pair stays
`[agent, total]` so an existing consumer reads the same shape. A declaration nobody attributed
counts in the total alone, because the decision was still made; a component that declares no
`public` recorded no interface decision and adds nothing. The projected component record carries
`requires` as `{component, decided_by}` entries with the default already resolved, and its own
`decided_by`, so the count comes from `architecture.json` bytes alone like every other (AD-16),
and the top-level record shows the declared edges it never carried before. `init` marks each
`public` list it drafts `decided_by: "agent"`, the way it already marks the rules it drafts.
`ANALYZER_VERSION` rises to 0.23.0 (AD-3). Archkeel's own three contracts record
`decided_by: "architect"` on all twelve components, which covers eight top-level `requires`
entries, six inside ones and eleven `public` lists: every rule in them was already
`architect`-decided in the same commits, and the AD log carries each edge and facade (AD-4 for
`analyzer` → `ir`, AD-9 for `public`, AD-20 and AD-34 for the insides), so `validate` now reports
`agent_decisions [0, 41]` where it reported `[0, 16]` rules. Reason: in a target-first contract
most decisions are exactly these edges and interface entries — which direction is allowed, which
name is the facade — so the audit question "who decided this, and was it reviewed" could not be
answered for them, and an auto-mode agent could draft a whole `public` surface that no count ever
mentioned. Rejected: turning `public` entries into objects, which would break every existing
contract for a field most contracts write per module. A second component field such as
`public_decided_by` beside a `requires`-only default, because two fields would hold one idea and
an architect would have to write both for the common case where one person decided the whole
boundary. A per-entry `provenance`, because a component already carries a required `provenance`
list pointing at the document that holds its reasons, and a second pointer to the same document
is a second source of one fact. A separate `entry_decisions` counter beside `agent_decisions`,
because a reviewer would have to add the two up to learn what is owed, and the terminal line
would print either one number that understates or two that compete. Leaving unattributed entries
out of the total, because the denominator would then describe only the contracts that adopted
this field. Limit: an attribution is one field per component, so a `public` list decided by two
people records the one the architect writes, and only a `requires` entry can disagree with it; a
count is not a finding, so the reviewer still reads the contract to see which edge is which, the
way `decided_by` on rules already works; and nothing checks that a stated decider is true. Check:
`tests/test_decisions.py::test_agent_decisions_counts_requires_entries_and_public_lists`,
`tests/test_analyzer.py::test_component_projection_writes_who_decided_each_edge_and_the_public_list`,
`tests/test_decisions.py::test_agent_decisions_counts_one_flipped_rule_from_the_observation`
counting 46 where it counted 35,
`tests/test_onboarding.py::test_deciding_every_open_pair_from_init_options_makes_validate_pass`
reading init's drafted lists, and `tests/contracts/valid/decided-by-entries.json` with
`tests/contracts/invalid/requires-decided-by-unknown.json` in `tests/test_contract_model.py`'s
corpus and round-trip tests.
**AD-51 A result carries its violations grouped by rule and by crossed component pair.**
`ir.decisions.violation_counts` reads one observation's violation records and returns
`ViolationCounts`: `by_rule`, every rule id with at least one violation, and
`by_component_pair`, every ordered pair of components an import violation crosses, both
heaviest first and then alphabetical. `report` and `validate` carry them as
`violations_by_rule` and `violations_by_component_pair`, beside the `violations` scalar,
which keeps its meaning. Reason: measuring a refactoring needs one data point per change,
per rule and per component, and the only way to get it was to decode `architecture.json`
with the internal codec and count 25,000 rows, which is what a downstream repository did.
Deriving it from the records the result already carries makes the breakdown and the total
incapable of disagreeing. The pair comes from each record's `source_module` and
`target_module`, never from the position of a subject: `classified` sorts subjects, so
`DEP-STORE-NO-MONEY` would otherwise read as `model -> store` instead of `store -> model`.
A rejected `validate` run carries the counts too, because that is the run whose numbers a
gate reads. Rejected: listing every rule including those at zero was rejected because the
contract already lists them, while this answers what remains; counting a second time in the
renderer was rejected for the same reason `review_claims` is derived once (AD-35); a
per-component total beside the pairs was rejected as the sum of pairs plus what crosses no
pair, both already present. Limit: a violation that names no import, such as a construct, an
unassigned module or a cycle, crosses no pair and appears only under `by_rule`, so the pair
counts sum to less than the total; an import whose target module no component owns, such as
an external dependency, is counted by rule alone as well. Check:
`tests/test_decisions.py`'s
`test_violation_counts_group_the_report_by_rule_and_by_crossing_pair`, which pins both
breakdowns for the demo tour and that they come from the same records the result reports.

**AD-52 A violation is named by what it is, and a baseline may hold the ones already there.**
`ir.baseline` derives a `ViolationFingerprint` from a violation record: the rule ids it cites
and its `subjects`, which the analyzer already sorts and which hold module names, a construct
owner or the members of a cycle, by kind. No position enters it, so an unrelated line inserted
above a violating import leaves it unchanged, while the `VIO-` id beside it still moves. The
fingerprint does not replace that id. Violations sharing a fingerprint — two `getattr` calls in
one function — are counted rather than told apart. `validate --baseline <file>` reads a file of
those fingerprints with their counts, and reports only where the file and the code disagree: a
count the file understates is a new violation, one it overstates is a violation somebody fixed.
Both are `failures` with exit 1, and a run whose baseline is exactly right exits 0 with
`declared_rules: FAIL`, because the violations are still there and still reported. Only
`rule.violated` is answered this way; every other diagnostic still exits 2, as does a baseline
that cannot be read (`baseline.invalid`). `--write-baseline` writes the observed violations to
that path, and writes nothing from a run that exited 2. `validate` without `--baseline` is
unchanged, and so is every other command. Reason: a contract that states the target
architecture is contradicted by the code that has yet to reach it, so `validate` is red by
design and gates nothing; the workaround was to declare the debt edges as `requires` or
`allowed_dependency`, which makes the contract describe the code instead of the target and
lets a *new* import over such an edge pass unseen. A baseline keeps the target intact and
moves the debt into a file that shrinks. datamimic CE had built this outside Archkeel by
decoding `architecture.json` with `ir.codec.decode_canonical_model`, an internal module.
Rejected: replacing `VIO-` with the fingerprint, because the fact id is what ties a violation
to its evidence, and two violations may legitimately share a fingerprint. Hashing the
fingerprint into one opaque token, as `stable_id` does elsewhere, because this file is read
and widened in review diffs (#11), where `CONSTRUCT-NO-DYNAMIC | shop.model.probe.read` is the
whole point. Keying on the violation's `title`, because prose is not an identity. Failing only
on new violations while reporting resolved ones as information, because a budget allowed to
exceed the code lets a violation someone removed return unreported — the flaw of the
workaround this replaces; requiring exact counts makes the file state today's debt and makes
shrinking it part of the change that shrinks it. Storing the fingerprint as one delimited
string, because a component label may contain the delimiter. Keeping `ANALYZER_VERSION` at
0.22.0 is deliberate: the derivation reads records the analyzer already writes, and no record
changes. Limit: a fingerprint follows a rename of what it names — move the violating code to
another module, or rename the function around a `getattr`, and the entry reads as one
violation resolved and one new, which is honest but noisier than a diff would be. Two
violations of one rule that name the same subjects are one entry, so the file cannot say
*which* two. The file is compared, never authenticated: `check`'s digest chain does not cover
it, and nothing yet stops a change from widening it — that is #11. Check:
`tests/test_baseline.py::test_a_moved_violation_keeps_its_fingerprint`,
`tests/test_baseline.py::test_two_violations_in_one_function_share_a_fingerprint_and_are_counted`,
`tests/test_baseline.py::test_a_baselined_violation_passes_while_validate_alone_still_fails`,
`tests/test_baseline.py::test_a_new_violation_of_the_same_rule_in_another_module_fails`,
`tests/test_baseline.py::test_a_resolved_baseline_entry_is_reported`,
`tests/test_baseline.py::test_a_smaller_count_for_a_known_fingerprint_is_resolved_too`,
`tests/test_baseline.py::test_a_baseline_does_not_hide_any_other_diagnostic`,
`tests/test_baseline.py::test_a_missing_baseline_file_is_exit_two_with_a_diagnostic`,
`tests/test_cli.py::test_validate_baseline_writes_then_gates_on_new_violations` and
`tests/test_schema_drift.py::test_baseline_schema_accepts_what_the_writer_writes_and_the_parser_reads`.

<<<<<<< HEAD
**AD-54 A typed violation row is the one supported way to read a report's violations, and
`ir.baseline` derives it once for everything that groups them.** `ir.baseline.ViolationRow`
names one violation the way a consumer off disk reads it: `fingerprint` (AD-52's `(rules,
subjects)`), `source_module`, `target_module`, `symbol`, `source_component`,
`target_component` and `evidence_ids`; a field a violation kind carries no value for, such as
a forbidden construct's `source_module`, is `None`, never guessed. `rules` and `subjects` live
only on `fingerprint`, not repeated at the top level too: two copies of one value is one more
place for them to drift, so a caller reads `row.fingerprint.rules`.
`ir.baseline.violation_rows(observation)` derives one row per violation record, and both
`observed_violations` (AD-52) and `ir.decisions.violation_counts` (AD-51) now build on it
instead of their own loop over `observation.records("violations")`, so a baseline comparison
and a rule-and-pair breakdown can never disagree with a consumer's own rows about what a
violation is or which component pair it crosses. `ir.codec.load_observation(path)` reads one
`architecture.json` from disk and returns its `Observation`, composing `decode_json`,
`decode_canonical_model` and `parse_observation` so a consumer calls one supported function
instead of three internal ones against a columnar, string-interned file; `ir/digest.py`
already reads files to hash the installed package, so this is not the first I/O in `ir`, only
the first that reads a report a consumer supplies. Because that file may be hand-edited or
truncated, `ir.codec.parse_record` now rejects a VIOLATION record whose `rule_ids` is empty
with a named `ValueError`, closing a gap `schema/architecture-ir-common.schema.json` already
documented (`minItems: 1`) but nothing enforced at runtime: `violation_counts` indexes
`fingerprint.rules[0]` unguarded, on the correct assumption that every violation
`embedded.violations` produces carries one, and an untrusted file read back through
`load_observation` needed the same guarantee, checked at the boundary where the untrusted
bytes enter rather than papered over with a fallback where the value is used. Reason: issue
#12 - a CI gate reading `architecture.json` from a test had only `ir.codec.decode_canonical_model`,
an internal module, to get named fields from, the same gap datamimic CE hit before AD-52. The
issue's two suggestions were rejected: a new `archkeel.api` package would be a second,
undeclared public surface beside the `public` list this repository already has (AD-9), and a
third JSON shape for violations would compete with `violations_by_rule` and
`violations_by_component_pair` (AD-51), which the result already carries, and would let
`architecture.json`'s digest-bound bytes diverge from what a report promises. Rejected: a new
`ir/violations.py` module, because `ir.baseline` already derives what a violation is (AD-52)
and a fourth loop over the same records would be one more place for the three to disagree, not
fewer; repeating `rules`/`subjects` beside `fingerprint` on `ViolationRow`, an ergonomic
shortcut that would have let the two silently disagree, since nothing ties a dataclass field to
another one. `ViolationRow`, `violation_rows` and `load_observation` add nothing to any
component's `public` list: that list is AD-9's internal cross-component control, populated by
what another Archkeel component actually imports across a boundary, and nothing inside this
repository imports these three - only a consumer outside it. Adding them by hand would have
made `architecture-contract.json` diverge from `init`'s own drafted proposal, the SPOT guard
`tests/test_self.py::test_self_contract_public_matches_drafted_proposal` holds it to. What did
move: the two new names in `ir.baseline` dropped the share of its public names that another
component uses under half, so `init` now drafts `ir.baseline`'s entry as three symbols,
`KnownViolation`, `compare_violations` and `observed_violations`, instead of the whole module;
`architecture-contract.json` follows that draft exactly, as it already did before this change.
Limit: `load_observation` performs I/O, which `ir/digest.py` already did before it, so `ir`'s
"no I/O" reading in AD-17 always meant no I/O in a *derivation* over already-read evidence, not
a blanket rule this function breaks; both are entry points that read one file a caller names
and hand its bytes to the pure code beside them, nothing more. `ViolationRow` promises nothing
about the columnar file format itself, nor about any `ir` module's internals beside
`ir.baseline`, `ir.codec` and `ir.decisions`, which `architecture-contract.json` already lists
as public. Check: `tests/test_violations.py`'s
`test_load_observation_reads_the_canonical_report_bytes_back`,
`test_violation_rows_type_an_import_violation`, `test_violation_rows_leave_construct_fields_none`,
`test_violation_rows_fingerprints_agree_with_ir_baseline`,
`test_reference_md_snippet_reads_a_report_and_lists_its_rows` and
`test_load_observation_rejects_a_violation_with_no_rule_ids`, all against the `tour` demo
variant (AD-11) except the last; `tests/test_decisions.py::test_violation_counts_group_the_report_by_rule_and_by_crossing_pair`
and `tests/test_baseline.py` passing unchanged; `tests/test_self.py::test_self_contract_public_matches_drafted_proposal`
against the corrected `ir.baseline` entries; and `archkeel validate --root . --json` on
Archkeel's own contract.
=======
**AD-53 `from pkg import name` follows `pkg/__init__.py`'s own binding before a same-named
submodule.** `imports.collect_package_bindings` reads every scanned `__init__.py`'s unconditional
top-level statements once, before any module's imports are resolved, and records the names each
package binds to something other than the identically named submodule: a `def`, a `class`, an
assignment, an aliased import, or a `from` import naming anything else. `ImportCollector` now
prefers that binding over the submodule interpretation it used alone before: `from pkg import
name` reads as the name `pkg:name` when `pkg/__init__.py` shadows it this way, and as the module
`pkg.name` otherwise, the way `import pkg.name` already resolves. A
plain `from . import name` is read out of the shadow set on purpose, because that statement binds
the identically named submodule itself; over-correcting it into an attribute would misread the
ordinary submodule re-export idiom as its own shadow. `ANALYZER_VERSION` rises to 0.24.0 (AD-3).
Reason: CPython's `_handle_fromlist` checks `hasattr(pkg, name)` before it ever imports a
submodule of that name (issue #23), so a package that assigns, defines or re-exports a name
shadows its own submodule at runtime; the scanner read only the submodule's existence and got
`interface_boundary`'s subject and `dependency_edges`' target wrong whenever the two collided,
an accident CPython treats as ordinary shadowing. Rejected: resolving this per module instead of
once up front, because a module can import from a package the scanner has not visited yet, and
`collect_package_bindings` already costs the cheapest possible pass, one walk of each
`__init__.py`'s own top-level statements; reusing `symbols`, because it never records a plain
assignment; reusing `bindings`, because it answers a different question, an unused function-scope
local rather than a module-scope shadow; expanding a star import inside `__init__.py` to decide
the names it introduces, because that reaches into a second module's exports for one case the
issue does not ask for. Limit: a `__getattr__` or a star import in `pkg/__init__.py` still makes
every one of its attributes undecidable, and the scan keeps the submodule-if-it-exists reading
for the whole package there, which is `docs/rules.md`'s narrowed #23 blind spot; a name bound
inside `if`/`try` is not seen either, matching `literal_all_exports`. Check:
`tests/test_analyzer.py::test_from_import_binds_the_package_attribute_over_a_same_named_submodule`,
`tests/test_analyzer.py::test_from_import_of_a_re_exported_submodule_still_resolves_to_the_submodule`,
and `fixtures/demo_catalog_interfaces.py`'s
`class-a-interface-boundary-package-attribute-over-submodule` row, where `shop.store`'s own
`sqlite` attribute makes `shop.app`'s crossing an `INTERFACE-BOUNDARY` violation instead of the
`DEP-APP-NO-STORE-SQLITE` forbidden-dependency violation the old resolution produced on the
untouched submodule.
>>>>>>> origin/main

## Allowed dependencies

| Edge | Reason |
|---|---|
| `cli` → `analyzer` | Supply the concrete, replaceable source analyzer to report and check workflows; `cli` composes, it does not analyze. |
| `cli` → `check` | Invoke deterministic and stable report and check services from the composition root. |
| `cli` → `host` | Supply the concrete, replaceable host-record loader to checks; `cli` composes, it does not fetch. |
| `cli` → `render` | Project typed results through the replaceable render adapter, keeping `cli` a thin composition root. |
| `analyzer` → `ir` | Publish observations through the common model and codec boundary, so `analyzer` stays isolated behind its digest. |
| `check` → `ir` | Compare observations and return typed results without losing determinism or stability. |
| `host` → `ir` | Construct validated host-record values through the stable evidence model, so `host` stays replaceable behind it. |
| `render` → `ir` | Render typed evidence without importing policy implementations, so `render` stays replaceable behind the stable model. |

<!-- archkeel-component-graph -->
```mermaid
flowchart LR
    analyzer --> ir
    check --> ir
    cli --> analyzer
    cli --> check
    cli --> host
    cli --> render
    host --> ir
    render --> ir
```
