# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Store view-spec stories and check each step against the selected snapshot."""

import ast
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .cli.core_output import write_new_at
from .explorer_store import open_snapshot
from .explorer_story_external import _external
from .explorer_story_spec import _ID, _validate

_LIMIT = 1_000_000


def _checked_folder(root: Path, create: bool) -> Path | None:
    folder = root
    for name in (".archkeel", "stories"):
        folder = folder / name
        if folder.is_symlink():
            raise ValueError("story directory cannot be a link or junction")
        if create:
            folder.mkdir(exist_ok=True)
        if not folder.exists():
            return None
        if not folder.is_dir() or folder.resolve() != folder:
            raise ValueError("story directory cannot be a link or junction")
    return folder


@contextmanager
def _folder(root: Path, *, create: bool) -> Iterator[int | Path | None]:
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        yield _checked_folder(root, create)
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    try:
        for name in (".archkeel", "stories"):
            if create:
                try:
                    os.mkdir(name, dir_fd=descriptor)
                except FileExistsError:
                    pass
            try:
                child = os.open(name, flags, dir_fd=descriptor)
            except FileNotFoundError:
                yield None
                return
            except OSError as error:
                raise ValueError("story directory cannot be a link or non-directory") from error
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _identity(db: Any, root: Path) -> tuple[dict[str, str], Any]:
    stored, coverage = db.execute("SELECT root,coverage FROM analysis").fetchone()
    if Path(stored) != root.resolve():
        raise ValueError("snapshot belongs to another repository")
    identity = db.execute("SELECT source,contract FROM snapshot WHERE complete=1").fetchone()
    return {"source_digest": identity[0], "contract_digest": identity[1]}, json.loads(coverage)


