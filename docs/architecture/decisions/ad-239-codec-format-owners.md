# AD-239: Codec format owners

The IR codec combined observation compression, contract grammar, recursive
inside linking, governance persistence, comparisons and command serialization.
These formats have separate callers and validation responsibilities.

Keep `ir.codec` as an eager compatibility facade. Flat sibling modules own
wire values, governance persistence, contract grammar, inside topology,
observations, deltas and result serialization. Each module names its format;
the existing governance component owns all of them.

Wire operations depend only on immutable values. Governance adds measurements,
locks, baselines and amendments. Contract grammar uses governance budget names;
inside linking uses contract grammar. Delta metadata uses observation parsers.
Results compose observation, delta, rule and existing command-view payloads,
importing their command-view owner directly.
No implementation imports the facade, and existing API/CLI imports retain it.
The existing whole-module codec publication stays unchanged. A literal
`__all__` names the same 38 public facade bindings: ordinary Python modules
otherwise leave imported alias routes unproven, adding eight UNKNOWNs. This
native declaration proves those routes and enumerates coupling without changing
analyzer semantics or widening a budget. Exact publication entries would add
unused-entry diagnostics for compatibility functions without production callers.
Implementation siblings are not published as whole modules.

Retain the same functions, errors, value identities, version gates, validation
order and wire bytes. Reexport the existing fact/value aliases. Physical function/class
module identities and the checker source digest change with their owner.

Move the existing named long-function reasons without increasing their count.
Replace the recursive codec Any permission with exact existing annotation
owners in wire conversion and canonical observation compression. Baselines,
budgets and external through selectors do not widen.
The bound v2 amendment records the fail-closed policy classifier's physical
ownership changes. The old recursive permission maps only to `_raw_object`,
`_raw_value`, encoder `rows_by_section` and `intern`, and decoder `expand`.
Independent signal/AST comparison retains seven annotations in these scopes;
the unchanged baseline binds the same ceilings on both sides.

Rejected: a codec package, registry, injected callbacks or lazy imports. Those
would obscure the real dependency direction. Keeping only the initial storage
extraction would leave unrelated contract, observation and result work mixed.

Limit: this is compatible responsibility extraction inside existing IR
boundaries. It does not redesign the grammar, split cohesive validation passes
or change dataclass/schema ownership. Existing topology reader callbacks keep
their current byte and canonical-identity contract.

`tests/test_codec_compatibility.py` checks facade object identity, the 38-name
star import and eager imports in both orders. Existing codec, contract, topology, baseline,
amendment, delta, result, schema and repository checks retain behavior proof.
Dispatch-reference assertions follow the physical contract parser names.
