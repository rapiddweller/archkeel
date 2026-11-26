# AD-1129 A direct callback argument has its own callable scope

**Status.** Accepted. Part of #829. Builds on AD-950.

**Decision.** A direct arrow argument of a call has a callable scope when it
has parenthesized parameters and its enclosing scope is modeled. Its name
contains its source position. Its explicit calls belong to this scope.
The existing lexical checks include the enclosing scopes and the callback.
The callback has no source binding, so its binding is not marked unique.

**Reason.** A callback can contain a direct call. Registration does not prove
that the registering function invokes the callback. A separate scope records
the call without creating that false edge.

**Rejected.** Do not assign callback calls to the registering function. Do not
infer invocation from an API name. Do not treat a shadowed name as a module
binding.

**Limit.** This decision does not model single-parameter arrows without
parentheses, JSX handlers, object properties or callbacks in unmodeled scopes.
It does not resolve dynamic receiver dispatch or prove that a callback runs.

**Check.** The TypeScript site tests check separate callback owners, direct
calls, parameter shadows, local bindings and the absence of a registration
call to the callback.
