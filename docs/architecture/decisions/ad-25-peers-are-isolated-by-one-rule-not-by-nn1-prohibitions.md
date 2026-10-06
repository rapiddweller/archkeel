# AD-25 Peers are isolated by one rule, not by n·(n-1) prohibitions

`sibling_isolation` declares module or package peers. They may import shared modules
and receive outside imports, but cannot import each other. The self-contract names
every analyzer collector; a hygiene test rejects an unnamed collector.

[AD-1](ad-01-analyzer-modules-are-flat-and-singlepurpose.md) requires flat collectors behind
one orchestrator. Measurements showed the intended shape: `records` had twelve
inbound imports and none outbound, `source` eight inbound, `scanner` ten outbound,
and collectors no peer imports. Enforcing eight peers with existing prohibitions
would require 56 rules.

Contract 2.1.0 stays valid: a new kind invalidates no existing contract; older versions
fail closed ([AD-8](ad-08-statement-constructs-are-class-a-rules.md)). The analyzer version
rises because it can emit new records ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).
Check: a peer import yields one violation; a shared-module import yields none;
the self-contract carries the rule.
