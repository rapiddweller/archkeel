# AD-1031 Explorer cites Python call declarations

Explorer has separate paths for call facts and written declaration candidates.
Resolved call facts already identify a declaration, but their evidence list only
shows the call site. A validated fresh-receiver witness also identifies a method,
but Explorer reads only the underlying call fact.

Use the declaration from the same scan in the evidence for a resolved call.
Project validated fresh-receiver witnesses as resolved calls in Explorer.
The collector facts and contract evaluation keep their existing behavior.

For a call through an imported module, use the collector's scoped attribute
record to locate a written declaration. The relation remains a candidate.
It has a call site and a declaration location, with no checked story step.

Dynamic, inherited and injected receivers still require a separate proof.
