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
from pathlib import Path

from archkeel.check.expectation import sha256_bytes
from fixtures.reproduce_milestone1 import _git, _json, reproduce

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


def reproduce_github(output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protocol = reproduce(output / "protocol")
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
        "name = 'pr.json' if '/pulls/' in sys.argv[-1] else 'events.json'\n"
        "root = pathlib.Path(os.environ['ARCHKEEL_SIMULATED_GITHUB'])\n"
        "print((root / name).read_text(), end='')\n"
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
    summary = {
        "protocol": protocol,
        "github": github,
        "incomparable_analyzer": _incomparable(output, source, provenance),
    }
    _json(output / "results.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reproduce_github(args.output)
    print(
        "Synthetic GitHub observations stay UNKNOWN; local protocol A/B/C: 1/1/0. "
        f"Evidence: {args.output.resolve()}"
    )
