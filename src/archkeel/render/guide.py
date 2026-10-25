# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Render the architecture contract as a Markdown guide; a pure function of the contract."""

from collections.abc import Sequence
from typing import Final, assert_never

from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    ArchitectureRuleKind,
    BoundaryTypesRule,
    BoundedNumericOperandRule,
    CallOwnerRule,
    CatalogArgumentRule,
    CatalogUseRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ContractComponent,
    DecisionMaker,
    ExternalDependencyScopeRule,
    ForbiddenCallArgumentRule,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    ForbiddenEffectUnderConditionRule,
    InterfaceBoundaryRule,
    LayerOrderRule,
    NoComponentCyclesRule,
    ProtocolDeclarationsRule,
    RootLayoutRule,
    SiblingIsolationRule,
    SourceOwnershipRule,
    SymbolPlacementRule,
)

# One explanation per kind, written from docs/rules.md; a kind without one is named, not dropped.
RULE_KIND_EXPLANATIONS: Final[dict[ArchitectureRuleKind, str]] = {
    ArchitectureRuleKind.CALL_OWNER: (
        "Only the callers the rule names may call the target. The check follows calls it can "
        "prove. An unproven call keeps the result UNKNOWN."
    ),
    ArchitectureRuleKind.FORBIDDEN_CALL_ARGUMENT: (
        "The named parameter of the named call may not receive a string literal written in "
        "the source. Only written string constants are checked."
    ),
    ArchitectureRuleKind.CATALOG_ARGUMENT: (
        "The named call argument must name an entry of the declared enum catalog. A wrong "
        "string literal fails. A dynamic argument stays UNKNOWN."
    ),
    ArchitectureRuleKind.CATALOG_USE: (
        "Each entry of the declared enum catalog must be read in the selected source. "
        "Comments, docstrings and definitions do not count as reads."
    ),
    ArchitectureRuleKind.FORBIDDEN_EFFECT_UNDER_CONDITION: (
        "The named effect may not happen while a declared Boolean condition is true. The "
        "check follows simple branches and early returns. It is Python-only."
    ),
    ArchitectureRuleKind.FORBIDDEN_DEPENDENCY: (
        "The source may not import the target. Use it to reject one component, module or "
        "symbol crossing."
    ),
    ArchitectureRuleKind.ALLOWED_DEPENDENCY: (
        "Records that a component pair may depend on each other. It is a permission, not a "
        "pass: it adds no violation and does not prove that the dependency exists."
    ),
    ArchitectureRuleKind.FORBIDDEN_CONSTRUCT: (
        "Forbids the named syntax forms in the selected source, such as getattr or cast. It "
        "matches syntax, not types. Each permitted case needs an exact allowance."
    ),
    ArchitectureRuleKind.SOURCE_OWNERSHIP: (
        "Retires a source name, or confines its definition, use or transfer to one owner. It "
        "is Python-only. Missing or ambiguous source evidence cannot certify it."
    ),
    ArchitectureRuleKind.EXTERNAL_DEPENDENCY_SCOPE: (
        "Limits one external package to the listed sources. Other sources may not import it."
    ),
    ArchitectureRuleKind.COMPLETE_ASSIGNMENT: (
        "Every module in the source must have one owning component. A module with no owner "
        "escapes every boundary rule."
    ),
    ArchitectureRuleKind.ROOT_LAYOUT: (
        "The root package may contain only the listed child packages and modules."
    ),
    ArchitectureRuleKind.COMPLETE_EXTERNAL_SCOPE: (
        "Every non-standard-library dependency must be named by a rule. An undeclared "
        "dependency fails."
    ),
    ArchitectureRuleKind.COMPLETE_REQUIRES: (
        "A cross-component import must be covered by a requires entry of the importing "
        "component. An import with no matching entry is a violation."
    ),
    ArchitectureRuleKind.LAYER_ORDER: (
        "Layers run from inner to outer. A component may not declare a requirement on a "
        "later, outer layer. A missing layer stays UNKNOWN."
    ),
    ArchitectureRuleKind.NO_COMPONENT_CYCLES: (
        "Components, or modules when the rule names the module level, may not import each "
        "other in a loop."
    ),
    ArchitectureRuleKind.INTERFACE_BOUNDARY: (
        "A component may import another only through names that the other component publishes "
        "in its public list. Module object grants are the named exception."
    ),
    ArchitectureRuleKind.SIBLING_ISOLATION: ("The listed peer modules may not import each other."),
    ArchitectureRuleKind.SYMBOL_PLACEMENT: (
        "Classes of the named kinds must be defined in the listed modules."
    ),
    ArchitectureRuleKind.BOUNDARY_TYPES: (
        "Declared facade signatures and model fields may use only types their owner publishes, "
        "builtins, enums and Pydantic models. Broad containers need an exact allowance."
    ),
    ArchitectureRuleKind.BOUNDED_NUMERIC_OPERAND: (
        "A modulo operation on the selected names must use a right-hand value at or above the "
        "minimum. A known smaller value fails. An unknown value stays UNKNOWN."
    ),
    ArchitectureRuleKind.PROTOCOL_DECLARATIONS: (
        "The named parameters or members must be declared with the canonical Protocol. This "
        "checks the declaration only, not that a class conforms to it."
    ),
}

