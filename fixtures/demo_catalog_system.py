# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-307: a public greenfield system landscape Target demo."""

import json
from pathlib import Path

from fixtures.demo_catalog_support import Variant

SYSTEM_LANDSCAPE_FIXTURE_DIR = Path(__file__).resolve().parent / "F-system-landscape"
_DEMO_CONTRACT = json.loads(
    (SYSTEM_LANDSCAPE_FIXTURE_DIR / "architecture-contract.json").read_text(encoding="utf-8")
)
_DEMO_CONTRACT["components"] = [
    {
        "id": "landscape-demo-target",
        "label": "landscape demo target",
        "role": "component",
        "lifecycle": "planned",
        "packages": [],
        "responsibilities": ["Describe the greenfield target for the report demo."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
    }
]
_DEMO_FILES = {
    # The current report CLI requires a valid source scan. This empty package makes the demo
    # scan complete; it is not mapped to either declared runtime entity. The runner also requires
    # a component graph, so the overlay adds a separate planned report owner without linking it to
    # either runtime endpoint.
    "architecture-contract.json": json.dumps(_DEMO_CONTRACT, indent=2) + "\n",
    "archkeel.toml": (
        '[scan]\nroots = ["src"]\nnamespace = "system_manifest"\n'
        'contract = "architecture-contract.json"\n'
    ),
    "docs/target.md": (
        "# Target system\n\n"
        "The API service sends requests to the external ledger over HTTPS.\n\n"
        "<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n```\n"
    ),
    "pyproject.toml": '[project]\nname = "system-landscape-demo"\nrequires-python = ">=3.11"\n',
    "src/system_manifest/__init__.py": (
        "# Archkeel\n# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n"
        "# SPDX-License-Identifier: MIT\n\n"
    ),
}

VARIANTS = (
    Variant(
        id="system-landscape-greenfield",
        section="class_c",
        item="ContractDeclarations.uml",
        summary=(
            "A greenfield target declares an API runtime, an external ledger, and their directed "
            "communication; source comparison remains UNKNOWN."
        ),
        files=_DEMO_FILES,
        expected_violations=(),
        expected_codes=(),
        fixture=SYSTEM_LANDSCAPE_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
)
