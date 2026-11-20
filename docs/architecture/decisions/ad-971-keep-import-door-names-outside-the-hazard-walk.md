# AD-971 Keep import door names outside the hazard walk

**Decision.** Let the Python survey own the existing import door vocabulary.
The globals check and the hazard walker both read it. The hazard walker keeps
the AST check for attribute writes and deletes.

**Reason.** The hazard walker reads the globals check. The globals check only
needs the string constants, not a path back into the walker. Giving the
existing vocabulary its own place under the survey removes that return path.

**Limit.** The list of door strings and the import proof do not change. The
module cycle rule still reports UNKNOWN for other possible paths.

**Tests.** The survey tests keep inert reads separate from import doors. The
native control plants a return call between the two globals modules. The
module rule must report FAIL with both observed edges.
