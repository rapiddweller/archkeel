# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: scope identity and serialized Studio startup."""

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_explore import _repository

import archkeel.analyzer.process as process_module
import archkeel.cli as cli
from archkeel.cli import arguments, launcher, studio
from archkeel.cli.launcher import StudioScope
from archkeel.ir.facts_codec import DEFAULT_RESPONSE_LIMIT_BYTES
from archkeel.studio.api import AgentKind


def test_windows_pid_liveness_never_uses_signal_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_os = SimpleNamespace(name="nt")
    fake_os.kill = lambda _pid, sig: pytest.fail(
        f"Windows liveness must not call os.kill with {sig=}"
    )
    kernel32 = SimpleNamespace(
        OpenProcess=lambda *_args: 123,
        WaitForSingleObject=lambda *_args: 258,
        CloseHandle=lambda *_args: True,
    )
    monkeypatch.setattr(process_module, "os", fake_os)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)

    assert launcher.is_process_alive(12345)


def test_windows_oversized_pid_is_unknown_without_probing_or_signaling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []

    def open_process(*args: object) -> int:
        calls.append(args)
        return 123

    fake_os = SimpleNamespace(
        name="nt",
        kill=lambda _pid, sig: pytest.fail(f"must not signal an oversized PID: {sig=}"),
    )
    kernel32 = SimpleNamespace(
        OpenProcess=open_process,
        WaitForSingleObject=lambda *_args: 258,
        CloseHandle=lambda *_args: True,
    )
    monkeypatch.setattr(process_module, "os", fake_os)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)

    assert launcher.is_process_alive((1 << 32) + 12345)
    assert calls == []


def test_unrepresentable_state_pid_is_never_signaled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    url = "http://127.0.0.1:1234/?token=verified"
    launcher.write_state(
        folder,
        launcher.StudioProcess(
            (1 << 32) + 12345,
            url,
            1234,
            str(tmp_path),
            "2026-11-05T00:00:00Z",
            stopping=True,
        ),
    )
    verified_urls: list[str] = []
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(launcher, "is_studio", lambda value: verified_urls.append(value) or True)
    monkeypatch.setattr(launcher, "is_process_alive", lambda _pid: True)
    monkeypatch.setattr(launcher, "_STOP_SECONDS", 0.01)
    monkeypatch.setattr(
        launcher,
        "os",
        SimpleNamespace(kill=lambda pid, sig: signals.append((pid, sig))),
    )

    launcher._stop_studio(folder)

    assert signals == []
    assert (folder / "studio.json").exists()
    assert verified_urls == []


@pytest.mark.parametrize(("platform", "maximum"), [("nt", (1 << 32) - 1), ("posix", (1 << 31) - 1)])
def test_process_id_validation_uses_native_width(
    monkeypatch: pytest.MonkeyPatch, platform: str, maximum: int
) -> None:
    monkeypatch.setattr(process_module, "os", SimpleNamespace(name=platform))

    assert process_module.is_safe_process_id(maximum)
    assert not process_module.is_safe_process_id(maximum + 1)
    assert not process_module.is_safe_process_id(1)


@pytest.mark.parametrize(("wait_result", "expected"), [(0, False), (258, True)])
def test_windows_pid_liveness_uses_synchronize_handle_and_closes_it(
    monkeypatch: pytest.MonkeyPatch, wait_result: int, expected: bool
) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class Function:
        def __init__(self, name: str, result: int | bool) -> None:
            self.name = name
            self.result = result

        def __call__(self, *args: object) -> int | bool:
            calls.append((self.name, args))
            return self.result

    kernel32 = SimpleNamespace(
        OpenProcess=Function("OpenProcess", 123),
        WaitForSingleObject=Function("WaitForSingleObject", wait_result),
        CloseHandle=Function("CloseHandle", True),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)

    monkeypatch.setattr(process_module, "os", SimpleNamespace(name="nt"))
    assert process_module.is_process_alive(12345) is expected
    assert calls == [
        ("OpenProcess", (0x00100000, False, 12345)),
        ("WaitForSingleObject", (123, 0)),
        ("CloseHandle", (123,)),
    ]


