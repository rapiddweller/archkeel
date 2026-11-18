# AD-906: Bind Python loader reach to a code constant

**Status.** Proposed. Part of #723.

**Problem.** AD-664 lets a contract name prefixes. A registry already lists the names in
source code. Copying its list into a contract lets the two lists disagree.

**Decision.** Contract 3.18 adds `loads_from` to a loader declaration, in place of `loads`.
Name a module and a tuple binding with `constant`, substitute each tuple member into
`template`, and match the exact `call` text at the declared line. A template has one
placeholder. Targets are exact module names, not prefixes.

The Python collector reads a stable module-level tuple of string literals without importing
the module. It also identifies a direct `importlib.import_module` call with a proven binding.
The neutral model reads these two facts. Other producers and archived replies cannot supply
this bound. Missing, ambiguous or changed call text, a missing tuple, and a target outside
the scan leave the gap open. No part of an invalid declaration applies.

Only the written tuple and the call identity come from the scan. The remaining premise is
that this call loads only the expanded targets and changes only the modules in `changes`.
The verdict names that premise and the tuple's source location. A possible edge can fail
a contract graph rule. It is not an observed import or a runtime trace.

**Rejected.** Do not copy a list of target names into a new field. Do not import the module
to read the tuple. Do not treat the bounds of a function's default argument as a proof about
all callers.

**Limit.** This slice accepts a non-empty immutable tuple and a direct call. It does not
fold expressions, prove arbitrary aliases, or prove that a caller never supplies a value
outside the tuple.