def _location(db: Any, root: Path, reference: object) -> dict[str, Any] | None:
    if not isinstance(reference, str):
        return None
    row = db.execute("SELECT path,line,digest FROM location WHERE id=?", (reference,)).fetchone()
    if row is None or not row[2]:
        return None
    relative = Path(row[0])
    path = root / relative
    if relative.is_absolute() or ".." in relative.parts or path.resolve() != root / relative:
        return None
    try:
        flags = os.O_RDONLY
        if os.name != "nt":
            flags |= os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(path, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return None
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
            if (
                (before.st_mtime_ns, before.st_ctime_ns, before.st_size)
                != (after.st_mtime_ns, after.st_ctime_ns, after.st_size)
                or digest != row[2]
                or path.resolve() != path
            ):
                return None
    except OSError:
        return None
    return {"path": row[0], "line": row[1], "reference": reference}


def _module(db: Any, parent: str) -> tuple[str, str] | None:
    seen: set[str] = set()
    while parent and parent != "system" and parent not in seen and len(seen) < 32:
        seen.add(parent)
        row = db.execute("SELECT name,kind,parent FROM element WHERE id=?", (parent,)).fetchone()
        if row is None:
            break
        if row[1] == "module":
            return parent, str(row[0])
        parent = row[2]
    return None


def _call_evidence(db: Any, root: Path, source: str, target: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for relation in db.execute(
        "SELECT body FROM relation WHERE source=? AND target=? AND kind='call'", (source, target)
    ):
        data = json.loads(relation[0])
        if data.get("resolution") != "resolved":
            continue
        sites = [
            _location(db, root, site.get("reference"))
            for site in data.get("evidence", [])
            if site.get("role") != "declaration"
        ]
        if sites and all(sites):
            evidence.extend(site for site in sites if site is not None)
    return evidence


def _pipe_site(root: Path, site: dict[str, Any], transition: str) -> bool:
    try:
        source = root / site["path"]
        if source.stat().st_size > 2_000_000:
            return False
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno != site["line"]:
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "run":
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "subprocess":
            continue
        if transition == "process_request":
            return any(
                arg.arg == "input"
                and not (isinstance(arg.value, ast.Constant) and arg.value.value is None)
                for arg in node.keywords
            )
        return any(
            arg.arg == "capture_output"
            and isinstance(arg.value, ast.Constant)
            and arg.value.value is True
            for arg in node.keywords
        )
    return False


def _process_evidence(db: Any, root: Path, function: str, transition: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for relation in db.execute(
        "SELECT body FROM relation WHERE source=? AND kind='call'", (function,)
    ):
        data = json.loads(relation[0])
        if data.get("expression") != "subprocess.run":
            continue
        for item in data.get("evidence", []):
            reference = item.get("reference")
            if (site := _location(db, root, reference)) and _pipe_site(root, site, transition):
                if _location(db, root, reference) is not None:
                    evidence.append(site)
    return evidence


def _step_evidence(
    db: Any,
    root: Path,
    step: dict[str, Any],
    node: Any,
    location: dict[str, Any] | None,
    previous: str | None,
    first: bool,
) -> tuple[str, str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    transition = step.get("transition", "call")
    status, reason = "unknown", "Definition or call evidence is unavailable."
    if node and location and previous is None and first:
        status, reason = "proven", "The definition is present in the snapshot."
    elif step.get("claim"):
        status, reason = "claim", "The author claims this step."
    elif transition == "return" and node and location and previous:
        evidence = _call_evidence(db, root, node[0], previous)
        reason = (
            "The caller-to-callee call is recorded; the runtime return is not observed."
            if evidence
            else "The caller-to-callee call and runtime return are not verified."
        )
    elif transition in ("process_request", "process_response") and node and location and previous:
        function = previous if transition == "process_request" else node[0]
        evidence = _process_evidence(db, root, function, transition)
        reason = (
            "The source passes subprocess input; the process target and runtime are unverified."
            if evidence and transition == "process_request"
            else "The source captures subprocess output; its target and runtime are unverified."
            if evidence
            else "The subprocess boundary and runtime are not fully resolved."
        )
    elif step.get("kind") not in (None, "calls"):
        reason = "This relationship kind is not checked by the Explorer."
    elif node and location and previous and step.get("kind") in (None, "calls"):
        evidence = _call_evidence(db, root, previous, node[0])
        if evidence:
            status, reason = "proven", "The snapshot records a resolved call."
    return status, reason, evidence


def _check(db: Any, root: Path, snapshot: Path, spec: dict[str, Any]) -> dict[str, Any]:
    identity, coverage = _identity(db, root)
    checked: list[dict[str, Any]] = []
    previous = None
    for step in spec.get("steps", []):
        rows = db.execute(
            "SELECT id,parent,body FROM element "
            "WHERE name=? AND kind IN ('function','method') LIMIT 2",
            (step["node"],),
        ).fetchall()
        node = rows[0] if len(rows) == 1 else None
        body = json.loads(node[2]) if node else {}
        location = _location(db, root, body.get("source"))
        module = _module(db, node[1]) if node else None
        transition = step.get("transition", "call")
        status, reason, evidence = _step_evidence(
            db, root, step, node, location, previous, not checked
        )
        checked.append(
            {
                "node": step["node"],
                "title": step.get("title"),
                "note": step.get("note"),
                "question": step.get("question"),
                "text_status": "claim",
                "transition": transition,
                "chapter": step.get("chapter"),
                "external": _external(
                    db,
                    root,
                    module[0] if module else None,
                    node[0] if node else None,
                    step.get("external", []),
                    location,
                    lambda ref: _location(db, root, ref),
                ),
                "lane": module[1] if module else None,
                "function": step["node"].rsplit(".", 1)[-1],
                "defined_at": location,
                "status": status,
                "reason": reason,
                "evidence": evidence,
            }
        )
        previous = node[0] if node and location else None
    story = spec["story"]
    return {
        "id": story["id"],
        "title": story["title"],
        "chapters": story.get("chapters", []),
        "snapshot": snapshot.stem,
        "coverage": coverage,
        "rebound": spec["snapshot"] != identity,
        "steps": checked,
    }


def _read_spec(root: Path, story_id: str) -> dict[str, Any]:
    if not isinstance(story_id, str) or not _ID.fullmatch(story_id):
        raise ValueError("invalid story id")
    with _folder(root, create=False) as folder:
        if folder is None:
            raise ValueError("story not found")
        try:
            name = f"{story_id}.story.json"
            if isinstance(folder, Path):
                path = folder / name
                if path.is_symlink() or path.resolve() != path or not path.is_file():
                    raise ValueError("story not found")
                descriptor = os.open(path, os.O_RDONLY)
            else:
                descriptor = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder
                )
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("story is not a regular file")
                data = stream.read(_LIMIT + 1)
            if isinstance(folder, Path) and _checked_folder(root, False) != folder:
                raise ValueError("story directory changed")
        except OSError as error:
            raise ValueError("story not found") from error
    if len(data) > _LIMIT:
        raise ValueError("story is too large")
    spec = _validate(json.loads(data))
    if spec["story"]["id"] != story_id:
        raise ValueError("story id differs from its filename")
    return spec


def read_story(root: Path, snapshot: Path, story_id: str) -> dict[str, Any]:
    """Read one stored story and check it again against the pinned snapshot."""
    root = root.resolve(strict=True)
    spec = _read_spec(root, story_id)
    with open_snapshot(snapshot) as db:
        return _check(db, root, snapshot, spec)


def list_stories(root: Path, snapshot: Path) -> list[dict[str, Any]]:
    """List bounded story specifications for the selected snapshot."""
    root = root.resolve(strict=True)
    with open_snapshot(snapshot) as db:
        _identity(db, root)
    with _folder(root, create=False) as folder:
        names = [] if folder is None else sorted(os.listdir(folder))
    rows = []
    for path in names:
        if not path.endswith(".story.json"):
            continue
        name = path.removesuffix(".story.json")
        if _ID.fullmatch(name):
            try:
                item = _read_spec(root, name)
                rows.append(
                    {
                        "id": name,
                        "title": item["story"]["title"],
                        "steps": len(item.get("steps", [])),
                    }
                )
            except (OSError, ValueError):
                rows.append({"id": name, "title": name, "error": "story unavailable"})
    return rows


def save_story(root: Path, snapshot: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Create a new story after validating its spec and snapshot identity."""
    spec = _validate(spec)
    data = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode()
    if len(data) > _LIMIT:
        raise ValueError("story is too large")
    root = root.resolve(strict=True)
    with open_snapshot(snapshot) as db:
        identity, _ = _identity(db, root)
        if spec["snapshot"] != identity:
            raise ValueError("story snapshot does not match")
        checked = _check(db, root, snapshot, spec)
    with _folder(root, create=True) as folder:
        if folder is None:
            raise ValueError("story directory is unavailable")
        name = f"{spec['story']['id']}.story.json"
        if isinstance(folder, Path):
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=folder, prefix=".story-", delete=False
                ) as stream:
                    temporary_path = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if _checked_folder(root, False) != folder:
                    raise ValueError("story directory changed")
                os.link(temporary_path, folder / name)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            return checked
        write_new_at(folder, name, data)
    return checked
