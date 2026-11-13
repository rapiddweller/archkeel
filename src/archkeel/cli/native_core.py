# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-390, AD-399: take the verdict of `archkeel report` and `archkeel check` from the Rust core,
stage 1.

The switch is `--native-core` or `ARCHKEEL_NATIVE_CORE=1`; it is off by default. With the switch,
the shell starts the verified `archkeel-core` binary of this install with the check request: the
contract and its inside contracts, the collector reply of the run, the scan roots and the
namespace. The request states no trust; the core derives it from the reply.

Stage 1: the Python engine still runs. When the frame of the core decides every rule, the shown
run status and rule statuses are the statuses of the core, and each must be the status of the
Python engine; a difference is a `CoreError` (exit 2). A PASS of the core for a rule that the
Python engine gives UNKNOWN is shown as such when the core names it beyond the reference (AD-384).
When the core names any part, the run is the run of the Python engine with one note that names
the reasons of the core.

`check` (AD-399) sends the candidate reply, the base reply and the contract at the baseline commit,
which the shell reads from Git. The shell also compares the exit code. The result of `check` shows
no rule rows: the command result schema of `check` has none, so the rows are only compared.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Final, TypeVar

from archkeel.check.git import read_blob
from archkeel.check.ports import Language, ScanConfig
from archkeel.ir.diagnostics import Diagnostic, DiagnosticKind
from archkeel.ir.model import RunResult

from .core_frame import (
    CoreError,
    CoreFrame,
    Gap,
    GapKind,
    RuleStatus,
    Status,
    Switch,
    read_frame,
)
from .native_scan import Scanned, exchange, scan
from .observe import NATIVE_STORE, verified_binary

CORE_BINARY: Final = "archkeel-core"
SWITCH_VARIABLE: Final = "ARCHKEEL_NATIVE_CORE"
PROTOCOL: Final = "archkeel-core-check-2"
# AD-379: the bounds of the inside contracts that the shell reads for the core
# (`native/core/src/contract.rs`). A chain of 900 mounts needs 900 rounds and a last one.
MAX_ROUNDS: Final = 901
MAX_FILES: Final = 1024
MAX_BYTES: Final = 64 << 20
_SUBJECT: Final = "native_core"
_Observer = TypeVar("_Observer")


class OverBudget(Exception):
    """The inside contracts hold more bytes than the shell reads."""


def read_inside(root: Path, path: str, budget: int) -> tuple[str, bytes] | None:
    """The resolved identity and the bytes of one inside contract, or `None` when the path is
    missing, not a file or outside the repository. A file larger than `budget` is refused."""
    repository = root.resolve()
    target = (repository / path).resolve()
    if not target.is_relative_to(repository) or not target.is_file():
        return None
    if target.stat().st_size > budget:
        raise OverBudget(path)
    data = target.read_bytes()
    if len(data) > budget:
        raise OverBudget(path)
    return target.relative_to(repository).as_posix(), data


def read_committed(root: Path, commit: str, path: str, budget: int) -> tuple[str, bytes] | None:
    """The identity and the bytes of one contract at `commit`, as `check` reads it (AD-399), or
    `None` when Git has no regular file at the path. A file larger than `budget` is refused."""
    try:
        # `read_blob` refuses an unsafe path, a missing path and a blob that is not a regular file
        # with `GitError`, a `ValueError`.
        data = read_blob(root, commit, path)
    except ValueError:
        return None
    if len(data) > budget:
        raise OverBudget(path)
    return PurePosixPath(path).as_posix(), data


# The identity and the bytes of a contract path within a byte budget, or `None` (AD-399).
ContractReader = Callable[[str, int], tuple[str, bytes] | None]


def switched_on(flag: bool, environ: Mapping[str, str]) -> bool:
    """The switch: the flag, or the variable set to 1. Another value of the variable is refused
    by name, so a typing error never reads as off."""
    value = environ.get(SWITCH_VARIABLE, "")
    try:
        switch = Switch(value)
    except ValueError as error:
        raise CoreError(f"{SWITCH_VARIABLE} must be 0 or 1, not {value!r}") from error
    return flag or switch is Switch.ON


@dataclass(frozen=True, slots=True)
class PythonRule:
    """One rule row of the Python engine, as the shell compares it."""

    rule: str
    status: RuleStatus
    count: int


