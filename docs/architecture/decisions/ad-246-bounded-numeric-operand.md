# AD-246: Bound selected numeric operands with source proofs

Contract 3.8 adds `bounded_numeric_operand` for selected Python modulo operations.
The rule owns source, binary/augmented form, terminal-name suffix and minimum RHS
value. The observer records operations and bounded exact-integer proofs; it does
not infer runtime types, entropy, collision freedom or whether dead code executes.

The supported grammar is integer/Boolean literals, unary `+`/`-`, bounded power,
and unique preceding local/module aliases. Module aliases cross-link their exact
assignment evidence to the existing static/dynamic symbol inventory, which must
mark the module binding unique and precede the operation. This additive
`source_binding_unique` field is emitted only by the Python symbol collector for
direct module assignment symbols; other language profiles and legacy symbol rows
are unchanged. A known module alias without this fact remains UNKNOWN.
When a module alias is used inside a function or class, the operation also
retains the bounded chain of named lexical-owner excerpts. Replay checks the
selected operation in that chain and rejects a module origin if a parameter,
local binding, or other shadowing site can own the read. Anonymous lambda and
comprehension scopes are covered by their named owner excerpt; a top-level
anonymous scope without one remains UNKNOWN.

Local aliases retain their assignment expression/span and a separate bounded
excerpt of the complete lexical owner, linked by exact file/span to that owner's
existing function/class symbol identity. It does not replace the declaration's
ordinary evidence excerpt. The scope excerpt is at most 16,384 characters. Replay verifies the exact
owner span, selected modulo operation, one direct preceding assignment, and the
same-binding parameter/import/assignment/mutation sites. Nested or unsupported
binding cases remain UNKNOWN when that complete witness does not establish one
stable value. A scope larger than the existing evidence limit is not truncated
or treated as a proof.

Depth, exponent and result-bit limits guard evaluation before expensive powers;
oversized direct literals are also UNKNOWN.

Known operation proofs fit their existing single-line source excerpt (at most
16,384 characters). Alias assignments retain their exact single-line evidence
plus the complete bounded owner witness described above. Exact AST spans,
expressions, subjects and values are checked again at the source-facts boundary.
Single-line `if`, `elif`,
`while`, `for`, `with`, function, and class headers can be replayed with bounded
synthetic suites. Other incomplete or multiline excerpts remain UNKNOWN.

Operation receipts bind the selected source modules, rule selector and threshold,
and observed operation/value derivations. Saved reports reject altered rule or
fact content and unsupported historical proofs. Historical contract versions
remain readable but cannot declare this rule.

The implementation deliberately leaves arbitrary arithmetic, overload behavior,
type-only/dead-code interpretation, masks, shifts, quoted examples and general
control-flow proof outside the claim. Tests cover collector, typed rule, codecs,
receipts and replay; these limits are not an execution or security guarantee.
