# AD-27 A type escape hatch is decided, not merely observed

`any_annotation` joins `ForbiddenConstructKind`, reusing `type_ignore`'s typing-signal
path through `_construct_violations`. `Any` was already observed but could not be
forbidden by a contract. No separate mechanism is needed.

Legitimate foreign-data boundaries use `allowed_sources` with a reason rather than
dropping the rule. Contract 2.1.0 stays unchanged for this additive kind
([AD-8](ad-08-statement-constructs-are-class-a-rules.md)).
Check: the shop declares no `Any` and passes; the tour adds one and fails
`CONSTRUCT-NO-ANY`.
