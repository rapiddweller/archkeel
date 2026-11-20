# AD-866 An unproved value origin keeps a destructor pair open

**Status.** Proposed. Part of #880 and #1811.

**Reason.** A reader can acquire an erased value without naming the module of its destructor.
A sibling store can pass the value between two callers. Unread code can do the same without
a static in the scan. The caller, not the store, runs the destructor.

**Decision.** Settle the known module routes first. If a reader reaches written static storage
or a path into an external package or the platform library, the scan has no proof of the value
origin. Keep a possible pair from that reader to each scanned module that may define a destructor.
Give the pair as an internal dispatch gap with a citation, not as an observed import.

**Rejected.** Name specific library calls, infer the payload from the type of a counter, or take
the absence of a scanned producer as proof that the reader cannot receive the value.

**Limit.** This step does not prove that a call passes a value or that a possible destructor runs.
A separate proof can remove a candidate if all construction and ownership transfers are known.
No wire shape, contract or pin changes.

**Tests.** Rust runs the sibling store, an opaque store without a local static, and an unread
package that stores or discards the value. An unread implementation cannot decide either cycle
rule or the exact ban in either variant. A written impl of another trait stays a control.
