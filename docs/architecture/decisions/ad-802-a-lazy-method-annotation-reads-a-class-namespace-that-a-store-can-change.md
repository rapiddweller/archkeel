# AD-802 A lazy method annotation reads a class namespace that a store can change

**Status.** Accepted (lead decision 2 on #1523, option B). Part of #880, closes #1523. It amends AD-550 and AD-283.

**Reason.** On Python 3.14 a method annotation is evaluated when something reads it, in the namespace of its class (PEP 649). `class Box: __slots__ = ('object',); def f(self, x: object)` reads `x` as the member descriptor of the slot. A store `app.api.Box.object = app.api.Hidden` in a script reads it as `Hidden`. The collector read the project as Python 3.11 (`requires-python = ">=3.11"`), proved `object` as the builtin, and `boundary_types` passed the allowance for `object`. Python 3.14 confirms both values.

**Decision.**
1. Annotations are lazy when the project can run on Python 3.14 (`requirement::lazy_annotations`). That is when the run reads it as 3.14, or when its `requires-python` range does not end at or below 3.14. A range that the collector cannot read counts as allowing 3.14. Without a range, a `python` setting below 3.14 is the statement of the project.
2. A module with `from __future__ import annotations` keeps its proofs: its annotations are strings, and Python does not evaluate them in the class namespace.
3. In a lazy module, a name in the annotation of a method is unproven (`Unproven::LazyClassNamespace`) in three cases:
   - it is a `__slots__` entry of the class, or the body computes `__slots__`;
   - an attribute store of the same name is in a file of the scan or in a non-test file of the repository (`ClassWrites`);
   - any such file calls `setattr`, `delattr`, `__setattr__` or `__delattr__` with a computed name, or uses one of them as a value.
4. The model reads the cause as `GapCause::LazyClassNamespace`. The reason of the row names what the user can do, in words that name no language: "narrow the version range of the project, make the annotations strings, or remove the namespace write". The core names no language (WP6-0). The text output of the shell (`REASON_WORDS`) says it for a Python project: narrow `requires-python` below 3.14, add `from __future__ import annotations`, or remove the namespace write.

**Why it is sound.** A class namespace gets a name after its statement only by a slot, a store or a writer function. A store does not show whether its value is a class, so each store of the name counts. A store in test code, in an installed package or in a metaclass outside the scan is covered by the stated premise of AD-770: such code "writes no binding of a module or class of the scan". A class body binder was already hidden for every version (AD-283).

**Measured.**
- The FastAPI reference project (no `boundary_types` rule): PASS 3/0/0.
- The shell self-check (no `boundary_types` rule): 26/0/0.
- The native self-check matches the pinned baseline.
- The two showcase `boundary_types` rules are `F-architecture` `APP-TYPES-NOT-DICT` and `python-stdlib-demo` `STDLIB-TYPES-DECLARED`. Both allow 3.14, and both were UNKNOWN on main for other gaps. Neither gets a `lazy_class_namespace` row, and their gap counts stay at 2 and 5. 0 rules change.

**Tests.** `tests/test_collector_false_pass_python_lazy_annotations.py`: the slot and outside-write plants of #1550, with the Python 3.14 truth when 3.14 is installed. The controls are a range below 3.14 and `from __future__ import annotations`. Also `survey/declared/shapes_tests.rs`, `requirement_tests.rs` and `model/src/boundary_judge_tests.rs`.
