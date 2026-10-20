# AD-246: Bound selected numeric operands with source proofs

Contract 3.8 adds `bounded_numeric_operand` for selected Python modulo operations.
The rule owns source, binary/augmented form, terminal-name suffix and minimum RHS
value. The observer records operations and bounded exact-integer proofs; it does
not infer runtime types, entropy, collision freedom or whether dead code executes.

The supported grammar is integer/Boolean literals, unary `+`/`-`, bounded power,
and unique preceding local/module aliases. Alias entries retain their declaration
source evidence and span. Ambiguous, late, reassigned, deleted or unsupported
bindings remain UNKNOWN. Depth, exponent and result-bit limits guard evaluation
before expensive powers; oversized direct literals are also UNKNOWN.

Known operation and alias proofs must fit their existing single-line source
excerpts (at most 16,384 characters). Exact AST spans, expressions, subjects and
values are checked again at the source-facts boundary. Single-line `if`, `elif`,
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
