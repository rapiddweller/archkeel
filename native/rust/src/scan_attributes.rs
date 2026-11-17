// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in an attribute: a path in its name, its tokens, its strings and the value
//! of `key = value`. The walker of `scan.rs` owns the facts; this file only fills them.

use proc_macro2::Span;
use syn::{Attribute, Meta};

use super::state::{Concern, Via, Walker};
use crate::attrs::kinds::{self as attribute_kinds, Kind};
use crate::attrs::model::{Proof, Usage, KNOWN};
use crate::tokens::{plain, string_paths};

pub(super) fn concern(walker: &mut Walker<'_>, reason: String, span: Span) {
    let site = walker.site(span);
    walker.out.concerns.push(Concern {
        reason,
        site,
        source: None,
        proof: None,
    });
}

pub(super) fn helper_strings(walker: &mut Walker<'_>, attr: &Attribute, list: &syn::MetaList) {
    if let Some(found) = crate::attrs::model::helper_paths(attr) {
        walker.refer_chains(found, &Via::Helper);
    } else {
        attribute_strings(walker, list, &Via::Helper);
    }
}

pub(super) fn expansion(walker: &mut Walker<'_>, meta: &Meta, depth: usize) {
    let path = meta.path();
    let name = path
        .segments
        .iter()
        .map(|s| plain(&s.ident))
        .collect::<Vec<_>>()
        .join("::");
    let prelude = match (depth < 16, attribute_kinds::kind(path)) {
        (true, Some(Kind::Inert | Kind::Cfg)) => return,
        (true, Some(Kind::Prelude)) => true,
        (true, Some(Kind::Derive)) if derive_expansion(walker, meta).is_some() => true,
        (true, Some(Kind::Conditional | Kind::Unsafe))
            if nested_expansion(walker, meta, depth).is_some() =>
        {
            return
        }
        (true, None) if walker.tools && attribute_kinds::tool(path) => return,
        _ => false,
    };
    let mut concern = expansion_concern(
        walker,
        format!("The attribute macro {name} can add code that the scan does not read"),
        path.segments
            .first()
            .map_or(Span::call_site(), |s| s.ident.span()),
    );
    if prelude {
        concern.proof = Some(Proof::Attribute(Usage {
            path: vec![name],
            absolute: false,
            complete: true,
            block: walker.blocks() > 0,
            prelude: walker.tools,
        }));
    } else if (name == "default"
        || KNOWN
            .iter()
            .any(|known| known.helpers.contains(&name.as_str())))
        && !walker.helpers.candidates.is_empty()
    {
        concern.proof = Some(Proof::Helper {
            namespace: name,
            candidates: walker.helpers.candidates.clone(),
        });
    }
    walker.out.concerns.push(concern);
}

pub(super) fn derive_expansion(walker: &mut Walker<'_>, meta: &Meta) -> Option<()> {
    for path in attribute_kinds::list::<syn::Path>(meta)? {
        let name = path
            .segments
            .iter()
            .map(|s| plain(&s.ident))
            .collect::<Vec<_>>()
            .join("::");
        let span = path
            .segments
            .first()
            .map_or(Span::call_site(), |s| s.ident.span());
        let mut concern = expansion_concern(
            walker,
            format!("The derive macro {name} can add code that the scan does not read"),
            span,
        );
        let parts: Vec<_> = path.segments.iter().map(|s| plain(&s.ident)).collect();
        let complete = walker
            .helpers
            .candidates
            .iter()
            .find(|c| c.path == parts)
            .is_some_and(|c| c.complete);
        concern.proof = Some(Proof::Derive(Usage {
            path: parts,
            absolute: path.leading_colon.is_some(),
            complete,
            block: walker.blocks() > 0,
            prelude: walker.tools,
        }));
        walker.derives.push(concern);
    }
    Some(())
}

pub(super) fn nested_expansion(walker: &mut Walker<'_>, meta: &Meta, depth: usize) -> Option<()> {
    let nested = attribute_kinds::list::<Meta>(meta)?;
    let skip = usize::from(meta.path().is_ident("cfg_attr"));
    for nested in nested.iter().skip(skip) {
        expansion(walker, nested, depth + 1);
    }
    Some(())
}

pub(super) fn expansion_concern(walker: &Walker<'_>, reason: String, span: Span) -> Concern {
    Concern {
        reason,
        site: walker.site(span),
        source: Some(walker.inline.clone()),
        proof: None,
    }
}

/// The paths in the strings of an attribute, under any key but the message keys of `tokens`.
pub(super) fn attribute_strings(walker: &mut Walker<'_>, list: &syn::MetaList, via: &Via) {
    let mut found = Vec::new();
    if string_paths(list.tokens.clone(), 0, &mut found).is_none() {
        let reason = "A string in an attribute holds a path that the scan cannot read";
        concern(walker, reason.to_owned(), list.delimiter.span().join());
    }
    walker.refer_chains(found, via);
}

pub(super) fn finish(walker: &mut Walker<'_>) {
    // Namespace and lock proofs require the complete workspace, not this syntax walk.
    walker.out.concerns.append(&mut walker.derives);
}

pub(super) fn gate(walker: &mut Walker<'_>, attrs: &[Attribute], what: &str, span: Span) {
    if let Some(reason) = crate::attrs::hidden_by(attrs, what, walker.features) {
        concern(walker, reason, span);
    }
}
