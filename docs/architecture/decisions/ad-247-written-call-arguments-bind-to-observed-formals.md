# AD-247: Written call arguments bind to observed formals

Argument policies judge explicit source actuals only after the collector has
recorded typed positional, keyword and spread facts with source evidence. Core
binds those facts to the selected declaration's observed pure-data signature
using Python's `inspect.Signature.bind`; it does not parse call snippets or
apply omitted defaults.

A policy names one canonical target and one formal parameter. It rejects a
written string constant only when a fully bound explicit actual reaches that
formal. Empty and adjacent string constants count. F-strings, concatenations
and named expressions do not claim a written string constant. Spreads,
duplicate or invalid bindings, absent signatures, unstable targets and
unproven receivers leave the scope UNKNOWN. A separate proven violation stays
FAIL beside those limits.

The call-scope receipt binds the contract and format to the full observed
source inventory, including signatures, argument kinds, literal values and
argument evidence. A saved receipt cannot certify changed arguments or a
different formal selector. Existing historical observation formats remain
readable, while argument facts require observation 2.5 and contract 3.10.
Calls without canonical call binding carry explicit null argument facts; a
canonical call whose complete actual inventory cannot be tied to a bounded
source excerpt keeps its binding but carries null arguments and remains UNKNOWN
for argument policies. A proven zero-argument call carries an empty list. This
keeps unsupported argument syntax UNKNOWN without losing proven call identity.

This is a written-literal policy, not a value-type checker, expression
evaluator, SQL parser or policy on omitted defaults. Language profiles without
these typed call facts do not claim support.
