// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `unused_public`: a public name of a component that no other component uses (AD-670).
//!
//! The rule judges each module-level item that the code declares public below `source`. A user
//! outside the scan (a binary that the scan does not read, an external API) is stated by name in
//! `external_users` with its consumer and a reason; no other exemption exists.

use crate::error::{invalid, Parsed};
use crate::json::{field, Json};
use crate::model::{RuleHead, Selector};
use crate::read::{fields, nonempty_field, repeats, rule_record};
use crate::words::value_of;

closed_enum!(
    /// The kind of a public item, as the symbol facts name it.
    PublicItemKind {
        /// A function at module level.
        Function,
        /// A class, a struct, an enum or a trait.
        Class,
        /// A constant.
        Constant,
        /// A constant with a value that is known statically (a Rust `static`).
        StaticConstant,
        /// A type alias.
        TypeAlias,
        /// A name binding.
        Binding,
        /// An alias of another name.
        Alias,
        /// A binding that is set at run time.
        DynamicBinding,
        /// A macro.
        Macro,
    }
);

impl PublicItemKind {
    /// The word of the kind, as the contract and the symbol facts write it.
    pub fn word(self) -> &'static str {
        match self {
            PublicItemKind::Function => "function",
            PublicItemKind::Class => "class",
            PublicItemKind::Constant => "constant",
            PublicItemKind::StaticConstant => "static_constant",
            PublicItemKind::TypeAlias => "type_alias",
            PublicItemKind::Binding => "binding",
            PublicItemKind::Alias => "alias",
            PublicItemKind::DynamicBinding => "dynamic_binding",
            PublicItemKind::Macro => "macro",
        }
    }
}

record!(
    pub(crate),
    /// A public item that a consumer outside the scan uses.
    ExternalUser {
        /// The item as `module:Name`.
        symbol: String,
        /// Who uses it: a binary, a tool or an API that the scan does not read.
        consumer: String,
        /// Why that consumer needs the item.
        rationale: String,
    }
);

record!(
    pub(crate),
    /// A rule that each public name of a component has a user in another component.
    UnusedPublic {
        /// The id, rationale, provenance and decider that every rule holds.
        head: RuleHead,
        /// The selector of the modules whose public items the rule judges.
        source: Selector,
        /// The kinds of item that the rule judges; empty is every kind.
        item_kinds: Vec<PublicItemKind>,
        /// The items that a consumer outside the scan uses, each with its reason.
        external_users: Vec<ExternalUser>,
    }
);

pub(crate) fn unused_public(raw: &Json, label: &str) -> Parsed<UnusedPublic> {
    let (item, head) = rule_record(raw, &["source"], &["item_kinds", "external_users"], label)?;
    let item_kinds = match field(item, "item_kinds") {
        None => Vec::new(),
        Some(Json::Array(words)) if !words.is_empty() => words
            .iter()
            .map(|word| match word {
                Json::Text(text) => value_of(text),
                _ => None,
            })
            .collect::<Option<Vec<PublicItemKind>>>()
            .ok_or_else(|| invalid(format!("{label}.item_kinds names an unknown kind")))?,
        Some(_) => {
            return Err(invalid(format!(
                "{label}.item_kinds must be a non-empty array"
            )))
        }
    };
    let users = match field(item, "external_users") {
        None => &[][..],
        Some(Json::Array(users)) => users.as_slice(),
        Some(_) => return Err(invalid(format!("{label}.external_users must be an array"))),
    };
    let external_users = users
        .iter()
        .enumerate()
        .map(|(index, raw)| user(raw, &format!("{label}.external_users[{index}]")))
        .collect::<Parsed<Vec<_>>>()?;
    if repeats(&item_kinds) || repeats(&external_users) {
        return Err(invalid(format!("{label} must not repeat an entry")));
    }
    Ok(UnusedPublic {
        head,
        source: nonempty_field(item, "source", label)?,
        item_kinds,
        external_users,
    })
}

fn user(raw: &Json, label: &str) -> Parsed<ExternalUser> {
    let entry = fields(raw, &["symbol", "consumer", "rationale"], &[], label)?;
    let symbol: String = nonempty_field(entry, "symbol", label)?;
    let named = symbol
        .split_once(':')
        .is_some_and(|(module, name)| !module.is_empty() && !name.is_empty());
    if !named {
        return Err(invalid(format!("{label}.symbol must be module:Name")));
    }
    Ok(ExternalUser {
        symbol,
        consumer: nonempty_field(entry, "consumer", label)?,
        rationale: nonempty_field(entry, "rationale", label)?,
    })
}

#[cfg(test)]
#[path = "unused_public_tests.rs"]
mod tests;
