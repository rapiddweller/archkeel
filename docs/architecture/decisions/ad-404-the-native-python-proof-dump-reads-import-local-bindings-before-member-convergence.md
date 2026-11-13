# AD-404 The native Python proof dump reads import-local bindings before member convergence

**Status.** Accepted. Part of #880, Python slice 3.

**Reason.** Member convergence consumes stable bindings, property operations and class-body
admission. Slice 2 measures these inputs with an empty alias map. That map cannot prove imported
builtin decorators. Port the local proofs before the cross-module convergence loop.

**Measurement.** The selected 27 function spans in `source.py` contain 619 lines.
The PR maps each analyzer file and each function span. It separates compared boundary spans
from deletion eligibility. No partly assembled runtime function earns deletion credit.

**Decision.**
1. Add `--dump-proofs <minor> <root>` under the existing `dump` feature. Each input line names
   one snapshot file. The dump compares one parsed module after static import binding.
   The module-name set contains that module only. Provider proof sets are empty.
2. Compare stable and unique bindings, decorator and property proofs, inert class bodies,
   explicit Generic parameters, type-alias admission and intrinsic nullable aliases.
   Keep property operations in source order. A later binder can cancel an earlier property.
   A decorator alias must have a stable import before the declaration that consumes it.
3. Keep all new modules in `py-symbols`, under `bindings.proofs`. They read `py-module`,
   `py-tree`, `py-unparse` and the work counter in `py-parse`. No upward edge is added.
4. Reuse the binding scan, namespace checks and statement admission. Resolve aliases only when
   the new dump populates them. The pre-import dump keeps its empty map and exact work counts.
5. Keep the 64,000,000-unit work budget and the 33,554,432-byte output bound of AD-396.
   Charge each input loop. Count each retained output row before retention and the final frame.
   A work or output refusal has `full_scope: false`, a named gap and no partial data.
   Walks use heap stacks. Literal admission has a 100-level recursion bound and a named gap.
6. Do not write a production section. The host and store still refuse the native Python reply
   until #1072 closes. No Python analyzer, IR or check code changes.

**Rejected.** Guessing decorator ownership from spelling; claiming member convergence from
local proofs; allowing a lower layer to call the survey; and retaining partial output on refusal.

**Limits.** Provider-proven expressions, cross-module import origins, overload-group convergence,
native factory headers and runtime integration remain for later slices. This dump does not
prove those states. The PR lists measured spans, partial historical coverage and remaining work.
No Python deletion or general speed improvement is claimed.

**Tests.** `test_collector_native_python_proofs.py` compares the unchanged Python functions,
fixtures, corpora and 264 generated probes. Exact work counts hold all 78 new loop charges.
It checks hostile input, time and peak memory scaling, and an empty corpus failure.
The PR records the four-minor matrix, isolated fault injections and the final gates.
