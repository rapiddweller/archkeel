# AD-189 Routing clearance uses numeric intervals

Member previews in the own As-Is graph took 11.6 seconds for 61 nodes and 297
connections. Profiling identified repeated string-key construction in the
segment-clearance cache as the largest cost. Removing one lookup did not help.

Cache clearance by axis, coordinate and ordered interval endpoints. Reversed
segments reuse the same answer. The cache lasts one render; positions and
obstacles cannot change underneath it. Routing order, candidate search, arrows
and visible and clickable geometry stay the same. No new dependency or setting.

The measured preview took 6.0 seconds with numeric keys. This is a local
measurement, not a bound for every graph. Browser acceptance still checks
readability, overlaps, unchanged identities and keyboard preview controls.