_VISIBLE_ROWS: Final = 10
_COMPONENT_ROW_LIMIT: Final = 40
_RATIONALE_LIMIT: Final = 200


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _cell(text: str) -> str:
    # A pipe would start a new column, and a newline would end the table row.
    escaped: str = text.replace("|", "\\|")
    return escaped.replace("\n", " ")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows)
    return lines


def _rows(
    headers: Sequence[str], rows: Sequence[Sequence[str]], *, limit: int, noun: str
) -> list[str]:
    """Show every row up to the limit; beyond it, the first ten and the rest in details."""
    if len(rows) <= limit:
        return _table(headers, rows)
    return [
        *_table(headers, rows[:_VISIBLE_ROWS]),
        "",
        "<details>",
        f"<summary>Show the other {_plural(len(rows) - _VISIBLE_ROWS, noun)}</summary>",
        "",
        *_table(headers, rows[_VISIBLE_ROWS:]),
        "",
        "</details>",
    ]


def _rationale(text: str) -> str:
    """Keep the contract's own words, cut at a sentence end when one is close enough."""
    if len(text) <= _RATIONALE_LIMIT:
        return text
    head: str = text[:_RATIONALE_LIMIT]
    sentence_end = head.rfind(". ")
    if sentence_end >= _RATIONALE_LIMIT // 2:
        return head[: sentence_end + 1]
    return head + "..."


def _decider(maker: DecisionMaker | None) -> str:
    return "not recorded" if maker is None else str(maker)


def _decision_makers(contract: ArchitectureContract) -> list[DecisionMaker | None]:
    """One entry per decision: each requires edge, each declared public list, each rule."""
    makers: list[DecisionMaker | None] = []
    for component in contract.components:
        for entry in component.requires or ():
            makers.append(
                entry.decided_by if entry.decided_by is not None else component.decided_by
            )
        if component.public is not None:
            makers.append(component.decided_by)
    makers.extend(rule.decided_by for rule in contract.rules)
    return makers


def _owns(component: ContractComponent, selector: str) -> bool:
    owned = (*component.packages, *(component.exact_modules or ()))
    return any(_overlaps(selector, name) for name in owned)


def _overlaps(selector: str, name: str) -> bool:
    # A selector above or below an owned name overlaps it; the scope is a judgement about reach.
    return selector == name or selector.startswith(f"{name}.") or name.startswith(f"{selector}.")


