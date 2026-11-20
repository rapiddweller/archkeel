# AD-890 A harmless pair does not hold the requires receipt

**Status.** Accepted. This narrows the kept pair reading of AD-418. AD-922 extends the port proof.

**Problem.** A kept pair gap can hold `complete_requires` even when the possible edge cannot
violate that rule. Other rules can still read the same gap.

**Decision.** The receipt ignores a pair only when both ends are observed and have exactly one
owner, and either share that owner or the source has a `requires` entry without `through` for
the target. The rule still reads every other pair. The run still reads each kept pair.

`crossings` ignores an edge within one component. For a crossing, `assessment` accepts an
unrestricted `requires` entry for every module and symbol of the target component. These facts
prove that the possible edge adds neither a violation nor an undecided position.

**Rejected.** Accept every declared target: a `through` entry can forbid its module or symbol.
Drop the pair from the run: another rule can read it.

**Limit.** This does not prove an unobserved end, an ambiguous owner, or a symbol port.
Other gaps and missing receipts remain independent reasons for UNKNOWN.

**Tests.** `native/eval/src/scoped_requires_tests.rs` checks both harmless cases, an open port,
an unseen target and an observed forbidden crossing. The Rust collector control in
`tests/test_collector_false_pass_rust_own_file_method.py` checks both contracts against one gap.
