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
- Source598 and599 now have final independent approval with measured native-call changes recorded below. Four additional bounded existing-owner domains and the final fixture repair still need explicit frozen ranges. Do not claim full542 completion while accepted valid scope remains outstanding.

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
|572|0e3b8a7f62b9b13417cda78e11b52d0de82986cd →620374305b7d45383458f62bccd20a183fdcd82a|dace9a80e1bdc8419ba64804bfcf97f22970087f, tree-identical to source-approvedf5e9f38b5671e3f1f8eb1ecd613c78e638e75fe5|3fdda84e4a58b0ac3ed15a8d28c761568d4d7809;570 closed|
|569|0e3b8a7f62b9b13417cda78e11b52d0de82986cd →6d03204f1b804be71386a036337fd17b4c54e351 plus atomiccf963 below|55f416d462a5b9ff44f761ed725eae4c5f9cf05b, Source98cd and actual metadata independently approved|113318809036cfa4550b2b8598dab63c0b548878;564 closed|

Final integration base is actual Main113318809036cfa4550b2b8598dab63c0b548878 with tree0b33fa7963d40a7bbe33fd50558aa14c6afc15ce, byte-identical to final56955f416d. #569 completed3494Core/48Report/5Publisher/2Mermaid, ordinary replay and exact final NoWrite865/52/58/0, independent Source+actual-generated-metadata approval. #564 is closed. Earlier572 base3fdda has tree56624f122d0fcfa7f8b07a6ed725f1f22cef636d, byte-identical to final572dace9. #572 completed3450Core/48Report/5Publisher/2Mermaid and exact final NoWrite865/52/58/0. Its 80 native/quality and317 regression controls passed; full H/Compass runtime wire bytes stayed identical. Four new conservative PARTIAL sites in _binding_sites were separately matched by AST/targets/reason/multiplicity, without changed existing records or UNKNOWN identities. #570 is closed; #542 remains open.

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



| PR | Explicit original base | Frozen feature |
|---|---|---|
|573|d08dfaf6a2e6992153a434341465306a88d993a2|0aee692c767150847089dbcfdcf1765464837ab6|
|574|4493b0a944e6caf0c56802c6333d9fd0090041b4|6f9df272790f4435df7735a75979e0bfc692c1cf|
|575|d3f7b008fedbedbf029312ddee30d4bfcafe4eb0|3dd2efdc54ef99f2b4cb742f3194cfd1f2619a84|
|578|3dd2efdc54ef99f2b4cb742f3194cfd1f2619a84|af9f0f708142bf0529992f4f7147c7d37e3b1a99|
|579|af9f0f708142bf0529992f4f7147c7d37e3b1a99|6452149d33186dc56d78f7072d73b5dbb988d35a|
|580|e99394254846318e236ba471a14c19cd160081cf|f6099877bdb325c095959f5df8f07f406c0f0dc2|
|581|f264c77eb55b1761a37a8083e479c3f1bc45f5cc|28938726de24fe8b2df69c61cd92c3f5dfb4cad1|
|571|fa37f59600cfae64ba0528cb56e609c6bbd756e4|97615e831e15b2fceb5a6b09743601042b9552c4|
|576|0e3b8a7f62b9b13417cda78e11b52d0de82986cd|124ab1c6ded4d7f7359a5265bc1434b96c0f9507|
|582|0aee692c767150847089dbcfdcf1765464837ab6|3ccd073fb4bb82639f51cc0f7b09497101d5ee3d|
|583|a25c37c564c82c1b42457f0528c931c769ee9362|11173d0125f0e70b6ef592ae7eec70ec37665e73|
|585|5fc94c10298c4bbcd98fd44f8ac72b321b03a0b4|c94d1fa926d62042477ca149232ade6afe3e4919|
|586|b06fd806ae0e76d340cba44eb7b5e84c887384d6|b4e9089b32e48ae420e2c529a93b85ec930db27e|
|587|6452149d33186dc56d78f7072d73b5dbb988d35a|a7e2c7184bea0f0aeb5b7003810aebd64aaa3761|
|588|5fc94c10298c4bbcd98fd44f8ac72b321b03a0b4|a91dfa9f52d9b95cfe00a9bc9ec9bd1e5bf752fc|
|589|c725df96543d1dd7ec4e20887a486ec9a7143c8a|36624bb7d147ed2056ceac8bd2332959ee3be5d6|
|590|cdcaa7f88537be077a9a44f7002816089ae5cde0|6776847a36bca8811a7126736cc0da2179ab73ae|
|591|68b656668a3fdbbbe482881d0dab41ff89a21ca3|4a58d277f17ff2375a50a92349b58d3b17812124|
|598|5937445491094abc00a4076dd4628a03f08e9064|01bc5d65beff3190f550a97bd71ea5071486594d|
|599|7cfe1298fb285dfb5c53c1b8f829207ce05b7e97|96e70a648eff9a404475db0af5c3a4738abd86ac|

