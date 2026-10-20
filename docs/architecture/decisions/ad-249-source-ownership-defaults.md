# AD-249: Source ownership names one declaration, not a copied value

`source_ownership` is one bounded contract rule over the existing Python symbol and reference facts. A `retired` rule names symbols and only definition/read/write/delete roles; every resolved selected occurrence is a violation. A `confined` rule names an owner module, selected symbols and/or selected `function.parameter` identities, and explicit roles. Symbol definitions and value transfers must resolve to that owner. A selected parameter's default or explicit fallback must use the canonical `value_owner` declaration rather than duplicate its literal.

The only transferable values are a resolved direct callable name used as a dictionary value, or a direct zero-argument lambda whose body calls that callable. Calls remain governed by `call_owner`. A default is a scalar literal or direct reference. A fallback is the two-operand `parameter or value` form where `value` is a scalar literal or direct reference. Canonical value comparison reads a unique source declaration; it never imports or executes project code.

Definitions, reads, writes, deletes, value transfers, defaults, and fallback expressions are separate source roles. Comments and strings are not references. Shadowing, mutation, duplicate definitions, dynamic/unsupported expressions, descriptors, ambiguous aliases, and incomplete source leave the affected decision UNKNOWN. There is no arbitrary value-flow, semantic-equivalence, runtime-liveness, or general CFG claim.

Receipts bind the rule, selected facts, canonical owner/value declaration, source and contract digests, scope and wire version. Mounted rules see only their selected physical source domain; partial or empty domains cannot prove absence. Existing product normalization, RNG, and worker-invariance tests remain independent.

This uses lexical origins and source-bound syntax already collected by Archkeel. A second scanner, copied default inventory, or executing imported code would create drift or unsafe evidence. Native source-to-saved-report, mutation, mixed FAIL/UNKNOWN, mount, and replay tests are the proof boundary.
