# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the TypeScript acceptance corpus with its frozen reference and in-package frontend.

The frozen reference and frontend read the same snapshot and request. Every difference is
classified:

- `equivalent`: the same facts, or a difference that cannot change a verdict;
- `more_conservative`: the oracle resolved or completed what the frontend leaves UNKNOWN;
- `suspicious`: the oracle left UNKNOWN what the frontend resolves or completes;
- `defect`: a different resolved target or flag, a dropped edge without a gap, a false verdict.

The checked-in allow-list names every `more_conservative` and `suspicious` case with its reason.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from archkeel.analyzer.process import ProcessCollector
from archkeel.cli.config import load_config
from archkeel.ir.facts import (
    BuiltinTarget,
    ExternalPackageTarget,
    LocalTarget,
    SourceFacts,
)
from archkeel.ir.protocol import (
    CollectionRequest,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)
from fixtures import typescript_scenarios
from fixtures.demo_catalog_support import Variant
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import Outcome, repository, run_variant

Klass = Literal["equivalent", "more_conservative", "suspicious", "defect"]
ORDER: Final[tuple[Klass, ...]] = ("equivalent", "more_conservative", "suspicious", "defect")
FRONTEND: Final = (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.typescript.entry")
FIXTURES: Final = Path(__file__).resolve().parent
ALLOWLIST: Final = FIXTURES / "typescript-differential-allowlist.json"
REFERENCE: Final = FIXTURES / "typescript-reference.json"
EXPECTED_GROUPS: Final = {
    "variant": 34,
    "hidden-loader": 111,
    "runtime-alias": 24,
    "module-identity": 9,
    "fixture": 2,
}
# Reasons that name the compiler's own wording or an absolute path, reduced to their cause.
_REASON: Final = (
    (re.compile(r"^(Syntax error in [^:]+): .*"), r"\1"),
    (re.compile(r"^(Compiler option \d+): .*"), r"\1"),
    (
        re.compile(r"^(Cannot read file|Cannot parse|File '.*' not found).*"),
        "TSConfig is unreadable",
    ),
    (re.compile(r"^No inputs were found in config file.*"), "No inputs were found in config file"),
)


@dataclass(frozen=True)
class Case:
    name: str
    group: str
    root: Path
    request: CollectionRequest
    variant: Variant | None = None
    # A module identity the catalog fixes for the one source file of the case.
    module: str | None = None


@dataclass(frozen=True)
class Edge:
    kind: str
    module: str | None
    file: str | None
    runtime: str | None
    declaration: str | None
    package: str | None
    flags: tuple[bool | None, bool | None, bool | None]


@dataclass(frozen=True)
class Summary:
    complete: bool
    selected: tuple[str, ...]
    counts: tuple[int, int]
    files: frozenset[tuple[str, str, str, bool]]
    edges: dict[tuple[str, str, str, int, int], Edge]
    reasons: frozenset[str]
    gap_modules: frozenset[str]
    inputs: dict[str, tuple[str, str]]


@dataclass(frozen=True)
class Finding:
    klass: Klass
    subject: str
    old: str
    new: str


@dataclass(frozen=True)
class Result:
    case: Case
    findings: tuple[Finding, ...]
    # (rule id, oracle status, frontend status) of every rule whose Core status differs.
    rules: tuple[tuple[str, str, str], ...] = ()
    # How many Core statuses were compared, for the report.
    compared: int = 0

    @property
    def klass(self) -> Klass:
        return max((item.klass for item in self.findings), key=ORDER.index, default="equivalent")


def request_for(
    root: Path, roots: tuple[str, ...], namespace: str, tsconfig: str = "tsconfig.json"
) -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(roots, namespace),
        TypeScriptSettings(tsconfig),
    )


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)


def _hidden(workspace: Path) -> list[Case]:
    catalog = json.loads((FIXTURES / "typescript-hidden-loaders.json").read_text())
    cases = []
    for index, item in enumerate(catalog):
        root = workspace / f"hidden-{index}"
        scenario = typescript_scenarios.Scenario(
            item["name"],
            {
                "package.json": json.dumps(item.get("manifest") or {}),
                "src/main.ts": item["source"],
                **typescript_scenarios.HIDDEN,
                **item.get("files", {}),
            },
            typescript_scenarios.only("src/main.ts"),
        )
        typescript_scenarios.write(root, scenario)
        cases.append(
            Case(
                f"hidden-loader/{item['name']}",
                "hidden-loader",
                root,
                request_for(root, ("src",), "app"),
            )
        )
    return cases


