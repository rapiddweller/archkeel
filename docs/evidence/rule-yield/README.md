# Historical version 1 rule measurements (#218)

The committed [measurements](measurements.json),
[classification](classification.json) and [controls](controls.json) compare
released 0.8.4 with the earlier #205 candidate on pinned CE/EE snapshots.
They are historical evidence, not a current release measurement.

Version 1 captured violations and UNKNOWNs, not decided position passes. The
candidate removed some CE UNKNOWN records without changing policy or violations.
EE declared no boundary-types policy, so EE boundary yield is N/A. Existing
violations were not reclassified. Local sequential timings cannot establish a
speed change.

Repeat each pin with its own installation using the
[current measurement command](../../rule-yield.md). Retain source snapshots,
runtime and provenance. Compare raw companion observations and review added
findings at their cited sources. Missing producer proof or replay runtime remains
unavailable; do not invent policy to obtain a measurement.