@dataclass(frozen=True, slots=True)
class Decided:
    """The core decides every rule, and the Python engine agrees on each one."""

    frame: CoreFrame
    beyond: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FellBack:
    """The core names a part: the run is the run of the Python engine."""

    gaps: tuple[Gap, ...]


def stage_one(frame: CoreFrame, rules: Sequence[PythonRule], status: Status) -> Decided | FellBack:
    """The stage 1 rule of AD-390. A difference on any rule or on the run status raises."""
    if not frame.decided:
        return FellBack(frame.gaps)
    python = {row.rule: row for row in rules}
    differences: list[str] = []
    if only := sorted(python.keys() ^ frame.rules.keys()):
        differences.append(f"the rules {', '.join(only)} are in one engine only")
    beyond: list[str] = []
    for rule, verdict in sorted(frame.rules.items()):
        row = python.get(rule)
        if row is None:
            continue
        if rule in frame.beyond:
            # The frame reader holds each beyond rule to PASS; the reference must give UNKNOWN.
            if row.status is RuleStatus.UNKNOWN:
                beyond.append(rule)
            else:
                differences.append(f"{rule}: core beyond the reference, Python {row.status}")
        elif verdict.status is not row.status:
            differences.append(f"{rule}: core {verdict.status}, Python {row.status}")
        elif verdict.status is RuleStatus.FAIL and frame.violations.get(rule) != row.count:
            found = frame.violations.get(rule)
            differences.append(f"{rule}: core {found} violations, Python {row.count}")
    beyond_pass = frame.status is Status.PASS and status is Status.UNKNOWN and bool(beyond)
    if frame.status is not status and not beyond_pass:
        differences.append(f"the run: core {frame.status}, Python {status}")
    if differences:
        raise CoreError(
            "the core and the Python engine differ: " + "; ".join(differences) + ". "
            "Report this difference; the run has no verdict."
        )
    return Decided(frame, tuple(beyond))


