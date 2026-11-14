# AD-454 The native Dart import survey resolves one package and names each gap

**Status.** Proposed. Part of #880. It extends AD-365, AD-369 and AD-400. No verdict changes.

**Decision.**
1. `native/dart` gets a library target. `survey(&DartRequest)` gives the typed `Survey`: inputs
   with digests, file facts, part owners, import records, their targets, named gaps and coverage.
   `typed_reply` assembles it with the sections `imports` and `unknowns` and the caller provenance.
   The binary still exits 2 with no reply on a valid request. `collect` still refuses Dart.
2. The survey reads one package: the root `pubspec.yaml`. It parses directives only. It refuses
   `exclude_test_sources`. Parse bounds (#1097): 1 MiB and 131,072 possible tokens for each source,
   bracket depth 900 (the tree limit) and 32 MiB in total.
3. Package configuration. An absent `.dart_tool/package_config.json` (no `pub get` yet) keeps the
   language rule: the own package is `lib/`. A present file is an input; it must map the own
   package to the root and `lib/`, and each other package outside the root.
4. Identity. A library file is a selected source without `part of`. Its module is the module of
   the discovery. A part file has no file fact, because the store requires one file for each module.
   Its owner is the one library whose `part` URI gives the part file, and the one `part of` of the
   part must name that library by URI or by the whole `library` name. An edge of a part is an edge of
   the owner module. The grammar refuses an import in a part, so that part gets a syntax gap.
5. A URI resolves as follows. Each resolved URI gives one record.
   - A relative URI joins the directory of the importer. It must give a selected library.
   - `package:<own>/<path>` gives `lib/<path>`, which must be a selected library.
   - `package:<other>/<path>` gives an external target of the package `<other>`.
   - `dart:<name>` gives the built-in target `dart.<name>`.
   - An `export` gives a re-export record. A deferred import gives a plain record (load time only).
   - A conditional directive gives one record for the default URI and for each alternative.
6. The survey is complete only with no gap. Each gap is a record of `unknowns` and of the coverage.
   Its message starts with a closed name (`GapName`).

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
| `DartIsolate` | `dart:isolate`: `Isolate.spawnUri` can run another library. The edge stays. |
| `DartPartUnowned` | A `part of` file that no library claims, or that names another library. |
| `DartPartNotPart` | A `part` URI gives a library. |
| `DartPartConflict` | Two libraries claim one part. |
| `DartWorkspace` | `workspace:` or `resolution:` in the root `pubspec.yaml`. |
| `DartPathDependency` | A `path:` key in the root `pubspec.yaml`: a local package outside the survey. |
| `DartNestedPackage` | A `pubspec.yaml` inside a scan root. |
| `DartPackageConfig` | `pubspec_overrides.yaml`, `package_config.json` or `.packages` outside `.dart_tool`; a link, unreadable or malformed `.dart_tool` file, or one that breaks rule 3. |
| `DartParseBudget` | A source over a parse bound of rule 2 is not parsed. |

The discovery and parse gaps stay: link, unreadable file or directory, module collision, missing
`pubspec.yaml`, SDK constraint, syntax error, bytes that are not UTF-8.

**Reason.** The wiring of Dart into `collect` needs an in-process API and a resolver of its own
(AD-400 takes resolver answers from outside). A named gap for each other case hides no edge.

**Rejected.** One branch of a conditional import hides edges; a gap for each loses known edges.
A gap on each present `.dart_tool` file: each project after `pub get` has one.

**Limits.** No `collect` dispatch, store acceptance, scope receipt, build provenance or test
feature list: the wiring change adds them. Symbols, calls, references and `show`/`hide` names are
not surveyed. Release build, worst case below the bounds: a dense source of 131,072 tokens takes
0.4 s and 131 MiB peak. Grammar parity (#1031) is unchanged. The self-check pins new pair gaps.

**Closed by AD-468.** A part has no file fact; its edges belong to its library. A part whose path
module and library have other components makes the scope of the run incomplete.

**Tests.** `import_survey/*_tests.rs`: one test for each rule and gap; the fixture edge sets and
gap names are pinned; a test checks this table. Cargo tests only, no shared dump binary (#1114).
