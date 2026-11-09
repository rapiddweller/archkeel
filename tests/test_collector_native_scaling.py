# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323: the time of the native collector is linear in the size of each construct class.

Consumer: every later phase of the native collector, which reads the facts of the walk. The method
is a scaling matrix, not a list of shapes. For each construct class of `scaling_shapes.SHAPES` the
test builds a file with n and with 2n of the construct, times the CPU time of the collector process
(the minimum of three runs) and bounds time(2n) / time(n). Linear is about 2 and quadratic is about
4, so the bound is 3. A shape whose CPU time is below the measurable time of its profile doubles n
first, so that the start of the process does not hide the growth. The shapes that stress each loop
of the walk (the run of comments before a member, the frames above a write, the line before a
column) were quadratic once; the matrix fails on those versions (see AD-323).

The matrix times the CPU time of the child, not its wall time, so that a loaded runner does not
change the ratio (see `collector_timing.py`). The wall time is printed beside it for comparison.

Environment variables:

- `ARCHKEEL_SCALING_BINARY` names another collector, to run the matrix against an older build.
- `ARCHKEEL_SCALING_SCALE` multiplies every n. An older build that is quadratic needs a smaller n.
- `ARCHKEEL_SCALING_PROFILE` names the build of the binary under test: `debug` (the default) or
  `release`. It selects the time limits of `TIMINGS`. A release binary never reaches the debug
  limits before the file cap (`MAX_BYTES`), so the release limits are lower. Set it to `release`
  when `ARCHKEEL_SCALING_BINARY` is a release build.

