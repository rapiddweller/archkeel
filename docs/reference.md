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

Version 4.0.1 expands the TypeScript profile with optional PARTIAL construct
evidence. The 3.0.1 Core/report reader rejects that receipt, even though SourceFacts
and protocol remain 3.0.0 and ArchitectureIR remains 2.0.0. Upgrade the package,
collectors and strict profile consumers together, then re-observe both comparison
revisions. Current readers retain legacy TypeScript receipts. See the
[4.0.1 upgrade notes](../RELEASE_NOTES.md#upgrade-from-301).

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

`bundler = true` (TypeScript only, default false) treats imports that a bundler
resolves as known: tsconfig `paths` aliases (not `baseUrl`-only matches), package
`exports` and `typesVersions` (an external edge to the package), and asset and JSON
imports whose file exists (an external edge to the reserved package `bundler:asset`;
a bare-package asset is an edge to its package and must lie inside it, without `.` or
`..` segments; `.` and `..` imports count as relative). It needs `compilerOptions.moduleResolution`
`bundler`; otherwise the scan records a gap and stays UNKNOWN. An active scan carries
the resolution feature `bundler-mode-v1`. The trade-off: it asserts that the bundler's aliases
equal tsconfig `paths`, which is not verified. See
[AD-260](architecture/decisions/ad-260-typescript-bundler-mode.md).

For supported UMD vendors, the `tsconfig` extension `archkeel` declares
`scriptHost: "classic-browser"` and `scriptProviders`, each with `source` and
`provenance` paths relative to `--root`. See the
[provenance example](../src/archkeel/render/assets/ELKJS-LICENSE.md).
Provenance records the package, version, bundle SHA-256 and license; the hash binds
the exact bundle bytes. Publication identity does not bound factory effects: unproved
calls or constructors leave standard-global and vendor dependencies UNKNOWN.
Missing, invalid or competing evidence stays UNKNOWN.

Named ES imports can prove exact local ports when the destination has one witnessed
runtime declaration and a direct or same-name export. Import aliases retain that
source identity. Defaults, namespaces, re-exports and ambiguous/missing bindings
remain unproved for exact ports. Global reads in modules retain UNKNOWN when their
binding cannot be established. This establishes a source dependency, not runtime
immutability or dispatch. ArchKeel's [browser configuration](architecture/browser.tsconfig.json)
uses these explicit ports; [AD-242](architecture/decisions/ad-242-explicit-browser-module-ports.md)
describes its offline publication checks.

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

Collector stdout defaults to a finite 64 MiB limit; protocol 8.0.0 replies are
zlib-compressed, so the limit counts compressed bytes and the decompressed size is
bounded at 16 times the limit. Large valid scopes may set
`collector_output_limit_bytes = 268435456` (256 MiB) in `[scan]`. The value must
be a positive integer; it changes transport capacity, not source scope or protocol
validation. Larger replies also require more memory to decode and assess. Existing
configurations retain the default; stderr and execution time remain bounded.
For a new setup, `archkeel init --collector-output-limit-bytes 268435456` uses that
limit for initialization and saves it in the generated config. `report`, `validate`
and `check` use the configured limit; `check` binds it to the accepted config like
the other scan inputs. See [AD-224](architecture/decisions/ad-224-configurable-collector-output-limit.md).

The collector deadline defaults to 300 seconds. A large repository that times out may set
`collector_timeout_seconds = 900` in `[scan]`; the value must be a positive integer no larger
than the platform's thread timeout limit. It changes only how long a collector may run; a
timeout still exits without a complete observation. `archkeel init --collector-timeout-seconds 900`
saves the same value, and `report`, `validate` and `check` use it like the output limit.

SourceFacts 3.0.0 introduced neutral list type syntax for explicit callback arguments.
Readers retain 1.0.0/2.0.0 packets; those versions reject that list vocabulary,
including nested shapes. Runtime `requirement_state` is required from SourceFacts
2.0.0 onward. At that migration, ArchitectureIR/Delta remained 2.0.0 and
command-result used 8.0.0. See [AD-223](architecture/decisions/ad-223-explicit-callable-boundaries.md).

### Current wire formats

The bundled Python provider collector uses **SourceFacts/protocol 4.0.0** for its
provider-source survey and **5.0.0** for full collection. V5 keeps the V4 facts and
provider fields while carrying records and evidence as canonical compact rows with
lossless string references. Decoders expand V5 before the same strict facts validation.
Source bytes, digests and inputs are checked across passes within one collector deadline;
project modules are parsed, not imported. The generic request default remains **3.0.0**.
Known legacy 1/2/3/4 packets remain readable; older protocol versions reject V5 packets.

New **ArchitectureIR 2.1.0** Python call records require `call_binding`: a validated
binding object or explicit JSON null when unproved. Omission is invalid. Existing
call-graph candidates remain separate from this ownership evidence. Strict command
consumers need **command-result 9.0.0**, which also accepts supported historical
observations. Command schemas 6/7/8 reject 2.1 observations; older reports remain
readable under their supported profiles. Delta remains **2.0.0** and still requires
comparable observations.

These evidence/protocol changes require a new package major under the compatibility
policy above. Pin CLI, collectors and schemas together, and re-observe both revisions
before comparing them. Historical reports do not acquire missing proofs on replay.

The internal `FilesToWrite` port now stores immutable ordered
`entries: tuple[tuple[str, bytes], ...]`, replacing its Mapping interface. Construct
`FilesToWrite(entries=(("path", content),))` and iterate `files.entries`; the caller
still owns writes. Documented `archkeel.api` exports retain their interfaces.


## Contract guide

`archkeel guide` reads the root contract and writes
`docs/architecture/contract-guide.md` under `--root`, or the path given by `--output`.
It needs no source scan, reads nothing else and never changes the contract. The file
is generated: it has no dates or commit hashes, so the same contract gives the same
bytes. Regenerate it after a contract edit instead of editing it.

`archkeel guide --check` writes nothing. It exits 1 and names the file when the file
is missing or differs from what would be written, so CI can keep it fresh. Without a
contract, `guide` exits 2 and says to run `archkeel init` first. The guide says
which dependency permissions are declared, and it counts decisions by `decided_by`.
That count is recorded metadata, not verified approval; the guide does not observe
imports and gives no verdicts.

## Explore without a contract

`archkeel explore [--root PATH] [--output DIR]` shows a repository that has no ArchKeel file
([AD-285](architecture/decisions/ad-285-explore-without-a-contract.md)). It finds the one
top-level Python package as `init` does, or reads the `init` options `--language`, `--source`,
`--namespace` and `--tsconfig`, and groups the modules by the package layout. A Python component
of more than 40 modules opens one level deeper, one child per direct subpackage, down to four
levels. On a complete scan, an undeclared Python range is a coverage note in `notes`, not exit 2
(`report` still exits 2). It writes
`architecture.json` and the report pages to `DIR`, or else to
`$XDG_CACHE_HOME/archkeel/explore/<root_digest>/` (`~/.cache` when the variable is not set). It
writes nothing into the repository, and an `--output` inside it exits 2. The result is a
`report` result with `target: unavailable`, `declared_rules: UNKNOWN`, `root_name` and
`root_digest`. The report page opens
with an inventory of the components before the findings. Query the snapshot like any other:
`archkeel report --input DIR/architecture.json --only architecture --component COMP-APP --json`.
TypeScript and Dart need the scope options. `validate` on a contract with no rule keeps PASS:
the contract is valid, and no rule was checked.

## Studio

`archkeel studio [--root PATH] [--no-open] [--stop] [--idle-exit MINUTES] [--agent claude|codex]` serves ArchKeel Studio,
a local web app, on 127.0.0.1 and opens it in the browser. It takes the scope options of `explore`
and passes them on
([AD-290](architecture/decisions/ad-290-archkeel-studio-is-a-local-web-application.md)). The
printed URL carries a token for this run; a request without it gets 403. At start, Studio runs
`archkeel explore` on the root into a private folder of this run below the explore cache.
Overview shows the progress. When the snapshot is done, Studio opens on the Map:

- **Four levels.** One navigation item, "Architecture", holds all four (Impact and Target / Diff
  show as "Planned" and are not links). The URL names the level. Each level has the same page: a location bar,
  a toolbar, a canvas, a structure tree and a side panel that starts with "You are here" (name,
  counts, what a card means) and an Up link. The location bar shows the architecture, the
  component, its packages, the module file and the function; each part is a link that goes up
  to its level. Esc goes one level up, Enter opens the focused card. A drill zooms in from the
  clicked card (250 ms; none with reduced motion), going up zooms out.
  - **Map** (`#/map`): the components as a dependency graph of the measured calls. Three bands,
    by net call flow: callers on the left, foundations on the right. A line is the sum of the call
    sites between two components; its width grows with the logarithm of the count. A line is
    `proven` only when it holds no claim; a line with a claim is dotted and shows both counts, for
    example `3 ✓ proven · 2 ✎ claim`. A call site counts once, also when a partly resolved call
    has two candidate targets. The header says where the components come from: `declared by the
    contract` (the first `responsibilities` entry shows on the card) or `observed package layout`
    (the top-level packages of the explore layout; also when the contract does not load). A click
    on a line or a count lists the calls behind it; a click on a card opens the component.
  - **Component** (`#/component/<n>`, also `/<package>`): the modules of the component as cards on
    plates by package. The page is calm: no line at rest. Hover a card to draw the lines of that card
    (its callers and callees, in the gutters between the cards, proven solid and claim dotted) and
    to dim the other cards; a click pins the focus, Esc clears it. The side panel lists each
    connected card with its module, file, line and proof. Stubs at the sides are the other
    components that call into it (left) and that it calls (right), each with its count and, while a
    card has the focus, the functions on the other side; a click on a stub opens that component. On a
    package of the component, the other packages of the component are stubs too. A focused line ends on
    its card with a port dot, and a dot runs along it from the caller to the callee (a chevron with
    reduced motion). At rest each stub has one faint line to the nearest plate. A
    double click or Enter on a module card opens the module. A package that does not fit the first
    screen is one tile that opens it.
  - **Module** (`#/module/<n>`): the functions of the module as cards and the other modules that call
    in or are called as stubs, grouped by module. The focus works as on the component level. A double
    click or Enter on a function opens the lens.
  - **Explore** (`#/explore/<function>`): the lens around one function: callers on the left,
    callees on the right, unknown calls below, one hop. Cards of one module share a plate. A
    large neighborhood folds into package groups. The search (Cmd/Ctrl+K) opens the lens at any
    function. Drag pans, the wheel zooms, Fit fits. Module-level calls are not shown, so "Called
    by 0" is no proof of no caller. A call to a target outside the scan (for example the standard
    library) is counted apart: it is neither an edge nor unknown. The unknown count of a function
    is the true count; the lens lists the first 4.
  A card never shows text across its border: a long name ends in "…" and the full text is in the
  tooltip and the side panel.
