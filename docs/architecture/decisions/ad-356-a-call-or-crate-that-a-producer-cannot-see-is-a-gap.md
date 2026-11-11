# AD-356 A call or a crate that a producer cannot see is a gap, not a PASS

**Status.** Accepted. It refines AD-250 and AD-335 for issues #758, #759 and #880 (FP-28, FP-45).

**Decision.**
1. Rust: `extern crate name;` (not `self`) gives the gap "The manifest does not declare the extern
   crate name" when `name` is not a crate of the sysroot (`std`, `core`, `alloc`, `proc_macro`,
   `test`), not an entry of the manifest and not the library of the own package.
2. Python guarded effect: a call in a condition scope that has no path facts is a limit of the
   rule, whatever its binding. A call in a class body has no path facts, so a guarded effect there
   gives UNKNOWN.
3. Python collector: a bare decorator (`@d`, not `@d(...)`) that a function encloses is the call
   `d(g)`. The collector records it as an unresolved call at the place of the decorator: its
   evidence shows no call, so the replay check cannot bind it.

**Problem.** Each form gave PASS with no gap. The extern crate compiles only through a link that a
`build.rs` prints, which the collector does not read. A class-body call had no binding and no path
facts, so no limit applied. A decorator application has no call node, so no call record existed.

**Rejected.** (a) Read `build.rs`: its output is the result of a program. (b) Give a class-body
call the path facts of its function: the replay check in `ir/` re-derives each fact, and the
frozen `ir/` cannot grow. (c) Record every decorator as a call: a module-level decorator changes
the call facts of almost every report, and no rule needs it yet.

**Limit.** A class-body effect gives UNKNOWN, not FAIL. A call without path facts in a nested
function of the condition scope also gives UNKNOWN. A module-level decorator stays without a call
record, so a call rule does not see it (#759).

**Tests.** `tests/test_collector_false_pass_rust_layout.py`,
`tests/test_guarded_effect_hidden_calls.py`, `resolve_tests.rs`, `scan_tests.rs`.
