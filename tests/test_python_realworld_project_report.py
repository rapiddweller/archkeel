# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Full-source replays for the pinned Python RealWorld Target."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts import SourceFacts
from archkeel.ir.graph_codec import parse_report
from archkeel.ir.protocol import PythonSettings
from fixtures.architecture_demo import CATALOG, REPORT_CASES, UML_DEMO_COMPARISONS, replay
from fixtures.demo_catalog_python_realworld import (
    PYTHON_REALWORLD_FIXTURE_DIR,
    VARIANTS,
)

ROOT = Path(__file__).parents[1]
TARGET_FILES = (
    "architecture-contract.json",
    "contracts/host-runtime.json",
    "contracts/http-interface.json",
    "contracts/product-policy.json",
    "contracts/product-contracts.json",
    "contracts/postgres-adapter.json",
)
TARGET_DIGEST = "5dcc89c72c96c49f80524b86137a4aba103bbe604f83bc2518aa542c6fa0519d"
# Fixture bytes remain pinned; native digests also bind captured provider sources.
SOURCE_DIGESTS = {
    "python-realworld-project": (
        "177b3854b42b7edd5ffad71c95d167aba3086013686d9a964e198bb079d047ce"
    ),
    "python-realworld-forbidden-edge": (
        "0749ba49669a5b41cf4eee83be56b0f7f5992d4028f69f8d9200a9cbec80a549"
    ),
    "python-realworld-signature-fail": (
        "6f8eb84c8afd9f164d138baf7438b2bda25b76f18c82489e6cd000cd6250fac1"
    ),
    "python-realworld-dynamic-unknown": (
        "b1e0e0fcac35279821dd4a1d3f88d49661ac5c77bf2223e3c7d8db7bb4032cc5"
    ),
}
EXPECTED_ASSESSMENT_STATUSES = {
    "python-realworld-project": Counter(PASS=1228, UNKNOWN=14, FAIL=0),
    "python-realworld-forbidden-edge": Counter(PASS=1228, UNKNOWN=14, FAIL=0),
    "python-realworld-signature-fail": Counter(PASS=1227, UNKNOWN=14, FAIL=1),
    "python-realworld-dynamic-unknown": Counter(PASS=1227, UNKNOWN=15, FAIL=0),
}
EXPECTED_UNKNOWN_ASPECTS = {
    "python-realworld-project": Counter(relationship=13, completeness=1),
    "python-realworld-forbidden-edge": Counter(relationship=13, completeness=1),
    "python-realworld-signature-fail": Counter(relationship=13, completeness=1),
    "python-realworld-dynamic-unknown": Counter(relationship=14, completeness=1),
}

UNKNOWN_INHERITANCE = {
    "inherits-app-api-dependencies-authentication-rwapikeyheader-symbol-fastapi-security-apikeyheader",
    "inherits-app-core-settings-app-appsettings-app-core-settings-base-baseappsettings",
    "inherits-app-core-settings-base-baseappsettings-symbol-pydantic-basesettings",
    "inherits-app-core-settings-development-devappsettings-app-core-settings-app-appsettings",
    "inherits-app-core-settings-production-prodappsettings-app-core-settings-app-appsettings",
    "inherits-app-core-settings-test-testappsettings-app-core-settings-app-appsettings",
    "inherits-app-models-domain-articles-article-app-models-common-datetimemodelmixin",
    "inherits-app-models-domain-articles-article-app-models-common-idmodelmixin",
    "inherits-app-models-domain-comments-comment-app-models-common-datetimemodelmixin",
    "inherits-app-models-domain-comments-comment-app-models-common-idmodelmixin",
    "inherits-app-models-domain-users-userindb-app-models-common-datetimemodelmixin",
    "inherits-app-models-domain-users-userindb-app-models-common-idmodelmixin",
    "inherits-app-models-schemas-articles-articleforresponse-app-models-domain-articles-article",
}


def _payload(html: Path) -> dict:
    match = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>',
        html.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


