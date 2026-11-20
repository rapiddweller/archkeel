# AD-1012 Live Python members can prove a Protocol declaration

**Decision.** Read the members of closed class bodies from the live AST. Judge
the selected member against the exact declaration named by its type. The
canonical Protocol must use the standard constructor under the existing
`standard_library_unchanged` premise.

**Reason.** Text can name a shadowed type. The class symbol inventory also
omits some bare annotations. PASS needs a complete inventory and a resolved
type. An unread class leaves the scope open while other classes can still
prove a violation.

**Rejected.** Read archived evidence or match annotation spelling.

**Limit.** The first native slice reads direct member selectors. It leaves
parameter selectors, optional selectors, unsupported aliases, decorated
classes and unread member inventories UNKNOWN.

**Tests.** The shop stays PASS with its canonical member, fails with a
concrete type or omitted annotation, and stays UNKNOWN with a hidden,
unresolved or writable binding. A saved reply cannot supply the live
inventory.
