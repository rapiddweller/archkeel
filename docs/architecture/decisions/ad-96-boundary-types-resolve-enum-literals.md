# AD-96: Boundary types resolve proven enum members in Literal

`boundary_types` accepts `Literal[State.READY]` only when `State` resolves to one
statically recognized enum class and `READY` is assigned one literal value in that
class body. Missing, repeated, dynamically assigned, or non-enum attributes remain
UNKNOWN. This recognizes a value inside `Literal`; it does not treat `State.READY`
as a type annotation.
