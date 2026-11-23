# AD-1062 A literal `__call__` attribute is the same read as the plain attribute

**Status.** Accepted (lead decision, 2026-11-23). It amends item 8 of [AD-1058](ad-1058-receiver-annotation-and-exposure-proofs-of-the-trojan-horse-rules-are-tightened.md) and the allow-list of [AD-1053](ad-1053-a-computed-attribute-name-on-an-unproved-receiver-is-a-trojan-horse.md).

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** The nightly run of the real FastAPI pin went from PASS to UNKNOWN with 10 `dynamic_import` gaps. Six gaps were `getattr(x, "__call__", None)` (`fastapi/dependencies/models.py`), the usual test "is this value callable". The rule of AD-1058 item 8 treated each literal dunder that is not on the allow-list as a site. A refusal of an ordinary read is a precision loss, and the nightly shows its cost on a real project.

**Premise.** `getattr(x, "__call__")` with a literal name returns the same object as the plain read `x.__call__`. The scan has never treated `x.__call__` as a site. So the literal form hands out nothing that the plain form does not hand out. The dangerous follow-on reads of the result (`__self__`, `__globals__`, `__code__`, `__defaults__`, `__class__`) are each a site of their own, in both forms.

**Decision.**
1. `__call__` joins `PLAIN_DUNDER` in `native/python/src/survey/hazards_comprehension.rs`. This is the only list of the allow-list names (SPOT). It now holds `__name__`, `__doc__`, `__file__`, `__version__`, `__all__`, `__module__`, `__qualname__` and `__call__`.
2. A literal `getattr(x, "__call__")` does not take the one-attribute shortcut of AD-530 (`reads_one_attribute`). The scan reads `x` too, as it reads `x` in `x.__call__`, because the result is `x` itself. So the loaders stay sites by their own name: `getattr(__import__, "__call__")("app.lib")` (the first plant run gave PASS without this rule), `getattr(exec, "__call__")(text)`, `getattr(im, "__call__")("app.lib")` after `from importlib import import_module as im`, and `getattr(importlib.import_module, "__call__")("app.lib")`. A computed name stays a site: `getattr(f, n)`.
3. A write of `__call__` (`setattr(C, "__call__", f)`) is not a read and is unchanged.

**Accepted trojan horses.** Four gaps stay on the real FastAPI pin, by owner decision: `getattr(field_info, attr, ...)` (`_compat/v2.py`), `setattr(new_field_info, name, v)` (`_compat/v2.py`), `vars(obj)` (`encoders.py`) and the pass-through `__getattr__` of `routing.py`. Each reads or writes an attribute by a computed name on a value that the scan cannot prove. No rule changes for them. The fixture pin records the result: status UNKNOWN, exit 2.

**Rejected.** (a) Keep the site and add declarations in the FastAPI fixture: the six calls are not a trojan horse, so a declaration would hide the real limit. (b) Clear every dunder: `__dict__`, `__getattribute__` and `__class__` hand out reflection (AD-1058).

**Limit.** Both forms run the same lookup, with the same `__getattr__` and `__getattribute__` hooks of the class, so the premise holds for any class. What the hook returns is out of the scan, for the plain read as before.

**Tests.** `tests/test_collector_false_pass_python_trojan_literal.py` (CPython 3.12 runs each plant; the sweep of all dunders now clears `__call__`, and the control `getattr(c, "__call__", None)` keeps PASS), `hazards_receiver_tests.rs` (the exact allow-list and the literal forms), `fixtures/matrix.json` (the real FastAPI pin).
