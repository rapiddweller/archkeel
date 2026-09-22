# AD-82 A component namespace restricts placement, not ownership

`packages` remains the sole logical owner. An optional component `namespace` names one owned
package as the intended physical home. Every observed module owned by that component outside the
namespace is a `module.placement` violation and can enter the existing baseline.

The namespace is typed and validated as an owned dotted package. Old contracts omit it and keep
their previous behavior. `--against` treats adding the restriction as narrowing; removing or
changing it as widening.

Rejected: moving ownership into `namespace`, inferring ownership from strings, or adding a second
placement abstraction. The analyzer already has typed module records and `component_for`.

The analyzer version rises to `0.35.0` because observations gain `module.placement`.

Check: `tests/test_contract_model.py`, `tests/test_analyzer.py`, `tests/test_widening.py`.
