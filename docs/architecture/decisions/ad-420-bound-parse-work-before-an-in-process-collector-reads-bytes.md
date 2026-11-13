# AD-420 Bound parse work before an in-process collector reads bytes

**Status.** Accepted. Issue #1111, part of #880. It follows AD-406.

**Decision.** The snapshot owns a linear per-file input charge, enabled by the composition.
The unit is **bytes + tokens**, each counted once, not once per later byte.
An ASCII word run is one possible token. Each other non-space byte is one possible token.
The bound is **8,388,608 byte/token units**. The existing per-file byte cap is 4 MiB.
At most two units per byte means every ordinary file up to that byte cap fits the charge.
Width alone must not refuse a generated client, declaration file or data table.

One scan can retain at most **64 MiB distinct input bytes** across all snapshot reads.
Charge a normalized path once, keyed by snapshot root. Distinct source aliases keep their own charge.
If a later read grows, charge only the growth. Check the per-file limits on every read.
Nested boundaries share the total. Repeated resolver, manifest and parser reads do not spend it again.

Bound the non-linear depth paths separately at **512 nesting levels**, not by file width.
A linear pre-pass checks paired delimiters before parsing. It skips comments and literal text,
including raw strings, and enters template interpolation expressions.
The TypeScript parser also checks actual tree depth before the syntax and fact walks.
This covers JSX and type constructs that a delimiter-only pre-pass cannot classify.

The snapshot records the first `WorkLimit` on the collector thread.
It gives no bytes on that read or any later read in that run.
The composition discards the whole result, even if the collector has already made facts.
It returns the typed `RefusalKind::ParseWork`, with the name `parse_work_limit`.
The core returns exit 2 and writes no frame. The shell writes no artifact.
The core writes the closed `archkeel-core-refusal-1` message on stderr.
The shell decodes its typed `kind` into `GapKind.PARSE_WORK_LIMIT`, not from a text prefix.
An ordinary unsupported part keeps the existing named UNKNOWN path.
These checks use no platform API and apply on macOS, Linux and Windows.

**Reason.** The initial cumulative-token charge was quadratic and refused honest 100 KB files.
It confused width with nesting. Count bytes and tokens linearly; bound actual depth separately.
The 817 MiB comment reproduction was aggregate retention, not a measured quadratic parse path.
The six deep files and one 1.5-million-level file reached 3 772.5 and 1 361.9 MiB before the guard.
Keep only the union of referenced source ranges and release parser caches. Keep all evidence.
Only the composition enables these limits. Subprocess collectors keep their existing host bounds.

**Rejected.** Cumulative-token charging: ordinary generated code must remain linear.
A process RSS limit alone: APIs differ. A timeout is not a deterministic input bound.
Tree depth alone: the primary deep-delimiter inputs must be stopped before parsing.

**Limit.** These are work, depth and distinct-input bounds, not an absolute process RSS cap.
Flat files with many facts can exceed 300 MiB: the 4 MiB function probes reached 797/966 MiB.
The 300 MiB tests cover the hostile shapes and the exact-64-MiB comment workload, not every file.
The lexical pre-pass is not a complete language grammar; the parser still decides syntax.
Future parse workers must share the scan total. This change enables no parallel parsing.
Use readable thread-owned state, not the opaque macro that held all 63 self-core PASS rows.

**Tests.** Function-style and data-table files at 100 KB, 1 MB and one byte below 4 MiB,
in both profiles, give the complete unguarded frame. All 12 also match main except build provenance.
The repeated-manifest project exceeds 64 MiB of reads but has about 1 MiB distinct input and completes.
Per-file plants in both profiles and a Rust scan-total plant hide a later forbidden edge: exit 2, no PASS.
Keep the unchanged 63 PASS / 1 FAIL / 19 UNKNOWN self-core rows and collector import records.

**Way back.** Do not add a bypass or widen a proof rule. If a legitimate construct reaches the depth limit,
add it to the main-frame parity tests, measure its parser and fact memory, and fix that path first.
Then raise or remove that depth bound with release RSS evidence. Keep the 4 MiB and 64 MiB units explicit.
