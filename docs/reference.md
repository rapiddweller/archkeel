# Archkeel reference

## State of `main`

The Rust core `archkeel-core` is the only decision path on `main` (AD-432, issue #880).
The Python engine is deleted. The shell reads the arguments, starts the core and prints its frame.

| Command | On `main` |
| --- | --- |
| `validate`, `report` | Served by the core, as text or JSON. See [the core path](#the-core-path). |
| `skill install claude\|codex` | Served by the shell. It writes the skill file. |
| `check`, `init` | Typed refusal, exit 2. Release 4.0.1 has them. |
| `explore`, `guide`, `story`, `view`, `studio` | Typed refusal, exit 2. No release has them. |

`main` supports Rust and TypeScript projects. Python and Dart profiles give exit 2 before collection (AD-430).
A config without `language` selects the Python profile, so it is refused. There is no partial PASS.
Interactive reports, `architecture.json`, saved reports, focused reports, baselines, amendments and
`--write-graph` are not on `main`. The shell refuses each of their options by name with exit 2.

Release 4.0.1 has the Python engine: `check`, `init`, full reports and baselines for Python,
Dart and TypeScript projects. It has no Rust profile, `explore`, Studio, stories or views.
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
not globs. Optional `language` is `rust` or `typescript`; a missing value or `python` or
`dart` is refused. TypeScript also uses `tsconfig`; roots may be files or directories.
Inputs must exist inside `--root`.

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

`report --output PATH` writes one static HTML page. `--format json` writes the core frame instead.
`--format html` is the default and needs `--output`. Without an output path, no file is written.
The HTML comes from the same ruling in the Rust core. It has no scripts, external resources or graph.
It includes verdicts, counts, rule rows, violations, evidence locations, gaps, unsupported parts and request identity.
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

`check` always refuses and names each check it cannot run: its expectation, lock, Git and host checks need #1103.
No failure falls back to Python.

The shell looks for the core only below its own package: `archkeel/_native` with a SHA-256 file,
else `native/target/release/archkeel-core` of the checkout that holds the package, else its debug build.
It never reads the scanned project, the current directory or `PATH`. Build the core with `make core`.
No package carries the core yet, so an installed package refuses with `core_binary_not_found`.
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
