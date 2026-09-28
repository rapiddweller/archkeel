# AD-121 `boundary_types` checks methods of exported classes

The analyzer checks public methods, constructors, and special methods only when their declaring
class is proven through the component's declared facade. Only stable, unshadowed imports of
`typing.overload` or `typing_extensions.overload` define the public callable surface. Receiver
parameters follow the resolved instance, class, or static method kind; variadic parameters are
never receivers. An exported class with an unresolved custom base reports `inherited_surface`
UNKNOWN; framework-root exemptions require a proven, unshadowed binding.
Parameterized bases are classified by their AST root, so `Generic[T]` stays a framework marker
while `Base[T]` remains a custom base.

The self-observation adds seven undecidable signature positions and records inherited surfaces
explicitly as UNKNOWN. The baseline records the measured values (`unknown_positions: 48`,
`calls_unresolved: 572`); it does not claim these positions are resolved or hide new method findings.
The two added unresolved calls are `alias.name.split` and the local `base_root` helper; the
accepted budget change is recorded in `ad-121-budget-amendment.json`.

Check: `tests/test_boundary_types_non_init_facades.py`, the boundary type test group, and
`make self-observation`.
