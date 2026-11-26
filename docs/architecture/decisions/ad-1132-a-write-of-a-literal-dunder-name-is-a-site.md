# AD-1132: A write of a literal dunder name is a site

Status: accepted. Closes #1979. Amends AD-1058.

## Why

Since `cbacb81d1`, `reflective(name, write = true)` in `native/python/src/survey/hazards_comprehension.rs` cleared each
write of a literal dunder name. A write of `__call__`, `__getattr__`, `__getattribute__`, `__init__`, `__new__` or
`__class__` changes what a later plain call, access or construction runs. `setattr(K, "__call__", f)`, `delattr(K, "__call__")`
and `K.__call__ = f` gave no site, so a rule could read PASS. CPython runs each of these plants and a counter file shows
that the hook ran (`tests/test_collector_false_pass_python_dunder_write.py`).

## Decision

1. `reflective(name)` has no write case. A literal dunder write is a site exactly like a literal dunder read. The names with
   an own hazard (`__code__`, `__globals__`, ...) and the names that no behavior reads (`PLAIN_DUNDER`: `__name__`,
   `__doc__`, `__file__`, `__version__`, `__all__`, `__module__`, `__qualname__`) stay clear.
2. An attribute in a store or delete context (`K.__call__ = f`, `del K.__call__`, `K.__init__ += g`, a tuple or `for`
   target) is a site with the kind `setattr` or `delattr`. The receiver is not proven, as in AD-1058.
3. A write of an exception-chain name (`__cause__`, `__context__`, `__traceback__`, `__suppress_context__`, `__notes__`)
   through `x.name = v`, `setattr`, `delattr` or `object.__setattr__` gives no site (#2090), only when no scanned module
   defines a hook that such a write can reach. The scan reads no type, so the receiver is unknown: a class or metaclass with
   `__setattr__` or `__delattr__`, a descriptor (`__set__`, `__delete__`, `__set_name__`), a class member with a chain name (a
   property), a class with a list base (`__notes__`), a `__del__`, or a string of one of the hook names (`type(n, b, {...})`)
   anywhere in the project makes the exemption void. A read stays a site. EE has such hooks (2 sites stay), CE has none
   (8 sites go). The first form of this exemption (#2092, the name only) was a false PASS and was reverted.
4. The change only adds sites. No site is removed and no other proof is narrowed.

## Known limit

A plant that imports a module only through such a write needs a loader that has no site of its own. None was found:
each loader that CPython can reach by name (`__import__`, `import_module`, `runpy`, ...) is a site where it is written.
The tests therefore prove that the write is a site (UNKNOWN), not that a module is loaded without any other site.

## Checks

`native/python/src/survey/hazards_receiver_tests.rs` (each form is one site; a plain name, `__doc__` and `__module__` are none)
and `tests/test_collector_false_pass_python_dunder_write.py` (CPython plants with a counter file, controls that keep PASS).
Mutation: with `reflective` blind to dunder names, 9 of 11 plants read PASS.
