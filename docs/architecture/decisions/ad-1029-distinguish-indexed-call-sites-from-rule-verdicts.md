# AD-1029: Distinguish indexed call sites from rule verdicts

Studio counts distinct outgoing call sites beneath a selected element. A missing target
remains inspectable by expression and source location. Studio and MCP page through the
same snapshot rows. External and built-in calls can lack a local symbol.

A single completeness percentage would mix collector coverage, target linking and
rule decisions. A rule can prove a violation while another call remains open.
The gallery therefore shows unknown rules, report findings and collection gaps separately.

The map and gallery tests cover an unresolved descendant and an unknown rule with
one collection gap. Old snapshots can lack call records.
