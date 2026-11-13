# AD-420 Bound parse work before an in-process collector reads bytes

**Status.** Accepted. Issue #1111, part of #880. It follows AD-406.

**Decision.** The snapshot owns a conservative parse-work charge. The composition crate
enables it on the collector thread before it calls any linked collector.
For each byte, add one plus the number of possible tokens seen so far.
An ASCII word run counts once. Other non-space bytes count individually.
The limit is 1 073 741 824 units per file. The existing 4 MiB byte limit also applies.
The check runs before the snapshot gives bytes to a parser. It allocates no syntax tree.
Quotes, comments and closing brackets cannot reduce the charge.
The possible-token count bounds token nesting without a language lexer.
Deep input has a quadratic charge. Long words retain the byte limit.

The snapshot records the first `WorkLimit` on the collector thread.
It gives no bytes on that read or any later read in that run.
The composition discards the whole result, even if the collector has already made facts.
It returns the typed `RefusalKind::ParseWork`, with the name `parse_work_limit`.
The core returns exit 2 and writes no frame. The shell writes no artifact.
An ordinary unsupported part keeps the existing named UNKNOWN path.
The bound applies on macOS, Linux and Windows. It needs no platform API.

**Reason.** The repository survey does not bound parser work within a file.
The charge must apply to every collector that the composition calls, including Rust.
The snapshot is the shared contained-read boundary. A collector must not read files itself.
Only the composition enables the bound. Subprocess collectors keep their host bounds.

**Rejected.** A process memory limit alone: the available APIs differ across platforms.
A source-text delimiter depth: strings, comments and repairs can hide or invent delimiters.
A tree-depth check after parsing: the parser has already allocated the hostile tree.
A parser timeout: it is not deterministic and is not a memory bound.

**Limit.** This is a per-file work bound, not an absolute process RSS bound.
It conservatively charges wide files and text in comments too.
It does not enable parallel parsing. A future collector thread must enter the same boundary.
The repository survey still bounds entries, directory depth and total file bytes.
Stage 1 retains the Python decision for accepted files. A refused file has no verdict.

**Tests.** The snapshot tests check charge edges, hidden delimiters and result discard.
The composition test compares every fact just below the bound with the unbounded producer.
The core test checks exit 2 and no frame after a work refusal.
The release integration tests check six deep files, one file 1.5 million levels deep,
the named refusal, no artifact, and the measured peak memory bound.
