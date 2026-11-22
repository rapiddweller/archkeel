# AD-1053 A computed attribute name on an unproved receiver is a trojan horse

**Status.** Accepted (owner decision on #1967, 2026-11-22). It narrows the premise of [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md).

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** `getattr(f, '__co' + 'de__')` gives the code of a function. Python imported `app.lib` in five plants and the rule gave PASS with no gap.

**Decision.** The Python collector gives a `dynamic_import` gap (name `getattr`, `setattr` or `__getattribute__`) for a call of the visible builtin `getattr` or `setattr`, or of `x.__getattribute__`, whose attribute name is not a string literal and whose receiver is not proven. A declaration by name can state its reach (AD-1052). There is no gap when:
- the name is a literal, or a local of the function that one assignment binds to a literal and nothing else binds;
- the receiver is a class of the module, the `self` or `cls` of a method that does not rebind it, or a module that a plain `import` binds.

**Limits.** A file outside the scan roots is not read for this rule: the premise of the run says that outside code writes no binding of the scan. Without this exception, one computed `getattr` in a test file of archkeel turned off call resolution of the shell scan (found by `make self-validate-shell`). `g = getattr` and `operator.attrgetter` are not read. A name proven only at module level is not resolved (another module can write it). A receiver that is an imported class stays a site. A module that is imported twice (at module level and inside a function) is not proven either, so `getattr(logging, name)` stays a site; a contract declares it.

**Measured.** datamimic-ee 70 to 88 collection gaps (18 sites), datamimic-ce 55 to 58 (3 sites). No rule changes: the rules were UNKNOWN already.

**Tests.** `tests/test_collector_false_pass_python_trojan_attribute.py` (the five plants of #1967 import `app.lib` in Python 3.12 and give UNKNOWN; controls with a literal, a project class, a module and a declared site clear), `hazards_inert_tests.rs`.
