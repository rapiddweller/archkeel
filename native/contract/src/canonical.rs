// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The canonical bytes of a contract, equal to Python `contract_bytes`
//! (`json.dumps(asdict(contract), indent=2, ensure_ascii=False) + "\n"`). The keys follow the
//! fields of each dataclass; an absent optional field is left out, as `_without_none` does.

use crate::contract::digest_of;
use crate::model::{
    Component, ComponentLabel, ConstructSelector, Contract, ContractDigest, CycleLevel,
    ForbiddenConstruct, ForbiddenDependency, Requirement, Rule, RuleHead, SelectorMatch,
    TargetKind,
};
use crate::rules::kind_of;
use crate::version::version_text;
use crate::words::spelling;

/// One value of the canonical document.
enum Out {
    Text(String),
    Int(u64),
    Bool(bool),
    List(Vec<Out>),
    Object(Vec<(&'static str, Out)>),
}

/// The fields of one object in order.
#[derive(Default)]
struct Fields(Vec<(&'static str, Out)>);

fn text(value: &str) -> Out {
    Out::Text(value.to_owned())
}

fn word<T: serde::Serialize>(value: &T) -> Out {
    Out::Text(spelling(value))
}

fn texts(values: &[String]) -> Out {
    Out::List(values.iter().map(|value| text(value)).collect())
}

fn labels(values: &[ComponentLabel]) -> Out {
    Out::List(values.iter().map(|value| text(&value.0)).collect())
}

fn put(fields: &mut Fields, key: &'static str, value: Out) {
    fields.0.push((key, value));
}

fn put_some(fields: &mut Fields, key: &'static str, value: Option<Out>) {
    if let Some(value) = value {
        put(fields, key, value);
    }
}

fn close(fields: Fields) -> Out {
    Out::Object(fields.0)
}

/// The canonical bytes of a contract.
pub fn canonical_bytes(contract: &Contract) -> Vec<u8> {
    let mut fields = Fields::default();
    put_some(&mut fields, "$schema", contract.schema.as_deref().map(text));
    put(
        &mut fields,
        "schema_version",
        text(&version_text(contract.version)),
    );
    put(
        &mut fields,
        "components",
        Out::List(contract.components.iter().map(component).collect()),
    );
    put(
        &mut fields,
        "rules",
        Out::List(contract.rules.iter().map(rule).collect()),
    );
    let mut written = String::new();
    write(&mut written, &close(fields), 0);
    written.push('\n');
    written.into_bytes()
}

/// The digest that an amendment binds to: the SHA-256 of the canonical bytes (AD-61).
pub fn canonical_digest(contract: &Contract) -> ContractDigest {
    digest_of(&canonical_bytes(contract))
}

fn requirement(entry: &Requirement) -> Out {
    let mut fields = Fields::default();
    put(&mut fields, "component", text(&entry.component.0));
    put(&mut fields, "rationale", text(&entry.rationale));
    put(&mut fields, "through", texts(&entry.through));
    put_some(
        &mut fields,
        "decided_by",
        entry.decided_by.map(|by| word(&by)),
    );
    close(fields)
}

fn component(item: &Component) -> Out {
    let mut fields = Fields::default();
    put(&mut fields, "id", text(&item.id.0));
    put(&mut fields, "label", text(&item.label.0));
    put(&mut fields, "role", word(&item.role));
    put(&mut fields, "packages", texts(&item.packages));
    put(
        &mut fields,
        "responsibilities",
        texts(&item.responsibilities),
    );
    put(
        &mut fields,
        "forbidden_responsibilities",
        texts(&item.forbidden_responsibilities),
    );
    put(&mut fields, "provenance", texts(&item.provenance));
    put_some(
        &mut fields,
        "capability_id",
        item.capability_id.as_ref().map(|id| text(&id.0)),
    );
    put_some(
        &mut fields,
        "requires",
        item.requires
            .as_ref()
            .map(|entries| Out::List(entries.iter().map(requirement).collect())),
    );
    put_some(&mut fields, "inside", item.inside.as_deref().map(text));
    put_some(&mut fields, "public", item.public.as_deref().map(texts));
    put_some(&mut fields, "planned", item.planned.as_deref().map(texts));
    put_some(
        &mut fields,
        "decided_by",
        item.decided_by.map(|by| word(&by)),
    );
    put_some(
        &mut fields,
        "namespace",
        item.namespace.as_deref().map(text),
    );
    if !item.exact_modules.is_empty() {
        put(&mut fields, "exact_modules", texts(&item.exact_modules));
    }
    put_some(&mut fields, "layer", item.layer.as_deref().map(text));
    put_some(
        &mut fields,
        "lifecycle",
        item.lifecycle.map(|value| word(&value)),
    );
    close(fields)
}

/// `id` and `kind`, the fields that every rule starts with.
fn start(rule: &Rule, head: &RuleHead) -> Fields {
    let mut fields = Fields::default();
    put(&mut fields, "id", text(&head.id.0));
    put(&mut fields, "kind", word(&kind_of(rule)));
    fields
}

/// `rationale`, `provenance` and `decided_by`, in the middle of every rule.
fn reasons(fields: &mut Fields, head: &RuleHead) {
    put(fields, "rationale", text(&head.rationale));
    put(fields, "provenance", texts(&head.provenance));
    put(fields, "decided_by", word(&head.decided_by));
}

fn rule(rule: &Rule) -> Out {
    let head = crate::rules::head_of(rule);
    let mut fields = start(rule, head);
    match rule {
        Rule::ForbiddenDependency(item) => forbidden_dependency(&mut fields, item),
        Rule::ForbiddenConstruct(item) => forbidden_construct(&mut fields, item),
        Rule::AllowedDependency(item) => {
            put(&mut fields, "source", text(&item.source));
            put(&mut fields, "target", text(&item.target));
            reasons(&mut fields, head);
        }
        Rule::ExternalDependencyScope(item) => {
            put(&mut fields, "dependency", text(&item.dependency));
            put(&mut fields, "allowed_sources", texts(&item.allowed_sources));
            reasons(&mut fields, head);
            put(&mut fields, "exact_sources", texts(&item.exact_sources));
        }
        Rule::CompleteAssignment(item) | Rule::CompleteExternalScope(item) => {
            put(&mut fields, "source", text(&item.source));
            reasons(&mut fields, head);
        }
        Rule::RootLayout(item) => {
            put(&mut fields, "root", text(&item.root));
            put(
                &mut fields,
                "allowed_children",
                texts(&item.allowed_children),
            );
            reasons(&mut fields, head);
        }
        _ => structure_rule(&mut fields, rule, head),
    }
    close(fields)
}

fn structure_rule(fields: &mut Fields, rule: &Rule, head: &RuleHead) {
    match rule {
        Rule::CompleteRequires(item) => {
            reasons(fields, head);
            put(
                fields,
                "include_type_checking",
                Out::Bool(item.include_type_checking),
            );
        }
        Rule::LayerOrder(item) => {
            put(fields, "layers", texts(&item.layers));
            reasons(fields, head);
            put_some(fields, "components", item.components.as_deref().map(labels));
        }
        Rule::NoComponentCycles(item) => {
            reasons(fields, head);
            if item.level == CycleLevel::Module {
                put(fields, "level", word(&item.level));
            }
            put_some(fields, "components", item.components.as_deref().map(labels));
        }
        Rule::InterfaceBoundary(item) => {
            reasons(fields, head);
            put(
                fields,
                "include_type_checking",
                Out::Bool(item.include_type_checking),
            );
            let grants = item.module_object_grants.as_ref().map(|grants| {
                Out::List(
                    grants
                        .iter()
                        .map(|grant| {
                            let mut entry = Fields::default();
                            put(&mut entry, "source_module", text(&grant.source_module));
                            put(&mut entry, "target_module", text(&grant.target_module));
                            close(entry)
                        })
                        .collect(),
                )
            });
            put_some(fields, "module_object_grants", grants);
        }
        Rule::SiblingIsolation(item) => {
            put(fields, "members", texts(&item.members));
            reasons(fields, head);
            put(
                fields,
                "include_type_checking",
                Out::Bool(item.include_type_checking),
            );
        }
        _ => {}
    }
}

fn forbidden_dependency(fields: &mut Fields, item: &ForbiddenDependency) {
    put(fields, "source", text(&item.source));
    put(fields, "target", text(&item.target));
    put(
        fields,
        "include_type_checking",
        Out::Bool(item.include_type_checking),
    );
    reasons(fields, &item.head);
    put_some(
        fields,
        "target_symbol",
        item.target_symbol.as_deref().map(text),
    );
    put(fields, "allowed_sources", texts(&item.allowed_sources));
    // An absent permission keeps the amendment digests of older contracts.
    if item.source_match != SelectorMatch::Prefix {
        put(fields, "source_match", word(&item.source_match));
    }
    if item.target_match != SelectorMatch::Prefix {
        put(fields, "target_match", word(&item.target_match));
    }
    if item.target_kind != TargetKind::Module {
        put(fields, "target_kind", word(&item.target_kind));
    }
}

fn forbidden_construct(fields: &mut Fields, item: &ForbiddenConstruct) {
    put(fields, "source", text(&item.source));
    let constructs = item.constructs.iter().map(|kind| word(&kind));
    put(fields, "constructs", Out::List(constructs.collect()));
    reasons(fields, &item.head);
    put(fields, "allowed_sources", texts(&item.allowed_sources));
    put(fields, "exact_sources", texts(&item.exact_sources));
    if !item.allowed_type_ignores.is_empty() {
        let ignores = item.allowed_type_ignores.iter().map(|ignore| {
            let mut entry = Fields::default();
            put(&mut entry, "qualified_name", text(&ignore.qualified_name));
            put(&mut entry, "line", Out::Int(ignore.line));
            put(&mut entry, "statement", text(&ignore.statement));
            put(&mut entry, "tag", text(&ignore.tag));
            close(entry)
        });
        put(fields, "allowed_type_ignores", Out::List(ignores.collect()));
    }
    put_some(fields, "selector", item.selector.as_ref().map(selector));
}

fn selector(item: &ConstructSelector) -> Out {
    let mut fields = Fields::default();
    put(&mut fields, "receiver", text(&item.receiver));
    put_some(&mut fields, "member", item.member.as_deref().map(text));
    put(&mut fields, "role", word(&item.role));
    put_some(&mut fields, "literal", item.literal.as_deref().map(text));
    close(fields)
}

/// A JSON string as Python `json.dumps` writes it with `ensure_ascii=False`.
fn write_text(out: &mut String, value: &str) {
    out.push('"');
    for character in value.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            control if u32::from(control) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", u32::from(control)));
            }
            other => out.push(other),
        }
    }
    out.push('"');
}

fn indent(out: &mut String, level: usize) {
    out.push('\n');
    out.push_str(&"  ".repeat(level));
}

/// The `indent=2` layout: an empty list is `[]`, an item has its own line.
fn write(out: &mut String, value: &Out, level: usize) {
    match value {
        Out::Text(text) => write_text(out, text),
        Out::Int(number) => out.push_str(&number.to_string()),
        Out::Bool(flag) => out.push_str(if *flag { "true" } else { "false" }),
        Out::List(items) if items.is_empty() => out.push_str("[]"),
        Out::Object(entries) if entries.is_empty() => out.push_str("{}"),
        Out::List(items) => {
            out.push('[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                indent(out, level + 1);
                write(out, item, level + 1);
            }
            indent(out, level);
            out.push(']');
        }
        Out::Object(entries) => {
            out.push('{');
            for (index, (key, item)) in entries.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                indent(out, level + 1);
                write_text(out, key);
                out.push_str(": ");
                write(out, item, level + 1);
            }
            indent(out, level);
            out.push('}');
        }
    }
}
