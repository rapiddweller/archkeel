# AD-930: A bound type path adds no unread name

**Reason.** AD-932 separates dispatch from a written name. Thirteen pairs still
hold four source-name rules. A written `T::member` can have a known route to `T`
and an unknown route to the impl that supplies `member`.

**Decision.** Reuse the private proof from AD-932 when an exact `use` binding
already records the name of the type in `T::member`. Match the import record to
the binding site, not to the first recorded use of the whole path. Require one
unconditional binding in the same lexical module and a known type. The member
lookup can stay open: a possible impl does not add another written type name.

**Boundary.** Do not use this proof for a path with unresolved binding, generic
arguments, or a macro that can change the binding. A resolved import that names
the forbidden type still fails the rule. Dispatch, Interface, cycle and legacy
rules do not read the new proof. The public facts schema does not change.

**Core.** Use a receiver call for the `Edge::target` method pointer in topology.
The function already has the edge value. The change does not change the target
of the call.

**Checks.** Use a qualified call through a proven import, an alias of the
forbidden type, and an unread import route. Keep the glob, type argument,
pattern, macro, and mixed-cause controls from AD-924 and AD-932.

**Result.** On `8a25894f`, Eval goes from 1 to 0 holding pairs, Report from 2
to 0, Core from 9 to 0, and Model from 1 to 0. All four pass. Store still
passes. The self-check gives 87 PASS, 0 FAIL, and 5 UNKNOWN. All 20,324
collection gap keys stay the same.
