// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Tests of the amendment codec and the binding (AD-375). The parity test in `tests/` compares
//! each decision and each written byte with Python; these tests name the rules.

use serde_json::{json, Value};

use crate::policy::amendment::blank;
use crate::policy::binding::absent_contract_digest;
use crate::policy::{
    amendment_bytes, assemble_tree, bind, parse_amendment, AmendmentError, AmendmentField,
    Baselines, ContractTree, GateStatus, OldContract,
};

const ROOT: &str = "architecture-contract.json";

fn digest(character: char) -> String {
    character.to_string().repeat(64)
}

fn document() -> Value {
    json!({
        "schema_version": "2.0.0",
        "before_digest": digest('a'),
        "after_digest": digest('b'),
        "decided_by": "Jordan",
        "rationale": "Accepted.",
        "before_baseline_digest": null,
        "after_baseline_digest": null,
    })
}

fn parsed(value: &Value) -> Result<crate::policy::Amendment, AmendmentError> {
    parse_amendment(&serde_json::to_vec(value).unwrap())
}

fn with(key: &str, value: Value) -> Value {
    let mut document = document();
    document[key] = value;
    document
}

fn tree(rules: &Value) -> ContractTree {
    let bytes = serde_json::to_vec(&json!({
        "schema_version": "3.14.0",
        "components": [],
        "rules": rules,
    }))
    .unwrap();
    assemble_tree(ROOT, crate::contract::parse(&bytes).unwrap(), &[]).unwrap()
}

fn widened() -> (ContractTree, ContractTree) {
    let rule = json!({
        "id": "R-1", "kind": "no_component_cycles", "rationale": "r",
        "provenance": ["d.md"], "decided_by": "architect",
    });
    (tree(&json!([rule])), tree(&json!([])))
}

#[test]
fn a_valid_amendment_is_read_and_written_as_python_writes_it() {
    let amendment = parsed(&document()).unwrap();
    let text = String::from_utf8(amendment_bytes(&amendment)).unwrap();
    let expected = format!(
        "{{\n  \"after_baseline_digest\": null,\n  \"after_digest\": \"{}\",\n  \
         \"before_baseline_digest\": null,\n  \"before_digest\": \"{}\",\n  \
         \"decided_by\": \"Jordan\",\n  \"rationale\": \"Accepted.\",\n  \
         \"schema_version\": \"2.0.0\"\n}}\n",
        digest('b'),
        digest('a')
    );
    assert_eq!(text, expected);
    assert_eq!(parse_amendment(text.as_bytes()).unwrap(), amendment);
}

#[test]
fn a_text_is_escaped_as_python_json_dumps_escapes_it() {
    let value = "a\u{1}\u{1f}\u{7f}\u{2028}\"\\\u{8}\u{c}\n\r\t/é😀";
    let amendment = parsed(&with("decided_by", json!(value))).unwrap();
    let text = String::from_utf8(amendment_bytes(&amendment)).unwrap();
    let line = "\"decided_by\": \"a\\u0001\\u001f\u{7f}\u{2028}\\\"\\\\\\b\\f\\n\\r\\t/é😀\"";
    assert!(text.contains(line), "{text}");
}

#[test]
fn schema_one_and_unknown_schemas_are_named_errors() {
    let v1 = json!({
        "schema_version": "1.0.0", "before_digest": digest('a'), "after_digest": digest('b'),
        "decided_by": "J", "rationale": "R",
    });
    assert_eq!(parsed(&v1), Err(AmendmentError::Version1));
    let unknown = parsed(&with("schema_version", json!("2.0.1")));
    assert_eq!(
        unknown.map_err(|e| e.to_string()),
        Err("unsupported amendment schema '2.0.1'".into())
    );
    let mut missing = document();
    missing.as_object_mut().unwrap().remove("schema_version");
    assert_eq!(
        parsed(&missing),
        Err(AmendmentError::UnsupportedSchema("None".into()))
    );
    assert_eq!(
        parsed(&with("schema_version", json!(2))),
        Err(AmendmentError::UnsupportedSchema("2".into()))
    );
}

