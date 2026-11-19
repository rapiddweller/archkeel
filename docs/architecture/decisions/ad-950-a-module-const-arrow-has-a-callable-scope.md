# AD-950 A module const arrow has a callable scope

**Status.** Accepted. Part of #829. Builds on AD-291 and AD-311.

**Decision.** A direct module-level `const` arrow with a simple name and a
parenthesized parameter list has a function symbol and its own lexical scope.
The existing call records carry calls from that scope to the model.

A call to a module binding with more than one declaration is not resolved.
Keep known candidates as partial. A write to a target binding also prevents a
resolved call, including through a local import. A write to a shadow does not
change the module binding.

**Reason.** React code often binds a component to an arrow. Its calls need a
source symbol. A JSX prop that names a handler registers it; it does not prove
that the handler runs. The compiler can reject a file with duplicate bindings.
The collector must still avoid a false proof for that file.

**Rejected.** Do not assign an anonymous callback's calls to its registering
function. Do not infer that `useCallback` returns its callback from its name.

**Limit.** Nested declarations, unparenthesized parameters, function
expressions, JSX component execution and HTTP boundaries remain outside this
slice. This decision does not prove runtime execution.

**Check.** The TypeScript site tests cover direct calls, shadows, writes,
duplicate bindings and JSX registration. The UML test checks the model edge
and the missing handler call through the native core and collector.
