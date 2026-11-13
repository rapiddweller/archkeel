# ArchKeel docs

On `main`, the Rust core decides `archkeel validate` and `archkeel report` for Rust and TypeScript
projects. Each other command gives a typed refusal with exit 2. Read the
[state of `main`](reference.md#state-of-main) first. Pages with a "Not on `main`" note describe
the Python engine before that change.

| Task | Start here |
|---|---|
| Set up a repository | [Onboarding](onboarding.md) |
| Fix architecture violations | [Target-first workflow](target-first.md) |
| Use the CLI or read a report | [Reference](reference.md) |
| Explore report evidence | [Report guide](report-visual-system.md) |
| Upgrade to the current release | [Release notes](../RELEASE_NOTES.md) |
| Define a constraint | [Rules](rules.md) |
| Understand missing evidence | [Known limits](known-limits.md) |

Reports check declared constraints. Read FAIL and UNKNOWN before accepting a change.

Contributors: [architecture of the Rust workspace](architecture/native.md),
[architecture of the deleted Python engine](architecture/archkeel.md), [report design](report-visual-system.md),
[demos of release 4.0.1](https://github.com/rapiddweller/archkeel/blob/4.0.1/docs/architecture-demo.md). Decision records explain individual choices;
they are an internal archive, not required onboarding.
