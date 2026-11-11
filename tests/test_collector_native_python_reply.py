# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The 10.0.0 reply of the native Python collector is the Python import survey, and no PASS.

Consumers: the host codec (`facts_codec.decode_response`), the Rust store (`archkeel-store`) and
the evaluation of a Python reply. The reply must equal the reply of the unmodified Python collector
in the phase `imports`; only the adapter (the producer) and the version differ. The reply declares
only the sections of the survey, so it never claims the whole collection. The codec and the store
refuse it with a named error, also when it claims completeness (AD-334, AD-365).
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest
from collector_pin import pin_of
from conftest import build_native_copy, by_python
from false_pass_support import copy_repository
from test_collector_native_python_scope import _FIXTURES
from test_collector_native_python_survey import _EDGES, _PARSE_FAILURES, _closed, _request, _tree

from archkeel.analyzer.interpreter import interpreter, python_request
from archkeel.analyzer.python.collect import PythonProviderCollector, collect
from archkeel.analyzer.store import StoreSession, _StoreError
from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir import facts_codec
from archkeel.ir.facts_codec import ProtocolError
from archkeel.ir.languages import Language
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonCollectionPhase,
)
from archkeel.ir.state_facts import ProducerKind

ROOT = Path(__file__).parents[1]
_LIMIT = 1 << 30


