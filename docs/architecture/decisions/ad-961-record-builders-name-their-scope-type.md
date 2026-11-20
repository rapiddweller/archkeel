# AD-961 Record builders name their scope type

**Decision.** Name `Scopes` in the three reads of a scope field inside a
closure in `kept`, `symbol_table`, and `site_records`. Use the existing
`qualified` and `describe` methods with the same field and scope index.

**Reason.** The fields already carry `Scopes`. The Rust collector cannot prove
the type from these receivers. The written type gives it a route that the
existing interface already lists. The TypeScript records do not change.

**Rejected.** Treat an observed module edge as proof of a separate name.
Other calls through that module can still use an unlisted name.

**Limit.** This covers the three record builders, not all scope reads or
all field receivers. Three interface pairs close. Other pairs still hold
`NATIVE-INTERFACE-BOUNDARY` UNKNOWN.

**Tests.** The native self-check reads the changed calls. The Rust interface
test compares a listed receiver type, an unlisted type, and an open receiver.
The TypeScript record tests check that the same facts are written.
