# AD-1140 The Explorer snapshot carries entry points that manifests and files prove

**Status.** Accepted. Builds on AD-1117 and AD-1017. Closes #2040. Part of #687.

**Decision.** An Explorer scan adds `entry_points` to each part of the `explorer` frame part.
The value is `null` when the scan has no reader for the language (Dart). Otherwise it holds
`entries` and `unread`. Each entry has `kind`, `basis` (`declared` or `observed`), `name`, `target`
and `evidence` (`path` and, for a manifest, `key`).

The sources are fixed and proven by a file:

| Language | Declared | Observed |
|---|---|---|
| Python | `[project.scripts]`, `[project.gui-scripts]` of `pyproject.toml` | a `__main__.py` file |
| Rust | `[[bin]]` of a `Cargo.toml` | the files `main.rs` and `bin/*.rs` below `src`, and `bin/*/main.rs`, of a crate where Cargo finds binaries itself |
| TypeScript | `bin`, `main` of a `package.json` | none |

The Python collector reads `pyproject.toml` (`archkeel_python_collector::scripts`). `archkeel-collect`
reads `Cargo.toml` and `package.json` (`entry_points.rs`) from the manifest of each directory above a
scanned file. The core projects the typed value. The Studio shell renders it and holds no rule.

A manifest that cannot be read is named in `unread`. The list is then unknown, never empty.
An empty `entries` with an empty `unread` means only: none of the forms above exist. Other forms
(`setup.py`, a framework command, a `main` function that no manifest names) are not read.
A `[[bin]]` without `path` has `target` null, because Cargo can find the file in two places.
Cargo finds binary files itself unless `autobins` is false, or the package is edition 2015 and
declares a `[[bin]]`. An inherited edition with a `[[bin]]` is unknown and goes to `unread`. A declared
name or path hides the matching file, so the scan never shows a binary that Cargo does not build.

**Reason.** The facts were collected already. The Explorer did not project them, so a newcomer
could not see how the project starts. Each entry cites its file or its manifest key. A guess is
never an entry.

**Limit.** No verdict, rule or user contract changes. The scan reads at most 500 manifests, each
at most 1 MiB. `NATIVE-EXTERNAL-TOML` names `archkeel_collect.entry_points` because it reads the
`[[bin]]` tables; `pyproject.toml` stays with the Python collector. Dart has no reader.

**Tests.** The unit tests of `entry_points.rs` and `requirement_tests.rs` cover each source, a
project without evidence and an unreadable manifest. `tests/test_explorer_entry_points.py` runs the
core on a Python and a Rust project and reads the Studio snapshot.
