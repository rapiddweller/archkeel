# Construct query API correction

Expanded issue #542 requires explicit component responsibilities and nominal APIs. The complete suite exposed twelve review candidates against the existing limit of eleven. Exact native comparison before and after Wire shows that both newly extracted literal-comparison queries are actually called through the visitor's compound helper receiver, but their targets are absent from native references.

The first one-line experiment declared the receiver on ConstructCollector. Run 38955457530 passed 103 controls but still failed both the unchanged candidate limit and the direct-reference assertion. Do not increase the limit, add an exemption, or expand resolver authority.

Keep the stateful literal context in its existing class. Move the two pure AST queries into direct private module functions accepting that typed context. The visitor names those algorithms directly; there are no wrappers or duplicate implementations. Their existing form strings remain source-description metadata and are not dispatched as protocol state.

The permanent native assertion checks actual call targets. Run the existing reference, string-construct and hygiene tests plus Ruff, mypy and actual self-validation. Review real call/partial/UNKNOWN-site differences, not only aggregate totals. Preserve the separate local-literal observer change during later integration. Independent Astra review and the corrected complete suite are merge gates.
