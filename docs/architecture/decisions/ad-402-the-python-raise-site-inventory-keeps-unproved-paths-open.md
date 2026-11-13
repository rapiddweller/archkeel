# AD-402 The Python raise-site inventory keeps unproved paths open

**Status.** Accepted for #880. It extends AD-389. It does not close #1072.
The store must still refuse the native Python reply.

**Problem.** The review of PR #1091 finds 17 classes of compiler refusals with native trees.
Passing generated probes does not prove that the compiler checks are complete.

**Decision.**
1. Keep an inventory of explicit error calls in pinned, read-only CPython sources.
   The tags are v3.11.12, v3.12.13, v3.13.15 and v3.14.7.
   `tests/python_compile_messages.json` pins the files, hashes, functions, calls and message strings.
   The inventory includes the requested compiler, symbol table, future, AST, parser and tokenizer files.
   It also includes assembly and control-flow graph errors. Only 3.14 has `Python/codegen.c` in these tags.
2. `tests/python_compile_sites.json` has one row for each pinned call.
   A source witness must fail real `compile(source, "p.py", "exec", dont_inherit=True)`.
   Native must refuse it with the pinned reason, incomplete scope and no file facts.
   A missing row fails the test. A witness that compiles fails the test.
   A matching message is evidence, not proof of every path to the C call.
   An unwitnessed call stays `UNPROVED`. It is never counted as `REFUSED`.
3. Use the default recursion limit of 1,000. Do not raise it to the host collector's 20,000.
   On 3.11, an `elif` chain with depth plus clause count above 900 gets a named bound gap.
   Keep the existing parser, depth and work bounds. Each new input loop has an exact work test.
4. Put the added checks under `parse.compilercheck`.
   The `py-parse` component owns it. Existing upward-import plants hold the direction.
   Shared expression, pattern, scope, string and token checks keep their existing lower owners.
5. Refuse the 100 review sources on each minor where CPython refuses them.
   H1–H5 now have pinned scope/name families and CPython rules in `python_compile_review_families.py`.
   Also check star-unpacking operand limits, mangled duplicate parameters and both declaration orders.
   Check surrogate escapes in docstrings on 3.13 and 3.14, not in ordinary assigned strings.
   `_PyCompile_CleanDoc` converts these docstrings to UTF-8 and can raise `UnicodeEncodeError`.
   The current wire vocabulary writes a named syntax-family gap, not that exception class.

**Limits.** The inventory has 1,334 calls: 285 / 304 / 361 / 384 by minor.
It has 257 message witnesses and 1,077 unproved rows. These are not 1,077 known unsafe acceptances.
The scanner does not prove indirect error propagation, dynamic message selection or source reachability.
Many AST-validator failures need a caller-built AST, not source text. Their reachability stays unproved.
Allocation failure depends on the process memory, not only on source text.
Warning filters and other interpreter settings also need a separate rule before completeness is claimed.
These missing proofs keep #1072 open even though every current witness gets a native gap.
`compiler_message` must equal the live compiler message. Coarse native reasons cannot replace it.
No Make target or workflow sets `ARCHKEEL_CPYTHON_SOURCES`. Source hash/extractor comparison is opt-in, not gated.
An unset variable produces a visible skip. Pytest uses `-rs` to show the reason.

The static-block check walks all branches, including branches CPython can remove.
It reserves one cleanup block for each async function. These are conservative choices at the block bound.
The 900-clause recursion bound can refuse a shorter chain that CPython accepts.
Each such refusal has a named file gap. No file in either measured corpus is newly refused.
All four minors compare 9,137 files: 9,137 equal, zero stricter and zero unsafe acceptances.
Private corpora contribute only aggregate counts. No production `src/` file changes.
Two parser limits remain: Tangut named escapes on 3.13/3.14 (`Got unexpected unicode`), and
single-quoted format specs with a literal newline on 3.12 (named newline gap).
F2, walrus in a comprehension in an ordinary annotation on 3.14, is fixed; type scopes stay restricted.
The self-check stays at 0 PASS, 1 FAIL, 42 UNKNOWN, 39 pinned gaps and 7 known violations.
The new module uses the existing parse component. No rule, gap or violation count changes.

**Rejected.** More passing probes as a completeness claim; unwitnessed sites marked covered;
embedding an interpreter; enabling the native reply; and weakening the compiler oracle.

**Tests.** `test_collector_native_python_compile_sites.py` checks the inventory and witnesses.
`test_collector_native_python_review.py` has no expected failures for the 100 review sources.
`test_collector_native_python_compiler.py` checks source-audit cases and accepted neighbours.
Rust tests pin work charges. The PR records fail-first runs, fault injections and the local gate.
