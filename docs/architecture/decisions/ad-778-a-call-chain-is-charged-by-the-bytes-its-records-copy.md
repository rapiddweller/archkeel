# AD-778 A call chain is charged by the bytes its records copy

**Status.** Accepted. Part of #880 (lead decision of 2026-11-17, closes #1347). Visible change: a TypeScript file whose site records would copy more than 64 MiB of expression text keeps no site record and gets a named gap.

**Reason.** The record of each call and reference site holds the text of its expression, and its id is a SHA-256 over that text. A chain `a.b().b()...` of n calls gives n sites whose texts grow by one link each, so one file costs the sum of these lengths: the square of the chain. The id and the title are part of the fact contract and stay as they are. A real chain is short (4,000 calls take 0.19 s). A hostile or generated file within the 4 MiB file limit, about a million calls, would copy and hash terabytes: a hang.

**Decision.**
1. `site_charge::charge` sums, for each file, the expression length of every site (a node text, or receiver, dot and name) before any record is made.
2. The limit is `MAX_RECORD_TEXT` = 2^26 bytes (64 MiB) per file. The highest real value is 180,956 bytes (`packages/excalidraw/components/App.tsx`, Excalidraw v0.18.1; 679 files; the generated `woff2-bindings.ts` reaches 173,879). graphql-js v16.15.0 reaches 18,670 and the showcase fixtures 2,160. The limit is about 370 times the highest real value and bounds the cost of one file to about a second. A chain of 5,000 calls (50 MB) keeps its records; 20,000 calls (800 MB) and 200,000 calls (80 GB) are refused by name. The `sites-chained-calls` scaling shape therefore has 5,000 calls.
3. Over the limit, the file keeps its imports, its definitions and its other facts, but no site. The gap reads "The call chain at line N is too long to record: X bytes of receiver text exceed the work limit of 67108864 (its own text has Y bytes): <file>". Every rule that needs the sites of that scope is UNKNOWN.
4. A frame of real code does not change: below the limit the charge does nothing.

**Rejected.** Hashing a digest instead of the text, or capping the text: both change ids and titles that 4.0.1 produced. A time limit: wall time is not reproducible.

**Tests.** `site_charge.rs` (5,000 calls below the limit, 20,000 above, the longest site), `collect_tests.rs` (a 200,000-call file is a gap and the other file is collected), `tests/test_cli_native_core_scan_large.py::test_a_long_call_chain_is_a_named_gap` (slow tier).
