// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::tests::{identity, repository};

fn charge(bytes: &[u8]) -> u64 {
    let (mut tokens, mut total, mut word) = (0, 0, false);
    for &byte in bytes {
        let next = byte.is_ascii_alphanumeric() || byte == b'_';
        if !(byte.is_ascii_whitespace() || word && next) {
            tokens += 1;
        }
        word = next;
        total += 1 + tokens;
    }
    total
}

#[test]
fn a_file_just_below_the_charge_keeps_every_fact() {
    let root = repository("H-typescript");
    let prefix = format!("/*{}", "*".repeat(1020));
    let suffix = "*/\nexport const value = 1;\n";
    let limit = archkeel_snapshot::work::MAX_PARSE_WORK;
    let mut count = 1_000_000;
    let source = format!("{prefix}{}{suffix}", "a".repeat(count));
    count += ((limit - charge(source.as_bytes())) / 1024) as usize;
    let source = format!("{prefix}{}{suffix}", "a".repeat(count));
    assert!(charge(source.as_bytes()) <= limit);
    let above = format!("{prefix}{}{suffix}", "a".repeat(count + 1));
    assert!(charge(above.as_bytes()) > limit);
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
