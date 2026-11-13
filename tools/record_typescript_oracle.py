# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run only the unchanged main Python producers for the public migration oracle."""

from __future__ import annotations

import base64
import importlib
import json
import locale
import platform
import subprocess
import sys
from pathlib import Path


def _verdict(producer, root: Path) -> dict:
    from test_collector_native_verdicts import PRODUCER, _scope_kinds

    from archkeel.check.observe import Observer
    from archkeel.check.report import run_report_with_observation
    from archkeel.cli.config import load_config
    from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
    from archkeel.ir.state_facts import ProducerKind

    class Original:
        def collect(self, request):
            return producer.collect(request)

    config = load_config(root)
    result, artifact, model = run_report_with_observation(
        root,
        config=config,
        analyzer=Observer(
            Original(), tsconfig=config.tsconfig or "tsconfig.json", producer=ProducerKind.PYTHON
        ),
    )
    sections = json.loads(artifact) if artifact else {}
    return {
        "declared": str(result.declared_rules.value),
        "complete": str(result.observation_complete.value),
        "exit": result.exit_code,
        "diagnostics": sorted(str(item.kind.value) for item in result.diagnostics),
        "rules": {
            item.id: [item.kind, str(item.status.value)]
            for item in (
                ()
                if model is None
                else rule_assessments(model, undecided_by_rule=unknown_positions_by_rule(model))
            )
        },
        "artifact": {key: value for key, value in sections.items() if key not in PRODUCER},
        "scope_kinds": _scope_kinds(sections),
    }


def serve(root: Path) -> None:
    from archkeel.ir.facts_codec import decode_request, encode_response
    from archkeel.ir.protocol import CollectionResponse

    sys.path.insert(0, str(root / "tests"))
    sys.path.insert(1, str(root))
    producer = importlib.import_module("archkeel.analyzer.typescript.collect")
    assert Path(producer.__file__).resolve() == root / "src/archkeel/analyzer/typescript/collect.py"
    locale.setlocale(locale.LC_CTYPE, "C")
    print(
        json.dumps(
            {
                "main_sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, text=True
                ).strip(),
                "python": platform.python_version(),
            }
        ),
        flush=True,
    )
    for line in sys.stdin:
        call = json.loads(line)
        kind, arguments = call["kind"], call["arguments"]
        if kind == "verdict":
            data = json.dumps(_verdict(producer, Path(arguments[0])), sort_keys=True).encode()
        elif kind in {"collect", "records"}:
            request = decode_request(bytes.fromhex(arguments[0]))
            if kind == "collect":
                data = encode_response(
                    CollectionResponse(producer.collect(request), request.protocol_version)
                )
            else:
                helper = importlib.import_module("test_collector_native_records")
                data = json.dumps(helper.python_records(request), sort_keys=True).encode()
        elif kind == "locale":
            helper = importlib.import_module("test_collector_locale")
            data = encode_response(
                CollectionResponse(helper._oracle(Path(arguments[0]), arguments[1]))
            )
        else:
            module = (
                "test_collector_native_syntax"
                if kind == "syntax"
                else "test_collector_native_script_umd"
            )
            helper = importlib.import_module(module)
            assert Path(helper.__file__).resolve().is_relative_to(root / "tests")
            value = helper._python(arguments[0], base64.b64decode(arguments[1], validate=True))
            data = json.dumps(value, sort_keys=True).encode()
        print(json.dumps(base64.b64encode(data).decode()), flush=True)