The initial Python string-predicate scope is exactlyde6f57f4f49b368373d40e8584e48761ab4b19b1→f624d99286983fa0e26aff5e87835c359ba63d55. Independently compared exact base==mergebase, three commits/eight paths: Make, Root, PythonTarget, dedicated document, constructs, analyzer test, native predicate Target test and predicate observation test. This initial scope must precede activation: the original571 TS-only and576 Dart-only ranges do not add the Python predicate owner. No broad LCA is substituted.

Coherent571/576 activation is exactly15f1fa127c37399541e09b16ccf23ebe246f3709→4a01cf7925db9f64295ef3a0f52292cb30f8bfb1 (six commits/six files, independently checked exact mergebase). It includes PythonTarget/docs/constructs, Dartcollect, predicate test and legacy-reference fixture. Use ORIGINAL571+576+activation exactly once. Alternative already assembled571 owner-union rangec7444205d4fe87eaae0de5e2dc98b70909fd1cc7→c245e1ebda1588e2c6f885ed37bcb7fcb48b9ba9 must NOT also be applied.

Mandatory586 durable Make follow-up is exactlyb4e9089b32e48ae420e2c529a93b85ec930db27e→0000dc6789d3c2c9dd85e64f7974b0c982c1d5d6, adding only tests/test_definition_context_types.py.

Root reports final Source approval for599. Its true original parent and feature both measure839, with AD10018 identities11added−11removed=0 and no unbalanced group. That earlier inherited Root baseline838 was stale at the true599 parent checkpoint; do not treat that old measurement as a valid final Main gate or copy its metadata. Actual Main comparison/writer remains authoritative.

Source598 is independently approved at5937445491094abc00a4076dd4628a03f08e9064→01bc5d65beff3190f550a97bd71ea5071486594d. Its six paths include two production files, PythonTarget, one document and two existing tests. Actual immutable host mutation control and326 focused tests passed. Honest standalone call cost is +2 unresolved: three new calls and one removed old call,841 versus actual parent839. Preserve the existing597 test tail and append the approved376-line feature tail; never replace the entire current test.

Awaiting Root's final explicit bounded ranges for StructureLevel(component/package), SourceGraphTopologyLevel(module/package), SourceNameVisibility(private/public_name), and RegularGitBlobKind(two byte pairs). Each uses an existing owner. No final union freeze is inferred until these and the causal predicate fixture repair are handed over.

Latest evolving Root comparison referenceff885e1c7f66afb2ede2e60eb4334a824deb9c81 includes598+599 and prior approved owners. Joint normal NoWrite39001250567/job117304451620 passes838/52/58/0, empty failures/diagnostics, clean tracked/untracked state; no budget change. Quality519/strict150 passes. Joint native388 passes/eight failures were traced to an unrelated SourceResolution function-scope guard copied into a constructs-only fixture, causing RuleWithoutSubjects; the earlier missing-document theory was disproved. The exact causal fixture repairff885e1c7f66afb2ede2e60eb4334a824deb9c81→0224cdd2ca3be4a6501a4f584bed80ecd253e941 adds ten lines in tests/test_python_string_predicate_target.py: retain every forbidden-construct guard whose source is the actual constructs module or its declaration; other owner guards retain their own real source fixtures. The production Target remains intact. Fresh eight-control replay is still pending, so this is not yet an all-green final union gate. Root's frozen source is a comparison reference, never an overlay.

## Newly verified bounded existing-owner ranges

Each following compare was read independently and has exact original base==mergebase. They are additions to the final union; no final source freeze is implied.

| Scope | Explicit original base | Frozen feature |
|---|---|---|
|visibility|bb3e498b9c43afc954ef9fe7078595983e0b3c2f|bcd0951665735a1f00c85b3a0cb6b88887bd8683|
|topology|bb3e498b9c43afc954ef9fe7078595983e0b3c2f|5076058e5e7167d5d6df866784e99036149cd47f|
|git-kind|bb3e498b9c43afc954ef9fe7078595983e0b3c2f|bf21e014fff57e5b963ea6785ae4a4b4f2c48a79|
|git-kind-final-doc|bf21e014fff57e5b963ea6785ae4a4b4f2c48a79|c2e96e3405930b3d1083b78f33e8486cb10e9fc8|
|structure-level|bb3e498b9c43afc954ef9fe7078595983e0b3c2f|7ff514624621334247bf89815e4a5f1d59404899|

