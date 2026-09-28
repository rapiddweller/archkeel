# AD-121 `boundary_types` checks methods of exported classes

The analyzer checks public methods, constructors, and special methods only when their declaring
class is proven through the component's declared facade. Overload signatures define the public
callable surface. Receiver parameters follow the resolved instance, class, or static method kind.
An exported class with an unresolved custom base reports `inherited_surface` UNKNOWN; known
framework roots do not imply an undecidable application API.
Parameterized bases are classified by their AST root, so `Generic[T]` stays a framework marker
while `Base[T]` remains a custom base.

The self-observation adds seven undecidable signature positions and nine unresolved analyzer
calls. It also records inherited surfaces explicitly as UNKNOWN. The baseline records the
measured values (`unknown_positions: 48`, `calls_unresolved: 570`); it does not claim these
positions are resolved or hide new method findings.

Check: `tests/test_boundary_types_non_init_facades.py`, the boundary type test group, and
`make self-observation`.
