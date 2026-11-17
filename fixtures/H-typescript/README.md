# TypeScript shop

Seven source modules, four components. The composition root uses data and presentation; both use the domain. The two data adapters are independent alternatives.

The fixture is source input for the core and for `make typescript-compiler-check`. Analysis must not execute this package.

`resolver-inputs` contains fixed package declarations. The runner copies these into the demo snapshot as committed `node_modules` inputs. It never installs dependencies or reads host packages.

Named runtime imports can prove a direct exported declaration. Type-only and reexport
routes remain UNKNOWN where identity is unproved. The historical `unsupported-symbol-*`
and `unsupported-target-symbol` replay IDs retain those missing-proof examples; their
contracts are accepted, rather than rejected as unsupported profiles. Exact written
forbidden names can still FAIL without proving runtime identity. Facade and coupling
name measurements remain unsupported by this profile.
