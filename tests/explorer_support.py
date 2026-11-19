# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Drive the Explorer of a written report page in a headless Chrome (Wave 2, E6).

The driver speaks the Chrome DevTools protocol over `--remote-debugging-pipe`, so it needs no
package beyond the standard library and the Chrome that the page script test already uses. A
local HTTP server serves the pages: history, the query and localStorage then act as on a site.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import http.server
import json
import os
import re
import select
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
CHROME_APP = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
READY = "document.getElementById('flow')?.dataset.layoutState === 'ready'"


def chrome() -> str:
    """The path of a Chrome; skip without one, but fail on CI where one must exist."""
    found = os.environ.get("CHROME") or next(
        (path for name in CHROME_NAMES if (path := shutil.which(name))), None
    )
    found = found or (CHROME_APP if Path(CHROME_APP).is_file() else None)
    if found is None:
        if os.environ.get("CI"):
            pytest.fail("no Chrome on this runner: the Explorer cannot be started")
        pytest.skip("no Chrome on this machine; set CHROME to its path")
    return found


def write_pages(
    core: Path, folder: Path, runs: dict[str, tuple[str | None, str, *tuple[str, ...]]]
) -> None:
    """Write `<name>.html` into the folder for each run (root, config, more arguments)."""
    from core_support import ROOT, run  # noqa: PLC0415 - the test path holds core_support

    from archkeel.cli import core_only  # noqa: PLC0415

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: core)
        for name, (root, config, *more) in runs.items():
            run(
                "report",
                *("--root", str(ROOT / root if root else ROOT)),
                *("--config", config, *more, "--output", str(folder / f"{name}.html")),
            )


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass


@contextlib.contextmanager
def serve(folder: Path) -> Iterator[str]:
    """The base URL of a local server for the files of the folder."""
    handler = functools.partial(_Quiet, directory=str(folder))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class BrowserError(RuntimeError):
    """The browser answered a command with an error, or the page threw."""