@pytest.mark.parametrize(("error", "expected"), [(5, True), (87, False), (1234, True)])
def test_windows_pid_liveness_treats_open_errors_conservatively(
    monkeypatch: pytest.MonkeyPatch, error: int, expected: bool
) -> None:
    kernel32 = SimpleNamespace(
        OpenProcess=lambda *_args: 0,
        WaitForSingleObject=lambda *_args: pytest.fail("no handle should be waited on"),
        CloseHandle=lambda *_args: pytest.fail("no handle should be closed"),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    monkeypatch.setattr(process_module, "os", SimpleNamespace(name="nt"))

    assert process_module.is_process_alive(12345) is expected


def _args(root: Path, *options: str) -> arguments.CLIArguments:
    return cli.build_parser().parse_cli_args(["studio", "--root", str(root), "--no-open", *options])


def test_a_different_scope_does_not_reuse_a_live_studio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    active = SimpleNamespace(
        root=str(root),
        url="http://127.0.0.1:1234/?token=active",
        scope=SimpleNamespace(language="python", sources=(), namespace=None, tsconfig=None),
        stopping=False,
    )
    monkeypatch.setattr(studio, "running_studio", lambda _folder: active)
    monkeypatch.setattr(
        studio, "studio_workspace", lambda *_args: pytest.fail("mismatch must not start a scan")
    )

    result = studio.serve_studio(
        _args(
            root,
            "--language",
            "typescript",
            "--source",
            "src",
            "--namespace",
            "shop",
            "--tsconfig",
            "tsconfig.json",
        )
    )

    output = capsys.readouterr().out
    assert result != 0
    assert "scope" in output.lower()
    assert "python" in output.lower()
    assert "typescript" in output.lower()
    assert "--stop" in output


def test_a_legacy_studio_without_scope_metadata_is_not_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    active = SimpleNamespace(
        root=str(root),
        url="http://127.0.0.1:1234/?token=active",
        scope=None,
        stopping=False,
    )
    monkeypatch.setattr(studio, "running_studio", lambda _folder: active)

    result = studio.serve_studio(_args(root))

    output = capsys.readouterr().out
    assert result != 0
    assert "scope" in output.lower()
    assert "--stop" in output


def test_a_legacy_scope_without_output_limit_remains_readable_with_unknown_scope(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    legacy = {
        "pid": os.getpid(),
        "url": "http://127.0.0.1:1234/?token=legacy",
        "port": 1234,
        "root": str(tmp_path),
        "started": "2026-11-05T00:00:00Z",
        "scope": {
            "language": "typescript",
            "sources": ["src"],
            "namespace": "shop",
            "tsconfig": "tsconfig.json",
            "agent": "claude",
        },
    }
    (folder / "studio.json").write_text(json.dumps(legacy))

    saved = launcher._read(folder)

    assert saved is not None
    assert saved.scope is None
    assert saved.pid == os.getpid()


def test_a_previous_explicit_scope_with_null_limit_means_the_default(tmp_path: Path) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    (folder / "studio.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": "http://127.0.0.1:1234/?token=legacy",
                "port": 1234,
                "root": str(tmp_path),
                "started": "2026-11-05T00:00:00Z",
                "scope": {
                    "language": "typescript",
                    "sources": ["src"],
                    "namespace": "shop",
                    "tsconfig": "tsconfig.json",
                    "agent": "claude",
                    "collector_output_limit_bytes": None,
                },
            }
        ),
        encoding="utf-8",
    )

    saved = launcher._read(folder)

    assert saved is not None
    assert saved.scope is not None
    assert saved.scope.collector_output_limit_bytes == DEFAULT_RESPONSE_LIMIT_BYTES


