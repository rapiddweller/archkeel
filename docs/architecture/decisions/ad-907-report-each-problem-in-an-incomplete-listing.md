# AD-907 Report each problem in an incomplete listing

**Status.** Accepted for #1864. Keeps the Cargo configuration boundary of AD-902.

**Decision.** Continue a directory listing after an unreadable entry or an invalid name.
Record each problem that the listing finds. Return no partial list and do not mark its children
as walked. Keep the existing entry limit.

**Rejected.** Stop at the first problem. This hides later problems and makes the reported paths
depend on the order of the directory entries. Return the readable entries as a complete listing.
Cargo can read a configuration below a path that the collector cannot inspect.

**Tests.** The Linux Dart test and a snapshot test check two invalid names in one directory.
The snapshot tests also check two unreadable link targets and the entry limit.