Git final-doc compare has three paths: baseline, old receipt and the new evidence document. Omit both metadata paths; carry only docs/architecture/typed-git-blob-boundary.md. Every Git production/Target/test blob stays exactly the source-approvedbf21 outcome.

Shared Target rows use exact ID/field unions: IR-COMPARISON-structure responsibilities/provenance preserve Graph and Structure, and TYPES-ENUM-IN-MODEL exact_sources/provenance/rationale preserve Git and Structure. Structure import/alias hunks retain the Graph model import. All Make edits append actual tests before line-continuation backslashes.

Preparation39003032411 composes the prior40 explicit scopes in memory against frozen569Source98cd:377 file applications/199 distinct paths, no conflict, valid Python/JSON syntax, checkout unchanged. Two contextual rulings are explicit: initial predicate UML schema1.1.0 replaces existing1.0.0 under the reviewed predicate Target addition; actual Main browser-runtime-check and feature browser-graph-check are both retained in report failure-prefix tests. This is composition evidence, not native/full/required/final review approval. Four bounded owner ranges and the pending Classifier fixture still require final composition and all final gates.

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

- [x] Finish572 exact current-base NoWrite, native/full-wire gates and strict requiredCI; normal expected-head merge3fdda,570 closed.
- [x] Carry569 original scoped delta plus exactcf963 tests onto actual Main, preserving diagnostics/current code; independent Source+actualmetadata Astra, fresh normal writer, exact NoWrite/requiredCI; normal merge113318809036cfa4550b2b8598dab63c0b548878,564 closed.
- [x] Record actual569 merge SHA, initial predicate pair and four bounded existing-owner pairs. Classifier final fixture/frozen final Root source remain pending.
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


## Latest preparation checkpoint: receipt complete; final union not frozen

Actual accepted Main remains `113318809036cfa4550b2b8598dab63c0b548878` (checked again after receipt work). Issue #564 and #570 remain separately merged; #542 remains the one final integration scope. The Root branch `integrate/542-owned-types-formatted` at `afc360674fdb4524f3d2c1fd9f8bfef72352d140` is a research reference, not a frozen final source or a tree overlay. No Main mutation or final metadata generation is authorized by this checkpoint.

### Bounded receipt implementation, ready for exact owned carry

Explicit immutable scope: `5b8a603274b2330b85fc6fe62c8d7f6fb15da8f1` → `1c4814addf48f31f563dc1b393f50adabcb38580`, branch `fix/542-rule-evaluation-receipts`. Exactly eleven paths, seven production paths, +42 net production lines; no accepted, baseline, amendment, schema or resolver-authority change. Existing `ir.model` owns the optional receipt view (presence plus two boolean completion facets), its private single-marker recognition and precise `Record | RawRecord` reader. Two producers retain plain-string wire tags; eight selection sites use the reader. Missing assessment completeness stays true; missing cycle completeness stays false. Generic record kinds and other payload remain open, and UML identity diagnostics remain hard errors.

- Actual RED: run 39004296837 / job 117313482983, four expected missing-reader/producer/native-port failures with no collection error.
- Exact final Source native/quality: run 39005532900 / job 117317117654, 36 PASS, Ruff/format 526 files and strict mypy 150 files, clean diff. Fixed authored field/signature weakenings and raw reader mutation fail natively. Unchanged actual Root placement rule passes the real owner and fails physical relocation into actual `ir.report_graph`; absent-original-owner Target remains honestly UNKNOWN because complete inventory is not proven.
- Affected regressions: run 39005365714 / job 117316620248, 577 PASS. Final Source differs only by the actual Ruff line wrapping of the tested conditional expression.
- Exact final runtime wire: run 39005532900 / job 117317117911. Eight actual Core receipt streams and eight complete report/module projections are byte-identical. Every untouched full raw report differs at exactly `/analyzer/code_digest`, preserving authentic tool identity; no artifact or source stamp is forged.
- Exact final native cost: run 39005532900 / job 117317488506, exit 0, diagnostics empty, 144/144 files, 19048 calls / 15691 resolved / 2517 PARTIAL / 840 UNRESOLVED / 52 typing positions / 58 UNKNOWN / 0 violations. Actual parent 5b8a: 19036 / 15678 / 2518 / 840 / 52 / 58 / 0. True unresolved net zero. The interim Root draft 838 ceiling is not the accepted Main ceiling 865; final ordinary metadata must be generated against actual Main after Source freeze, without an accept flag or a manual cap edit.

