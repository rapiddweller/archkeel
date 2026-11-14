# AD-450 The native Dart import survey resolves one package and names each gap

**Status.** Proposed. Part of #880. It extends AD-365, AD-369 and AD-400. No verdict changes.

**Decision.**
1. `native/dart` gets a library target. `survey(&DartRequest)` gives the typed `Survey`: inputs
   with digests, file facts, part owners, import records, their targets, named gaps and coverage.
   `typed_reply` assembles it with the sections `imports` and `unknowns` only, and the provenance of the caller.
   The binary calls the library. A valid request still exits 2 with no reply. `collect` still refuses Dart.
2. The survey reads one package: the `pubspec.yaml` at the snapshot root. It parses directives only;
   definitions and sites are not built. A request with `exclude_test_sources` is refused.
3. Identity. A library file is a selected source without `part of`. Its module is the module of
   the discovery. A part file has no file fact, because the store requires one file for each module.
   Its owner is the one library whose `part` URI gives the part file, and the one `part of` of the
   part must name that library by URI or by the whole `library` name. An edge of a part is an edge of
   the owner module. The grammar refuses an import in a part, so that part gets a syntax gap.
4. A URI resolves as follows. Each resolved URI gives one record.
   - A relative URI joins the directory of the importer. It must give a selected library.
   - `package:<own>/<path>` gives `lib/<path>`, which must be a selected library.
   - `package:<other>/<path>` gives an external target of the package `<other>`.
   - `dart:<name>` gives the built-in target `dart.<name>`.
   - An `export` gives a re-export record. A deferred import gives a plain import record:
     deferral changes the load time, not the dependency.
   - A conditional import or export gives one record for the default URI and for each
     alternative. The survey never selects one branch. Each alternative resolves by these rules.
5. The survey is complete only with no gap. Each gap is a record of `unknowns` and of the coverage.
   Its message starts with a closed name (`GapName`). Each gap keeps the scope UNKNOWN.

| Name | Cause |
|---|---|
| `DartTargetMissing` | A relative or own-package URI gives no file. A missing generated file (`.g.dart`, `.freezed.dart`) is named so. |
| `DartTargetNotSelected` | The file exists but is outside the scan roots or is a link. |
| `DartTargetOutside` | A URI leaves the snapshot root, or `lib` for the own package. |
| `DartTargetIsPart` | An import or export gives a part file. |
| `DartTargetUnparsed` | The target has no proven module: a syntax error, the parse budget or a module collision. |
| `DartUnsupportedUri` | Another scheme, an absolute path, a query, a fragment, an escape or an empty package path. |
| `DartUriNotLiteral` | A URI with interpolation or without a plain string, also in a conditional alternative. |
| `DartMirrors` | `dart:mirrors`: reflection can reach code without an import. The edge stays. |
| `DartPartUnowned` | A `part of` file that no library claims, or that names another library. |
| `DartPartNotPart` | A `part` URI gives a library. |
| `DartPartConflict` | Two libraries claim one part. |
| `DartWorkspace` | `workspace:` or `resolution:` in the root `pubspec.yaml`. |
| `DartPathDependency` | A `path:` key in the root `pubspec.yaml`: a local package outside the survey. |
| `DartNestedPackage` | A `pubspec.yaml` inside a scan root. |
| `DartPackageConfig` | A `pubspec_overrides.yaml`, `package_config.json` or `.packages` outside `.dart_tool`. |
| `DartParseBudget` | A source over the parse budget of 1 MiB is not parsed (#1097). |

The discovery and parse gaps stay as they are: a link, an unreadable file or directory, a module
collision, a missing `pubspec.yaml`, the SDK constraint, a syntax error and bytes that are not UTF-8.

**Reason.** The wiring of Dart into `collect` needs an in-process API and a resolver of its own.
AD-400 assembles records from resolver answers that come from outside. A bounded subset with a
named gap for each other case cannot give a PASS that a missing edge hides.

**Rejected.** One branch of a conditional import: it hides the other edges. A gap for each
conditional import: the edges are known, so a gap loses facts. Reading `package_config.json`:
pub writes it from `pubspec.yaml`, so the survey reads the source of truth.

**Limits.** No `collect` dispatch, store acceptance, scope receipt, build provenance or test
feature list: the wiring change adds them. Symbols, calls, references and `show`/`hide` names are
not surveyed. The budget does not bound memory or time; #1097 stays open. On the release build a
1 MiB source of 520,000 tokens takes 1.8 s and 1.0 GiB; 100 KB of nested classes takes 4.7 s.
The grammar parity across wheels (#1031) is unchanged. The self-check pins four new method-call pair gaps.

**Tests.** `native/dart/src/import_survey/*_tests.rs` hold one test for each rule and each gap.
`fixture_tests.rs` pins the files, parts, edges and gaps of the four Dart fixtures. A test checks
that this table names each `GapName`. All tests are Cargo tests and share no dump binary (#1114).
