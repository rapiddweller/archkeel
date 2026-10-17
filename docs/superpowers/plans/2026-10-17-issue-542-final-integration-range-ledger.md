# Final Issue 542 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Root has already chosen native execution by the exclusive Main steward with independent final Astra review; this document records that decision and requires no new user approval.

**Goal:** Integrate all remaining approved Issue542 owner/Target/control slices in one final PR after separate fixes for Issues570 and564.
**Architecture:** Build the final tree on actual Main using only explicit immutable per-slice diffs. The frozen Root union is a source/Target comparison reference; it is never a whole-file overlay or a mutable-base/LCA-derived patch.
**Tech Stack:** Python3.11.12, uv0.12.13, GitHub Git-data connector, isolated read-only hosted Actions.
**Spec:** https://github.com/rapiddweller/archkeel/issues/542 and Root's explicit consolidation decision of2026-10-17.

## Global constraints

- Exclusive Main mutation lease: merge_reviewed_prs_final; no other Main writer.
- Separate issue fixes572/570 and569/564 finish first. #542 stays open until its accepted valid scope is complete.
- No policy/resolver-authority expansion, new allowance, raised baseline ceiling, fake module scope, skipped guard or invented evidence.
- Preserve every actual-Main change unless an explicit approved remaining range changes that exact field/hunk.
- No mutable PR-base inference and no broad LCA patch.
- No old baseline or receipt is inherited; normal actual-Main output is authoritative.
- All Source/Target scopes and atomic fixture prerequisites are reviewable before creating final metadata.
- Old542 drafts close as incorporated only after the final normal merge, each with the exact incorporated range and merge SHA.
-598/599 are not approved while their+5/+1 unresolved-call regressions remain unexplained. Do not claim full542 completion while any accepted valid scope remains outstanding.

## Review focus

- Shared source files must retain Main's Source coordinate implementation and existing nominal owners.
- Root/inner Target JSON must preserve IDs, public ports, guard coverage and rationale outside the exact original delta.
- Navigation/provenance fixtures contain real guarded owners and declared documents, with assertions preserved.
- Compatibility aliases remain visible and strictly checked; the remaining-reference limit stays11.
- Generated metadata binds the actual final Main predecessor and exact carried policy/baseline, with clean final NoWrite.

## Actual Main checkpoint and separate issues

| PR | Immutable original range | Final approved head | Actual merge |
|---|---|---|---|
|555|7b2a14de58eb18be716c8eadef5c43928ec464a5 →6fba15000baaeff6a274058291654b7301f2077a|43ecc3e67d8a8362c2b8eb9d0e3c59fa3358da80|8605b8cef0e764c797aa9ffef2367ae7f5420cb7|
|560|6fba15000baaeff6a274058291654b7301f2077a →49922fea2c7a4b049e947d5da902c96be669140f|8f9bbeef7bbd4ed2f4cc0b90787ab957be9a293e|a6515288cbbe3961e8a9aaac2054779dbd7877e3|
|558|8ebc1da53b3ac7290f78978d5e69e4f3c59185c3 →a5d478a7f40c00ad2cd7f5ed98c82a0778f182ec|9b5abc0a990b577a920218678db525937fd390cd|e26b73764089f06138c2829045660a74047f5c20|
|559|1f9cd588c21d2e485e8d7cf75b4c7a7e41ba793d →cd54501a8bd95facfd7e3e71929595c920fc2360|d2c2e3daf0cbb441c1fb7d3d786b469ed94be453|cef2d99ac1aa6e3be4710c5df03f89ab57c0dde5|
|561|5933ffbbfd588ac96e36748de937cb1f6e739655 →62fd95e68b07df1149e30a9690bd58f7129fa59b|64b3a0637a40b25df6baafef5299ae85b487d587|950520fd126ca05744c19066bb28ccbef5627964|
|572|0e3b8a7f62b9b13417cda78e11b52d0de82986cd →620374305b7d45383458f62bccd20a183fdcd82a|dace9a80e1bdc8419ba64804bfcf97f22970087f, tree-identical to source-approvedf5e9f38b5671e3f1f8eb1ecd613c78e638e75fe5|Pending exact final gates; closes570 only after merge|
|569|0e3b8a7f62b9b13417cda78e11b52d0de82986cd →6d03204f1b804be71386a036337fd17b4c54e351 plus atomiccf963 below|Carry after actual572 merge|Pending; closes564 only after merge|

Main checkpoint950520 has tree7f391949b6a6aee1143eeda972717c7afaff8fd1, byte-identical to approved64b3. #561 completed3439Core/48Report/5Publisher/2Mermaid; exact NoWrite/ordinary replay865/52/58/0. #542 remains open.

## Known immutable remaining ranges

