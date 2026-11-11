// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `--dump` (feature `dump`, test only, as AD-323 requires): run the discovery on a snapshot and print its sections as one JSON object, for
//! `tools/dart_discovery_parity.py`. The time covers the discovery and the sections, not the
//! start of the process and not the JSON output.

use std::time::Instant;

use archkeel_snapshot::Snapshot;
use serde_json::json;

use crate::discover::{discover, scan_roots};
use crate::records::sections;

/// The JSON text of the sections, from `<snapshot-root> <namespace> <root>...`.
pub(crate) fn run(arguments: &[String]) -> Result<String, String> {
    let [root, namespace, roots @ ..] = arguments else {
        return Err("usage: --dump <snapshot-root> <namespace> <root>...".to_owned());
    };
    if roots.is_empty() {
        return Err("--dump needs at least one scan root".to_owned());
    }
    let roots = scan_roots(roots);
    let started = Instant::now();
    // A snapshot root that is a link, missing or not a directory stops the collection.
    let result = Snapshot::open_root(root)
        .and_then(|mut snapshot| discover(&mut snapshot, namespace, &roots));
    let result = result.map(|found| {
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

#[cfg(test)]
mod tests {
    use archkeel_snapshot::test_tree::Tree;

    use super::run;

    #[test]
    fn a_snapshot_root_that_is_missing_stops_with_a_named_error() {
        let tree = Tree::new(&[("lib/a.dart", "")]);
        let missing = tree.root.join("absent").to_string_lossy().into_owned();
        let text = run(&[missing, "shop".to_owned(), "lib".to_owned()]).unwrap();
        assert!(
            text.contains("\"error\":\"cannot resolve snapshot root: "),
            "{text}"
        );
        assert!(!text.contains("\"inputs\""), "{text}");
    }

    #[test]
    fn a_repeated_root_gives_one_scope_entry() {
        let tree = Tree::new(&[("pubspec.yaml", "name: shop\n"), ("lib/a.dart", "")]);
        let roots = ["lib", "./lib"].map(str::to_owned);
        let text = run(&[&[tree.path(), "shop".to_owned()][..], &roots].concat()).unwrap();
        assert!(text.contains("\"scope\":[\"lib/**/*.dart\"]"), "{text}");
    }
}
