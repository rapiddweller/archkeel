// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `facts_codec.decode_response` in the host reads this reply, and the host compares
// `source_digest` with the Python collector, so the digests below come from Python.

use std::io::Read;

use flate2::read::ZlibDecoder;
use serde_json::Value;

use super::*;

fn input(path: &str, digest: char, role: Role) -> Input {
    Input {
        path: path.to_owned(),
        digest: digest.to_string().repeat(64),
        role,
    }
}

fn facts() -> Facts {
    Facts {
        provenance: Provenance {
            profile: "archkeel-typescript-imports",
            adapter_version: "0.0.0".to_owned(),
            code_digest: "d".repeat(64),
            runtime_name: "rust",
            runtime_version: "1.88.0".to_owned(),
            runtime_required: ">=1.88".to_owned(),
        },
        git_head: "a".repeat(40),
        dirty: Value::Bool(false),
        scope: vec!["src/**".to_owned()],
        sections: vec![("imports", vec![]), ("unknowns", vec![])],
        features: vec!["literal-imports"],
        inputs: vec![input("tsconfig.json", 'b', Role::Resolution)],
        files: vec![],
        imports: vec![],
        selected_files: vec![],
        files_read: 0,
        gaps: vec![],
        evidence: vec![],
    }
}

#[test]
fn source_digest_matches_the_python_listing() {
    // hashlib.sha256(json.dumps(listing, separators=(",", ":"), ensure_ascii=False)) in collect.py
    let inputs = [
        input("src/ü.ts", 'a', Role::Selected),
        input("tsconfig.json", 'b', Role::Resolution),
    ];
    assert_eq!(
        source_digest(&inputs),
        "0a71a1a9acb8b5509c38847c6205b452b90bf71e03343c8509d0956925e47ed3"
    );
    // The same listing with quotes, a backslash and control characters in the path.
    let escaped = [input(
        "a\"b\\c\n\u{1}\u{7f}\u{2028}é.ts",
        'c',
        Role::Selected,
    )];
    assert_eq!(
        source_digest(&escaped),
        "11151077fe35549194af69f47e5e4c411b03425df66b7ac01918cc32c51692f2"
    );
    // json.dumps([]) of a scan that read nothing.
    assert_eq!(
        source_digest(&[]),
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    );
}

#[test]
fn the_reply_is_zlib_framed_json_with_the_requested_version() {
    for version in [Version::V8, Version::V9] {
        let wire = encode(version, &facts()).unwrap();
        // The host reads a first byte 0x78 as the zlib frame of protocols 8.0.0 and 9.0.0.
        assert_eq!(wire[0], 0x78);
        let mut plain = String::new();
        ZlibDecoder::new(wire.as_slice())
            .read_to_string(&mut plain)
            .unwrap();
        let reply: Value = serde_json::from_str(&plain).unwrap();
        assert_eq!(reply["protocol_version"], version.as_str());
        assert_eq!(reply["provider_sources"], Value::Array(vec![]));
        let facts = reply["facts"].as_object().unwrap();
        assert_eq!(facts.len(), 16);
        assert_eq!(facts["adapter"]["name"], "archkeel-typescript-imports");
        assert_eq!(facts["coverage"]["full_scope"], true);
    }
}

#[test]
fn a_gap_makes_the_collection_partial() {
    let mut partial = facts();
    partial.gaps.push(Record {
        id: "UNKNOWN-1".to_owned(),
        evidence_class: "UNKNOWN",
        area: "source",
        kind: "collection_gap",
        title: "reason".to_owned(),
        subjects: vec![],
        evidence_ids: vec![],
        data: Map::new(),
    });
    let wire = encode(Version::V8, &partial).unwrap();
    let mut plain = Vec::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_end(&mut plain)
        .unwrap();
    let reply: Value = serde_json::from_slice(&plain).unwrap();
    assert_eq!(reply["facts"]["coverage"]["full_scope"], false);
}

#[test]
fn the_plain_version_3_reply_is_not_written() {
    assert!(encode(Version::V3, &facts()).is_err());
}

#[test]
fn a_target_has_the_fields_of_its_kind() {
    let targets = [
        Target::Local {
            import_id: "IMP-1".to_owned(),
            module: "app.b".to_owned(),
            file: "b.ts".to_owned(),
            runtime_file: Some("b.ts".to_owned()),
            declaration_file: None,
        },
        Target::External {
            import_id: "IMP-2".to_owned(),
            package: "react".to_owned(),
        },
        Target::Builtin {
            import_id: "IMP-3".to_owned(),
            name: "fs".to_owned(),
        },
        Target::Unresolved {
            import_id: "IMP-4".to_owned(),
            specifier: "x".to_owned(),
            reason: "Unresolved module: x".to_owned(),
        },
    ];
    let mut with_imports = facts();
    with_imports.imports = targets.to_vec();
    let wire = encode(Version::V8, &with_imports).expect("encodes");
    let mut plain = String::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_string(&mut plain)
        .expect("zlib");
    let reply: Value = serde_json::from_str(&plain).expect("JSON");
    let kinds: Vec<(&str, usize)> = reply["facts"]["imports"]
        .as_array()
        .expect("a list")
        .iter()
        .map(|item| {
            (
                item["kind"].as_str().expect("a kind"),
                item.as_object().expect("an object").len(),
            )
        })
        .collect();
    assert_eq!(
        kinds,
        [
            ("local", 6),
            ("external", 3),
            ("builtin", 3),
            ("unresolved", 4)
        ]
    );
    assert_eq!(
        reply["facts"]["imports"][0]["declaration_file"],
        Value::Null
    );
}
