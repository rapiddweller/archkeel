# AD-119: Index re-exports once per boundary pass

Status: accepted. Issue: #192.

## Problem

The same import set was scanned twice for each facade function, at each recursive
contract level. CE's 22-contract target exceeded the analyzer's 60-second deadline.

## Decision

Build origin, alias-chain and ambiguous-binding indexes once per boundary pass.
Reuse them within its symbol loop. Resolve ownership against the current contract;
never cache facade permissions across contract levels or scans.

The deadline, rule semantics, UNKNOWN handling and report format stay unchanged.
A work-count test holds index construction independent of public-function count.
Existing alias, rebinding and nested-contract cases remain the semantic oracle.

No global cache, timeout option or additional dependency is needed.