def _report(output: Path):
    main = output.with_suffix(".report.html")
    atlas = _payload(main)["atlas"]
    detail = main.with_name(atlas["detail_page"])
    data = _payload(detail)
    assert data["navigation"]["main_href"] == main.name
    return parse_report(
        {
            key: value
            for key, value in data.items()
            if key not in {"initial_scope", "initial_view", "navigation", "boundary_permissions"}
        }
    )


def _assess(report, subject_id: str, aspect: str):
    assert report.comparison is not None
    return next(
        item
        for item in report.comparison.assessments
        if item.subject_id == subject_id and item.aspect == aspect
    )


def test_python_realworld_variants_are_source_only_and_keep_all_upstream_inputs() -> None:
    expected = {
        "python-realworld-project",
        "python-realworld-forbidden-edge",
        "python-realworld-signature-fail",
        "python-realworld-dynamic-unknown",
    }
    assert {item.id for item in VARIANTS} == expected
    assert {item.id for item in CATALOG if item.id.startswith("python-realworld-")} == expected
    assert {key for key, (variant_id, _) in REPORT_CASES.items() if variant_id in expected} == {
        f"uml-{variant_id}" for variant_id in expected
    }
    assert {
        key: UML_DEMO_COMPARISONS[key]
        for key in UML_DEMO_COMPARISONS
        if key.startswith("uml-python-realworld-")
    } == {
        "uml-python-realworld-project": "UNKNOWN",
        "uml-python-realworld-forbidden-edge": "UNKNOWN",
        "uml-python-realworld-signature-fail": "FAIL",
        "uml-python-realworld-dynamic-unknown": "UNKNOWN",
    }

    snapshot = json.loads((PYTHON_REALWORLD_FIXTURE_DIR / "SNAPSHOT.json").read_bytes())
    app_files = {
        item["path"]: item for item in snapshot["files"] if item["path"].startswith("app/")
    }
    python_paths = {path for path in app_files if path.endswith(".py")}
    assert len(app_files) == 79
    assert len(python_paths) == 72
    for variant in VARIANTS:
        assert variant.fixture == PYTHON_REALWORLD_FIXTURE_DIR
        changed_paths = set(variant.files)
        assert changed_paths <= python_paths
        for relative, item in app_files.items():
            if relative not in changed_paths:
                assert (
                    hashlib.sha256(
                        (PYTHON_REALWORLD_FIXTURE_DIR / relative).read_bytes()
                    ).hexdigest()
                    == item["sha256"]
                )
        for relative, content in variant.files.items():
            assert content is not None
            assert content != (PYTHON_REALWORLD_FIXTURE_DIR / relative).read_text()

    target_digest = hashlib.sha256(
        b"".join((PYTHON_REALWORLD_FIXTURE_DIR / path).read_bytes() for path in TARGET_FILES)
    ).hexdigest()
    assert target_digest == TARGET_DIGEST
    assert f"Target bundle SHA-256: `{TARGET_DIGEST}`" in (
        PYTHON_REALWORLD_FIXTURE_DIR / "docs/target.md"
    ).read_text(encoding="utf-8")
    variants = {item.id: item for item in VARIANTS}
    edge = variants["python-realworld-forbidden-edge"].files
    assert set(edge) == {"app/api/routes/articles/articles_resource.py"}
    assert (
        "from app.db.queries.queries import queries"
        in edge["app/api/routes/articles/articles_resource.py"]
    )
    signature = variants["python-realworld-signature-fail"].files
    assert signature["app/models/domain/articles.py"].count("tags: List[int]") == 1
    assert signature["app/models/domain/articles.py"].count("tags: List[str]") == 0
    dynamic = variants["python-realworld-dynamic-unknown"].files["app/api/routes/authentication.py"]
    login, register = dynamic.split("async def register", maxsplit=1)
    assert 'getattr(jwt, "create_access_token_for_user")' in login
    assert "token = jwt.create_access_token_for_user(" in register


