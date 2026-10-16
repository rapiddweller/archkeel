# Core Command and two RunResult controls — issue #542

Parent approved this bounded stage on0e3b8a7f62b9b13417cda78e11b52d0de82986cd. Execute inline with Superpowers TDD and independent final Astra review after freeze; remote GitHub/Actions only.

## Owned design
- Move the actual six-member Command enum from CLI arguments to ir.model beside RunResult. CLI explicitly reexports the same class. ContractCommand.command remains arbitrary shell-command data; the published command-result schema remains exactly report/validate/check/init.
- RunResult.command:Command. observation_complete is the exact Literal subset of canonical AssessmentStatus.PASS/UNKNOWN, never FAIL. expectation_fulfilled uses the separate ExpectationOutcome PASS/FAIL/UNKNOWN/n/a domain.
- Normalize valid legacy constructor strings at the existing frozen DTO boundary without a generic conversion framework. Keep existing diagnostic/exit invariants and actual CLI skill/arguments error paths. Keep binary Verdict fields and Amendment/Delta/Measurement domains unchanged.
- Migrate actual producers and consumers, preserve summary wording/JSON bytes. Reuse model/RunResult Target anchors, remove CLI's old enum-definition Target, and make CLI fixtures consume actual canonical owner source.
- Model and summary still contain unmigrated vocabularies: no whole-module string-freedom claim. Existing CLI whole-package guards protect actual CLI dispatch; source-backed native construct facts can bound new Core controls explicitly.
- Root CLI requires only the additional canonical model:Command port, never Core→CLI.

## TDD sequence
- [ ] Commit plan and author independent API/subset/legacy/schema/error-path tests plus actual source-widening, enum-substitution and raw-dispatch controls.
- [ ] Hosted native RED before production; confirm missing canonical owner, loose fields and unchanged four-value schema.
- [ ] Implement only Command and two fields with necessary producers/consumers, no other status collection.
- [ ] Focused native controls and existing CLI/command-view/schema/summary/report tests; strict Mypy, Ruff, hygiene.
- [ ] Real own baseline plus normal receipt and NoWrite. Compare all UNKNOWN IDs and unresolved/PARTIAL target multisets with multiplicity against0e3, without cap/baseline increases.
- [ ] Clean product freeze and exact-source carrier for parent/Astra. Stop before another Core stage.

Review focus: four-valued published schema rejects skill/arguments even though actual CLI failures retain those tags; Observation completion rejects FAIL; free shell commands and actors remain data; old constructor/wire behavior and CLI invalid-input remedies remain; shared types have one owner and no duplicated status enums in render.
