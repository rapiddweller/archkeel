# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Committed Python/Dart CLI checks with a local origin and supplied host records."""

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from archkeel.analyzer import observe
from archkeel.check.expectation import EXPECTATION_SCHEMA_VERSION, GUARDRAIL_KEYS, sha256_bytes
from archkeel.check.ratchets import measure_python_ratchets
from archkeel.check.run import observe_revision
from archkeel.cli.config import load_config
from archkeel.ir.codec import canonical_report_bytes
from archkeel.ir.digest import package_digest
from fixtures.reproduce_milestone1 import _git, _json


def run_snapshot_check(
    workspace: Path, language: Literal["python", "dart"], *, incomplete: bool = False
) -> dict:
    root = workspace / language
    root.mkdir()
    remote = workspace / f"{language}-origin.git"
    _git(workspace, "init", "--bare", "-q", str(remote))
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Snapshot fixture")
    _git(root, "remote", "add", "origin", str(remote))
    source = "src/main.py" if language == "python" else "src/main.dart"
    (root / "src").mkdir()
    text = "value = 1\n" if language == "python" else "void main() {}\n"
    (root / source).write_text(text)
    (root / "archkeel.toml").write_text(
        f'[scan]\nlanguage="{language}"\nroots=["src"]\nnamespace="src"\ncontract="contract.json"\n'
    )
    _json(root / "contract.json", {"schema_version": "2.1.0", "components": [], "rules": []})
    (root / "pyproject.toml").write_text('[project]\nrequires-python=">=3.11"\n')
    (root / "pubspec.yaml").write_text("name: src\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "accepted source")
    accepted_commit = _git(root, "rev-parse", "HEAD")
    config = load_config(root)
    accepted_result = observe_revision(
        observe, root, accepted_commit, config, declared_at=accepted_commit
    )
    assert accepted_result.exit_code == 0, accepted_result.diagnostics
    accepted = accepted_result.observation
    assert accepted is not None
    observation_digest = sha256_bytes(canonical_report_bytes(accepted))
    checker_digest = package_digest()
    lock_bytes = _json(
        root / "architecture-accepted.json",
        {
            "schema_version": "1.0.0",
            "accepted_commit": accepted_commit,
            "observation_digest": observation_digest,
            "config_digest": config.digest,
            "checker_digest": checker_digest,
            "measurements": asdict(measure_python_ratchets(accepted)),
            "approval_ref": "fixture-only:supplied-local-host-records",
        },
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "accepted lock")
    baseline = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "main")
    _git(root, "checkout", "-qb", "candidate")
    expected_bytes = _json(
        root / "expectation.json",
        {
            "schema_version": EXPECTATION_SCHEMA_VERSION,
            "evidence_class": "HYPOTHESIS",
            "accepted_digest": sha256_bytes(lock_bytes),
            "baseline_commit": baseline,
            "checker_digest": checker_digest,
            "analyzer_digest": accepted.analyzer.code_digest,
            "contract_digest": accepted.contract.digest,
            "baseline_digest": observation_digest,
            "selected_changes": [],
            "guardrails": dict.fromkeys(GUARDRAIL_KEYS, True),
        },
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "declare unchanged architecture")
    declared = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-qu", "origin", "candidate")
    candidate = "def broken(:\n" if language == "python" else "import 'missing.dart';\n"
    (root / source).write_text(
        candidate
        if incomplete
        else text + ("# comment\n" if language == "python" else "// comment\n")
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "candidate source")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "candidate")
    host = workspace / f"{language}-host.json"
    _json(
        host,
        [
            {
                "sha": declared,
                "event": "expectation_published",
                "timestamp": "2026-10-03T10:00:00Z",
            },
            {"sha": head, "event": "candidate_submitted", "timestamp": "2026-10-03T10:01:00Z"},
        ],
    )
    command = [
        sys.executable,
        "-m",
        "archkeel.cli",
        "check",
        "--root",
        str(root),
        "--baseline",
        baseline,
        "--expectation-commit",
        declared,
        "--head",
        head,
        "--expected",
        "expectation.json",
        "--expected-digest",
        sha256_bytes(expected_bytes),
        "--branch",
        "candidate",
        "--accepted-branch",
        "main",
        "--host-records",
        str(host),
        "--json",
    ]
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    (workspace / f"{language}-check.stdout.json").write_text(run.stdout)
    (workspace / f"{language}-check.stderr").write_text(run.stderr)
    return {
        "exit_code": run.returncode,
        "result": json.loads(run.stdout),
        "command": command,
        "python_version": accepted.python_version,
        "runtime": asdict(accepted.runtime) if accepted.runtime is not None else None,
        "producer": asdict(accepted.producer) if accepted.producer is not None else None,
    }


if __name__ == "__main__":
    with TemporaryDirectory(prefix="archkeel-snapshot-check-") as temporary:
        for language in ("python", "dart"):
            outcome = run_snapshot_check(Path(temporary), language)
            assert outcome["exit_code"] == 0, outcome["result"]
            print(
                json.dumps(
                    {
                        "language": language,
                        "exit_code": outcome["exit_code"],
                        "python_version": outcome["python_version"],
                        "runtime": outcome["runtime"],
                        "producer": outcome["producer"],
                    },
                    sort_keys=True,
                )
            )
