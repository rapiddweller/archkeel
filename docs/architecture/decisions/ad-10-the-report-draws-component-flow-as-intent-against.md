# AD-10 The report draws component flow as intent against observation

`report` embeds component cards, observed edges labeled with import-site counts,
dashed violated edges labeled with rule ids, a weak-edge threshold and a module
and interface inspector. All edges have one width. The communication table
remains the fallback without script.

The view uses only the canonical observation and packaged script, with no external
library. Data, ordering and output bytes are deterministic in one self-contained file.

The internal-service graph exposed seven violating edges faster than the table;
the shop prototype showed every rule kind. Width previously encoded weight, but
also enlarged arrowheads and crowded out labels inside components. One width and
an explicit count avoid those ambiguities.

Check: HTML report tests, `tests/test_determinism.py` and the shop tour's violated
edges. Runtime edge widths and labels in `flow.js` were measured on the self report;
a test does not assert them.
