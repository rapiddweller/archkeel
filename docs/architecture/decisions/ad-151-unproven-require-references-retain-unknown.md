# AD-151 Unproven require references retain UNKNOWN

The TypeScript import profile resolves direct literal CommonJS `require` calls.
Member references such as `module.require` can escape through aliases, `.call`
or `.apply`. A call-only guard loses these dependencies and falsely claims complete
coverage.

Mark unproven property and element references as coverage gaps at the reference
site. Erased TypeScript assertions, non-null and satisfies expressions retain the
known Node namespace. Its `.then` use and unproved value escapes stay UNKNOWN,
including calls, containers, returns and reassignment. Direct members and proven
aliases stay supported, including the known `Module` and `default` exports.
Namespace rest, nested export bindings and default initializer escapes stay UNKNOWN.
Type-only references create no value gap.
Keep supported direct literal calls resolved. Resolving
arbitrary loader aliases would require further binding and flow proof; this phase
does not claim it.

The adapter test covers indirect forms and a direct positive control.
`fixtures/typescript-hidden-loaders.json` and the CLI init acceptance test prove
that Core retains UNKNOWN and unavailable measurements instead of dependency absence.
