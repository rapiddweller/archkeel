# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The repository rule is independent of language facts and uses the selected revision."""

import json
from collections import Counter

import pytest

from archkeel.analyzer.python.collect import collect
from archkeel.check.observe import Observer
from archkeel.check.ports import RepositorySnapshotPaths
from archkeel.check.repository_inputs import read_repository_inputs
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import RuleAssessmentStatus


class Collector:
    def collect(self, request):
        return collect(request)


def _setup(root, *, rules=True):
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x=1\n")
    (root / "Makefile").write_text("one\ntwo\nthree\n")
    payload = {"schema_version": "3.8.0", "components": [], "rules": []}
    if rules:
        payload["rules"] = [
            {
                "id": "LINES",
                "kind": "max_file_lines",
                "max_lines": 2,
                "rationale": "reviewable source",
                "provenance": ["contract.json"],
                "decided_by": "architect",
                "selection": {
                    "scopes": [
                        {
                            "root": ".",
                            "suffixes": [],
                            "exact_filenames": ["Makefile"],
                            "shebang": False,
                        }
                    ],
                    "exclusions": [],
                },
            }
        ]
    (root / "contract.json").write_text(json.dumps(payload))
    return payload


def _observe(root, reader=read_repository_inputs):
    return Observer(Collector(), repository_reader=reader)(
        root,
        roots=("src",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
        repository_snapshot=RepositorySnapshotPaths(("Makefile", "src/a.py"), "a" * 40, False),
    )


def test_no_active_rule_does_not_invoke_repository_reader(tmp_path):
    _setup(tmp_path, rules=False)

    def forbidden(*args, **kwargs):
        pytest.fail("inactive repository reader")

    result = _observe(tmp_path, forbidden)
    assert result.observation is not None, result.diagnostics


def test_active_rule_uses_text_inventory_and_exact_evidence(tmp_path):
    _setup(tmp_path)
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    report = result.observation
    assert [(item.id, item.status) for item in _rows(report)] == [
        ("LINES", RuleAssessmentStatus.FAIL)
    ]
    assert any(item.kind == "max_file_lines" for item in report.records("violations"))
    assert any(
        item.file == "Makefile" and item.excerpt.startswith("sha256:") for item in report.evidence
    )


def test_shared_selection_inventory_is_published_once_for_multiple_rules(tmp_path):
    payload = _setup(tmp_path)
    payload["rules"].append({**payload["rules"][0], "id": "OTHER", "max_lines": 4})
    (tmp_path / "contract.json").write_text(json.dumps(payload))
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    records = result.observation.records("scope_observations")
    assert len([item for item in records if item.kind == "repository_file_inventory"]) == 1
    assert {item.id: item.status for item in _rows(result.observation)} == {
        "LINES": RuleAssessmentStatus.FAIL,
        "OTHER": RuleAssessmentStatus.PASS,
    }


def test_missing_expected_file_remains_unknown(tmp_path):
    _setup(tmp_path)
    (tmp_path / "Makefile").unlink()
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert _rows(result.observation)[0].status is RuleAssessmentStatus.UNKNOWN


def _rows(report):
    return rule_assessments(
        report,
        undecided_by_rule=Counter(
            rule for item in report.records("unknowns") for rule in item.rule_ids
        ),
    )


def test_mounted_rule_uses_qualified_id_and_projected_declaration(tmp_path):
    nested = _setup(tmp_path)
    nested["rules"][0]["max_lines"] = 4
    (tmp_path / "inside.json").write_text(json.dumps(nested))
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "3.8.0",
                "components": [
                    {
                        "id": "app",
                        "label": "app",
                        "packages": ["sample"],
                        "role": "component",
                        "responsibilities": ["application"],
                        "forbidden_responsibilities": [],
                        "provenance": ["contract.json"],
                        "inside": "inside.json",
                    }
                ],
                "rules": [],
            }
        )
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert {item.id: item.status for item in _rows(result.observation)} == {
        "app:LINES": RuleAssessmentStatus.PASS,
    }


