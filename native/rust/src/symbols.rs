// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol records (AD-351, slice 5b-4a): one record for each definition that the scan reads,
//! with its visibility and its module. A member of an inherent `impl` is a method of its type, and
//! the type must be a definition of the same module and scope. A member whose type is not found
//! there is not invented and gets no gap (AD-351): the graph lists the symbols as PARTIAL, and
//! slice 5b-4b adds the count of unread items.

use std::collections::BTreeMap;

use archkeel_facts::data::{CallableData, ClassData, Declared, ValueData};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::nested::{MemberInventory, VisibilityDetail};
use archkeel_facts::vocab::{
    Area, ClassKind, EvidenceClass, InventoryStatus, MemberKind, MethodKind, SymbolCategory,
};
use archkeel_facts::{Record, SymbolFact};

use crate::builder::Builder;
use crate::definitions::{Access, Definition, Form, Owner};
use crate::tree::Module;

/// Where a definition stands: its qualified name and the definition that holds it.
struct Place {
    qualified: String,
    parent: Option<usize>,
}

/// The qualified name of a module item: the module, the inline modules and the name.
fn item_name(module: &str, def: &Definition) -> String {
    let path = def.scope.iter().chain([&def.name]);
    path.fold(module.to_owned(), |id, part| format!("{id}.{part}"))
}

/// The place of each definition. A member has a place only when its holder is a definition of the
/// same module and scope: an `impl` of a type that is not found there is not read (AD-351).
fn place(module: &str, defs: &[Definition]) -> Vec<Option<Place>> {
    let held = |def: &Definition, forms: &[Form], name: &str| {
        defs.iter().position(|other| {
            other.owner == Owner::Module
                && other.scope == def.scope
                && other.name == name
                && forms.contains(&other.form)
        })
    };
    defs.iter()
        .map(|def| {
            let holder = match &def.owner {
                Owner::Module => {
                    return Some(Place {
                        qualified: item_name(module, def),
                        parent: None,
                    })
                }
                Owner::Trait(name) => held(def, &[Form::Trait], name),
                Owner::Impl(ty) => ty
                    .as_deref()
                    .and_then(|name| held(def, &[Form::Struct, Form::Enum, Form::Alias], name)),
            }?;
            Some(Place {
                qualified: format!("{}.{}", item_name(module, defs.get(holder)?), def.name),
                parent: Some(holder),
            })
        })
        .collect()
}

fn detail(def: &Definition) -> VisibilityDetail {
    let (kind, basis, spelling) = match &def.access {
        Access::Public => ("public", "declared", "pub".to_owned()),
        Access::Package(text) => ("package", "declared", text.clone()),
        Access::Private => ("private", "language", def.name.clone()),
    };
    VisibilityDetail {
        basis: basis.to_owned(),
        kind: kind.to_owned(),
        spelling: spelling.to_owned(),
    }
}

/// The member receipts of a class-like definition. Both are partial: another module, a macro or a
/// field that the scan does not read may add a member (AD-351). The methods are those found here.
fn inventories(methods: &[FactId]) -> Vec<MemberInventory> {
    let receipt = |kind, ids: Vec<FactId>, reason: &str| MemberInventory {
        definition_ids: ids,
        kind,
        reason: Some(reason.to_owned()),
        schema_version: "1.0.0".to_owned(),
        status: InventoryStatus::Partial,
    };
    vec![
        receipt(MemberKind::Attribute, Vec::new(), "Fields are not read"),
        receipt(
            MemberKind::Method,
            methods.to_vec(),
            "Members of an impl block in another module and members that a macro generates are not read",
        ),
    ]
}

fn fact(def: &Definition, header: Declared, methods: &[FactId]) -> SymbolFact {
    let value = |category| ValueData::declared(header.clone(), category);
    match def.form {
        Form::Function if def.owner == Owner::Module => {
            let mut data = CallableData::declared(header, None);
            data.is_async = def.is_async.then_some(true);
            SymbolFact::Function(data)
        }
        Form::Function => {
            let kind = if def.receiver {
                MethodKind::Instance
            } else {
                MethodKind::Static
            };
            let mut data = CallableData::declared(header, Some(kind));
            data.is_async = def.is_async.then_some(true);
            SymbolFact::Method(data)
        }
        Form::Struct | Form::Enum | Form::Trait => {
            let kind = match def.form {
                Form::Struct => ClassKind::Class,
                Form::Enum => ClassKind::Enum,
                _ => ClassKind::Protocol,
            };
            let mut data = ClassData::declared(header, kind);
            data.member_inventories = inventories(methods);
            if def.form == Form::Enum {
                data.enum_members = Some(def.variants.clone());
            }
            SymbolFact::Class(data)
        }
        Form::Constant => SymbolFact::Constant(value(Some(SymbolCategory::Constant))),
        Form::Static => SymbolFact::StaticConstant(value(None)),
        Form::Alias => SymbolFact::TypeAlias(value(Some(SymbolCategory::TypeAlias))),
        Form::Macro => SymbolFact::Macro(value(Some(SymbolCategory::Macro))),
    }
}

fn id(module: &str, qualified: &str, def: &Definition) -> String {
    let site = &def.site;
    let parts = [
        Part::Text(module),
        Part::Text(qualified),
        Part::Number(site.line),
        Part::Number(site.column),
    ];
    stable_id("RSDEF", &parts)
}

