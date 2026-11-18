# AD-852: Cycle rules read pairs with a possible return path

Status: accepted. Extends AD-418 and AD-806. Part of #880.

## Context
An unresolved dispatch adds a possible edge when the caller can reach the impl's file.
The Rust collector treated every dotted descendant as part of a file. It also followed
paths from macro templates that no call expands.

## Decision
Follow a reachable child as a route to its parent file only if the index puts it in that
file. An unindexed path and an opaque expansion keep their existing fallback. Use the
same import and re-export pairs for value flow as for the member resolver. A macro call
records its own paths when the collector can expand it.

A cycle rule uses return paths at its own level. Build them from the known edges and all
pair gaps. A possible edge with no return path cannot close a cycle or change its cited
imports. A gap with an unseen endpoint still holds the rule. An edge between two modules
of one component cannot change that component's cycle result.

Do not use only known edges: two gaps can close a cycle together. Do not remove a gap
from the report or change which gaps hold the run.

## Verification
The trait dispatch probes compile inline, separate-file, glob and include cases. They also
compile used and unused macro templates. Cycle receipt tests check an acyclic gap and a
cycle that needs two gaps.

The native self-check changes from 80 PASS and 12 UNKNOWN to 82 PASS and 10 UNKNOWN.
Both cycle rules pass. The collector reports 18,725 pair gaps, down from 22,599.
