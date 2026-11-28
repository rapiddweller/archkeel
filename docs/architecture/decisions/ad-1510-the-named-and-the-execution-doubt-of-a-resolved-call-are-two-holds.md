# AD-1510: The named doubt and the execution doubt of a resolved call are two holds

Status: accepted. Amends AD-1185. Cut 1 of the native-zero design (`designs/NATIVE-ZERO-DESIGN.md`).
This change can turn a held interface pair into PASS.

## Why

A method call `x.m()` whose receiver the scan cannot type gives each module that has a member `m` a named
candidate. AD-1185 settles the candidate when the compiler resolved the call to a function in another file.
It kept the candidate when an argument of the call could run code of that file (an open type, a callback, a type
of that file). That mixed two doubts:

- Named doubt: does the call name the method `m` of this module? The compiler answered no.
- Execution doubt: can code of this module run through an argument of the call? This is a different question.

Because of the mix, the interface rule held 1,103 pairs on this revision.

## Decision

1. A named candidate whose call the compiler resolved elsewhere (AD-1185: the same one callee in every
   configuration, a library unit, the callee file is not the file of the candidate) leaves the named pairs.
   This holds also when an argument can run code of the candidate file.
2. When an argument can run code of the candidate file (`open`, or the file in `touch`), the candidate does not
   vanish. It becomes an execution candidate with its own evidence: the `impl` keyword of the block in the file
   of the candidate (`ImplBlock::site`). The store requires the evidence of an execution hold in the file of
   the target.
3. The pairs aggregate all sites. A pair is no named pair when every named candidate on it is settled. One
   unsettled named site keeps the pair named. An execution hold of a pair does not read as a named doubt for the
   interface rule (`scope_receipt::open_sites` reads only named holds).
4. `REQUIRES` and the cycle rule read execution holds as before. Their pairs do not change.

## Effect on the self-check (local run, `ARCHKEEL_ALLOW_BUILD=1`, base `a92d2cfcc`)

| Rule | Base | This change |
|---|---:|---:|
| `NATIVE-INTERFACE-BOUNDARY` held pairs | 1,103 | 710 |
| `NATIVE-REQUIRES-COMPLETE` held pairs | 7,820 | 7,820 |
| `NATIVE-NO-MODULE-CYCLES` held pairs | 39 | 39 |
| violations | 0 | 0 |

The gap records do not change (13,285 both): the same pair gaps exist; 393 pairs change from a named gap to an
execution gap. The two `Iterator::chain` cycle candidates keep an open argument, so they stay possible edges
(execution), as the design says.

## Counter-examples that were tried

`tests/test_cli_native_rust_named_doubt.py` runs the real driver with a `cargo run` counter:
- an argument that runs a closure of `b`: the call names no method of `b`; the pair keeps the execution doubt in `REQUIRES`;
- the same call with `use b::S` (an edge): no named site, the interface rule passes; with the mutation (the old rule) it is held;
- two calls on one line: the callee of one does not settle the method of `b` that the other calls (FAIL);
- a call that a macro writes settles nothing;
- the same method name in another file: only the call of that file is settled.

`type_reach_filter_tests.rs` pins the three answers of `resolved_elsewhere`: not settled, settled, settled with an execution doubt.

## Not done yet

- The design counted 427 method records whose compiler call points elsewhere. This change releases 393 interface pairs. The rest stay held: a second named site on the pair is unsettled, or the callee does not hold in all configurations. I did not measure the split.
- The execution hold has the `impl` keyword as evidence, not the member. The member has no site in the scan.
