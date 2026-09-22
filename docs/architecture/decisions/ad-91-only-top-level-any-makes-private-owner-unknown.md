# AD-91 Top-level owner resolution decides private ownership UNKNOWN

## Decision

Private attribute access is UNKNOWN when the parameter's outer annotation is untyped, unresolved,
or resolves to `Any` through a deterministic import alias. `Any` nested inside a container or
another typing form does not erase the deterministic owner named by that outer annotation.

The analyzer resolves that outer owner at the shared private-parameter boundary. It keeps the
existing fail-closed treatment of shadowed aliases, recognizes local and imported bindings, and
does not infer ownership from nested type arguments.

## Evidence

`tests/test_private_crossings.py` and the `class-a-private-attribute-any-owner` demo cover bare,
qualified and aliased `Any`, an unresolved `Unknown[Any]`, local classes, and nested containers.

The analyzer version rises to `0.41.0`: the same source can now produce fewer UNKNOWN records.