@dataclass(slots=True)
class NativeCore:
    """The core of one run: the verified binary, or `None` with the switch off, and the raw
    collector replies of the run."""

    binary: str | None
    replies: list[bytes] = field(default_factory=list)
    # AD-406: the request payload that the shell sent to each collector of the run.
    requests: list[bytes] = field(default_factory=list)

    @staticmethod
    def requested(flag: bool, environ: Mapping[str, str]) -> NativeCore:
        """The core of the switch. With the switch on, a missing or changed binary is a
        `CoreError` before the scan starts; there is no fallback to the Python engine."""
        if not switched_on(flag, environ):
            return NativeCore(None)
        if environ.get(NATIVE_STORE):
            # The variable names a binary that decodes the reply for the Python engine; stage 1
            # compares with that engine, so no variable may redirect it (AD-390).
            raise CoreError(f"{NATIVE_STORE} redirects the decode of the reply; unset it")
        try:
            return NativeCore(verified_binary(CORE_BINARY).path)
        except LookupError as error:
            raise CoreError(f"the core binary is missing: {error}") from error
        except ValueError as error:
            raise CoreError(f"the core binary is not verified: {error}") from error

    def observer(self, factory: Callable[..., _Observer]) -> Callable[..., _Observer]:
        """The observer factory, with a sink for each raw collector reply when the switch is on.
        It verifies each bundled collector binary that the run starts (AD-390): a missing or stale
        digest file is a `CoreError`. With the switch off, the factory is the same object."""
        if self.binary is None:
            return factory
        verifying = partial(
            factory,
            reply_sink=self.replies.append,
            request_sink=self.requests.append,
            verify_bundled=True,
        )

        def verified(*arguments: object, **options: object) -> _Observer:
            try:
                return verifying(*arguments, **options)
            except LookupError as error:
                raise CoreError(f"a bundled collector is missing: {error}") from error
            except ValueError as error:
                raise CoreError(f"a bundled collector is not verified: {error}") from error

        return verified

    def run(
        self,
        binary: str,
        config: ScanConfig,
        read: ContractReader,
        reply: bytes,
        base: bytes | None,
    ) -> CoreFrame:
        """The frame of the last round: the core asks for each inside contract (AD-379). `read`
        reads the contract and each inside contract: the working tree for `report`, the baseline
        commit for `check` (AD-399)."""
        try:
            root_contract = read(config.contract, MAX_BYTES)
        except OverBudget as error:
            raise CoreError(f"the contract holds more than {MAX_BYTES} bytes") from error
        if root_contract is None:
            raise CoreError(f"the shell cannot read the contract {config.contract}")
        request: dict[str, object] = {
            "protocol": PROTOCOL,
            "contract": {"path": config.contract, "hex": root_contract[1].hex()},
            "insides": [],
            "reply": {"hex": reply.hex()},
            "roots": list(config.roots),
            "namespace": config.namespace,
            "base": None if base is None else {"reply": {"hex": base.hex()}},
        }
        sent: dict[str, dict[str, str]] = {}
        total = 0
        for _ in range(MAX_ROUNDS):
            frame = _send(binary, request)
            added = False
            for path in frame.missing:
                if path in sent:
                    continue
                if len(sent) >= MAX_FILES:
                    raise CoreError(f"the tree needs more than {MAX_FILES} inside contracts")
                try:
                    found = read(path, MAX_BYTES - total)
                except OverBudget as error:
                    raise CoreError(
                        f"the inside contracts hold more than {MAX_BYTES} bytes"
                    ) from error
                if found is not None:
                    identity, data = found
                    total += len(data)
                    sent[path] = {"reference": path, "identity": identity, "hex": data.hex()}
                    added = True
            if not added:
                # The frame names each path that the shell cannot read: a named gap.
                return frame
            request = {**request, "insides": list(sent.values())}
        raise CoreError(f"the tree needs more than {MAX_ROUNDS} rounds")

    def _unsent(
        self, result: RunResult, config: ScanConfig, replies: int, completed: frozenset[int]
    ) -> Gap | None:
        """The reason that the shell sends this run to no core, or `None`. `completed` holds the
        exit codes of a Python run that completed: 0 for `report`, 0 and 1 for `check`."""
        if config.collector_argv is not None:
            # A configured command can write any adapter and digest: the shell sends its reply to
            # no core, so the core never trusts it (AD-390).
            reason = f"the run uses the configured collector {config.collector_argv[0]}"
            return Gap(GapKind.EXTERNAL_COLLECTOR, "collector", reason)
        if result.exit_code not in completed or result.rule_assessments is None:
            reason = f"the Python run did not complete (exit {result.exit_code})"
            return Gap(GapKind.PYTHON_INCOMPLETE, "run", reason)
        if len(self.replies) != replies:
            reason = (
                f"the run has {len(self.replies)} collector replies, and the core reads {replies}"
            )
            return Gap(GapKind.REPLIES, "run", reason)
        return None

    def decide(
        self, result: RunResult, root: Path, config: ScanConfig, config_path: str = "archkeel.toml"
    ) -> RunResult:
        """The `report` result that the user gets under the stage 1 rule; with the switch off,
        `result`. A validation baseline adds evidence rows and changes no verdict (AD-399).

        AD-406: a linked profile first asks the core to run the collector itself (the scan
        request). A frame that decides every rule goes through the same stage 1 rule; anything
        else sends the run to the check request with the reply of the shell, as before."""
        if self.binary is None:
            return result
        if (gap := self._unsent(result, config, 1, frozenset({0}))) is not None:
            return _fell_back(result, (gap,))
        [reply] = self.replies
        rows, status = _python_rows(result), Status(result.declared_rules)
        gaps: tuple[Gap, ...] = ()
        if config.language in {Language.TYPESCRIPT, Language.RUST} and len(self.requests) == 1:
            scanned = scan(self.binary, self.requests[0], config_path)
            if not isinstance(scanned, Scanned):
                gaps = scanned
            elif isinstance(decided := stage_one(scanned.frame, rows, status), Decided):
                language = "Rust" if config.language == Language.RUST else "TypeScript"
                return _decided(result, decided, _SCAN_PARTS.format(language=language))
        frame = self.run(self.binary, config, partial(read_inside, root), reply, None)
        outcome = stage_one(frame, rows, status)
        if isinstance(outcome, FellBack):
            # A gap that both requests name is named one time.
            return _fell_back(result, tuple(dict.fromkeys((*gaps, *outcome.gaps))))
        return _decided(result, outcome, _scan_note(gaps))

    def decide_check(
        self, result: RunResult, root: Path, config: ScanConfig, baseline: str
    ) -> RunResult:
        """The `check` result under the stage 1 rule (AD-399). The core reads the candidate reply,
        the base reply and the contract at `baseline`. `result` has the rule rows of Python
        (`run_check(rule_rows=True)`); the shell compares them and shows none, as before."""
        shown = replace(result, rule_assessments=None)
        if self.binary is None:
            return shown
        if (gap := self._unsent(result, config, 2, frozenset({0, 1}))) is not None:
            return _fell_back(shown, (gap,))
        base, candidate = self.replies
        read = partial(read_committed, root, baseline)
        frame = self.run(self.binary, config, read, candidate, base)
        outcome = stage_one(frame, _python_rows(result), Status(result.declared_rules))
        if isinstance(outcome, FellBack):
            return _fell_back(shown, outcome.gaps)
        # The exit code reads the Git, host and expectation failures and the rule verdict.
        exit_code = 1 if result.failures or outcome.frame.status is Status.FAIL else 0
        if exit_code != result.exit_code:
            raise CoreError(
                f"the core and the Python engine differ: the exit code: core {exit_code}, "
                f"Python {result.exit_code}. Report this difference; the run has no verdict."
            )
        return replace(_decided(result, outcome, _CHECK_PARTS), rule_assessments=None)


