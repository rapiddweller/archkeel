# SDD ledger — plan: docs/superpowers/plans/2026-10-16-typed-diagnostic-owner.md

Pre-flight: model is shared with the independent ContractVersion and RuleGrammar work. This increment changes only diagnostic declarations, the ReportLocation value and their explicit reexports; final integration must apply those owned deltas without overwriting colleagues' model fields.
Ruling: Extract a coherent diagnostic owner rather than append enums to the large model facade. The parent explicitly approved the extraction and ReportLocation move. Cost if wrong: misplaced ownership/import-cycle risks; identity, frozen DTO and native controls prove the boundary.
Ruling: Keep result/comparison/amendment/command controls for independently reviewable later increments. Command inventory has six existing CLI values but no Core-to-CLI dependency will be introduced. Cost if wrong: scope remains explicitly incomplete rather than hidden behind a whole-model guard.
Ruling: Remote isolated branch and hosted Actions replace unavailable local worktree/executor operations; no local files or shared branches are mutated.

Task1 RED: hosted38950559155 on731024c93fcc2768d03eae38126202ef0277dae0:57 failed/1 preserved wire-byte test passed. Nominal kind/code values and the extracted owner are absent; the real native observer reports rule_without_subjects for the not-yet-present diagnostic namespace. Production unchanged until this evidence was read.

Task1 owner GREEN: hosted38951076299 onf11ac2db0e3bbda040b8470e203cfcfa7b30581d:58 native/identity/wire tests passed. The model shrinks86 lines; the complete owner is107 lines (combined net+21 before necessary producer imports). Actual AST inventory identifies100 typed diagnostic literals across21 producer/decision files; edits preserve record-data dictionary keys and use private new implementation imports. These are temporary tooling proposals, not a production converter framework.

Integration ruling: reapply only the owned diagnostic extraction, four onboarding diagnostic constants, five facade imports and20 Target entries onto finalGraph+Version5933ffbbfd588ac96e36748de937cb1f6e739655. Preserve ContractVersion/NominalRankOwner implementations, metadata, typed fields, existing declarations and test gates. No whole-model rollback.
