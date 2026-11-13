// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! L-117: these versioned derives emit impl code using their own crate, written field types,
//! and documented helper paths. The identity resolver must prove both registry artifacts.
//! Every helper is checked, including fields and variants. Unlisted keys or opaque values
//! withhold the model. This models written dependencies, not trait dispatch (issue #1004).

use syn::parse::Parser;
use syn::visit::{self, Visit};
use syn::{Attribute, Expr, Item, Lit, Meta, Token};

pub(crate) struct Known {
    pub package: &'static str,
    pub name: &'static str,
    pub version: &'static str,
    pub implementation: &'static str,
    pub helpers: &'static [&'static str],
}

/// Reviewed registry implementations: serde/serde_derive 1.0.229 and schemars/_derive 1.2.3.
pub(crate) const KNOWN: &[Known] = &[
    Known {
        package: "serde",
        name: "Serialize",
        version: "1.0.229",
        implementation: "serde_derive",
        helpers: &["serde"],
    },
    Known {
        package: "serde",
        name: "Deserialize",
        version: "1.0.229",
        implementation: "serde_derive",
        helpers: &["serde"],
    },
    Known {
        package: "schemars",
        name: "JsonSchema",
        version: "1.2.3",
        implementation: "schemars_derive",
        helpers: &["serde", "schemars", "validate", "garde"],
    },
];

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Usage {
    pub path: Vec<String>,
    pub absolute: bool,
    pub complete: bool,
    pub block: bool,
    pub prelude: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Proof {
    Derive(Usage),
    Helper {
        namespace: String,
        candidates: Vec<Usage>,
    },
}

#[derive(Default)]
pub(crate) struct Context {
    pub candidates: Vec<Usage>,
}

impl Context {
    pub(crate) fn of(item: &Item, block: bool, prelude: bool) -> Self {
        let attrs = crate::attrs::item_attributes(item);
        if !attrs.iter().any(|a| a.path().is_ident("derive")) {
            return Self::default();
        }
        let mut checked = Check(true);
        checked.visit_item(item);
        let candidates = attrs
            .iter()
            .filter(|a| a.path().is_ident("derive"))
            .filter_map(|a| super::kinds::list::<syn::Path>(&a.meta))
            .flatten()
            .map(|path| Usage {
                path: path
                    .segments
                    .iter()
                    .map(|s| crate::tokens::plain(&s.ident))
                    .collect(),
                absolute: path.leading_colon.is_some(),
                complete: checked.0,
                block,
                prelude,
            })
            .collect();
        Self { candidates }
    }
}

#[derive(Clone, Copy)]
enum ValueKind {
    Flag,
    Text,
    Path,
    Type,
    Bounds,
    Default,
    Borrow,
    SplitText,
}

/// Sources per key: serde.rs/field-attrs.html#<key>, container-attrs.html#<key>, and
/// variant-attrs.html#<key>; schemars keys: graham.cool/schemars/deriving/attributes/#<key>.
/// `with` is a module for serde and a type for schemars. Both must parse as Rust syntax.
const HELPERS: &[(&str, &str, ValueKind)] = &[
    // https://serde.rs/field-attrs.html#with, #serialize_with, #deserialize_with,
    // #skip_serializing_if, #getter; https://serde.rs/container-attrs.html#crate.
    ("serde", "with serialize_with deserialize_with skip_serializing_if getter crate", ValueKind::Path),
    // https://serde.rs/container-attrs.html#from, #into, #try_from, #remote.
    ("serde", "from into try_from remote", ValueKind::Type),
    // https://serde.rs/container-attrs.html#bound; https://serde.rs/field-attrs.html#bound.
    ("serde", "bound", ValueKind::Bounds),
    // https://serde.rs/field-attrs.html#default--path; https://serde.rs/container-attrs.html#default.
    ("serde", "default", ValueKind::Default),
    // https://serde.rs/container-attrs.html#rename, #rename_all, #rename_all_fields.
    ("serde", "rename rename_all rename_all_fields", ValueKind::SplitText),
    // https://serde.rs/field-attrs.html#alias; https://serde.rs/container-attrs.html#tag, #expecting.
    ("serde", "alias tag content expecting", ValueKind::Text),
    // https://serde.rs/field-attrs.html#skip, #skip_serializing, #skip_deserializing, #flatten;
    // https://serde.rs/container-attrs.html#deny_unknown_fields, #transparent, #field_identifier,
    // #variant_identifier; https://serde.rs/variant-attrs.html#other, #untagged.
    ("serde", "skip skip_serializing skip_deserializing flatten deny_unknown_fields transparent field_identifier variant_identifier other untagged", ValueKind::Flag),
    // https://serde.rs/field-attrs.html#borrow.
    ("serde", "borrow", ValueKind::Borrow),
    // https://graham.cool/schemars/deriving/attributes/#with, #from, #into.
    ("schemars", "with from try_from into", ValueKind::Type),
    // https://graham.cool/schemars/deriving/attributes/#schema_with, #crate, #default.
    ("schemars", "schema_with crate serialize_with skip_serializing_if", ValueKind::Path),
    ("schemars", "default", ValueKind::Default),
    // https://graham.cool/schemars/deriving/attributes/#bound.
    ("schemars", "bound", ValueKind::Bounds),
    // https://graham.cool/schemars/deriving/attributes/#rename, #rename_all, #rename_all_fields.
    ("schemars", "rename rename_all rename_all_fields", ValueKind::SplitText),
    // https://graham.cool/schemars/deriving/attributes/#tag, #title-description.
    ("schemars", "tag content title description", ValueKind::Text),
    // https://graham.cool/schemars/deriving/attributes/#skip, #flatten, #deny_unknown_fields,
    // #transparent, #inline, #required, #deprecated.
    ("schemars", "skip skip_serializing skip_deserializing flatten deny_unknown_fields transparent untagged inline required deprecated", ValueKind::Flag),
];

fn string(meta: &Meta) -> Option<&syn::LitStr> {
    let Meta::NameValue(pair) = meta else {
        return None;
    };
    let Expr::Lit(syn::ExprLit {
        lit: Lit::Str(value),
        ..
    }) = &pair.value
    else {
        return None;
    };
    Some(value)
}

fn value(kind: ValueKind, meta: &Meta, found: &mut Vec<crate::tokens::Chain>) -> bool {
    use ValueKind as K;
    if matches!(kind, K::Flag | K::Default | K::Borrow) && matches!(meta, Meta::Path(_)) {
        return true;
    }
    if matches!(kind, K::SplitText | K::Bounds) && matches!(meta, Meta::List(_)) {
        return super::kinds::list::<Meta>(meta).is_some_and(|items| {
            items.iter().all(|item| {
                (item.path().is_ident("serialize") || item.path().is_ident("deserialize"))
                    && value(kind, item, found)
            })
        });
    }
    let Some(literal) = string(meta) else {
        return false;
    };
    let text = literal.value();
    if !matches!(kind, K::Text | K::SplitText | K::Borrow) && !crate::tokens::bounded_value(&text) {
        return false;
    }
    let mut paths = Paths { literal, found };
    match kind {
        K::Text | K::SplitText | K::Borrow => true,
        K::Path | K::Default => syn::parse_str::<syn::Path>(&text).is_ok_and(|path| {
            paths.visit_path(&path);
            let mut check = Check(true);
            check.visit_path(&path);
            check.0
        }),
        K::Type => syn::parse_str::<syn::Type>(&text).is_ok_and(|ty| {
            paths.visit_type(&ty);
            let mut check = Check(true);
            check.visit_type(&ty);
            check.0
        }),
        K::Bounds => {
            syn::punctuated::Punctuated::<syn::WherePredicate, Token![,]>::parse_terminated
                .parse_str(&text)
                .is_ok_and(|bounds| {
                    let mut check = Check(true);
                    for bound in bounds {
                        paths.visit_where_predicate(&bound);
                        check.visit_where_predicate(&bound);
                    }
                    check.0
                })
        }
        K::Flag => false,
    }
}

struct Paths<'a> {
    literal: &'a syn::LitStr,
    found: &'a mut Vec<crate::tokens::Chain>,
}

