# Archkeel reference

For a gate that moves from 4.0.1 to 5.0, see [the migration guide](migration-4-to-5.md).

## State of `main`

This page describes the development checkout. Studio and its optional MCP server are
available from this checkout. The build on `main` does not expose them.

The Rust core `archkeel-core` is the only decision path (AD-432, issue #880).
The Python engine is deleted. The shell reads the arguments, starts the core and prints its frame.

| Command | In this checkout |
| --- | --- |
| `validate`, `report` | Served by the core, as text or JSON. See [the core path](#the-core-path). |
| `skill install claude\|codex` | Served by the shell. It writes the skill file. |
| `init` | Served by the shell: drafts `archkeel.toml` and a contract from the folder layout ([guide](onboarding.md), AD-626, AD-638). `validate` and `report` do it when `archkeel.toml` is missing, unless `--no-init` or `ARCHKEEL_NO_INIT=1`. |
| `studio` | Open the [local Explorer](explorer.md). Existing scripts can use `explore`. |
| `archkeel-mcp` | Start the [MCP stdio server](explorer.md) on a pinned snapshot. Requires the `mcp` extra. |

The core supports Rust, TypeScript, Python and Dart. See [known limits](known-limits.md)
for the evidence each collector can provide.
A config without `language` selects the Python profile. There is no partial PASS.
The shell refuses legacy saved-report inputs, focused-report options, amendments and
`--write-graph` by name with exit 2.
Use `validate --baseline` and `validate --write-baseline` for [baselines](#baselines).

Release 4.0.1 has the Python engine: `check`, `init`, full reports and baselines for Python,
Dart and TypeScript projects. It has no Rust profile, `explore`, Studio, stories or views.
Its documents are at the [tag 4.0.1](https://github.com/rapiddweller/archkeel/tree/4.0.1/docs).

## Configuration

[The schema](../schema/archkeel.schema.json) defines `archkeel.toml`. The source suffixes of the
languages are one file, [`schema/archkeel-source-suffixes.txt`](../schema/archkeel-source-suffixes.txt),
read by the core and by `archkeel init`
([AD-738](architecture/decisions/ad-738-one-data-file-owns-the-source-suffixes-of-both-languages.md)).

The options of `archkeel.toml`:

```toml
[scan]
roots = ["src"]
namespace = "app"
contract = "architecture-contract.json"
```

Roots are repository-relative, nonoverlapping and not globs. With Python
`namespace = ""`, module names are relative to their import roots. The
[draft guide](onboarding.md) describes how ArchKeel finds those roots. Optional `language` is `rust`, `typescript`, `python` or `dart`; a missing value
selects `python`. TypeScript also uses `tsconfig`; roots may be files or directories.
Inputs must exist inside `--root`.

For Python, set `python = "3.13"` in `[scan]` to select a target version. Without it,
ArchKeel uses the lowest version in `requires-python`, or its default when no requirement exists.
The collector supports Python 3.11 through 3.14. It does not run an interpreter or read `PATH`.
The summary names the target. Unread requirement forms and unsupported targets are refused.

An explicit component `inside` mounts a child contract over the same scan. Its path is
relative to `--root`, not to its parent contract. `validate` and `report` read all mounts
through the core. Labels and rule IDs are mount-qualified; each mount keeps its own source domain.
The shell checks the SHA-256 of every contract file. A changed, linked, missing or unsafe
nested file cannot produce PASS. See [nested intent](rules.md#nested-and-independent-intent).

`exclude_test_sources = true` (default false) leaves recognized test sources out of the scan
of `report` and `validate`. The result names the excluded paths for Python, TypeScript and Dart.
The rules use test naming conventions, not proof that each file is a test. Check the named paths
before relying on the verdict. An import from production code into an excluded test source stays
UNKNOWN. Keep the default to include test sources in architecture checks.
The Explorer (`studio`, `explore`, `archkeel-mcp`) leaves test sources out of a Python or TypeScript scan when
`archkeel.toml` does not state `exclude_test_sources`. If that removes a file, the core holds the verdict: UNKNOWN with the gap
`implicit_test_exclusion`, never PASS where `validate` reads FAIL. Its `verdict` answer gives `excluded_sources`, `excluded_paths`
and a `scope` note. State `exclude_test_sources = true` or `false` to decide the scope; the Explorer then has the ruling of
`validate` ([AD-1119](architecture/decisions/ad-1119-the-explorer-leaves-test-sources-out-unless-the-config-states-the-scope.md)).
For Dart, this option excludes `.dart` files under `test` or `tests` within a selected root,
and files whose names end in `_test.dart`. It also excludes a root named `test` or `tests`,
unless that root is a Dart package directory.
It does not classify a nested Dart package directory as a test only because of its name.
The result names each excluded file. A scope with only excluded Dart files stays UNKNOWN.

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

### Root and configuration

Without flags, a run reads the nearest `archkeel.toml` at or above the current folder inside the
Git work tree, and its folder is the root; without one it uses the top of the work tree.
`--config PATH` is read from the current folder, as each command line tool reads a path; a file
that is not there is refused with the path that was tried. Its folder is then the root, unless its
`[scan]` names another with `root` (`"."` or a path of `..` parts, such as `root = "../.."` for
`docs/architecture/shell.toml`). A system document names the top of its work tree. With `--root`,
a relative `--config` is read below that root. The first text line and the JSON result (`root`,
`config`) name the root and the configuration of the run
([AD-776](architecture/decisions/ad-776-a-relative-config-is-read-from-the-current-folder.md)).

Each language runs its own
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

`browser_entry = "web/index.html"` in `[scan]` (TypeScript only, [AD-1460](architecture/decisions/ad-1460-the-browser-scope-of-a-part-is-the-script-closure-of-its-entry-page.md)) names
the HTML page that the part ships to a browser. The core derives the browser scope from the scripts that the page loads
(`<script src>`, `<link rel="modulepreload">`, then `import`, `export … from`, `import("…")`, `importScripts` and
`new Worker` with a literal path, transitively). Only these files, outside the scan roots, can replace a global for the
part; a fixture, a tool or a second page that no entry loads cannot, and a file that the entry loads stays in. Without
`browser_entry`, every script of the repository outside the scan roots counts, and so does every Node preload.
`browser_assets = ["web", "lib"]` names the folders that serve a path that starts with `/`, in order (default: the folder
of the page); a relative path is resolved against the URL of the file that names it. A missing entry or folder refuses the
run. A reference that cannot be followed (a path in no folder, a bare name, a path that is no literal) never narrows the
scope: no global has a native proof, and the gap names the file and the reference.

`rust_type_reach = true` in `[scan]` asks for compiler type-reach facts. Producing them runs `cargo check` on the
scanned repository, and so its build scripts and procedural macros. The repository cannot allow that for itself:
the operator must also set `ARCHKEEL_ALLOW_BUILD=1` in the environment of the run. Without it no cargo command
starts and the scan reports the gap `type reach not allowed by the operator`; the trait-impl, destructor and receiver
gaps stay. See [AD-1130](architecture/decisions/ad-1130-the-operator-allows-the-build-of-a-scanned-repository.md).

The host limits the memory of each collector to 4 GiB ([AD-319](architecture/decisions/ad-319-a-collector-process-has-a-memory-limit-and-a-checked-adapter-version.md)).
Linux limits address space and Windows limits committed memory. A collector that runs out of
memory gives an `execution_error` that names the limit. macOS has no memory limit.

## Results

Read `observation_complete`, `declared_rules` and `expectation_fulfilled` separately.
Rule PASS needs completed scope evaluation and sufficient evidence; permission
rows are DECLARATION. Known violations remain FAIL alongside UNKNOWNs. Report
expectations are n/a. Filtering and baseline display do not change canonical facts.

### Exit codes

| Command | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `validate`, `report` | PASS: the core decided each rule and no rule fails | FAIL: a rule fails | UNKNOWN: a rule or a part is not decided. Or a refusal: nothing was decided |
| `skill install` | Instructions written | — | Target could not be updated |
| Unsupported command | — | — | Typed refusal `not_on_this_development_line` |

Exit 0 needs a frame of the core. No path of the shell gives exit 0 for `validate` or `report` without it.
Each JSON result starts with `command`, `outcome`, `status` and `exit_code`
([AD-735](architecture/decisions/ad-735-the-draft-step-has-one-outcome-and-runs-after-the-core-is-found.md)).
`outcome` is `verdict`, `collect_refused`, `command_refused`, `delivery_failed` or `completed`
(`init`, `skill`; their `status` is `null`).
In JSON, a refusal has the field `refusal` with `kind` and `message`. A command refusal has no frame. A collection refusal or a failed file write keeps its frame. In text, it starts with `REFUSED:`.
The result of a run that gave a frame also has `refusals`, which lists each refusal in order;
`refusal` is the first. A run that could not write a file keeps its frame.
With `--baseline`, exit 2 means that every UNKNOWN is accepted, so only a verdict of the core gives it.
A refusal, and a baseline file that was not written, exit 1 with `--baseline` and 2 without
it ([AD-731](architecture/decisions/ad-731-under-a-baseline-only-a-verdict-exits-2.md)).
A gap has `kind`, `subject` and `reason`. A rule kind without a port is UNKNOWN with the gap `rule_kind_not_ported`.

<a id="core-only-architecture-gate"></a>

## The core path

`archkeel validate` and `archkeel report` use `archkeel-core scan` and nothing else (AD-432, AD-422).
The core reads the configuration and the Git state, collects the source and decides the architecture rules.
The shell prints the frame. PASS exits 0, FAIL exits 1, and UNKNOWN or a refusal exits 2.
The shell also compares the root, the commit and the dirty state of the frame with its request.
A difference is a refusal. The rule rows are trusted to the located core binary.

`--core-only` is accepted and changes nothing. `ARCHKEEL_CORE_ONLY` and `ARCHKEEL_NATIVE_CORE` are ignored.
`--native-core`, `--html` and unported options of the Python engine give a typed refusal with exit 2.
`validate --timings FILE` and `report --timings FILE` write the seconds of the phases of the core as one JSON file
(`prepare`, `collect`, `validate`, `evaluate`, `render`, `join` for a system run, and `core_seconds`, measured with a
monotonic clock, AD-878). `core_seconds` is the time inside the core, not the time of the whole command.
Standard output, the verdict and the report do not change. A scan that the core refuses, also in one part of a system
run, writes no file. `--timings` creates a new file and never replaces one: a name that exists (also as a link) is
refused before the scan, and so is a name that `--output` or `--write-baseline` also names. Give each run a new
name, for example `--timings "timings-$(date +%s).json"`.
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
`--format markdown` writes a Markdown guide of the components, their responsibilities, the requirements and the layer orders. It renders the topology of the core frame and adds no verdict (AD-1121).
`report --part-of DOCUMENT --system-href URL` writes the page of one part of a system (#1451). The core
reads the titles of the system and of the part from the system document, so the root of the Explorer reads
"<part> of <system>" and links to `URL`, the page of the system. A document that is no system document, or
that names no part with this configuration, is a refusal. Both options need an HTML `--output`.
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
An existing regular file is replaced atomically. When the HTML links to gap records,
the same directory also contains the linked `archkeel-gaps-<sha256>.json` file.
The page uses compact detail fields and cited evidence locations. The Tool block labels the core code digest.
It shows no package version, because the scan request does not carry one. The crate version is not the package version.
This safe file output requires POSIX directory handles; other platforms refuse file output.
`validate --output` stays refused, as release 4.0.1 did not have it. See AD-440.

### Baselines

`validate --baseline PATH` compares the run with a baseline file. `validate --write-baseline PATH`
writes the baseline of the run (schema 1.5.0). `PATH` names a regular file below the root, not an
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
| `--write-baseline` on a run with a refused part: no file is written | `not_written` | 1 with `--baseline`, else the exit code of the run |

The file lists each accepted UNKNOWN as `kind`, `subject` and `reason`, with a `count` above 1.
A rule row has the rule id as subject, so a new rule that is UNKNOWN for an accepted cause is a new
entry: write the file again and review the diff. A rule can have several causes, and the file lists
all of them (schema 1.5.0, [AD-1330](architecture/decisions/ad-1330-a-baseline-keys-every-cause-of-a-rule.md)):
resolving the first cause is a `gone` entry, never a new one. A file of schema 1.4.0 lists the first
cause only and is compared on that cause; write it again once to get the full list. A collector gap is
matched by its exact kind, subject and reason.
There is no line, evidence id or digest, so an unrelated edit does not change an entry. An accepted
UNKNOWN stays UNKNOWN: the rule row, the run status and the exit code keep the word, and the text
says `accepted UNKNOWN entries`. UNKNOWN never exits 0. Accepted violations are known debt: they do
not make the exit code 1.
A file of schema 1.4.0 compares the budgets `cycle_edges`, `private_crossings`, `calls_unresolved`,
`typing_positions` and `untyped_private_accesses`. A budget above its ceiling is `drift`, exit 1.
A budget that the contract declares and the file lacks is also `drift`, exit 1. A budget that the
run does not measure is the gap `budget.unmeasured`, exit 2. A file of schema 1.0.0 to 1.3.0 is
read; it accepts no UNKNOWN, and its three call and typing budgets give
`baseline.budget_of_older_schema`, exit 2. The status can read `FAIL` with exit 2: the status names
the worst verdict, the exit code names the gate, and each violation of such a run is accepted
([AD-1090](architecture/decisions/ad-1090-baseline-1-4-0-compares-the-three-call-and-type-budgets.md)).
A run that declares `measurement_budgets` and compares with no baseline gets the row `budget.unknown`. The JSON result has a
`baseline` object with `state`, `exit_code`, `accepted_unknowns`, `new`, `gone` and `gaps`
([AD-546](architecture/decisions/ad-546-a-baseline-accepts-an-unknown-by-what-it-is-and-the-core-compares-it-both-ways.md)).

A baseline of schema 1.0.0 to 1.3.0 comes from release 4.0.1. The text names that, prints the one
command that writes it again (`archkeel validate --write-baseline <file>`), and says which parts the
core does not read: the budgets `calls_unresolved`, `typing_positions` and `untyped_private_accesses`,
and the amendment file of the project. The text and the page also show the call measure: how many
calls the core resolved, with the percentage, and how many targets remain open. A proven violation yields FAIL even if another call has an open target.

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
