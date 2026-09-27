# AD-116 Diagram filtering is an explicit choice

Automatic fit and hidden neighbor limits made large reports look incomplete (#171).

Start the report at 100% zoom, with all groups and threshold zero. Preserve the user's
zoom and threshold while navigating. Use a bounded native scroll area, not automatic fit.
Fit is an explicit overview; 100% restores readable labels.
Focus includes every direct neighbor and all violated edges. Counters disclose filtering.

Arrange resets positions without changing filters or zoom. Navigation resets obsolete
scroll offsets. Dragging within the same level retains its coordinate origin and native
scroll compensation. Physical-folder state belongs to its own breadcrumb, not its ancestors.

Reuse native controls and the existing SVG renderer. No new layout or gesture dependency.
Tests exercise focus completeness, nested navigation, actual layout/sizing and bounded scroll.
Browser acceptance also checks desktop, narrow touch screens, keyboard and no-JavaScript
fallback. Module inventory equality is a separate check, not proof of visual usability.