impl<'a> Visit<'a> for Paths<'_> {
    fn visit_path(&mut self, path: &'a syn::Path) {
        self.found.push(crate::tokens::Chain {
            names: path
                .segments
                .iter()
                .map(|s| crate::tokens::plain(&s.ident))
                .collect(),
            absolute: path.leading_colon.is_some(),
            span: self.literal.span(),
        });
        visit::visit_path(self, path);
    }
}

pub(crate) fn helper_paths(attr: &Attribute) -> Option<Vec<crate::tokens::Chain>> {
    let namespace = attr.path().get_ident()?.to_string();
    let mut found = Vec::new();
    for item in super::kinds::list::<Meta>(&attr.meta)? {
        let key = item.path().get_ident()?.to_string();
        let (_, _, kind) = HELPERS
            .iter()
            .find(|(ns, keys, _)| *ns == namespace && keys.split_whitespace().any(|k| k == key))?;
        if !value(*kind, &item, &mut found) {
            return None;
        }
    }
    Some(found)
}

struct Check(bool);

impl<'a> Visit<'a> for Check {
    fn visit_attribute(&mut self, attr: &'a Attribute) {
        if attr.path().is_ident("cfg_attr") {
            self.0 = false;
            return;
        }
        let namespace = attr.path().get_ident().map(ToString::to_string);
        if !namespace.is_some_and(|n| KNOWN.iter().any(|k| k.helpers.contains(&n.as_str()))) {
            return;
        }
        self.0 &= helper_paths(attr).is_some();
    }
    fn visit_macro(&mut self, _: &'a syn::Macro) {
        self.0 = false;
    }
    fn visit_type(&mut self, ty: &'a syn::Type) {
        if matches!(ty, syn::Type::Verbatim(_)) {
            self.0 = false;
        }
        visit::visit_type(self, ty);
    }
}