- **Stories**: the player of a checked story ([AD-291](architecture/decisions/ad-291-a-story-is-a-checked-view-and-the-trace-proposes-its-path.md)).
  A spec is a `*.story.json` file in the `stories` folder below the explore cache folder of the
  root. Studio runs `archkeel view check` on it against the snapshot of the run. Each step is a
  card in the lane of its component; one route line joins the steps and a dot marks the order. A
  step is `✓ proven`, `✎ claim` or `? unknown`; a partial call shows its candidate count. The
  side panel has the author text (a claim), the evidence (file and line), the external systems
  (the touchpoint is observed, the direction is a claim) and the question. Keys: arrows and space.
  With reduced motion, Play shows the final state.
- **Ask**: a chat panel in the Map and the lens. A reply has three kinds of block: `✎ CLAIM`
  (agent text), `◌ PROPOSED - NOT APPLIED` and `✓ OBSERVED` (made by Studio from the snapshot).
  A reference opens the lens. "Pin to story" shows a draft spec of the traced path; Studio
  writes no file.
- **Static report** (a link at the bottom of the navigation): the Explorer page of `archkeel explore`,
  the artifact that CI and Pages publish. It keeps its own look, so it is not part of the workspace.

A call has one of three statuses, each with a glyph and a word: `✓ proven` (resolved call),
`✎ claim` (partly resolved call), `? unknown` (no target found). Studio shows no verdict and no
agent text outside the chat. The API (`GET /api/v1/state`, `GET /api/v1/graph`, `GET /api/v1/stories`, `GET /api/v1/stories/<id>`, `GET /api/v1/draft` and `POST /api/v1/chat`) follows
[studio-api-1.1](../schema/studio-api-1.1.schema.json); the graph answer is `graph: null` until
the run is done. The 1.0 file stays. Studio writes nothing into the
repository. It is parallel to the static report, which stays the CI and Pages artifact.

