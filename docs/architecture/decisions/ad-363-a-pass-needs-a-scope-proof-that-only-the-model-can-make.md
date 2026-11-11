# AD-363 A PASS needs a scope proof that only the model can make

**Status.** Accepted. Epic #880, WP6 slice 0b (design WP6-0, sections B and C; AD-359 point 4).

**Decision.**
1. `archkeel-model` holds `ScopeComplete`. Its one field is private to the module `scope`, so no
   other module and no other crate can make one (a `compile_fail` doctest checks this).
2. `Decision::pass` takes a `&ScopeComplete`. `Decision::fail` needs no proof: a found violation
   is a fact also in an incomplete scope. `Decision::unknown` takes a `Reason`. The fields of
   `Decision` are private, so a PASS comes only from `pass`.
3. `Model::scope_complete` is the only maker of the proof. Until slice S4 writes it, it answers
   `Unsupported::ScopeProof`, so no rule of the core can PASS.
4. A part that no slice has ported answers with a named `Reason::Unsupported`: the scope proof,
   a section (with the slice that ports it), a rule kind, a contract part of slice 0c-2, or the
   report. It never answers with an empty result. `Rows` has no variant until S1 ports a section.
5. `archkeel-model` has typed ids (`ModuleId`, `PackageId`, `ComponentId`) that only a `Table`
   gives out, the components of the contract, and `Section`: the 20 sections of
   `tools/dual_run_schema.json`, each with the slice that ports it.
6. `archkeel-core` is the only binary. It has the typed requests `Contract`, `Ingest`,
   `Sections` and `Report`, and it speaks the engine command of the dual run
   (`archkeel-core dual-run`, AD-360). The harness sends the contract bytes and the collector
   reply. The store validates the reply through a new public seam (`ingest_reply`, `Ingested`).
7. The core owns no section and no rule family. The harness fails a slice that names no part
   (`--sections none --families none`). `--self-test` proves the round trip: the rule ids and
   kinds that the core read from the contract bytes equal the verdict map, and the store accepts
   the reply. The host uses the core for no verdict, and the wheel does not carry it.
8. The model and the core name no language. A test checks their sources: the Rust profile has
   no rule kind that reads an identifier, so the native contract cannot check it.

**Reason.** The largest risk of the Rust evaluator is a false PASS: a rule passes because a fact
or a file was not seen. A type that only the scope proof can make turns that risk into a compile
error. A named `unsupported` keeps the dual run honest while the slices land one by one.

**Rejected.**
- A `bool` field `complete` on the model. Any code can set it, and a test must find each misuse.
- A PASS proof in `eval`. Then `eval` could make the proof that `model` must give.
- Owning one section for the wiring proof. The S1 sections (`modules`, `packages`) need edges and
  ranks of S2 and S3; a self-test of the inputs needs no slice.
- A copy of the byte frames of the store session in the core. The frames move to the core when
  the host switches to it (step 5); a copy now would be a clone of 40 lines.

**Limit.** The store refuses the replies of the Python and Dart collectors (they are not
compressed, or have parts that it does not read), so their self-test names the refusal. The
contracts with `declarations` or a Python-only rule kind are unsupported until 0c-2. The
fake-language test of design section B needs a reply that the model reads, so it comes with S1.

**Tests.** `native/model/src/model_tests.rs`, the `compile_fail` doctest in `scope.rs`,
`native/core/src/engine_tests.rs`, `native/core/src/dual_run_tests.rs`; `tests/test_native_core.py`:
`test_a_slice_that_owns_nothing_fails_the_run`,
`test_each_owned_part_is_unsupported_by_name_and_never_equal`,
`test_the_round_trip_reads_the_contract_and_the_reply_of_each_rust_case`,
`test_on_the_fixtures_each_self_test_difference_is_named`,
`test_the_host_uses_the_core_for_no_verdict`, `test_the_model_and_the_core_name_no_language`;
`tests/test_dual_run.py`: `test_an_unsupported_part_of_the_frame_is_a_named_difference`,
`test_the_self_test_compares_the_rule_kinds_that_the_engine_read`.