def _aliases(workspace: Path) -> list[Case]:
    catalog = json.loads((FIXTURES / "typescript-runtime-aliases.json").read_text())
    cases = []
    for index, item in enumerate(catalog):
        for state in ("first", "hidden"):
            root = workspace / f"alias-{index}-{state}"
            entry = item.get("entry_path", "src/main.ts")
            default = {
                "src/runtime.ts": "export const value=1;",
                "src/runtime.js": "throw Error('must not execute');",
            }
            files = {
                "package.json": json.dumps(item["manifest"]),
                entry: item.get("source") or f"import '{item['specifier']}';",
                **(item.get("files") or default),
            }
            if item.get("runtime"):
                files[f"src/{item['runtime']}"] = "import './missing.js';"
            if state == "hidden":
                runtime = item.get("runtime_path", "src/runtime.js")
                files[runtime] = (
                    "require('./missing.cjs');" if item.get("files") else "import './missing.js';"
                )
            scenario = typescript_scenarios.Scenario(
                item["name"],
                files,
                typescript_scenarios.only(*item.get("selected_files", ["src/main.ts"])),
            )
            typescript_scenarios.write(root, scenario)
            name = f"runtime-alias/{item['name']}/{state}"
            cases.append(Case(name, "runtime-alias", root, request_for(root, ("src",), "app")))
    return cases


def _identities(workspace: Path) -> list[Case]:
    catalog = json.loads((FIXTURES / "typescript-module-identities.json").read_text())
    cases = []
    for index, item in enumerate(catalog):
        root = workspace / f"identity-{index}"
        scenario = typescript_scenarios.Scenario(
            item["path"], {item["path"]: "export {};\n"}, {"include": [item["path"].split("/")[0]]}
        )
        typescript_scenarios.write(root, scenario)
        request = request_for(root, (item["path"].split("/")[0],), item["namespace"])
        cases.append(
            Case(
                f"module-identity/{item['path']}",
                "module-identity",
                root,
                request,
                module=item["module"],
            )
        )
    return cases


def _fixtures(workspace: Path) -> list[Case]:
    cases = []
    for name, namespace in (("H-typescript", "shop"), ("H-uml-typescript", "demo")):
        root = workspace / name
        shutil.copytree(FIXTURES / name, root)
        if (root / "resolver-inputs").is_dir():
            shutil.copytree(root / "resolver-inputs", root / "node_modules")
        cases.append(
            Case(f"fixture/{name}", "fixture", root, request_for(root, ("src",), namespace))
        )
    return cases


def _variants(workspace: Path) -> list[Case]:
    cases = []
    for variant in VARIANTS:
        root = repository(workspace / "variants", variant)
        config = load_config(root)
        request = request_for(
            root, config.roots, config.namespace, config.tsconfig or "tsconfig.json"
        )
        cases.append(Case(f"variant/{variant.id}", "variant", root, request, variant))
    return cases


def _scenarios(workspace: Path) -> list[Case]:
    cases = []
    for scenario in (
        *typescript_scenarios.SCENARIOS,
        *typescript_scenarios.configurations(),
        *typescript_scenarios.matrix(),
    ):
        root = workspace / "scenarios" / scenario.name.replace("/", "-") / "root"
        typescript_scenarios.write(root, scenario)
        request = request_for(root, scenario.roots, "app", scenario.tsconfig)
        group = "matrix" if scenario.name.startswith("matrix/") else "scenario"
        cases.append(Case(f"{group}/{scenario.name.removeprefix('matrix/')}", group, root, request))
    return cases


def corpus(workspace: Path) -> list[Case]:
    """Every case of the acceptance corpus, materialized below `workspace`."""
    return [
        *_variants(workspace),
        *_hidden(workspace),
        *_aliases(workspace),
        *_identities(workspace),
        *_fixtures(workspace),
        *_scenarios(workspace),
    ]


def collect(argv: tuple[str, ...], request: CollectionRequest) -> SourceFacts:
    result = ProcessCollector(argv).collect(request)
    if isinstance(result, SourceFacts):
        return result
    raise RuntimeError(f"{result.kind}: {result.message}")


