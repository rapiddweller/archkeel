// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The expected texts come from CPython 3.11 (`repr`, `parse_record`, `stable_id`).

use archkeel_facts::envelope::Evidence;
use archkeel_facts::ids::EvidenceId;
use serde_json::{json, Value};

use super::{binding_id, evidence, record, string};

fn repr(text: &str) -> String {
    let mut out = String::new();
    string(text, &mut out);
    out
}

#[test]
fn a_text_has_the_quotes_and_escapes_of_python_repr() {
    let cases = [
        ("plain", "'plain'"),
        ("it's", "\"it's\""),
        ("say \"hi\"", "'say \"hi\"'"),
        ("both ' and \"", "'both \\' and \"'"),
        ("tab\there\nnl\r", "'tab\\there\\nnl\\r'"),
        ("\u{0}\u{1f}\u{7f}", "'\\x00\\x1f\\x7f'"),
        ("back\\slash", "'back\\\\slash'"),
        ("nbsp\u{a0}x", "'nbsp\\xa0x'"),
        ("zwj\u{200d}x", "'zwj\\u200dx'"),
        ("emoji\u{1F600}", "'emoji\u{1F600}'"),
        ("tag\u{E0001}", "'tag\\U000e0001'"),
        ("\u{fc}\u{20ac}", "'\u{fc}\u{20ac}'"),
        ("\u{2028}", "'\\u2028'"),
    ];
    for (text, expected) in cases {
        assert_eq!(repr(text), expected, "{text:?}");
    }
}

fn wire() -> Value {
    json!({
        "id": "IMP-1", "evidence_class": "FACT", "area": "source", "kind": "import",
        "title": "a imports b", "subjects": ["a"], "evidence_ids": ["EVD-1"], "rule_ids": [],
        "fact_ids": [], "provenance": [],
        "data": {"z": [1, 2.5, null], "a": {"y": true, "b": ["only"]}, "s": "x'y"}
    })
}

fn entry() -> Evidence {
    Evidence {
        id: EvidenceId::new("EVD-1"),
        file: "src/a.ts".to_owned(),
        line: 1,
        end_line: 2,
        column: 0,
        excerpt: "import b from './b'".to_owned(),
    }
}

#[test]
fn a_record_is_written_as_the_python_record_of_parse_record() -> Result<(), String> {
    let Value::Object(map) = wire() else {
        return Err("not an object".to_owned());
    };
    let expected =
        "Record(id='IMP-1', evidence_class=<EvidenceClass.FACT: 'FACT'>, area='source', \
        kind='import', title='a imports b', subjects=('a',), evidence_ids=('EVD-1',), rule_ids=(), \
        fact_ids=(), provenance=(), data=RecordData(entries=(('a', RecordData(entries=(('b', \
        ('only',)), ('y', True)))), ('s', \"x'y\"), ('z', (1, 2.5, None)))))";
    assert_eq!(record(&map)?, expected);
    assert_eq!(
        evidence(&entry()),
        "Evidence(id='EVD-1', file='src/a.ts', line=1, end_line=2, column=0, \
         excerpt=\"import b from './b'\")"
    );
    Ok(())
}

#[test]
fn the_binding_id_is_the_stable_id_of_the_python_tuple() -> Result<(), String> {
    let Value::Object(map) = wire() else {
        return Err("not an object".to_owned());
    };
    let one = record(&map)?;
    assert_eq!(
        binding_id(std::slice::from_ref(&one), &[evidence(&entry())]),
        "DEPENDENCY-PROOF-19c48e2969f1aa51"
    );
    assert_eq!(
        binding_id(&[one.clone(), one], &[]),
        "DEPENDENCY-PROOF-5bd0f8f5e95f29d8"
    );
    Ok(())
}

#[test]
fn the_printable_table_is_sorted_and_disjoint() {
    assert_eq!(crate::printable::UNICODE_VERSION, "14.0.0");
    let ranges = super::ranges();
    assert_eq!(
        ranges.len(),
        crate::printable::HIDDEN.split_whitespace().count()
    );
    assert!(ranges
        .windows(2)
        .all(|pair| pair[0].0 <= pair[0].1 && pair[0].1 < pair[1].0));
}