The chat route ([AD-292](architecture/decisions/ad-292-the-studio-chat-lets-the-owners-agent-answer-read-only.md))
lets your own coding agent answer a question about a selected function. Studio starts it as one
child process in the root, on your own sign-in, and passes no API key. The default is `claude -p`
with the tools `Read`, `Grep` and `Glob`: no shell, no write tool. `--agent codex` is an opt-in:
`codex exec --sandbox read-only` also runs shell commands of the model, can read the whole disk,
and gets only a short allow list of environment variables. Studio never falls back to the other
agent. The files an agent reads go to its provider.
- The pages under `/files/` carry `Content-Security-Policy: sandbox allow-scripts`: an Explorer page
  has an opaque origin and cannot call the chat route or read the parent page.
- Request: `{"question": "...", "context": "<qualified name>"}` (JSON, at most 16 KiB; `context`
  is optional). The header `X-Archkeel-Studio` must be present and `Origin` must be the server.
- Answer: `blocks` of agent text (`claim` or `proposal`), `facts` that Studio computes from the
  snapshot (file, line, resolved callers and callees, unknown calls) and `dropped_refs`. Show `text`
  as plain text. Only
  Studio makes a fact; agent text is never OBSERVED. A proposal reads `PROPOSED - NOT APPLIED`.
  Nothing applies it.
