// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Derive the report's CSP hashes from the scripts embedded in the page.

use sha2::{Digest, Sha256};
use std::error::Error;

fn hash(path: &str) -> Result<String, Box<dyn Error>> {
    println!("cargo:rerun-if-changed={path}");
    let digest = Sha256::digest(std::fs::read(path)?);
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut result = String::new();
    for bytes in digest.chunks(3) {
        let value = (u32::from(bytes[0]) << 16)
            | (u32::from(bytes.get(1).copied().unwrap_or(0)) << 8)
            | u32::from(bytes.get(2).copied().unwrap_or(0));
        for shift in [18, 12, 6, 0] {
            let index = (value >> shift & 63) as usize;
            result.push(
                if (shift == 0 && bytes.len() < 3) || (shift == 6 && bytes.len() < 2) {
                    '='
                } else {
                    char::from(alphabet[index])
                },
            );
        }
    }
    Ok(result)
}

fn main() -> Result<(), Box<dyn Error>> {
    for (name, path) in [
        ("THEME", "assets/archkeel-theme.js"),
        ("ELK", "assets/explorer/elkjs-0.12.0.bundled.js"),
        ("PROTOCOL", "assets/explorer/report-graph-protocol.js"),
        ("GRAPH", "assets/explorer/report-graph-scene.js"),
        ("ATLAS", "assets/explorer/report-atlas-deviations.js"),
        ("SCENE", "assets/explorer/report-scene.js"),
        ("ROUTES", "assets/explorer/report-routes.js"),
        ("LAYOUT", "assets/explorer/report-layout.js"),
        ("FLOW", "assets/explorer/flow.runtime.js"),
        ("CANVAS", "assets/explorer/report-canvas.js"),
    ] {
        println!("cargo:rustc-env=REPORT_{name}_HASH={}", hash(path)?);
    }
    Ok(())
}
