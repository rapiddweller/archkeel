# Archkeel reference

## State of `main`

The Rust core `archkeel-core` is the only decision path on `main` (AD-432, issue #880).
The Python engine is deleted. The shell reads the arguments, starts the core and prints its frame.

| Command | On `main` |
| --- | --- |
| `validate`, `report` | Served by the core, as text or JSON. See [the core path](#the-core-path). |
| `skill install claude\|codex` | Served by the shell. It writes the skill file. |
| `init` | Served by the shell: drafts `archkeel.toml` and a contract for a Python project with one top-level package ([guide](onboarding.md), AD-626). |
| `check` | Typed refusal, exit 2. Release 4.0.1 has it. |
| `explore`, `guide`, `story`, `view`, `studio` | Typed refusal, exit 2. No release has them. |

`main` supports Rust and TypeScript projects, and the import rules of Python (AD-450) and Dart (AD-468) projects.
A config without `language` selects the Python profile. There is no partial PASS.
Interactive reports, `architecture.json`, saved reports, focused reports, amendments and
`--write-graph` are not on `main`. The shell refuses each of their options by name with exit 2.
`validate --baseline` and `validate --write-baseline` are on `main` ([baselines](#baselines)).

Release 4.0.1 has the Python engine: `check`, `init`, full reports and baselines for Python,
Dart and TypeScript projects. It has no Rust profile, `explore`, Studio, stories or views. The Explorer and Studio browser assets are
not in the tree on `main` (AD-582); they return with the port of `explore` and Studio to the core (5.1).
Its documents are at the [tag 4.0.1](https://github.com/rapiddweller/archkeel/tree/4.0.1/docs).
This page and [known limits](known-limits.md) describe `main`.

## Configuration

[The schema](../schema/archkeel.schema.json) defines `archkeel.toml`:

```toml
[scan]
roots = ["src"]
namespace = "app"
contract = "architecture-contract.json"
```

One run covers one namespace. Roots are repository-relative, nonoverlapping and
not globs. Optional `language` is `rust`, `typescript`, `python` or `dart`; a missing value
selects `python`. A Dart run refuses `exclude_test_sources`. TypeScript also uses `tsconfig`; roots may be files or directories.
Inputs must exist inside `--root`.

An explicit component `inside` mounts a child contract over the same scan. Its path is
relative to `--root`, not to its parent contract. `validate` and `report` read all mounts
through the core. Labels and rule IDs are mount-qualified; each mount keeps its own source domain.
The shell checks the SHA-256 of every contract file. A changed, linked, missing or unsafe
nested file cannot produce PASS. See [nested intent](rules.md#nested-and-independent-intent).

`exclude_test_sources = true` (default false) leaves recognized test sources out of the scan
of `report` and `validate`. File counts and verdicts then cover production code only, and the
result has a note that says so. An import from production code into a test source stays UNKNOWN.

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
[provenance example](https://github.com/rapiddweller/archkeel/blob/4.0.1/src/archkeel/render/assets/ELKJS-LICENSE.md).
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

`report` and `validate --config PATH` select a root-relative file. Each language runs its own
collector inside the core. A scan with `collector_argv` gives at most UNKNOWN, because an external
collector cannot prove a rule ([AD-344](architecture/decisions/ad-344-only-a-producer-that-the-host-trusts-can-give-pass.md)).

Collector stdout defaults to a finite 64 MiB limit; protocol 8.0.0 replies are
zlib-compressed, so the limit counts compressed bytes and the decompressed size is
bounded at 16 times the limit. Large valid scopes may set
`collector_output_limit_bytes = 268435456` (256 MiB) in `[scan]`. The value must
be a positive integer no greater than `sys.maxsize // 16`; it changes transport
capacity, not source scope or protocol validation. Larger replies also require
more memory to decode and assess. Existing configurations retain the default;
stderr and execution time remain bounded.
See [AD-224](architecture/decisions/ad-224-configurable-collector-output-limit.md).

The collector deadline defaults to 300 seconds. A large repository that times out may set
`collector_timeout_seconds = 900` in `[scan]`; the value must be a positive integer no larger
than the platform's thread timeout limit. It changes only how long a collector may run; a
timeout still exits without a complete observation.

The host limits the memory of each collector to 4 GiB ([AD-319](architecture/decisions/ad-319-a-collector-process-has-a-memory-limit-and-a-checked-adapter-version.md)).
Linux limits address space and Windows limits committed memory. A collector that runs out of
memory gives an `execution_error` that names the limit. macOS has no memory limit.

## Results

Read `observation_complete`, `declared_rules` and `expectation_fulfilled` separately.
Rule PASS needs completed scope evaluation and sufficient evidence; permission
rows are DECLARATION. Known violations remain FAIL alongside UNKNOWNs. Report
expectations are n/a. Filtering and baseline display do not change canonical facts.

### Exit codes

On `main`:

| Command | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `validate`, `report` | PASS: the core decided each rule and no rule fails | FAIL: a rule fails | UNKNOWN: a rule or a part is not decided. Or a refusal: nothing was decided |
| `skill install` | Instructions written | — | Target could not be updated |
| Each other command | — | — | Typed refusal `not_on_this_development_line` |

Exit 0 needs a frame of the core. No path of the shell gives exit 0 for `validate` or `report` without it.
In JSON, a refusal has the field `refusal` with `kind` and `message`, and no frame. In text, it starts with `REFUSED:`.
A gap has `kind`, `subject` and `reason`. A rule kind without a port is UNKNOWN with the gap `rule_kind_not_ported`.

<a id="core-only-architecture-gate"></a>

## The core path

`archkeel validate` and `archkeel report` use `archkeel-core scan` and nothing else (AD-432, AD-422).
The core reads the configuration and the Git state, collects the source and decides the architecture rules.
The shell prints the frame. PASS exits 0, FAIL exits 1, and UNKNOWN or a refusal exits 2.
The shell also compares the root, the commit and the dirty state of the frame with its request.
A difference is a refusal. The rule rows are trusted to the located core binary.

`--core-only` is accepted and changes nothing. `ARCHKEEL_CORE_ONLY` and `ARCHKEEL_NATIVE_CORE` are ignored.
`--native-core`, `--timings`, `--html` and unported options of the Python engine give a typed refusal with exit 2.
`report --json` gives the verdict frame as JSON, and `--text` gives the text summary.
Neither stdout form is a complete `architecture.json` or an HTML report.
`report --topology` adds a bounded `topology` section: components, modules, edges, completeness, budgets
and the rules that cite each edge (AD-464). Without the option the frame and its time do not change.
The section also states the declared structure: the `layer` and the public surfaces of each component,
each `requires` with the number of observed imports, and each `layer_order` (AD-594).
Each module names the language of its collector, and each component its responsibilities (AD-606).
A total over a budget sets `truncated` and keeps the exact total. The section never changes a verdict.
`topology.complete` means only: the scope is complete and no list is truncated. It is not the verdict
and does not mean that the run has no gap: an UNKNOWN run can show `complete: true`.

`report --output PATH` writes one static HTML page. `--format json` writes the core frame instead.
`--format html` is the default and needs `--output`. Without an output path, no file is written.
The HTML comes from the same ruling in the Rust core. It loads no external resource; each script is admitted by its hash (AD-496).
Its architecture section is the Explorer: As-Is, Target and Diff for the system and for each component, with a drill-down (AD-606).
It includes verdicts, counts, rule rows, violations, evidence locations, gaps, unsupported parts and request identity.
The identity block lists each bound contract file and its SHA-256 digest, including nested contracts (AD-438).
UNKNOWN and collection-refused frames write reports that show their verdict and causes.
A refusal without an accepted frame writes nothing and says so. Stdout and verdict exits stay unchanged.
If the report file cannot be written, stdout still shows the frame verdict with typed `io_error`, exit 2.
Exit 2 replaces exit 1 of a FAIL: a run that cannot deliver the requested file is not a clean FAIL.
The parent must exist. Ancestor links are allowed, including `/tmp` on macOS; the resolved parent is pinned once.
A final-component link, directory or special file is refused. Empty and `.` output paths refuse before the scan.
`--output -` refuses: standard output is not a file target; omit `--output`.
An existing regular file is replaced atomically. No sidecar or parent directory is created.
The page uses compact detail fields and cited evidence locations. The Tool block labels the core code digest.
It shows no package version, because the scan request does not carry one. The crate version is not the package version.
This safe file output requires POSIX directory handles; other platforms refuse file output.
`validate --output` stays refused, as release 4.0.1 did not have it. See AD-440.

### Baselines

`validate --baseline PATH` compares the run with a baseline file. `validate --write-baseline PATH`
writes the baseline of the run (schema 1.4.0). `PATH` names a regular file below the root, not an
absolute or parent path. The two options cannot name the same file. Run `--write-baseline` once,
review the file, and keep it in the repository.

| What the run has against the file | State | Exit code |
|---|---|---|
| A violation, a gap or a budget that the file does not have, or a higher count | `drift` | 1 |
| An accepted entry that the run no longer has, or a lower count (the file is stale) | `drift` | 1 |
| The file is absent, outside the repository, damaged or unsorted | `invalid` | 1 |
| No difference, and the run has at least one UNKNOWN | `current` | 2 |
| No difference, and no UNKNOWN | `current` | 0 |
| A refused part of the run (reply, contract, section, report), or a refused scan | `not_compared` | 1 |

The file lists each accepted UNKNOWN as `kind`, `subject` and `reason`, with a `count` above 1.
A rule row has the rule id as subject, so a new rule that is UNKNOWN for an accepted cause is a new
entry: write the file again and review the diff.
There is no line, evidence id or digest, so an unrelated edit does not change an entry. An accepted
UNKNOWN stays UNKNOWN: the rule row, the run status and the exit code keep the word, and the text
says `accepted UNKNOWN entries`. UNKNOWN never exits 0. Accepted violations are known debt: they do
not make the exit code 1.
The budgets `cycle_edges` and `private_crossings` are compared. A budget that the core does not
measure (`calls_unresolved`, `typing_positions`, `untyped_private_accesses`) is the gap
`budget.unmeasured`, exit 2. A file of schema 1.0.0 to 1.3.0 is read; it accepts no UNKNOWN, and its
three call and typing budgets give `baseline.budget_of_older_schema`, exit 2. The JSON result has a
`baseline` object with `state`, `exit_code`, `accepted_unknowns`, `new`, `gone` and `gaps`
([AD-546](architecture/decisions/ad-546-a-baseline-accepts-an-unknown-by-what-it-is-and-the-core-compares-it-both-ways.md)).

A baseline of schema 1.0.0 to 1.3.0 comes from release 4.0.1. The text names that, prints the one
command that writes it again (`archkeel validate --write-baseline <file>`), and says which parts the
core does not read: the budgets `calls_unresolved`, `typing_positions` and `untyped_private_accesses`,
and the amendment file of the project. The text and the page also show the call measure: how many
calls the core resolved, with the percentage, and that an unresolved call is no edge, so a rule that
reads calls stays UNKNOWN while a rule of imports does not read it.

`check` always refuses and names each check it cannot run: its expectation, lock, Git and host checks need #1103.
No failure falls back to Python.

The shell looks for the core only below its own package: `archkeel/_native` with a SHA-256 file,
else `native/target/release/archkeel-core` of the checkout that holds the package below `src/`, else its debug build.
An installed package has no checkout and uses only `archkeel/_native`.
The digest finds a damaged or wrong file. It does not stop a party that can write both files,
and the binary can change between the check and its start.
It never reads the scanned project, the current directory or `PATH`. Build the core with `make core`.
A platform wheel carries the core and its digest in `archkeel/_native` (AD-436). No release carries it yet.
A package without the core refuses with `core_binary_not_found`.
The scan reads Git through the fixed system executable, not PATH. Missing Git is a named refusal.

The repository survey refuses a root with more than 1 GiB of file bytes or more than 100,000 entries.
Below a directory that holds a `CACHEDIR.TAG` file with the standard signature, the survey does not
count the file bytes, and it counts the entries against a separate limit of 1,000,000.
Cargo writes this file into `target/`. The rule selects no source
and hides none: a source file below such a directory is still collected when the project names it.

## Plugins

Plugins reuse the CLI skill. New [GitHub releases](https://github.com/rapiddweller/archkeel/releases)
include `archkeel-plugin-<version>.zip` and its SHA-256 checksum. The ZIP contains
both plugin manifests and the canonical skill; install the CLI separately.
The repository root is the plugin: `.claude-plugin/marketplace.json` and
`.agents/plugins/marketplace.json` list it with `source ./`. Directory listing and
host activation remain separate acceptance steps.
