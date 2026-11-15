---
name: explain-flow
description: Not available on this development line. Use when the owner asks for a flow to be explained as a checked story, to say so and to offer the static report.
---

# Explain a flow

The story trace and the checked view are not available on this development line: the shell
refuses `story` and `view` with exit 2. No release has them.

Do not run `story` or `view`. A refusal is not a result. Do not write a flow from
memory and call it checked: agent text is a claim, never a fact.

What this line offers:

1. Run `archkeel report --topology --output report.html` in the repository. It writes one static HTML
   page from the Rust core with the components and the dependencies between them.
2. Tell the owner what the page shows and which rules are UNKNOWN. UNKNOWN is not PASS.

For the checks of this line, use the `archkeel` skill.
