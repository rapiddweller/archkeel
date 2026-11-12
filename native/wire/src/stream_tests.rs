// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `facts_codec.decode_response` in the host reads this reply, and the host compares
// `source_digest` with the Python collector, so the digests below come from Python.

use std::io::Read;

use flate2::read::ZlibDecoder;
use serde_json::Value;

use archkeel_facts::envelope::{source_digest, Profile, Reply, Role};
use archkeel_facts::ids::{FactId, ModuleName, PackageName};

use super::*;
use crate::protocol::Version;
use archkeel_facts::{GapFact, ImportFact};

fn input(path: &str, digest: char, role: Role) -> Input {
    Input {
        path: path.to_owned(),
        digest: digest.to_string().repeat(64),
        role,
    }
}

fn head() -> Head {
    Head {
        provenance: Provenance::native(
            Profile::TypeScript,
            ("0.0.0", &"d".repeat(64)),
            ("1.88.0", "1.88"),
        ),
        git_head: "a".repeat(40),
        dirty: Value::Bool(false),
        scope: vec!["src/**".to_owned()],
        sections: vec!["imports", "unknowns"],
        features: vec!["literal-imports"],
        constructs: vec![],
        inputs: vec![input("tsconfig.json", 'b', Role::Resolution)],
        source_digest: None,
        files: vec![],
        imports: vec![],
    }
}

fn tail() -> Tail {
    Tail {
        selected_files: vec![],
        files_read: 0,
        gaps: vec![],
        evidence: vec![],
    }
}

/// The reply of a head and a tail, with the two sections that `head` declares and no record.
fn encode(version: Version, head: Head, tail: Tail) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    encode_stream(version, head, &mut bytes, |writer| {
        writer.write_typed_section::<ImportFact>(|_| {})?;
        writer.write_typed_section::<GapFact>(|_| {})?;
        Ok(tail)
    })?;
    Ok(bytes)
}

/// The plain JSON of a reply.
fn plain(version: Version, head: Head, tail: Tail) -> String {
    let mut plain = String::new();
    ZlibDecoder::new(encode(version, head, tail).unwrap().as_slice())
        .read_to_string(&mut plain)
        .unwrap();
    plain
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
        let wire = encode(version, head(), tail()).unwrap();
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
    let mut partial = tail();
    partial.gaps.push(archkeel_facts::Record::unknown(
        archkeel_facts::ids::FactId::new("UNKNOWN-1"),
        "reason",
        None,
        "",
        archkeel_facts::GapFact::collection("reason", ""),
    ));
    let wire = encode(Version::V8, head(), partial).unwrap();
    let mut plain = Vec::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_end(&mut plain)
        .unwrap();
    let reply: Value = serde_json::from_slice(&plain).unwrap();
    assert_eq!(reply["facts"]["coverage"]["full_scope"], false);
}

#[test]
fn the_plain_version_3_reply_is_not_written() {
    assert!(encode(Version::V3, head(), tail()).is_err());
}

#[test]
fn a_target_has_the_fields_of_its_kind() {
    let targets = [
        Target::Local {
            import_id: FactId::new("IMP-1"),
            module: ModuleName::new("app.b"),
            file: "b.ts".to_owned(),
            runtime_file: Some("b.ts".to_owned()),
            declaration_file: None,
        },
        Target::External {
            import_id: FactId::new("IMP-2"),
            package: PackageName::new("react"),
        },
        Target::Builtin {
            import_id: FactId::new("IMP-3"),
            name: "fs".to_owned(),
        },
        Target::Unresolved {
            import_id: FactId::new("IMP-4"),
            specifier: "x".to_owned(),
            reason: "Unresolved module: x".to_owned(),
        },
    ];
    let mut with_imports = head();
    with_imports.imports = targets.to_vec();
    let wire = encode(Version::V8, with_imports, tail()).expect("encodes");
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

#[test]
fn the_construct_capability_has_a_place_in_the_reply() {
    let mut inner = head();
    inner.constructs = vec![("string_literal_compare", "partial")];
    let wire = encode(Version::V9, inner, tail()).unwrap();
    let mut plain = String::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_string(&mut plain)
        .unwrap();
    let reply: Value = serde_json::from_str(&plain).unwrap();
    let facts = &reply["facts"];
    let names: Vec<&str> = facts["sections"]
        .as_array()
        .unwrap()
        .iter()
        .map(|section| section["name"].as_str().unwrap())
        .collect();
    assert_eq!(names, ["imports", "unknowns"]);
    assert_eq!(
        facts["capabilities"]["constructs"][0],
        serde_json::json!({"name": "string_literal_compare", "status": "partial"})
    );
}

#[test]
fn a_section_that_the_head_does_not_declare_next_is_an_error() {
    let mut bytes = Vec::new();
    let result = encode_stream(Version::V9, head(), &mut bytes, |writer| {
        writer.write_typed_section::<GapFact>(|_| {})?;
        Ok(tail())
    });
    assert!(result.is_err());
}

#[test]
fn the_streamed_reply_decodes_through_the_envelope_and_encodes_to_the_same_value() {
    let mut full = head();
    full.constructs = vec![("string_literal_compare", "partial")];
    full.files = vec![FileFact::of(
        ("src/a.ts", "ns.src.a"),
        false,
        "EVD-1".to_owned(),
    )];
    full.imports = vec![Target::Builtin {
        import_id: FactId::new("IMP-1"),
        name: "fs".to_owned(),
    }];
    let mut last = tail();
    last.gaps = vec![archkeel_facts::Record::unknown(
        FactId::new("UNKNOWN-1"),
        "gap",
        Some("EVD-1"),
        "m",
        archkeel_facts::GapFact::resolution("gap", "m"),
    )];
    last.evidence = vec![Evidence::at("src/a.ts", 1, 2, 3, "x")];
    for version in [Version::V8, Version::V9] {
        let text = plain(version, full.clone(), last.clone());
        let decoded: Reply = serde_json::from_str(&text).unwrap();
        assert_eq!(decoded.protocol_version.as_str(), version.as_str());
        assert_eq!(decoded.facts.files, full.files);
        assert_eq!(decoded.facts.imports, full.imports);
        assert_eq!(decoded.facts.evidence, last.evidence);
        assert_eq!(decoded.facts.coverage.files_parsed, 1);
        assert!(!decoded.facts.coverage.full_scope);
        assert_eq!(
            decoded.facts.source.source_digest,
            source_digest(&full.inputs)
        );
        assert_eq!(
            serde_json::to_value(&decoded).unwrap(),
            serde_json::from_str::<Value>(&text).unwrap()
        );
    }
}

#[test]
fn a_given_source_digest_replaces_the_digest_of_the_listing() {
    let mut given = head();
    given.source_digest = Some("e".repeat(64));
    let decoded: Reply = serde_json::from_str(&plain(Version::V10, given, tail())).unwrap();
    assert_eq!(decoded.facts.source.source_digest, "e".repeat(64));
    let listed: Reply = serde_json::from_str(&plain(Version::V10, head(), tail())).unwrap();
    assert_eq!(
        listed.facts.source.source_digest,
        source_digest(&head().inputs)
    );
}
