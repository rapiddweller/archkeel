# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Recent GitHub observations never certify complete publication history."""

import copy
import json
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from archkeel.check.git import MissingBlobError
from tools.github_pr_report import github_pr_report

B, E, H = "b" * 40, "e" * 40, "a" * 40
REPOSITORY = "example/project"


def test_make_github_demo_keeps_protocol_proof_and_bounded_observations_separate(
    tmp_path: Path,
) -> None:
    output = tmp_path / "github-demo"
    run = subprocess.run(
        ["make", "--no-print-directory", "demo-github", f"OUTPUT={output}"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    summary = json.loads((output / "results.json").read_bytes())
    assert {case: summary["protocol"][case]["exit_code"] for case in ("A", "B", "C")} == {
        "A": 1,
        "B": 1,
        "C": 0,
    }
    assert summary["incomparable_analyzer"]["exit_code"] == 2
    assert (
        "analyzer_digest does not match"
        in summary["incomparable_analyzer"]["diagnostics"][0]["unknown_claim"]
    )
    assert set(summary["github"]) == {
        "ordered",
        "reversed",
        "missing",
        "ambiguous",
        "changed-head",
        "missing-lock",
    }
    for case, result in summary["github"].items():
        assert result["exit_code"] == 2 and result["host_order"] is None
        assert (output / f"{case}.check.html").is_file()
    initial = summary["initial_pr"]
    assert initial["opened-expectation"]["exit_code"] == 0
    assert initial["opened-expectation"]["host_order"] == "PASS"
    assert initial["opened-expectation"]["host_source"] == "github_initial_pr_head"
    for case in ("opened-candidate", "reopened", "wrong-run", "tampered", "incomparable"):
        assert initial[case]["exit_code"] == 2 and initial[case]["host_order"] is None
    assert "Original GitHub PR head" in (output / "opened-expectation.check.html").read_text()


def _pr() -> dict:
    return {
        "number": 7,
        "created_at": "2026-10-01T12:00:00Z",
        "base": {"sha": B, "ref": "main", "repo": {"full_name": REPOSITORY}},
        "head": {"sha": H, "ref": "feature", "repo": {"full_name": REPOSITORY}},
    }


def _push(head: str, before: str, hour: int, event_id: str) -> dict:
    return {
        "id": event_id,
        "type": "PushEvent",
        "repo": {"id": 9, "name": REPOSITORY},
        "payload": {
            "repository_id": 9,
            "ref": "refs/heads/feature",
            "head": head,
            "before": before,
        },
        "created_at": f"2026-10-01T{hour:02}:00:00Z",
    }


def _run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pr: object, pages: object
) -> tuple[dict, dict]:
    replies = iter((json.dumps(pr), json.dumps(pages)))
    original_run = subprocess.run

    def request(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[0] == "git":
            return original_run(args, **kwargs)
        assert args[:4] == ["gh", "api", "--hostname", "github.com"]
        assert kwargs["cwd"] == tmp_path
        assert kwargs["timeout"] == 30
        assert args[-1] in {
            "repos/example/project/pulls/7",
            "repos/example/project/events?per_page=100",
        }
        return subprocess.CompletedProcess(args, 0, stdout=next(replies), stderr="")

    def missing(*args: object) -> bytes:
        raise MissingBlobError("architecture-accepted.json")

    monkeypatch.setattr("tools.github_pr_report.subprocess.run", request)
    monkeypatch.setattr("tools.github_pr_report.read_blob", missing)
    output = tmp_path / "report/result.json"
    result = github_pr_report(tmp_path, REPOSITORY, 7, B, H, output)
    assert result.exit_code == 2
    payload = json.loads(output.read_bytes())
    assert payload["host_order"] is None and payload["git_predicate"] is None
    assert payload["host_source"] is None
    assert payload["delta"] is None and payload["measurements"] is None
    assert payload["expectation_fulfilled"] == "UNKNOWN"
    assert "NOT CHECKED" in output.with_suffix(".check.html").read_text()
    metadata = json.loads(output.with_suffix(".github.json").read_bytes())
    for filename, digest in metadata["raw_sha256"].items():
        assert sha256((output.parent / filename).read_bytes()).hexdigest() == digest
    return payload, metadata


@pytest.mark.parametrize("reverse", [False, True])
def test_both_observed_orders_are_unknown_without_complete_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, reverse: bool
) -> None:
    events = [_push(E, B, 11 if reverse else 10, "1"), _push(H, E, 10 if reverse else 11, "2")]
    payload, metadata = _run(monkeypatch, tmp_path, _pr(), [events])
    assert {item["kind"] for item in payload["diagnostics"]} == {"parse_error"}
    assert {item["subject"] for item in payload["diagnostics"]} == {
        "architecture-accepted.json",
        "GitHub example/project PR #7 publication history",
    }
    assert metadata["validated_binding"] == {
        "repository": REPOSITORY,
        "pull_request": 7,
        "base": B,
        "head": H,
        "head_repository": REPOSITORY,
        "head_ref": "refs/heads/feature",
    }
    assert metadata["history"]["event_count"] == 2
    assert metadata["history"]["cap_reached"] is False
    assert metadata["history"]["first_publication_proven"] is False


@pytest.mark.parametrize("pages", [[], [[]]])
def test_missing_history_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pages: object
) -> None:
    _, metadata = _run(monkeypatch, tmp_path, _pr(), pages)
    assert metadata["history"]["event_count"] == 0
    assert metadata["history"]["first_publication_proven"] is False


