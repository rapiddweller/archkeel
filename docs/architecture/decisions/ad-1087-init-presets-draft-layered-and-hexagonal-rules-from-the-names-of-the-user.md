# AD-1087 Init presets draft layered and hexagonal rules from the names of the user

**Status.** Accepted. Issue #1987. It extends [AD-626](ad-626-init-drafts-open-decisions-from-the-folder-layout-and-decides-nothing.md) and [AD-638](ad-638-validate-and-report-draft-a-missing-archkeel-toml-and-never-overwrite.md): `archkeel init` still reads the folder layout only.

**Reason.** A new user writes a layered contract by hand. The draft names the components but does not know the intent "layers".

**Decision.**
1. **Flags.** `archkeel init --preset layered|hexagonal` with `--layers` and, for hexagonal, `--adapters`. Both flags take comma-separated component names. `--layers` runs from the outermost to the innermost layer. The user names the components; the preset never guesses a name.
2. **Existing rule kinds only.** The preset adds no rule kind and no core code. It adds `layer` to each named component and these rules, each with a rationale of one sentence:
   - `forbidden_dependency` for each pair of an inner and an outer layer (`include_type_checking: true`). This rule checks imports.
   - `sibling_isolation` over the packages of the adapters (hexagonal only).
   - `layer_order` over the layers, innermost first. This rule checks declared `requires` only (`docs/rules.md`). It is in the draft so that a later `requires` cannot point from an inner layer to an outer layer. It does not check imports.
3. **Hexagonal.** `--layers` names the core layers. `--adapters` (two or more) names components that sit side by side in one outer layer, named `adapters`. The core must not import an adapter.
4. **Refusals.** A wrong shape refuses the draft at `init` with exit 2 and writes no file. Wrong shapes: `--layers` or `--adapters` without `--preset`, fewer than two layers (layered), no core or fewer than two adapters (hexagonal), a repeated or empty name, a name that is no component of the layout, a named component that owns more than one package or module, and a repository with several language areas.
5. **Default output.** Without `--preset` the draft, and the output of `init`, are the same bytes as before. A draft with a preset keeps `complete_assignment` and `no_component_cycles`, and their rationale stays a `TODO`.
6. **Where.** `src/archkeel/cli/init_preset.py` holds `Preset` and `Shape`. `init_draft.py` writes the rules. `core_arguments.py` reads the flags and checks the names before any file is written.

**Rejected.**
- *`requires` from the layer order plus `complete_requires`.* It also forbids imports between peers of one layer and imports into a component outside the layers, which the user did not state.
- *Guessing layer names from folder names such as `domain` or `infra`.* A wrong guess is a wrong rule. The issue excludes it.
- *Presets for CQRS and microservices.* Out of scope.

**Limit.** The draft does not decide `requires`: each outer-to-inner dependency stays an open decision, as in a draft without a preset. A layer must be one package or module. The preset applies to a draft of one language area; use `--root` for one part of a system. The first verdict stays `UNKNOWN` while a responsibility is a `TODO`. Not done yet: a stricter shape in which a layer imports only the next inner layer.

**Tests.** `tests/test_cli_init_preset.py`: one test for each acceptance item of #1987 (schema check, equal runs, a verdict and a FAIL on an inner import of an outer layer, the default bytes, the commands in `docs/onboarding.md`), the order of `--layers`, the hexagonal rules and the refusals.
