import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path("tests").resolve()))
from test_report_filter import CONFIG, _tour_root
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.render.html import render_architecture_html
from test_report_renderer_units import _asset_page
from playwright import sync_api

with TemporaryDirectory() as temporary:
    root = _tour_root(Path(temporary))
    contract_path = root / CONFIG.contract
    contract = json.loads(contract_path.read_text())
    cli = next(item for item in contract["components"] if item["id"] == "COMP-CLI")
    cli["requires"] = [{"component":"model","rationale":"Exercise an unused root permission."}]
    contract_path.write_text(json.dumps(contract))
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    html = render_architecture_html(result, architecture, repository="shop", architecture_href="architecture.json").decode()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    data = json.loads(match.group(1))
    assert len(data["atlas"]["levels"]) >= 2
    assert {"allowed_unused","undeclared"} <= {row["kind"] for row in data["atlas"]["deviations"]}
    old_source = subprocess.check_output(["git","show","0aee692c767150847089dbcfdcf1765464837ab6:src/archkeel/render/assets/report-scene.js"], text=True)
    playwright, browser, page = _asset_page(sync_api, ["report-scene.js"])
    try:
        page.evaluate("window.NewReportScene = ArchkeelReportScene")
        page.add_script_tag(content=old_source)
        proof = page.evaluate("""data => {
          const before = JSON.stringify(data);
          const oldModel = ArchkeelReportScene.create(data);
          const originalDecode = ArchkeelGraphSceneProtocol.decodeAtlasDeviations;
          let decodes = 0;
          ArchkeelGraphSceneProtocol.decodeAtlasDeviations = value => { decodes++; return originalDecode(value); };
          const newModel = NewReportScene.create(data);
          let scenes = 0;
          for (const oldLevel of oldModel.atlas.levels) {
            const newLevel = newModel.atlas.levels.find(row => row.id === oldLevel.id);
            for (const mode of ["diagram","target","diff","actual","structure","review"]) {
              const oldScene = oldModel.atlasScene(oldLevel, mode);
              const newScene = newModel.atlasScene(newLevel, mode);
              if (JSON.stringify(oldScene) !== JSON.stringify(newScene)) throw Error("Scene parity " + oldLevel.id + "/" + mode);
              if (ArchkeelReportScene.sceneToMermaid(oldScene) !== NewReportScene.sceneToMermaid(newScene)) throw Error("Mermaid parity");
              scenes++;
            }
          }
          return {scenes, levels:oldModel.atlas.levels.length, decodes, inputUnchanged:JSON.stringify(data)===before};
        }""", data)
        assert proof["decodes"] == 1 and proof["inputUnchanged"] and proof["scenes"] >= 12, proof
        print("ATLAS_ACTUAL_PREDECESSOR_PARITY=" + json.dumps(proof))
    finally:
        browser.close()
        playwright.stop()
