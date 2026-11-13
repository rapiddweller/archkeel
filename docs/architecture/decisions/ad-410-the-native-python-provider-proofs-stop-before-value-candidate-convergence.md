# AD-410 The native Python provider proofs stop before value candidate convergence

**Status.** Accepted. Part of #880, Python slice 4. AD-410 is free in the open PR inventory.

**Reason.** Member convergence needs provider headers, overload groups, type protection and
directed containment. Import-local decorator proofs alone do not establish these facts.

**Measurement.** The selected 26 function spans in `source.py` contain 882 Python lines.
The port includes the member-reference helpers that these functions call. The PR names every
span and updates the prior 2,176-line ledger. These are compared spans, not deletion credit.

**Decision.**
1. Add `--dump-protection <minor> <root>` only under feature `dump`. Compare one module after
   static import binding, before provider value candidates and import/member convergence.
2. Keep incoming escapes, unsafe external providers and provider-proven expression sets empty.
   The scanned module is an unsafe provider. Compare all header, reference and containment data.
   Compare local constructor candidates separately. Do not install them into the earlier state.
3. Compute explicit escapes without creation uncertainty. Their generic inheritance checks cannot
   admit a native factory: a Generic base excludes both native dataclass and TypedDict headers.
   Pass the complete bound-name set to that initial check. This avoids a circular proof dependency.
4. Reuse the existing bounded scan, namespace checks, property proofs and closure work list.
   Keep the old dumps and their work counts unchanged. Charge each new input loop.
5. Keep the 64,000,000-unit budget and 33,554,432-byte output bound. Refuse the complete table
   on exhaustion. Bound generic inheritance at 100 levels. Keep literal admission at 100 levels.
   Preflight quoted expressions with the bounded parser before expression parsing.
6. Assign the new proof modules to `py-symbols` through the existing `bindings` package.
   Assign quoted parsing to `py-parse`. Add no cycle, external scope or clone exception.
7. Pin the complete set and count of native-stricter files. Include the inherited slice 3 refusals
   and generated star-import refusals in functions and classes. Private corpora give aggregates only.
8. Keep the production reply and store unchanged. Issue #1072 still blocks native Python acceptance.
   Do not change or delete Python analyzer code, facts or checks.

**Rejected.** Prove provider identity from a decorator spelling; use empty escape sets as proof;
hide native-stricter files behind totals; or claim cross-module candidates from a one-module dump.

**Limits.** Numeric and type class-value candidates, map unions, annotation carriers and callable
candidates remain for the next slice. Nonempty provider-proven and incoming-escape states remain
outside this boundary. No production reply, Python deletion or speed improvement is claimed.

**Tests.** `test_collector_native_python_protection.py` compares canonical complete data on
fixtures, corpora and generated branch probes. It pins exact work, refusal sets and work scaling.
The PR records four Python minors, charge-removal faults, hostile inputs and final gates.
