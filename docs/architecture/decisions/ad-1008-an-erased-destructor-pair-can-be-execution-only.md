# AD-1008 An erased destructor pair can be execution only

**Decision.** Apply the execution marker of AD-900 to an erased destructor pair
when no candidate for that pair can hide a named use.

**Reason.** AD-866 leaves the origin and execution of the value open. The
destructor candidate, by itself, does not leave a written name route open.
The reader of the interface needs only the named use and its publication route.

**Rejected.** Drop the pair. A destructor can run in the caller and can affect
the cycle and dependency rules.

**Limit.** A mixed pair retains its doubt. An earlier unclassified pair, a
separate named site or an unread source keeps its own meaning. The execution
mark still requires the live worker evidence of AD-900.

**Tests.** The Rust collector checks erased and mixed pairs in both orders.
The compiler-backed storage probe executes the destructor, proves the named
interface and keeps the dependency and cycle rules open. An added unlisted
name fails the interface. An unresolved method keeps it open.
