# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Simulated provider receipts exercise authentication; no live GitHub proof is claimed."""

import copy
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from archkeel.check.expectation import sha256_bytes
from archkeel.ir.host_records import OrderingError
from tools import github_pr_report as tool

ROOT = Path(__file__).parents[1]
CALLER = ".github/workflows/github-opened.yml"
WORKER = ".github/workflows/github-opened-receipt.yml"
REPOSITORY = "example/project"
E, H = "e" * 40, "a" * 40


def archive(event: object, entries: tuple[str, ...] = ("original-event.json",)) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for name in entries:
            # Repeated API responses must retain the original provider digest.
            output.writestr(
                zipfile.ZipInfo(name),
                json.dumps(event).encode(),
                compress_type=zipfile.ZIP_DEFLATED,
            )
    return stream.getvalue()


def test_receipt_archive_does_not_change_with_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    event = {"action": "opened"}
    monkeypatch.setattr(zipfile.time, "localtime", lambda *_: (2026, 10, 3, 0, 0, 0, 5, 276, 0))
    before = archive(event)
    monkeypatch.setattr(zipfile.time, "localtime", lambda *_: (2026, 10, 3, 0, 0, 2, 5, 276, 0))
    assert archive(event) == before
    with zipfile.ZipFile(io.BytesIO(before)) as zipped:
        assert zipped.getinfo("original-event.json").compress_type == zipfile.ZIP_DEFLATED
        assert json.loads(zipped.read("original-event.json")) == event