def _python_rows(result: RunResult) -> tuple[PythonRule, ...]:
    return tuple(
        PythonRule(row.id, RuleStatus(row.status), row.count)
        for row in result.rule_assessments or ()
    )


def _send(binary: str, request: Mapping[str, object]) -> CoreFrame:
    return read_frame(*exchange(binary, "check", bytes(json.dumps(request), "utf-8")))


def _note(claim: str, remedy: str) -> Diagnostic:
    return Diagnostic(DiagnosticKind.NOT_EXAMINED, _SUBJECT, claim, remedy)


def _fell_back(result: RunResult, gaps: tuple[Gap, ...]) -> RunResult:
    reasons = "; ".join(f"{gap.subject}: {gap.reason}" for gap in gaps)
    note = _note(
        f"The core did not decide this run, so the verdict is the verdict of the Python engine. "
        f"The core names {len(gaps)} parts: {reasons}",
        "Run without --native-core, or wait for the slice that ports the named part (#880).",
    )
    return replace(result, notes=(*result.notes, note))


# AD-406: the run that the core decided with the collector in its own process.
_SCAN_PARTS: Final = (
    " The core ran the {language} collector in its own process (scan request, AD-406); the shell "
    "sent it no collector reply."
)


def _scan_note(gaps: tuple[Gap, ...]) -> str:
    """The reasons of the scan request when the check request decided the run instead."""
    if not gaps:
        return ""
    reasons = "; ".join(f"{gap.subject}: {gap.reason}" for gap in gaps)
    return f" The scan request (AD-406) did not decide: {reasons}"


# AD-399: what of a `check` run the core does not decide in stage 1.
_CHECK_PARTS: Final = (
    " The expectation over the architecture delta, the Git order and the host order are the "
    "verdicts of the Python engine."
)


def _decided(result: RunResult, decided: Decided, parts: str = "") -> RunResult:
    frame = decided.frame
    rows = tuple(
        replace(
            row,
            status=type(row.status)(frame.rules[row.id].status),
            reason=f"core decides, Python does not: {frame.beyond[row.id]}"
            if row.id in decided.beyond
            else row.reason,
        )
        for row in result.rule_assessments or ()
    )
    names = ", ".join(decided.beyond)
    beyond = f" The core decides {names} beyond the Python engine (AD-384)." if names else ""
    note = _note(
        f"The core decides every rule of this run ({frame.engine}), and the Python engine gives "
        f"the same verdict on each other rule.{beyond}{parts}",
        "Run without --native-core to see the verdict of the Python engine alone.",
    )
    return replace(
        result,
        declared_rules=type(result.declared_rules)(frame.status),
        rule_assessments=rows,
        notes=(*result.notes, note),
    )


def add_switch(parser: argparse.ArgumentParser) -> None:
    """Add `--native-core` to a command parser."""
    parser.add_argument(
        "--native-core",
        action="store_true",
        help=f"Take the rule verdicts from the Rust core when it decides every rule (stage 1, "
        f"AD-390, AD-399). Also {SWITCH_VARIABLE}=1. A difference to the Python engine exits 2.",
    )
