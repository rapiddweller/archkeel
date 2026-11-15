---
name: explore
description: Not available on this development line. Use when the owner asks to open the codebase map or Studio, to say so and to offer the static report.
---

# Explore the codebase

The `explore` command and Studio are not available on this development line: the shell refuses
them with exit 2. No release has them. A new static overview of the core may return later.

Do not start Studio and do not run `explore`. A refusal is not a result.

For a picture of the architecture today:

1. Run `archkeel report --topology --output report.html` in the repository. It writes one static HTML
   page from the Rust core. Add `--config PATH` when the contract is not `archkeel.toml`.
2. Tell the owner the verdict of the run. UNKNOWN is not PASS.
3. For the full report of release 4.0.1, use that release.

For the checks of this line, use the `archkeel` skill.
