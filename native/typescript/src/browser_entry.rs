// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The browser scope of a part (AD-1420): the files that its entry page loads, transitively.
//!
//! The repository guard of the premise reads each file of the repository outside the scan roots.
//! A part that ships one page to a browser needs only the files that the page loads: a fixture, a
//! tool or a second page that no entry loads is not browser code of this part. A file that the
//! entry loads stays in, whatever its place. The scope is derived, never listed:
//!
//! - the entry page names scripts with `<script src>` and `<link rel="modulepreload" href>`;
//! - a loaded script or module names more files with `import … from`, `export … from`,
//!   `import("…")`, `importScripts("…")` and `new Worker("…")`;
//! - a URL path that starts with `/` is searched in each assets folder, in order; a relative path
//!   is resolved against the URL of the file that names it.
//!
//! A reference that cannot be followed does not narrow the scope: it is the cause of the run
//! (`Closure::incomplete`), and then no global has a native proof.

use std::collections::BTreeSet;

use archkeel_facts::request::BrowserSettings;
use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;
use tree_sitter::Node;

use crate::source_input::classify_file;
use crate::syntax::Parsers;

/// The most files that one entry may load: a run with more is not read.
const BUDGET: usize = 2_000;

/// The files that the entry loads, and why the list may be short.
#[derive(Default)]
pub(crate) struct Closure {
    /// The repository paths of the entry and of each file that it loads, sorted.
    pub files: BTreeSet<String>,
    /// The first reference that the closure could not follow.
    pub incomplete: Option<String>,
}

/// One file of the closure with the URL that a browser requests it by.
struct Loaded {
    rel: String,
    url: String,
}

/// The files that `browser.entry` loads.
pub(crate) fn closure(
    snapshot: &mut Snapshot,
    parsers: &mut Parsers,
    browser: &BrowserSettings,
) -> Closure {
    let mut found = Closure::default();
    let entry = join(".", &browser.entry);
    let mut pending = vec![Loaded {
        rel: entry,
        url: "/".to_owned(),
    }];
    while let Some(file) = pending.pop() {
        if !found.files.insert(file.rel.clone()) {
            continue;
        }
        if found.files.len() > BUDGET {
            found
                .incomplete
                .get_or_insert_with(|| format!("the browser entry loads more than {BUDGET} files"));
            break;
        }
        let Some(data) = snapshot.read(&file.rel) else {
            found.incomplete.get_or_insert_with(|| {
                format!(
                    "the browser file {} cannot be read (over the size limit of a file?)",
                    file.rel
                )
            });
            continue;
        };
        let references = references_of(parsers, &file.rel, &data);
        found.incomplete = found.incomplete.take().or(references.incomplete);
        for reference in references.found {
            match resolve(snapshot, browser, &file.url, &reference) {
                Resolved::File(next) => pending.push(next),
                Resolved::Remote => {}
                Resolved::Missing(cause) => {
                    found
                        .incomplete
                        .get_or_insert(format!("{} loads {reference}, which is {cause}", file.rel));
                }
            }
        }
    }
    found
}

/// What a reference of a loaded file is.
enum Resolved {
    File(Loaded),
    /// A URL outside the repository: the premise covers it, as for any code outside the repository.
    Remote,
    Missing(&'static str),
}

/// The file that a reference names: an absolute URL path against the assets folders, a relative
/// one against the URL of the file that names it.
fn resolve(
    snapshot: &mut Snapshot,
    browser: &BrowserSettings,
    base_url: &str,
    reference: &str,
) -> Resolved {
    let reference = reference.split(['?', '#']).next().unwrap_or_default();
    if reference.is_empty() {
        return Resolved::Missing("empty");
    }
    if reference.starts_with("//") || reference.contains("://") || reference.starts_with("data:") {
        return Resolved::Remote;
    }
    let relative_start = reference.starts_with("./") || reference.starts_with("../");
    if !reference.starts_with('/') && !relative_start {
        return Resolved::Missing("a bare name that the page does not map");
    }
    let url = if reference.starts_with('/') {
        join("/", reference)
    } else {
        join(dirname(base_url), reference)
    };
    let served = url.trim_start_matches('/');
    if served.is_empty() {
        return Resolved::Missing("the root of the page");
    }
    for folder in &browser.assets {
        let rel = join(folder, served);
        if snapshot.is_file(&rel) {
            return Resolved::File(Loaded { rel, url });
        }
    }
    Resolved::Missing("in no assets folder")
}

/// The references of one loaded file, and the first one that has no literal path.
struct References {
    found: Vec<String>,
    incomplete: Option<String>,
}

fn references_of(parsers: &mut Parsers, rel: &str, data: &[u8]) -> References {
    let lower = rel.to_ascii_lowercase();
    if lower.ends_with(".html") || lower.ends_with(".htm") {
        return References {
            found: page_references(data),
            incomplete: None,
        };
    }
    let Some(suffix) = classify_file(rel) else {
        return nothing();
    };
    if !matches!(
        suffix.source_kind(),
        Some(
            crate::source_input::SourceKind::JavaScript
                | crate::source_input::SourceKind::TypeScript
        )
    ) {
        return nothing();
    }
    let Some((tree, _)) = parsers.parse(suffix.parser_typescript(), data) else {
        return References {
            found: Vec::new(),
            incomplete: Some(format!("the browser file {rel} cannot be parsed")),
        };
    };
    let mut found = References {
        found: Vec::new(),
        incomplete: None,
    };
    walk(tree.root_node(), data, rel, &mut found);
    found
}

fn nothing() -> References {
    References {
        found: Vec::new(),
        incomplete: None,
    }
}

/// The text of a string literal without a substitution, or `None`.
fn literal(node: Node<'_>, data: &[u8]) -> Option<String> {
    match node.kind() {
        "string" => {
            let text = std::str::from_utf8(data.get(node.byte_range())?).ok()?;
            let quote = text.chars().next().filter(|c| matches!(c, '"' | '\''))?;
            text.strip_prefix(quote)?
                .strip_suffix(quote)
                .map(str::to_owned)
        }
        "template_string" if node.named_child_count() == 1 => {
            let text = std::str::from_utf8(data.get(node.byte_range())?).ok()?;
            text.strip_prefix('`')?.strip_suffix('`').map(str::to_owned)
        }
        _ => None,
    }
}

/// The first argument as a path: a literal, or `new URL("…", …)`.
fn path_argument(arguments: Node<'_>, data: &[u8]) -> Option<String> {
    let first = arguments.named_child(0)?;
    if let Some(text) = literal(first, data) {
        return Some(text);
    }
    if first.kind() == "new_expression" {
        let name = first.child_by_field_name("constructor")?;
        if data.get(name.byte_range()) == Some(b"URL".as_slice()) {
            return literal(
                first.child_by_field_name("arguments")?.named_child(0)?,
                data,
            );
        }
    }
    None
}

fn walk(node: Node<'_>, data: &[u8], rel: &str, out: &mut References) {
    let line = node.start_position().row.saturating_add(1);
    match node.kind() {
        "import_statement" | "export_statement" => {
            if let Some(source) = node.child_by_field_name("source") {
                match literal(source, data) {
                    Some(text) => out.found.push(text),
                    None => note(out, rel, line, "a module path that is no literal"),
                }
            }
        }
        "call_expression" => call(node, data, rel, line, out),
        "new_expression" => {
            let named = node
                .child_by_field_name("constructor")
                .and_then(|name| data.get(name.byte_range()));
            if matches!(named, Some(b"Worker") | Some(b"SharedWorker")) {
                match node
                    .child_by_field_name("arguments")
                    .and_then(|arguments| path_argument(arguments, data))
                {
                    Some(text) => out.found.push(text),
                    None => note(out, rel, line, "a worker path that is no literal"),
                }
            }
        }
        _ => {}
    }
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk(child, data, rel, out);
    }
}

