# AD-1053 A computed attribute name on an unproved receiver is a trojan horse

**Status.** Accepted (owner decision on #1967, 2026-11-22). It narrows the premise of [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md).

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** `getattr(f, '__co' + 'de__')` gives the code of a function. Python imported `app.lib` in five plants and the rule gave PASS with no gap.

**Decision.** The Python collector gives a `dynamic_import` gap for a call of the visible builtin `getattr`, `setattr` or `delattr`, or of the method `__getattribute__`, `__setattr__` or `__delattr__` (`x.m(name)` has the receiver `x`, `C.m(x, name)` has the receiver `x`), whose attribute name is not a string literal. A declaration by name can state its reach (AD-1052). AD-1058 sets the proofs that remain:
- The call is no site only when the name is a literal that hands out no reflection, or a local that the module binds exactly once, in an outermost function, to such a literal. A literal that names reflection stays a site (`__dict__`, `__getattribute__`, `__class__`, an access name); only a short allow-list of dunders that hand out text (`__name__`, `__doc__`, `__file__`, `__version__`, `__all__`, `__module__`, `__qualname__`) is cleared.
- No receiver is proven: not `self`, not `cls`, not a class, not a module, not a local that a loader call binds.

**Limits.** A file outside the scan roots is not read for this rule: the premise of the run says that outside code writes no binding of the scan. Without this exception, one computed `getattr` in a test file of archkeel turned off call resolution of the shell scan (found by `make self-validate-shell`). A loop over a literal tuple of names is not proven; its site stays. A module that is imported twice keeps its site, like every module. The lazy `__getattr__` table of AD-654 has no exemption (AD-1058): its `getattr` calls keep their site until a contract declares them.

**Superseded in part.** AD-1058 removes the receiver proofs of the first version (`self`, `cls`, a class, a module, a loaded local), makes the other forms of access sites, and lists the open limits.

**Measured.** datamimic-ee 70 to 88 collection gaps (18 sites), datamimic-ce 55 to 58 (3 sites). No rule changes: the rules were UNKNOWN already.

**Tests.** `tests/test_collector_false_pass_python_trojan_attribute.py`, `tests/test_collector_false_pass_python_trojan_literal.py` and `tests/test_collector_false_pass_python_trojan_plants.py` (every plant imports `app.lib` in Python 3.12 and must not give PASS; the controls with a literal name clear), `hazards_receiver_tests.rs`.
