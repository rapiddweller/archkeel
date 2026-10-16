# Typed CLI input boundaries implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode closed command, report-mode, agent and language protocols once into typed CLI arguments, while preserving existing CLI wire behavior.
**Architecture:** The CLI owns argument vocabulary and a bounded Namespace subclass. The installer owns its agent and legacy-marker vocabulary. Language remains the shared source-fact enum, reexported by check.ports.
**Tech Stack:** Python 3.11+, argparse, StrEnum, pytest, native Archkeel source observation.
**Spec:** User clarification on issue #542: parser/protocol string comparisons are forbidden too.

## Global constraints

- Preserve valid legacy CLI text, JSON output, help, choice errors and installer paths.
- No raw literal/Final-string control comparisons, Enum.value comparisons, Any annotations, new dependencies or raised native budgets.
- Paths, module names, free text and Git identities remain data strings.
- Remote GitHub isolation and hosted Actions only; the execution container cannot fork.

## Review focus

- No-command and malformed-command paths must preserve overview/exit-2 behavior.
- Report mode restrictions must behave identically for saved and observed reports.
- Agent defaults must never silently turn an invalid agent into a supported installer path.
- Parser defaults as well as supplied choices must be actual enum members.
- The independent Target must reject source field/signature widening; the whole CLI guard must never infer PASS from a method-only scope.

### Task 1: Typed argument and installer boundary

**Files:** create src/archkeel/cli/arguments.py; modify cli/__init__.py and cli/skill.py; add tests/test_cli_typed_inputs.py; add docs/architecture/contracts/cli.json and docs/architecture/cli-input-types.md. Root contract mount, enum-placement and guard deltas are integrated by the parent.

**Interfaces:** consumes check.ports.Language (canonical facts enum with PYTHON/DART/TYPESCRIPT); produces Command, ReportMode, SkillAction, ConfigurationSource and CLIArguments at cli.arguments; InstallationAgent at cli.skill; build_parser().parse_cli_args(...) returns CLIArguments.

- [x] Write parser/default/invalid-choice and installer ingress controls; run on unchanged source and confirm typed-argument failures.
- [x] Implement the bounded typed Namespace, converters and enum-driven dispatch; preserve serialized CLI names and errors.
- [x] Author the lower-level Target independently, pinning the real namespace fields and parser return signature.
- [x] Observe actual source with native whole-CLI string-control guard; mutate literal equality, membership, match and Final controls and an annotation, with Target bytes unchanged.
- [ ] Run CLI/skill/config/native controls, mypy, Ruff, hygiene and unchanged-budget own validation on the real shared-Language dependency overlay.
- [ ] Deliver a clean intended ref with exact files and hosted check evidence for independent Astra review.

## Verified design ruling

Argparse's ordinary parse_args API is generic in a supplied Namespace. Its subclass must not narrow that contract. The owned parse_cli_args entry point supplies CLIArguments to the unchanged library method and returns that bounded type. The actual main path and independent Target use this entry point; no cast, ignored override or extra TypeVar is required.

RED run 38932141308 observed17 expected failures and4 existing choice-error passes. GREEN run38932952968 observed152 compatibility passes; run38934612789 observed154 compatibility passes and full Ruff success. Native run38933812577 passed10 real-source Target/guard/mutation controls; two fresh-own checks remained blocked by the shared-wire Target integration, not waived.
