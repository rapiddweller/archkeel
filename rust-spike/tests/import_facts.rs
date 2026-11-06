use std::io::Write;
use std::process::{Command, Stdio};

fn run_with_args(args: &[&str], source: &str) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_archkeel-import-facts-spike"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(source.as_bytes())
        .unwrap();
    child.wait_with_output().unwrap()
}

fn run(source: &str) -> std::process::Output {
    run_with_args(&[], source)
}

#[test]
fn emits_import_occurrences_and_marks_resolution_unknown() {
    let output = run(
        "import os, package.sub as alias\nfrom .internal import thing as local\nfrom .. import sibling\nfrom pkg.sub import (first, second as second_alias)\n",
    );
    assert!(output.status.success());
    let batch: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(batch["status"], "COMPLETE");
    assert_eq!(batch["complete"], true);
    assert_eq!(batch["target_python_version"], "3.11");
    assert_eq!(batch["semantic_status"], "UNKNOWN");
    let imports = batch["imports"].as_array().unwrap();
    assert_eq!(imports.len(), 6);
    assert_eq!(imports[0]["form"], "import");
    assert_eq!(imports[0]["name"], "os");
    assert_eq!(imports[0]["alias"], serde_json::Value::Null);
    assert_eq!(imports[1]["name"], "package.sub");
    assert_eq!(imports[1]["alias"], "alias");
    assert_eq!(imports[2]["module"], "internal");
    assert_eq!(imports[2]["level"], 1);
    assert_eq!(imports[2]["name"], "thing");
    assert_eq!(imports[2]["alias"], "local");
    assert_eq!(imports[3]["module"], serde_json::Value::Null);
    assert_eq!(imports[3]["level"], 2);
    assert_eq!(imports[4]["line"], 4);
    assert_eq!(imports[4]["name"], "first");
    assert_eq!(imports[5]["line"], 4);
    assert_eq!(imports[5]["alias"], "second_alias");
    for import in imports {
        assert!(import["line"].as_u64().is_some());
        assert!(import["column"].as_u64().is_some());
        assert!(import["end_line"].as_u64().is_some());
        assert!(import["end_column"].as_u64().is_some());
    }
}

#[test]
fn rejects_invalid_python_instead_of_emitting_partial_imports() {
    let output = run("from . import\n");
    assert!(output.status.success());
    let batch: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(batch["status"], "UNKNOWN");
    assert_eq!(batch["complete"], false);
    assert_eq!(batch["reason"], "syntax_error");
    assert!(batch["imports"].as_array().unwrap().is_empty());
}

#[test]
fn unsupported_syntax_for_explicit_target_is_unknown_and_has_no_complete_batch() {
    let output = run_with_args(
        &["--target", "3.11"],
        "def identity[T](value: T) -> T:\n    return value\nimport after\n",
    );
    assert!(output.status.success());
    let batch: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(batch["status"], "UNKNOWN");
    assert_eq!(batch["complete"], false);
    assert_eq!(batch["reason"], "unsupported_syntax");
    assert!(batch["imports"].as_array().unwrap().is_empty());
}
