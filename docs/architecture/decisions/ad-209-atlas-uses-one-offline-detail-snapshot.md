# AD-209: Atlas uses one offline detail snapshot

Atlas publishes one self-contained detail page beside the report. A component or module URL selects a recorded scope in that snapshot; browser history returns to the matching map state. Inline assets and the existing CSP keep `file://` use independent of network access. Re-reporting removes obsolete same-stem detail pages after the replacement artifacts are ready.

The Atlas payload carries Core-derived rule findings and dependency balances. UI counts reference those records rather than reconstructing policy from diagram edges.

This supersedes AD-204's per-component sidecars; the shared detail snapshot is the only HTML detail payload.

HTML omits unused source-record ID lists and duplicated audit metadata. Canonical JSON retains those records and references; displayed entities, relationships, findings and evidence remain unchanged.
