# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The version gates of the graph and report schemas: a field that a later version added is
invalid in an earlier one."""

from __future__ import annotations


def graph_gates() -> list[dict[str, object]]:
    return [
        {
            "if": {"properties": {"schema_version": {"enum": ["1.0.0", "1.1.0"]}}},
            "then": {
                "properties": {"component_intents": {"items": {"not": {"required": ["layer"]}}}}
            },
        },
        {
            "if": {"properties": {"schema_version": {"enum": ["1.0.0", "1.1.0", "1.2.0"]}}},
            "then": {
                "properties": {"component_intents": {"items": {"not": {"required": ["lifecycle"]}}}}
            },
        },
        {
            # AD-351: the entity kind macro came after 1.2.0.
            "if": {"properties": {"schema_version": {"enum": ["1.0.0", "1.1.0", "1.2.0"]}}},
            "then": {
                "properties": {
                    "entities": {"items": {"properties": {"kind": {"not": {"const": "macro"}}}}}
                }
            },
        },
        {
            "if": {"properties": {"schema_version": {"const": "1.3.0"}}},
            "then": {
                "properties": {
                    "component_intents": {
                        "items": {
                            "allOf": [
                                {
                                    "if": {
                                        "required": ["lifecycle"],
                                        "properties": {"lifecycle": {"const": "planned"}},
                                    },
                                    "then": {
                                        "properties": {
                                            "packages": {"maxItems": 0},
                                            "exact_modules": {"maxItems": 0},
                                            "public": {"maxItems": 0},
                                        }
                                    },
                                },
                                {
                                    "if": {
                                        "properties": {
                                            "packages": {"maxItems": 0},
                                            "exact_modules": {"maxItems": 0},
                                        }
                                    },
                                    "then": {"required": ["lifecycle"]},
                                },
                            ]
                        }
                    }
                }
            },
        },
    ]


def report_gates() -> list[dict[str, object]]:
    return [
        {
            "if": {"properties": {"schema_version": {"const": "1.0.0"}}},
            "then": {
                "properties": {
                    key: {
                        "not": {
                            "type": "object",
                            "properties": {"schema_version": {"enum": ["1.2.0", "1.3.0"]}},
                            "required": ["schema_version"],
                        }
                    }
                    for key in ("observed", "target")
                }
            },
        },
        {
            "if": {"properties": {"schema_version": {"const": "1.2.0"}}},
            "then": {
                "properties": {
                    key: {
                        "not": {
                            "type": "object",
                            "properties": {"schema_version": {"const": "1.3.0"}},
                            "required": ["schema_version"],
                        }
                    }
                    for key in ("observed", "target")
                }
            },
        },
    ]