| PR | Explicit original base | Frozen feature | Scope/preservation note |
|---|---|---|---|
|562|df14a43645316b74e67108e751e5acecc405b88b|e0ed68775f56bd20b79b470d3e5cbdeb0ffbc970|12 original paths; omit old receipt; bootstrap5prod, Root/Make/AnalyzerTarget preserve Main.|
|563|b475e027f4384feb8cdf2cc9844b82cdf89185ea|8d597b516c4ea3b95c1e009aa5009204d473cc00|13 paths; omit old receipt; preserve canonical diagnostics + symbol-requires in model/validation.|
|565|8a56d6d09e16372b43064798cc0b24428daa5e5f|f367015340044e12356c3963c63d29a2df90f095|12 paths; omit old receipt; property owner + strict legacy inventory prerequisite.|
|567|e5215b1403d98522003220b4c240aae9b011575f|a9fb1879aea33aa747fc4ce7d43965729f8879d3|17 paths; omit old receipt; preserve Requires and Amendment/Diagnostic owners in shared files.|
|577|7f99d03afaaea57530c56d688ce84e4b0867152e|b11aad0a60a26ecdf020ce36a5262d640315eb36|11 paths; canonical badges; preserve publisher/diagnostic imports; atomic c1ca + 16ca.|
|592|68b656668a3fdbbbe482881d0dab41ff89a21ca3|f051e6deee7de905984c1e648376fb88a07cc8a2|8 paths; omit old receipt; host_records enum placement + IR ports + durable Make.|
|597|68b656668a3fdbbbe482881d0dab41ff89a21ca3|8d9c67779b682b710cf1bed5d58d1ee24d9a7eb2|5 paths; only rules.py production +44; required before qualified guards in593/596; no redundant equal-state receipt.|
|593|68b656668a3fdbbbe482881d0dab41ff89a21ca3|29b161ca39de84d02919f209ade6b8c9b5fa8dc4|20 paths/14production; depends597; actual IR/PythonTarget + Make; fresh union metadata.|
|594|68b656668a3fdbbbe482881d0dab41ff89a21ca3|917b8177636c5401a51eecafafee6baf7b3bb35a|10 paths/3production; omit old receipt; preserve Snapshot Target and Make continuations.|
|595|cdcaa7f88537be077a9a44f7002816089ae5cde0|a4e7c423ba1338facdd430baf933fcbd4fc9068d|Final single-hunk refinement on0bbe7e39e6ce8c0da90cfba08b4f8168b55251ad; already canonical589 sort-only imports remain unchanged.|
|596|68b656668a3fdbbbe482881d0dab41ff89a21ca3|61dde9cc026a07ea348fbf5f9e56a172a5bbb90b|8 paths/+11net production +5real owner HRC guards; depends597; use final joint actual evidence.|

Explicit pairs still required from Root before applying573,574,575,578,579,580,581,571/576 coherent activation,582,583,585,586,587,588,589,590,591. Do not infer these from current PR bases. This ledger is incomplete until those pairs and any finally approved598/599 pairs are supplied.

Latest Root comparison reference at this checkpoint: fad36e2695de7587e09a87dd304fde7e586f009f. Joint329native controls and519Ruff/strict150/clean diff are green in run38999976942. Root must provide the final frozen Source SHA and current normal/full/Astra evidence before final carry.

## Mandatory atomic compatibility scopes

| Owning scope | Explicit immutable range | Exact intent |
|---|---|---|
|569|a25c37c564c82c1b42457f0528c931c769ee9362 →cf963ecb214d1c37bc67f549fe9c22dd35acd335|Existing shared requires_import_assessment alias identity and AssessmentStatus.UNKNOWN tests; preserve other assertions; no separate584 merge.|
|565+577 and actual owners|c7444205d4fe87eaae0de5e2dc98b70909fd1cc7 →16ca88691a250e537439d1b118e767af32744e98|Strict _PropertyBinding(class/private/python.source) and summary.State(type_alias/public_name/render.summary) metadata, remaining candidates≤11. Apply other inventory rows only for actual owners. CLI/Binding already on Main; diagnostic protocol leaf already incorporated561.|
|577|c7444205d4fe87eaae0de5e2dc98b70909fd1cc7 →c1ca9d98595af1d09f619cc0a135eae155b25ee6|Exactly4 fixture lines importing real summary_badges.py in tests/test_target_navigation_graph.py; assertions retained.|
|578|a25c37c564c82c1b42457f0528c931c769ee9362 →3e50a1764bffa24100892bf231e208e15919dacc|tests/test_typescript_demo.py exhausts actual NameBudgetKind enum rather than get_args of an old Literal.|
|582|5fc94c10298c4bbcd98fd44f8ac72b321b03a0b4 →809263d0b311033428b54f05a396032a39da25ef|Exactly7 navigation fixture lines: real atlas_deviations owner and actual declared spec; assertions retained.|
|582 including future588 provenance|ebfc072a9bf8afcbaca323024dcc8ad8488a76ee →ab5af9f9d68703d79688ec7327d58d43dafa72ea|One existing validation fixture copytree line copies ROOT/docs to root/docs, retaining all assertions and real provenance.|

