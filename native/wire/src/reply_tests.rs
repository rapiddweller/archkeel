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
use crate::stream::encode;

fn input(path: &str, digest: char, role: Role) -> Input {
    Input {
        path: path.to_owned(),
        digest: digest.to_string().repeat(64),
        role,
    }
}

fn facts() -> Facts {
    Facts {
        provenance: Provenance::native(
            Profile::TypeScript,
            ("0.0.0", &"d".repeat(64)),
            ("1.88.0", "1.88"),
        ),
        git_head: "a".repeat(40),
        dirty: Value::Bool(false),
        scope: vec!["src/**".to_owned()],
        sections: vec![
            ReplySection::Typed(archkeel_facts::Section::Imports(vec![])),
            ReplySection::Records("unknowns", vec![]),
        ],
        features: vec!["literal-imports"],
        constructs: vec![],
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
        let wire = encode(version, facts()).unwrap();
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
    partial.gaps.push(archkeel_facts::Record::unknown(
        archkeel_facts::ids::FactId::new("UNKNOWN-1"),
        "reason",
        None,
        "",
        archkeel_facts::GapFact::collection("reason", ""),
    ));
    let wire = encode(Version::V8, partial).unwrap();
    let mut plain = Vec::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_end(&mut plain)
        .unwrap();
    let reply: Value = serde_json::from_slice(&plain).unwrap();
    assert_eq!(reply["facts"]["coverage"]["full_scope"], false);
}

#[test]
fn the_plain_version_3_reply_is_not_written() {
    assert!(encode(Version::V3, facts()).is_err());
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
    let mut with_imports = facts();
    with_imports.imports = targets.to_vec();
    let wire = encode(Version::V8, with_imports).expect("encodes");
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
fn every_source_section_and_the_construct_capability_have_a_place_in_the_reply() {
    let mut inner = facts();
    let record = |kind: &'static str| Record {
        id: format!("{kind}-1"),
        evidence_class: "FACT",
        area: "source",
        kind,
        title: kind.to_owned(),
        subjects: vec![],
        evidence_ids: vec![],
        fact_ids: vec!["ESM_EXPORT-1".to_owned()],
        data: Map::new(),
    };
    inner.sections = [
        "imports",
        "symbols",
        "calls",
        "references",
        "bindings",
        "constructs",
    ]
    .into_iter()
    .map(|name| ReplySection::Records(name, vec![record("kind")]))
    .collect();
    inner.constructs = vec![("string_literal_compare", "partial")];
    let wire = encode(Version::V9, inner).unwrap();
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
    assert_eq!(
        names,
        [
            "imports",
            "symbols",
            "calls",
            "references",
            "bindings",
            "constructs"
        ]
    );
    assert_eq!(
        facts["sections"][1]["records"][0]["fact_ids"][0],
        "ESM_EXPORT-1"
    );
    assert_eq!(
        facts["capabilities"]["constructs"][0],
        serde_json::json!({"name": "string_literal_compare", "status": "partial"})
    );
}

/// The plain JSON of the reply that `encode` writes for `facts`.
fn plain(version: Version, facts: Facts) -> String {
    let wire = encode(version, facts).unwrap();
    let mut plain = String::new();
    ZlibDecoder::new(wire.as_slice())
        .read_to_string(&mut plain)
        .unwrap();
    plain
}

#[test]
fn the_streamed_reply_decodes_through_the_envelope_and_encodes_to_the_same_value() {
    let mut full = facts();
    full.sections = vec![
        ReplySection::Typed(archkeel_facts::Section::Imports(vec![])),
        ReplySection::Typed(archkeel_facts::Section::Unknowns(vec![])),
    ];
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
    full.gaps = vec![archkeel_facts::Record::unknown(
        FactId::new("UNKNOWN-1"),
        "gap",
        Some("EVD-1"),
        "m",
        archkeel_facts::GapFact::resolution("gap", "m"),
    )];
    full.evidence = vec![Evidence::at("src/a.ts", 1, 2, 3, "x")];
    for version in [Version::V8, Version::V9] {
        let text = plain(version, full.clone());
        let decoded: Reply = serde_json::from_str(&text).unwrap();
        assert_eq!(decoded.protocol_version.as_str(), version.as_str());
        assert_eq!(decoded.facts.files, full.files);
        assert_eq!(decoded.facts.imports, full.imports);
        assert_eq!(decoded.facts.evidence, full.evidence);
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

/// The plain JSON of a reply that has one imports section.
fn imports_reply(section: ReplySection) -> String {
    let mut facts = facts();
    facts.sections = vec![section, ReplySection::Records("unknowns", vec![])];
    let mut plain = String::new();
    ZlibDecoder::new(encode(Version::V9, facts).unwrap().as_slice())
        .read_to_string(&mut plain)
        .unwrap();
    plain
}

/// AD-345: a typed import record of archkeel-facts writes the bytes of the record that the native
/// collector built with a map before (`imports.rs` up to this change).
#[test]
fn a_typed_import_section_writes_the_bytes_of_the_map_record() {
    use archkeel_facts::data::ImportData;
    use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
    use archkeel_facts::vocab::{Area, EvidenceClass};
    use archkeel_facts::ImportFact;

    let data = serde_json::json!({
        "source_module": "shop.a_x2e_ts", "source_package": "shop",
        "target_module": "react", "target_package": "react", "symbol": null, "binding": null,
        "symbols_known": false, "specifier": "react", "type_only": true, "relative_level": 0,
        "under_type_checking": true, "reexport": false, "module_level_import": true,
    });
    let plain = Record {
        id: "IMP-1".to_owned(),
        evidence_class: "FACT",
        area: "source",
        kind: "import_type",
        title: "shop.a_x2e_ts imports react".to_owned(),
        subjects: vec!["react".to_owned(), "shop.a_x2e_ts".to_owned()],
        evidence_ids: vec!["EVD-1".to_owned()],
        fact_ids: vec![],
        data: data.as_object().unwrap().clone(),
    };
    let typed = archkeel_facts::Record {
        id: FactId::new("IMP-1"),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: "shop.a_x2e_ts imports react".to_owned(),
        subjects: vec!["react".to_owned(), "shop.a_x2e_ts".to_owned()],
        evidence_ids: vec![EvidenceId::new("EVD-1")],
        fact_ids: vec![],
        data: ImportFact::ImportType(ImportData {
            source_module: ModuleName::new("shop.a_x2e_ts"),
            source_package: PackageName::new("shop"),
            target_module: ModuleName::new("react"),
            target_package: PackageName::new("react"),
            specifier: Some("react".to_owned()),
            type_only: Some(true),
            under_type_checking: true,
            module_level_import: true,
            ..ImportData::statement()
        }),
    };
    let typed = ReplySection::Typed(archkeel_facts::Section::Imports(vec![typed]));
    assert_eq!(
        imports_reply(typed),
        imports_reply(ReplySection::Records("imports", vec![plain]))
    );
}
