# AD-944 The script index is built only from a tree

**Decision.** Initialize the three empty collections inside `DeclIndex::new`.
Do not provide a separate `Default` implementation.

**Reason.** The index has one constructor. Its caller supplies the tree and the
assignment targets. The unused trait entry lets the Rust collector report a possible
execution edge from TypeScript flow into the script index. The flow has no port for
that crossing. It reaches the constructor through the parser and the script reader.

**Rejected.** Add a port for the flow or exempt derived traits from the proof.
Neither is necessary to construct the index, and an actual crossing must still count.

**Limit.** The constructor returns the same index. The rules and their scope stay
the same. The self-check reports 48 fewer gaps. Of these, 31 held
`NATIVE-REQUIRES-COMPLETE`. Other crossings still hold the rule UNKNOWN.

**Tests.** The native self-check must not report the crossing from TypeScript flow
to the script index. The TypeScript script tests check the index through its callers.
