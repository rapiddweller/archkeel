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
        return page_references(parsers, rel, data);
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
    // A tree with an error node can hide a reference: the file is not read in full.
    if tree.root_node().has_error() {
        return References {
            found: Vec::new(),
            incomplete: Some(format!("the browser file {rel} cannot be parsed in full")),
        };
    }
    let mut found = nothing();
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
        ("member_expression", Some(text)) => member_call(text, arguments, data, rel, line, out),
        _ => {}
    }
}

/// A call `object.name(…)` that loads code or makes a script: `createElement("script")`,
/// `serviceWorker.register("…")` and `document.write`.
fn member_call(
    text: &[u8],
    arguments: Node<'_>,
    data: &[u8],
    rel: &str,
    line: usize,
    out: &mut References,
) {
    let text = String::from_utf8_lossy(text);
    let name = text.rsplit('.').next().unwrap_or_default();
    match name {
        "createElement" | "createElementNS" => {
            let tag = arguments
                .named_child(usize::from(name == "createElementNS"))
                .and_then(|first| literal(first, data));
            // A tag that is no literal is not examined (AD-1460, "Not done"): a helper such as
            // `element(tag)` is the plain form of a page, and the scan cannot bound its callers.
            if tag.is_some_and(|tag| tag.eq_ignore_ascii_case("script")) {
                note(out, rel, line, "a script element that code creates");
            }
        }
        "register" if text.ends_with("serviceWorker.register") => {
            match path_argument(arguments, data) {
                Some(path) => out.found.push(path),
                None => note(out, rel, line, "a service worker path that is no literal"),
            }
        }
        "addModule" => match path_argument(arguments, data) {
            Some(path) => out.found.push(path),
            None => note(out, rel, line, "a worklet module path that is no literal"),
        },
        "write" | "writeln" if text.trim() == format!("document.{name}") => {
            note(out, rel, line, "a document.write that can load a script");
        }
        _ => {}
    }
}

fn note(out: &mut References, rel: &str, line: usize, what: &str) {
    out.incomplete
        .get_or_insert_with(|| format!("{rel}:{line} has {what}"));
}

/// What the elements of a page load and run: `src` of `<script>`, `<iframe>`, `<frame>` and `<embed>`,
/// `data` of `<object>`, `href` of a modulepreload link, and the code of an inline script, of an `on…`
/// attribute and of a `javascript:` address, which names more files the same way a script does. A
/// `<base>`, an import map and an `srcdoc` change or hide what a path means, so they are not read.
fn page_references(parsers: &mut Parsers, rel: &str, data: &[u8]) -> References {
    let text = String::from_utf8_lossy(data);
    let mut out = nothing();
    let mut at = 0;
    while let Some(open) = text[at..].find('<').map(|offset| offset + at) {
        // `<` starts a tag only before a letter, `/` or `!`; elsewhere it is text.
        let next = text[open + 1..].chars().next();
        if !next.is_some_and(|c| c.is_ascii_alphabetic() || matches!(c, '/' | '!')) {
            at = open + 1;
            continue;
        }
        let (tag, end) = tag_at(&text, open);
        at = end;
        let name: String = tag
            .chars()
            .take_while(|c| !c.is_whitespace() && *c != '/')
            .collect::<String>()
            .to_ascii_lowercase();
        let attributes = attributes(tag.get(name.len()..).unwrap_or_default());
        let attribute = |wanted: &str| {
            attributes
                .iter()
                .find(|(key, _)| key == wanted)
                .map(|(_, value)| value.clone())
        };
        let line = text[..open].matches('\n').count().saturating_add(1);
        let place = format!("{rel}:{line}");
        for (key, value) in &attributes {
            let address = value.trim_start().to_ascii_lowercase();
            if key.starts_with("on") && !value.trim().is_empty() {
                code(parsers, &place, value.as_bytes(), &mut out);
            } else if address.starts_with("javascript:") {
                code(
                    parsers,
                    &place,
                    value.trim_start().as_bytes().get(11..).unwrap_or_default(),
                    &mut out,
                );
            }
        }
        match name.as_str() {
            "base" => note(
                &mut out,
                rel,
                line,
                "a <base> element that changes every path",
            ),
            "script" | "style" => {
                let closing = format!("</{name}");
                let body_end = text[end..]
                    .to_ascii_lowercase()
                    .find(&closing)
                    .map_or(text.len(), |offset| offset + end);
                at = body_end;
                let kind = attribute("type").map(|kind| kind.to_ascii_lowercase());
                if name == "style" {
                    continue;
                }
                if kind.as_deref() == Some("importmap") {
                    note(
                        &mut out,
                        rel,
                        line,
                        "an import map that maps names to paths",
                    );
                } else if let Some(src) = attribute("src") {
                    out.found.push(src);
                } else if runs_as_code(kind.as_deref()) {
                    code(parsers, &place, text[end..body_end].as_bytes(), &mut out);
                }
            }
            "iframe" if attribute("srcdoc").is_some() => {
                note(
                    &mut out,
                    rel,
                    line,
                    "an iframe whose page is an srcdoc text",
                );
            }
            "iframe" | "frame" | "embed" => out.found.extend(attribute("src")),
            "object" => out.found.extend(attribute("data")),
            "link"
                if attribute("rel")
                    .is_some_and(|rel| rel.eq_ignore_ascii_case("modulepreload")) =>
            {
                out.found.extend(attribute("href"));
            }
            _ => {}
        }
    }
    out
}

/// The tag that starts at `open` (without `<` and `>`) and the place after it. A quoted attribute
/// value can hold `>`, and a comment holds no tag.
fn tag_at(text: &str, open: usize) -> (&str, usize) {
    if text[open..].starts_with("<!--") {
        let end = text[open..]
            .find("-->")
            .map_or(text.len(), |offset| open + offset + 3);
        return ("", end);
    }
    let mut quote: Option<char> = None;
    let mut previous = ' ';
    for (offset, c) in text[open + 1..].char_indices() {
        match quote {
            Some(q) if c == q => quote = None,
            Some(_) => {}
            None if matches!(c, '"' | '\'') && previous == '=' => quote = Some(c),
            None if c == '>' => {
                let end = open + 1 + offset;
                return (&text[open + 1..end], end + 1);
            }
            None => {}
        }
        if !c.is_whitespace() {
            previous = c;
        }
    }
    (&text[open + 1..], text.len())
}

/// A script type that runs as JavaScript (as in `script_outside_page`).
fn runs_as_code(kind: Option<&str>) -> bool {
    matches!(
        kind,
        None | Some(
            "" | "module"
                | "text/javascript"
                | "application/javascript"
                | "text/ecmascript"
                | "application/ecmascript"
                | "text/jsx"
                | "text/babel"
        )
    )
}

/// The references of a piece of code inside a page: an inline script, a handler, an address.
fn code(parsers: &mut Parsers, place: &str, bytes: &[u8], out: &mut References) {
    let Some((tree, _)) = parsers.parse(false, bytes) else {
        out.incomplete
            .get_or_insert_with(|| format!("{place} has code that cannot be parsed"));
        return;
    };
    if tree.root_node().has_error() {
        out.incomplete
            .get_or_insert_with(|| format!("{place} has code that cannot be parsed in full"));
        return;
    }
    walk(tree.root_node(), bytes, place, out);
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
