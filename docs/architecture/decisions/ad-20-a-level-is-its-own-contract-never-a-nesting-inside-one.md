# AD-20 A level is its own contract, never a nesting inside one contract

Each architecture level has its own contract and scope. Nesting should expose a responsibility
boundary, not merge several levels into one permission table. Mounted levels require their own
evidence before conformance can be claimed.

[AD-111](ad-111-recursive-inside-contract-tree.md) defines recursive mounting;
[AD-112](ad-112-local-publication-at-each-boundary.md) defines publication at each local boundary.
Those amendments replace the original one-depth limit.