def _check_native_source_digest(request, facts, fixture_digest):
    assert isinstance(facts, SourceFacts)
    assert isinstance(request.resolver, PythonSettings)
    providers = request.resolver.provider_sources
    assert providers
    snapshot = json.loads((PYTHON_REALWORLD_FIXTURE_DIR / "SNAPSHOT.json").read_bytes())
    selected = {
        item["path"]
        for item in snapshot["files"]
        if item["path"].startswith("app/") and item["path"].endswith(".py")
    }
    assert set(facts.coverage.selected_files) == selected
    source = hashlib.sha256()
    inputs = {}
    for path in sorted(selected | {"pyproject.toml"}):
        content = (Path(request.snapshot.root) / path).read_bytes()
        inputs[path] = (
            hashlib.sha256(content).hexdigest(),
            "selected" if path in selected else "resolution",
        )
        source.update(path.encode() + b"\0" + content + b"\0")
    assert source.hexdigest() == fixture_digest
    for provider in sorted(providers, key=lambda item: item.path):
        assert provider.path not in inputs
        content = provider.source.encode("utf-8")
        assert hashlib.sha256(content).hexdigest() == provider.digest
        inputs[provider.path] = (provider.digest, "resolution")
        source.update(provider.path.encode() + b"\0" + content + b"\0")
    assert len(facts.inputs) == len(inputs)
    assert {item.path: (item.digest, item.role) for item in facts.inputs} == inputs
    assert facts.source.source_digest == source.hexdigest()


