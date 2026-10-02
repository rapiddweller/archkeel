# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small consumer fixture; validate against command-result.schema.json before consuming."""

import json
import sys


def main() -> None:
    result = json.load(sys.stdin)
    verdicts = " / ".join(
        result[key] for key in ("observation_complete", "declared_rules", "expectation_fulfilled")
    )
    print(f"{result['command']}: {verdicts}")


if __name__ == "__main__":
    main()
