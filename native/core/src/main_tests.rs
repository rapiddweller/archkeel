// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The process writes one frame or none (review M4 of #1090).

use serde_json::{json, Value};

use super::respond;
use crate::engine::tests::{golden_profile, golden_reply};

fn request() -> Value {
    let reply = golden_reply();
    json!({
        "protocol": "archkeel-dual-run-5", "case": "c", "root": "/r", "config": "archkeel.toml",
        "baseline": null, "collector_argv": null,
        "contracts": {"architecture-contract.json":
            r#"{"schema_version": "2.2.0", "components": [], "rules": []}"#},
        "reply": {"hex": reply.iter().map(|b| format!("{b:02x}")).collect::<String>()},
        "sections": [], "namespace": "shop", "profile": golden_profile(),
        "standard_library": [], "insides": [], "roots": [],
    })
}

#[test]
fn the_process_writes_exactly_one_frame_or_none() {
    let mut out = Vec::new();
    let (code, message) = respond(request().to_string().as_bytes(), &mut out);
    assert_eq!((code, message), (3, None));
    // Two frames in a row are no JSON value: `from_slice` refuses the trailing bytes.
    let frame: Value = serde_json::from_slice(&out).unwrap_or(Value::Null);
    assert_eq!(
        frame["status"],
        "UNKNOWN",
        "{}",
        String::from_utf8_lossy(&out)
    );
    let mut out = Vec::new();
    let (code, message) = respond(b"{}", &mut out);
    assert_eq!(code, 2);
    assert!(out.is_empty());
    assert!(message.is_some());
}

#[test]
fn a_request_over_the_limit_is_refused_after_one_byte_more_than_the_limit() {
    struct Endless(u64);
    impl std::io::Read for Endless {
        fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
            self.0 += buffer.len() as u64;
            buffer.fill(b' ');
            Ok(buffer.len())
        }
    }
    let mut endless = Endless(0);
    let refused = super::read_request(&mut endless, 1000);
    assert!(matches!(refused, Err(super::Unread::Over)));
    // The reader was asked for the limit plus one byte, at most one buffer more.
    assert!(endless.0 < 1000 + 64 * 1024, "{}", endless.0);
}

#[test]
fn a_request_at_the_limit_is_read_whole() {
    let bytes = vec![b'x'; 1000];
    let read = super::read_request(bytes.as_slice(), 1000);
    assert_eq!(read.ok().map(|read| read.len()), Some(1000));
    let over = super::read_request(vec![b'x'; 1001].as_slice(), 1000);
    assert!(matches!(over, Err(super::Unread::Over)));
}