def _reason(text: str, root: str) -> str:
    plain = text.replace(root, "<root>")
    return next(
        (pattern.sub(old, plain) for pattern, old in _REASON if pattern.match(plain)), plain
    )


def summarize(facts: SourceFacts, root: str) -> Summary:
    evidence = {item.id: item for item in facts.evidence}
    targets = {item.import_id: item for item in facts.imports}
    edges: dict[tuple[str, str, str, int, int], Edge] = {}
    for section in facts.sections:
        for record in section.records if section.name == "imports" else ():
            target, spot = targets[record.id], evidence[record.evidence_ids[0]]
            key = (
                str(record.data.get("source_module")),
                record.kind,
                str(record.data.get("specifier")),
                spot.line,
                spot.column,
            )
            flags = tuple(
                value if isinstance(value := record.data.get(name), bool) else None
                for name in ("type_only", "reexport", "module_level_import")
            )
            edges[key] = Edge(
                type(target).__name__,
                target.module if isinstance(target, LocalTarget) else None,
                target.file if isinstance(target, LocalTarget) else None,
                target.runtime_file if isinstance(target, LocalTarget) else None,
                target.declaration_file if isinstance(target, LocalTarget) else None,
                target.package
                if isinstance(target, ExternalPackageTarget)
                else target.name
                if isinstance(target, BuiltinTarget)
                else None,
                (flags[0], flags[1], flags[2]),
            )
    gaps = facts.coverage.gaps
    return Summary(
        facts.coverage.full_scope,
        facts.coverage.selected_files,
        (facts.coverage.files_read, facts.coverage.files_parsed),
        frozenset((f.rel_path, f.module, f.package, f.blank) for f in facts.files),
        edges,
        frozenset(_reason(item.title, root) for item in gaps),
        frozenset(str(item.data.get("module")) for item in gaps),
        {item.path: (item.digest, item.role) for item in facts.inputs},
    )


