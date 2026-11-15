# AD-550 Dart names loader tokens and relative package roots

**Status.** Proposed. Closes #1222. Amends AD-542.

**Decision.** Each `spawnUri` identifier in selected Dart source gives `DartIsolate`, even when
no selected directive imports `dart:isolate`. The identifiers `currentMirrorSystem`, `reflect`,
`reflectClass` and `reflectType` give `DartMirrors`. A string or comment is not an identifier.
The gap cites the source token. A direct SDK edge stays in the graph.

A non-own package in `.dart_tool/package_config.json` is external only when its `rootUri` is an
absolute `file:///` URI outside the snapshot. A relative URI can name a local package through a
link. A `file://` URI with a host is not resolved. Both give `DartPackageConfig`.

A hosted dependency named `path` is not itself a local path key. A `path` key inside its value
still gives `DartPathDependency`. Invalid or unsupported YAML still gives a gap.

**Reason.** A hosted package can re-export isolate or mirror APIs. Its consumer can reach those
APIs without a direct SDK import. A relative package root can link back into selected source.

**Rejected.** Treat a relative package outside the root as external. A symlink below it can
resolve an import into the root. Treat only direct SDK imports as evidence of a loader.

**Limits.** Absolute external package roots stay external under the outside-code premise of
AD-542. This change does not resolve the code of an external package or its links. The owner
must make the premise visible in the report scope before it relies on this proof.

**Tests.** `import_survey/review_tests.rs` plants relative and hosted roots, the URI authority,
the isolate token and all four mirror tokens. `package.rs` plants a hosted `path` dependency and
a local path under the same name. The #1222 review corpus supplies runtime mutation plants.