fn call(node: Node<'_>, data: &[u8], rel: &str, line: usize, out: &mut References) {
    let Some(function) = node.child_by_field_name("function") else {
        return;
    };
    let Some(arguments) = node.child_by_field_name("arguments") else {
        return;
    };
    match (function.kind(), data.get(function.byte_range())) {
        ("import", _) => match arguments
            .named_child(0)
            .and_then(|first| literal(first, data))
        {
            Some(text) => out.found.push(text),
            None => note(out, rel, line, "a dynamic import with no literal path"),
        },
        ("identifier", Some(b"importScripts")) => {
            let mut cursor = arguments.walk();
            for argument in arguments.named_children(&mut cursor) {
                match literal(argument, data) {
                    Some(text) => out.found.push(text),
                    None => note(out, rel, line, "an importScripts path that is no literal"),
                }
            }
        }
        _ => {}
    }
}

fn note(out: &mut References, rel: &str, line: usize, what: &str) {
    out.incomplete
        .get_or_insert_with(|| format!("{rel}:{line} has {what}"));
}

/// The script paths of a page: `src` of each `<script>` and `href` of each modulepreload link.
fn page_references(data: &[u8]) -> Vec<String> {
    let text = String::from_utf8_lossy(data);
    let lower = text.to_ascii_lowercase();
    let mut found = Vec::new();
    let mut at = 0;
    while let Some(start) = lower[at..].find('<').map(|offset| offset + at) {
        let tag_end = lower[start..]
            .find('>')
            .map_or(lower.len(), |offset| offset + start);
        let tag = &text[start + 1..tag_end];
        at = tag_end.max(start + 1);
        let name: String = tag
            .chars()
            .take_while(|c| !c.is_whitespace() && *c != '/')
            .collect::<String>()
            .to_ascii_lowercase();
        let attributes = attributes(&tag[name.len().min(tag.len())..]);
        let attribute = |wanted: &str| {
            attributes
                .iter()
                .find(|(key, _)| key == wanted)
                .map(|(_, value)| value.clone())
        };
        match name.as_str() {
            "script" => found.extend(attribute("src")),
            "link"
                if attribute("rel")
                    .is_some_and(|rel| rel.eq_ignore_ascii_case("modulepreload")) =>
            {
                found.extend(attribute("href"));
            }
            _ => {}
        }
    }
    found
}

/// The `name=value` pairs of a tag: a name is lower case, a value may be quoted or bare.
fn attributes(text: &str) -> Vec<(String, String)> {
    let mut chars = text.chars().peekable();
    let mut pairs = Vec::new();
    loop {
        while chars.next_if(|c| c.is_whitespace() || *c == '/').is_some() {}
        let mut key = String::new();
        while let Some(c) = chars.next_if(|c| !c.is_whitespace() && !matches!(*c, '=' | '/')) {
            key.push(c.to_ascii_lowercase());
        }
        while chars.next_if(|c| c.is_whitespace()).is_some() {}
        let mut value = String::new();
        if chars.next_if_eq(&'=').is_some() {
            while chars.next_if(|c| c.is_whitespace()).is_some() {}
            value = match chars.next_if(|c| matches!(*c, '"' | '\'')) {
                Some(quote) => {
                    let quoted: String = chars.by_ref().take_while(|c| *c != quote).collect();
                    quoted
                }
                None => std::iter::from_fn(|| chars.next_if(|c| !c.is_whitespace())).collect(),
            };
        }
        if key.is_empty() {
            return pairs;
        }
        pairs.push((key, value));
    }
}

#[cfg(test)]
#[path = "browser_entry_tests.rs"]
mod tests;