impl Builder {
    /// The symbol records of one module. A definition that the scan cannot read gives no record
    /// and no gap (AD-351).
    pub(crate) fn symbols(&mut self, module: &Module) {
        let defs = &module.scan.definitions;
        let places = place(&module.module, defs);
        let ids: Vec<Option<String>> = (defs.iter().zip(&places))
            .map(|(def, found)| {
                found
                    .as_ref()
                    .map(|at| id(&module.module, &at.qualified, def))
            })
            .collect();
        let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
        for found in places.iter().flatten() {
            *counts.entry(found.qualified.as_str()).or_default() += 1;
        }
        let mut methods: BTreeMap<usize, Vec<FactId>> = BTreeMap::new();
        for ((def, found), identity) in defs.iter().zip(&places).zip(&ids) {
            let held = found.as_ref().and_then(|at| at.parent);
            if let (Some(held), Some(identity), Form::Function) = (held, identity, def.form) {
                methods
                    .entry(held)
                    .or_default()
                    .push(FactId::new(identity.as_str()));
            }
        }
        for (index, (def, found)) in defs.iter().zip(&places).enumerate() {
            let (Some(at), Some(Some(identity))) = (found, ids.get(index)) else {
                continue;
            };
            let holder = at.parent.and_then(|held| places.get(held)?.as_ref());
            let lexical = at.parent.and_then(|held| ids.get(held)?.clone());
            let header = Declared {
                module: ModuleName::new(&module.module),
                package: PackageName::new(module.package()),
                name: def.name.clone(),
                qualified_name: at.qualified.clone(),
                parent: holder.map(|held| held.qualified.clone()),
                lexical_parent_id: lexical.map(FactId::new),
                unique: counts.get(at.qualified.as_str()) == Some(&1),
                visibility: detail(def),
            };
            let evidence = self.cite(&module.rel, &def.site);
            self.symbols.push(Record {
                id: FactId::new(identity.as_str()),
                evidence_class: EvidenceClass::Fact,
                area: Area::Source,
                title: format!("{} declaration", at.qualified),
                subjects: vec![at.qualified.clone()],
                evidence_ids: vec![EvidenceId::new(evidence)],
                fact_ids: Vec::new(),
                data: fact(def, header, methods.get(&index).map_or(&[], Vec::as_slice)),
            });
        }
    }
}

impl Builder {
    /// #1450: the items that a module-level call of `def` publishes; another call publishes none. The arms of the macro that
    /// the call names follow its input; an inner macro gives each of its arms.
    pub(crate) fn macro_items(
        &mut self,
        module: &Module,
        call: &crate::scan::MacroCall,
        def: &crate::scan::MacroDef,
        named: bool,
    ) {
        if !call.fills {
            return;
        }
        let level = &def.item_level;
        let (mut items, opaque) = match named {
            true => crate::macro_items::published(level, &def.name, &call.public.head),
            false => (level.public.clone(), level.opaque),
        };
        // An arm may write items of the call tokens, which only the call shows.
        if opaque && call.public.bare_pub {
            items.extend(call.public.items.iter().cloned());
        }
        self.macro_symbols(module, call, &items);
    }

    /// The public items that a module-level call of a `macro_rules!` of the workspace writes
    /// (#1450, AD-718). A name that the call gives through a metavariable is not read: the record
    /// keeps the kind and the place, and its visibility basis is `macro_call`. An inline `mod` of
    /// the expansion holds items that are not read: an item of no kind.
    pub(crate) fn macro_symbols(
        &mut self,
        module: &Module,
        call: &crate::scan::MacroCall,
        items: &std::collections::BTreeSet<(String, String, bool)>,
    ) {
        for (kind, name, from_call) in items {
            // A `vis` metavariable is public only when the call holds a bare `pub`; then the
            // visibility is not read.
            if *from_call && !call.public.bare_pub {
                continue;
            }
            let form = match kind.as_str() {
                "fn" => Some(Form::Function),
                "const" => Some(Form::Constant),
                "static" => Some(Form::Static),
                "struct" | "union" => Some(Form::Struct),
                "enum" => Some(Form::Enum),
                "trait" => Some(Form::Trait),
                "type" => Some(Form::Alias),
                "macro" => Some(Form::Macro),
                _ => None,
            };
            let named = form.is_some() && !name.is_empty() && !name.starts_with('$') && !from_call;
            let def = Definition {
                form: form.unwrap_or(Form::Constant),
                name: if name.is_empty() {
                    format!("${kind}")
                } else {
                    name.clone()
                },
                scope: call.scope.clone(),
                access: Access::Public,
                owner: Owner::Module,
                site: call.site.clone(),
                variants: Vec::new(),
                receiver: false,
                is_async: false,
                ret: crate::definitions::Written::Unknown,
            };
            let qualified = item_name(&module.module, &def);
            let mut visibility = detail(&def);
            if !named {
                visibility.basis = "macro_call".to_owned();
                visibility.spelling = format!("{}!", call.name);
            }
            let header = Declared {
                module: ModuleName::new(&module.module),
                package: PackageName::new(module.package()),
                name: def.name.clone(),
                qualified_name: qualified.clone(),
                parent: None,
                lexical_parent_id: None,
                unique: false,
                visibility,
            };
            let identity = id(&module.module, &format!("{qualified}!{kind}"), &def);
            let data = match form {
                Some(_) => fact(&def, header, &[]),
                None => SymbolFact::DynamicBinding(ValueData::declared(header, None)),
            };
            let evidence = self.cite(&module.rel, &call.site);
            self.symbols.push(Record {
                id: FactId::new(identity),
                evidence_class: EvidenceClass::Fact,
                area: Area::Source,
                title: format!("{qualified} declaration by {}!", call.name),
                subjects: vec![qualified],
                evidence_ids: vec![EvidenceId::new(evidence)],
                fact_ids: Vec::new(),
                data,
            });
        }
    }
}

#[cfg(test)]
#[path = "symbols_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "public_items_tests.rs"]
mod public_items;