- Limits: one question at a time (409), 180 s, 128 KiB of output. Studio compares
  `git status` of the root, with size and mtime of the listed files, before and after the run. If
  they differ, it discards the answer (502 `repository_changed`); the edit may stay on disk. Errors are `{"api_version", "error", "detail"}`.

A running server writes `studio.json` (pid, URL with token, port, root, start time) into the
explore cache folder of the root, with mode 0600. It removes the file when it stops.

- A second `archkeel studio` for the same root prints `ArchKeel Studio: <URL> (already running)`
  and starts no second server. It reuses the server only if a request to the stored URL gets the
  Studio login redirect (303 with the cookie `archkeel_studio_<port>`). A live pid is not enough.
  The scope options of the first start stay in force.
- `archkeel studio --stop [--root PATH]` sends SIGTERM to a server that passed the same check,
  waits up to 15 seconds until its URL stops answering and prints `ArchKeel Studio: stopped.`.
  Without a verified server it deletes a stale file (only if it still holds the pid that it read)
  and prints `ArchKeel Studio: not running.`. The command can return while the server still
  unwinds its explore child.
- SIGTERM and Ctrl-C stop the server the same way: the explore child unwinds and the file goes.
  Windows ends the process at once on `--stop`, with no cleanup: the file is deleted by `--stop`,
  but the explore child and the `studio-*` folder of the run can stay behind.
