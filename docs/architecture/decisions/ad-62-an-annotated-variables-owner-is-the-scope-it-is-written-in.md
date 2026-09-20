# AD-62 An annotated variable's owner is the scope it is written in, not its bare name

Since `any_annotation` joined `ForbiddenConstructKind` (AD-27), `collect_typing_signals` has given
an `ast.AnnAssign` the owner `annotation_text(node.target) or module.module` -- for a plain `Name`
target, the bare identifier, with no module, class or function prefix at all. `_construct_violations`
scopes a signal by `owner.split(":", 1)[0]` and `in_scope(scope, rule.source)`, a dotted-prefix
match; a bare name such as `PROBE_MODULE_VAR` or `probe_attr` never starts with `archkeel`, so it
never matched a `source`-scoped rule. A parameter's owner, `f"{module.module}.{node.name}:{arg}"`,
carried the module correctly and so was never blind. The result: `CONSTRUCT-NO-ANY` has enforced
`Any` in a function parameter and a return type since AD-27, and has been structurally unable to
see `Any` in a module-level or class-level annotated variable for the same span -- every release
from AD-27 forward reported a clean architecture while `src/archkeel/ir/widening.py`'s
`_DataclassInstance.__dataclass_fields__: ClassVar[dict[str, Any]]` sat outside both of
`CONSTRUCT-NO-ANY`'s `allowed_sources`, unreported. Three probes added to a non-exempt module
(a module variable, a class attribute, a function parameter, each `dict[str, Any]` or `Any`)
confirmed it: `archkeel validate --root .` found one violation, not three.

The fix gives an `AnnAssign` the same kind of owner a function already gets: `collect_typing_signals`
now walks each module with a `_walk_typing_signals` recursion that carries the enclosing scope
downward, exactly the way `symbols.py`'s `walk_class` builds a qualified name by recursion instead
of `ast.walk`'s flat, scope-blind traversal. A module-level variable's owner is
`<module>.<name>`; a class-level one, `<module>.<class chain>.<name>`; a function-local one,
`<module>.<function chain>.<name>`. The same recursion fixed a second instance of the identical
bug in the same function: a nested function's or a method's owner was `f"{module.module}.{name}"`,
built from a flat `ast.walk` that also forgot every enclosing class or function, so
`archkeel.ir.lock.ProbeClass.method` was reported as `archkeel.ir.lock.method`. The module prefix
was always right, so this never caused the blindness AD-27 reported, but it is the same shape of
mistake in the same function the walk was already being rewritten to fix, so it moved with it.

For a target that is not a plain `Name` -- `self.x: int`, `a.b: int`, `a[0]: int` -- the owner is
`<scope>.<annotation_text(target)>`: the target's own source text, appended verbatim, never
resolved. Resolving `self` to the enclosing class was rejected: `self` is a convention, not a
keyword, an attribute can be annotated outside `__init__`, and guessing which class it names is
exactly the kind of inference AD-49's Rejected section already ruled out for a construct's owner.
Rendering the literal text instead means `self.x` and `a.b` and `a[0]` can never collide with a
same-named local, and the scope a reader sees is always the one the annotation was actually written
in.

Rejected: keeping `ast.walk` and building a `dict[int, str]` of node id to scope on the side, the
way `contexts.py`'s private `_function_class_owners` does for its own, narrower purpose (class
scope only, for state-access attribution, not a rule-scoped owner) -- a second walk-plus-side-table
next to `symbols.py`'s recursive one would be a second way to solve the one problem SPOT already
has an answer for. `calls.py`, `contexts.py`, `imports.py` and `symbols.py` were checked for the
same defect: none compute a rule-scoped owner from an unscoped `ast.walk`.  `calls.py`'s local
receiver typing reads `AnnAssign` only through `source.own_scope`, already confined to one
function's own body. `contexts.py` reads a class's `AnnAssign` fields from `context_node.body`
directly and a method's `self.x` fields from `ast.walk` of that one already-identified method, both
already scoped by construction. `imports.py`'s `_shadowed_names` reads only `module.tree.body`,
top-level statements, by design. `symbols.py`'s `_class_is_frozen` reads only `node.body` of the one
class it was given. None needed a fix.

Once the owner is right, `CONSTRUCT-NO-ANY` found exactly the one occurrence AD-27's gap had hidden
for its whole life: `archkeel.ir.widening._DataclassInstance.__dataclass_fields__`. Its `Any` is
structural, not incidental: `_DataclassInstance` is a hand-written stand-in for
`_typeshed.DataclassInstance` (a stub-only type, not importable at runtime), whose own
`__dataclass_fields__` is `ClassVar[dict[str, Field[Any]]]` because a dataclass's fields carry no
one shared type. There is no more precise annotation to give it, so the contract's `exact_sources`
names exactly that one scope, with the reason recorded in the rule's own `rationale` (AD-49):
widening `allowed_sources` to the whole module, or the package, was rejected, since nothing else in
`archkeel.ir.widening` needs the exemption and a wider grant would have hidden a real `Any` there
just as this one was hidden before. `ANALYZER_VERSION` rises to 0.26.0 (AD-3): a contract now sees
violations no earlier analyzer build could find.

Limit: two different methods that each annotate the same `self.x` produce two different owners
(one per method scope), so an `exact_sources` entry naming one does not cover the other; this is
the same trade AD-49 already accepts for functions sharing a name across modules, now visible for
attributes too, and an `allowed_sources` prefix on the shared class still covers every method
beneath it. The owner is still a string built for scope matching, not a resolvable reference: `a[0]`
and `a.b` never resolve to a real symbol, so a rule can exempt the write site but cannot ask what
`a` actually is. Check: `tests/test_analyzer.py::test_collect_typing_signals_scopes_annassign_owner_to_its_enclosing_scope`
red on the pre-fix owner for a module variable, a class attribute and a function-local variable, and
green after, while the parameter case it also covers never moved;
`tests/test_analyzer.py::test_collect_typing_signals_scopes_a_nested_function_to_its_enclosing_function`
for the method/closure case; `fixtures/demo_catalog_constructs.py`'s `class-a-construct-any_annotation`
row now covers both a variable and a parameter, regenerated into `docs/architecture-demo.md`; and
`archkeel validate --root . --json` exits 0 on this repository, honestly, with the one real
occurrence named in `exact_sources` rather than folded into a wider `allowed_sources`.
