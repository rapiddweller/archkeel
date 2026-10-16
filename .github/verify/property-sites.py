import json
import sys
from collections import Counter
from pathlib import Path

root, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
sys.path.insert(0, str(root / "src"))
from archkeel.cli.observe import observe
from archkeel.ir.facts_codec import record_payload

result = observe(
    root, roots=("src/archkeel",), namespace="archkeel",
    contract="architecture-contract.json", git_head="0" * 40,
    dirty=False, contract_root=root,
)
assert result.diagnostics == () and result.observation is not None, result.diagnostics
observation = result.observation

def site(record):
    data = record_payload(record)["data"]
    return {
        "kind": record.kind,
        "source": data.get("source_module"),
        "scope": data.get("source_scope"),
        "expression": data.get("expression"),
        "status": data.get("status"),
        "reason": data.get("reason"),
        "targets": data.get("targets"),
        "candidate_count": data.get("candidate_count"),
        "candidates_truncated": data.get("candidates_truncated"),
    }

def items(section, status):
    return [site(row) for row in observation.records(section)
            if row.data.get("status") == status]

unknowns = [
    {"id": row.id, "kind": row.kind, "subjects": row.subjects,
     "rule_ids": row.rule_ids}
    for row in observation.records("unknowns")
]
body = {
    "unresolved_calls": items("calls", "unresolved"),
    "partial_calls": items("calls", "partially_resolved"),
    "unresolved_references": items("references", "unresolved"),
    "partial_references": items("references", "partially_resolved"),
    "unknowns": unknowns,
}
for key, value in body.items():
    value.sort(key=lambda item: json.dumps(item, sort_keys=True))
output.write_text(json.dumps(body, sort_keys=True))
print(json.dumps({"root": str(root), "counts": {key: len(value) for key,value in body.items()}}))
