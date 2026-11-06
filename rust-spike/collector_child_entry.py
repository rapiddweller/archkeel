"""Scratch-only entry point to test PyO3 inside the Python collector process."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


class RustUnsupportedSyntaxError(ValueError):
    """Identify a scratch parser rejection in collector coverage."""


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))

    extension = os.environ["ARCHKEEL_RUST_IMPORT_CORE_PATH"]
    target = os.environ["ARCHKEEL_RUST_PYTHON_TARGET"]
    spec = importlib.util.spec_from_file_location("_core", extension)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the scratch parser extension")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)

    from archkeel.analyzer.python import source
    from archkeel.analyzer.python.entry import main as collector_main

    parse_bounded = source._parse_bounded

    def parse_with_rust_target(text: str, filename: str):
        batch = json.loads(core.collect_import_batch_json(text, target))
        if batch["status"] != "COMPLETE" or not batch["complete"]:
            raise RustUnsupportedSyntaxError(batch["reason"])
        return parse_bounded(text, filename)

    source._parse_bounded = parse_with_rust_target
    return collector_main()


if __name__ == "__main__":
    raise SystemExit(main())