def _fingerprint(case: Case) -> str:
    files = []
    for path in sorted(case.root.rglob("*")):
        relative = path.relative_to(case.root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            value = path.readlink().as_posix().replace(str(case.root.parent), "<parent>")
            files.append([relative.as_posix(), "link", value])
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append([relative.as_posix(), "file", digest])
    value = [asdict(case.request.scope), asdict(case.request.resolver), files]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _reference_summary(data: dict[str, object]) -> Summary:
    return Summary(
        data["complete"],
        tuple(data["selected"]),
        tuple(data["counts"]),
        frozenset(tuple(item) for item in data["files"]),
        {
            tuple(key): Edge(**{**edge, "flags": tuple(edge["flags"])})
            for key, edge in data["edges"]
        },
        frozenset(data["reasons"]),
        frozenset(data["gap_modules"]),
        {path: tuple(value) for path, value in data["inputs"].items()},
    )


@lru_cache(maxsize=1)
def _reference_records(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def reference(case: Case) -> tuple[Summary, dict[str, str]]:
    records = _reference_records(REFERENCE)
    record = records.get(case.name)
    if record is None:
        raise ValueError(f"missing frozen TypeScript reference case: {case.name}")
    actual = _fingerprint(case)
    if record["input_digest"] != actual:
        raise ValueError(f"stale frozen TypeScript reference case: {case.name}")
    return _reference_summary(record["summary"]), record["statuses"]


def _edge(key: tuple[str, str, str, int, int], old: Edge, new: Edge) -> list[Finding]:
    subject = " ".join(map(str, key[1:]))
    findings = []

    def add(klass: Klass, label: str, before: object, after: object) -> None:
        findings.append(Finding(klass, f"{subject}: {label}", str(before), str(after)))

    if old.flags != new.flags:
        add("defect", "flags (type_only, reexport, module_level)", old.flags, new.flags)
    resolved = ("LocalTarget", "ExternalPackageTarget", "BuiltinTarget")
    if old.kind == new.kind == "UnresolvedTarget":
        return findings
    if old.kind in resolved and new.kind == "UnresolvedTarget":
        add("more_conservative", "target", old.kind, new.kind)
    elif old.kind == "UnresolvedTarget" and new.kind in resolved:
        add("suspicious", "target", old.kind, new.kind)
    elif old.kind != new.kind:
        add("defect", "target kind", old.kind, new.kind)
    elif old.kind == "LocalTarget":
        if old.declaration != new.declaration:
            add("defect", "declaration_file", old.declaration, new.declaration)
        if (old.runtime is None) != (new.runtime is None):
            klass: Klass = "more_conservative" if new.runtime is None else "suspicious"
            add(klass, "runtime_file", old.runtime, new.runtime)
        elif old.runtime != new.runtime or (old.file, old.module) != (new.file, new.module):
            add("defect", "runtime_file or file", (old.runtime, old.file), (new.runtime, new.file))
    elif old.package != new.package:
        add("defect", "package or builtin name", old.package, new.package)
    return findings


def compare(old: Summary, new: Summary) -> list[Finding]:
    findings: list[Finding] = []
    if old.complete != new.complete:
        klass: Klass = "more_conservative" if old.complete else "suspicious"
        findings.append(Finding(klass, "full_scope", str(old.complete), str(new.complete)))
    old_files, new_files = {item[0] for item in old.files}, {item[0] for item in new.files}
    for path in sorted(old_files - new_files):
        klass = "more_conservative" if not new.complete else "defect"
        findings.append(Finding(klass, f"file not parsed: {path}", "parsed", "absent"))
    for path in sorted(new_files - old_files):
        klass = "suspicious" if not old.complete else "defect"
        findings.append(
            Finding(klass, f"file parsed only by the frontend: {path}", "absent", "parsed")
        )
    if old_files == new_files and (old.files != new.files or old.counts != new.counts):
        findings.append(Finding("defect", "file facts or counts", str(old.counts), str(new.counts)))
    if old_files == new_files and old.selected != new.selected:
        findings.append(Finding("defect", "selected files", str(old.selected), str(new.selected)))
    modules = {item[1] for item in old.files} & {item[1] for item in new.files}
    for key in sorted(old.edges.keys() | new.edges.keys()):
        before, after = old.edges.get(key), new.edges.get(key)
        if key[0] not in modules:
            continue
        if before is not None and after is not None:
            findings.extend(_edge(key, before, after))
        elif before is not None:
            covered = key[0] in new.gap_modules
            klass = "more_conservative" if covered else "defect"
            findings.append(Finding(klass, f"edge dropped: {key[1:]}", str(before.kind), "absent"))
        elif after is not None:
            klass = "suspicious" if key[0] in old.gap_modules else "defect"
            findings.append(
                Finding(klass, f"edge only in the frontend: {key[1:]}", "absent", str(after.kind))
            )
    shared = old.inputs.keys() & new.inputs.keys()
    for path in sorted(shared):
        if old.inputs[path][0] != new.inputs[path][0]:
            findings.append(
                Finding(
                    "defect",
                    f"input bytes: {path}",
                    old.inputs[path][0][:12],
                    new.inputs[path][0][:12],
                )
            )
    # Reasons and resolution-only inputs the compiler reads beyond the frontend's rules are
    # recorded for review; they cannot change a verdict while completeness and edges agree.
    if old.reasons != new.reasons:
        findings.append(
            Finding(
                "equivalent",
                "gap reasons",
                "; ".join(sorted(old.reasons - new.reasons)),
                "; ".join(sorted(new.reasons - old.reasons)),
            )
        )
    if set(old.inputs) != set(new.inputs):
        findings.append(
            Finding(
                "equivalent",
                "resolution inputs",
                ", ".join(sorted(set(old.inputs) - set(new.inputs))),
                ", ".join(sorted(set(new.inputs) - set(old.inputs))),
            )
        )
    return findings


def _statuses(outcome: Outcome) -> dict[str, str]:
    result = outcome.report
    rules = {item.id: item.status for item in result.rule_assessments or ()}
    return {
        **rules,
        "<declared_rules>": result.declared_rules,
        "<observation_complete>": result.observation_complete,
        "<exit>": str(result.exit_code),
        "<diagnostics>": ",".join(sorted({item.kind for item in result.diagnostics})),
    }


def _verdicts(
    old: dict[str, str], case: Case, workspace: Path
) -> tuple[list[Finding], list[tuple[str, str, str]], int]:
    if case.variant is None:
        return [], [], 0
    new = _statuses(run_variant(workspace / "core-new", case.variant))
    findings, rules = [], []
    for rule in sorted(old.keys() | new.keys()):
        before, after = old.get(rule, "absent"), new.get(rule, "absent")
        if before == after:
            continue
        if rule.startswith("<"):
            klass: Klass = (
                "more_conservative"
                if before in ("PASS", "FAIL") and after == "UNKNOWN"
                else "defect"
            )
            klass = "equivalent" if rule == "<exit>" and klass != "defect" else klass
        elif after == "UNKNOWN":
            klass = "more_conservative"
            rules.append((rule, before, after))
        elif before == "UNKNOWN":
            klass = "suspicious"
        else:
            klass = "defect"
        findings.append(Finding(klass, f"Core verdict {rule}", before, after))
    return findings, rules, len(old.keys() | new.keys())


def evaluate(case: Case, workspace: Path) -> Result:
    root = str(case.root)
    try:
        old, statuses = reference(case)
    except (OSError, ValueError, KeyError, TypeError) as error:
        finding = Finding("defect", "the frozen reference failed", str(error)[:200], "")
        return Result(case, (finding,))
    try:
        new = summarize(collect(FRONTEND, case.request), root)
    except RuntimeError as error:
        return Result(case, (Finding("defect", "the frontend failed", "", str(error)[-300:]),))
    findings = compare(old, new)
    if case.module is not None:
        modules = {item[1] for item in new.files}
        if modules != {case.module}:
            findings.append(
                Finding("defect", "module identity", case.module, ", ".join(sorted(modules)))
            )
    verdicts, rules, compared = _verdicts(statuses, case, workspace)
    return Result(case, (*findings, *verdicts), tuple(rules), compared)


def run(workspace: Path) -> list[Result]:
    cases = corpus(workspace)
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda case: evaluate(case, workspace), cases))