def _selectors(rule: ArchitectureRule) -> tuple[str, ...]:
    match rule:
        case (
            CallOwnerRule()
            | ForbiddenCallArgumentRule()
            | CatalogArgumentRule()
            | ForbiddenEffectUnderConditionRule()
            | ForbiddenDependencyRule()
            | AllowedDependencyRule()
        ):
            return (rule.source, rule.target)
        case (
            BoundedNumericOperandRule()
            | CatalogUseRule()
            | ForbiddenConstructRule()
            | SourceOwnershipRule()
            | CompleteAssignmentRule()
            | CompleteExternalScopeRule()
            | SymbolPlacementRule()
            | BoundaryTypesRule()
            | ProtocolDeclarationsRule()
        ):
            return (rule.source,)
        case ExternalDependencyScopeRule():
            return (*rule.allowed_sources, *rule.exact_sources)
        case RootLayoutRule():
            return (rule.root,)
        case SiblingIsolationRule():
            return rule.members
        case CompleteRequiresRule() | InterfaceBoundaryRule() | NoComponentCyclesRule():
            return ()
        case LayerOrderRule():
            # Its named components are labels, not selectors; `_scope` reads them directly.
            return ()
        case _:
            assert_never(rule)


def _scope(rule: ArchitectureRule, components: tuple[ContractComponent, ...]) -> str:
    match rule:
        case LayerOrderRule(components=named) | NoComponentCyclesRule(components=named) if named:
            return ", ".join(named)
    selectors = _selectors(rule)
    if not selectors:
        return "whole project"
    matched = tuple(
        component.label
        for component in components
        if any(_owns(component, selector) for selector in selectors)
    )
    if len(matched) == len(components):
        return "whole project"
    # A selector that names no component is shown as written, so the gap stays visible.
    return ", ".join(matched) if matched else ", ".join(selectors)


def _requires_count(contract: ArchitectureContract) -> int:
    return sum(len(component.requires or ()) for component in contract.components)


def _rule_count(contract: ArchitectureContract, kind: ArchitectureRuleKind) -> int:
    return sum(rule.kind == kind for rule in contract.rules)


def _dependency_decisions(contract: ArchitectureContract) -> int:
    """Every recorded dependency decision: requires entries and explicit dependency rules."""
    return (
        _requires_count(contract)
        + _rule_count(contract, ArchitectureRuleKind.ALLOWED_DEPENDENCY)
        + _rule_count(contract, ArchitectureRuleKind.FORBIDDEN_DEPENDENCY)
    )


def _at_a_glance(contract: ArchitectureContract) -> list[str]:
    makers = _decision_makers(contract)
    requires = _requires_count(contract)
    complete = _rule_count(contract, ArchitectureRuleKind.COMPLETE_REQUIRES)
    lines = [
        f"- Components: {len(contract.components)}",
        f"- Rules: {len(contract.rules)}",
        f"- Requires entries: {requires}. allowed_dependency rules: "
        f"{_rule_count(contract, ArchitectureRuleKind.ALLOWED_DEPENDENCY)}. "
        f"forbidden_dependency rules: "
        f"{_rule_count(contract, ArchitectureRuleKind.FORBIDDEN_DEPENDENCY)}. "
        f"complete_requires rules: {complete}.",
    ]
    if _dependency_decisions(contract) == 0 and complete == 0:
        lines.append(
            "- No `requires` entries, no `allowed_dependency` or `forbidden_dependency` rule "
            "and no `complete_requires` rule: dependency permissions are not declared. A "
            "missing entry does not mean a dependency is allowed or forbidden."
        )
    else:
        declared = sum(component.requires is not None for component in contract.components)
        lines.append(
            f"- Dependency permissions are declared on {declared} of "
            f"{len(contract.components)} components."
        )
        lines.append(
            "- The permission set is closed: a cross-component import with no requires entry "
            "is a violation."
            if complete
            else "- The permission set is open: a missing requires entry is not a violation."
        )
    lines.append(
        f"- Decided by: {makers.count(DecisionMaker.AGENT)} agent, "
        f"{makers.count(DecisionMaker.ARCHITECT)} architect, "
        f"{makers.count(None)} not recorded (requires entries, public lists and rules)."
    )
    lines.append("- Decided by is recorded metadata, not verified approval.")
    return lines


