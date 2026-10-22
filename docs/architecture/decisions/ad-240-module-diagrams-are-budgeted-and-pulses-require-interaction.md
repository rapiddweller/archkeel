# AD-240: Module diagrams are budgeted and pulses require interaction

An Atlas module diagram is drawn only at or below 80 modules and 300 relationships.
The budget applies to this diagram, not to recorded architecture facts or other views.
Above either limit, the report states the exact counts and keeps facts available through
the module list, search, Inspector, and selected-module navigation. Empty drawing data
must retain the counts and explicit skipped state; it must not look like missing evidence.

Edge pulses run only while a relationship is emphasized by focus or hover. At rest,
and after emphasis is cleared, no `flow-pulse` animation runs. This proves the animation
state, not the absence of every compositor or repaint activity.

We choose bounded drawing because the full module graph is unreadable at this scale and
layout can stall the browser. Raising the limits or dropping facts would hide the cost
or evidence. Requiring a separate view implementation would add machinery without
improving navigation; the existing list and module-detail route remain the fallback.

The limits are strict: 80 modules and 300 relationships remain drawable; exceeding
either skips the diagram. The candidate preserves the limits and all facts. The
original five-run local readiness check uses the median; its saved samples were 789,
808.3, 588, 1,584, and 963.5 ms at 1,174 modules / 5,292 relationships, for an
808.3 ms median. The 1,584 ms outlier remains recorded. This local observation does
not establish a universal latency bound or identify a cause.

Checked by `tests/test_atlas_report.py` boundary, facts, navigation, and pulse cases,
plus the focused browser tests in `tests/test_report_renderer_units.py`. Focused local
browser receipts used during these checks are not included and do not establish release
verification.
