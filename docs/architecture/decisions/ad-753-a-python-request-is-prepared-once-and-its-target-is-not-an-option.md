# AD-753: A Python request is prepared once and its target is not an option

Status: accepted (owner order, #1451 Wave 5, F7). Structural: no frame, text or page changes.
Part of #880. AD-742 was taken on main, so this record takes AD-753.

`prepare` in `lib.rs` and `prepared` in `dump.rs` each cloned a request and wrote
`resolver.interpreter = Some(..)` into it. Three readers (`survey`, `modules`, `provenance`) then
unwrapped the `Option` with `ok_or("no Python target")`, and the source of the target was a separate
argument through `reply`, `typed`, `parts` and `provenance`. Nothing stopped a reader from getting an
unprepared request.

`Prepared` (in `requirement.rs`) holds the request, the interpreter and the source of the target.
`Prepared::of` is the one place that selects the target. The survey, the replies and the dumps take a
`&Prepared`, so the `ok_or("no Python target")` unwraps and the `source` arguments are gone, and
`verify` compares two `Prepared` values. `--dump-scope` selects its target by the same function.

Proof of no change: the frame, status and exit code of the matrix runs, the system report, the shell and
the native report are byte-identical before and after on the same tree.
