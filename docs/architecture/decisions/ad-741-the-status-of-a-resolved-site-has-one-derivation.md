# AD-741: The status of a resolved site has one derivation

Status: accepted (owner order, #1451 Wave 5, F4). Structural: no frame, text or page changes.
Part of #880.

The TypeScript resolver, the TypeScript construction and base records, the Dart construction record and
the Python call and construction records each turned "how many targets, and are they proven unique"
into `Resolved`, `PartiallyResolved` or `Unresolved` with their own `if` or `match`.

`Status::of_candidates(candidates, unique)` in `archkeel-facts` states it once: no target is
`Unresolved`; one proven-unique target is `Resolved`; every other case is `PartiallyResolved`. The
collectors call it where they derived a status from a count. The reason text of each site stays with its
collector, because the text is part of the frame and differs by language.

Left as it was, on purpose: the Dart site status of `targets.rs` also depends on whether the site is a
call, whether the target is a method or function and whether the analyzer resolved it. Those are rules
of the Dart language, not a count, and folding them into the shared function would change a frame.

Proof of no change: the frame, status and exit code of 25 runs (the 22 runs of `fixtures/matrix.json`,
the system report, the shell and the native report) are byte-identical before and after on the same tree.
