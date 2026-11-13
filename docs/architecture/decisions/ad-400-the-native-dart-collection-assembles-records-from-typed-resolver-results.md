# AD-400 The native Dart collection assembles records from typed resolver results

**Status.** Accepted. Epic #880, Dart slice 4c. Initially stacked on #1093; now based on its merged AD-392.
PR #1102 owns number 398. Reserve number 400 as the lead requests.

**Decision.** Port all remaining functions of `analyzer/dart/collect.py` as one assembly layer.
The Python file has 1 538 lines. Slices 4a and 4b port 116 and 529 function lines.
This slice ports the remaining 819 function lines. No collection function remains in Python only.
Discovery and parsing already exist. `resolve.py` stays Python until 4d; typed results cross that seam.
The dump compares collection state and the final source metadata, files, targets and coverage.
It is not a registered collector reply. The store still refuses Dart replies.

**Cut, source ranges on `9622f5cc7`.**
`collect` 121–130 (10); `__init__` 134–164 (31); `facts` 166–169 (4);
`_prepare_sources` 171–207 (37); `_collect_records` 209–216 (8);
`_resolver_gaps` 218–228 (11); `_source_facts` 230–288 (59);
`_language_overrides` 346–383 (38); `_imports` 790–866 (77);
`_bases` 868–935 (68); `_canonical_target` 937–945 (9); `_sites` 947–965 (19);
`_binding_sites` 967–1039 (73); `_site_record` 1041–1119 (79);
`_site_target_state` 1121–1188 (68); `_construction_record` 1191–1217 (27);
`_scope` 1219–1263 (45); `_binding_name` 1265–1267 (3); `_symbol_kind` 1269–1271 (3);
`_duplicates` 1273–1312 (40); `_finalize_inventories` 1314–1333 (20);
`_files` 1335–1358 (24); `_cite` 1360–1363 (4); `_gap` 1365–1415 (51);
`_selected_symbols` 1439–1447 (9); `_file_span` 1537–1538 (2).

**Literal Python rules.**
1. Preparation keeps selected sources, but removes unparsed files and files without a unique owner.
   Parts inherit their owner's module and have no independent file fact.
2. Parse gaps precede snapshot problems and SDK gaps. A repeated gap keeps its first evidence.
3. Missing language overrides are allowed. Compare the first matching override of each file.
4. Resolve every conditional import target. Apply ordered show/hide intersections literally.
5. Bind local imports to selected files, then builtins, external packages or an unresolved target.
6. Canonicalize an alias only with exactly one name result. A mixin base must prove mixin capability.
7. Collect bindings before calls and references. Preserve closure scopes, initializer suppression,
   accessor names, read/write splitting and constructor status precedence.
8. Duplicate declarations keep their records but lose uniqueness and duplicate attributes.
   Incomplete inventories become partial. Unsupported SDK constraints remove inventories entirely.
9. Sort final sections and evidence by identity. Source coverage keeps every selected file.
   `full_scope` is false with any gap or no selected sources.

**Stricter cases.** Missing, repeated or inconsistent typed resolver results give
`CollectionInputGap`, never a guessed target. Work exhaustion gives `CollectionWorkLimit` and
no partial records. Every loop and copied text is charged. There is no recursive assembly walk.
Python's unbounded integer language versions keep the existing named digit limit.
The test-only dump accepts no unknown field or enum member.

**Bounds.** Charge one budget of `min(2^34, 2^20 + 128 * N)` for N serialized typed-input bytes.
Reserve each loop, copy and final sort before work. Index scopes by file and name; preserve first-on-tie selection.
Assembly has no recursive walk. Closed typed decoding uses serde_json's 128-level depth bound.
The 64/128-file scope test checks linear charged work. A 4 MiB hostile name stops within ten seconds.

**Limits.** The Python oracle supplies the typed resolver results; this does not port resolution.
Its repeated whole-site scans remain quadratic. The tool reuses real site answers, not assembly records.
Private input: 184 123 bytes, 120 definitions, 946 members, 10 681 sites; 94.15 s before, 41.40 s after caching.
Native takes 2.62 s after caching. Per-file timings and resumable output support 900 s corpus commands.
4d must port the resolver, connect the snapshot pipeline, and review whole-project limits before
slice 5 registers a Dart reply. Codec normalization belongs to facts/wire, not record assembly.

**Rejected.** Port the resolver in the same slice: it adds 2 013 lines and hides the assembly seam.
Copy Python logic into the parity tool: call the real functions and serialize their state instead.
Emit partial facts after a stop: that could give a false PASS.

**Tests.** Compare fixtures and all three Dart corpora with real Python collection functions.
Keep 120 original edge probes. Fourteen isolated injected faults fail tests in a removed worktree.
Run the native self-contract and final-head gate. Report LOCAL VERIFIED and CI-ONLY separately.
