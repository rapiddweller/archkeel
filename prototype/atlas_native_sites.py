import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from archkeel.check.ratchets import call_rows, measure_python_ratchets, unresolved_call_changes
from archkeel.ir.codec import decode_canonical_model, parse_observation
root = Path(os.environ["RUNNER_TEMP"])
before = parse_observation(decode_canonical_model(json.loads((root / "atlas-before.json").read_bytes())))
after = parse_observation(decode_canonical_model(json.loads((root / "atlas-after.json").read_bytes())))
changes = unresolved_call_changes(before, after)
print("ATLAS_ACTUAL_SITE_CHANGES=" + json.dumps([asdict(row) for row in changes]))
print("ATLAS_ACTUAL_METRICS=" + json.dumps({"before":asdict(measure_python_ratchets(before)),
    "after":asdict(measure_python_ratchets(after))}))
print("ATLAS_CALLER_ROWS=" + json.dumps([asdict(row) for row in call_rows(after)
    if row.path in ("src/archkeel/render/atlas.py", "src/archkeel/render/atlas_deviations.py")]))
old = Counter(row.id for row in before.records("unknowns") or ())
new = Counter(row.id for row in after.records("unknowns") or ())
print("ATLAS_UNKNOWN_IDS=" + json.dumps({"added":list((new-old).elements()),
    "removed":list((old-new).elements())}))
