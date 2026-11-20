# AD-1019 List only working CLI commands

**Decision.** Show `validate`, `report`, `studio`, `init` and `skill` in the
`archkeel` help. Keep `explore` as an alias for existing scripts. The optional
MCP server uses the separate `archkeel-mcp` command.

This supersedes AD-432 item 4 for `guide`, `story` and `view`. No release served
these commands. The shell treats them as unknown arguments and exits 2.
Keep the typed refusal for `check` because release 4.0.1 serves it.

**Reason.** The command list describes workflows that users can run.

**Alternative.** Retaining the three unused registrations would preserve a
refusal code for workflows that never ran.

**Limit.** Studio and MCP retain their story operations.

**Checks.** CLI tests check the command list and refusals. The installed wheel
smoke test checks both console scripts and the Studio alias.