def test_a_scope_missing_optional_fields_and_with_an_unknown_field_is_unknown(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    (folder / "studio.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": "http://127.0.0.1:1234/?token=fake",
                "port": 1234,
                "root": str(tmp_path),
                "started": "2026-11-05T00:00:00Z",
                "scope": {
                    "language": "python",
                    "sources": [],
                    "namespace": None,
                    "tsconfig": None,
                    "future_scope_field": "unknown",
                },
            }
        ),
        encoding="utf-8",
    )

    process = launcher._read(folder)

    assert process is not None
    assert process.scope is None


@pytest.mark.parametrize("agent", [[], {}])
def test_a_non_string_agent_makes_only_the_scope_unknown(tmp_path: Path, agent: object) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    (folder / "studio.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": "http://127.0.0.1:1234/?token=fake",
                "port": 1234,
                "root": str(tmp_path),
                "started": "2026-11-05T00:00:00Z",
                "scope": {
                    "language": "python",
                    "sources": [],
                    "namespace": None,
                    "tsconfig": None,
                    "agent": agent,
                },
            }
        ),
        encoding="utf-8",
    )

    process = launcher._read(folder)

    assert process is not None
    assert process.scope is None


def test_a_different_chat_agent_does_not_reuse_a_live_studio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    active = SimpleNamespace(
        root=str(root),
        url="http://127.0.0.1:1234/?token=active",
        scope=StudioScope("python", (), None, None, AgentKind.CLAUDE),
        stopping=False,
    )
    monkeypatch.setattr(studio, "running_studio", lambda _folder: active)
    monkeypatch.setattr(
        studio, "studio_workspace", lambda *_args: pytest.fail("agent mismatch must not scan")
    )

    result = studio.serve_studio(_args(root, "--agent", "codex"))

    output = capsys.readouterr().out
    assert result != 0
    assert "claude" in output.lower()
    assert "codex" in output.lower()
    assert "--stop" in output


def test_a_different_collector_limit_does_not_reuse_a_live_studio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    active = SimpleNamespace(
        root=str(root),
        url="http://127.0.0.1:1234/?token=active",
        scope=StudioScope("typescript", ("src",), "shop", "tsconfig.json", AgentKind.CLAUDE, 1),
        stopping=False,
    )
    monkeypatch.setattr(studio, "running_studio", lambda _folder: active)
    monkeypatch.setattr(
        studio, "studio_workspace", lambda *_args: pytest.fail("limit mismatch must not scan")
    )

    result = studio.serve_studio(
        _args(
            root,
            "--language",
            "typescript",
            "--source",
            "src",
            "--namespace",
            "shop",
            "--tsconfig",
            "tsconfig.json",
            "--collector-output-limit-bytes",
            "104857600",
        )
    )

    output = capsys.readouterr().out
    assert result == 2
    assert "scope" in output.lower()
    assert "--stop" in output


@pytest.mark.parametrize("active_uses_default", [True, False])
def test_default_and_explicit_default_collector_limits_share_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    active_uses_default: bool,
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    active = SimpleNamespace(
        root=str(root),
        url="http://127.0.0.1:1234/?token=active",
        scope=(
            StudioScope("python", (), None, None, AgentKind.CLAUDE)
            if active_uses_default
            else StudioScope("python", (), None, None, AgentKind.CLAUDE, 64 * 1024 * 1024)
        ),
        stopping=False,
    )
    monkeypatch.setattr(studio, "running_studio", lambda _folder: active)
    monkeypatch.setattr(
        studio, "studio_workspace", lambda *_args: pytest.fail("equivalent scope must be reused")
    )

    options = (
        ("--collector-output-limit-bytes", str(64 * 1024 * 1024)) if active_uses_default else ()
    )
    result = studio.serve_studio(_args(root, *options))

    assert result == 0
    assert "already running" in capsys.readouterr().out