@pytest.mark.parametrize(
    "part,key,value",
    [
        ("base", "sha", "c" * 40),
        ("head", "sha", "c" * 40),
        ("base", "ref", "feature"),
        ("head", "ref", "../unsafe"),
        ("head", "sha", "short"),
    ],
)
def test_changed_or_invalid_pr_binding_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, part: str, key: str, value: str
) -> None:
    pr = _pr()
    pr[part][key] = value
    payload, metadata = _run(monkeypatch, tmp_path, pr, [[]])
    assert any(item["subject"].endswith("API evidence") for item in payload["diagnostics"])
    assert metadata["validated_binding"] is None
    assert metadata["history"]["event_count"] is None


@pytest.mark.parametrize(
    "change",
    [
        "head",
        "before",
        "timestamp",
        "repo",
        "repository_id",
        "boolean_id",
        "negative_id",
        "duplicate",
        "page",
        "ref",
    ],
)
def test_malformed_or_ambiguous_push_observations_are_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    event = _push(H, E, 11, "1")
    if change in {"head", "before"}:
        event["payload"][change] = "short"
    elif change == "timestamp":
        event["created_at"] = "2026-10-01T11:00:00"
    elif change == "repo":
        event["repo"]["name"] = "other/repo"
    elif change == "repository_id":
        event["payload"]["repository_id"] = 10
    elif change == "boolean_id":
        event["repo"]["id"] = 1
        event["payload"]["repository_id"] = True
    elif change == "negative_id":
        event["repo"]["id"] = event["payload"]["repository_id"] = -1
    elif change == "ref":
        event["payload"]["ref"] = "refs/heads/../unsafe"
    pages = [[event, copy.deepcopy(event)]] if change == "duplicate" else [[event]]
    if change == "page":
        pages = {"message": "not pages"}
    payload, metadata = _run(monkeypatch, tmp_path, _pr(), pages)
    assert any(item["subject"].endswith("API evidence") for item in payload["diagnostics"])
    assert metadata["history"]["event_count"] is None


def test_three_full_pages_explicitly_record_the_300_event_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pages = [
        [_push(H, E, 11, str(100 * page + row + 1)) for row in range(100)] for page in range(3)
    ]
    _, metadata = _run(monkeypatch, tmp_path, _pr(), pages)
    assert metadata["history"]["cap_reached"] is True
    assert metadata["history"]["max_events"] == 300
    assert metadata["history"]["retention_days"] == 30


def test_gh_failure_still_writes_usable_unknown_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original_run = subprocess.run

    def denied(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[0] == "git":
            return original_run(args, **kwargs)
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="denied")

    monkeypatch.setattr("tools.github_pr_report.subprocess.run", denied)
    result = github_pr_report(tmp_path, REPOSITORY, 7, B, H, tmp_path / "result.json")
    assert result.exit_code == 2
    assert (tmp_path / "result.json").exists()
    assert (tmp_path / "result.check.html").exists()
    assert any("denied" in item.unknown_claim for item in result.diagnostics)


def test_ci_tolerates_unknown_collection_but_requires_usable_artifacts() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text()
    job = workflow.split("  github-order-report:\n", 1)[1].split("\n  mermaid:", 1)[0]
    setup, steps = job.split("    steps:\n", 1)
    assert "continue-on-error" not in setup
    assert "Collect GitHub order evidence (report only)" in setup
    collection, verification = steps.split("      - name: Verify report artifacts\n", 1)
    assert collection.count("continue-on-error: true") == 1
    verification = verification.split("      - name: Upload", 1)[0]
    assert "continue-on-error" not in verification and "if:" not in verification
    assert (
        "uv run --locked python -m json.tool test-artifacts/github-order/result.json >/dev/null"
        in verification
    )
    assert "test -s test-artifacts/github-order/result.check.html" in verification
