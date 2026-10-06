# AD-53 `from pkg import name` follows `pkg/__init__.py`'s own binding before a same-named submodule

Resolve `from pkg import name` through unconditional top-level package bindings before a same-named
submodule. Definitions, assignments, aliases and re-exports can shadow the submodule; `from . import
name` remains a submodule re-export.

This follows Python binding semantics. Conditional bindings, star imports and package `__getattr__`
are not established by this lookup. Proof: [test_analyzer.py](../../../tests/test_analyzer.py).
