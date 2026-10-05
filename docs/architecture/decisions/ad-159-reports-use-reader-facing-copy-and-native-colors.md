# AD-159: Reports use reader-facing copy and native colors

HTML follows the system light/dark scheme through CSS. Inline code wraps on small screens;
wide evidence tables retain their own scroll areas. Diagram and status colors stay readable.

Visible labels use plain words. Finding IDs, assessments, verdicts, provenance and handoff
contents keep their existing meaning. Report-mode guidance belongs beside the decision,
not in an empty Failures list. Module counts use the singular for one module.

The CLI displays a valid raw Python `[project].name`, falling back to the configured namespace.
This changes presentation only; no configuration or IR field is added. Other languages use
the namespace. Invalid-rule help lists `rule_assessments[].id`, including rules with no failures.

Checks: report HTML, real report/check CLI, filter remedy, mobile wrapping and themed UML.
