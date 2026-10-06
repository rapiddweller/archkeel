# AD-147 Revision snapshots preserve language inputs

Read revision source and resolver metadata as exact Git blobs; archive attributes
cannot remove or rewrite evidence. Reject unsafe paths, duplicates and links.
TypeScript identities preserve path distinctions; Dart collisions retain UNKNOWN.

Comparison requires known analyzer, contract, producer and runtime identities.
Equal missing values supply no proof. Legacy null Python-version aliases remain
readable without proving runtime identity. Shared module naming publishes no private
helpers or additional language capability.

[Snapshot proof](../../../tests/test_snapshot.py) and
[runtime proof](../../../tests/test_runtime_delta.py).
