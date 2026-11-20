# AD-1020 Lease the snapshot for the MCP session

**Decision.** Hold the Explorer snapshot lease from MCP startup until the
stdio server stops. Each tool continues to open its own read connection.
The HTTP server uses the same lease during its lifetime.

**Reason.** The cache can evict an idle MCP session's snapshot between tool
calls. Active sessions must keep access to the snapshot that they opened.

**Alternative.** A lease for each tool call only protects its current read.

**Limit.** A leased snapshot uses cache space until the server stops. Requests
can still report stale source evidence if files change after the scan.

**Checks.** The MCP test reads under the session lease and attempts an eviction
while the server is running. Eviction succeeds after normal or failed shutdown.
