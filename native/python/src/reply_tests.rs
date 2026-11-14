// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host decodes this reply (`facts_codec.decode_response`) and refuses 10.0.0; the
// store refuses it too. `tests/test_collector_native_python_reply.py` compares it with Python.

use std::io::Read;

use archkeel_facts::envelope::{ProtocolVersion, Reply, RequirementState};
use archkeel_snapshot::test_tree::Tree;
use archkeel_wire::request::decode_python;
use flate2::read::ZlibDecoder;
use serde_json::{json, Value};

use super::*;

const BUILD: Build<'static> = Build {
    version: "0.0.0",
    code_digest: "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
};

fn request(root: &str) -> PythonRequest {
    let raw = json!({
        "protocol_version": "10.0.0",
        "snapshot": {"root": root, "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": ["src"], "namespace": "app", "exclude_test_sources": false},
        "resolver": {"language": "python", "phase": "imports", "interpreter": {
            "version": "3.12.10", "stdlib_module_names": ["os"], "builtin_module_names": ["sys"]}},
    });
    decode_python(raw.to_string().as_bytes()).unwrap()
}

fn decoded(files: &[(&str, &str)]) -> (Reply, Value) {
    let tree = Tree::new(files);
    let request = request(&tree.path());
    let survey = crate::survey::survey(&request).unwrap();
    let bytes = reply(&request, survey, &BUILD).unwrap();
    let mut text = String::new();
    ZlibDecoder::new(bytes.as_slice())
        .read_to_string(&mut text)
        .unwrap();
    (
        serde_json::from_str(&text).unwrap(),
        serde_json::from_str(&text).unwrap(),
    )
}

const SHOP: [(&str, &str); 3] = [
    ("pyproject.toml", "[project]\nrequires-python = '>=3.11'\n"),
    ("src/app/__init__.py", "import os\nfrom . import sub\n"),
    ("src/app/sub.py", "def (:\n"),
];

#[test]
fn the_reply_declares_only_the_sections_of_the_import_survey() {
    let (reply, _) = decoded(&SHOP);
    let capabilities = &reply.facts.capabilities;
    let sections: Vec<&str> = capabilities
        .sections
        .iter()
        .map(|name| name.as_str())
        .collect();
    assert_eq!(sections, SURVEY_SECTIONS);
    assert!(capabilities.resolution_features.is_empty());
    assert!(capabilities.constructs.is_empty());
    let written: Vec<&str> = reply
        .facts
        .sections
        .iter()
        .map(|item| item.name())
        .collect();
    assert_eq!(written, SURVEY_SECTIONS);
}

#[test]
fn the_reply_has_the_request_version_and_echoes_the_interpreter() {
    let (reply, _) = decoded(&SHOP);
    assert_eq!(reply.protocol_version, ProtocolVersion::V10);
    let runtime = &reply.facts.runtime;
    assert_eq!(runtime.name, "python");
    assert_eq!(runtime.version, "3.12.10");
    assert_eq!(runtime.required.as_deref(), Some(">=3.11"));
    assert_eq!(runtime.requirement_state, RequirementState::Declared);
    let adapter = &reply.facts.adapter;
    assert_eq!(adapter.name, "archkeel-python-analyzer");
    assert_eq!(
        (adapter.version.as_str(), adapter.code_digest.as_str()),
        (BUILD.version, BUILD.code_digest)
    );
}

#[test]
fn a_failure_is_a_gap_and_the_coverage_is_partial() {
    let (reply, _) = decoded(&SHOP);
    let coverage = &reply.facts.coverage;
    assert!(!coverage.full_scope);
    assert_eq!((coverage.files_read, coverage.files_parsed), (2, 1));
    assert_eq!(coverage.gaps.len(), 1);
    assert_eq!(coverage.gaps[0].subjects, ["src/app/sub.py"]);
}

#[test]
fn the_source_digest_is_the_digest_of_the_python_collector() {
    let tree = Tree::new(&SHOP);
    let mut snapshot = Snapshot::new(&tree.path());
    let selected = vec![
        "src/app/__init__.py".to_owned(),
        "src/app/sub.py".to_owned(),
    ];
    let (_, expected) = inputs::inputs(&mut snapshot, &selected);
    let (reply, _) = decoded(&SHOP);
    assert_eq!(reply.facts.source.source_digest, expected);
    assert_eq!(reply.facts.source.scope, ["src/**"]);
}

#[test]
fn the_lists_of_the_collection_phase_are_empty() {
    let (_, raw) = decoded(&SHOP);
    let facts = &raw["facts"];
    for key in [
        "uncertain_reexports",
        "type_shapes",
        "candidate_evidence",
        "provider_bindings",
    ] {
        assert_eq!(facts[key], json!([]), "{key}");
    }
    assert_eq!(facts["state"], json!({"classes": [], "functions": []}));
    assert_eq!(raw["provider_sources"], json!([]));
}

#[test]
fn a_coverage_that_the_stream_cannot_write_is_no_reply() {
    let tree = Tree::new(&SHOP);
    let request = request(&tree.path());
    let mut survey = crate::survey::survey(&request).unwrap();
    survey.coverage.full_scope = true;
    let refused = reply(&request, survey, &BUILD).unwrap_err();
    assert_eq!(
        refused,
        "the coverage of the reply differs from the coverage of the survey"
    );
}

#[test]
fn a_file_that_changes_after_its_parse_gives_no_reply() {
    let tree = Tree::new(&[("src/app/__init__.py", ""), ("src/app/a.py", "import os\n")]);
    let request = request(&tree.path());
    let survey = crate::survey::survey(&request).unwrap();
    std::fs::write(tree.root.join("src/app/a.py"), "import app\n").unwrap();
    let error = typed(&request, survey, &BUILD).unwrap_err();
    assert_eq!(error, "the source changed during the scan: src/app/a.py");
}