def test_a_timed_out_start_does_not_scan_and_reports_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(launcher, "STUDIO_LOCK_WAIT_SECONDS", 0.01)
    cache = cli.cache_folder(arguments.Command.EXPLORE, cli.root_digest(root.resolve()))
    monkeypatch.setattr(
        studio, "studio_workspace", lambda *_args: pytest.fail("a timed-out start must not scan")
    )

    with launcher.studio_lock(cache):
        result = studio.serve_studio(_args(root))

    error = capsys.readouterr().err
    assert result == 1
    assert "held the session lock for 0.01 seconds" in error
    assert "no session was started" in error


def test_a_timed_out_stop_does_not_signal_a_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(launcher, "STUDIO_LOCK_WAIT_SECONDS", 0.01)
    folder = tmp_path / "cache"
    monkeypatch.setattr(
        launcher, "_stop_studio", lambda *_args: pytest.fail("a timed-out stop must not signal")
    )

    with launcher.studio_lock(folder):
        result = launcher.stop_studio(folder)

    output = capsys.readouterr().out
    assert result == 1
    assert "held the session lock for 0.01 seconds" in output
    assert "no stop was sent" in output


def test_the_start_lock_is_held_until_http_service_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(launcher, "STUDIO_LOCK_WAIT_SECONDS", 0.01)
    cache = cli.cache_folder(arguments.Command.EXPLORE, cli.root_digest(root.resolve()))
    observed: list[str] = []

    def run_studio_stub(_workspace: object, *, ready, serving=None, **_kwargs: object) -> int:
        ready("http://127.0.0.1:1234/?token=fake")
        contender = launcher.studio_lock(cache)
        try:
            contender.acquire()
        except launcher.StudioLockTimeout:
            observed.append("held until serving")
        else:
            contender.release()
            pytest.fail("state publication released the lock before HTTP readiness")
        assert callable(serving), "the server must release the lock after it starts serving"
        serving()
        contender.acquire()
        contender.release()
        return 0

    monkeypatch.setattr(studio, "running_studio", lambda _folder: None)
    monkeypatch.setattr(studio, "studio_workspace", lambda *_args: object())
    monkeypatch.setattr(studio, "run_studio", run_studio_stub)

    assert studio.serve_studio(_args(root)) == 0
    assert observed == ["held until serving"]


