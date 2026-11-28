# ArchKeel 5.0.0 (unreleased) — Breaking changes and migration

The Rust core decides each run ([AD-432](docs/architecture/decisions/ad-432-the-rust-core-is-the-only-decision-path.md)).
The Python engine of 4.0.1 is deleted. The facts below are measured on the development line and on release 4.0.1.
For an EE or CE gate, follow [docs/migration-4-to-5.md](docs/migration-4-to-5.md).

## Breaking changes

| What | 4.0.1 | 5.0 |
|---|---|---|
| Exit code | `validate`: PASS 0, FAIL 2. With `--baseline`: known violation 0, new violation 1. `report` exits 0 when it observed the repository, also with violations. | `validate` and `report`: PASS 0, FAIL 1, UNKNOWN or refusal 2. UNKNOWN never exits 0. |
| `validate` without `archkeel.toml` | Exit 2 with the diagnostic `contract.invalid` ("run archkeel init"). Writes nothing. | Drafts `archkeel.toml` and a contract, then checks. Use `--no-init` or `ARCHKEEL_NO_INIT=1` to write nothing (exit 2). |
| Command `check` | Available. | Refused: `not_on_this_development_line`, exit 2. |
| `validate` options | `--against`, `--amendment`, `--write-amendment`, `--accept-new`, `--write-graph`, `--compact-open-decisions`, `--decided-by`, `--rationale` | Refused by name, exit 2. |
| `report` options | `--only`, `--rule`, `--component`, `--full`, `--input`, `--baseline` | `--baseline` is an unknown argument (exit 1). The others are refused by name (exit 2). |
| `init` options | `--source`, `--namespace`, `--language`, `--tsconfig`, `--full`, `--force`, `--collector-argv`, `--collector-output-limit-bytes` | Refused (exit 2). Run `init`, then edit `archkeel.toml`. |
| `--write-baseline` | A flag. It writes the file of `--baseline`; new debt needs `--accept-new`. | Takes a file: `--write-baseline FILE`. `--baseline` and `--write-baseline` cannot name the same file. |
| Baseline file | Schema 1.0.0 to 1.3.0. | Schema 1.5.0 (1.4.0 is read). A file of 1.4.0 names the first cause of a rule only and is compared on it; write it again once to name every cause (AD-1330). An older file is read, accepts no UNKNOWN, and its call and typing budgets exit 2 (`baseline.budget_of_older_schema`). |
| `report` output | Saved `architecture.json`, focused reports. | `--output FILE` writes one `html` (default), `json` or `markdown` file. |
| `archkeel.toml` | `collector_argv` starts your own collector. | `collector_argv` is refused: the core runs only its own collectors. All other `[scan]` keys stay. New keys: `collector_timeout_seconds`, `bundler`, `exclude_test_sources`, `python`, `import_roots_ambiguous`, `rust_type_reach`, `root`. |
| JSON result | Result schema 7.0 and 8.0. | Starts with `command`, `outcome`, `status`, `exit_code`. A run that decides has a core `frame`. A command refusal has `refusal` and no frame. A collection refusal or a failed file write keeps its frame and also has `refusal`. |
| Removed schemas | `architecture-graph`, `architecture-report`, `architecture-comparison`, `source-member-inventory` | Not written. |
| Python API | `archkeel.api`, `archkeel.analyzer`, `archkeel.check`, `archkeel.ir`, `archkeel.host` | Not in the package. Run `archkeel` as a subprocess and read the JSON. |
| Install | One pure wheel with six runtime dependencies. | Six platform wheels (macOS x86_64 and arm64, manylinux x86_64 and aarch64, musllinux x86_64, Windows x86_64). No runtime dependency. Other platforms need a native build. |
| Commands | `check`, `init`, `report`, `skill`, `validate` | `validate`, `report`, `init`, `skill` and `studio` (`explore` is an alias). `guide`, `story` and `view` are unknown commands. |
| Rust main binary | No Rust collector. | A package without a library names its main binary (the bin named like the package, else the bin of `src/main.rs`) with the package module name, `<namespace>.<package>`. A contract that named it `bin_<name>` must rename those modules (AD-1410). |

## Verdict changes

