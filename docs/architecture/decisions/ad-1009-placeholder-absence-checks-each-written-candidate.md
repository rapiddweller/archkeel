# AD-1009 Placeholder absence checks each written candidate

**Status.** Proposed. Extends AD-29 and AD-737.

**Decision.** The Python collector records each proven empty implementation body. It keeps
absence open if it cannot classify a candidate, or if a selected input is unread. A directly
bound standard-library `typing.Protocol` can exempt a uniquely bound, undecorated method.
The import must precede the class. The class must be a plain, top-level direct subclass.

The linked collector carries this exemption separately. It can support PASS only when the
contract declares `standard_library_unchanged`. The report records the premise. A saved
reply keeps conditional support partial.

**Reason.** A protocol declaration specifies an operation without implementing it. Its written
body does not make the same claim as a placeholder in an implementation.

**Limits.** Foreign imports, local shadows of the standard library, unread inputs, and possible
changes to the Protocol declaration leave the exemption open. General bases, unread decorators,
duplicate bindings and lone raises also remain open. The checker does not run Python code or
infer whether a real implementation is useful.

**Rejected.** Treat the name `Protocol` as an exemption. A local class, replacement import or
runtime mutation can bind the same spelling.

**Checks.** The CLI controls exercise plain functions, declarations with and without the premise,
shadowed names, a helper that mutates typing, duplicate methods and unread candidates. The native
support test checks that a saved reply cannot carry the linked conditional support.
The shop fixture proves the placeholder rule under its existing premise. Its other undecided
rules stay open.
