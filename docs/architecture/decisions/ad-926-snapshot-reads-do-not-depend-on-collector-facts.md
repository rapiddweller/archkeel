# AD-926 Snapshot reads do not depend on collector facts

**Decision.** Keep the path, digest, and selection of each read in `archkeel-snapshot`. Give
collectors these values in path order. Build the typed `Input` record at the collector boundary.
Use the SHA-256 dependency already in the workspace.

**Reason.** A snapshot read does not need the collector's wire format. The old dependency
also let a possible destructor edge from `facts` to `snapshot` close a component cycle.
Removing the dependency removes the return path. The collector still reports the open edge.

**Rejected.** Exempt an uncertain destructor from the cycle proof. The same uncertainty can
close a cycle in another graph. Move the facts types into snapshot. Their fields belong to
the wire format and not to file reads.

**Limit.** The change does not decide the remaining cycle candidates. It does not change
snapshot containment, read limits, cleanup, input order, or the collector wire format.

**Tests.** The native self-scan checks that neither the manifest nor code links snapshot to
facts. The snapshot tests check the digest and selection flag after repeated reads.
