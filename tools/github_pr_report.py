# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check an authenticated initial PR receipt, or report bounded observations as UNKNOWN."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import zipfile
import zlib
from dataclasses import replace
from pathlib import Path

from archkeel.analyzer import observe
from archkeel.check.expectation import sha256_bytes
from archkeel.check.git import git_bytes, read_blob
from archkeel.check.report import render_result, unknown_result
from archkeel.check.run import run_check
from archkeel.cli.config import load_check_config
from archkeel.ir.codec import decode_json, parse_lock
from archkeel.ir.host_records import (
    InitialPRHeadEvidence,
    OrderingError,
    parse_timestamp,
    validate_sha,
)
from archkeel.ir.lock import LOCK_PATH, LockError
from archkeel.ir.model import Diagnostic, RunResult
from archkeel.render.html import render_check_html

HISTORY_LIMIT = (
    "Recent GitHub events do not prove first publication: history retains at most 300 events "
    "for 30 days and can arrive 30 seconds to 6 hours late."
)
EVIDENCE_LIMIT = 1024 * 1024
CALLER = ".github/workflows/github-opened.yml"
WORKER = ".github/workflows/github-opened-receipt.yml"
# AD-143: these reviewed bytes, not arbitrary workflow names, define the receipt producer.
COLLECTOR_DIGESTS = {
    CALLER: "8431d541a0aede29149d3a0dd2e725b5d8911f17ac570c1dc279dabce01e5b45",
    WORKER: "8627b15f0f7b1438a71d15ad051d10b9352aa00475aa2c2e5566d1a666b1e79a",
}