- The core says UNKNOWN when its evidence is not complete, and it names the cause in `frame.gaps`. Some rules that read PASS on 4.0.1 now read UNKNOWN. A proven violation stays FAIL.
- A rule kind that the core does not decide is UNKNOWN with the gap `rule_kind_not_ported`. These kinds are `catalog_argument`, `catalog_use`, `forbidden_effect_under_condition`, `source_ownership` and `bounded_numeric_operand`: 4.0.1 has none of them. No rule kind of 4.0.1 is removed.
- Code that the scan does not read can change a verdict. A Python file outside the scan roots that can write a module of the scan holds the rules that read it ([AD-770](docs/architecture/decisions/ad-770-code-of-the-repository-outside-the-scan-that-writes-a-module-of-the-scan-withholds-its-routes.md)). A Rust crate outside the workspace members that can reach a member holds the member ([AD-1097](docs/architecture/decisions/ad-1097-a-crate-that-is-no-workspace-member-is-foreign-code-in-the-rust-scan.md)). Without `ARCHKEEL_ALLOW_BUILD=1` such a crate is not proven and holds.
- `rust_type_reach` runs `cargo check` only with `ARCHKEEL_ALLOW_BUILD=1` ([AD-1130](docs/architecture/decisions/ad-1130-the-operator-allows-the-build-of-a-scanned-repository.md)).

## Migration

1. Install a platform wheel. Run `archkeel --version`.
2. Replace each removed command and option in your scripts with the table above. Keep 4.0.1 for `check`, amendments and `--against`.
3. Read `status`, `outcome` and `exit_code` of the JSON. Exit 1 is FAIL. With `--baseline`, exit 1 is also a difference, a refused run or a file that was not written. Exit 2 is not decided, or a refusal.
4. Run `archkeel validate --no-init` in CI, so that a missing `archkeel.toml` writes no file.
5. Write the baseline again: `archkeel validate --write-baseline known-violations.json`. Review the diff. Then run `archkeel validate --baseline known-violations.json`.
6. Read each UNKNOWN in `frame.gaps`. Fix the cause, or accept it in the baseline.
7. Replace an import of `archkeel.*` with a subprocess call.
8. Move a `collector_argv` setting to a collector that the core provides, or remove it.

---

# ArchKeel 4.0.1 — Exact dependency rules and typed controls

Declare narrower component APIs and check more native source evidence.

## Highlights

- **Exact dependency intent.** Opt-in contract **3.4.0** adds exact module
  selectors; **3.5.0** can forbid an import namespace even after its module has
  been removed. Contract **3.6.0** adds caller-scoped Python module-object grants without
  publishing named symbols. `requires.through` also checks exact `module:Symbol`
  ports. Unexpanded wildcard names remain UNKNOWN when an exact symbol is required.
- **Substantive responsibilities.** Architect-attributed components containing
  only `TODO`, `TBD` or `placeholder` markers now receive
  `responsibility.missing`. Validation exits 2; agent drafts remain accepted.
  Non-placeholder prose still does not prove that a responsibility is correct.
- **More precise native controls.** Python observes supported literal equality,
  membership, `match`, stable imported constants and guarded Enum values at their
  actual lexical owners, preserving physical source lines. TypeScript/JavaScript
  observes written string comparisons and switch cases as PARTIAL evidence:
  witnessed violations can FAIL, while an empty inventory cannot prove PASS.
  Dart local callables retain lexical precedence over imported names.
