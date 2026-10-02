# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Real local Git protocol; GitHub responses and accepted-lock authorship are simulated."""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from archkeel.check.expectation import sha256_bytes
from fixtures.reproduce_milestone1 import _git, _json, reproduce
from tools.github_pr_report import CALLER, WORKER

ROOT = Path(__file__).resolve().parents[1]


def _incomparable(output: Path, source: Path, provenance: dict) -> dict:
    root, remote = output / "incomparable", output / "incomparable-origin.git"
    shutil.copytree(source, root)
    _git(output, "init", "--bare", "-q", str(remote))
    _git(root, "remote", "set-url", "origin", str(remote))
    assert _git(root, "remote", "get-url", "origin") == str(remote)
    _git(root, "checkout", "-q", "-B", "candidate", provenance["baseline"])
    expected = json.loads((source / "expectation.json").read_bytes())
    expected["analyzer_digest"] = "0" * 64
    payload = _json(root / "expectation.json", expected)
    _git(root, "add", "expectation.json")
    _git(root, "commit", "-q", "-m", "declare with incomparable analyzer")
    expectation = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "main", "candidate")
    shutil.copyfile(source / "sample/work.py", root / "sample/work.py")
    _git(root, "add", "sample/work.py")
    _git(root, "commit", "-q", "-m", "candidate refactor")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "candidate")
    records = output / "incomparable-host-records.json"
    _json(
        records,
        [
            {
                "sha": expectation,
                "event": "expectation_published",
                "timestamp": "2026-10-01T10:00:00Z",
            },
            {"sha": head, "event": "candidate_submitted", "timestamp": "2026-10-01T11:00:00Z"},
        ],
    )
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "check",
            "--root",
            str(root),
            "--baseline",
            provenance["baseline"],
            "--expectation-commit",
            expectation,
            "--head",
            head,
            "--expected",
            "expectation.json",
            "--expected-digest",
            sha256_bytes(payload),
            "--branch",
            "candidate",
            "--accepted-branch",
            "main",
            "--host-records",
            str(records),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    (output / "incomparable.stdout.json").write_text(run.stdout)
    assert run.returncode == 2, (run.stdout, run.stderr)
    result = json.loads(run.stdout)
    assert "analyzer_digest does not match" in result["diagnostics"][0]["unknown_claim"]
    return result


def _initial_pr_cases(output: Path, source: Path, provenance: dict, stub: Path) -> dict:
    results = {}
    for case in (
        "opened-expectation",
        "opened-candidate",
        "reopened",
        "wrong-run",
        "tampered",
        "incomparable",
    ):
        root = output / "incomparable" if case == "incomparable" else source
        baseline = provenance["baseline"]
        head = _git(root, "rev-parse", "HEAD")
        expectation = _git(root, "rev-parse", "HEAD^")
        fixture = output / f"simulated-{case}"
        fixture.mkdir()
        repository = {"id": 1, "full_name": "fixture/local"}
        pr = {
            "id": 11,
            "number": 7,
            "created_at": "2026-10-01T12:00:00Z",
            "base": {"sha": baseline, "ref": "main", "repo": repository},
            "head": {"sha": head, "ref": "candidate", "repo": repository},
        }
        original = copy.deepcopy(pr)
        original["head"]["sha"] = head if case == "opened-candidate" else expectation
        event = {
            "action": "reopened" if case == "reopened" else "opened",
            "number": 7,
            "repository": repository,
            "pull_request": original,
        }
        _json(fixture / "original-event.json", event)
        artifact_path = fixture / "artifact.zip"
        with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(fixture / "original-event.json", "original-event.json")
        run = {
            "id": 14 if case == "wrong-run" else 13,
            "run_attempt": 1,
            "event": "pull_request_target",
            "path": CALLER,
            "head_sha": original["head"]["sha"],
            "repository": repository,
            "head_repository": repository,
            "status": "completed",
            "conclusion": "success",
            "referenced_workflows": [
                {
                    "path": f"fixture/local/{WORKER}@{baseline}",
                    "ref": "refs/heads/main",
                    "sha": baseline,
                }
            ],
        }
        artifact = {
            "id": 17,
            "name": "initial-pr-event",
            "expired": False,
            "size_in_bytes": artifact_path.stat().st_size,
            "digest": "sha256:"
            + ("0" * 64 if case == "tampered" else sha256_bytes(artifact_path.read_bytes())),
            "workflow_run": {
                "id": 13,
                "repository_id": 1,
                "head_repository_id": 1,
                "head_sha": original["head"]["sha"],
            },
        }
        _json(fixture / "pr.json", pr)
        _json(fixture / "run.json", run)
        _json(
            fixture / "jobs.json",
            {
                "total_count": 1,
                "jobs": [
                    {
                        "id": 23,
                        "run_id": 13,
                        "run_attempt": 1,
                        "head_sha": original["head"]["sha"],
                        "status": "completed",
                        "conclusion": "success",
                    }
                ],
            },
        )
        _json(fixture / "artifacts.json", {"total_count": 1, "artifacts": [artifact]})
        endpoint = "repos/fixture/local/actions/runs/13"
        _json(
            fixture / "responses.json",
            {
                "repos/fixture/local/pulls/7": "pr.json",
                endpoint: "run.json",
                endpoint + "/attempts/1": "run.json",
                endpoint + "/attempts/1/jobs?per_page=100": "jobs.json",
                endpoint + "/artifacts?per_page=100": "artifacts.json",
                "repos/fixture/local/actions/artifacts/17/zip": "artifact.zip",
            },
        )
        result_path = output / f"{case}.json"
        run_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.github_pr_report",
                "--root",
                str(root),
                "--repository",
                "fixture/local",
                "--pull-request",
                "7",
                "--base",
                baseline,
                "--head",
                head,
                "--initial-run",
                "13",
                "--expectation-commit",
                expectation,
                "--expected-digest",
                sha256_bytes((root / "expectation.json").read_bytes()),
                "--output",
                str(result_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{stub.parent}{os.pathsep}{os.environ.get('PATH', '')}",
                "ARCHKEEL_SIMULATED_GITHUB": str(fixture),
            },
        )
        assert run_cli.returncode == (0 if case == "opened-expectation" else 2), (
            run_cli.stdout,
            run_cli.stderr,
        )
        results[case] = json.loads(result_path.read_bytes())
    return results


