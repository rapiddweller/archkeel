# AD-426 The linked collector states profile limits before the scope proof

**Status.** Accepted. Part of #880 and #1095. Extends AD-378 without a new PASS proof.

**Reason.** The TypeScript scan corpus has 144 rules held by an unknown profile difference.
The core cannot tell whether an interface rule or a symbol selector is a profile limit.
It holds every rule of the contract, including rules that read neither feature.
One more measured refusal is a mounted `layer_order` receipt, not a profile limit.

**Reference behavior.** `ir/profiles.py` declares the supported rule kinds and symbol support.
`check/evaluation/evaluate.py` enables dependency symbols for `script-globals-v1`.
`profile_failures` records unsupported rules, declarations and symbol selectors as coverage failures.
This does not exempt an unread source construct. Actual source gaps remain separate facts.

**Decision.**
1. The linked collector attaches `ProfileLimits` to its typed reply.
   `LimitSupport` states support for dependency symbols and module interface boundaries.
   The collector owns these facts. The model has no language table.
2. The store checks the symbol statement against the registered resolution capability.
   The same store validation still checks all sections, records, evidence and coverage gaps.
3. The model turns a stated unsupported feature into the existing certain profile limit.
   A stated supported feature removes only that profile ambiguity.
   An absent statement keeps the old conservative behavior.
4. Every rule still needs its own existing scope proof, receipt and resolved positions.
   Actual coverage gaps, dynamic imports, partial constructs and pair gaps keep their existing checks.
   Interface rules remain unported and cannot pass.
5. `ScopeComplete`, `Scope::complete`, `Scope::pass_run` and `ModelTree::pass_run` are unchanged.
   No new path makes a rule PASS or a run PASS.

**Soundness.** A profile statement says which collection model applies. It does not claim source completeness.
The symbol rule still reads `symbols_known` for every selected import.
`Supported` is a flag, not a proof: the store only compares the capability, `interface_boundary: Supported` is constant, and PASS still needs `symbols_known` on every selected import plus all coverage and pair-gap checks.
A namespace import with an unread symbol position stays UNKNOWN.
An unresolved dynamic import can hide a forbidden edge and still holds that rule.
An unported interface rule holds the run, but does not hold an unrelated rule.

**Rejected.**
- Add a language test to the model. That puts collection knowledge in a second owner.
- Delete every uncertain limit. That can pass a selector which the collector cannot read.
- Treat a documented source gap as harmless. Its name is not proof that it cannot change a rule.
- Change the legacy wire protocol in this slice. The end-to-end scan needs no saved-reply authority.

**Limit.** The statements exist only on the linked collector's in-process reply.
They are not serialized. A wire field with this name is refused, not trusted.
Saved replies and the dual-run wire path retain their conservative profile refusals.
The mounted layer receipt, interface evaluator and UML evaluator remain unported.
This change makes no new claim about constructs that the collector cannot read.
Until D2, the capability table has two owners, `src/archkeel/ir/profiles.py` with `check/evaluation/evaluate.py`, and `native/typescript/src/records.rs`; this duplication is debt.

**Tests.** `tests/test_cli_native_profile_limits.py` checks symbol selectors, required symbol ports,
public symbol ports and interface rules. Each class has a planted dynamic forbidden edge.
The store tests reject a contradictory symbol statement and a wire claim.
The collector test checks the typed statement and its absence after serialization.
The unchanged self-core test checks 63 PASS, 1 FAIL and 19 UNKNOWN.

**Measurement.** The release scan of 223 projects has 1,785 rules, including two declarations.
Before: 887 PASS, 110 FAIL, 786 UNKNOWN. After: 1,031 PASS, 110 FAIL, 642 UNKNOWN.
All 144 profile-held rules now pass. No core PASS has a non-PASS reference result.