class Browser:
    """One headless Chrome with one page, driven over the DevTools pipe."""

    def __init__(self, profile: Path, *, width: int = 1440, height: int = 900) -> None:
        import fcntl  # noqa: PLC0415 - POSIX only; no test on Windows drives a browser

        to_chrome_read, self._to_chrome = os.pipe()
        self._from_chrome, from_chrome_write = os.pipe()

        def child() -> None:
            # Chrome reads commands on fd 3 and writes replies on fd 4.
            high_read = fcntl.fcntl(to_chrome_read, fcntl.F_DUPFD, 10)
            high_write = fcntl.fcntl(from_chrome_write, fcntl.F_DUPFD, 10)
            os.dup2(high_read, 3)
            os.dup2(high_write, 4)

        self._process = subprocess.Popen(  # noqa: S603 - a fixed Chrome command line
            [
                chrome(),
                "--headless=new",
                "--remote-debugging-pipe",
                "--disable-gpu",
                "--no-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={profile}",
                f"--window-size={width},{height}",
                "about:blank",
            ],
            preexec_fn=child,  # noqa: PLW1509 - the pipe fds must be 3 and 4 in the child
            close_fds=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.close(to_chrome_read)
        os.close(from_chrome_write)
        self._buffer = b""
        self._next = 0
        self._events: list[dict[str, Any]] = []
        target = next(
            item
            for item in self._call("Target.getTargets")["targetInfos"]
            if item["type"] == "page"
        )
        self._session = self._call(
            "Target.attachToTarget", targetId=target["targetId"], flatten=True
        )["sessionId"]
        for domain in ("Page", "Runtime"):
            self.send(f"{domain}.enable")
        self.send(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=False,
        )

    # ---- protocol ----
    def _write(self, message: dict[str, Any]) -> None:
        os.write(self._to_chrome, json.dumps(message).encode() + b"\0")

    def _read(self, timeout: float) -> dict[str, Any] | None:
        while b"\0" not in self._buffer:
            ready, _, _ = select.select([self._from_chrome], [], [], timeout)
            if not ready:
                return None
            chunk = os.read(self._from_chrome, 1 << 20)
            if not chunk:
                raise BrowserError("Chrome closed the DevTools pipe")
            self._buffer += chunk
        message, self._buffer = self._buffer.split(b"\0", 1)
        return json.loads(message)

    def _call(self, method: str, session: str | None = None, **params: Any) -> dict[str, Any]:
        self._next += 1
        ident = self._next
        message: dict[str, Any] = {"id": ident, "method": method, "params": params}
        if session:
            message["sessionId"] = session
        self._write(message)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            reply = self._read(deadline - time.monotonic())
            if reply is None:
                break
            if reply.get("id") == ident:
                if "error" in reply:
                    raise BrowserError(f"{method}: {reply['error']}")
                return reply.get("result", {})
            if "method" in reply:
                self._events.append(reply)
        raise BrowserError(f"{method}: no reply in 60 s")

    def send(self, method: str, **params: Any) -> dict[str, Any]:
        """Send one command to the page and return its result."""
        return self._call(method, self._session, **params)

    # ---- page ----
    def evaluate(self, expression: str) -> Any:
        """The value of a JavaScript expression in the page; a promise is awaited."""
        result = self.send(
            "Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            text = details.get("exception", {}).get("description") or details.get("text")
            raise BrowserError(f"{expression[:80]}: {text}")
        return result["result"].get("value")

    def wait(self, expression: str, timeout: float = 60.0) -> Any:
        """Wait until the expression is truthy in the page; return its value."""
        deadline = time.monotonic() + timeout
        value = None
        while time.monotonic() < deadline:
            with contextlib.suppress(BrowserError):
                value = self.evaluate(expression)
                if value:
                    return value
            time.sleep(0.05)
        raise BrowserError(f"timed out waiting for {expression}: last value {value!r}")

    def settle(self) -> None:
        """Wait until the Explorer finished its layout and two frames were painted."""
        self.wait(READY)
        self.evaluate(
            "new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))"
        )
        self.wait(READY)

    def open(self, url: str) -> None:
        """Load a page and wait for the Explorer."""
        self.send("Page.navigate", url=url)
        self.wait("document.readyState === 'complete'")
        self.settle()

    def color_scheme(self, scheme: str) -> None:
        """Emulate the operating system colour scheme: "light" or "dark"."""
        self.send(
            "Emulation.setEmulatedMedia",
            features=[{"name": "prefers-color-scheme", "value": scheme}],
        )

    def press(self, key: str, *, code: str | None = None, modifiers: int = 0) -> None:
        """Press one key on the focused element (modifiers: 1 Alt, 2 Ctrl, 4 Meta, 8 Shift)."""
        codes = {"Enter": 13, "Escape": 27, "ArrowUp": 38, "ArrowDown": 40, " ": 32}
        common = {
            "key": key,
            "code": code or ("Space" if key == " " else key),
            "modifiers": modifiers,
            "windowsVirtualKeyCode": codes.get(key, ord(key[0].upper())),
        }
        text = {"text": key} if len(key) == 1 else {}
        self.send("Input.dispatchKeyEvent", type="keyDown", **common, **text)
        self.send("Input.dispatchKeyEvent", type="keyUp", **common)

    def screenshot(self, path: Path) -> None:
        """Write a PNG of the visible page."""
        data = self.send("Page.captureScreenshot", format="png")["data"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))

    # ---- Explorer ----
    def state(self) -> dict[str, Any]:
        """`window.ArchkeelFlow.state()` without the scene, plus the URL query and what is drawn."""
        return self.evaluate(
            "(() => { const { scene, ...s } = window.ArchkeelFlow.state();"
            " return { ...s, view: s.viewMode, search: location.search,"
            " details: document.getElementById('flow').dataset.detailsOpen === 'true',"
            " theme: document.documentElement.dataset.theme }; })()"
        )

    def close(self) -> None:
        with contextlib.suppress(OSError, BrowserError):
            self._call("Browser.close")
        with contextlib.suppress(subprocess.TimeoutExpired):
            self._process.wait(timeout=10)
        if self._process.poll() is None:
            self._process.kill()
            self._process.wait()
        for fd in (self._to_chrome, self._from_chrome):
            with contextlib.suppress(OSError):
                os.close(fd)


@contextlib.contextmanager
def browser(profile: Path, **size: int) -> Iterator[Browser]:
    """One Browser that is closed at the end."""
    driven = Browser(profile, **size)
    try:
        yield driven
    finally:
        driven.close()


def shell_layer_frames(site: str, page: Browser, folder: Path) -> dict[str, Any]:
    """Read the shell's module frames with enough cards to exercise ungrouped layout."""
    import urllib.request  # noqa: PLC0415

    report = urllib.request.urlopen(f"{site}/system.html").read().decode()  # noqa: S310
    report, replacements = re.subn(r'("module_box_limit":)\d+', r"\g<1>100", report, count=1)
    assert replacements == 1
    (folder / "system.html").write_text(report)
    with serve(folder) as fixture:
        page.open(f"{fixture}/system.html?scope=PART%3Ashell&content=modules")
        frames = page.evaluate(
            "[...document.querySelectorAll('#flow svg .uml-frame')].map((g) => {"
            " const r = g.querySelector('.target-frame').getBoundingClientRect();"
            " return { id: g.dataset.umlId, label: g.dataset.label,"
            " box: [r.left, r.top, r.right, r.bottom] }; })"
        )
    return {frame["id"]: frame for frame in frames}
