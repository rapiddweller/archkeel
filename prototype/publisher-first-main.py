from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
BASE = "e7b586c10721007c55339659ed2e29064ff9e3ab"
SCENE = "851b77a431e75ab8473e8a1bd71d2de8a728a75e"
PUBLISHER = "115f7c0f62dd30f7efc5dd6788db8f25ca0eed60"
PATHS = ["docs/superpowers/plans/2026-10-16-flow-runtime-publication.md","tests/test_flow_runtime_publication.py","tests/browser_runtime_ast.cjs","tools/browser-runtime/package.json","tools/browser-runtime/options.json","tools/browser-runtime/package-lock.json","tools/browser_runtime.py","src/archkeel/render/html.py",".gitignore","Makefile","tests/smoke_test.py","src/archkeel/render/assets/flow.runtime.js","tests/test_make_gate.py","tools/ci_changes.py","tests/test_ci_changes.py"]
root = Path.cwd()
for ref in (BASE, SCENE, PUBLISHER):
    subprocess.run(["git","fetch","--no-tags","origin",ref], check=True)
subprocess.run(["git","reset","--hard",BASE],check=True)
patch = subprocess.check_output(["git","diff","--binary",SCENE,PUBLISHER,"--",*PATHS])
result = subprocess.run(["git","apply","--3way","--index","-"],input=patch,capture_output=True)
conflicts = subprocess.check_output(["git","diff","--name-only","--diff-filter=U"]).decode().splitlines()
print("MAIN_3WAY_INITIAL=" + json.dumps({"base":BASE,"incoming":PUBLISHER,"returncode":result.returncode,"conflicts":conflicts,"stderr":result.stderr.decode()}))
if set(conflicts) - {"Makefile","tests/smoke_test.py"}:
    raise SystemExit("Unexpected conflict; inspect before resolution")
# Publisher owns no Scene/compiler source. Resolve context against actual Main.
make = subprocess.check_output(["git","show",BASE+":Makefile"]).decode()
before = "ci-core-check: browser-install gate typescript-compiler-check ci-typescript"
assert make.count(before) == 1
make = make.replace(before, before + " browser-runtime-check")
before = "ci-pr-report-check: browser-install pr-report-test"
assert make.count(before) == 1
make = make.replace(before,"ci-pr-report-check: browser-install browser-runtime-check pr-report-test")
before = "tools/architecture_graph_schema.py tools/report_timing.py tools/report_artifact_retention.py"
assert make.count(before) == 1
make = make.replace(before, before + " tools/browser_runtime.py")
incoming_make = subprocess.check_output(["git","show",PUBLISHER+":Makefile"]).decode()
publisher_targets = incoming_make.split("# Development publication only;",1)[1]
make = make.rstrip() + "\n\n# Development publication only;" + publisher_targets
Path("Makefile").write_text(make)
smoke = subprocess.check_output(["git","show",BASE+":tests/smoke_test.py"]).decode()
smoke = smoke.replace("from importlib.resources import files","from hashlib import sha256\nfrom importlib.resources import files")
smoke = smoke.replace("def main() -> None:\n","def main() -> None:\n"
    '    assets = files("archkeel.render").joinpath("assets")\n'
    '    flow_digest = sha256(assets.joinpath("flow.js").read_bytes()).hexdigest()\n'
    '    assert f"// Generated from flow.js; source-sha256={flow_digest}" in assets.joinpath(\n'
    '        "flow.runtime.js"\n'
    '    ).read_text(encoding="utf-8")\n')
Path("tests/smoke_test.py").write_text(smoke)
gate = Path("tests/test_make_gate.py").read_text()
assert gate.count('    "browser-graph-check",\n') == 1
Path("tests/test_make_gate.py").write_text(gate.replace('    "browser-graph-check",\n',""))
subprocess.run(["git","add","--",*PATHS],check=True)
subprocess.run(["git","diff","--cached","--check"],check=True)
changed = subprocess.check_output(["git","diff","--cached","--name-only",BASE]).decode().splitlines()
assert set(changed) <= set(PATHS)
for path in ("src/archkeel/render/assets/flow.js","src/archkeel/render/assets/report-scene.js",
             "src/archkeel/render/assets/report-layout.js","architecture-contract.json",
             "architecture-baseline.json","docs/architecture/contract.md"):
    subprocess.run(["git","diff","--cached","--exit-code",BASE,"--",path],check=True)
assert not Path("src/archkeel/render/assets/report-graph-protocol.js").exists()
print("MAIN_PUBLISHER_FILES=" + json.dumps({path:Path(path).read_text() for path in changed}))
print("MAIN_PUBLISHER_PROOF=" + json.dumps({"base":BASE,"changed_paths":changed,
    "tree":subprocess.check_output(["git","write-tree"]).decode().strip(),
    "flow_blob":subprocess.check_output(["git","rev-parse",BASE+":src/archkeel/render/assets/flow.js"]).decode().strip()}))
