# AD-1018 Resolve package imports before projecting the map

**Decision.** The Python collector assigns module names from the import base.
Several packages can share one import directory. An import between those packages
can be local. A package can also have the same name as a source directory.
The scan must preserve this distinction and the location of the import.
Changing the collector changes the snapshot fingerprint (AD-1017).

The Studio map opens at the system boundary. It groups modules before it draws
a level. Opening a group reveals its children. A group inferred from source is
a package group. A declared component retains its contract identity.
An aggregate has one direction and one relation type. Its evidence comes
from the contributing relations in the same snapshot. Studio and MCP share
these reads.

**Reason.** A source directory used as a package prefix can turn a local import
into an external dependency. A page of files cuts across the package boundaries
that an architect needs to follow that dependency.

**Alternatives.** Matching name suffixes in the browser can join unrelated packages.
Adding a contract to each repository would make users declare facts that the
collector can read from source.

**Limit.** A static import describes a dependency. A runtime call or a network
destination needs separate evidence. Overlapping import roots and unsupported
package selection rules leave local targets open. Gaps remain visible in the snapshot.

**Checks.** Collector tests exercise sibling packages and ambiguous names.
Map tests follow group relations to source. Browser tests exercise drilldown.
The local corpus checks a source import across a cold and a warm launch.
