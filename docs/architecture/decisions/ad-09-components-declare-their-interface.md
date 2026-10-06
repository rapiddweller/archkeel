# AD-9 Components declare their interface

A component declares `public` as modules or symbols. `pkg.module` exposes its
non-underscore top-level names, or its `__all__`; `pkg.module:Name` exposes one name.
`interface_boundary` permits a cross-component import only through a declared
name, directly or through re-exports. Underscore names never qualify.
`TYPE_CHECKING` imports count unless `include_type_checking` is false.

With this rule, validation reports inbound imports to a component without
`public`, and unused `public` entries. `init` proposes a module entry when it
has `__all__` or consumers use at least half its public names; otherwise it
proposes symbols. A module entry therefore admits at most twice the names in use.

`declarations.public_api` names consumers outside the package. [AD-66](ad-66-declarationspublicapi-names-a-consumer-outside-the-package.md)
clarifies this older distinction after AD-64 introduced the external surface;
component `public` checks do not automatically cover it.

The report lists used interface names, parameter and return annotations per edge,
and `UNKNOWN` for missing annotations. Protocol conformance, labeled graphs and
new regression measures are out of scope. Declaring interfaces makes access to
another component's internals a visible contract change.

Check: `tests/test_analyzer.py`, drift tests in `tests/test_validation.py`, the
self-contract and the measured profile in `docs/evidence/`.
