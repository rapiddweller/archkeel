"""Replaceable argv collectors fail with bounded, named diagnostics."""

import json
import sys

from test_collection_protocol import _request, _response

from archkeel.ir.facts_codec import decode_request
from archkeel.ir.protocol import CollectionError


def _collector(code: str, **limits):
    from archkeel.analyzer.process import ProcessCollector

    return ProcessCollector((sys.executable, "-B", "-c", code), **limits)


def test_configured_executable_collects_facts_without_receiving_policy(tmp_path) -> None:
    response = _response()
    code = (
        "import json,sys; request=json.load(sys.stdin); "
        "assert set(request)=={'protocol_version','snapshot','scope','resolver'}; "
        f"print({json.dumps(json.dumps(response))})"
    )
    request = decode_request(_request())
    from dataclasses import replace

    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    facts = _collector(code).collect(request)
    assert not isinstance(facts, CollectionError)
    assert facts.adapter.name == "alternate-parser"
    assert facts.files[0].module == "project.app"


def test_nonzero_process_exit_cannot_be_a_complete_collection(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector("import sys; sys.stderr.write('collector failed'); sys.exit(2)").collect(
        request
    )
    assert isinstance(result, CollectionError)
    assert result.kind == "execution_error"
    assert "collector failed" in result.message


def test_output_limit_stops_collector_while_it_is_running(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector(
        "import sys; sys.stdout.write('x'*1000000); sys.stdout.flush()", output_limit_bytes=1000
    ).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "protocol_error"
    assert "limit" in result.message


def test_timeout_also_bounds_a_process_that_never_reads_stdin(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector("import time; time.sleep(30)", timeout_seconds=0.05).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "timeout"


def test_unavailable_executable_is_a_named_missing_tool(tmp_path) -> None:
    from dataclasses import replace

    from archkeel.analyzer.process import ProcessCollector

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = ProcessCollector((str(tmp_path / "missing-tool"),)).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "missing_tool"


def test_response_revision_must_match_requested_snapshot(tmp_path) -> None:
    from dataclasses import replace

    response = _response()
    response["facts"]["source"]["git_head"] = "b" * 40
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector(f"print({json.dumps(json.dumps(response))})").collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "protocol_error"
    assert "snapshot" in result.message
