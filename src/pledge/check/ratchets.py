"""Extent ratchets over the typed Python decoded-IR measurement profile."""

from pledge.ir.measurements import Measurements, RatchetError, RatchetScalars
from pledge.ir.model import Observation, Record

from .python_profile import crossing_imports


def _records(observation: Observation, section: str) -> tuple[Record, ...]:
    records = observation.records(section)
    if records is None:
        raise RatchetError(f"{section} must be a record list")
    return records


def _positions(value: object, label: str) -> int:
    if (
        not isinstance(value, tuple)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(set(value)) != len(value)
    ):
        raise RatchetError(f"{label} must be a non-empty list of distinct strings")
    return len(value)


def measure_python_ratchets(observation: Observation) -> Measurements:
    """Project raw counts; producer percentages never participate in the policy."""
    coverage = observation.coverage
    if (
        coverage.status != "PASS"
        or coverage.rules == "FAIL"
        or coverage.files_discovered == 0
        or coverage.failures
        or len({coverage.files_discovered, coverage.files_read, coverage.files_parsed}) != 1
    ):
        raise RatchetError("scan must be complete: discovered = read = parsed, without failures")
    total = coverage.calls_analyzed
    if (
        total
        != coverage.calls_resolved + coverage.calls_partially_resolved + coverage.calls_unresolved
    ):
        raise RatchetError("calls_analyzed must equal resolved + partially_resolved + unresolved")
    cycle_edges = sum(
        _positions(cycle.data.get("internal_edges"), "cycle.internal_edges")
        for cycle in _records(observation, "cycles")
    )
    typing_positions = 0
    for signal in _records(observation, "typing_signals"):
        if signal.kind == "missing_cross_package_annotation":
            typing_positions += _positions(signal.data.get("positions"), "typing_signal.positions")
        else:
            typing_positions += 1
    imports = _records(observation, "imports")
    for item in imports:
        symbol = item.data.get("symbol")
        source = item.data.get("source_package")
        target = item.data.get("target_package")
        if symbol is not None and not isinstance(symbol, str):
            raise RatchetError("import.symbol must be a string or null")
        if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
            raise RatchetError("import packages must be non-empty strings")
    return Measurements(
        scalars=RatchetScalars(
            violations=len(_records(observation, "violations")),
            cycle_edges=cycle_edges,
            private_crossings=len(crossing_imports(imports, private=True)),
            typing_positions=typing_positions,
            calls_unresolved=coverage.calls_unresolved,
            coverage_failures=len(coverage.failures),
        ),
        calls_total=total,
        resolution="measured" if total else "n/a",
    )


def compare_ratchets(accepted: Measurements, candidate: Measurements) -> tuple[str, ...]:
    """Compare validated measurements supplied by the caller, without rounding."""
    failures = [
        f"ratchet regression in {name}: {before}->{after}"
        for (name, before), (_, after) in zip(
            accepted.scalars.items(), candidate.scalars.items(), strict=True
        )
        if after > before
    ]
    if (
        accepted.calls_total > 0
        and candidate.calls_total > 0
        and candidate.scalars.calls_unresolved * accepted.calls_total
        > accepted.scalars.calls_unresolved * candidate.calls_total
    ):
        failures.append(
            "ratchet regression in unresolved_ratio: "
            f"{accepted.scalars.calls_unresolved}/{accepted.calls_total}->"
            f"{candidate.scalars.calls_unresolved}/{candidate.calls_total}"
        )
    return tuple(sorted(failures))
