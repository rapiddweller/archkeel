// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a file does that no static import can prove: loaders, indirect `require`, comments.
//!
//! Each concern becomes a collection gap, so the file never reads as proven (`parse.parse`).

use tree_sitter::Node;

use crate::jsdoc;
use crate::references::{literal, Reference};
use crate::scan::Scan;
use crate::source::{Source, Span};
use crate::source_input::{SourceKind, Suffix};

const LOADER: &str = "Node module loader is not observed";

pub struct Concern {
    pub reason: String,
    pub span: Span,
}

/// What `require_concerns` finds, with whether a name `require` may be rebound.
pub struct Found {
    pub list: Vec<Concern>,
    pub shadows_require: bool,
}

fn contains(data: &[u8], needle: &[u8]) -> bool {
    data.windows(needle.len()).any(|window| window == needle)
}

fn starts_with(parent: Option<Node>, node: Node, kinds: &[&str]) -> bool {
    parent.is_some_and(|parent| {
        kinds.contains(&parent.kind()) && parent.start_byte() == node.start_byte()
    })
}

fn concern(source: &Source, node: Node, reason: &str) -> Concern {
    Concern {
        reason: reason.to_owned(),
        span: source.span(node, None),
    }
}

/// Report every `require` that is not a plain call; true when one may rebind the name.
fn require_concerns(source: &Source, scan: &Scan, list: &mut Vec<Concern>) -> bool {
    let mut shadows = false;
    for node in scan.require_names.iter().copied() {
        let parent = node.parent();
        if starts_with(parent, node, &["call_expression"]) {
            continue;
        }
        list.push(concern(
            source,
            node,
            "Indirect require use is not resolved",
        ));
        // Reading `require.main` or `typeof require` does not rebind it; anything else might.
        let reads = starts_with(parent, node, &["member_expression", "subscript_expression"]);
        let typeof_use = parent.is_some_and(|parent| {
            parent.kind() == "unary_expression"
                && crate::members::children(parent)
                    .into_iter()
                    .any(|child| child.kind() == "typeof")
        });
        shadows = shadows || !(reads || typeof_use);
    }
    for node in scan.require_members.iter().copied() {
        list.push(concern(source, node, "Unproven require member use"));
    }
    for node in scan.subscripts.iter().copied() {
        list.push(concern(source, node, "Computed require member use"));
    }
    let modules = scan.module_name;
    for node in scan.pairs.iter().copied() {
        let Some(key) = node.child(0) else { continue };
        let computed = key.kind() == "computed_property_name";
        let inner = if computed {
            key.named_child(0).unwrap_or(key)
        } else {
            key
        };
        let name = if inner.kind() == "string" {
            literal(Some(inner), source)
        } else {
            Some(source.text(inner))
        };
        // A computed key may select `require` from the module object by a name built at runtime.
        let runtime_name = computed && inner.kind() != "string";
        if name.as_deref() == Some("require") || (runtime_name && modules) {
            list.push(concern(
                source,
                node,
                "Indirect require binding is not resolved",
            ));
        }
    }
    shadows
}

fn comment_concerns(
    source: &Source,
    root: Node,
    scan: &Scan,
    suffix: Option<Suffix>,
) -> Vec<Concern> {
    let mut list = Vec::new();
    // `tsc` reads JSDoc types only in JavaScript files; an unknown suffix keeps the gap.
    let jsdoc_scope = !matches!(
        suffix.and_then(Suffix::source_kind),
        Some(SourceKind::TypeScript | SourceKind::Declaration)
    );
    // Triple-slash directives count only before the first statement of the file.
    let first = crate::members::children(root)
        .into_iter()
        .find(|child| !matches!(child.kind(), "comment" | "hash_bang_line"))
        .map_or(source.data.len(), |child| child.start_byte());
    for node in scan.comments.iter().copied() {
        let body = source.text(node);
        let directive = if node.start_byte() < first {
            jsdoc::triple_slash(&body)
        } else {
            None
        };
        // A `types` entry is no concern: it only adds globals, which the catalog does not model.
        if let Some(path) = directive {
            let reason = format!("Unobserved triple-slash reference: {path}");
            list.push(concern(source, node, &reason));
        }
        if jsdoc_scope && jsdoc::imports(&body) {
            list.push(concern(source, node, "JSDoc import is not observed"));
        }
    }
    list
}

/// `augmentations.augmentation_concerns`: `declare module "./x"` names a file of the project, as an
/// import does (#976). A bare name reaches one only through `paths` or `baseUrl`, and only in a
/// module file; a wildcard name is a pattern. The resolver is not asked: when the project has
/// `paths` or `baseUrl`, such a bare name is a concern.
fn augmentation_concerns(
    source: &Source,
    scan: &Scan,
    (module_file, aliased): (bool, bool),
) -> Vec<Concern> {
    let mut list = Vec::new();
    for node in scan.augmentations.iter().copied() {
        let text = source.text(node);
        let value: String = text
            .chars()
            .skip(1)
            .take(text.chars().count().saturating_sub(2))
            .collect();
        let bare = module_file && aliased && !value.is_empty() && !value.contains('*');
        if value.starts_with(['.', '/']) || bare {
            let reason = format!("Unobserved module augmentation: {value}");
            list.push(concern(source, node, &reason));
        }
    }
    list
}

/// The concerns of one file, in the order that `parse.parse` collects them.
pub fn read(
    source: &Source,
    root: Node,
    scan: &Scan,
    references: &[Reference],
    suffix: Option<Suffix>,
    augmenting: (bool, bool),
) -> Found {
    let mut list = Vec::new();
    // `module[name]` can reach `require` without spelling it.
    let needed = contains(source.data, b"require") || contains(source.data, b"module");
    let shadows_require = needed && require_concerns(source, scan, &mut list);
    let mut loaders: Vec<Span> = references
        .iter()
        .filter(|item| matches!(item.specifier.as_deref(), Some("module" | "node:module")))
        .map(|item| item.span.clone())
        .collect();
    if contains(source.data, b"createRequire") {
        loaders.extend(scan.create_require.iter().map(|n| source.span(*n, None)));
    }
    // One gap per file: the first use already makes every later `require` unprovable.
    if let Some(first) = loaders
        .into_iter()
        .min_by_key(|span| (span.line, span.column))
    {
        list.push(Concern {
            reason: LOADER.to_owned(),
            span: first,
        });
    }
    if contains(source.data, b"/**") || contains(source.data, b"///") {
        list.extend(comment_concerns(source, root, scan, suffix));
    }
    if contains(source.data, b"module") {
        list.extend(augmentation_concerns(source, scan, augmenting));
    }
    Found {
        list,
        shadows_require,
    }
}