#[test]
fn the_fields_are_exact_and_checked_in_the_python_order() {
    assert_eq!(
        parsed(&with("extra", json!(1))),
        Err(AmendmentError::FieldsMismatch)
    );
    let mut missing = document();
    missing
        .as_object_mut()
        .unwrap()
        .remove("after_baseline_digest");
    assert_eq!(parsed(&missing), Err(AmendmentError::FieldsMismatch));
    let mut two = with("before_digest", json!(1));
    two["decided_by"] = json!("");
    assert_eq!(
        parsed(&two),
        Err(AmendmentError::NotString(AmendmentField::BeforeDigest))
    );
    assert_eq!(
        parsed(&with("decided_by", json!(null))),
        Err(AmendmentError::NotString(AmendmentField::DecidedBy))
    );
    assert_eq!(parsed(&json!([])), Err(AmendmentError::NotObject));
    let mut texts = with("decided_by", json!(" "));
    texts["rationale"] = json!("");
    assert_eq!(
        parsed(&texts),
        Err(AmendmentError::Empty(AmendmentField::DecidedBy))
    );
}

#[test]
fn a_digest_is_sixty_four_lowercase_hex_digits() {
    for bad in [
        "A".repeat(64),
        "a".repeat(63),
        "a".repeat(65),
        "g".repeat(64),
        format!("{} ", "a".repeat(63)),
    ] {
        let error = parsed(&with("after_baseline_digest", json!(bad)));
        assert_eq!(
            error,
            Err(AmendmentError::NotDigest(
                AmendmentField::AfterBaselineDigest
            ))
        );
    }
    assert!(parsed(&with(
        "before_baseline_digest",
        json!("0123456789abcdef".repeat(4))
    ))
    .is_ok());
}

#[test]
fn blank_is_python_str_isspace() {
    for space in [
        '\u{1c}', '\u{1f}', '\u{85}', '\u{a0}', '\u{2028}', '\u{3000}', ' ', '\t',
    ] {
        assert!(blank(&space.to_string()), "{space:?}");
        let error = parsed(&with("rationale", json!(format!("{space}{space}"))));
        assert_eq!(error, Err(AmendmentError::Empty(AmendmentField::Rationale)));
    }
    for text in ['\u{200b}', '\u{180e}', '\u{feff}', 'x'] {
        assert!(!blank(&text.to_string()), "{text:?}");
    }
    let python: Vec<u32> = (0..=0x10_ffff)
        .filter_map(char::from_u32)
        .filter(|c| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(c))
        .map(u32::from)
        .collect();
    let table: Vec<u32> = (0..=0x10_ffff)
        .filter_map(char::from_u32)
        .filter(|c| blank(&c.to_string()))
        .map(u32::from)
        .collect();
    assert_eq!(table, python);
}

#[test]
fn hostile_bytes_are_refused_without_a_panic() {
    let valid = serde_json::to_vec(&document()).unwrap();
    let mut bom = b"\xef\xbb\xbf".to_vec();
    bom.extend_from_slice(&valid);
    let mut trailing = valid.clone();
    trailing.extend_from_slice(b" {}");
    let deep = format!("{}{}", "[".repeat(100_000), "]".repeat(100_000));
    let duplicate = br#"{"decided_by": "a", "decided_by": "b"}"#.to_vec();
    let surrogate = br#"{"decided_by": "\ud800"}"#.to_vec();
    for bytes in [
        bom,
        trailing,
        deep.into_bytes(),
        b"\xff".to_vec(),
        b"".to_vec(),
        b"NaN".to_vec(),
    ] {
        assert!(matches!(
            parse_amendment(&bytes),
            Err(AmendmentError::Json(_))
        ));
    }
    assert!(matches!(
        parse_amendment(&duplicate),
        Err(AmendmentError::DuplicateKey(_))
    ));
    assert!(matches!(
        parse_amendment(&surrogate),
        Err(AmendmentError::Json(_))
    ));
}

#[test]
fn a_million_keys_are_read_in_bounded_time() {
    let keys: Vec<String> = (0..1_000_000).map(|n| format!("\"k{n}\": 0")).collect();
    let bytes = format!("{{{}}}", keys.join(","));
    let started = std::time::Instant::now();
    assert_eq!(
        parse_amendment(bytes.as_bytes()),
        Err(AmendmentError::UnsupportedSchema("None".into()))
    );
    assert!(started.elapsed().as_secs() < 20);
}

