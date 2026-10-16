"""Positive native observation of a mutation to the actual checked browser source."""

import json
from pathlib import Path

from archkeel.analyzer.typescript.collect import collect
from archkeel.ir.facts import ConstructSupport, SourceSectionName
from archkeel.ir.facts_codec import decode_response, encode_response
from archkeel.ir.protocol import (
    CollectionRequest, CollectionResponse, SnapshotInput, SourceScope, TypeScriptSettings,
)
from archkeel.ir.model import ForbiddenConstructKind


def test_real_scene_source_literal_mutation_has_a_native_fact_and_keeps_partial_capability(tmp_path):
    production = Path("src/archkeel/render/assets/report-graph-scene.js").read_text()
    before = "graph.origin !== G.OriginKind.OBSERVED"
    assert production.count(before) == 1
    (tmp_path / "src").mkdir()
    config = {"compilerOptions": {"allowJs": True, "checkJs": True, "module": "commonjs",
        "moduleResolution": "node"}, "include": ["src"]}
    (tmp_path / "tsconfig.json").write_text(json.dumps(config))
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("src",), "browser"), TypeScriptSettings(),
    )

    def observed(source):
        (tmp_path / "src/scene.js").write_text(source)
        facts = decode_response(encode_response(CollectionResponse(collect(request)))).facts
        capability = next(item for item in facts.capabilities.constructs
            if item.name is ForbiddenConstructKind.STRING_LITERAL_COMPARE)
        assert capability.status is ConstructSupport.PARTIAL
        records = [record for section in facts.sections for record in section.records
            if section.name is SourceSectionName.CONSTRUCTS and record.kind == ForbiddenConstructKind.STRING_LITERAL_COMPARE]
        return facts, records

    original, clean = observed(production)
    mutated, found = observed(production.replace(before, 'graph.origin !== "observed"'))
    assert not clean
    assert len(found) == 1
    record = found[0]
    evidence = {entry.id: entry for entry in mutated.evidence}
    assert record.evidence_ids
    proof = [evidence[key] for key in record.evidence_ids]
    assert all(entry.file == "src/scene.js" and entry.line > 0 for entry in proof)
    assert any('graph.origin !== "observed"' in entry.excerpt for entry in proof)
    print("ACTUAL_SCENE_NATIVE_MUTATION=" + json.dumps({
        "original_construct_count": len(clean), "mutated_construct_count": len(found),
        "record": record.id, "file": proof[0].file, "line": proof[0].line,
        "capability": "partial", "absence_pass_claimed": False,
    }))
