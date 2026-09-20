# AD-24a A module opens the same way, and its interface is what crosses its edge

The third
level shows the functions and classes one module declares and the calls and references between
them, with methods listed inside the class that owns them rather than as cards of their own. What
counts as the module's external interface is the one genuinely new question here, and the answer is
already in the observation: the names other modules import from it, and the names it imports from
elsewhere. Neither is a decision, so no rule and no contract field appears; the level is read the
way the component level is read. Cards, edges and the selection model keep the shape `level()`
already returns, because layout, ranking, routing and the inspector all consume that shape and a
third level that invented its own would rewrite them. Check: opening `archkeel.ir.codec` shows 71
symbols and the 165 edges between them.