- `--idle-exit MINUTES` stops the server when no HTTP request came for that time. The default 0
  means never. Only requests count. A running Explore does not keep the server alive; the open
  page polls the state, and each poll is a request.
- An agent starts it with `--no-open --idle-exit 60` in the background; see the `explore` skill.

## Checked views

`archkeel view check <spec> [--snapshot architecture.json] [--json] [--strict]` checks a view
spec against one saved report ([AD-284](architecture/decisions/ad-284-studio-shows-views-as-checked-data.md)).
It reads two files and writes nothing. [`schema/view-spec.schema.json`](../schema/view-spec.schema.json)
defines the spec; [`fixtures/F-architecture-view/place-order.json`](../fixtures/F-architecture-view/place-order.json)
is an example.

1. Run `archkeel report` to write the snapshot.
2. Copy `source.source_digest` and `contract.digest` from it into the spec `snapshot`.
3. List each node: a top-level component id, such as `COMP-APP`, or a module name.
4. Add edges and steps. Set `"claim": true` on each one you cannot prove from the snapshot.
5. Run `archkeel view check flow.json --snapshot build/architecture.json`.

The result gives each node, edge and step one status: `proven` (observed, with record ids,
evidence ids and source lines), `declared` (a component or a `requires` entry of the contract),
`claim` (author text, not checked), `unknown` (the snapshot cannot decide) or `missing`. A
step is proven only by one direct edge of its kind: structure, not runtime order. Without a
direct edge the step is `missing`, or `unknown` under a coverage gap; add the nodes between
as steps. A spec with another snapshot identity is not checked. The check runs the same
snapshot validation as `report --input`.

Exit 2 prints one of two JSON documents:
- The spec names another snapshot: the check result, with `snapshot_current: false` and each
  reference `unknown`. [`schema/view-check.schema.json`](../schema/view-check.schema.json)
  defines it, as for exit 0 and 1.
- The spec or the snapshot cannot be read or is invalid: a command result with
  `"command": "view"` and one diagnostic. Its `subject` names the file that failed.

`archkeel view show <spec> [--snapshot architecture.json] [--output DIR] [--json] [--strict]`
prints the same result and draws it in the Explorer
([AD-287](architecture/decisions/ad-287-the-explorer-draws-a-checked-view.md)). It writes
`architecture.report.html`, its detail pages and a copy of the snapshot to `DIR`, by default
`$XDG_CACHE_HOME/archkeel/view/<16 hex of the hash of both snapshot digests and the spec>/`.
Stderr names the page. A run first removes the files it writes in `DIR`; Archkeel owns them.
The page opens on the checked flow: numbered steps, each edge with its status as text and icon,
and the evidence in Details. `?flow=1&step=2` in the URL opens the same picture; `view=diagram`
without `flow` opens As-Is.

A spec with `"schema_version": "1.1.0"` can list `stops`: a tour for the first contact with a
codebase ([AD-289](architecture/decisions/ad-289-a-tour-shows-author-stops-beside-measured-facts.md)).
A stop has `node` (one of `nodes`), and an optional `title` and `note`; it takes no `kind`. The
check gives each stop its node status and `facts` from the snapshot: the module count, the
import pairs out and in with evidence, a `gap` when a count is a lower bound, and the violation
and unknown records of the node. An `unknown` or `missing` node has no facts. A page with stops
opens the tour at stop 1: an Author block and a Measured block side by side, with Previous and
Next. `?tour=3` opens stop 3; `?flow=1` opens the flow. An incomplete scan is drawn too: its gaps show as unknown. When the
check does not run (exit 2), the command writes nothing. A snapshot without an Explorer prints
the check result, writes nothing, says "not drawn" on stderr and exits 2.

## Stories

A story explains one flow through the code. ArchKeel proposes the path and proves each step. You
write only the words ([AD-291](architecture/decisions/ad-291-a-story-is-a-checked-view-and-the-trace-proposes-its-path.md)).
The `explain-flow` skill gives an agent the same steps.