def test_a_second_start_cannot_replace_state_before_http_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(launcher, "STUDIO_LOCK_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(studio, "running_studio", lambda _folder: None)
    workspaces: list[object] = []
    starts: list[int] = []

    def workspace(*_args: object) -> object:
        result = object()
        workspaces.append(result)
        return result

    def run_studio_stub(_workspace: object, *, ready, serving=None, **_kwargs: object) -> int:
        starts.append(1)
        ready("http://127.0.0.1:1234/?token=fake")
        if len(starts) == 1:
            nested_result = studio.serve_studio(_args(root))
            assert nested_result == 1
            assert callable(serving), "HTTP readiness must release the start lock"
            serving()
        return 0

    monkeypatch.setattr(studio, "studio_workspace", workspace)
    monkeypatch.setattr(studio, "run_studio", run_studio_stub)

    assert studio.serve_studio(_args(root)) == 0
    assert len(workspaces) == 1


def test_stop_does_not_report_not_running_before_http_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(launcher, "STUDIO_LOCK_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(studio, "running_studio", lambda _folder: None)
    monkeypatch.setattr(launcher, "running_studio", lambda _folder: None)

    def run_studio_stub(_workspace: object, *, ready, serving=None, **_kwargs: object) -> int:
        ready("http://127.0.0.1:1234/?token=fake")
        result = studio.serve_studio(_args(root, "--stop"))
        assert result == 1
        assert callable(serving), "HTTP readiness must release the start lock"
        serving()
        return 0

    monkeypatch.setattr(studio, "studio_workspace", lambda *_args: object())
    monkeypatch.setattr(studio, "run_studio", run_studio_stub)

    assert studio.serve_studio(_args(root)) == 0
    assert "no stop was sent" in capsys.readouterr().out


def test_stop_keeps_the_lock_until_workspace_cleanup_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(launcher, "STUDIO_LOCK_WAIT_SECONDS", 0.01)
    cache = cli.cache_folder(arguments.Command.EXPLORE, cli.root_digest(root.resolve()))
    cache.mkdir(parents=True)
    active = launcher.StudioProcess(
        os.getpid(),
        "http://127.0.0.1:1234/?token=fake",
        1234,
        str(root),
        "2026-11-05T00:00:00Z",
        StudioScope("python", (), None, None, AgentKind.CLAUDE),
    )
    launcher.write_state(cache, active)
    monkeypatch.setattr(launcher, "running_studio", lambda _folder: active)
    monkeypatch.setattr(launcher, "is_studio", lambda _url: True)
    monkeypatch.setattr(launcher.os, "kill", lambda *_args: None)
    monkeypatch.setattr(studio, "running_studio", lambda _folder: None)
    monkeypatch.setattr(
        studio, "studio_workspace", lambda *_args: pytest.fail("restart must wait for cleanup")
    )
    original_sleep = time.sleep
    restart_results: list[int] = []

    def slow_workspace_cleanup(_seconds: float) -> None:
        if not restart_results:
            restart_results.append(studio.serve_studio(_args(root)))
            launcher.forget_state(cache, active.pid)
        else:
            original_sleep(_seconds)

    monkeypatch.setattr(
        launcher,
        "time",
        SimpleNamespace(monotonic=time.monotonic, sleep=slow_workspace_cleanup),
    )

    assert launcher.stop_studio(cache) == 0
    assert restart_results == [1]


def test_a_timed_out_cleanup_keeps_state_and_denies_a_second_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repository(tmp_path / "shop")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(launcher, "_STOP_SECONDS", 0.01)
    monkeypatch.setattr(launcher, "is_studio", lambda _url: False)
    monkeypatch.setattr(launcher, "is_process_alive", lambda _pid: True)
    cache = cli.cache_folder(arguments.Command.EXPLORE, cli.root_digest(root.resolve()))
    cache.mkdir(parents=True)
    active = launcher.StudioProcess(
        os.getpid(),
        "http://127.0.0.1:1234/?token=fake",
        1234,
        str(root),
        "2026-11-05T00:00:00Z",
        StudioScope("python", (), None, None, AgentKind.CLAUDE),
        stopping=True,
    )
    launcher.write_state(cache, active)
    monkeypatch.setattr(
        studio, "studio_workspace", lambda *_args: pytest.fail("pending cleanup must not scan")
    )

    assert launcher.stop_studio(cache) == 1
    output = capsys.readouterr().out
    assert "still stopping" in output
    assert str(cache / "studio.json") in output
    assert "verify no ArchKeel Studio or Explore process" in output
    assert (cache / "studio.json").exists()
    assert studio.serve_studio(_args(root)) == 1
    start_output = capsys.readouterr().out
    assert "no new session was started" in start_output
    assert str(cache / "studio.json") in start_output
    assert "verify no ArchKeel Studio or Explore process" in start_output
    assert (cache / "studio.json").exists()


def test_a_dead_process_allows_stale_state_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    process = launcher.StudioProcess(
        12345,
        "http://127.0.0.1:1234/?token=fake",
        1234,
        str(tmp_path),
        "2026-11-05T00:00:00Z",
        stopping=True,
    )
    launcher.write_state(folder, process)
    monkeypatch.setattr(launcher, "is_studio", lambda _url: False)
    monkeypatch.setattr(launcher, "is_process_alive", lambda _pid: False)

    assert launcher.stop_studio(folder) == 0
    assert "not running" in capsys.readouterr().out
    assert not (folder / "studio.json").exists()


def test_a_verified_stop_persists_its_cleanup_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    process = launcher.StudioProcess(
        os.getpid(),
        "http://127.0.0.1:1234/?token=fake",
        1234,
        str(tmp_path),
        "2026-11-05T00:00:00Z",
    )
    launcher.write_state(folder, process)
    monkeypatch.setattr(launcher, "is_studio", lambda _url: True)
    monkeypatch.setattr(launcher.os, "kill", lambda *_args: None)
    monkeypatch.setattr(launcher, "is_process_alive", lambda _pid: True, raising=False)
    monkeypatch.setattr(launcher, "_STOP_SECONDS", 0.01)
    monkeypatch.setattr(
        launcher,
        "time",
        SimpleNamespace(monotonic=time.monotonic, sleep=lambda _seconds: None),
    )

    assert launcher.stop_studio(folder) == 1
    state = launcher._read(folder)
    assert state is not None
    assert state.stopping is True


def test_an_unmarked_foreign_live_pid_is_stale_without_http_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "cache"
    folder.mkdir()
    process = launcher.StudioProcess(
        os.getpid(),
        "http://127.0.0.1:1234/?token=foreign",
        1234,
        str(tmp_path),
        "2026-11-05T00:00:00Z",
    )
    launcher.write_state(folder, process)
    monkeypatch.setattr(launcher, "is_studio", lambda _url: False)
    monkeypatch.setattr(launcher, "is_process_alive", lambda _pid: True, raising=False)

    assert launcher.running_studio(folder) is None
    assert not (folder / "studio.json").exists()


def test_concurrent_starts_for_the_same_scope_create_one_studio(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path / "shop")
    cache = tmp_path / "cache"
    entered = tmp_path / "entered"
    go = tmp_path / "go"
    started = tmp_path / "started"
    release = tmp_path / "release"
    script = """
import os
import sys
import time
from pathlib import Path
from archkeel.cli import launcher, main, studio

entered = Path(__ENTER__)
go = Path(__GO__)
started = Path(__STARTED__)
release = Path(__RELEASE__)
with entered.open("a") as stream:
    stream.write("ready\\n")
while not go.exists():
    time.sleep(0.01)

original_running = studio.running_studio
def slow_running(folder):
    active = original_running(folder)
    if active is None:
        time.sleep(0.3)
    return active

launcher.is_studio = lambda _url: True
studio.running_studio = slow_running
def workspace(_args, _cache):
    with started.open("a") as stream:
        stream.write("created\\n")
    return object()

def run_studio(_workspace, *, ready, serving, idle_seconds, agent):
    url = f"http://127.0.0.1:{10000 + os.getpid() % 50000}/?token=fake"
    ready(url)
    serving()
    print(f"ArchKeel Studio: {url}\\nPress Ctrl-C to stop.", flush=True)
    while not release.exists():
        time.sleep(0.01)
    return 0

studio.studio_workspace = workspace
studio.run_studio = run_studio
sys.exit(main(["studio", "--root", __ROOT__, "--no-open"]))
"""
    for marker, path in (
        ("__ENTER__", entered),
        ("__GO__", go),
        ("__STARTED__", started),
        ("__RELEASE__", release),
        ("__ROOT__", root),
    ):
        script = script.replace(marker, repr(str(path)))

    env = {**os.environ, "XDG_CACHE_HOME": str(cache)}
    children = [
        subprocess.Popen(
            [sys.executable, "-c", script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        deadline = time.monotonic() + 10
        while (
            not entered.is_file() or len(entered.read_text().splitlines()) < 2
        ) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert entered.is_file() and len(entered.read_text().splitlines()) == 2
        go.touch()

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            count = len(started.read_text().splitlines()) if started.exists() else 0
            if count > 1 or (count == 1 and any(child.poll() is not None for child in children)):
                break
            time.sleep(0.01)
        assert started.is_file()
        assert len(started.read_text().splitlines()) == 1
        assert sum(child.poll() is not None for child in children) == 1
    finally:
        release.touch()
        outputs = []
        for child in children:
            try:
                outputs.append(child.communicate(timeout=10))
            except subprocess.TimeoutExpired:
                child.terminate()
                outputs.append(child.communicate(timeout=10))

    assert all(child.returncode == 0 for child in children), outputs
    assert sum("(already running)" in stdout for stdout, _stderr in outputs) == 1
