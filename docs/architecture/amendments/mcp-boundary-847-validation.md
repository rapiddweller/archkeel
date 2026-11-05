# #847 historical contract widening

CI job 127221703786 reported two `ir.widening` findings for the API and server
`forbidden_responsibilities` fields. The generic comparator treats these unmodeled field
changes as widening; the new prose adds boundaries.

The amendment binds the exact pre-#847 and post-#847 contract and baseline pair. Verify it with:

```sh
archkeel validate --root . --baseline architecture-baseline.json \
  --against 78097cf8c0bfa36d3762a71947a95ee636467c69 \
  --amendment docs/architecture/amendments/mcp-boundary-847.record
```

Keep this historical base explicit. The amendment does not bind the current or a future PR base.
