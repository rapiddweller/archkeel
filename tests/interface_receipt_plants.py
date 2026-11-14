# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The TypeScript trees of the proof review of #1155 for the `interface_boundary` receipt (AD-480).

Each tree maps a relative path to its text. `EXPECTED` gives the row of release 4.0.1 on it.
"""

from __future__ import annotations

EXPECTED: dict[str, tuple[str, str]] = {
    "41-if-parent-package-unseen": ("a:IN-IF", "UNKNOWN"),
    "41b-if-parent-exact-nonexistent": ("a:IN-IF", "UNKNOWN"),
    "41c-if-inner-zero-module-comp": ("a:IN-IF", "UNKNOWN"),
    "41f-if-only-parent-package-unseen": ("a:IN-IF", "UNKNOWN"),
    "41h-if-inner-exact-nonexistent": ("a:IN-IF", "UNKNOWN"),
    "41i-if-hidden-violation-outside-roots": ("a:IN-IF", "UNKNOWN"),
    "42-root-if-package-unseen": ("ROOT-IF", "UNKNOWN"),
    "61-if-hidden-violation-overall": ("a:IN-IF", "UNKNOWN"),
    "62-root-if-hidden-violation": ("ROOT-IF", "UNKNOWN"),
}

PLANTS: dict[str, dict[str, str]] = {
    "41-if-parent-package-unseen": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a",\n'
        '    "app.gone"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "inside": "inside.json"\n'
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "REQUIRES",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "ax",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  },\n"
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-REQ",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "41b-if-parent-exact-nonexistent": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "inside": "inside.json",\n'
        '   "exact_modules": [\n'
        '    "app.src.zz.none_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "REQUIRES",\n'
        '   "kind": '
        '"complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "ax",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  },\n"
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-REQ",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "41c-if-inner-zero-module-comp": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "inside": "inside.json"\n'
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "REQUIRES",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "ax",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AZ",\n'
        '   "label": "az",\n'
        '   "packages": [\n'
        '    "app.src.a.z"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  },\n"
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-REQ",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "41f-if-only-parent-package-unseen": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": '
        '"2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a",\n'
        '    "app.gone"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "inside": "inside.json"\n'
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep '
        'it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "REQUIRES",\n'
        '   "kind": '
        '"complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "ax",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  }\n"
        " ]\n"
        "}",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "41h-if-inner-exact-nonexistent": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "inside": "inside.json"\n'
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "REQUIRES",\n'
        '   "kind": '
        '"complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "ax",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ],\n"
        '   "exact_modules": [\n'
        '    "app.src.a.y.none_x2e_ts"\n'
        "   ]\n"
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  },\n"
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-REQ",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "41i-if-hidden-violation-outside-roots": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": '
        '"2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": '
        '"component",\n'
        '   "responsibilities": '
        "[\n"
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a",\n'
        '    "app.lib.q"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "inside": '
        '"inside.json"\n'
        "  },\n"
        "  {\n"
        '   "role": '
        '"component",\n'
        '   "responsibilities": '
        "[\n"
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep '
        'it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": '
        '"architect",\n'
        '   "id": "REQUIRES",\n'
        '   "kind": '
        '"complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        "contract = "
        '"architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "ax",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AZ",\n'
        '   "label": "az",\n'
        '   "packages": [\n'
        '    "app.lib.q"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  },\n"
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-REQ",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "lib/q/h.ts": "import { secret } from '../../src/a/x/priv';\nexport const h = secret;\n",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/x/priv.ts": "export const secret = 2;\n",
        "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "42-root-if-package-unseen": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b",\n'
        '    "app.gone"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "a",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "ROOT-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  },\n"
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "REQUIRES",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": []\n'
        "}",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/b/t.ts": "import { one } from '../a/x/one';\nexport const t = one;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "61-if-hidden-violation-overall": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a",\n'
        '    "app.lib.q"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "inside": "inside.json"\n'
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        "   "
        '"forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": []\n'
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "ax",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AZ",\n'
        '   "label": "az",\n'
        '   "packages": [\n'
        '    "app.lib.q"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  }\n"
        " ]\n"
        "}",
        "lib/q/h.ts": "import { secret } from '../../src/a/x/priv';\nexport const h = secret;\n",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/x/priv.ts": "export const secret = 2;\n",
        "src/a/y/two.ts": "import { one } from '../x/one';\nexport const two = one;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
    "62-root-if-hidden-violation": {
        "README.md": "x\n",
        "architecture-contract.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "A",\n'
        '   "label": "a",\n'
        '   "packages": [\n'
        '    "app.src.a"\n'
        "   ],\n"
        '   "requires": [],\n'
        '   "public": [\n'
        '    "app.src.a.x.one_x2e_ts"\n'
        "   ]\n"
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "B",\n'
        '   "label": "b",\n'
        '   "packages": [\n'
        '    "app.src.b"\n'
        "   ],\n"
        '   "requires": []\n'
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": '
        "[],\n"
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "C",\n'
        '   "label": "c",\n'
        '   "packages": [\n'
        '    "app.lib.q"\n'
        "   ],\n"
        '   "requires": [\n'
        "    {\n"
        '     "component": "a",\n'
        '     "rationale": "Use it."\n'
        "    }\n"
        "   ]\n"
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "ROOT-IF",\n'
        '   "kind": "interface_boundary"\n'
        "  }\n"
        " ]\n"
        "}",
        "archkeel.toml": "[scan]\n"
        'language = "typescript"\n'
        'roots = ["src"]\n'
        'namespace = "app"\n'
        'contract = "architecture-contract.json"\n'
        'tsconfig = "tsconfig.json"\n',
        "inside.json": "{\n"
        ' "schema_version": "2.2.0",\n'
        ' "components": [\n'
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AX",\n'
        '   "label": "ax",\n'
        '   "packages": [\n'
        '    "app.src.a.x"\n'
        "   ],\n"
        '   "requires": []\n'
        "  },\n"
        "  {\n"
        '   "role": "component",\n'
        '   "responsibilities": [\n'
        '    "Own."\n'
        "   ],\n"
        '   "forbidden_responsibilities": [],\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "AY",\n'
        '   "label": "ay",\n'
        '   "packages": [\n'
        '    "app.src.a.y"\n'
        "   ],\n"
        '   "requires": []\n'
        "  }\n"
        " ],\n"
        ' "rules": [\n'
        "  {\n"
        '   "rationale": "Keep it.",\n'
        '   "provenance": [\n'
        '    "README.md"\n'
        "   ],\n"
        '   "decided_by": "architect",\n'
        '   "id": "IN-REQ",\n'
        '   "kind": "complete_requires"\n'
        "  }\n"
        " ]\n"
        "}",
        "lib/q/h.ts": "import { secret } from '../../src/a/x/priv';\nexport const h = secret;\n",
        "src/a/x/one.ts": "export const one = 1;\n",
        "src/a/x/priv.ts": "export const secret = 2;\n",
        "src/b/t.ts": "export const t = 1;\n",
        "tsconfig.json": '{"compilerOptions": {"strict": true}}\n',
    },
}
