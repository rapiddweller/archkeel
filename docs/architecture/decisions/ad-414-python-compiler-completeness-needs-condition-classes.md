# AD-414 Python compiler completeness needs condition classes

**Status.** Accepted for #1072 and #880. Extends AD-402. The Python reply stays refused.

**Problem.** A message witness does not establish coverage of a compiler condition.
The remaining 1,077 calls need source reachability proofs and condition families.

**Decision.** Classify every remaining call before adding checks.
Keep the original message-witness rows. Do not invent a source witness for a source-unreachable condition.
`python_compile_classes.py` defines the condition classes and quotes their source-entry proofs.
`python_compile_completeness.json` pins class membership and the current UNPROVED count.
The original table keeps 1,077 unwitnessed rows, but 494 condition rows remain UNPROVED.
This distinction changes no native acceptance or production reply.

| Class | Rows | Proof |
|---|---:|---|
| A: AST structure | 120 | Parser shape invariants; AST-object validation is a separate entry |
| A: type comments | 8 | The oracle does not set `PyCF_TYPE_COMMENTS` |
| A: other parser modes | 6 | The oracle selects exec without incomplete-input flags |
| A: instruction APIs | 5 | Caller-built instruction objects, not the source compiler |
| A: pre-3.6 feature version | 4 | The oracle selects minor 11 through 14 |
| A: file/readline tokenizers | 4 | The source-string entry uses neither tokenizer |
| A: declarations | 3 | A declaration is not an executable raise call |
| B: grammar conditions | 433 | Generated rule-alternative families and accepted neighbours |
| C: native trees for refusals | 0 | No such case in the touched families on four minors |
| D: unresolved conditions | 494 | Counted by class, with reasons in the summary |

Expand grammar alternatives through 21 suite positions, with and without future annotations.
Record exact real-compiler exception classes and messages as four outcome digests, not a large case file.
Test every generated source against its requested native minor. Refused files must emit gaps, not facts.
Retain the original message inventory. Message matches alone cannot establish a new condition class.
Keep source-independent resource failures separate from source syntax conditions.
Do not call an allocation failure unreachable merely because a source probe cannot reproduce it.
Use public CPython sources and generated probes only for committed evidence.

**Rejected.** Counting message matches as complete control-flow proofs, or treating resource failures as syntax errors.

**Limit.** The target of fewer than 300 UNPROVED rows is not met in this bounded grammar/entry-proof slice.
Resource failures (139), diagnostic forwarding, scope, string, lexer and recursion conditions remain open.
AST identifier and recursion checks remain open, including debug-build behavior.
The two parser false-refusal classes of AD-402 remain. No new false refusal is allowed.
The store stays closed. The lead must assign the next unresolved condition classes before #1072 can close.

**Tests.** `test_collector_native_python_completeness.py` pins initial counts and exact proof-class membership.
It checks the generated families, compiler outcome digests and named gaps without file facts.