def test_python_realworld_reports_keep_coverage_architecture_and_uml_distinct(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {
        "python-realworld-project": ("UNKNOWN", "UNKNOWN", 0),
        "python-realworld-forbidden-edge": ("FAIL", "UNKNOWN", 2),
        "python-realworld-signature-fail": ("FAIL", "FAIL", 2),
        "python-realworld-dynamic-unknown": ("UNKNOWN", "UNKNOWN", 0),
    }
    collect = ProcessCollector.collect
    reports = {}
    target_digests = set()
    target_module_sets = set()
    observed_module_sets = set()
    for variant_id, (rules_status, comparison_status, replay_exit) in expected.items():
        assert REPORT_CASES[f"uml-{variant_id}"] == (variant_id, replay_exit)
        output = tmp_path / f"{variant_id}.json"
        captured_digests = []

        def checked_collect(
            collector,
            request,
            *,
            fixture_digest=SOURCE_DIGESTS[variant_id],
            captured=captured_digests,
        ):
            facts = collect(collector, request)
            _check_native_source_digest(request, facts, fixture_digest)
            captured.append(facts.source.source_digest)
            return facts

        with monkeypatch.context() as capture:
            capture.setattr(ProcessCollector, "collect", checked_collect)
            assert replay(variant_id, output) == REPORT_CASES[f"uml-{variant_id}"][1]
        summaries = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("{") and line.endswith("}")
        ]
        validate_summary = next(item for item in summaries if item.get("command") == "validate")
        report_summary = next(item for item in summaries if item.get("command") == "report")
        assert validate_summary["exit_code"] == replay_exit
        assert report_summary["exit_code"] == 0
        assert report_summary["observation_complete"] == "PASS"
        assert report_summary["declared_rules"] == rules_status
        assert report_summary["coverage"]["status"] == "PASS"
        assert report_summary["coverage"]["files_discovered"] == 72
        assert report_summary["coverage"]["files_read"] == 72
        assert report_summary["coverage"]["files_parsed"] == 72
        assert report_summary["coverage"]["ast_coverage_percent"] == 100.0
        assert report_summary["coverage"]["failures"] == []

        raw = json.loads(output.read_text(encoding="utf-8"))
        assert captured_digests
        assert set(captured_digests) == {raw["source"]["source_digest"]}
        target_digests.add(raw["contract"]["digest"])
        assert output.with_suffix(".report.html").is_file()
        assert output.with_suffix(".detail.html").is_file()
        report = _report(output)
        assert report.comparison is not None
        assert report.comparison.status == comparison_status
        assert len(report.comparison.assessments) == 1242
        assert (
            Counter(item.status for item in report.comparison.assessments)
            == (EXPECTED_ASSESSMENT_STATUSES[variant_id])
        )
        assert (
            Counter(
                item.aspect for item in report.comparison.assessments if item.status == "UNKNOWN"
            )
            == EXPECTED_UNKNOWN_ASPECTS[variant_id]
        )
        incomplete_enum = "Host and runtime composition:class-app-core-settings-base-appenvtypes"
        closed = {
            item.subject_id: item.status
            for item in report.comparison.assessments
            if item.aspect == "completeness"
        }
        assert len(closed) == 34
        assert closed == {
            scope.scope_id: "UNKNOWN" if scope.scope_id == incomplete_enum else "PASS"
            for scope in report.target.target_scopes
        }
        unknown = {
            (item.subject_id, item.aspect): item.reason
            for item in report.comparison.assessments
            if item.status == "UNKNOWN"
        }
        expected_unknown = {
            (identity, "relationship"): "Unresolved source sites may refer to this endpoint."
            for identity in UNKNOWN_INHERITANCE
        }
        expected_unknown[incomplete_enum, "completeness"] = (
            "Closed scope inventory or resolution is incomplete."
        )
        if variant_id == "python-realworld-dynamic-unknown":
            expected_unknown["login-creates-access-token", "relationship"] = (
                "Unresolved source sites may refer to this endpoint."
            )
        assert unknown == expected_unknown
        assert len(report.target.entities) == 329
        assert len(report.target.relationships) == 259
        assert sum(item.kind == "imports" for item in report.target.relationships) == 170
        modules = frozenset(
            item.file_path for item in report.target.entities if item.kind == "module"
        )
        assert len(modules) == 72
        target_module_sets.add(modules)
        observed_modules = frozenset(
            item.file_path for item in report.observed.entities if item.kind == "module"
        )
        assert len(observed_modules) == 72
        observed_module_sets.add(observed_modules)
        reports[variant_id] = (raw, report)

    assert len(target_digests) == 1
    assert len(target_module_sets) == 1
    assert len(observed_module_sets) == 1
    snapshot = json.loads((PYTHON_REALWORLD_FIXTURE_DIR / "SNAPSHOT.json").read_bytes())
    expected_modules = {
        item["path"]
        for item in snapshot["files"]
        if item["path"].startswith("app/") and item["path"].endswith(".py")
    }
    assert next(iter(target_module_sets)) == expected_modules
    assert next(iter(observed_module_sets)) == expected_modules

    article_tags_id = next(
        item.id
        for item in reports["python-realworld-project"][1].target.entities
        if item.qualified_name == "app.models.domain.articles.Article.tags"
    )
    baseline_tags = _assess(reports["python-realworld-project"][1], article_tags_id, "annotation")
    changed_tags = _assess(
        reports["python-realworld-signature-fail"][1], article_tags_id, "annotation"
    )
    assert (baseline_tags.status, changed_tags.status) == ("PASS", "FAIL")
    assert baseline_tags.evidence_ids == changed_tags.evidence_ids == ("EVD-c2388a9ba3d25a6a",)

    call_id = "login-creates-access-token"
    baseline_call = _assess(reports["python-realworld-project"][1], call_id, "relationship")
    dynamic_call = _assess(reports["python-realworld-dynamic-unknown"][1], call_id, "relationship")
    assert (baseline_call.status, dynamic_call.status) == ("PASS", "UNKNOWN")
    assert baseline_call.evidence_ids == ("EVD-88d03eb1dba95d8e",)
    assert set(baseline_call.evidence_ids) <= set(dynamic_call.evidence_ids)

    forbidden = reports["python-realworld-forbidden-edge"][0]["violations"]
    assert len(forbidden) == 1
    assert forbidden[0][7] == ["REQUIRES-COMPLETE"]
    assert forbidden[0][6] == ["EVD-9ce79f4676056d33"]
