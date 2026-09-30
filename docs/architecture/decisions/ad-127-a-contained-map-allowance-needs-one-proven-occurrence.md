# AD-127 A contained-map allowance needs one proven occurrence

An empty-path `boundary_types` allowance may match one parameterized mapping inside a supported
collection or union when the allowance annotation exactly matches the full signature. The shared
annotation walk retains mapping occurrences before finding deduplication. Identical siblings
therefore remain ambiguous, and the fallback applies only when one pathless mapping is proven.

The emitted allowance fact names the selected map and container depth. Alias expansion on the
route to that map is not eligible: the complete signature string does not pin the alias's shape.
Aliases inside unrelated key or value members do not disqualify the map. A direct map allowance
keeps its existing behavior, as do DTO field allowances.

Multiple contained maps remain unsupported without a selector in the public contract. Known
member violations and UNKNOWN remain independently reported. The contract schema is unchanged;
adding an allowance still follows `--against` amendment checks. Analyzer semantics move to
0.61.0 (AD-3).
