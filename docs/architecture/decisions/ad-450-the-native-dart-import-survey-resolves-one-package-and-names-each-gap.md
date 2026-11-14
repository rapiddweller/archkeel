# AD-450 The native Dart import survey resolves one package and names each gap

**Status.** Proposed. Part of #880. It extends AD-365, AD-369 and AD-400. No verdict changes.

**Decision.**
1. `native/dart` gets a library target. `survey(&DartRequest)` gives the typed `Survey`: inputs
   with digests, file facts, part owners, import records, their targets, gaps and coverage.
   `typed_reply` assembles it as a reply with the sections `imports` and `unknowns` only.
   The binary calls the library. A valid request still exits 2 with no reply. `collect` still refuses Dart.
2. The survey reads one package: the `pubspec.yaml` at the snapshot root. It parses directives only;
   definitions and sites are not built. A source over 1 MiB is not parsed and gets a gap.
3. Identity. A library file is a selected source without `part of`. Its module is the module of
   the discovery. A part file has no file fact, because a module has one file. Its owner is the
   one library whose `part` URI gives the part file, and the `part of` of the part must name that
   library by URI or by `library` name. An edge of a part is an edge of the owner module.
4. A URI resolves as follows. Each resolved directive gives one record.
   - A relative URI joins the directory of the importer. It must give a selected source.
   - `package:<own>/<path>` gives `lib/<path>`, which must be a selected source.
   - `package:<other>/<path>` gives an external target of the package `<other>`.
   - `dart:<name>` gives the built-in target `dart.<name>`.
   - An `export` gives a re-export record. A deferred import gives a plain import record:
     deferral changes the load time, not the dependency.
   - A conditional import or export gives one record for the default URI and for each
     alternative. The survey never selects one branch. Each alternative resolves by these rules.
5. The survey is complete only with no gap. Each gap is a record of `unknowns` and of the coverage.
   Its message starts with a closed name (`GapName`). Each gap below keeps the scope UNKNOWN.

| Name | Cause |
|---|---|
| `DartTargetMissing` | A relative or own-package URI gives no file. A missing generated file (`.g.dart`, `.freezed.dart`) is named so. |
| `DartTargetNotSelected` | The file exists but is outside the scan roots or is not a source. |
| `DartTargetOutside` | A relative URI leaves the snapshot root. |
| `DartUnsupportedUri` | Another scheme, an absolute path, a query, a fragment or an empty package path. |
| `DartUriNotLiteral` | A URI with interpolation or without a plain string (the `DirectiveError` of the parse). |
| `DartMirrors` | `dart:mirrors`: reflection can reach code without an import. The edge stays. |
| `DartPartUnowned` | A `part of` file that no library claims, or that names another library. |
| `DartPartNotPart` | A `part` URI gives a file without `part of`, or no file. |
| `DartPartConflict` | Two libraries claim one part. |
| `DartWorkspace` | `workspace:` or `resolution: workspace` in the root `pubspec.yaml`. |
| `DartPathDependency` | A `path:` dependency: a local package outside the survey. |
| `DartNestedPackage` | A `pubspec.yaml` below the snapshot root inside a scan root. |
| `DartPackageConfig` | A `package_config.json` or `.packages` file outside `.dart_tool`. |
| `DartParseBudget` | A source over the parse budget of 1 MiB (#1097). |

The discovery and parse gaps stay as they are: a link, an unreadable file or directory, a module
collision, a missing `pubspec.yaml`, a syntax error and bytes that are not UTF-8 (AD-365, AD-369).

**Reason.** The wiring of Dart into `collect` needs an in-process API and a resolver of its own.
AD-400 assembles records from resolver answers that come from outside. A bounded subset with a
named gap for each other case cannot give a PASS that a missing edge hides.

**Rejected.** One branch of a conditional import: it hides the other edges. A gap for each
conditional import: the edges are known, so a gap loses facts. Reading `package_config.json`:
pub writes it from `pubspec.yaml`, so the survey reads the source of truth. A file fact for a part
with the module of its library: the store requires one file for each module.

**Limits.** No `collect` dispatch, store acceptance or scope receipt: the wiring change adds them.
Symbols, calls, references and `show`/`hide` names are not surveyed; the reply does not declare them.
The 1 MiB budget does not bound the time of a smaller hostile file; #1097 stays open.
The grammar parity across wheels (#1031) is unchanged. Parts with their own imports (enhanced
parts) give edges of the owner module, not a gap.

**Tests.** `native/dart/src/survey/*_tests.rs` hold one test for each rule and each gap.
`native/dart/src/survey/fixture_tests.rs` surveys the Dart fixtures and pins the counts of files,
edges and gaps by name. All tests are Cargo tests, so no test shares a dump binary (#1114).