@dataclass(frozen=True)
class Verdict:
    report: dict[str, object]
    failures: list[str] = field(default_factory=list)


def judge(results: list[Result], allowlist: dict[str, dict[str, str]]) -> Verdict:
    """Count the classes and name every case the allow-list does not cover."""
    failures: list[str] = []
    seen: dict[str, Klass] = {}
    for result in results:
        seen[result.case.name] = result.klass
        if result.klass == "defect":
            failures.append(f"defect: {result.case.name}")
        elif result.klass in ("more_conservative", "suspicious"):
            reason = allowlist.get(result.klass, {}).get(result.case.name, "")
            if not reason.strip():
                failures.append(f"{result.klass} without an allow-list reason: {result.case.name}")
    for klass, entries in allowlist.items():
        for name, reason in entries.items():
            if seen.get(name) != klass:
                failures.append(f"stale allow-list entry ({klass}): {name}")
            if not reason.strip():
                failures.append(f"allow-list entry without a reason: {name}")
    counts = Counter(result.klass for result in results)
    groups = Counter(result.case.group for result in results)
    lost = Counter(
        (rule, before)
        for result in results
        for rule, before, _ in result.rules
        if before != "UNKNOWN"
    )
    report: dict[str, object] = {
        "counts": {klass: counts.get(klass, 0) for klass in ORDER},
        "allowlist_entries": {klass: len(entries) for klass, entries in sorted(allowlist.items())},
        "core_statuses_compared": sum(result.compared for result in results),
        "groups": dict(sorted(groups.items())),
        "fail_to_unknown": {
            rule: n for (rule, before), n in sorted(lost.items()) if before == "FAIL"
        },
        "pass_to_unknown": {
            rule: n for (rule, before), n in sorted(lost.items()) if before == "PASS"
        },
        "cases": [
            {
                "case": result.case.name,
                "group": result.case.group,
                "class": result.klass,
                "findings": [
                    {
                        "class": item.klass,
                        "subject": item.subject,
                        "oracle": item.old,
                        "frontend": item.new,
                    }
                    for item in result.findings
                ],
            }
            for result in results
        ],
        "failures": failures,
    }
    return Verdict(report, failures)


def load_allowlist() -> dict[str, dict[str, str]]:
    return json.loads(ALLOWLIST.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="archkeel-differential-") as workspace:
        verdict = judge(run(Path(workspace)), load_allowlist())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "typescript-differential.json").write_text(
        json.dumps(verdict.report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(verdict.report["counts"], sort_keys=True))
    print("\n".join(verdict.failures))
    return 1 if verdict.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