## Main preservation rules

- Preserve Python physical-source coordinates, Binding/Receiver owners and Target ports in src/archkeel/analyzer/python/source.py and docs/architecture/contracts/python.json. #565 may apply only its original property hunks; any later SourceResolution/ClassKind hunks use their exact explicit ranges.
- Preserve current publisher/CLI/Dart/TS work. In src/archkeel/render/html.py and terminal.py apply only each original import/body hunk; keep canonical Diagnostic imports and actual publisher changes.
- Preserve canonical ir.diagnostics, Requires symbol matcher/AssessmentStatus and nominal owners in ir/model.py and check/validation/__init__.py when carrying Amendment/Grammar/other owners.
- Preserve IR-VERSION-supports as supports_feature(version:ContractVersion,feature:ContractFeature)->bool and its public port.
- Root and inner JSON edits are per-field/object/ID deltas. Keep every unrelated current ID/port/guard/rationale. Replace a port only when that exact canonical ownership move is in the approved original range.
- Make arguments are inserted before the line-continuation backslash. Root's former whole-Make overlay bug593744 is not copied; original594 Make was valid.
- Keep existing receipts as Main history. Add only one fresh final actual-Main union receipt and its genuine normal baseline output, if the comparison requires it.

## Execution tasks

### Task1: Finish separate issues and complete the range ledger

**Files:** Existing572/569 source/test files; this ledger only. Interfaces: consumes explicit immutable ranges; produces two independent normal merge SHAs and the final actual Main base.

- [ ] Finish572 exact current-base NoWrite, native/full-wire gates and strict requiredCI; normal expected-head merge, close570.
- [ ] Carry569 original scoped delta plus exactcf963 tests onto actual Main, preserving diagnostics and current code; independent Astra, fresh normal metadata, exact NoWrite/requiredCI; normal merge, close564.
- [ ] Record those actual merge SHAs; fill every missing remaining explicit original pair from Root's verified ledger.
- [ ] Freeze final Root Source after all included Source fixes have final independent approval and blocked unresolved regressions are actually solved or clearly left open.

### Task2: Build one reviewable final542 Source carry

**Files:** Exactly the remaining immutable range paths plus causal atomic fixtures. Shared paths above use explicit hunks/JSON deltas. Interfaces: actual Main+range ledger → frozen union source commit.

- [ ] Compare each explicit original base→feature and inventory every touched path, excluding old metadata.
- [ ] Apply only these deltas on actual Main. Reconcile shared files by approved hunks, never Root whole-file replacement.
- [ ] Compare resulting production/Target outcomes with the final approved Root freeze; record each intentional Main-preservation difference and demonstrate its exact original/Main provenance.
- [ ] Freeze source and obtain independent final Astra over this actual Main carry. No new production changes after this freeze without a fresh bounded review.

### Task3: Generate actual metadata and verify exact final tree

**Files:** architecture-baseline.json and one new ordinary final542 amendment only, plus already reviewed source. Interfaces: frozen source+actual Main → normal writer output and immutable final head.

- [ ] Run existing normal baseline writer, write-amendment and NoWrite replay against the actual Main SHA; retain actual stdout/Base64 artifacts and successful logs.
- [ ] Commit only actual generated bytes; no manual digest, allowance or ceiling increase.
- [ ] Have Astra independently compare committed metadata with actual generated output and predecessor digests.
- [ ] Run exact-final-head clean NoWrite, current requiredCI, and the full suite on the final tree using isolated read-only Actions with pinned setup and persist-credentials:false.
- [ ] Verify complete logs: no unexpected failure/diagnostic/widening, no false PASS/UNKNOWN widening, all required jobs successful. Full-suite known validation fixture must genuinely pass with actual declared docs.
- [ ] Freshly check Main/head, strict check+mermaid requirements and no-bypass rules; normal merge with expected full head SHA.

### Task4: Close incorporated drafts with evidence

**Files:** Final PR body and old draft metadata only. Interfaces: actual normal merge SHA+completed ledger → precise incorporated notices.

- [ ] Verify merged tree equals reviewed final tree; record actual merge SHA.
- [ ] For each old542 draft, state its exact incorporated base→feature range and final merge SHA before closing it.
- [ ] Close542 only when its accepted valid scope is complete; keep outstanding valid work visible otherwise.