`archkeel story trace --from NAME [--to NAME] [--snapshot architecture.json] [--max-paths N] [--max-hops N] --json`
reads a saved snapshot and prints candidate paths over its call graph. `NAME` is the qualified name of a
function or method. [`schema/story-trace.schema.json`](../schema/story-trace.schema.json) defines the result.

- With `--to`, it lists simple paths. Paths over resolved calls come first, then paths that cross a seam.
  Shorter paths come first. Without `--to`, it follows resolved calls only and lists the farthest functions.
- A hop is `proven` (a resolved call, with each call site) or `claim` (a partial call: the analysis lists
  `candidates` and does not prove the target; its call sites carry `candidates`). An unresolved call,
  a call through a re-export and a partial call with more candidates than listed are seams of their function.
- Each function has its `lane` (the contract component, else the second name of its module), its
  `defined_at` line and the external systems whose client library its module imports. The catalog is:
  redis, sqlalchemy, pymongo, boto3, botocore, minio, azure.storage, kafka and pika.
- `complete: false` means only that the path search stopped at its work limit (200,000 steps). It
  says nothing about the call analysis. `--max-hops` is at most 100; a larger value is exit 2.
- No path is `"paths": []` with exit 0. A name that is no function of the snapshot is exit 2.

To tell the story, write a view spec with `"schema_version": "1.2.0"` and a `story`:
`id`, `title` and `chapters` (`id`, `title`). Each step can add `chapter`, `title`, `question`
and `external` (`system`, `direction`). The step `note` is the story text. These fields are author
text. A node can be a function or a method. `archkeel view check` then adds, for each step, the
status and call sites as for any step, and a `story` block with the `lane`, `defined_at`, `seam`
and external `touched` systems of each step by `index`, and a `verdict` of counts. A partial call
is `claim`; it does not fail `--strict`, and its call sites carry `candidates`. An unresolved call, a
module call gap or the dynamic call limit makes a step without a call `unknown`. A process boundary is not detected: use
`"claim": true`. A spec of version 1.0.0 or 1.1.0 cannot have a story, and its result is unchanged.
A stored story lies in `<root>/.archkeel/stories/<id>.story.json`; commit it like documentation. Studio
lists that folder (mark `repository`) and the local cache folder (mark `local`); the repository wins on
an equal id. Studio checks the spec against the current snapshot by node name: the digests of the spec
are replaced in memory, and a node that is gone is `missing`. The optional text fields `created`,
`git_head`, `author_kind` (`agent` or `human`) and `agent` of a 1.2.0 spec say where it comes from.

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
| `explore` | Observation complete; no rule verdict | — | No single Python package, no Git commit, output inside the root, or incomplete coverage |
| `init` | Draft written | — | Draft unavailable |
| `skill install` | Instructions written | — | Target could not be updated |
| `guide` | Guide written, or `--check` up to date | `--check`: missing or different | No contract, or it cannot be read |
| `view check` | No reference is missing (`--strict`: or unknown) | A reference is missing (`--strict`: or unknown) | Invalid spec or snapshot, or another snapshot |
| `view show` | As `view check`; pages written | As `view check`; pages written | As `view check`, or no Explorer for the snapshot; nothing written |
| `story trace` | The trace ran; no path is an empty list | — | Invalid option, snapshot or name; the name is not a function of the snapshot |
| `studio` | Stopped (Ctrl-C, SIGTERM, `--idle-exit`), reused, or `--stop` done | `--stop`: still running after 15 s | The server could not start |

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
Rule and `requires` rationale checks (`rationale.placeholder`, `rationale.repeated`) also
apply to root and mounted contracts; a mounted diagnostic carries its contract path.

