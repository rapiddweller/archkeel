# AD-389 The native Python collector checks compiler refusals before facts

**Status.** Accepted for #880, #1072 and the Python structure part of #1083.
The number is 387 + 2: main and the open PRs held 387 when this slice started.
One number stays free for the deletion slice in work.

**Problem.** Ruff can build a tree for a source that CPython refuses.
The import survey then writes facts for a file that the interpreter cannot read.
The symbol table also imported shared module data through the higher survey layer.

**Decision.**
1. `facts::pyminor::PyMinor` has exactly four variants: 3.11 through 3.14.
   `PythonVersion` makes it once during request decode and keeps the original wire text.
   All version choices use exhaustive matches. An unknown minor is a named decode error.
2. The collection spine is survey -> symbols -> unparse -> module, tree and parse.
   Each lower component has a forbidden-direction rule to each higher component.
   The existing complete-requires rule holds the adapters and the lower source helpers.
   Each new forbidden rule has a planted import and path, also with a matching requires entry.
3. `module.rs` owns `Module`, `EvidenceMap` and the named `Location`.
   Both the survey and symbols read this lower component. Neither owns the shared data.
   `facts::pyrepr` owns string repr and the per-minor printable tables.
   `pytext::rstrip` owns Python trailing white space. The carriers are `ConversionFlag`, `Quotes`,
   `ParseFailure`, `TextFailure`, `LexicalScope` and the named dump input `Modules`.
4. The parse checks named Unicode escapes against the Unicode database of the request's minor.
   A generated table lists unassigned ranges. Lowercase Hangul names fail on 3.11 and 3.12.
   Raw strings do not decode names. The 3.12 raw format-spec decode failure gets its own gap.
5. The token scan rejects replacement fields beyond the CPython format-spec limit.
   Ruff keeps these fields; the CPython view must never truncate them without a parse failure.
   A boolean starred expression must enclose the whole boolean expression in parentheses.
6. The post-parse checks also cover control-flow scope, duplicate parameters, global and
   nonlocal declarations, future imports, starred targets, comprehensions and pattern bindings.
   Reserved names and control flow that exits an exception-group handler also get checked.
   These checks use real `compile()` results as the oracle, not a handwritten outcome table.
   CPython's AST-only reader can accept compiler-invalid sources. Native refuses them with a
   named file gap. This is an explicit stricter extension of AD-367.
7. The token scan charges source bytes and tokens. Additional validation charges each input walk.
    Each counter stops after 2,000,000 units. A partial scope scan also exhausts the counter.
    The post-parse visitor stops at 1,000 levels. The scope scan stops at 200 levels.
   Pattern validation stops at 100 levels. Each stop gives a named gap and no file facts.
   The bounds also stop 3,000-level attribute and call chains that CPython 3.11 refuses.
8. The host codec and store still refuse the native Python reply. No Python behavior changes.
9. The L-41 float probe differs: Rust picks an odd tie digit for `2.0**-25`.
   Explicit standard-library precision rounds the shortest digit count to even. No copy or
   dependency is needed. A test compares every power of two and 2,000 generated floats.

**Rejected.** A silent 3.11 default for unknown minors; a second string repr; a tree for a
compiler-invalid source; embedding an interpreter; and new RustPython dependencies.

**Limits.** The validator is not a second Python compiler. The probe suite checks its refusal
classes against each supported interpreter. A newly found unproved class must get a named gap.
A source accepted by CPython can reach a work or depth bound. The gap states that bound.
Named-escape checks can also refuse a literal that joins a valid named escape with an unassigned
literal character. This class stays a named gap until the escape-to-character map is needed.
The 3.12 format-spec text gaps and surrogate gaps of AD-377 stay unchanged.
The native self-check changes from 31 to 43 UNKNOWN rules and from 50 to 57 pinned gaps.
It has no violations. The seven added gaps are conservative `at` and `is_link` method candidates
from the module move and the changed survey source. They are not proved upward edges.

**Tests.** The structure-only build equals main on all dump modes and the reply for the fixtures,
`src/` and all Python corpora of the measured set, on all four minors.
`test_collector_native_python_refusals.py` runs each issue case and 297 generated sources against
the real CPython. It checks refusal, a named gap, incomplete scope and no facts for issue cases.
`postparse_tests.rs` guards parenthesized boolean stars. `work.rs` checks the inclusive counter.
`test_native_self_contract.py` plants all 12 upward pairs in three forms.
The PR records the per-version tables, fault injections and the full local gate.
