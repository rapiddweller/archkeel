# AD-1011 Written Python call arguments are live evidence

**Decision.** Record the written actuals of a proved direct Python call with its
live call link. Bind explicit positional and keyword actuals to the observed
signature. Reject a written string literal at the selected formal.

**Reason.** A call target and signature do not prove what the caller writes.
The argument inventory comes from the same AST as the call link. Its format
records whether an explicit argument is a string constant. The evaluator does
not parse an evidence excerpt.

**Rejected.** Read a saved argument claim as live evidence. A saved reply does
not carry the call link.

**Limit.** A spread, variadic signature, incomplete binding or incomplete call
scope leaves the rule UNKNOWN. An omitted default is not an explicit actual.
Only a direct call to a proved undecorated function can supply a binding.

**Tests.** The shop controls cover a variable, empty and adjacent string
constants, an f-string, a spread, a duplicate binding and an omitted required
argument.
