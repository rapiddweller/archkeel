# AD-283 A later class binding blocks every annotation

**Status.** Accepted. Issue #773.

**Decision.** A class-scope annotation can see every binding of its class body. This applies with
and without `from __future__ import annotations`. A name that a class-body statement binds at any
place makes the annotation position UNKNOWN. A dynamic namespace access in the class body
(`locals()`, `vars()`, `globals()`, `exec`, `eval`) can bind any name, so it makes every
annotation of that class UNKNOWN. The rule covers method parameters, method returns and class
fields. The verdict is the same on every host and for every declared Python range.

**Reason.** Python 3.14 evaluates annotations lazily, in the final class namespace (PEP 649).
The analyzer read a module without the future import as eager: only a binding before the
annotation counted. A later `object = Hidden` then gave a proven `object` allowance, but the
3.14 runtime annotation is `Hidden`. The lookup range "whole body" contains the eager range
"before the annotation", so one rule covers the class body for 3.11 to 3.14.

**Rejected.**
- Decide from `requires-python`: lazy only when the range admits 3.14. It changes a verdict only
  for a project capped below 3.14. It needs the requirement in symbol collection, a PEP 440
  parse in the analyzer and a demo pinned for each version.
- Decide from the Python that runs the collector: the verdict then changes with the host.

**Limits.**
- A project that never runs on 3.14 gets UNKNOWN where the eager value is provable, for example
  when a method annotation comes before `object = Hidden`, or a binding is deleted later.
- An annotation-only field named as its type, for example `date: date`, stays UNKNOWN. It does
  not bind the name, but on 3.14 a `__slots__` entry `"date"` does.
- Syntactic module-level rebindings and `TYPE_CHECKING` imports were already UNKNOWN; this rule
  does not change them. A nested class does not see the namespace of its outer class.
- The rule reads the class body only. These writes outside it still give a wrong proof (#775):
  - On 3.14: `__slots__`, `setattr`, a class decorator, or a write to the class or module from
    another module. `source_member_binding_static` is not a fix: construction, `isinstance`
    and `@dataclass` also make it false.
  - On 3.14: a module-level `globals()['object'] = Hidden` after the class, and
    `global object; object = Hidden` inside a method.
  - On every version: a metaclass `__prepare__` that puts the name in the class namespace.
- The native creation check (`_deferred_creation_annotation`) keeps the eager rule for a module
  without the future import. That rule asks for an inert annotation, so it stays fail closed.

**Checks.** `tests/test_boundary_type_native_payloads.py`:
`test_a_later_class_binding_blocks_lazy_and_deferred_annotations`,
`test_a_dynamic_class_body_write_blocks_every_annotation` and
`test_class_field_scope_uncertainty_is_a_source_fact_for_any_name`. The demo row
`class-a-boundary-types-native-payload-lazy-shadow` shows the UNKNOWN verdict.
