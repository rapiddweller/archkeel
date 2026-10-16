from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

ROOT = Path.cwd()
BASE = "c7444205d4fe87eaae0de5e2dc98b70909fd1cc7"
SCENE_BASE = "d08dfaf6a2e6992153a434341465306a88d993a2"
SCENE = "851b77a431e75ab8473e8a1bd71d2de8a728a75e"
PUBLISHER = "7f6979c0ddbee2a47318bf3e4291a0f17a0b865f"
SCENE_PATHS = ["docs/superpowers/specs/2026-10-16-native-graph-scene-protocol.md","docs/superpowers/plans/2026-10-16-native-graph-scene-protocol.md","tests/test_graph_scene_protocol.py","tools/browser_graph_protocol.py","src/archkeel/render/assets/report-graph-protocol.ts","src/archkeel/render/assets/report-graph-scene.js","src/archkeel/render/assets/report-scene.js","src/archkeel/render/html.py","tests/test_report_renderer_units.py","src/archkeel/render/assets/report-graph-vocabulary.ts","src/archkeel/render/assets/report-graph-protocol.js","tests/browser_graph_scene_target.ts","Makefile","tests/smoke_test.py"]
PUBLISHER_PATHS = ["docs/superpowers/plans/2026-10-16-flow-runtime-publication.md","tests/test_flow_runtime_publication.py","tests/browser_runtime_ast.cjs","tools/browser-runtime/package.json","tools/browser-runtime/options.json","tools/browser-runtime/package-lock.json","tools/browser_runtime.py","src/archkeel/render/html.py",".gitignore","Makefile","tests/smoke_test.py","src/archkeel/render/assets/flow.runtime.js"]

def run(*args: str, cwd: Path = ROOT, input: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, cwd=cwd, input=input, capture_output=True)

for ref in (BASE, SCENE_BASE, SCENE, PUBLISHER):
    result = run("git", "fetch", "--no-tags", "origin", ref)
    if result.returncode:
        raise SystemExit(result.stderr.decode())

for name, stages in (
    ("scene-then-publisher", ((SCENE_BASE, SCENE, SCENE_PATHS), (SCENE, PUBLISHER, PUBLISHER_PATHS))),
    ("publisher-first", ((SCENE, PUBLISHER, PUBLISHER_PATHS),)),
):
    checkout = Path(os.environ["RUNNER_TEMP"]) / name
    result = run("git", "worktree", "add", "--detach", str(checkout), BASE)
    if result.returncode:
        raise SystemExit(result.stderr.decode())
    proofs = []
    clean = True
    for predecessor, incoming, paths in stages:
        patch = run("git", "diff", "--binary", predecessor, incoming, "--", *paths).stdout
        applied = run("git", "apply", "--3way", "--index", "-", cwd=checkout, input=patch)
        conflicts = run("git", "diff", "--name-only", "--diff-filter=U", cwd=checkout).stdout.decode().splitlines()
        proofs.append({"from": predecessor, "to": incoming, "patch_bytes": len(patch),
                       "returncode": applied.returncode, "stdout": applied.stdout.decode(),
                       "stderr": applied.stderr.decode(), "conflicts": conflicts})
        if applied.returncode:
            print("INTEGRATION_CONFLICTS=" + json.dumps({path: (checkout / path).read_text() for path in conflicts}))
            clean = False
            break
    changed = run("git", "diff", "--cached", "--name-only", BASE, cwd=checkout).stdout.decode().splitlines()
    proof = {"case": name, "base": BASE, "clean": clean, "stages": proofs, "changed_paths": changed}
    if clean:
        proof["tree"] = run("git", "write-tree", cwd=checkout).stdout.decode().strip()
        untouched = ["src/archkeel/render/assets/flow.js", "src/archkeel/render/assets/report-layout.js",
                     "architecture-contract.json", "architecture-baseline.json",
                     "docs/architecture/contract.md"]
        proof["untouched"] = {path: not run("git", "diff", "--cached", "--quiet", BASE, "--", path, cwd=checkout).returncode for path in untouched}
        print("INTEGRATION_FILES_" + name.upper().replace("-", "_") + "=" + json.dumps({path: (checkout / path).read_text() for path in changed}))
    print("INTEGRATION_PROOF=" + json.dumps(proof))