- **Shared control types.** Covered Core, collector and browser boundaries use
  owned nominal vocabularies, checked ingress and native regression guards.
  This is a bounded migration; remaining string-control work in
  [#542](https://github.com/rapiddweller/archkeel/issues/542) stays open.
- **Less repeated collector work.** Python member-escape propagation indexes
  dotted prefixes once per convergence pass and preserves live binding updates.
  This removes repeated per-import scans; it does not guarantee a runtime budget
  on every project or runner.
- **Report and review corrections.** Published browser assets include the current
  runtime. Module views reuse the report graph already derived by their caller.
  Direct UML scopes use more edge spacing. Repeated-logic review
  candidates can distinguish complete, resolved call sequences; ambiguous
  evidence retains the candidate and proves no runtime equivalence.

## Release verification

The 4.0.0 tag did not reach PyPI: the full gate caught a Windows checkout failure
before the collector-safety tests ran. Fetching all branch refs tried to create
an `aux/...` path; Windows reserves the name `AUX`. Those jobs now fetch only the requested
ref. Both Python versions, collector-safety tests and the publication gate remain
required. Native TypeScript mutation fixtures also read and write UTF-8 explicitly
instead of depending on the Windows locale. Flow source and runtime assets retain
LF line endings so packaged source checksums remain valid on Windows.
The public 4.0.0 tag is retained.

## Upgrade from 3.0.1

```sh
uv tool upgrade archkeel
```

**Upgrade strict readers and collectors together.** New TypeScript observations
can include a `constructs` section that the 3.0.1 report reader rejects. This is
an incompatible profile expansion and requires the new package major. SourceFacts
and protocol remain **3.0.0**, ArchitectureIR/Delta **2.0.0**, and command-result
**8.0.0**; unchanged version numbers do not make the new profile readable by an
older Core. Existing legacy TypeScript receipts remain supported by this release.

CLI options, configuration and documented `archkeel.api` exports retain their
interfaces. Existing contract versions remain supported; older releases reject
the new opt-in contract fields. Analyzer corrections can change findings and
identities: re-observe both revisions with the same package before comparing
snapshots. Saved reports retain their original evidence.

Static evidence still does not establish compiler parity, runtime correctness or
complete language coverage. See [known limits](docs/known-limits.md),
[dependency rules](docs/rules.md) and the [compatibility policy](docs/reference.md).

# ArchKeel 3.0.1 — Scoped proof and quieter reports

Check the rules whose evidence is complete, while keeping real analysis limits visible.

## Highlights

- **Scoped Dart and TypeScript rule proof.** An unrelated source-resolution gap no
  longer makes every `complete_requires` rule UNKNOWN. Complete, authenticated
  dependency scopes can PASS; unresolved imports still block their owning scopes
  and affected ancestors. Known violations remain FAIL even when the observation
  is incomplete. Global coverage and exit codes retain their uncertainty.
- **More precise native declarations.** Dart named constructors use their lexical
  owner once, matching the independent Compass Target. Complete direct-member
  inventories retain local proof despite unrelated gaps. TypeScript now observes
  named constructor parameter properties, supported decorated member inventories
  and module-level array constants, and distinguishes type/value namespaces.
  Runtime-generated members, dynamic imports and ambiguous bindings remain UNKNOWN.
- **Quieter report inspection.** The unselected fact sheet summarizes boundary
  permissions; selecting a component or member shows its relevant records. The
  complete audit stays available, grouped by rule and revealed in batches of 20.
  Structure overview replaces size-based review questions with neutral measurements.
- **Less rendering work before interaction.** Health check builds its module matrix
  when opened, and closed module lists defer their links. Permission details are
  constructed on demand. Evidence, canonical JSON, offline links and verdicts stay
  available without rendering every detail up front.
- **Smaller agent responses when requested.** `validate --compact-open-decisions
  --json` returns observed undecided crossings with exact total/completeness fields.
  Default validation output retains every open pair. Large collector replies can
  use the explicit `collector_output_limit_bytes` setting; the default stays 64 MiB.
- **Clearer internal ownership.** Proof issuance and replay share one binding
  definition. Command-view preparation is separate from authenticated projection;
  seven focused format owners back the compatible codec facade. Historical
  full-policy test copies are replaced by a small fixed compatibility fixture.

## Release verification

The 3.0.0 tag was not published to PyPI: the full release gate caught an older
corpus test that assumed every valid contract was version 2.1 without UML. The
check now preserves each input version, UML presence and semantic round trip,
and runs in the required Core sample. Product parsers, schemas and policy remain
unchanged by this correction.

## Upgrade from 2.0.0

```sh
uv tool upgrade archkeel
```

Pin strict command-JSON consumers to the bundled **command-result 8.0.0** schema.
It accepts existing version 6/7 results and adds traceable FAIL for an incomplete
report, including filtered views that retain the global verdict. Version 6/7
schemas remain unchanged and reject that newly permitted combination. This
consumer-visible format change is why this release uses a new package major.
Exit 2 still means the observation cannot certify complete evidence; it can coexist
with a confirmed violation and must not be treated as PASS.

CLI options, configuration, `archkeel.api`, supported contract versions,
SourceFacts and ArchitectureIR/Delta formats retain their interfaces. Analyzer
corrections change recorded identities and findings: re-observe both revisions
before comparing snapshots. Existing saved reports retain their recorded evidence;
they do not acquire missing native proofs by being opened with the new CLI.

Compass and Nest demos retain source gaps and dynamic behavior as UNKNOWN. The
release does not establish compiler parity, runtime correctness or complete UML
conformance. See [known limits](docs/known-limits.md), the
[report guide](https://github.com/rapiddweller/archkeel/blob/4.0.1/docs/report-visual-system.md) and [demo catalog](https://github.com/rapiddweller/archkeel/blob/4.0.1/docs/architecture-demo.md).

# ArchKeel 2.0.0 — ArchQ Explorer and exact permissions

Architecture checks for coding agents.

- **ArchQ Explorer replaces the previous report navigation.** The report opens
  with the new Explorer embedded. Fullscreen expands the same view; Restore
  preserves selection and zoom. Offline module and member pages share its controls.
- **Find and explore recorded evidence.** Search components, modules and rules;
  browse sortable Objects, inspect Health check, or highlight authorship, layer
  and evidence perspectives. Pointer zoom, keyboard shortcuts and SVG, Mermaid
  and link export support review. As-Is, Target and Diff retain the same recorded
  verdicts, UNKNOWNs and source links. No new runtime dependency is required.
  See the [report guide](https://github.com/rapiddweller/archkeel/blob/4.0.1/docs/report-visual-system.md) and
  [Explorer work](https://github.com/rapiddweller/archkeel/issues/467).
- **Exact native boundary permissions.** Opt-in contract schemas **3.0–3.3**
  add source-and-body-bound alias permissions, heterogeneous typed-map unions
  with exact key-alias proof, directly written literal map arms, and explicit
  bare-map permissions at exact DTO fields or registry parameters. Separate
  depth selectors accept only the supported native object leaves. Metadata
  fields, sibling findings and UNKNOWNs remain independently checked.
  See [boundary rules](docs/rules.md#interfaces-and-types).
- **Compatibility stays explicit.** Supported **2.1–2.3** contract schemas and
  serialization without the new bindings remain unchanged. Existing contracts
  are not rewritten; older readers reject unsupported opt-in schemas.
- **Unproven alias bodies stay UNKNOWN.** They do not justify body-dependent findings or
  grants. Proven literal findings remain; ordinary permissions cannot bypass
  uncertain alias proof by changing union order.
- **Explicit Callable signatures.** Proven stdlib argument lists and results use
  the existing boundary checks. SourceFacts **3.0.0** carries neutral TypeList
  facts; versions 1/2 retain exact round trips and reject that new shape.
- **Direct stdlib TypedDict fields.** Proven declarations check every key,
  including underscore keys. Broad fields fail; unproven providers remain UNKNOWN.
  Public model fields also retain proven type-name reach during validation.
- **Full reports retain every recorded UNKNOWN.** `report --only architecture
  --full --json` exports complete original records, including IDs, details and
  evidence references, even with a component filter. Full architecture output uses schema
  **2.0.0**, with command-result schema **7.0.0**. Compact architecture output
  remains **1.0.0**; published legacy **6.0.0** result schemas are unchanged.
  Empty and unavailable evidence remain distinct. See [CLI reference](docs/reference.md).
- **Static proof fixes.** Supported quoted builtin annotations retain their
  original positions; proven stdlib overload re-exports expose all declared
  signatures; property setters retain their own local binding scope. Safe
  annotation carriers and nullable DTO paths preserve supported alias and field
  proof. Unsupported or ambiguous forms retain UNKNOWN.
- **Review the exact permission.** ArchQ Explorer distinguishes declared and applied
  permissions and links evidence to members. Reset and fit controls are labelled
  consistently; rejected offline routes retain the complete URL until explicit
  recovery.

Accepted native values remain opaque. These checks certify neither serialization,
materialization, type closure nor runtime correctness. Product listings use
ArchKeel and “Architecture checks for coding agents”.

# Archkeel 1.1.2 — Bind native allowances to exact signatures

- **Nested map allowances stay bound to the root annotation.** An `Annotated`
  wrapper cannot reuse the inner-map or native-value permission for an unwrapped
  `Mapping[str, list[dict[str, object]]]` signature. Outer-map permission remains
  separate; aliases, DTO fields, unions and unproven bindings do not qualify.
  See [AD-217](docs/architecture/decisions/ad-217-nested-map-allowances.md).
- **JSON Schema agrees with the parser.** A selector with `mapping_depth`
  requires an empty `field_path`. Omitting `field_path` still means the direct
  signature; a nonempty DTO path is rejected.
- **Exact native Iterable elements.** Direct and proven facade signatures can
  permit one `object` element in `Iterable[object]`, optionally unioned with
  `None`. Match the callable, parameter or return position, complete annotation,
  empty `field_path` and `container_depth: 1`. The `typing` or `collections.abc`
  origin and builtin `object` must be proven. Aliases, DTO fields, wrappers,
  other collections, additional union arms and repeated opaque leaves do not
  qualify. See [AD-218](docs/architecture/decisions/ad-218-native-iterable-elements-use-proven-signatures.md).

Accepted native values remain opaque. These allowances prove neither
serialization nor materialization nor type closure. Contract and result schema
versions are unchanged.
Open gaps remain for [native Properties map unions](https://github.com/rapiddweller/archkeel/issues/438),
[heterogeneous typed-map unions](https://github.com/rapiddweller/archkeel/issues/439),
[static overload re-exports](https://github.com/rapiddweller/archkeel/issues/440),
[quoted builtin annotations](https://github.com/rapiddweller/archkeel/issues/441)
and [report-view traceability](https://github.com/rapiddweller/archkeel/issues/445).

# Archkeel 1.1.1 — Exact native mapping allowances

`boundary_types` can now prove the alternatives in an inline union such as
`dict[str, str] | dict[str, object] | None`. An exact annotation allowance permits
the two outer maps; a separate `container_depth` allowance permits one proven
native value. The same rule applies to a uniquely declared DTO field.
Aliases, unknown arms, ambiguous fields and simultaneous maps still grant nothing
through that union selector.
Accepted native opacity does not prove type closure. Contract and result schemas
keep their versions. See [AD-216](docs/architecture/decisions/ad-216-native-mapping-alternatives.md).

For one proven `Mapping[str, list[dict[str, object]]]` boundary, the new optional
`mapping_depth: 2` permits only the inner map. Add `container_depth: 3` to permit
only its native `object` value. Outer map permission remains separate. Aliases,
wrappers, unions and ambiguous or shadowed bindings do not qualify. See
[AD-217](docs/architecture/decisions/ad-217-nested-map-allowances.md).

After successful package publication, the release pipeline starts full
verification on Main when the tag still points to its current commit. If that
run passes, it publishes the verified report gallery.
The report timing guard allows 120 seconds to absorb measured runner variance;
the generated-output limit is unchanged.

# Archkeel 1.1.0 — Dart UML and project-scale architecture reports

Inspect Dart declarations and UML without a Dart SDK, and explore larger
architecture reports through components, modules and members.

## Highlights

- **SDK-free Dart UML.** Observe classes, mixins, enums, members, signatures and bounded
  source relationships through the Python installation. A pinned Tree-sitter grammar
  replaces the SDK dependency; missing resolution and dynamic behavior remain UNKNOWN.
- **Complete-project demos.** Explore pinned Flutter Compass (111 Dart files), Python
  RealWorld (72 modules) and Nest RealWorld (41 prepared TypeScript inputs). Their Targets
  define responsibilities, nested components, module relationships and principal UML
  member scopes. Source-only variants demonstrate violations and analysis limits.
- **Readable architecture maps.** Relationship-driven ELK layouts arrange components and
  modules hierarchically. Nested ownership groups and colors help navigation; closing
  Details releases the diagram space. Target navigation and asynchronous detail layout
  retain the selected scope across views.
- **More precise evidence.** TypeScript resolves supported package-export cases and retains
  uncertainty for incomplete or ambiguous source facts. Native DTO value allowances can
  select an exact `field_path` and `container_depth` without permitting other positions.
- **Safer amendment output.** Failed or colliding amendment destinations retain widening
  findings. Baseline and graph outputs cannot silently overwrite amendment evidence.
- **Less repository churn.** Generated self-observation snapshots no longer require
  committed updates. Normal CI uses focused checks; exhaustive language, platform and
  report verification runs nightly and before release publication. Report artifacts expire
  after one day, with older retained report artifacts pruned by the cleanup workflow.

## Upgrade from 1.0.0

```sh
uv tool upgrade archkeel
```

Python, TypeScript and Dart analysis use the installed Python package. Dart no longer
needs an SDK, `DART_EXECUTABLE` or `archkeel-dart-setup`. Scans do not download packages
or modify the scanned project. Building or running a Flutter app still requires Flutter.

The Dart migration intentionally drops the legacy `archkeel-dart-directives` producer.
Re-observe both revisions with 1.1.0 before comparing Dart snapshots. This is an explicit
exception to the [1.x compatibility policy](docs/reference.md).
Schemas now accept Dart `mixin` entities and `mixes_in` relationships, while retaining
their existing version identifiers. Update strict enum consumers and pin the CLI,
collectors and bundled schemas together; do not mix the old and new Dart evidence.

## Limits

Static analysis does not prove runtime dispatch, live object identity or complete call
coverage. Compass still has source-resolution gaps; Python RealWorld retains incomplete
class and inheritance evidence; Nest retains unresolved dynamic imports and framework
semantics. The demos show these limits, not compiler parity or verified Flutter execution.
See [demo evidence](https://github.com/rapiddweller/archkeel/blob/4.0.1/docs/architecture-demo.md) and [known limits](docs/known-limits.md).

# Older releases

See the Git history and the GitHub releases.
