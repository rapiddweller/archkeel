# AD-1540: A read of a re-exported module name is keyed by its receiver

Status: accepted. Issue #2142. Narrows AD-1152 (#2085). The soundness rule of AD-1152 stays: the
first read of a module value is a site.

## Why

AD-1152 made each read `x.name` a site when `name` is a re-exported module name (`xml`, `warnings`,
`multiprocessing`). It did not look at `x`. A read of a field of an object, such as `self.xml`, is no
read of a module of the project.

## Decision

A read `x.name` is no site when `x` is provably no module:

1. `self` or `cls`, the first parameter of a method of a proven class. The method must not bind the name
   again: no assignment, loop or `with` target, parameter of a nested function or lambda, import,
   definition, `except` name, pattern, `global` or `nonlocal`. A method with a decorator that is not
   `property`, `classmethod`, `abstractmethod` or `cached_property` has no receiver proof. `staticmethod`
   is one of them.
2. A local of an outermost function that is bound once in the module, to a literal, a display, a
   comprehension or a call of a proven class.
3. A literal, a display, a comprehension or a call of a proven class as the receiver itself.

A proven class is a module-level class, bound once, with no metaclass and no `__new__`. It has no
decorator but `dataclass`, `final`, `total_ordering` and `unique`. Its bases are proven classes of the
scan (resolved through the import bindings) or plain bases (`object`, `ABC`, `Enum`, `Exception`, `dict`,
...). A relative import binds nothing here, so a class that it names is unproven. `ModuleType` is no plain
base: `sys.modules[name].__class__ = K` makes a `K` that extends it a module. A class that is not proven
makes each base of it unproven, also a class that is nested or bound twice.

Everything else stays a site: an import binding, a parameter, an attribute, a call result, a local bound
twice. A parameter with an annotation is no proof, because a module can be passed as an argument.

## Measured

CE `e1000a6e` and EE `9177e3743`, the core of main and the core of this change.

| Repository | `module_value` sites before | after | Rules PASS / UNKNOWN / FAIL before and after |
|---|---|---|---|
| CE | 6 | 6 | 176 / 99 / 1 |
| EE | 24 | 24 | 256 / 223 / 0 |

No site of CE or EE changes. Each of the 30 reads has a parameter or a call result as receiver, for
example `request: ReferenceRequest`, `message: WorkerMessage`, `model: SetupModel`. A proof for these
needs the annotation (unsound) or a flow rule for a project module that is passed as a value
(`f(util)` is no site today). That is a separate decision.

## Tests

- Rust, `hazards_module_value_tests.rs`: 21 receivers that stay a site, 12 that are no site, and the
  class proof through an import. Five mutations (any receiver proven, no rebind check, no subclass
  closure, no nested-class taint, no single-binder check) each fail a test.
- `tests/test_collector_false_pass_python_module_attribute.py`: 7 new plants that run under CPython 3.12
  and must stay UNKNOWN or FAIL, and 3 controls that must be PASS.
