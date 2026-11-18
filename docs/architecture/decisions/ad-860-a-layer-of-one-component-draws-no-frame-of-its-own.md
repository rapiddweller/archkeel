# AD-860 A layer of one component draws no frame of its own

Status. Accepted. Issue #1815.

The Modules view drew a frame for each component on the owner chain of a module. A layer that
holds one component got a frame, and the component inside it got a second frame. Both frames had
the same name and the stereotype `«component»`. In the shell part this showed `entry` in `entry`,
`commands` in `commands` and `frame` in `frame`.

The fact sheet already treats such a layer as that component (`atlasBoxKind`, #1441). The
diagram now follows the sheet. A layer with `layer_rank` set and one component has no frame. Its
component is drawn in the next frame above it. The test is the one function
`atlasBoxHoldsOneComponent`, which the sheet and the layout share.

A layer of several components stays a frame, because it is a real parent of its components.

## Rejected

- Drop a frame when its label equals the label of its parent. A label is not an identity. Two
  real boxes can share a name.
- Name the outer frame `«layer»`. The sheet calls the box a component, so the diagram and the
  sheet would disagree.
- Remove the layer from the Atlas data. The Components view, the search and the breadcrumb
  still need the layer box.

## Not decided here

A layer of several components is still drawn as `«component»`. That is a separate stereotype
question.

The browser test `a_layer_of_one_component_draws_no_frame_around_that_component` in
`tests/test_report_explorer_layout.py` checks the shell part: no frame for the three layers of one
component, a frame for `foundation` and `present` with their components inside, and no frame inside
a frame of the same name.