def _repository(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", value, re.ASCII):
        raise OrderingError("GitHub repository must be owner/name")
    if any(part in {".", ".."} for part in value.split("/")):
        raise OrderingError("GitHub repository must be owner/name")
    return value


def _request(root: Path, endpoint: str, output: Path, *, pages: bool = False) -> object:
    args = ["gh", "api", "--hostname", "github.com", "-H", "Accept: application/vnd.github+json"]
    if pages:
        args.extend(("--paginate", "--slurp"))
    result = subprocess.run(args + [endpoint], cwd=root, capture_output=True, text=True, timeout=30)
    if len(result.stdout.encode()) > EVIDENCE_LIMIT:
        raise OrderingError("GitHub API evidence exceeds the one MiB receipt limit")
    output.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise OrderingError(f"GitHub request failed: {result.stderr.strip() or 'unknown error'}")
    return decode_json(result.stdout)


def _object(raw: object, label: str) -> dict[str, object]:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise OrderingError(f"GitHub {label} must be an object")
    return raw


def _id(raw: object) -> int:
    if type(raw) is not int or raw < 1:
        raise OrderingError("GitHub provider IDs must be positive integers")
    return raw


def _repo(raw: object, repository: str, identifier: int) -> None:
    data = _object(raw, "repository")
    if _repository(data.get("full_name")) != repository or _id(data.get("id")) != identifier:
        raise OrderingError("GitHub repository identity does not match")


def _collector(root: Path, base: str) -> None:
    for path, digest in COLLECTOR_DIGESTS.items():
        if sha256_bytes(read_blob(root, base, path)) != digest:
            raise OrderingError("GitHub collector source differs from the reviewed producer")


def _run_binding(
    raw: object,
    repository: str,
    repository_id: int,
    run_id: int,
    initial: str,
    head_repository: str,
    head_repository_id: int,
) -> dict[str, object]:
    run = _object(raw, "workflow run")
    _repo(run.get("repository"), repository, repository_id)
    _repo(run.get("head_repository"), head_repository, head_repository_id)
    if (
        _id(run.get("id")) != run_id
        or type(run.get("run_attempt")) is not int
        or run["run_attempt"] != 1
        or run.get("event") != "pull_request_target"
        or run.get("head_sha") != initial
        or run.get("path") != CALLER
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        raise OrderingError("GitHub run is not the original accepted collector execution")
    return run


def _worker_binding(run: dict[str, object], repository: str, base: str) -> None:
    references = run.get("referenced_workflows")
    if not isinstance(references, list) or len(references) != 1:
        raise OrderingError("GitHub run must reference exactly the trusted receipt worker")
    reference = _object(references[0], "referenced workflow")
    if reference != {
        "path": f"{repository}/{WORKER}@{base}",
        "ref": "refs/heads/main",
        "sha": base,
    }:
        raise OrderingError("GitHub referenced worker source is not the accepted baseline")


def _sole_worker(raw: object, run_id: int, initial: str) -> None:
    listing = _object(raw, "attempt jobs")
    jobs = listing.get("jobs")
    # AD-143: a skipped trusted worker plus another uploader must still count as two jobs.
    if (
        type(listing.get("total_count")) is not int
        or listing["total_count"] != 1
        or not isinstance(jobs, list)
        or len(jobs) != 1
    ):
        raise OrderingError("GitHub receipt requires the complete sole-worker job list")
    job = _object(jobs[0], "producer job")
    _id(job.get("id"))
    if (
        _id(job.get("run_id")) != run_id
        or type(job.get("run_attempt")) is not int
        or job["run_attempt"] != 1
        or job.get("head_sha") != initial
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
    ):
        raise OrderingError("GitHub sole producer job did not complete the original run")


def _artifact(
    raw: object,
    repository_id: int,
    run_id: int,
    initial: str,
    head_repository_id: int,
) -> dict[str, object]:
    listing = _object(raw, "artifacts")
    entries = listing.get("artifacts")
    if (
        type(listing.get("total_count")) is not int
        or listing["total_count"] != 1
        or not isinstance(entries, list)
        or len(entries) != 1
    ):
        raise OrderingError("GitHub initial event artifact is missing or duplicated")
    artifact = _object(entries[0], "artifact")
    _id(artifact.get("id"))
    run = _object(artifact.get("workflow_run"), "artifact run")
    if (
        artifact.get("name") != "initial-pr-event"
        or artifact.get("expired") is not False
        or _id(run.get("id")) != run_id
        or _id(run.get("repository_id")) != repository_id
        or _id(run.get("head_repository_id")) != head_repository_id
        or run.get("head_sha") != initial
    ):
        raise OrderingError("GitHub artifact does not bind the accepted collector run")
    size = artifact.get("size_in_bytes")
    if type(size) is not int or not 0 < size <= EVIDENCE_LIMIT:
        raise OrderingError("GitHub event artifact exceeds the one MiB receipt limit")
    return artifact


def _original_event(
    root: Path, repository: str, artifact: dict[str, object], output: Path
) -> tuple[object, str, str]:
    identifier = _id(artifact["id"])
    result = subprocess.run(
        [
            "gh",
            "api",
            "--hostname",
            "github.com",
            f"repos/{repository}/actions/artifacts/{identifier}/zip",
        ],
        cwd=root,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise OrderingError("GitHub initial event artifact could not be downloaded")
    blob = result.stdout
    digest = sha256_bytes(blob)
    if not 0 < len(blob) <= EVIDENCE_LIMIT or artifact.get("digest") != f"sha256:{digest}":
        raise OrderingError("GitHub artifact bytes do not match their provider digest")
    output.with_suffix(".artifact.zip").write_bytes(blob)
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            entries = archive.infolist()
            if (
                len(entries) != 1
                or entries[0].filename != "original-event.json"
                or not 0 < entries[0].file_size <= EVIDENCE_LIMIT
            ):
                raise OrderingError(
                    "GitHub receipt archive must contain only the bounded original event"
                )
            event = archive.read(entries[0])
    except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError) as error:
        raise OrderingError(f"GitHub receipt archive is invalid: {error}") from error
    output.with_suffix(".original-event.json").write_bytes(event)
    return decode_json(event), digest, sha256_bytes(event)


def authenticate_initial_pr(
    root: Path,
    repository: str,
    number: int,
    base: str,
    head: str,
    expectation: str,
    run_id: int,
    current: object,
    output: Path,
) -> InitialPRHeadEvidence:
    repository = _repository(repository)
    _id(number)
    _id(run_id)
    validate_sha(base, "base")
    validate_sha(head, "head")
    validate_sha(expectation, "expectation")
    head_repository, head_ref = _binding(root, current, repository, number, base, head)
    pr = _object(current, "pull request")
    repository_id = _id(_object(_object(pr["base"], "base")["repo"], "base repository").get("id"))
    head_repository_id = _id(
        _object(_object(pr["head"], "head")["repo"], "head repository").get("id")
    )
    pull_request_id = _id(pr.get("id"))
    _collector(root, base)
    endpoint = f"repos/{repository}/actions/runs/{run_id}"
    for suffix, target in (("", ".run.json"), ("/attempts/1", ".attempt.json")):
        run = _run_binding(
            _request(root, endpoint + suffix, output.with_suffix(target)),
            repository,
            repository_id,
            run_id,
            expectation,
            head_repository,
            head_repository_id,
        )
        if suffix:
            _worker_binding(run, repository, base)
    _sole_worker(
        _request(
            root, endpoint + "/attempts/1/jobs?per_page=100", output.with_suffix(".jobs.json")
        ),
        run_id,
        expectation,
    )
    artifact = _artifact(
        _request(root, endpoint + "/artifacts?per_page=100", output.with_suffix(".artifacts.json")),
        repository_id,
        run_id,
        expectation,
        head_repository_id,
    )
    raw, artifact_digest, event_digest = _original_event(root, repository, artifact, output)
    _run_binding(
        _request(root, endpoint, output.with_suffix(".run-final.json")),
        repository,
        repository_id,
        run_id,
        expectation,
        head_repository,
        head_repository_id,
    )
    event = _object(raw, "original event")
    _repo(event.get("repository"), repository, repository_id)
    if event.get("action") != "opened" or _id(event.get("number")) != number:
        raise OrderingError("GitHub receipt is not the original PR opened event")
    original = _object(event.get("pull_request"), "original pull request")
    initial_repository, initial_ref = _binding(
        root, original, repository, number, base, expectation
    )
    original_head = _object(original["head"], "original head")
    original_base = _object(original["base"], "original base")
    _repo(original_base.get("repo"), repository, repository_id)
    _repo(original_head.get("repo"), head_repository, head_repository_id)
    if (
        _id(original.get("id")) != pull_request_id
        or original.get("created_at") != pr.get("created_at")
        or initial_repository != head_repository
        or initial_ref != head_ref
    ):
        raise OrderingError("GitHub initial and current heads do not belong to the same PR")
    published = original["created_at"]
    if not isinstance(published, str):
        raise OrderingError("GitHub original PR creation timestamp is missing")
    return InitialPRHeadEvidence(
        repository,
        repository_id,
        number,
        pull_request_id,
        head_repository_id,
        expectation,
        head,
        published,
        base,
        run_id,
        _id(artifact["id"]),
        artifact_digest,
        event_digest,
    )


def _binding(
    root: Path, raw: object, repository: str, number: int, base: str, head: str
) -> tuple[str, str]:
    if not isinstance(raw, dict) or type(raw.get("number")) is not int or raw["number"] != number:
        raise OrderingError("GitHub pull request number does not match")
    parse_timestamp(raw.get("created_at"))
    for side, sha in (("base", base), ("head", head)):
        part = raw.get(side)
        if not isinstance(part, dict) or validate_sha(part.get("sha"), side) != sha:
            raise OrderingError(f"GitHub pull request {side} SHA does not match the run")
        repo = part.get("repo")
        if not isinstance(repo, dict):
            raise OrderingError(f"GitHub pull request {side} repository is missing")
        _repository(repo.get("full_name"))
        ref = part.get("ref")
        if not isinstance(ref, str) or not ref:
            raise OrderingError(f"GitHub pull request {side} ref is missing")
        git_bytes(root, "check-ref-format", f"refs/heads/{ref}")
    if raw["base"]["repo"]["full_name"] != repository or raw["base"]["ref"] != "main":
        raise OrderingError("GitHub pull request must target the supplied repository's main")
    return _repository(raw["head"]["repo"]["full_name"]), f"refs/heads/{raw['head']['ref']}"


def _events(root: Path, raw: object, repository: str) -> int:
    if not isinstance(raw, list) or len(raw) > 3:
        raise OrderingError("GitHub events must contain at most three pages")
    seen: set[str] = set()
    count = 0
    for page in raw:
        if not isinstance(page, list) or len(page) > 100:
            raise OrderingError("GitHub events page is invalid")
        for event in page:
            count += 1
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise OrderingError("GitHub event is invalid")
            identifier = event.get("id")
            if not isinstance(identifier, str) or not identifier.isdecimal() or identifier in seen:
                raise OrderingError("GitHub event ID is invalid or duplicated across pages")
            seen.add(identifier)
            repo = event.get("repo")
            if not isinstance(repo, dict) or repo.get("name") != repository:
                raise OrderingError("GitHub event repository does not match")
            parse_timestamp(event.get("created_at"))
            if event["type"] != "PushEvent":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict) or type(repo.get("id")) is not int or repo["id"] < 1:
                raise OrderingError("GitHub push payload is invalid")
            if (
                type(payload.get("repository_id")) is not int
                or payload["repository_id"] != repo["id"]
            ):
                raise OrderingError("GitHub push repository ID does not match")
            validate_sha(payload.get("head"), "GitHub push head")
            validate_sha(payload.get("before"), "GitHub push before")
            ref = payload.get("ref")
            if not isinstance(ref, str) or not ref.startswith("refs/"):
                raise OrderingError("GitHub push ref is invalid")
            git_bytes(root, "check-ref-format", ref)
    return count


def github_pr_report(
    root: Path,
    repository: str,
    number: int,
    base: str,
    head: str,
    output: Path,
    *,
    expectation: str | None = None,
    initial_run: int | None = None,
    expected_path: str = "expectation.json",
    expected_digest: str | None = None,
) -> RunResult:
    output.parent.mkdir(parents=True, exist_ok=True)
    pr_path, events_path = (
        output.with_suffix(".pull-request.json"),
        output.with_suffix(".events.json"),
    )
    evidence_paths = (
        pr_path,
        events_path,
        *(
            output.with_suffix(suffix)
            for suffix in (
                ".run.json",
                ".run-final.json",
                ".attempt.json",
                ".jobs.json",
                ".artifacts.json",
                ".artifact.zip",
                ".original-event.json",
            )
        ),
    )
    for path in evidence_paths:
        path.unlink(missing_ok=True)
    diagnostics: list[Diagnostic] = []
    binding, count = None, None
    result = None
    proof = None
    initial_mode = any(value is not None for value in (initial_run, expectation, expected_digest))
    try:
        repository = _repository(repository)
        validate_sha(base, "base")
        validate_sha(head, "head")
        if type(number) is not int or number < 1:
            raise OrderingError("GitHub pull request number must be positive")
        raw = _request(root, f"repos/{repository}/pulls/{number}", pr_path)
        head_repository, head_ref = _binding(root, raw, repository, number, base, head)
        binding = {
            "repository": repository,
            "pull_request": number,
            "base": base,
            "head": head,
            "head_repository": head_repository,
            "head_ref": head_ref,
        }
        if initial_mode:
            if initial_run is None or expectation is None or expected_digest is None:
                raise OrderingError("initial PR mode needs run, expectation and expected digest")
            proof = authenticate_initial_pr(
                root,
                repository,
                number,
                base,
                head,
                expectation,
                initial_run,
                raw,
                output,
            )
            result = run_check(
                root,
                config=load_check_config(root, base, head),
                baseline=base,
                expectation_commit=expectation,
                head=head,
                expected_path=expected_path,
                expected_digest=expected_digest,
                branch=head_ref.removeprefix("refs/heads/"),
                accepted_branch="main",
                host_records_path=None,
                environ=os.environ,
                host=lambda *_args, **_kwargs: proof,
                analyzer=observe,
            )
        else:
            raw = _request(
                root, f"repos/{head_repository}/events?per_page=100", events_path, pages=True
            )
            count = _events(root, raw, head_repository)
            diagnostics.append(
                Diagnostic(
                    "parse_error",
                    f"GitHub {repository} PR #{number} publication history",
                    HISTORY_LIMIT,
                    "Review the observations; supply authenticated complete history before gating.",
                )
            )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        diagnostics.append(
            Diagnostic(
                "parse_error",
                f"GitHub {repository} PR #{number} API evidence",
                str(error),
                "Check gh authentication, PR binding and saved API responses, then retry.",
            )
        )
    try:
        parse_lock(read_blob(root, validate_sha(base, "base"), LOCK_PATH))
    except (OSError, ValueError) as error:
        diagnostics.append(LockError(str(error)).diagnostic)
    metadata: dict[str, object] = {
        "host": "github.com",
        "requested_binding": {
            "repository": repository,
            "pull_request": number,
            "base": base,
            "head": head,
        },
        "validated_binding": binding,
        "raw_sha256": {
            path.name: sha256_bytes(path.read_bytes()) for path in evidence_paths if path.exists()
        },
    }
    if initial_mode:
        metadata["initial_receipt"] = {"run_id": initial_run, "authenticated": proof is not None}
    else:
        metadata["history"] = {
            "event_count": count,
            "max_events": 300,
            "retention_days": 30,
            "cap_reached": count == 300 if count is not None else None,
            "first_publication_proven": False,
            "limit": HISTORY_LIMIT,
        }
    output.with_suffix(".github.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    if result is None:
        result = replace(
            unknown_result("check", "GitHub order evidence", OrderingError(HISTORY_LIMIT)),
            diagnostics=tuple(diagnostics),
        )
    output.write_bytes(render_result(result))
    output.with_suffix(".check.html").write_bytes(
        render_check_html(result, repository=repository, result_href=output.name)
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial-run", type=int)
    parser.add_argument("--expectation-commit")
    parser.add_argument("--expected", default="expectation.json")
    parser.add_argument("--expected-digest")
    args = parser.parse_args()
    result = github_pr_report(
        args.root,
        args.repository,
        args.pull_request,
        args.base,
        args.head,
        args.output,
        expectation=args.expectation_commit,
        initial_run=args.initial_run,
        expected_path=args.expected,
        expected_digest=args.expected_digest,
    )
    print(render_result(result).decode(), end="")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
