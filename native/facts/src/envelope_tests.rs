// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use serde_json::{json, Value};

use super::{Dirty, Reply, Target};

fn reply() -> Value {
    json!({
        "protocol_version": "9.0.0",
        "provider_sources": [],
        "facts": {
            "profile": "archkeel-typescript-imports",
            "adapter": {"name": "archkeel-typescript-imports", "version": "1", "code_digest": "0"},
            "runtime": {"name": "rust", "version": "1.88.0", "required": null,
                        "requirement_state": "declared"},
            "source": {"git_head": "a", "dirty": "unknown", "source_digest": "0", "scope": []},
            "capabilities": {"sections": ["imports", "unknowns"], "resolution_features": [],
                             "constructs": []},
            "inputs": [{"path": "src/a.ts", "digest": "0", "role": "selected"}],
            "files": [],
            "imports": [{"kind": "builtin", "import_id": "IMP-1", "name": "fs"}],
            "sections": [{"name": "imports", "records": []}, {"name": "unknowns", "records": []}],
            "coverage": {"selected_files": [], "files_read": 0, "files_parsed": 0,
                         "full_scope": true, "gaps": []},
            "evidence": [],
            "uncertain_reexports": [],
            "type_shapes": [],
            "state": {"classes": [], "functions": []},
            "candidate_evidence": [],
            "provider_bindings": []
        }
    })
}

#[test]
fn a_reply_envelope_decodes_and_encodes_equal() -> Result<(), serde_json::Error> {
    let decoded: Reply = serde_json::from_value(reply())?;
    assert_eq!(
        decoded.facts.source.dirty,
        Dirty::Unknown(super::UnknownDirty::Unknown)
    );
    assert!(matches!(decoded.facts.imports[0], Target::Builtin { .. }));
    assert_eq!(serde_json::to_value(&decoded)?, reply());
    Ok(())
}

#[test]
fn an_unknown_key_is_a_decode_error() {
    let mut value = reply();
    value["facts"]["coverage"]["extra"] = json!(1);
    assert!(serde_json::from_value::<Reply>(value).is_err());
}

#[test]
fn a_part_that_no_reader_types_must_be_empty() {
    for (part, entry) in [
        ("type_shapes", json!({"expression": "x", "shape": {}})),
        ("candidate_evidence", json!({})),
        ("provider_bindings", json!({})),
    ] {
        let mut value = reply();
        value["facts"][part] = json!([entry]);
        let error = serde_json::from_value::<Reply>(value)
            .err()
            .map(|e| e.to_string());
        assert!(
            error.is_some_and(|text| text.contains("does not read")),
            "{part}"
        );
    }
    let mut value = reply();
    value["facts"]["state"]["classes"] = json!([{}]);
    assert!(serde_json::from_value::<Reply>(value).is_err());
}

#[test]
fn a_protocol_before_8_is_not_a_compressed_reply() {
    let mut value = reply();
    value["protocol_version"] = json!("3.0.0");
    assert!(serde_json::from_value::<Reply>(value).is_err());
}
