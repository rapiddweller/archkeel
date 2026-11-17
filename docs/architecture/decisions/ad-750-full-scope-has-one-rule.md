# AD-750: The `full_scope` flag of a collection has one rule

Status: accepted (owner order, #1451 Wave 5, F5). Structural: no frame, text or page changes.
Part of #880.

Three places decided whether a collection covers the whole scope, each with its own formula:
`Coverage::of` (gaps only), the Python survey (`modules == selected && no gap`) and the Dart
collection (`no gap && some file`).

`Coverage::is_full(gaps, unparsed)` states the rule once: no gap, and no selected file left unparsed.
`Coverage::of` passes `unparsed = 0`, because a collector reports a file it cannot read as a gap. The
Python survey passes the difference between the selected files and the parsed modules. The Dart
collection passes `0` and still requires one file: an empty scope is not a full scope there.

A rule that also demanded `files_parsed == selected` in `of` was tried and rejected: the Dart reply
counts one file fewer than it selects (a part has no file record), so it turned a full Dart reply into a
store refusal. Part files are owned by their library: the imports of the library carry the use of the
part, and an import inside a part is a syntax gap (UNKNOWN), not a pass.

Proof of no change: the frame, status and exit code of 25 runs (the 22 runs of `fixtures/matrix.json`,
the system report, the shell and the native report) are byte-identical before and after on the same tree.