@pytest.fixture
def receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in (CALLER, WORKER, "tools/github_pr_report.py"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    for args in (("init", "-qb", "main"), ("add", "."), ("commit", "-qm", "collector")):
        subprocess.run(
            ["git", "-c", "user.email=test@example.invalid", "-c", "user.name=Test", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    repository = {"id": 9, "full_name": REPOSITORY}
    current = {
        "id": 11,
        "number": 7,
        "state": "open",
        "created_at": "2026-10-01T12:00:00Z",
        "base": {"sha": base, "ref": "main", "repo": repository},
        "head": {
            "sha": H,
            "ref": "candidate",
            "repo": {
                "id": 19,
                "full_name": "contributor/project",
            },
        },
    }
    original = copy.deepcopy(current)
    original["head"]["sha"] = E
    event = {"action": "opened", "number": 7, "repository": repository, "pull_request": original}
    run = {
        "id": 13,
        "run_attempt": 1,
        "event": "pull_request_target",
        "path": CALLER,
        "head_sha": E,
        "repository": repository,
        "head_repository": current["head"]["repo"],
        "status": "completed",
        "conclusion": "success",
        "referenced_workflows": [
            {
                "path": f"{REPOSITORY}/{WORKER}@{base}",
                "ref": "refs/heads/main",
                "sha": base,
            }
        ],
    }
    packet = {
        "id": 17,
        "name": "initial-pr-event",
        "expired": False,
        "workflow_run": {"id": 13, "repository_id": 9, "head_repository_id": 19, "head_sha": E},
    }
    data = {
        "root": tmp_path,
        "base": base,
        "current": current,
        "event": event,
        "run": run,
        "final_run": copy.deepcopy(run),
        "run_reads": 0,
        "attempt": copy.deepcopy(run),
        "artifacts": [packet],
        "jobs": {
            "total_count": 1,
            "jobs": [
                {
                    "id": 23,
                    "run_id": 13,
                    "run_attempt": 1,
                    "head_sha": E,
                    "status": "completed",
                    "conclusion": "success",
                }
            ],
        },
        "zip": None,
        "entries": ("original-event.json",),
    }
    original_run = subprocess.run

    def request(args: list[str], **kwargs: object):
        if args[0] == "git":
            return original_run(args, **kwargs)
        assert args[:4] == ["gh", "api", "--hostname", "github.com"]
        assert kwargs["timeout"] == 30
        endpoint = args[-1]
        blob = data["zip"] or archive(data["event"], data["entries"])
        for item in data["artifacts"]:
            item.setdefault("digest", f"sha256:{sha256_bytes(blob)}")
            item.setdefault("size_in_bytes", len(blob))
        replies = {
            f"repos/{REPOSITORY}/pulls/7": data["current"],
            f"repos/{REPOSITORY}/actions/runs/13": data["run"],
            f"repos/{REPOSITORY}/actions/runs/13/attempts/1": data["attempt"],
            f"repos/{REPOSITORY}/actions/runs/13/attempts/1/jobs?per_page=100": data["jobs"],
            f"repos/{REPOSITORY}/actions/runs/13/artifacts?per_page=100": {
                "total_count": len(data["artifacts"]),
                "artifacts": data["artifacts"],
            },
            f"repos/{REPOSITORY}/actions/artifacts/17/zip": blob,
        }
        value = replies[endpoint]
        if endpoint == f"repos/{REPOSITORY}/actions/runs/13":
            if data["run_reads"]:
                value = data["final_run"]
            data["run_reads"] += 1
        stdout = value if isinstance(value, bytes) else json.dumps(value)
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(tool.subprocess, "run", request)
    return data


def authenticate(data):
    return tool.authenticate_initial_pr(
        data["root"],
        REPOSITORY,
        7,
        data["base"],
        H,
        E,
        13,
        data["current"],
        data["root"] / "result.json",
    )


def test_original_opened_expectation_binds_a_later_same_pr_head(receipt) -> None:
    proof = authenticate(receipt)
    assert (proof.initial_sha, proof.head_sha) == (E, H)
    assert (proof.repository_id, proof.pull_request_id, proof.head_repository_id) == (9, 11, 19)
    assert (proof.run_id, proof.run_attempt, proof.artifact_id) == (13, 1, 17)
    assert proof.collector_sha == receipt["base"]
    assert proof.published_at == "2026-10-01T12:00:00Z"
    assert proof.event_digest == sha256_bytes(
        (receipt["root"] / "result.original-event.json").read_bytes()
    )


def test_rest_head_describes_the_triggering_fork_not_the_collector_commit(receipt) -> None:
    for run in (receipt["run"], receipt["attempt"]):
        run["head_sha"] = E
        run["head_repository"] = receipt["current"]["head"]["repo"]
    artifact_run = receipt["artifacts"][0]["workflow_run"]
    artifact_run["head_sha"] = E
    artifact_run["head_repository_id"] = 19
    proof = authenticate(receipt)
    assert proof.collector_sha == receipt["base"] and proof.initial_sha == E


def test_a_rerun_during_artifact_acquisition_never_authenticates_attempt_one(receipt) -> None:
    receipt["final_run"]["run_attempt"] = 2
    with pytest.raises(OrderingError):
        authenticate(receipt)


def test_consumer_baseline_does_not_vendor_the_external_pinned_reader(receipt) -> None:
    root = receipt["root"]
    subprocess.run(
        ["git", "rm", "tools/github_pr_report.py"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=Test",
            "commit",
            "-qm",
            "consumer only owns collector source",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    receipt["base"] = base
    receipt["current"]["base"]["sha"] = base
    receipt["event"]["pull_request"]["base"]["sha"] = base
    for run in (receipt["run"], receipt["attempt"]):
        run["referenced_workflows"][0]["sha"] = base
        run["referenced_workflows"][0]["path"] = f"{REPOSITORY}/{WORKER}@{base}"
    proof = authenticate(receipt)
    assert proof.collector_sha == base


def test_receipt_authentication_errors_render_a_usable_unknown(receipt) -> None:
    receipt["event"]["action"] = "reopened"
    output = receipt["root"] / "report.json"
    result = tool.github_pr_report(
        receipt["root"],
        REPOSITORY,
        7,
        receipt["base"],
        H,
        output,
        expectation=E,
        initial_run=13,
        expected_path="expectation.json",
        expected_digest="f" * 64,
    )
    assert result.exit_code == 2 and result.host_order is None
    assert result.provenance is None
    assert "original PR opened event" in output.read_text()
    assert "NOT CHECKED" in output.with_suffix(".check.html").read_text()
    metadata = json.loads(output.with_suffix(".github.json").read_text())
    assert metadata["initial_receipt"] == {"run_id": 13, "authenticated": False}
    assert "history" not in metadata
    jobs_path = output.with_suffix(".jobs.json")
    assert metadata["raw_sha256"][jobs_path.name] == sha256_bytes(jobs_path.read_bytes())


@pytest.mark.parametrize(
    "change",
    [
        "skipped-worker-and-uploader",
        "truncated",
        "missing",
        "boolean-count",
        "skipped",
        "failed",
        "incomplete",
        "wrong-run",
        "wrong-attempt",
        "wrong-head",
        "boolean-id",
    ],
)
def test_only_the_complete_sole_successful_worker_can_have_produced_the_receipt(
    receipt, change
) -> None:
    listing = receipt["jobs"]
    job = listing["jobs"][0]
    if change == "skipped-worker-and-uploader":
        worker = copy.deepcopy(job)
        worker.update(id=24, conclusion="skipped", steps=[])
        listing.update(total_count=2, jobs=[job, worker])
    elif change == "truncated":
        listing["total_count"] = 2
    elif change == "missing":
        listing.update(total_count=0, jobs=[])
    elif change == "boolean-count":
        listing["total_count"] = True
    elif change in {"skipped", "failed"}:
        job["conclusion"] = "skipped" if change == "skipped" else "failure"
    elif change == "incomplete":
        job["status"] = "in_progress"
    elif change == "wrong-run":
        job["run_id"] = 14
    elif change == "wrong-attempt":
        job["run_attempt"] = 2
    elif change == "wrong-head":
        job["head_sha"] = H
    else:
        job["id"] = True
    with pytest.raises(OrderingError):
        authenticate(receipt)


@pytest.mark.parametrize(
    "change",
    [
        "reopened",
        "initial-head",
        "current-head",
        "pr-id",
        "pr-created",
        "repo-id",
        "head-repo",
        "run-id",
        "run-attempt",
        "run-event",
        "run-head",
        "run-path",
        "run-repository",
        "run-head-repository",
        "worker-sha",
        "worker-path",
        "worker-ref",
        "worker-duplicate",
        "worker-missing",
        "artifact-run",
        "artifact-repository",
        "artifact-head",
        "artifact-head-repository",
        "artifact-digest",
        "artifact-expired",
        "artifact-missing",
        "artifact-duplicate",
        "artifact-size",
        "zip-entry",
        "zip-duplicate",
        "zip-invalid",
        "zip-corrupt-data",
        "zip-oversized",
        "base-id-missing",
        "collector-changed",
    ],
)
def test_untrusted_or_wrong_scope_receipts_never_become_order_proof(receipt, change) -> None:
    data = receipt
    event, run, attempt = data["event"], data["run"], data["attempt"]
    item = data["artifacts"][0]
    if change == "reopened":
        event["action"] = "reopened"
    elif change == "initial-head":
        event["pull_request"]["head"]["sha"] = H
    elif change == "current-head":
        data["current"]["head"]["sha"] = E
    elif change == "pr-id":
        event["pull_request"]["id"] = 12
    elif change == "pr-created":
        event["pull_request"]["created_at"] = "2026-10-01T12:00:01Z"
    elif change == "repo-id":
        event["repository"]["id"] = True
    elif change == "head-repo":
        event["pull_request"]["head"]["repo"]["id"] = 20
    elif change == "run-id":
        run["id"] = 14
    elif change == "run-attempt":
        run["run_attempt"] = 2
    elif change == "run-event":
        run["event"] = "pull_request"
    elif change == "run-head":
        run["head_sha"] = data["base"]
    elif change == "run-path":
        run["path"] = ".github/workflows/other.yml"
    elif change == "run-repository":
        run["repository"] = {"id": 10, "full_name": "other/project"}
    elif change == "run-head-repository":
        run["head_repository"] = {"id": 20, "full_name": "other/project"}
    elif change == "worker-sha":
        attempt["referenced_workflows"][0]["sha"] = E
    elif change == "worker-path":
        attempt["referenced_workflows"][0]["path"] = "other/project/work.yml@refs/heads/main"
    elif change == "worker-ref":
        attempt["referenced_workflows"][0]["ref"] = "refs/heads/candidate"
    elif change == "worker-duplicate":
        attempt["referenced_workflows"] *= 2
    elif change == "worker-missing":
        attempt["referenced_workflows"] = []
    elif change == "artifact-run":
        item["workflow_run"]["id"] = 14
    elif change == "artifact-repository":
        item["workflow_run"]["repository_id"] = 10
    elif change == "artifact-head":
        item["workflow_run"]["head_sha"] = data["base"]
    elif change == "artifact-head-repository":
        item["workflow_run"]["head_repository_id"] = 20
    elif change == "artifact-digest":
        item["digest"] = "sha256:" + "0" * 64
    elif change == "artifact-expired":
        item["expired"] = True
    elif change == "artifact-missing":
        data["artifacts"] = []
    elif change == "artifact-duplicate":
        data["artifacts"].append(copy.deepcopy(item))
    elif change == "artifact-size":
        item["size_in_bytes"] = 10**9
    elif change == "zip-entry":
        data["entries"] = ("../original-event.json",)
    elif change == "zip-duplicate":
        data["entries"] *= 2
    elif change == "zip-invalid":
        data["zip"] = b"invalid zip"
    elif change == "zip-corrupt-data":
        blob = archive(event)
        with zipfile.ZipFile(io.BytesIO(blob)) as zipped:
            entry = zipped.infolist()[0]
        start = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        data["zip"] = (
            blob[:start] + b"\xff" * entry.compress_size + blob[start + entry.compress_size :]
        )
    elif change == "zip-oversized":
        event["pull_request"]["body"] = "x" * tool.EVIDENCE_LIMIT
    elif change == "base-id-missing":
        del data["current"]["base"]["repo"]["id"]
    else:
        path = WORKER
        subprocess.run(["git", "checkout", "-qb", "changed"], cwd=data["root"], check=True)
        (data["root"] / path).write_bytes((data["root"] / path).read_bytes() + b"\n")
        subprocess.run(["git", "add", path], cwd=data["root"], check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "user.name=Test",
                "commit",
                "-qm",
                "change collector",
            ],
            cwd=data["root"],
            check=True,
        )
        data["base"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=data["root"], text=True
        ).strip()
    with pytest.raises((OrderingError, ValueError)):
        authenticate(data)
