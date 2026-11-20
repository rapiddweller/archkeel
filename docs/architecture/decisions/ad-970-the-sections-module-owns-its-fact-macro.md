# AD-970 The sections module owns its fact macro

**Decision.** Keep `section_facts!` private to `sections`. Resolve the types in
its expansion through the names in that module. Leave the data and vocabulary
macros in the shared module.

**Reason.** Only `sections` calls `section_facts!`. Its old home also held the
macros that data and vocabulary modules call. The scanner found paths from
those calls back to section and record code. The data macros do not need those
paths.

**Limit.** The section types, schema, wire format and rule scope do not change.
The new macro file gets two possible destructor paths. The rule does not
hold on either of them. The rule remains UNKNOWN for other possible paths.

**Tests.** The facts tests check the schema and wire records. The native
self-test checks macro ownership and plants an observed return edge from data
to sections. The rule must fail with both edges.
