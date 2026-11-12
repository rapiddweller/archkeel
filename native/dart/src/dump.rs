// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `--dump` (feature `dump`, test only, as AD-323 requires): run the discovery and the parse on a
//! snapshot and print the sections as one JSON object, for `tools/dart_discovery_parity.py`.
//! The time covers the discovery, the parse and the sections, not the start of the process and
//! not the JSON output.
//!
//! `--dump-syntax` reads one file path on each line of stdin and prints one JSON line for each:
//! the syntax of the file, the time of its parse and the share of the site work limit that it
//! used, for `tools/dart_syntax_parity.py`.

use std::time::Instant;

use archkeel_snapshot::Snapshot;
use serde_json::json;

use crate::discover::{discover, scan_roots};
use crate::parse::DartParser;
use crate::records::sections;

/// The input of the test-only SDK boundary dump. Unknown fields stop the dump.
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SdkInput {
    state: crate::pubspec::SdkState,
    constraint: Option<String>,
}

/// One result for each JSON input line; this is not a collector reply.
pub(crate) fn sdk(text: &str) -> Result<String, String> {
    let mut output = String::new();
    for line in text.lines() {
        let input: SdkInput = serde_json::from_str(line).map_err(|error| error.to_string())?;
        let (supported, gaps, work) =
            crate::records::sdk_support(input.state, input.constraint.as_deref());
        let value = json!({"sdk_supported": supported, "gaps": gaps, "work": work});
        output.push_str(&serde_json::to_string(&value).map_err(|error| error.to_string())?);
        output.push('\n');
    }
    Ok(output)
}

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
    let result = result.and_then(|found| {
        let mut parser = DartParser::new()?;
        let syntax: Vec<_> = found
            .sources
            .iter()
            .map(|source| parser.parse(&source.content))
            .collect();
        let built = sections(&found, &roots, &syntax);
        Ok((found, built))
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

/// The JSON lines of `--dump-syntax`: one line for each path of `paths`.
pub(crate) fn syntax(paths: &str) -> Result<String, String> {
    let mut parser = DartParser::new()?;
    let mut lines = String::new();
    for path in paths.lines().filter(|line| !line.is_empty()) {
        let content =
            std::fs::read(path).map_err(|error| format!("cannot read {path}: {error}"))?;
        let started = Instant::now();
        let parsed = parser.parse(&content);
        let nanos = started.elapsed().as_nanos();
        let value = json!({
            "syntax": parsed,
            "nanos": nanos.to_string(),
            "work_permille": parser.work_permille,
        });
        lines.push_str(&serde_json::to_string(&value).map_err(|error| error.to_string())?);
        lines.push('\n');
    }
    Ok(lines)
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
