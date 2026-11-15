# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Serialize the DOM of a rendered Explorer page after its scripts ran, in headless Chromium.

The Explorer fixtures in `tests/browser_fixtures` are pages of the report renderer that AD-432
deleted (commit `5cbf811ad^`, `archkeel report` on `fixtures/H-typescript` and
`fixtures/F-typescript-story`). The page text of a fixture is kept; the script bodies are the
current `explorer.runtime.js` and the ELK bundle of `src/archkeel/render/assets` (the published
runtime of the fixture is byte-equal to the current one). A scenario clicks controls of the page,
one after the other, and the harness records which `innerHTML` and `insertAdjacentHTML` sites of
the runtime ran. The snapshot is the DOM that a reader sees, without the script and style text. It
guards a rewrite of the code that builds the nodes: the same page must give the same nodes. No
browser driver and no JavaScript dependency is used, only the command line of Chromium.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_FIXTURES = _ROOT / "tests/browser_fixtures"
_ASSETS = _ROOT / "src/archkeel/render/assets"
_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
)
_BUDGET_MS = 20000
_SINK_META = "x-sinks"
# The sink recorder runs first and the driver last; neither is a part of the page under test.
_RECORDER = r"""<script>(function () {
  const sites = [];
  const site = () => {
    for (const row of new Error().stack.split("\n")) {
      const hit = /:(\d+):(\d+)\)?$/.exec(row);
      if (hit && Number(hit[1]) > @FIRST@ && Number(hit[1]) <= @LAST@) return (Number(hit[1]) - @FIRST@) + ":" + hit[2];
    }
    return "0:0";
  };
  const html = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
  Object.defineProperty(Element.prototype, "innerHTML", { ...html, set(value) { sites.push(site()); html.set.call(this, value); } });
  const adjacent = Element.prototype.insertAdjacentHTML;
  Element.prototype.insertAdjacentHTML = function (...args) { sites.push(site()); return adjacent.apply(this, args); };
  window.__sinks = sites;
})();</script>"""
_DRIVER = r"""<script>(function () {
  const steps = @STEPS@;
  let at = 0;
  const next = () => {
    if (at >= steps.length) {
      const meta = document.createElement("meta");
      meta.name = "@META@";
      meta.content = JSON.stringify([...new Set(window.__sinks)]);
      document.head.append(meta);
      return;
    }
    const [selector, index] = steps[at++].split("@");
    const found = document.querySelectorAll(selector)[Number(index || 0)];
    if (found && !found.disabled) found.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    setTimeout(next, 400);
  };
  setTimeout(next, 800);
})();</script>"""


def chromium() -> str | None:
    """The Chromium of this machine: the `ARCHKEEL_CHROMIUM` path, or the first known one."""
    wanted = os.environ.get("ARCHKEEL_CHROMIUM")
    for name in (wanted,) if wanted else _CANDIDATES:
        if name and (shutil.which(name) or Path(name).exists()):
            return name
    return None


def assemble(fixture: str, steps: list[str]) -> str:
    """The page of a fixture with the current runtime, the recorder and the driver."""
    page = (_FIXTURES / f"{fixture}.html").read_text(encoding="utf-8")
    elk = (_ASSETS / "elkjs-0.12.0.bundled.js").read_text(encoding="utf-8")
    runtime = (_ASSETS / "explorer.runtime.js").read_text(encoding="utf-8")
    page = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', "", page)
    page = page.replace("@STYLE@", "").replace("@ELK@", elk)
    head, _, tail = page.partition("@EXPLORER@")
    first = head.count("\n") + 1
    last = first + runtime.count("\n") + 1
    # The recorder is inserted before the runtime: it moves the first line of the runtime down.
    shift = _RECORDER.count("\n") + 1
    recorder = _RECORDER.replace("@FIRST@", str(first + shift - 1)).replace(
        "@LAST@", str(last + shift)
    )
    driver = _DRIVER.replace("@STEPS@", json.dumps(steps)).replace("@META@", _SINK_META)
    marker = '<script data-report-asset="explorer">'
    head = head[: head.rindex(marker)] + recorder + "\n" + head[head.rindex(marker) :]
    return head + runtime + tail.replace("</body>", driver + "</body>")


def run(fixture: str, steps: list[str]) -> tuple[str, list[str]]:
    """The normalized DOM after the steps, and the lines of the runtime whose sinks ran."""
    binary = chromium()
    if binary is None:
        raise SystemExit("no Chromium: set ARCHKEEL_CHROMIUM")
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "page.html"
        report.write_text(assemble(fixture, steps), encoding="utf-8")
        done = subprocess.run(
            [
                binary,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--virtual-time-budget={_BUDGET_MS}",
                "--dump-dom",
                report.as_uri(),
            ],
            capture_output=True,
            check=True,
            timeout=180,
            text=True,
        )
    meta = re.search(rf'<meta name="{_SINK_META}" content="([^"]*)">', done.stdout)
    sinks = json.loads(meta.group(1).replace("&quot;", '"')) if meta else []
    return normalize(done.stdout), sinks


def normalize(dom: str) -> str:
    """Drop the script and style text, the recorder note and the line ends of the dump."""
    dom = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", dom, flags=re.S)
    dom = re.sub(r"<style\b[^>]*>.*?</style>", "<style></style>", dom, flags=re.S)
    dom = re.sub(rf'<meta name="{_SINK_META}"[^>]*>', "", dom)
    dom = re.sub(r"(?:file://)?/[^\"'\s]*?/page\.html", "PAGE.html", dom)
    return dom.replace("\r\n", "\n").rstrip() + "\n"


def sinks() -> list[tuple[int, int]]:
    """Each place of the runtime that sets markup: the line and the column of the sink name."""
    lines = (_ASSETS / "explorer.runtime.js").read_text(encoding="utf-8").split("\n")
    return [
        (number, hit.start() + 1)
        for number, row in enumerate(lines, 1)
        for hit in re.finditer(r"innerHTML|insertAdjacentHTML", row)
    ]


def reached(found: list[str]) -> set[tuple[int, int]]:
    """The sinks that ran: each `line:column` that the recorder saw is the nearest sink before it."""
    places = sinks()
    result: set[tuple[int, int]] = set()
    for site in found:
        line, _, column = site.partition(":")
        before = [at for at in places if at[0] == int(line) and at[1] <= int(column)]
        if before:
            result.add(max(before))
    return result


if __name__ == "__main__":
    steps = sys.argv[2:]
    dom, found = run(sys.argv[1], steps)
    sys.stdout.write(dom)
    sys.stderr.write(json.dumps(found) + "\n")
