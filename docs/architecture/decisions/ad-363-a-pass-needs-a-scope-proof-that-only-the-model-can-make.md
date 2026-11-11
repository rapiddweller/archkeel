# AD-363 A PASS needs a scope proof that only the model can make

**Status.** Accepted. Epic #880, WP6 slice 0b (design WP6-0, sections B and C; AD-359 point 4).

**Decision.**
1. `Model::scope` gives a `Scope<'id, '_>` with a brand: an invariant lifetime that only this
   call has. `Scope::complete` is the only maker of the proof `ScopeComplete<'id>`, and
   `Scope::pass` takes only a proof of the same brand. A proof cannot be used with another
   model, cannot leave its scope, and no other crate can make one (`compile_fail` doctests).
2. Until slice S4 writes it, `Scope::complete` answers `Unsupported::ScopeProof`: no rule can PASS.
3. `Decision` has private fields. PASS comes only from `Scope::pass`; `fail()` needs no proof (a
   found violation is a fact also in an incomplete scope); `unknown(Reason)` needs a reason.
   `Verdict::Pass` holds a `Proven` mark that only the model makes, so another crate cannot write
   a PASS verdict.
4. Rule for `eval` and `report`: an outcome of `eval` and a rule of the report payload hold a
   `Decision`, never a bare `Verdict`. The types enforce that no other crate makes a PASS. A
   `Verdict` that a crate reads from a `Decision` and keeps on its own is not checked by a type:
   that part is a written rule, and its review checks it.
5. The ids (`ModuleId`, `PackageId`, `ComponentId`) come only from a `Table` of the model. The
   trait `Id` is sealed and `from_index` is private to the crate (`compile_fail` doctests).
6. A part with no result answers with a named `Reason`, never with an empty result:
   `Unsupported` (the scope proof, a section with the slice that ports it, a rule kind, a
   contract part of 0c-2, the report of 0d) or `MissingInput` (no valid contract or reply).
7. `archkeel-core` is the only binary. Each request has its own file (`contract`, `ingest`,
   `sections`, `report`), so the slices change different files. It speaks the engine command of
   the dual run (AD-360) and exits 3 when its frame names an unsupported part or a refused input.
   The harness accepts exit 3 only with such a frame and exit 0 only without one.
8. The core owns no section and no rule family. A slice that owns nothing fails the run.
   `--self-test` proves the round trip: the rule ids and kinds that the core read from the
   contract bytes equal the verdict map, and the store accepts the reply. The host uses the core
   for no verdict, and the wheel does not carry it.
9. The model and the core name no language. A test checks their sources: the Rust profile has
   no rule kind that reads an identifier, so the native contract cannot check it.

**Amendment (2026-11-11, lead decision).** The model reads the reply through `archkeel-facts`
directly: `model` depends on `contract`, `store` and `facts` (AD-359 point 2 is corrected). The
store gives one accessor, `Ingested::reply()`. It gives no re-export and no accessor per slice.

**Reason.** The largest risk of the Rust evaluator is a false PASS: a rule passes because a fact
or a file was not seen. A proof that only the scope of its own model makes turns that risk into
a compile error. A named reason and exit 3 keep the dual run honest while the slices land.

**Rejected.**
- A `bool` field `complete` on the model. Any code can set it.
- A proof bound by a plain lifetime. Two models with the same borrow region would accept each
  other's proof; only a brand that a closure gives is distinct per call.
- Owning one section for the wiring proof. The S1 sections need the edges and ranks of S2 and S3.
- A copy of the byte frames of the store session in the core. They move with the host switch.

**Limit.** The store refuses the replies of the Python and Dart collectors, so their self-test
names the refusal. Contracts with `declarations` or a Python-only kind are unsupported until 0c-2.
The fake-language test of design section B comes with S1.

**Tests.** The `compile_fail` doctests of `ids.rs`, `scope.rs` and `verdict.rs`;
`native/model/src/model_tests.rs`; `native/core/src/engine_tests.rs` and `dual_run_tests.rs`;
`tests/test_native_core.py` (the run that owns nothing, the unsupported parts, the missing input,
the round trip, the named self-test differences, no host use, no language); `tests/test_dual_run.py`
(the unsupported frame, the self-test, exit 3 only with a gap, a run that compares nothing).