def _owned_text(component: ContractComponent) -> str:
    parts = []
    if component.packages:
        parts.append("packages " + ", ".join(f"`{name}`" for name in component.packages))
    if component.exact_modules:
        parts.append("modules " + ", ".join(f"`{name}`" for name in component.exact_modules))
    return "; ".join(parts) or "Not declared"


def _components(contract: ArchitectureContract) -> list[str]:
    rows = [
        [
            f"`{component.label}`",
            _owned_text(component),
            component.responsibilities[0] if component.responsibilities else "Not declared",
            component.layer or "-",
        ]
        for component in contract.components
    ]
    return [
        "## Components",
        "",
        *_rows(
            ("Component", "Owns", "Responsibility", "Layer"),
            rows,
            limit=_COMPONENT_ROW_LIMIT,
            noun="component",
        ),
    ]


def _interfaces(contract: ArchitectureContract) -> list[str]:
    rows = []
    for component in contract.components:
        public = component.public or ()
        examples = ", ".join(f"`{entry}`" for entry in public[:3]) or "Not declared"
        decider = "-" if component.public is None else _decider(component.decided_by)
        rows.append([f"`{component.label}`", str(len(public)), examples, decider])
    return [
        "## Public interfaces",
        "",
        *_rows(
            ("Component", "Entries", "Examples", "Decided by"),
            rows,
            limit=_COMPONENT_ROW_LIMIT,
            noun="component",
        ),
    ]


def _kind_name(kind: ArchitectureRuleKind) -> str:
    name: str = kind.value
    spaced: str = name.replace("_", " ")
    return spaced.capitalize()


def _kind_section(contract: ArchitectureContract, kind: ArchitectureRuleKind) -> list[str]:
    rules = [rule for rule in contract.rules if rule.kind == kind]
    rows = [
        [
            f"`{rule.id}`",
            _scope(rule, contract.components),
            _decider(rule.decided_by),
            _rationale(rule.rationale),
        ]
        for rule in rules
    ]
    explanation = RULE_KIND_EXPLANATIONS[kind]
    return [
        f"### {_kind_name(kind)} ({kind.value}, {_plural(len(rules), 'rule')})",
        "",
        explanation,
        "",
        *_rows(
            ("Rule", "Scope", "Decided by", "Rationale"),
            rows,
            limit=_VISIBLE_ROWS,
            noun="rule",
        ),
        "",
    ]


def _rules(contract: ArchitectureContract) -> list[str]:
    lines = ["## Rules", ""]
    for kind in ArchitectureRuleKind:
        if any(rule.kind == kind for rule in contract.rules):
            lines.extend(_kind_section(contract, kind))
    return lines


