# AD-151 Unproven require references retain UNKNOWN

The TypeScript import profile resolves direct literal CommonJS `require` calls.
Member references such as `module.require` can escape through aliases, `.call`
or `.apply`. A call-only guard loses these dependencies and falsely claims complete
coverage.

Mark unproven property and element references as coverage gaps at the reference
site. Keep supported direct literal calls resolved. Resolving arbitrary loader
aliases would require further binding and flow proof; this phase does not claim it.

The adapter test covers indirect forms and a direct positive control. The
`typescript-indirect-require` case in the 32-variant catalog proves that Core
retains UNKNOWN, exit 2 and unavailable measurements instead of dependency absence.
