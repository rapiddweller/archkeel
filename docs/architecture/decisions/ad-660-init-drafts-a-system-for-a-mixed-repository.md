# AD-660: `init` drafts a system for a mixed repository

## Context

A repository with several languages (a Python service and a Dart app; a Python platform with two
TypeScript apps) needs the system view of AD-616 to AD-620: one part for each language area, with
the verdict, the parts and the drill-down. Until now `init` drafted one configuration, and a mixed
repository got one language or a refusal.

## Decision

1. `init`, and the auto-init of `validate` and `report` (AD-638), find the language areas by folder
   layout and manifest only (depth three, no hidden or generated folder): a Python project
   (the repository root, or a folder with `pyproject.toml` or `setup.py`), a Cargo workspace
   (`Cargo.toml` with `[workspace]`), a `package.json` with `workspaces` (one area, its members are
   components) or with a `tsconfig.json` (one area), and a `pubspec.yaml` with `lib` (one area).
2. One area is drafted as before: `archkeel.toml`, a contract and its page at the root. Several
   areas are drafted as a system: `docs/architecture/architecture-system.json` (AD-616) with one
   part for each area, and for each part `archkeel.toml`, a contract and a page in
   `docs/architecture/<part>/`. The ids of the rules and the components carry the part id, because
   a system refuses an id that two parts use. The responsibilities of a part are `TODO` lines.
3. A part is one scan. Each part has its own namespace and roots, and its components follow its
   layout: the subpackages of a Python package, the crates, the workspace packages, the folders of a
   TypeScript project (the folders inside `src` count instead of `src`), the folders of Dart `lib`.
   Files beside the components are the component `root`.
4. **TypeScript: one part for each project, not one part for two apps.** A scan has one `tsconfig`,
   one module resolution and one namespace, and two apps have their own `tsconfig` and their own
   deployment. One part for each app makes each verdict and each cycle belong to one app, and the
   system view shows the apps as boxes. Several packages of one `workspaces` list share a root and
   are components of one part. The scan root of a TypeScript project is the project folder, not
   `src`, so that an import of a file beside `src` is a module of the scan.
5. A Python scan has one root folder, and its namespace must be the name of that folder. A folder
   without `src` gives one scan for each top-level package. Below `src`, one scan of `src` with one
   component for each folder that holds Python (a folder without `__init__.py` is a namespace
   package that the scan reads), or the scan of the only folder.
6. Interfaces: the manifests name no crossing. The draft names one only where a schema file lies in
   the folder of one area (OpenAPI, Swagger, AsyncAPI, a proto file): each other part is a candidate
   caller, as an interface with the title `TODO: confirm that <part> uses <file>`. A system interface
   needs an existing schema file, so none is drafted without one, and the output says so.
7. The default configuration lookup: without `archkeel.toml`, the system document
   `docs/architecture/architecture-system.json` is the configuration of `validate` and `report`. With
   `archkeel.toml`, that file wins, and `init` prints the `--config` for the system.
8. `exclude_test_sources = true` is drafted for a TypeScript scan: the `tsconfig` of a project leaves
   its test files out, and each file left out is a coverage gap that makes the whole scope unknown.
   The result says that tests are not scanned.
9. The topology of a report: an import that resolves to a file that is no module of the list (a JSON
   or asset file, a file beside the root) is an `external` edge. Before, it was a `resolved` edge
   without a module row, and the shell refused the whole report ("a module edge names no listed
   module"). Found on a real TypeScript project; it blocked each report of a project that imports JSON.

## Alternatives and limits

- Reading the source to find crossings (an HTTP client that names a server). Not done: `init` reads
  no source (AD-626); the user adds the interfaces.
- Several top-level packages at one root as one part: impossible, a scan has one namespace.
- A Dart package below the repository root gives the named gap `DartNestedPackage` (the Dart
  collector resolves package URIs only at the snapshot root), so its assignment rule is UNKNOWN.
- A Python scan below `src` that holds other languages' folders (`src/ui`) gives a component for
  each folder with Python code, also a test folder of the other part.
- The draft decides nothing: a real cycle or a real unowned module is shown as FAIL.

## Checks

`tests/test_cli_system_init.py`: a plant of Python, TypeScript, Dart and Cargo areas gets four
parts, the interfaces of a spec file, the system run through the default lookup, one block and no
violation, a page; an existing `archkeel.toml` is kept; `--no-init` names the parts. A TypeScript
plant that imports JSON renders its report.
