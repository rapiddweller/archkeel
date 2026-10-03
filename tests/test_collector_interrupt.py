# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Candidate acceptance: Ctrl-C must clean the active collector tree and I/O workers."""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from test_collection_protocol import _request

from archkeel.ir.facts_codec import decode_request, encode_request


@pytest.mark.skipif(os.name != "posix", reason="this case asserts POSIX process-group cleanup")
def test_sigint_propagates_after_collector_tree_and_workers_stop(tmp_path: Path) -> None:
    collector_pid = tmp_path / "collector.pid"
    descendant_pid = tmp_path / "descendant.pid"
    heartbeat = tmp_path / "heartbeat"
    collector_heartbeat = tmp_path / "collector-heartbeat"
    result = tmp_path / "interrupt.json"

    descendant = (
        "import os,time\nfrom pathlib import Path\n"
        f"Path({str(descendant_pid)!r}).write_text(str(os.getpid()))\n"
        "count=0\nwhile True:\n"
        f"    Path({str(heartbeat)!r}).write_text(str(count))\n"
        "    count += 1\n    time.sleep(0.025)\n"
    )
    collector = (
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        f"Path({str(collector_pid)!r}).write_text(str(__import__('os').getpid()))\n"
        f"subprocess.Popen([sys.executable,'-B','-c',{descendant!r}], "
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        f"while not Path({str(heartbeat)!r}).exists(): time.sleep(0.005)\n"
        "count=0\nwhile True:\n"
        f"    Path({str(collector_heartbeat)!r}).write_text(str(count))\n"
        "    count += 1\n    time.sleep(0.025)\n"
    )
    host = (
        "import json,sys,threading\nfrom pathlib import Path\n"
        "from archkeel.analyzer.process import ProcessCollector\n"
        "from archkeel.ir.facts_codec import decode_request\n"
        "request=decode_request(sys.stdin.buffer.read())\n"
        f"try: ProcessCollector((sys.executable,'-B','-c',{collector!r})).collect(request)\n"
        "except KeyboardInterrupt:\n"
        "    workers = [t.name for t in threading.enumerate() "
        "if t is not threading.main_thread()]\n"
        f"    Path({str(result)!r}).write_text(json.dumps(workers))\n"
        "    sys.exit(0)\n"
        "sys.exit(3)\n"
    )
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    host_process = subprocess.Popen(
        [sys.executable, "-B", "-c", host],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    collector_group: int | None = None
    try:
        assert host_process.stdin is not None
        host_process.stdin.write(encode_request(request))
        host_process.stdin.close()
        ready_deadline = time.monotonic() + 5
        while time.monotonic() < ready_deadline and not (
            collector_pid.exists()
            and descendant_pid.exists()
            and heartbeat.exists()
            and collector_heartbeat.exists()
        ):
            if host_process.poll() is not None:
                pytest.fail(f"collector host exited before setup: {host_process.returncode}")
            time.sleep(0.01)
        assert (
            collector_pid.exists()
            and descendant_pid.exists()
            and heartbeat.exists()
            and collector_heartbeat.exists()
        ), "collector and detached-stdio descendant must be running before SIGINT"
        collector_group = int(collector_pid.read_text())
        os.kill(host_process.pid, signal.SIGINT)
        try:
            return_code = host_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pytest.fail("SIGINT did not propagate promptly; collector call remained blocked")
        assert return_code == 0, "the caller must observe KeyboardInterrupt from collect()"
        leaked_threads = json.loads(result.read_text())
        assert leaked_threads == [], f"collector I/O workers remain alive: {leaked_threads}"
        stopped = heartbeat.read_text()
        collector_stopped = collector_heartbeat.read_text()
        time.sleep(0.15)
        assert heartbeat.read_text() == stopped, "SIGINT left the detached-stdio descendant running"
        assert collector_heartbeat.read_text() == collector_stopped, (
            "SIGINT left the collector running"
        )
    finally:
        if host_process.poll() is None:
            os.killpg(host_process.pid, signal.SIGKILL)
            host_process.wait(timeout=2)
        if collector_group is not None:
            try:
                os.killpg(collector_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
