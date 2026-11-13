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