JSON null means unavailable/inapplicable; an empty list means measured empty.
Pin CLI and [command schema](../schema/command-result-11.0.schema.json) together.
Version 11 adds `findings` to an unfiltered `report` (see below) and `target: unavailable`
to a report whose observation declares no rule and no UML target. It retains 10.0, which
adds `contract_changes`. Version 9 accepts ArchitectureIR 2.1 observations with strict call-binding shapes
and retains supported version 6/7/8 results. Incomplete reports may preserve a
traceable FAIL while
coverage stays UNKNOWN/FAIL; they cannot claim PASS.
Ignore unknown result properties; required fields and enum meanings remain strict.
Schema shape validation proves neither authenticity nor conformance.
`report`/`check --output` also write `.report.html`/`.check.html` companions.

### Ranked findings

An unfiltered `report` opens with one verdict line and one ranked list of findings. The
terminal's top five, the HTML list (five shown, the rest behind "Show all") and `findings`
in `--json` read the same list
([AD-258](architecture/decisions/ad-258-report-opens-with-ranked-findings.md)). Each
finding has `kind`, `rules`, `subjects`, `size`, `title`, `sentence`, `locations` and
`component_ids`. The order is fixed and every threshold already existed:

| Order | `kind` | `size` |
| --- | --- | --- |
| 1 | `violation`: one per rule set and subjects, as in a baseline | occurrences |
| 2 | `module_cycle`, then `package_cycle` (roll-up only, no module cycle backs it) | import edges |
| 3 | `fan_in_hub`, `fan_out_hub`: at least 10, top 3 per level, 10 in total | the fan |

Within a kind, findings sort by size, then by subject name. A module cycle that a
module-level `no_component_cycles` rule already reports as a violation is listed once.
`change` and `before` are absent: nothing compares revisions yet, and absence never means
"new". `findings` is absent from filtered reports and from other commands, which is not an
empty list. An empty list means measured empty; absent means not ranked.

An incomplete observation ranks what one piece of evidence proves
([AD-272](architecture/decisions/ad-272-rank-what-an-incomplete-observation-proves.md)):
violations with a complete trace and cycles whose every step has an import site. It ranks no hub,
because a missing import lowers a count. The page and the terminal then say so and name the
number of coverage failures. With nothing proven, `findings` is absent. The states, the sentences
and the equivalence classes are in [findings-path](architecture/findings-path.md).

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

## Phase timings

`archkeel report --timings PATH` writes one JSON file after a successful live report.
Without the flag, nothing is measured and nothing is written. The report, the HTML
pages and the `--json` result do not change. `--input` refuses the flag.

```json
{"schema_version": 1, "phases": {"collect": 0.412}, "counters": {"files_parsed": 160}}
```

Keys are sorted. Seconds have three decimals. A phase that did not run is absent. A
failed run writes no file. Only the Python run measures `providers`.

| Name | Kind | Meaning |
| --- | --- | --- |
| `providers` | phase | Python survey pass, including its process |
| `collect` | phase | Collector process |
| `decode` | phase | Decode and validate the collector response |
| `assemble` | phase | Build the observation from the collected facts, including UML graphs and checks |
| `result` | phase | Rule results and the report result |
| `encode` | phase | Canonical `architecture.json` bytes |
| `render` | phase | Both HTML pages |
| `files_parsed` | counter | Source files parsed |
| `modules` | counter | Module records |
| `calls_analyzed` | counter | Calls in the coverage record; absent when unknown |
| `records` | counter | Records in all observation sections |
| `evidence_records` | counter | Evidence records |
| `collector_wire_bytes` | counter | Collector response bytes, from the clocked pass only |
| `architecture_bytes` | counter | `architecture.json` bytes |
| `report_page_bytes` | counter | HTML page bytes |

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

Plugins reuse the CLI skill. New [GitHub releases](https://github.com/rapiddweller/archkeel/releases)
include `archkeel-plugin-<version>.zip` and its SHA-256 checksum. The ZIP contains
both plugin manifests and the canonical skill; install the CLI separately.
The repository root is the plugin: `.claude-plugin/marketplace.json` and
`.agents/plugins/marketplace.json` list it with `source ./`. Directory listing and
host activation remain separate acceptance steps.