### Newly verified precise inputs for composition

| Owned scope | Exact predecessor | Exact reviewed source | Handling |
| --- | --- | --- | --- |
| Initial TypeScript source input | bbcba3ae4e79ca72329d382333c1fba9546586cd | d894c0692b06dd5f1ea114c3a81edbb180bc93cf | REST compare verifies exact mergebase, 11 commits and only 14 paths. This is narrower than the later 32-path union. Carry explicit hunks, preserving current predicate/construct observations. |
| TS input inventory / integration-plan supplement | f63840b5c912ae40eff42fa7b12fd41240566d46 | cd610282d11fb2195bfe93fedbb4ee1b4f82f412 | Only the source_input owner line in tests/test_self.py and the dedicated activation-plan document; original 14-path scope already supplies Root/Make/TS Target. No Dart/Python files or whole union overlay. |
| TS canonical public catalog correction | b06fd806ae0e76d340cba44eb7b5e84c887384d6 | a25c37c564c82c1b42457f0528c931c769ee9362 | Exactly typescript.json and its source-input document; remove five obsolete component-public declarations while retaining Python compatibility exports. |
| Fact classifier projection | bcd0951665735a1f00c85b3a0cb6b88887bd8683 | 2d55dfb42c455ac47b2dc5715270cd14521d396c | Seven paths; explicit exact predecessor already verified. |
| Call directions / Terminal | 5b8a603274b2330b85fc6fe62c8d7f6fb15da8f1 | befb7e8ac4adfb39ba2ae4c6b9308f4c33bbd638 | Exact compare verified, twelve paths; additive model/Target/Make carry. |

All five original TypeScript production added/removed hunk sequences match the later f638→cd610 integration exactly. Config, resolve, source_input and the new source-input test are also whole-blob equal. Collect and parse whole blobs differ because the later integration retains independently owned predicate/construct observations; those files must never be replaced wholesale. Original Root/Make changes supply only the TS owner and source-input test selections. The TypeScript Target remains a contextual JSON owner union; preserve actual current entities, public ports and guards.

Root has additionally supplied these immutable ranges; they remain to be independently checked and included with the rest of Root's forthcoming final freeze map:

- Host OS: 5b8a603274b2330b85fc6fe62c8d7f6fb15da8f1 → 7313832f307b54dbe99311df691fe1a907feb355.
- Collection grammar: befb7e8ac4adfb39ba2ae4c6b9308f4c33bbd638 → aa84fab9c5bb6833b9ab58bcccbbbb443dc0a114.
- Canonical source enum: befb7e8ac4adfb39ba2ae4c6b9308f4c33bbd638 → 5c07aa82b81c93f2f88ad81ba98f5e492192f3ef.

### Read-only residual grammar research

Exact current reference afc360674fdb4524f3d2c1fd9f8bfef72352d140; original audit manifest 19f9d436b1c3098c1c445926c1016e35575abee0. Read-only run 39006077074 / job 117318727877 joins all 31 requested original sites by actual owner, AST SHA256 and physical column, with no unmatched site. Current scope has **33** comparisons: 26 wildcard, six selector and one pragma. Two additional actual wildcard checks, omitted by the legacy 24-site subset, are `imports.typed_dict_unsafe_providers:663` and `imports._escaped_import_origins:723`, each selecting `symbol in {None, "*"}`. This is an inventory and a minimal design proposal only; no product implementation or completion claim is attached.

Proposed minimal existing-owner conversions: reuse the existing ImportSymbolMarker canonically at the pure source-facts boundary with an identity compatibility export, use one bool-returning existing model selector parser rather than an enum of punctuation, and let tokenize plus a single str.partition parse the existing type-ignore marker and retain its open tag suffix. Preserve the current permissive comment substring and attachment semantics; replacing it solely with ast.TypeIgnore would narrow legacy behavior. Root owns the decision and any implementation.

The previous 45-scope apply preview remains a syntax/conflict preparation result, not final validation. Its bare-Ruff failure was an overbroad verifier invocation across intentionally excluded fixtures; final checks must use the repository's actual Make lint/typecheck selection. Final Main preservation, ordinary writer/amendment/replay, committed NoWrite, complete regression suite, required exact-head CI and independent whole-union Astra remain necessary after the final source is frozen.
