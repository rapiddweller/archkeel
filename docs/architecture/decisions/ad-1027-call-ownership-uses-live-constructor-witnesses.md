# AD-1027: Call ownership uses live constructor witnesses

**Status:** Accepted. First #613 slice for #619.

**Decision.** The linked Python survey connects an existing construction site, one direct
method declaration and the call site. For a local receiver, it also connects the sole assignment.
It proves the receiver from the AST, not from a type annotation or a method candidate.
It accepts only `return C().m()` and `value = C(); return value.m()` with no call arguments.
`C` is a unique source class with no bases, decorators, allocation or lookup hooks.
Existing namespace and write checks can withhold the witness.

**Admission.** Explorer navigation candidates have no authority. The store checks the types and identities of the source, allocation, member and
owner records. It checks the direct import, the receiver expression, the assignment when present,
and the order and file of the evidence. A candidate list alone does not meet these checks.
The linked producer supplies the witness in memory. Wire replies cannot supply that authority.
The store still refuses the historical, unchecked `call_binding` field.

**Decision scope.** A proved forbidden call gives FAIL before the scope proof runs.
PASS needs an observed target and a nonempty selected source. For each relevant module not
fully exempt, the written call count must equal the number of distinct, validated call sites.
The existing scope proof still holds gaps and missing inputs. An unexamined or ambiguous
call cannot certify PASS. A function-body selector uses its own written call count. This is a policy on written calls, not on all runtime dispatch.

**Limits.** No injected or stored instance fields, inheritance, custom allocation, native
providers or general flow analysis. No saved replay verdict. The released 4.0.1 call graph
provides context, not a verdict for this rule. It does not accept `call_owner`.

**Not chosen.** Do not promote the existing candidate to a binding. Do not admit historical
`CallBinding` values without their source and scope checks. Do not use a global scope flag
in place of a call inventory.

**Checks.** `tests/test_cli_python_call_owner.py` checks the selected scope, both allowance
forms, an unrelated method, reassignment, reflection, and a violation beside an unproved site.
`native/collect/src/python_tests.rs` checks live admission, forged links and loss of authority
on serialization.
