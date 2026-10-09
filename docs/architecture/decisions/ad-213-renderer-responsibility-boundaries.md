# AD-213: Renderer responsibility boundaries

Separate the Atlas payload from HTML composition. HTML may consume the payload
and shared summary; neither may depend on HTML. Keep the outer public API and
existing rules. The user requested explicit renderer responsibilities.

Browser scene projection owns report data. Layout owns automatic placement and
manual routing. The Explorer owns measurement, DOM, input and navigation state.
These assets stay inline and offline; Python rules cover Python dependencies.

The HTML cleanup reduces measured unresolved calls from 714 to 704. Ratchet the
baseline down without granting new debt.

[Bound amendment](ad-213-renderer-responsibility-boundaries-amendment.json).
