# AD-388 The core writes its status and verdicts only through the report

**Status.** Accepted. Epic #880, #1073 items 4 and 5. It closes the seam that AD-381 left for the
wiring slice (review F4).

**Decision.**
1. One status rule (item 4). `native/core/src/status.rs` is deleted. The core takes the status of
   the run, the verdict of each rule and their rows (`status`, `rules`, `explained`, `violations`,
   `beyond`, `scope`, `unsupported.rules`) only from `archkeel_report::Ruling`. Only
   `archkeel_report::rule(models, named)` makes one: it evaluates each model of the `ModelTree`
   itself (AD-385), takes the status from `run_status` (which `status_of` also uses) and needs
   `ModelTree::pass_run`, the one maker of a run PASS of a tree, for a PASS. A `Ruling` holds the
   same `Decided` mark as a `Report<Decided>`.
2. One frame exit (review N1 of #1090). Only `Ruling::frame(parts)` makes an `EngineFrame`, the
   bytes that the core writes one time (`core/src/main.rs` `respond`). It writes the keys of the
   ruling and refuses a part of the core with one of them (`FrameError::RulingKey`).
3. Gaps only. The core adds `Named`: the reason of each rule without a decision, one reason for
   the whole contract, and the hold of a tree whose models do not hold every mount (AD-379,
   AD-385). `Named` has no verdict field.
4. The report rule wins (AD-381 F4): a PASS of another rule or model, a DECLARATION that the
   model does not declare and rows that give PASS without the run proof write no frame (exit 2).
5. No trust from the caller (item 5, lead decision L-35c). The core cannot verify the pin of an
   external collector: the pin, the reply and its adapter fields are all bytes that the caller
   writes. So the core trusts only the bundled collector, which the shell runs itself, and only
   when the reply names the collector of its profile as its adapter. Protocol
   `archkeel-dual-run-5` removes `pinned`; a request with it is refused. A rule that needs the
   facts of any other reply is UNKNOWN with `the reply does not come from the bundled collector,
   and the collector pin is not verified by the core`, and the run is never PASS. Python trusts a
   pinned collector (AD-344), so this is a named stricter difference (`core stricter than
   Python:`): 155 rules in 56 corpus cases (`complete_assignment` 56, `no_component_cycles` 53,
   `complete_requires` 38, `forbidden_dependency` 5, `sibling_isolation` 3). The 21 `beyond`
   rules of AD-384 were in these cases and are UNKNOWN now. No verdict is less strict.
6. The standard library is pinned (item 5). `archkeel_store::standard_library(profile)` holds
   the list of each profile. For Python it is `sys.stdlib_module_names` of CPython 3.11 to 3.14,
   which CPython defines the same on each platform; a name of any supported minor is accepted.
   A name outside it refuses the settings by name. The shell leaves out a built-in module of its
   build that is not in that set (`tools/dual_run.py` `core_standard_library`), which only makes
   the core stricter. No corpus frame changes from it.
7. Barrier. `report/src/lib.rs` R5 to R12 with their error codes; R11 builds an `EngineFrame`
   with a hand-made status, R12 a ruling from one model of a tree. `ruling.rs` and `engine_frame.rs` have no wildcard arm.

**Reason.** Two status rules can drift. A caller of the core must not choose a trusted producer
or a standard library: either can turn an UNKNOWN or a FAIL into a PASS.

**Rejected.** A full `Report<Decided>` for the engine frame: `build` needs tables that no slice
produces yet (`BuildError::NotProduced`). A pin that the core checks against reply fields: the
caller writes both. `sys.builtin_module_names` in the list: it depends on the build.

**Limit.** The bundled path trusts the shell, which runs the collector and writes the reply
bytes; the core verifies nothing about the producer. An external collector, pinned or not, gives
no PASS in the core. A decision in a model (`Decision`) cannot hold a PASS with a reason or an
UNKNOWN without one (`model/src/verdict.rs`); the ruling checks both again.

**Tests.** `native/report/src/ruling_tests.rs`; R5 to R12 of `native/report/src/lib.rs`;
`native/core/src/hostile_tests.rs`, `main_tests.rs`; `native/model/src/settings_tests.rs`,
`verdict_tests.rs`; `native/store/src/standard.rs`; `tests/test_native_standard_library.py`;
`tests/test_native_core.py`; the case `pin/a-pinned-external-collector-is-not-trusted-by-the-core`.
