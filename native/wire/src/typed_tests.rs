// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The typed reply equals the decoded stream of the same head, sections and tail (AD-406).

use std::io::Read;

use flate2::read::ZlibDecoder;
use serde_json::Value;

use archkeel_facts::envelope::{Input, Profile, Provenance, Reply, Role};
use archkeel_facts::ids::FactId;
use archkeel_facts::{GapFact, ImportFact, Record};

use super::*;
use crate::stream::encode_stream;

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
        constructs: vec![("string_literal_compare", "partial")],
        inputs: vec![Input {
            path: "tsconfig.json".to_owned(),
            digest: "b".repeat(64),
            role: Role::Resolution,
        }],
        source_digest: None,
        files: vec![],
        imports: vec![],
    }
}

fn gap() -> Record<GapFact> {
    Record::unknown(
        FactId::new("UNKNOWN-1"),
        "reason",
        None,
        "",
        GapFact::collection("reason", ""),
    )
}

fn tail() -> Tail {
    Tail {
        selected_files: vec!["src/a.ts".to_owned()],
        files_read: 1,
        gaps: vec![gap()],
        evidence: vec![],
    }
}

fn decoded(version: Version) -> Reply {
    let mut bytes = Vec::new();
    encode_stream(version, head(), &mut bytes, |writer| {
        writer.write_typed_section::<ImportFact>(|_| {})?;
        writer.write_typed_section::<GapFact>(|emit| emit(&gap()))?;
        Ok(tail())
    })
    .unwrap();
    let mut plain = Vec::new();
    ZlibDecoder::new(bytes.as_slice())
        .read_to_end(&mut plain)
        .unwrap();
    serde_json::from_slice(&plain).unwrap()
}

fn typed(version: Version) -> Result<Reply, String> {
    assemble(version, head(), |sink| {
        sink.write_typed_section::<ImportFact>(|_| {})?;
        sink.write_typed_section::<GapFact>(|emit| emit(&gap()))?;
        Ok(tail())
    })
}

#[test]
fn the_typed_reply_equals_the_decoded_stream_value_and_bytes() {
    for version in [Version::V8, Version::V9] {
        let (typed, decoded) = (typed(version).unwrap(), decoded(version));
        assert_eq!(
            serde_json::to_vec(&typed).unwrap(),
            serde_json::to_vec(&decoded).unwrap()
        );
        assert_eq!(typed, decoded);
    }
}

#[test]
fn a_typed_reply_needs_each_declared_section_in_order() {
    let missing = assemble(Version::V8, head(), |sink| {
        sink.write_typed_section::<ImportFact>(|_| {})?;
        Ok(tail())
    });
    assert_eq!(
        missing.unwrap_err(),
        "cannot assemble the reply: a declared section was not given"
    );
    let swapped = assemble(Version::V8, head(), |sink| {
        sink.write_typed_section::<GapFact>(|_| {})?;
        Ok(tail())
    });
    assert!(swapped
        .unwrap_err()
        .contains("the section unknowns is not the next declared section"));
}

#[test]
fn version_3_has_no_typed_reply() {
    assert!(typed(Version::V3)
        .unwrap_err()
        .contains("no compressed reply for version 3.0.0"));
}