#[test]
fn the_absent_contract_digest_is_the_python_digest() {
    // python3 -c "from archkeel.ir.codec_contract import absent_contract_digest as d; print(d(p))"
    assert_eq!(
        absent_contract_digest(ROOT),
        "36720af03f402116b1ace0299aad2f1eb341a6cc93b8a39ce233e87398b89c10"
    );
    assert_eq!(
        absent_contract_digest("é/c.json"),
        "3aec08fabd9a5c3a09bbfde69021c844aba67e97e5a12d16474019b5210dd3fe"
    );
}

#[test]
fn an_amendment_covers_only_the_comparison_that_it_binds() {
    let (before, after) = widened();
    let binding = bind(
        OldContract::Tree(&before),
        &after,
        Baselines::not_configured(),
    );
    let missing = binding.check(None);
    assert_eq!(*missing.status(), GateStatus::Unamended);
    assert!(!missing.passes());
    let amendment = binding.amend("Jordan", "Accepted.").unwrap();
    assert_eq!(
        *binding.check(Some(&amendment)).status(),
        GateStatus::Covered
    );
    // A replay on the reversed pair, and on the same pair with a baseline, is stale.
    let reverse = bind(
        OldContract::Tree(&after),
        &before,
        Baselines::not_configured(),
    );
    let stale = reverse.check(Some(&amendment));
    assert_eq!(*stale.status(), GateStatus::Stale);
    assert_eq!(
        stale.failures(),
        &["amendment does not bind this contract and baseline comparison".to_owned()]
    );
    let with_baseline = bind(
        OldContract::Tree(&before),
        &after,
        Baselines::bound(&digest('c'), &digest('d')),
    );
    let verdict = with_baseline.check(Some(&amendment));
    assert_eq!(*verdict.status(), GateStatus::Stale);
    assert!(!verdict.failures().is_empty());
    let bound = with_baseline.amend("J", "R").unwrap();
    assert_eq!(
        *with_baseline.check(Some(&bound)).status(),
        GateStatus::Covered
    );
    assert_eq!(*binding.check(Some(&bound)).status(), GateStatus::Stale);
    let swapped = bind(
        OldContract::Tree(&before),
        &after,
        Baselines::bound(&digest('d'), &digest('c')),
    );
    assert_eq!(*swapped.check(Some(&bound)).status(), GateStatus::Stale);
}

#[test]
fn an_unchanged_pair_passes_and_a_stale_amendment_fails_it() {
    let (before, _) = widened();
    let binding = bind(
        OldContract::Tree(&before),
        &before,
        Baselines::not_configured(),
    );
    assert_eq!(*binding.check(None).status(), GateStatus::Unchanged);
    let amendment = parsed(&document()).unwrap();
    assert!(!binding.check(Some(&amendment)).passes());
}

#[test]
fn an_introduced_contract_is_one_widening_bound_to_its_path() {
    let (_, after) = widened();
    let old = OldContract::Introduced {
        path: ROOT,
        against: "HEAD~1",
    };
    let binding = bind(old, &after, Baselines::not_configured());
    let verdict = binding.check(None);
    let message = format!("contract introduced: {ROOT} does not exist at HEAD~1");
    assert_eq!(verdict.failures(), &[message]);
    let change = &binding.comparison().changes()[0];
    assert_eq!(
        (change.subject().as_str(), change.field().as_str()),
        ("contract architecture-contract.json", "presence")
    );
    let amendment = binding.amend("J", "R").unwrap();
    assert_eq!(
        amendment.before_digest().as_text(),
        absent_contract_digest(ROOT)
    );
    assert!(binding.check(Some(&amendment)).passes());
    let moved = bind(
        OldContract::Introduced {
            path: "other.json",
            against: "HEAD~1",
        },
        &after,
        Baselines::not_configured(),
    );
    assert_eq!(*moved.check(Some(&amendment)).status(), GateStatus::Stale);
}

#[test]
fn a_blank_author_or_reason_is_not_written() {
    let (before, after) = widened();
    let binding = bind(
        OldContract::Tree(&before),
        &after,
        Baselines::not_configured(),
    );
    assert_eq!(
        binding.amend(" ", "R"),
        Err(AmendmentError::Empty(AmendmentField::DecidedBy))
    );
    assert_eq!(
        binding.amend("J", "\u{1c}"),
        Err(AmendmentError::Empty(AmendmentField::Rationale))
    );
}
