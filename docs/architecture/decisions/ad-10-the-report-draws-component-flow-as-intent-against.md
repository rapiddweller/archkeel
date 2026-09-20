# AD-10 The report draws component flow as intent against observation

The HTML report of
`report` embeds an interactive flow view: component cards, observed edges drawn at one width and
labelled with the import sites crossing them, edges that break a rule drawn dashed with the rule
id, a threshold that hides weak edges, and an inspector for modules and interface names. It is
derived from the canonical observation alone, so the report stays one self-contained file; the
script is a packaged asset with no external library, and its data, ordering and output bytes are
deterministic. The existing communication table stays as
the fallback without script. Reason: on the internal service the graph showed the seven edges that
break its documented intent faster than any table, and a prototype on the shop sample did the same
for every rule kind. Width encoded the weight until two costs showed: an arrow head scales with the
line it ends, so a heavy edge grew a head that read as weight where it should read as direction,
and inside a component, where every edge is observed and the label spots are crowded, the number
that would have said so was the first thing dropped. Check: the HTML report tests,
`tests/test_determinism.py`, and the shop tour report drawing every violated edge; the one width
and the label on every edge are drawn by `flow.js` at runtime and measured on the self report, not
asserted by a test.