def _open_questions(contract: ArchitectureContract) -> list[str]:
    components = contract.components
    total = len(components)
    with_scope = sum(bool(c.packages or c.exact_modules) for c in components)
    with_responsibility = sum(bool(c.responsibilities) for c in components)
    with_public = sum(bool(c.public) for c in components)
    closed = _rule_count(contract, ArchitectureRuleKind.COMPLETE_REQUIRES) > 0
    forbidden = sum(bool(c.forbidden_responsibilities) for c in components)
    rows = [
        [
            "Who owns each module?",
            f"Packages or exact modules are declared for {with_scope} of {total} components. "
            "Actual coverage needs a scan.",
        ],
        [
            "What does each component do?",
            f"{with_responsibility} of {total} have a responsibility.",
        ],
        [
            "Which components publish interfaces?",
            f"{with_public} of {total} declare a public list.",
        ],
        [
            "Are dependency permissions declared?",
            f"{_requires_count(contract)} requires entries, "
            f"{_rule_count(contract, ArchitectureRuleKind.ALLOWED_DEPENDENCY)} "
            "allowed_dependency rules, "
            f"{_rule_count(contract, ArchitectureRuleKind.FORBIDDEN_DEPENDENCY)} "
            "forbidden_dependency rules.",
        ],
        [
            "Is the permission set closed?",
            "Yes: a `complete_requires` rule exists."
            if closed
            else "No: no `complete_requires` rule exists.",
        ],
        [
            "Are responsibilities forbidden anywhere?",
            f"Yes: {forbidden} components declare forbidden responsibilities."
            if forbidden
            else "No component declares a forbidden responsibility.",
        ],
        [
            "Does the implementation comply?",
            "The contract alone does not answer this. Run `archkeel report`.",
        ],
    ]
    return ["## Decided and open", "", *_table(("Question", "Answer"), rows), ""]


def _review_items(contract: ArchitectureContract) -> list[str]:
    components = contract.components
    items: list[str] = []
    complete = _rule_count(contract, ArchitectureRuleKind.COMPLETE_REQUIRES) > 0
    if _dependency_decisions(contract) == 0 and not complete:
        items.append(
            "Dependency permissions are not declared. Decide them, or record why none are needed."
        )
    elif not complete:
        items.append(
            "The permission set is open. Add a `complete_requires` rule once the permitted pairs "
            "are decided."
        )
    agent = _decision_makers(contract).count(DecisionMaker.AGENT)
    if agent:
        items.append(
            f"Agent decisions awaiting the architect: {agent}. An architect confirms one by "
            "setting its `decided_by` to `architect`."
        )
    without_public = sum(not c.public for c in components)
    if without_public:
        items.append(f"Components with no public interface: {without_public}.")
    without_responsibility = sum(not c.responsibilities for c in components)
    if without_responsibility:
        items.append(f"Components with no responsibility text: {without_responsibility}.")
    lines = ["## Review items", ""]
    if not items:
        return [*lines, "No review items apply.", ""]
    return [*lines, *(f"{number}. {item}" for number, item in enumerate(items, start=1)), ""]


def _inside_line(contract: ArchitectureContract) -> list[str]:
    paths = [component.inside for component in contract.components if component.inside]
    if not paths:
        return []
    listed = ", ".join(f"`{path}`" for path in paths)
    return [
        f"This guide covers the root contract only. {len(paths)} inside contracts are mounted: "
        f"{listed}.",
        "",
    ]


def render_guide(payload: bytes, *, repository: str, contract_path: str) -> str:
    """Parse one contract's bytes and return its guide; invalid input raises ValueError.

    The facade takes bytes, not ArchitectureContract: the contract's rule classes are not
    published by ir, so a typed parameter here would fail the boundary-types rule.
    """
    return _render(
        parse_contract(decode_json(payload)), repository=repository, contract_path=contract_path
    )


def _render(contract: ArchitectureContract, *, repository: str, contract_path: str) -> str:
    """The same contract always gives the same text: no dates, no hashes, stable order."""
    header = [
        f"# {repository} architecture contract guide",
        "",
        f"Generated by `archkeel guide` from `{contract_path}` (schema version "
        f"{contract.schema_version}). Do not edit this file; regenerate it with "
        "`archkeel guide`.",
        "",
        "## At a glance",
        "",
        *_at_a_glance(contract),
        "",
    ]
    body = [
        *_components(contract),
        "",
        *_interfaces(contract),
        "",
        *_rules(contract),
        *_open_questions(contract),
        *_review_items(contract),
        *_inside_line(contract),
        "This guide reads the contract only. It does not scan source code, read observed imports "
        "or give verdicts. Run `archkeel report` for what the code does.",
    ]
    return "\n".join([*header, *body]) + "\n"
