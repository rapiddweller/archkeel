# TypeScript shop

Seven source modules, four components. The composition root uses data and presentation; both use the domain. The two data adapters are independent alternatives.

The fixture is source input for `make demo-typescript`. Analysis must not execute this package.

`resolver-inputs` contains fixed package declarations. The runner copies these into the demo snapshot as committed `node_modules` inputs. It never installs dependencies or reads host packages.