def reproduce_github(output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protocol = reproduce(output / "protocol", initial_pr=True)
    source = output / "protocol/C"
    provenance = json.loads((output / "protocol/C-check.stdout.json").read_bytes())["provenance"]
    baseline, expectation, head = (provenance[key] for key in ("baseline", "expectation", "head"))
    pr = {
        "number": 7,
        "created_at": "2026-10-01T12:00:00Z",
        "base": {"sha": baseline, "ref": "main", "repo": {"full_name": "fixture/local"}},
        "head": {"sha": head, "ref": "candidate", "repo": {"full_name": "fixture/local"}},
    }
    events = [
        {
            "id": str(number),
            "type": "PushEvent",
            "repo": {"id": 1, "name": "fixture/local"},
            "payload": {
                "repository_id": 1,
                "ref": "refs/heads/candidate",
                "head": sha,
                "before": before,
            },
            "created_at": timestamp,
        }
        for number, sha, before, timestamp in (
            (1, expectation, baseline, "2026-10-01T10:00:00Z"),
            (2, head, expectation, "2026-10-01T11:00:00Z"),
        )
    ]
    stub = output / "simulated-bin/gh"
    stub.parent.mkdir()
    stub.write_text(
        f"#!{sys.executable}\nimport os, pathlib, sys\n"
        "root = pathlib.Path(os.environ['ARCHKEEL_SIMULATED_GITHUB'])\n"
        "mapping = root / 'responses.json'\n"
        "name = __import__('json').loads(mapping.read_bytes())[sys.argv[-1]] if mapping.exists() "
        "else ('pr.json' if '/pulls/' in sys.argv[-1] else 'events.json')\n"
        "sys.stdout.buffer.write((root / name).read_bytes())\n"
    )
    stub.chmod(0o755)
    github = {}
    for case in ("ordered", "reversed", "missing", "ambiguous", "changed-head", "missing-lock"):
        fixture = output / f"simulated-{case}"
        fixture.mkdir()
        case_pr, case_events = copy.deepcopy(pr), copy.deepcopy(events)
        if case == "reversed":
            case_events[0]["created_at"], case_events[1]["created_at"] = (
                case_events[1]["created_at"],
                case_events[0]["created_at"],
            )
        elif case == "missing":
            case_events = []
        elif case == "ambiguous":
            case_events.append(copy.deepcopy(case_events[0]))
        elif case == "changed-head":
            case_pr["head"]["sha"] = "f" * 40
        elif case == "missing-lock":
            case_pr["base"]["sha"] = json.loads(
                (source / "architecture-accepted.json").read_bytes()
            )["accepted_commit"]
        _json(fixture / "pr.json", case_pr)
        _json(fixture / "events.json", [case_events])
        result_path = output / f"{case}.json"
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.github_pr_report",
                "--root",
                str(source),
                "--repository",
                "fixture/local",
                "--pull-request",
                "7",
                "--base",
                case_pr["base"]["sha"],
                "--head",
                head,
                "--output",
                str(result_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{stub.parent}{os.pathsep}{os.environ.get('PATH', '')}",
                "ARCHKEEL_SIMULATED_GITHUB": str(fixture),
            },
        )
        assert run.returncode == 2, (run.stdout, run.stderr)
        github[case] = json.loads(result_path.read_bytes())
    incomparable = _incomparable(output, source, provenance)
    summary = {
        "protocol": protocol,
        "github": github,
        "incomparable_analyzer": incomparable,
        "initial_pr": _initial_pr_cases(output, source, provenance, stub),
    }
    _json(output / "results.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reproduce_github(args.output)
    print(
        "Simulated opened(E) receipt: PASS; five causal controls: UNKNOWN; "
        "bounded events: UNKNOWN; local protocol A/B/C: 1/1/0. "
        f"Evidence: {args.output.resolve()}"
    )
