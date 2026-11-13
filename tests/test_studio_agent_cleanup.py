# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An exited macOS group leader can give EPERM until its parent reaps it."""

import errno
import os
import select
import signal
import subprocess
import sys
from unittest.mock import Mock, call

import pytest

from archkeel.studio import agent


def test_an_exited_group_leader_is_reaped_before_retry(monkeypatch):
    child = Mock(spec=subprocess.Popen, pid=4321)
    killpg = Mock(
        side_effect=[
            PermissionError(errno.EPERM, "zombie"),
            ProcessLookupError(),
            ProcessLookupError(),
        ]
    )
    monkeypatch.setattr(agent.os, "killpg", killpg, raising=False)
    agent._end(child)
    child.poll.assert_called_once_with()
    assert killpg.call_args_list == [
        call(4321, signal.SIGINT),
        call(4321, signal.SIGINT),
        call(4321, signal.SIGKILL),
    ]
    assert child.wait.call_count == 2


@pytest.mark.parametrize("interrupt_succeeds", [False, True])
def test_a_group_that_still_refuses_the_signal_fails_closed(monkeypatch, interrupt_succeeds):
    child = Mock(spec=subprocess.Popen, pid=4321)
    failures = [PermissionError(errno.EPERM, "denied"), PermissionError(errno.EPERM, "denied")]
    killpg = Mock(side_effect=[*([None] if interrupt_succeeds else []), *failures])
    monkeypatch.setattr(agent.os, "killpg", killpg, raising=False)
    with pytest.raises(PermissionError):
        agent._end(child)
    child.poll.assert_called_once_with()
    assert killpg.call_count == (3 if interrupt_succeeds else 2)


@pytest.mark.skipif(sys.platform != "darwin", reason="the macOS zombie process-group behavior")
def test_macos_reaps_the_exited_group_leader_before_cleanup():
    child = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    queue = select.kqueue()
    try:
        queue.control(
            [
                select.kevent(
                    child.pid,
                    filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                    fflags=select.KQ_NOTE_EXIT,
                )
            ],
            1,
            10,
        )
        assert child.returncode is None
        with pytest.raises(PermissionError):
            os.killpg(child.pid, signal.SIGINT)
        agent._end(child)
        assert child.returncode == 0
    finally:
        queue.close()
        child.wait()
