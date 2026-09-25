# AD-107 A module's file is its evidence, even when the file is empty

`root_layout`, `complete_assignment` and a component `namespace` judge a module by its own file.
Their violation cites the module fact, and that fact's evidence is the file: line 1 with its text
when line 1 holds text, otherwise line 0, which cites the file itself with `end_line` 0, column 0
and an empty excerpt. `file_evidence` in `analyzer/embedded/source.py` writes it for the Python
and the Dart profile. The trace check in `ir/trace.py` accepts exactly that form of line 0; a
cited line from 1 on must still carry its text.

## Why

Issue #153: root `sample` allows only `sample.keep`, and `sample/extra/__init__.py` is added.
`archkeel report --only violations --rule ROOT-LAYOUT --json`, then the AD-11 shop sample:

| Unexpected child | main | this change |
|---|---|---|
| `sample/extra/__init__.py` with a docstring | exit 0, FAIL, `VIO-ffe8dc9f2f3744e0` | same |
| `sample/extra/__init__.py` empty | exit 2, UNKNOWN | exit 0, FAIL, `VIO-ffe8dc9f2f3744e0` |
| `shop/extra/__init__.py` empty | exit 2, UNKNOWN | FAIL: `ROOT-LAYOUT` |
| `shop/stray.py`, a blank line, then `VALUE = 1` | exit 2, UNKNOWN | FAIL: `ASSIGNMENT-COMPLETE`, `ROOT-LAYOUT` |

The module fact quoted line 1 of the empty file as `line: 1, excerpt: ""`. The trace check
requires a quoted line to show text, so one violation made the whole run UNKNOWN with
`violation records lack a complete rule/fact/source trace`, although AST coverage was 100% and
the package exists. Issue #153 reports the same for the DATAMIMIC EE probe: 16 unexpected root
children, exit 2 because two of them have empty initializers. `docs/rules.md` listed the
blank-first-line case as a limit of `complete_assignment`.

## Rejected

- **Accepting an empty excerpt anywhere.** An import line without text proves nothing, and the
  check would stop catching a location that points past the end of a file.
- **Filler text,** such as the path or `<empty>`: an excerpt claims to quote the source.
- **Skipping blank files,** as `complete_assignment` does for ownership: an empty `__init__.py`
  still makes a package, and a layout rule that ignored it would pass a forbidden child.
- **The first non-blank line:** an arbitrary line of code proves the file no better than the
  file does, and an empty file has none.
- **A new evidence field** for file versus line: a schema change for every consumer, where no
  line is numbered 0.
- **Line 0 for every module:** every report row would lose its first line and every module
  evidence id would change, for no gain.

## Limit

The trace check is structural: it cannot tell whether a fact needed a line, so an observation
citing line 0 for an import would pass it. Only `file_evidence` writes line 0. The HTML report
shows such a location as the file alone. Blank files stay exempt from `complete_assignment`.
The observation schema stays 1.3.0 because its fields are unchanged; `line` and `end_line` now
allow 0, and analyzer version 0.52.0 marks the new output. All 71 of Archkeel's own files start
with their license header, so its self-observation keeps every evidence entry.

## Check

`tests/test_file_evidence.py` pins the same `root_layout` violation, and FAIL from
`inspect_observation`, for an `__init__.py` holding a docstring, nothing, one newline, or a blank
line before code; a blank-first-line module under `complete_assignment`; an empty module outside
its `namespace`; and an empty Dart library. `tests/test_trace.py` still rejects a cited line
without text and a malformed line 0. The AD-11 rows `class-a-root-layout-empty-package` and
`class-a-root-layout-blank-first-line` run it on the shop sample, and `tests/test_html_report.py`
reads the first row's location as the file alone.
