# AD-848 An unread re-export leaves its package origin unknown

**Status.** Proposed.

**Reason.** A caller can name an item of an external package through a workspace re-export.
A second package outside the scan can re-export the item. The first package in the route
does not prove which package defines the item. A dispatch gap alone adds no import (AD-837).
This route is a written import, not a dispatch gap.

**Decision.** Keep the known local edge. When a proven publication route reaches an unread
external package, record an edge gap at the source of the import. Cite the written path.
The gap does not change the wire schema. A direct import still names the package in its path.

**Rejected.** Substitute the package at the end of the scanned route for the package that
defines the item. The scan does not read that package's exports.

**Limit.** This step uses the existing named publication route. It does not extend the walk
through an external glob, a macro expansion, or an incomplete route.

**Tests.** Cargo runs the same call through a foreign re-export and through a local definition.
The external scope rule is UNKNOWN for the unread route and PASS for the local definition.
A direct path to the restricted package gives FAIL.
