# AD-121 `boundary_types` checks methods of exported classes

The analyzer checks public methods, constructors, and special methods only when their declaring
class is proven through the component's declared facade. Only stable, unshadowed imports of
`typing.overload` or `typing_extensions.overload` define the public callable surface. Receiver
parameters follow the resolved instance, class, or static method kind; variadic parameters are
never receivers. Framework-root exemptions require a proven, unshadowed binding. Parameterized
bases are classified by their AST root, so `Generic[T]` stays a framework marker while `Base[T]`
remains a custom base.

One bounded inherited proof is allowed: a single resolvable direct generic base, explicitly
declared `Generic` TypeVars, and concrete bare class arguments. The analyzer substitutes those
TypeVars in the base's direct public method signatures only. Inherited fields and constructors
remain candidate usage evidence, not proven facade publication. It does not infer the full MRO.
Class-local TypeVar rebinding, repeated bindings, imports, deletes, or class-body control flow make
the effective surface uncertain; affected inherited methods are not emitted as definitive type
positions. The existing `inherited_surface` UNKNOWN remains. Annotation-only subclass names do
not override inherited methods; assignment, import, and deletion are accounted for when deciding
whether a method is shadowed.

Analyzer profile `0.58.0` identifies the inherited-generic metadata and bounded method proof.
The self-observation keeps its existing measured values (`unknown_positions: 48`,
`calls_unresolved: 572`, `typing_positions: 53`); uncertain inherited surfaces remain UNKNOWN.
The earlier AD-121 budget amendment for `alias.name.split` and `base_root` remains recorded in
`ad-121-budget-amendment.json`; this inherited-generic proof adds no unresolved calls.

Public method return types also count as interface usage at each declared contract level;
private methods and unpublished classes do not (#201). The interface demo includes both cases.

Check: `tests/test_class_method_publication.py`, boundary-type and inherited-generic tests,
`make self-observation`, and
`archkeel validate --root . --baseline architecture-baseline.json`.