@pytest.mark.parametrize("adapter", [False, True])
def test_revision_uses_pinned_rule_selection_and_revision_file_bytes(
    tmp_path, monkeypatch, adapter
):
    import subprocess

    from archkeel.check.ports import ScanConfig
    from archkeel.check.run import observe_revision

    _setup(tmp_path)

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "test")
    git("config", "user.email", "test@example.invalid")
    git("add", ".")
    git("commit", "-qm", "source")
    revision = git("rev-parse", "HEAD")
    (tmp_path / "Makefile").write_text("short\n")
    payload = json.loads((tmp_path / "contract.json").read_text())
    payload["rules"][0]["max_lines"] = 4
    (tmp_path / "contract.json").write_text(json.dumps(payload))
    git("add", ".")
    git("commit", "-qm", "declaration")
    declaration = git("rev-parse", "HEAD")
    (tmp_path / "Makefile").unlink()
    (tmp_path / "contract.json").write_text("broken live declaration")
    config = ScanConfig(("src",), "sample", "contract.json", "config")
    from archkeel.cli import observe as cli_observe

    monkeypatch.setattr(cli_observe, "observer_for", lambda language: Observer(Collector()))
    analyzer = cli_observe.observe if adapter else Observer(Collector())
    result = observe_revision(analyzer, tmp_path, revision, config, declared_at=declaration)
    assert result.observation is not None, result.diagnostics
    assert _rows(result.observation)[0].status is RuleAssessmentStatus.PASS
    inventories = [
        item
        for item in result.observation.records("scope_observations")
        if item.kind == "repository_file_inventory"
    ]
    assert inventories[0].data.get("snapshot_head") == revision
    # Three archived lines pass only the later four-line declaration; neither live file is read.
    from archkeel.ir.codec_repository_files import parse_repository_inventory
    from archkeel.ir.facts_codec import record_payload

    inventory = parse_repository_inventory(record_payload(inventories[0])["data"])
    assert inventory.files[0].physical_lines == 3


def test_source_bytes_changed_between_collector_and_inventory_stay_unknown(tmp_path):
    payload = _setup(tmp_path)
    scope = payload["rules"][0]["selection"]["scopes"][0]
    scope["suffixes"] = [".py"]
    scope["exact_filenames"] = []
    (tmp_path / "contract.json").write_text(json.dumps(payload))

    def changed_reader(root, selection, **kwargs):
        (root / "src/a.py").write_text("changed = True\n")
        return read_repository_inputs(root, selection, **kwargs)

    result = _observe(tmp_path, changed_reader)
    assert result.observation is not None, result.diagnostics
    assert _rows(result.observation)[0].status is RuleAssessmentStatus.UNKNOWN


def test_repository_gap_does_not_invalidate_independent_source_rule(tmp_path):
    payload = _setup(tmp_path)
    (tmp_path / "src/b.py").write_text("other = 1\n")
    (tmp_path / "Makefile").unlink()
    payload["rules"].append(
        {
            "id": "NO-EDGE",
            "kind": "forbidden_dependency",
            "source": "src.a",
            "target": "src.b",
            "include_type_checking": True,
            "rationale": "independent modules",
            "provenance": ["contract.json"],
            "decided_by": "architect",
        }
    )
    (tmp_path / "contract.json").write_text(json.dumps(payload))
    result = Observer(Collector())(
        tmp_path,
        roots=("src",),
        namespace="src",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
        repository_snapshot=RepositorySnapshotPaths(
            ("Makefile", "src/a.py", "src/b.py"), "a" * 40, False
        ),
    )
    assert result.observation is not None, result.diagnostics
    report = result.observation
    assert {item.id: item.status for item in _rows(report)} == {
        "LINES": RuleAssessmentStatus.UNKNOWN,
        "NO-EDGE": RuleAssessmentStatus.PASS,
    }
    assert report.coverage.status.value == "PASS"
    assert report.coverage.rules.value == "PASS"
    assert not report.coverage.failures
    assert any(item.kind == "repository_file_limit" for item in report.records("unknowns"))
