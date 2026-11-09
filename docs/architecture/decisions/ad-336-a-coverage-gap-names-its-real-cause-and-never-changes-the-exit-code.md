# AD-336 A coverage gap names its real cause and never changes the exit code

**Decision.** `gap_diagnostic` in `check/gap_diagnostics.py` derives the diagnostic kind of a
coverage gap from the record of the gap. Before this decision every gap was a `parse_error` with a
TypeScript remedy. Excalidraw parsed 519 of 519 files and still gave 2631 `parse_error`
diagnostics. The cause was a missing `node_modules`. The user could not act on the text. This is a
finding of epic #880.

**Rule.** Prefer a structured field over a title. A title is matched only when the producer
gives no structured field. The title parts that the host matches are the constants of `GapTitle`
in `ir/protocol.py`. The collectors build their titles from the same constants, so a rewording
changes both sides. A test checks that the native collector (`imports.rs`) repeats them.

| Record of the gap | Kind |
|---|---|
| Dart kind `SyntaxError`, `syntax_error`, `invalid_encoding` | `parse_error` |
| Python file failure (area `analysis_coverage`, title ends `could not be analyzed`) | `parse_error` |
| TypeScript title `Syntax error in` | `parse_error` |
| Title `Unresolved module:` or `Unidentified external package`; Dart kind `ImportError` | `unresolved_import` |
| Title `... has no unique unconditional publication`; the native title `Script-global dependencies are not examined...`; Dart kind `Unsupported*` | `not_examined` |
| Every other gap, for example a local alias, `DirectiveError`, a host gap, an unreadable file | `incomplete_scan` |

1. The exit code and the verdict do not change. An incomplete scan stays incomplete: coverage is
   `FAIL`, the exit code is 2. Only `kind` and `remedy` change.
2. The fallback is `incomplete_scan`, not `parse_error`. A reason that this table does not know is
   not proven to be a parse failure. `DirectiveError` also covers unresolved imports, so it is
   `incomplete_scan`.
3. Each kind has its own remedy. `not_examined` says that a change in the project may not help.
4. A test lists every title template of every producer and its kind. A second test compares the
   Python constant of the native title with `GLOBALS_UNEXAMINED` in `imports.rs`.

**Schema.** [AD-138](ad-138-json-results-have-a-published-schema.md) says that an enum change is
breaking. So the three kinds need `schema/command-result-12.0.schema.json`. It differs from 11.0
only in the diagnostic kind. It cannot wrap 11.0 by `$ref`: a schema that a `$ref` names cannot
have its enum widened, and 6.0 is pinned. So it copies the chain and both architecture-command
schemas. A test rebuilds the file from the published schemas, so a copy cannot drift. Schemas 6.0 to 11.0 stay byte-exact: a test pins their digests. An
exception for an in-place edit of 6.0 is not allowed, because the pin exists to stop it. A result
that has a new kind validates against 12.0 only. Every older result validates against 11.0 and 12.0.

**Rejected.**
- **Add a reason code to each gap record.** It changes the wire, the digests and three collectors.
- **Let `not_examined` pass the scan.** The owner decided that an incomplete scan stays incomplete.
- **Widen 6.0 in place.** It breaks AD-138 and the pin.

**Limit.** The title match for the TypeScript and native producers is text-based. A reworded
title moves to `incomplete_scan`; it never changes a verdict.

Proof: [test_gap_diagnostics.py](../../../tests/test_gap_diagnostics.py).
