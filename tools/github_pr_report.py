# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Save bounded GitHub observations and an explicit, report-only UNKNOWN check."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

from archkeel.check.expectation import sha256_bytes
from archkeel.check.git import git_bytes, read_blob
from archkeel.check.report import render_result, unknown_result
from archkeel.ir.codec import decode_json, parse_lock
from archkeel.ir.host_records import OrderingError, parse_timestamp, validate_sha
from archkeel.ir.lock import LOCK_PATH, LockError
from archkeel.ir.model import Diagnostic, RunResult
from archkeel.render.html import render_check_html

HISTORY_LIMIT = (
    "Recent GitHub events do not prove first publication: history retains at most 300 events "
    "for 30 days and can arrive 30 seconds to 6 hours late."
)


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
    output.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise OrderingError(f"GitHub request failed: {result.stderr.strip() or 'unknown error'}")
    return decode_json(result.stdout)


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
    root: Path, repository: str, number: int, base: str, head: str, output: Path
) -> RunResult:
    output.parent.mkdir(parents=True, exist_ok=True)
    pr_path, events_path = (
        output.with_suffix(".pull-request.json"),
        output.with_suffix(".events.json"),
    )
    for path in (pr_path, events_path):
        path.unlink(missing_ok=True)
    diagnostics: list[Diagnostic] = []
    binding, count = None, None
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
    metadata = {
        "host": "github.com",
        "requested_binding": {
            "repository": repository,
            "pull_request": number,
            "base": base,
            "head": head,
        },
        "validated_binding": binding,
        "raw_sha256": {
            path.name: sha256_bytes(path.read_bytes())
            for path in (pr_path, events_path)
            if path.exists()
        },
        "history": {
            "event_count": count,
            "max_events": 300,
            "retention_days": 30,
            "cap_reached": count == 300 if count is not None else None,
            "first_publication_proven": False,
            "limit": HISTORY_LIMIT,
        },
    }
    output.with_suffix(".github.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    result = replace(
        unknown_result("check", "GitHub publication history", OrderingError(HISTORY_LIMIT)),
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
    args = parser.parse_args()
    result = github_pr_report(
        args.root, args.repository, args.pull_request, args.base, args.head, args.output
    )
    print(render_result(result).decode(), end="")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
