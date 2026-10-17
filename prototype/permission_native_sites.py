import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from archkeel.check.ratchets import call_rows, measure_python_ratchets, unresolved_call_changes
from archkeel.ir.codec import decode_canonical_model, parse_observation

root = Path(os.environ["RUNNER_TEMP"])
before = parse_observation(decode_canonical_model(json.loads((root / "permission-before.json").read_bytes())))
after = parse_observation(decode_canonical_model(json.loads((root / "permission-after.json").read_bytes())))
print("PERMISSION_SITE_CHANGES=" + json.dumps([asdict(row) for row in unresolved_call_changes(before, after)]))
print("PERMISSION_METRICS=" + json.dumps({"before":asdict(measure_python_ratchets(before)), "after":asdict(measure_python_ratchets(after))}))
old = Counter(row.id for row in before.records("unknowns") or ())
new = Counter(row.id for row in after.records("unknowns") or ())
print("PERMISSION_UNKNOWN_IDS=" + json.dumps({"added":list((new-old).elements()), "removed":list((old-new).elements())}))
print("PERMISSION_OWNER_CALLS=" + json.dumps([asdict(row) for row in call_rows(after) if row.path == "src/archkeel/ir/architecture_projection.py"]))
