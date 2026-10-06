# AD-31 Deciding inside a component is opt-in, and only for pairs that exist

The unreleased complete-inner-decisions model was replaced by
[AD-33](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md). It made architects decide
observed inner pairs without authorizing those pairs automatically; exhaustive pair declarations
became unnecessary once inner levels could use `requires`.

Use the replacement rather than introducing this retired contract field.
