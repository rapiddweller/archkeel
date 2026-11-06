# Typed CLI input boundaries

The CLI decodes its closed protocols before workflow dispatch. `cli.arguments` owns commands, report modes and installation actions. Its `CLIArguments` Namespace declares the actual command, mode, action, agent and language fields; the owned parse_cli_args entry point returns that type while argparse's ordinary parse_args API remains intact. Supplied values and defaults are enum members.

`cli.skill` owns the supported installation agents and legacy managed-section markers. Its public installer accepts existing known text at ingress and converts it immediately to `InstallationAgent`. Invalid agents fail before any file is written. The shared `Language` enum remains owned by source facts and reaches the CLI through the existing Core port.

Argparse help, supported command text, invalid-choice messages, JSON command names, paths and installed instructions retain their existing wire representation. Enum values are read only when forming that representation, never to make a control decision. Arbitrary paths, module names and free text remain data.

`contracts/cli.json` independently declares the bounded input Target. It pins the Namespace's closed fields, the parser return and the concrete decoder returns. Native tests observe the real source and change annotations or introduce literal equality, membership, match and Final-string controls while keeping intent unchanged. The whole `archkeel.cli` guard covers configuration and installation protocols as well as the composition root; it has no method-only scope or exemptions.

The experimental `stream` command has its own `StreamArguments` Namespace and `parse_stream_args` normalization boundary. Stream-only optional paths and source scope stay out of the shared `CLIArguments` type.

This Target is intentionally bounded. It does not claim a complete command-specific DTO for every path, boolean and free-text argparse option, or browser JavaScript protocol coverage.

The integrated CLI source on the actual local-literal/version predecessor passed 190 tests, Ruff and strict mypy in run 38955326327. Normal baseline generation changes only calls_unresolved from 918 to 917; typing52, UNKNOWN58, all coupling budgets and all other policy entries remain identical. A fresh normal v2 amendment binds the actual predecessor policy and this tighter baseline. This evidence is specific to the integrated source, not a copied receipt from its standalone branch.
