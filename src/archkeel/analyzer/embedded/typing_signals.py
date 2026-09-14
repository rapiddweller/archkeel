# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dynamic-typing signal collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass

from .records import RawEvidence, RawRecord, classified, stable_id
from .source import ParsedModule, add_evidence, annotation_text, location


def _annotation_signals(
    module: ParsedModule,
    node: ast.AST,
    annotation: ast.AST | None,
    *,
    owner: str,
    evidence: dict[str, RawEvidence],
) -> list[RawRecord]:
    text = annotation_text(annotation)
    if annotation is None or not text:
        return []
    names = {
        child.id if isinstance(child, ast.Name) else child.attr
        for child in ast.walk(annotation)
        if isinstance(child, (ast.Name, ast.Attribute))
    }
    root_name = ""
    if isinstance(annotation, ast.Subscript):
        root_name = (annotation_text(annotation.value) or "").rsplit(".", 1)[-1]
    kinds: list[str] = []
    if "Any" in names:
        kinds.append("any_annotation")
    if root_name in {"dict", "Dict"} and "Any" in names:
        kinds.append("dict_any_annotation")
    if root_name == "Callable" and "Any" in names:
        kinds.append("callable_any_annotation")
    if isinstance(annotation, ast.Name) and annotation.id == "object":
        kinds.append("object_annotation")
    items: list[RawRecord] = []
    for kind in sorted(set(kinds)):
        evidence_id = add_evidence(evidence, module, node)
        line, _, _ = location(node)
        items.append(
            classified(
                item_id=stable_id("TYPE", module.rel_path, line, owner, kind, text),
                evidence_class=EvidenceClass.FACT,
                area="type_architecture",
                kind=kind,
                title=f"{owner}: {text}",
                subjects=[owner],
                evidence_ids=[evidence_id],
                data={"owner": owner, "annotation": text, "signal": kind},
            )
        )
    return items


def collect_typing_signals(
    modules: Sequence[ParsedModule],
    calls: Sequence[RawRecord],
    symbols: Sequence[RawRecord],
    imports: Sequence[RawRecord],
    evidence: dict[str, RawEvidence],
) -> list[RawRecord]:
    items: list[RawRecord] = []
    used_cross_package: set[str] = set()
    for item in imports:
        data = item["data"]
        if data["source_package"] == data["target_package"] or not data["symbol"]:
            continue
        used_cross_package.add(f"{data['target_module']}.{data['symbol']}")

    for module in modules:
        for node in ast.walk(module.tree):
            if isinstance(node, ast.AnnAssign):
                owner = annotation_text(node.target) or module.module
                items.extend(
                    _annotation_signals(
                        module, node, node.annotation, owner=owner, evidence=evidence
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = f"{module.module}.{node.name}"
                for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                    items.extend(
                        _annotation_signals(
                            module,
                            argument,
                            argument.annotation,
                            owner=f"{owner}:{argument.arg}",
                            evidence=evidence,
                        )
                    )
                items.extend(
                    _annotation_signals(
                        module, node, node.returns, owner=f"{owner}:return", evidence=evidence
                    )
                )
        comments = tokenize.generate_tokens(io.StringIO(module.source).readline)
        for token in comments:
            if token.type != tokenize.COMMENT or "type: ignore" not in token.string:
                continue
            line_number, column = token.start
            fake = ast.Pass(
                lineno=line_number,
                col_offset=column,
                end_lineno=token.end[0],
                end_col_offset=token.end[1],
            )
            evidence_id = add_evidence(evidence, module, fake)
            items.append(
                classified(
                    item_id=stable_id("TYPE", module.rel_path, line_number, "type-ignore"),
                    evidence_class=EvidenceClass.FACT,
                    area="type_architecture",
                    kind="type_ignore",
                    title=f"{module.rel_path}:{line_number} uses type: ignore",
                    subjects=[module.module],
                    evidence_ids=[evidence_id],
                    data={"owner": module.module, "signal": "type_ignore"},
                )
            )

    dynamic_targets = {
        "typing.cast": "cast_call",
        "typing_extensions.cast": "cast_call",
        "builtins.getattr": "getattr_call",
        "builtins.hasattr": "hasattr_call",
        "builtins.eval": "eval_call",
        "builtins.exec": "exec_call",
        "builtins.__import__": "dynamic_import",
        "importlib.import_module": "dynamic_import",
    }
    evidence_by_id = evidence
    for call in calls:
        expression = call["data"]["expression"]
        kind = next(
            (
                dynamic_targets[target]
                for target in call["data"]["targets"]
                if target in dynamic_targets
            ),
            None,
        )
        if not kind:
            continue
        items.append(
            classified(
                item_id=stable_id("TYPE", call["id"], kind),
                evidence_class=EvidenceClass.FACT,
                area="type_architecture",
                kind=kind,
                title=f"{call['data']['source_scope']} uses {expression}",
                subjects=[call["data"]["source_scope"]],
                evidence_ids=[value for value in call["evidence_ids"] if value in evidence_by_id],
                fact_ids=[call["id"]],
                data={
                    "owner": call["data"]["source_scope"],
                    "signal": kind,
                    "expression": expression,
                },
            )
        )

    symbol_by_name = {item["data"]["qualified_name"]: item for item in symbols}
    for used in sorted(used_cross_package):
        used_symbol = symbol_by_name.get(used)
        if not used_symbol or used_symbol["data"].get("symbol_category") not in {
            "function",
            "method",
        }:
            continue
        signature = used_symbol["data"]
        missing = [
            parameter["name"]
            for parameter in signature.get("parameters", [])
            if parameter["annotation"] is None
        ]
        if signature.get("returns") is None:
            missing.append("return")
        if not missing:
            continue
        items.append(
            classified(
                item_id=stable_id("TYPE", used, "missing-boundary-annotation", *missing),
                evidence_class=EvidenceClass.FACT,
                area="type_architecture",
                kind="missing_cross_package_annotation",
                title=f"{used} has unannotated cross-package boundary positions",
                subjects=[used],
                evidence_ids=used_symbol["evidence_ids"],
                fact_ids=[used_symbol["id"]],
                data={
                    "owner": used,
                    "signal": "missing_cross_package_annotation",
                    "positions": sorted(missing),
                },
            )
        )
    return sorted(items, key=lambda item: item["id"])
