// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `--dump`: run the discovery on a snapshot and print its sections as one JSON object, for
//! `tools/dart_discovery_parity.py`. The time covers the discovery and the sections, not the
//! start of the process and not the JSON output.

use std::time::Instant;

use archkeel_snapshot::paths::normpath;
use archkeel_snapshot::Snapshot;
use serde_json::json;

use crate::discover::discover;
use crate::records::sections;

/// The JSON text of the sections, from `<snapshot-root> <namespace> <root>...`.
pub(crate) fn run(arguments: &[String]) -> Result<String, String> {
    let [root, namespace, roots @ ..] = arguments else {
        return Err("usage: --dump <snapshot-root> <namespace> <root>...".to_owned());
    };
    if roots.is_empty() {
        return Err("--dump needs at least one scan root".to_owned());
    }
    let roots: Vec<String> = roots.iter().map(|root| normpath(root)).collect();
    let started = Instant::now();
    let mut snapshot = Snapshot::new(root);
    let result = discover(&mut snapshot, namespace, &roots).map(|found| {
        let built = sections(&found, &roots);
        (found, built)
    });
    let nanos = started.elapsed().as_nanos();
    let value = match result {
        Ok((found, built)) => json!({
            "inputs": built.inputs,
            "source_digest": built.source_digest,
            "scope": built.scope,
            "files": built.files,
            "gaps": built.gaps,
            "evidence": built.evidence,
            "selected_files": built.selected_files,
            "package_name": found.package_name,
            "sdk_constraint": found.sdk,
            "sdk_state": found.sdk_state.as_str(),
            "nanos": nanos.to_string(),
        }),
        Err(error) => json!({"error": error, "nanos": nanos.to_string()}),
    };
    serde_json::to_string(&value).map_err(|error| error.to_string())
}
