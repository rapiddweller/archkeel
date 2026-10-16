# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Formatting preserves witnessed constructs; a derivative is not a second input."""

import json
from collections import Counter
from pathlib import Path

from archkeel.analyzer.typescript.collect import collect
from archkeel.ir.facts import ConstructSupport, SourceSectionName
from archkeel.ir.facts_codec import decode_response, encode_response
from archkeel.ir.model import ForbiddenConstructKind
from archkeel.ir.protocol import (
    CollectionRequest, CollectionResponse, SnapshotInput, SourceScope, TypeScriptSettings,
)


def test_authored_flow_and_derivative_preserve_native_construct_multisets(tmp_path: Path) -> None:
    assets = Path("src/archkeel/render/assets")
    source = (assets / "flow.js").read_bytes()
    emitted = (assets / "flow.runtime.js").read_bytes()
    (tmp_path / "src").mkdir()
    (tmp_path / "src/flow.runtime.js").write_bytes(emitted)
    (tmp_path / "tsconfig.json").write_text(json.dumps({
        "compilerOptions":{"allowJs":True,"checkJs":True},
        "files":["src/flow.js"],
    }))
    request = CollectionRequest(
        SnapshotInput(str(tmp_path),"a"*40,False),
        SourceScope(("src",),"browser"),
        TypeScriptSettings(),
    )

    def observed(data: bytes) -> tuple[Counter[str], int]:
        (tmp_path / "src/flow.js").write_bytes(data)
        facts = decode_response(encode_response(CollectionResponse(collect(request)))).facts
        status = next(item.status for item in facts.capabilities.constructs
            if item.name is ForbiddenConstructKind.STRING_LITERAL_COMPARE)
        assert status is ConstructSupport.PARTIAL
        assert tuple(file.rel_path for file in facts.files) == ("src/flow.js",), (
            "The derivative must not become a second authored input"
        )
        records = [record for section in facts.sections for record in section.records
            if section.name is SourceSectionName.CONSTRUCTS
            and record.kind == ForbiddenConstructKind.STRING_LITERAL_COMPARE]
        owners: list[str] = []
        for record in records:
            owner = record.data.get("owner")
            assert isinstance(owner,str)
            owners.append(owner)
        return Counter(owners), len(records)

    original, count = observed(source)
    derivative, emitted_count = observed(emitted)
    assert count > 0
    assert derivative == original
    assert emitted_count == count
    print("FLOW_NATIVE_SOURCE_PARITY="+json.dumps({
        "authored_modules":1,"derivative_is_second_input":False,
        "authored_constructs":count,"derivative_constructs":emitted_count,
        "owner_kind_multiset_equal":True,"capability":"partial",
        "absence_pass_claimed":False,
    }))