A second test compares the dump with `parse.parse()` for each shape at small sizes, so that each
shape holds the construct that it claims.
"""

from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from collector_timing import Taken, interleaved_least, least_of, timed_run
from scaling_shapes import COVERAGE, FIELD_COVERAGE, KIND_CLASSES, NAME_ONLY, SHAPES, Shape
from test_collector_native_syntax import FIELDS, _native, compare, dump_binary  # noqa: F401

from archkeel.analyzer.typescript.syntax import Definition
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

# A file may not be larger than this: the collector reads at most 4 MiB (AD-319).
MAX_BYTES = 3_500_000
# The bound of time(2n) / time(n): linear is about 2, quadratic is about 4.
RATIO = 3.0
# A guard for a machine that is far too slow: the biggest case may not take longer.
CAP = 60.0
MAX_DOUBLINGS = 6


@dataclasses.dataclass(frozen=True)
class Timing:
    """The time limits of one build profile, in CPU seconds of the collector."""

    # A first size below this time doubles n, while the file of 4n is still at most MAX_BYTES.
    measurable: float
    # A first size below this time says that the shape is too cheap: the ratio would be noise.
    min_time: float


# Release runs are faster: the limits of the release profile are lower, see the docstring above.
# The release floor for `measurable` is 20 ms. A 10 ms run is too close to the start-up noise of
# the process, so a size could look measurable before its CPU time is large enough to compare.
TIMINGS = {
    "debug": Timing(measurable=0.25, min_time=0.1),
    "release": Timing(measurable=0.02, min_time=0.01),
}


def timing_for_profile() -> Timing:
    """The limits of `ARCHKEEL_SCALING_PROFILE`: `debug` by default, or `release`."""
    profile = os.environ.get("ARCHKEEL_SCALING_PROFILE", "debug")
    if profile not in TIMINGS:
        raise ValueError(f"ARCHKEEL_SCALING_PROFILE must be debug or release, not {profile!r}")
    return TIMINGS[profile]


@pytest.fixture(scope="session")
def collector(native_binary: Path) -> Path:
    other = os.environ.get("ARCHKEEL_SCALING_BINARY")
    return Path(other) if other else native_binary


def _request(root: Path) -> bytes:
    return encode_request(
        CollectionRequest(
            SnapshotInput(str(root), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings("tsconfig.json", False),
            ProtocolVersion.V8,
        )
    )


CONFIG = '{"compilerOptions":{"allowJs":true},"include":["src"]}'


def _prepare(root: Path, shape: Shape, n: int) -> Path:
    """Write the file of `shape` with n constructs into a root of its own, and return the root."""
    case = root / f"n{n}"
    (case / "src").mkdir(parents=True, exist_ok=True)
    (case / "tsconfig.json").write_text(CONFIG)
    (case / "src" / f"a{shape.suffix}").write_bytes(shape.make(n))
    return case


def _run(binary: Path, case: Path) -> Taken:
    """One run of the collector on the prepared root `case`."""
    wall, cpu, done = timed_run(
        [str(binary)],
        _request(case),
        preexec_fn=_limit_address_space if sys.platform == "linux" else None,
    )
    assert done.returncode == 0, done.stderr[-300:]
    return Taken(cpu=cpu, wall=wall)


def _sample(binary: Path, root: Path, shape: Shape, n: int) -> Taken:
    """One run of the collector with n constructs, for the size search."""
    return _run(binary, _prepare(root, shape, n))


def measure(binary: Path, root: Path, shape: Shape, timing: Timing) -> tuple[int, Taken, Taken]:
    """`(n, taken(n), taken(2n))` with the least n whose CPU time is measurable.

    The search takes one run of n per step. The last search run of n seeds the n side of the final
    pair, so the pair costs 2 * RUNS runs and the whole measure costs one run more than before.
    """
    n = max(1, int(shape.base * float(os.environ.get("ARCHKEEL_SCALING_SCALE", "1"))))
    first = _sample(binary, root, shape, n)
    for _ in range(MAX_DOUBLINGS):
        # The file of 2n after the doubling must still be readable: 4n of the old n.
        if first.cpu >= timing.measurable or len(shape.make(4 * n)) > MAX_BYTES:
            break
        n *= 2
        first = _sample(binary, root, shape, n)
    # The final pair is interleaved, so that a slow phase of the runner hits both sizes (AD-323).
    cases = {n: _prepare(root, shape, n), 2 * n: _prepare(root, shape, 2 * n)}
    small, large = interleaved_least(lambda size: _run(binary, cases[size]), n, 2 * n, seed=first)
    return n, small, large


# The peak memory of the collector, in bytes, for nests that write many names. The memo of the write
# lookup once kept n squared entries (1.5 GB for 8 000 undeclared names, 3.7 GB for 8 000 imported
# names written at the bottom of 8 000 functions, release build), against under 300 MiB for 4.2.
MEMORY_CAP = 300 * 1024 * 1024
MEMORY_CASES = (
    ("writes-distinct-names", 8_000),
    ("writes-imports-all-at-bottom", 4_000),
    ("writes-import-at-own-depth", 4_000),
)
# A process may not take more address space than this on Linux (the limit of AD-319), so a
# regression ends in an error and not in minutes of swapping. macOS has no such limit, and the
# sizes above are small enough to end there.
ADDRESS_SPACE = 4 * 1024**3
_RUSAGE = (
    "import resource, subprocess, sys\n"
    "subprocess.run([sys.argv[1]], stdin=open(sys.argv[2], 'rb'), stdout=subprocess.DEVNULL,"
    " check=True)\n"
    "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)\n"
)


def _limit_address_space() -> None:
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE, ADDRESS_SPACE))


def _peak_memory(tmp_path: Path, collector: Path, name: str, count: int) -> int:
    """The peak resident memory of the collector, in bytes, for the file of `name` and `count`."""
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"allowJs":true},"include":["src"]}'
    )
    (tmp_path / "src").mkdir(exist_ok=True)
    for old in (tmp_path / "src").iterdir():
        old.unlink()
    (tmp_path / "src" / f"a{SHAPES[name].suffix}").write_bytes(SHAPES[name].make(count))
    request = tmp_path / "request.bin"
    request.write_bytes(_request(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", _RUSAGE, str(collector), str(request)],
        capture_output=True,
        text=True,
        check=False,
        preexec_fn=_limit_address_space if sys.platform == "linux" else None,
    )
    assert done.returncode == 0, done.stderr[-300:]
    # `ru_maxrss` is in kilobytes on Linux and in bytes on macOS.
    return int(done.stdout) * (1 if sys.platform == "darwin" else 1024)


@pytest.mark.parametrize(("name", "count"), MEMORY_CASES)
def test_writes_keep_the_memory_bounded(
    tmp_path: Path, collector: Path, name: str, count: int
) -> None:
    peak = _peak_memory(tmp_path, collector, name, count)
    assert peak < MEMORY_CAP, f"{name} n={count}: {peak / 2**20:.0f} MiB"


# The sites keep a chain, a path or a range of bytes for each node, and never a copy of the names
# above them. The shapes that stress each of these: a union of names for each site (n nested arrow
# functions with n sites at the bottom), a path for each member of a chain, the receiver text of
# each call of a chain, and the frames above each name. Their memory is bounded by a ratio: the
# peak for 2n is at most 2.5 times the peak for n (linear growth is below 2 with the fixed cost of
# the process; quadratic growth is 4).
MEMORY_GROWTH = 2.5
SITE_MEMORY_CASES = (
    ("sites-shadow-nest-arrows", 4_000),
    ("sites-calls-in-arrow-nest", 3_000),
    ("sites-many-shadowed-names", 30_000),
    ("sites-member-chain-call", 100_000),
    ("sites-chained-calls", 40_000),
    ("sites-computed-access", 100_000),
    ("sites-comparison-wrappers", 30_000),
    ("sites-publication-chain", 30_000),
    ("sites-many-bound-names", 8_000),
    ("sites-calls-at-depth", 8_000),
    ("sites-after-comment-run", 200_000),
    ("sites-script-wrapper-nest", 8_000),
)


@pytest.mark.parametrize(("name", "count"), SITE_MEMORY_CASES)
def test_sites_keep_the_memory_linear(
    tmp_path: Path, collector: Path, name: str, count: int
) -> None:
    first = _peak_memory(tmp_path, collector, name, count)
    second = _peak_memory(tmp_path, collector, name, 2 * count)
    print(f"MEMORY {name} n={count} {first / 2**20:.0f} MiB 2n {second / 2**20:.0f} MiB")
    assert second < MEMORY_CAP, f"{name} n={2 * count}: {second / 2**20:.0f} MiB"
    assert second <= MEMORY_GROWTH * first, (
        f"{name}: n={count} {first / 2**20:.0f} MiB, 2n {second / 2**20:.0f} MiB"
    )


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_time_grows_linearly_with_the_size(tmp_path: Path, collector: Path, name: str) -> None:
    timing = timing_for_profile()
    n, first, second = measure(collector, tmp_path, SHAPES[name], timing)
    # The wall ratio is printed for comparison only; the assertion uses the CPU time.
    print(
        f"SCALING {name} n={n} t(n)={first.cpu:.3f} t(2n)={second.cpu:.3f} "
        f"ratio={second.cpu / first.cpu:.2f} wall_ratio={second.wall / first.wall:.2f}"
    )
    ratio = second.cpu / first.cpu
    assert len(SHAPES[name].make(2 * n)) <= MAX_BYTES, (
        f"{name}: the file is too large for n={2 * n}"
    )
    assert first.cpu >= timing.min_time, (
        f"{name}: {first.cpu:.3f} s CPU for n={n} is too short to measure"
    )
    assert second.cpu < CAP, f"{name}: {second.cpu:.1f} s CPU for n={2 * n}"
    assert ratio < RATIO, (
        f"{name}: n={n} {first.cpu:.3f} s, 2n {second.cpu:.3f} s CPU, ratio {ratio:.2f}"
    )


def test_the_timing_follows_the_build_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCHKEEL_SCALING_PROFILE", raising=False)
    assert timing_for_profile() == Timing(measurable=0.25, min_time=0.1)
    monkeypatch.setenv("ARCHKEEL_SCALING_PROFILE", "release")
    assert timing_for_profile() == Timing(measurable=0.02, min_time=0.01)
    monkeypatch.setenv("ARCHKEEL_SCALING_PROFILE", "fast")
    with pytest.raises(ValueError, match="fast"):
        timing_for_profile()


def test_the_least_of_three_runs_keeps_the_least_cpu_and_the_least_wall() -> None:
    samples = iter([Taken(cpu=0.3, wall=2.0), Taken(cpu=0.1, wall=3.0), Taken(cpu=0.2, wall=1.0)])
    assert least_of(lambda: next(samples)) == Taken(cpu=0.1, wall=1.0)


def test_the_interleaved_pair_alternates_the_sizes_and_keeps_the_least() -> None:
    order: list[int] = []
    samples = {
        10: iter([Taken(cpu=0.3, wall=2.0), Taken(cpu=0.1, wall=3.0), Taken(cpu=0.2, wall=1.0)]),
        20: iter([Taken(cpu=0.6, wall=5.0), Taken(cpu=0.7, wall=4.0), Taken(cpu=0.5, wall=6.0)]),
    }

    def fake(size: int) -> Taken:
        order.append(size)
        return next(samples[size])

    small, large = interleaved_least(fake, 10, 20)
    assert order == [10, 20, 10, 20, 10, 20]
    assert small == Taken(cpu=0.1, wall=1.0)
    assert large == Taken(cpu=0.5, wall=4.0)


def test_a_seed_joins_the_small_side_without_a_run() -> None:
    order: list[int] = []

    def fake(size: int) -> Taken:
        order.append(size)
        return Taken(cpu=0.4, wall=0.4)

    small, _ = interleaved_least(fake, 10, 20, seed=Taken(cpu=0.05, wall=9.0))
    assert order == [10, 20, 10, 20, 10, 20]
    assert small == Taken(cpu=0.05, wall=0.4)


@pytest.mark.skipif(sys.platform == "win32", reason="the CPU time of a child needs Unix")
def test_the_timer_counts_the_cpu_of_the_child_not_its_sleep() -> None:
    wall, cpu, _ = timed_run([sys.executable, "-c", "import time; time.sleep(0.5)"], b"")
    assert wall >= 0.5
    assert cpu < 0.1


@pytest.mark.skipif(sys.platform == "win32", reason="the CPU time of a child needs Unix")
def test_the_timer_counts_only_its_own_child_cpu() -> None:
    """A second child that burns CPU and ends inside the timed window is not counted.

    The burner runs in a thread and burns 0.5 s of CPU time, not a fixed amount of work, so a slow
    runner gives it the same CPU. The test fails unless the burner ends before the timed child.
    A timer that reads the CPU of all children would count the burner.
    """
    burn = (
        "import time\n"
        "start = time.process_time()\n"
        "while time.process_time() - start < 0.5: pass\n"
        "print(time.process_time() - start)\n"
    )
    burned: list[subprocess.CompletedProcess[bytes]] = []
    ended: list[float] = []

    def run_burner() -> None:
        burned.append(subprocess.run([sys.executable, "-c", burn], capture_output=True, check=True))
        ended.append(time.perf_counter())

    burner = threading.Thread(target=run_burner)
    burner.start()
    try:
        begin = time.perf_counter()
        _, cpu, done = timed_run([sys.executable, "-c", "import time; time.sleep(1.5)"], b"")
    finally:
        burner.join()
    end = time.perf_counter()
    assert done.returncode == 0
    assert len(burned) == 1, "the burner did not finish, so the test proves nothing"
    assert float(burned[0].stdout) >= 0.5, "the burner did not burn its CPU time"
    assert ended[0] < end, "the burner ended after the timed child, so it was not in the window"
    assert begin < ended[0], "the burner ended before the window began"
    assert cpu < 0.2, f"the timer counted {cpu:.2f} s of CPU that is not the sleeping child's"


@pytest.mark.skipif(sys.platform == "win32", reason="the CPU time of a child needs Unix")
def test_a_hung_child_fails_at_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("collector_timing.CHILD_TIMEOUT", 0.3)
    begin = time.perf_counter()
    with pytest.raises(pytest.fail.Exception, match="ran more than 0.3 s and was killed"):
        timed_run([sys.executable, "-c", "import time; time.sleep(60)"], b"")
    assert time.perf_counter() - begin < 10


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_each_shape_equals_the_python_parser_at_small_sizes(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
    name: str,
) -> None:
    shape = SHAPES[name]
    files = []
    for count in (1, 3, 12):
        path = tmp_path / f"s{count}{shape.suffix}"
        path.write_bytes(shape.make(count))
        files.append((f"src/{path.name}", path))
    result = compare(dump_binary, files)
    assert result.native_failed == []
    assert result.differences == [], "\n".join(result.differences[:10])
    assert result.python_failed == 0


def _kinds() -> list[str]:
    source = (Path(__file__).parents[1] / "native/typescript/src/kinds.rs").read_text()
    body = source[source.index("pub enum K {") :].split("\n}\n", 1)[0]
    return re.findall(r"^    (\w+),", body, flags=re.MULTILINE)


def test_every_shape_the_table_names_exists() -> None:
    named = {name for shapes in (*COVERAGE.values(), *FIELD_COVERAGE.values()) for name in shapes}
    assert sorted(named - SHAPES.keys()) == []
    # A shape that no class names holds no construct that anyone promised.
    assert sorted(SHAPES.keys() - named) == []


def test_every_kind_of_the_port_is_in_one_construct_class_with_shapes() -> None:
    kinds = [kind for kind in _kinds() if kind != "Other"]
    assert len(kinds) > 100
    placed = [kind for names in KIND_CLASSES.values() for kind in names]
    assert sorted(set(kinds) - set(placed)) == [], "a kind of kinds.rs has no construct class"
    assert sorted(set(placed) - set(kinds)) == [], "a class names a kind that does not exist"
    assert len(placed) == len(set(placed)), "a kind is in two classes"
    assert KIND_CLASSES.keys() <= COVERAGE.keys()
    assert all(COVERAGE[name] for name in KIND_CLASSES)


def test_every_fact_and_every_definition_field_has_shapes() -> None:
    fields = {field.name for field in dataclasses.fields(Definition)}
    assert sorted((set(FIELDS) | fields) - FIELD_COVERAGE.keys()) == []
    assert sorted(FIELD_COVERAGE.keys() - (set(FIELDS) | fields)) == []


def test_a_shape_holds_the_kinds_that_its_class_claims(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
) -> None:
    """The dump lists the node kinds of each file. Each shape is run at n = 3."""
    files = []
    for name, shape in SHAPES.items():
        path = tmp_path / f"{name}{shape.suffix}"
        path.write_bytes(shape.make(3))
        files.append((f"src/{path.name}", path))
    replies = _native(dump_binary, files)
    seen = {name: set(reply["kinds"]) for name, reply in zip(SHAPES, replies, strict=True)}
    problems = []
    for construct, kinds in KIND_CLASSES.items():
        shapes = COVERAGE[construct]
        held = set().union(*(seen[shape] for shape in shapes))
        problems += [
            f"{construct}: no shape holds {kind}" for kind in kinds if kind not in held | NAME_ONLY
        ]
        problems += [
            f"{construct}: {shape} holds none of its kinds"
            for shape in shapes
            if not seen[shape] & set(kinds)
        ]
    assert problems == []
    # A name-only kind is one that no shape holds.
    assert sorted(kind for kind in NAME_ONLY if any(kind in kinds for kinds in seen.values())) == []