@pytest.fixture(scope="module")
def python_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The native Python collector as the wheel would build it: no `dump` feature."""
    return build_native_copy(tmp_path_factory, "native-python", binary="archkeel-python-collector")


def _native(binary: Path, request: CollectionRequest) -> bytes:
    block = interpreter()
    assert not isinstance(block, CollectionError), block
    completed = subprocess.run(
        [str(binary)], input=python_request(request, block), capture_output=True, check=True
    )
    return completed.stdout


def _python(request: CollectionRequest) -> dict[str, Any]:
    response = CollectionResponse(collect(request), ProtocolVersion.V9)
    found: dict[str, Any] = json.loads(zlib.decompress(facts_codec.encode_response(response)))
    return found


def _comparable(reply: dict[str, Any]) -> str:
    """The reply without its producer and version, with each syntax failure on its file and
    class only, and without the evidence that only a syntax failure cites (AD-365 point 1)."""
    facts = dict(reply["facts"])
    del facts["adapter"]
    records = [record for section in facts["sections"] for record in section["records"]]
    failures = [record for record in records if record["kind"] in _PARSE_FAILURES]
    cited = {
        evidence
        for record in records
        if record["kind"] not in _PARSE_FAILURES
        for evidence in record.get("evidence_ids", ())
    }
    cited.update(item["evidence_id"] for item in facts["files"])
    only_failures = {
        evidence for record in failures for evidence in record.get("evidence_ids", ())
    } - cited
    facts["evidence"] = [item for item in facts["evidence"] if item["id"] not in only_failures]
    rest = {key: value for key, value in reply.items() if key not in {"facts", "protocol_version"}}
    return json.dumps(_closed({**rest, "facts": facts}), sort_keys=True, ensure_ascii=False)


def _equal(binary: Path, root: Path, roots: tuple[str, ...], namespace: str) -> None:
    for exclude in (False, True):
        request = _request(root, roots, namespace, exclude)
        found = json.loads(zlib.decompress(_native(binary, request)))
        assert found["protocol_version"] == "10.0.0"
        assert _comparable(found) == _comparable(_python(request)), (root, exclude)


def test_the_reply_of_the_edge_cases_is_the_python_survey(
    tmp_path: Path, python_binary: Path
) -> None:
    root = _tree(tmp_path / "repo", _EDGES)
    (root / "src/app/latin.py").write_bytes(b"x = '\\xff'\n\xff\n")
    if os.name != "nt":
        (root / "src/app/dangling.py").symlink_to("nowhere.py")
    _equal(python_binary, root, ("src",), "app")


@pytest.mark.parametrize("fixture", _FIXTURES)
def test_the_reply_of_each_fixture_is_the_python_survey(fixture: str, python_binary: Path) -> None:
    config = load_config(ROOT / fixture)
    _equal(python_binary, ROOT / fixture, config.roots, config.namespace)


def test_the_reply_of_the_archkeel_source_is_the_python_survey(python_binary: Path) -> None:
    _equal(python_binary, ROOT, ("src",), "archkeel")


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_PYTHON_SCOPE_CORPORA"), reason="no corpus is named"
)
def test_the_reply_of_each_named_corpus_is_the_python_survey(python_binary: Path) -> None:
    for entry in os.environ["ARCHKEEL_PYTHON_SCOPE_CORPORA"].split(";"):
        root, namespace, roots = entry.split("=")
        _equal(python_binary, Path(root), tuple(roots.split(",")), namespace)


def _stops_python(
    binary: Path, root: Path, rels: tuple[str, ...], error: type[Exception], fixed: bool
) -> None:
    """AD-365 points 11 and 12: where the Python collector stops with `error`, native writes a
    gap that names each file and no file fact for it. Where Python does not stop, the replies are
    equal."""
    request = _request(root, ("src",), "app", False)
    if fixed and error is RuntimeError:
        _equal_but_os_error(binary, request, rels)
    elif fixed:
        _equal(binary, root, ("src",), "app")
    else:
        with pytest.raises(error):
            collect(request)
    facts = json.loads(zlib.decompress(_native(binary, request)))["facts"]
    named = {gap["data"].get("file") for gap in facts["coverage"]["gaps"]}
    assert set(rels) <= named, named
    assert not {item["rel_path"] for item in facts["files"]} & set(rels)
    assert not facts["coverage"]["full_scope"]


def _equal_but_os_error(binary: Path, request: CollectionRequest, rels: tuple[str, ...]) -> None:
    """3.13 and 3.14 write `OSError` for a file of the loop and native `FileNotFoundError`: the
    rule of AD-365 point 10 for these files only. The rest of the reply is equal."""
    replies = [json.loads(zlib.decompress(_native(binary, request))), _python(request)]
    for reply in replies:
        facts = reply["facts"]
        for records in (facts["coverage"]["gaps"], facts["sections"][1]["records"]):
            kinds = {item["data"].get("file"): item["kind"] for item in records}
            assert all(issubclass(getattr(builtins, kinds[rel]), OSError) for rel in rels), kinds
            records[:] = [item for item in records if item["data"].get("file") not in rels]
    assert _comparable(replies[0]) == _comparable(replies[1])


@pytest.mark.parametrize("fixed", by_python(12))
def test_an_integer_in_an_f_string_that_stops_python_is_a_named_gap(
    fixed: bool, tmp_path: Path, python_binary: Path
) -> None:
    rel = "src/app/big.py"
    root = _tree(
        tmp_path / "repo", {"src/app/__init__.py": "", rel: 'x = f"{' + "1" * 5000 + '}"\n'}
    )
    _stops_python(python_binary, root, (rel,), SystemError, fixed)


@pytest.mark.skipif(os.name == "nt", reason="needs POSIX symbolic links")
@pytest.mark.parametrize("fixed", by_python(13))
def test_a_symlink_loop_that_stops_python_is_a_named_gap(
    fixed: bool, tmp_path: Path, python_binary: Path
) -> None:
    root = _tree(tmp_path / "repo", {"src/app/__init__.py": "import os\n"})
    (root / "src/app/cyc.py").symlink_to("cyc2.py")
    (root / "src/app/cyc2.py").symlink_to("cyc.py")
    _stops_python(python_binary, root, ("src/app/cyc.py", "src/app/cyc2.py"), RuntimeError, fixed)


def test_the_reply_declares_only_the_sections_of_the_survey(python_binary: Path) -> None:
    found = json.loads(
        zlib.decompress(_native(python_binary, _request(ROOT, ("src",), "archkeel", False)))
    )
    capabilities = found["facts"]["capabilities"]
    assert capabilities == {
        "constructs": [],
        "resolution_features": [],
        "sections": ["imports", "unknowns"],
    }
    assert [section["name"] for section in found["facts"]["sections"]] == ["imports", "unknowns"]


def _claims_completeness(reply: dict[str, Any], root: Path, namespace: str) -> None:
    """The planted fault: the reply claims the capabilities of the whole Python collection, has
    each of its sections and a full scope without a gap."""
    request = _request(root, ("src",), namespace, False)
    whole = collect(
        CollectionRequest(
            request.snapshot,
            request.scope,
            type(request.resolver)(phase=PythonCollectionPhase.COLLECT),
            request.protocol_version,
        )
    )
    payload = facts_codec.encode_response(CollectionResponse(whole, ProtocolVersion.V9))
    capabilities = json.loads(zlib.decompress(payload))["facts"]["capabilities"]
    # The store types the construct status of the native vocabulary only; the claim uses it, so
    # the refusal below is the refusal of the version and not of an unknown word.
    for entry in capabilities["constructs"]:
        entry["status"] = "supported"
    facts = reply["facts"]
    facts["capabilities"] = capabilities
    held = {section["name"] for section in facts["sections"]}
    facts["sections"] += [
        {"name": name, "records": []} for name in capabilities["sections"] if name not in held
    ]
    for section in facts["sections"]:
        if section["name"] == "unknowns":
            section["records"] = []
    facts["coverage"] = {**facts["coverage"], "full_scope": True, "gaps": []}


_REPLIES = ("honest", "claims-completeness")


def _reply(binary: Path, root: Path, namespace: str, kind: str) -> bytes:
    payload = _native(binary, _request(root, ("src",), namespace, False))
    if kind == "honest":
        return payload
    reply = json.loads(zlib.decompress(payload))
    _claims_completeness(reply, root, namespace)
    assert reply["facts"]["capabilities"]["resolution_features"], "the claim is not complete"
    return zlib.compress(json.dumps(reply).encode(), 1)


@pytest.mark.parametrize("kind", _REPLIES)
def test_the_host_codec_refuses_a_native_reply(kind: str, python_binary: Path) -> None:
    root = ROOT / "fixtures/F-architecture"
    payload = _reply(python_binary, root, load_config(root).namespace, kind)
    with pytest.raises(ProtocolError, match="^unsupported collection protocol version$"):
        facts_codec.decode_response(payload)


@pytest.mark.parametrize("kind", _REPLIES)
def test_the_store_refuses_a_native_reply(
    kind: str, python_binary: Path, store_binary: Path
) -> None:
    root = ROOT / "fixtures/F-architecture"
    payload = _reply(python_binary, root, load_config(root).namespace, kind)
    session = StoreSession(str(store_binary), _LIMIT, _LIMIT)
    try:
        with pytest.raises(_StoreError, match=r"does not read protocol 10\.0\.0 replies yet"):
            session.ingest(payload)
    finally:
        session.close()


def _relabelled_argv(binary: Path, workspace: Path) -> tuple[str, ...]:
    """A producer that sends the honest native reply under the version of the host request."""
    script = workspace / "relabel.py"
    script.write_text(
        "import json, subprocess, sys, zlib\n"
        "from archkeel.analyzer.interpreter import interpreter, python_request\n"
        "from archkeel.ir.facts_codec import decode_request\n"
        "request = decode_request(sys.stdin.buffer.read())\n"
        f"answer = subprocess.run([{str(binary)!r}], input=python_request(request, interpreter()),"
        " capture_output=True, check=True).stdout\n"
        "reply = json.loads(zlib.decompress(answer))\n"
        "reply['protocol_version'] = '9.0.0'\n"
        "sys.stdout.buffer.write(zlib.compress(json.dumps(reply).encode(), 1))\n",
        encoding="utf-8",
    )
    return (sys.executable, "-I", "-B", str(script))


def _verdict(root: Path, argv: tuple[str, ...] | None) -> tuple[list[str], list[str]]:
    config = load_config(root)
    pinned = pin_of(argv[0]) if argv else None
    observer = observer_for(config.language, collector_argv=argv, pinned_digest=pinned)
    result, _ = run_report(root, config=config, analyzer=observer)
    rules = result.rule_assessments or ()
    passing = sorted(item.id for item in rules if str(item.status) == "PASS")
    return passing, [str(item.unknown_claim) for item in result.diagnostics]


def test_the_survey_capabilities_alone_give_no_pass(tmp_path: Path, python_binary: Path) -> None:
    """Without the version refusal, the capabilities of the survey still stop each PASS: the
    evaluation refuses a Python reply that does not declare the sections of the collection."""
    root = copy_repository(ROOT / "fixtures/F-architecture", tmp_path)
    assert _verdict(root, None)[0], "the probe is empty: the Python collector gives no PASS"
    passing, claims = _verdict(root, _relabelled_argv(python_binary, tmp_path))
    assert passing == []
    assert any(
        "source sections do not match the registered profile" in claim for claim in claims
    ), claims


def test_the_host_keeps_the_python_collector_with_a_native_binary(tmp_path: Path) -> None:
    """No PASS before slice 8 (AD-334): the host starts the Python collector for Python, also
    when a native Python binary and its digest lie in the native directory."""
    name = "archkeel-python-collector" + (".exe" if os.name == "nt" else "")
    (tmp_path / name).write_bytes(b"binary")
    digest = hashlib.sha256(b"binary").hexdigest()
    (tmp_path / f"{name}.sha256").write_text(digest + "\n", encoding="utf-8")
    observer = observer_for(Language.PYTHON, native_directory=tmp_path)
    assert observer.producer == ProducerKind.PYTHON
    assert isinstance(observer.collector, PythonProviderCollector)
    assert observer.collector.collector.argv[-1] == "archkeel.analyzer.python.entry"
    assert '"archkeel-python-collector"' not in (ROOT / "native/hatch_build.py").read_text()
    assert "archkeel-python-collector" not in (ROOT / "src/archkeel/cli/observe.py").read_text()
