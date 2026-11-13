// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::tests::{identity, repository};

#[test]
fn a_typescript_corpus_project_below_both_bounds_keeps_byte_equal_reply() {
    let root = repository("H-typescript");
    let scanned = scan(&identity(root.to_str().unwrap()), 1 << 26).unwrap();
    let request = serde_json::to_vec(&scanned.request).unwrap();
    assert_eq!(
        crate::tests::binary_bytes(&request),
        serde_json::to_vec(scanned.reply.reply()).unwrap()
    );
}

#[test]
fn a_file_just_below_the_byte_cap_keeps_every_fact() {
    let root = repository("H-typescript");
    let prefix = "/*";
    let suffix = "*/\nexport const value = 1;\n";
    let count = archkeel_snapshot::MAX_FILE_BYTES as usize - prefix.len() - suffix.len() - 1;
    let source = format!("{prefix}{}{suffix}", "a".repeat(count));
    assert_eq!(source.len(), archkeel_snapshot::MAX_FILE_BYTES as usize - 1);
    let above = "(".repeat(archkeel_snapshot::work::MAX_NESTING + 1);
    let path = root.join("src/work.ts");
    std::fs::write(&path, &source).unwrap();
    let scanned = scan(&identity(root.to_str().unwrap()), 1 << 26).unwrap();
    let request = serde_json::to_vec(&scanned.request).unwrap();
    let before = crate::tests::binary_bytes(&request);
    assert_eq!(before, serde_json::to_vec(scanned.reply.reply()).unwrap());
    std::fs::write(path, above).unwrap();
    let refusal = scan(&identity(root.to_str().unwrap()), 1 << 26)
        .err()
        .unwrap();
    assert_eq!(refusal.kind, RefusalKind::ParseWork);
    assert!(reply_of(Profile::TypeScript, &request)
        .unwrap_err()
        .contains("parse_work_limit"));
}

#[test]
fn measure_scan_input_from_public_corpus_roots() {
    let Some(manifest) = std::env::var_os("ARCHKEEL_SCAN_INPUT_ROOTS") else {
        return;
    };
    let cases: Vec<(String, String, String)> =
        serde_json::from_slice(&std::fs::read(manifest).unwrap()).unwrap();
    for (name, path, config_path) in cases {
        let root = crate::repository::Root::of(&path).unwrap();
        let Ok(config) = read_config(&root, &config_path) else {
            continue;
        };
        let identity = Identity {
            config: &config_path,
            ..identity(&path)
        };
        let request = serde_json::to_vec(&request(&identity, &config)).unwrap();
        let profile = config.profile;
        let (reply, charged, reads) = run::isolated(move || {
            let reply = reply_of(profile, &request).unwrap();
            (
                reply,
                archkeel_snapshot::test_tree::charged_bytes().unwrap(),
                archkeel_snapshot::test_tree::read_bytes().unwrap(),
            )
        })
        .unwrap();
        let distinct: u64 = reply
            .facts
            .inputs
            .iter()
            .map(|input| {
                std::fs::metadata(std::path::Path::new(&path).join(&input.path))
                    .unwrap()
                    .len()
            })
            .sum();
        println!(
            "SCAN_INPUT {}",
            json!({
                "case": name, "charged": charged, "distinct": distinct, "reads": reads,
                "files": reply.facts.files.len(), "inputs": reply.facts.inputs.len(),
                "bound": archkeel_snapshot::work::MAX_SCAN_BYTES,
            })
        );
    }
}

fn guarded_rust(request: &[u8]) -> (archkeel_facts::envelope::Reply, u64) {
    let request = request.to_vec();
    run::isolated(move || {
        let reply = reply_of(Profile::Rust, &request).unwrap();
        (
            reply,
            archkeel_snapshot::test_tree::charged_bytes().unwrap(),
        )
    })
    .unwrap()
}

#[test]
fn a_rust_project_just_below_both_bounds_keeps_every_fact() {
    use std::fs;
    let root = crate::rust_tests::repository();
    let prefix = "/*";
    let suffix = "*/\npub const VALUE: u8 = 1;\n";
    let count = archkeel_snapshot::MAX_FILE_BYTES as usize - prefix.len() - suffix.len() - 1;
    let source = format!("{prefix}{}{suffix}", "a".repeat(count));
    assert_eq!(source.len(), archkeel_snapshot::MAX_FILE_BYTES as usize - 1);
    fs::write(root.join("src/work.rs"), source).unwrap();
    let mut modules = "mod work;\n".to_owned();
    for number in 0..20 {
        modules += &format!("mod padding{number};\n");
        fs::write(
            root.join(format!("src/padding{number}.rs")),
            format!("/*{}*/\npub const VALUE: u8 = 1;\n", "a".repeat(1 << 20)),
        )
        .unwrap();
    }
    fs::write(root.join("src/lib.rs"), modules).unwrap();
    let scanned = scan(&identity(root.to_str().unwrap()), 1 << 26).unwrap();
    let request = serde_json::to_vec(&scanned.request).unwrap();
    drop(scanned);
    let (_, charged) = guarded_rust(&request);
    let total = archkeel_snapshot::work::MAX_SCAN_BYTES;
    let mut remaining = (total - charged - 1) as usize;
    for number in 0..20 {
        let path = root.join(format!("src/padding{number}.rs"));
        let mut text = fs::read_to_string(&path).unwrap();
        let extra = remaining.min(archkeel_snapshot::MAX_FILE_BYTES as usize - text.len());
        text.insert_str(2, &"a".repeat(extra));
        fs::write(path, text).unwrap();
        remaining -= extra;
    }
    assert_eq!(remaining, 0);
    let decoded = archkeel_wire::request::decode_rust(&request).unwrap();
    let before = archkeel_rust_collector::typed_reply(
        &decoded,
        archkeel_rust_collector::provenance(),
        archkeel_wire::protocol::reply_version(decoded.protocol_version),
    )
    .unwrap();
    let (after, charged) = guarded_rust(&request);
    assert_eq!(charged, total - 1);
    let after = archkeel_store::ingest_typed(after).unwrap();
    assert_eq!(
        serde_json::to_vec(&before).unwrap(),
        serde_json::to_vec(after.reply()).unwrap()
    );
    let path = root.join("src/padding19.rs");
    use std::io::Write;
    fs::OpenOptions::new()
        .append(true)
        .open(path)
        .unwrap()
        .write_all(b"  ")
        .unwrap();
    let refused = run::collect(Profile::Rust, &request).err().unwrap();
    assert_eq!(refused.kind, RefusalKind::ParseWork);
    assert!(refused.reason.contains("scan input exceeds"));
}
