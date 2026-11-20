# AD-972 Withhold literal imports through a replaced loader

**Decision.** Withhold the direct `importlib.import_module` literal edge when
the scan sees a write to that loader. Keep the dynamic-import gap. Reuse the
lexical import bindings and their one-step aliases to identify the writer
and receiver. Keep the write possible when their scope has both import and
other bindings. A local binding that hides an import does not count as that
import.
Cover attribute stores and deletes, attribute writer calls, and literal-key
stores through `__dict__` or `vars`.

**Reason.** A literal argument identifies a target only if the loader is
unchanged. A gap beside a false edge can still produce a false violation.

**Alternatives.** Do not match a local alias spelling or stop the proof for
unrelated writes. Do not infer the order in which modules run.

**Limit.** This does not follow arbitrary aliases, computed attribute names,
or writes outside the scanned modules. It does not change builtin `__import__`
or prove local variable values. It adds no premise.

**Tests.** Native survey tests cover direct and aliased writers, a write in a
second module, the stable literal path, and unrelated writes and open doors.
A CLI test checks that a shadowed receiver still leaves a forbidden edge.
