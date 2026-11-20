// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The call and reference sites of the functions that have a record (AD-520).
//!
//! A name resolves to a symbol only when no scope between the use and the module hides it
//! (`scope.rs`) and the module binds it once with a record (AD-518), or one plain import that is
//! the sole binder of its name brings it from a module that has the record. Any other call is an
//! unresolved site with no target: a receiver whose type is not proven (`self.m()`), an alias,
//! a call of a call, a decorated or conditional target.

use std::collections::{HashMap, HashSet};

use super::DirectMethods;
use archkeel_facts::data::{CallData, ImportData, ReferenceData};
use archkeel_facts::envelope::{ConstructedCall, DirectCall};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::{
    ids::{EvidenceId, FactId, ModuleName},
    nested::{Construction, ResultBinding},
    nullable::Nullable,
    vocab::{Area, EvidenceClass, ReferenceContext, Status, Use},
    CallFact, FactData, ImportFact, Record, ReferenceFact, SymbolFact,
};
use ruff_python_ast::{Expr, ExprCall, ExprName};
use ruff_text_size::{Ranged, TextSize};

use super::found::{Found, Source};
use super::reader::Reader;
use super::scope::{self, Stored, Uses};
use crate::module::{EvidenceMap, Module};
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;

/// What a name of the module body is, for a site.
pub(crate) struct Sym {
    pub class: bool,
    pub function: bool,
    pub constructible: bool,
    direct_function: Option<FactId>,
}

/// True for a record whose name is the module and one part: a class, function or value of the
/// module body.
fn top_level(record: &Record<SymbolFact>) -> bool {
    let fields = record.data.fields();
    let (Some(name), Some(Some(module))) = (fields.qualified_name, fields.module) else {
        return false;
    };
    name.strip_prefix(module)
        .and_then(|rest| rest.strip_prefix('.'))
        .is_some_and(|rest| !rest.contains('.'))
}

/// The symbols of every module by qualified name, and the plain imports that bring one.
pub(crate) struct Context {
    pub symbols: HashMap<String, Sym>,
    /// For each importing module: the name that a plain import binds to the qualified name.
    imports: HashMap<String, HashMap<String, (String, Option<FactId>)>>,
}

impl Context {
    /// The module-level symbols of `found` and the sole plain imports of `records`
    /// (`sole` and `ambiguous` are the sets of the survey).
    pub(crate) fn collect(
        found: &[Found<'_>],
        (records, written): (&[Record<ImportFact>], &[Record<ImportFact>]),
        (sole, ambiguous): (&HashSet<String>, &HashSet<String>),
    ) -> Self {
        let mut symbols = HashMap::new();
        for module in found {
            for record in module.records.iter().filter(|record| top_level(record)) {
                let name = record.data.fields().qualified_name.unwrap_or_default();
                let (class, function) = match &record.data {
                    SymbolFact::Class(_) => (true, false),
                    SymbolFact::Function(_) => (false, true),
                    _ => (false, false),
                };
                let constructible = module.constructible.contains(name);
                let sym = Sym {
                    class,
                    function,
                    constructible,
                    direct_function: function.then(|| record.id.clone()),
                };
                symbols.insert(name.to_owned(), sym);
            }
        }
        let mut imports = HashMap::<String, HashMap<String, _>>::new();
        // AD-654 keeps import order when it substitutes the provider in the view.
        for (record, original) in records.iter().zip(written) {
            let data = record.data.data();
            let id = record.id.as_str();
            let (Some(symbol), Some(binding)) = (&data.symbol, &data.binding) else {
                continue;
            };
            if !sole.contains(id) || ambiguous.contains(id) || data.under_type_checking {
                continue;
            }
            imports
                .entry(data.source_module.as_str().to_owned())
                .or_default()
                .insert(
                    binding.clone(),
                    (
                        format!("{}.{symbol}", data.target_module.as_str()),
                        direct_import(original, data),
                    ),
                );
        }
        Context { symbols, imports }
    }

    /// The qualified name and the symbol that `name` means in `module`, unless `hidden` has it.
    fn resolve(
        &self,
        name: &str,
        module: &str,
        hidden: &HashSet<String>,
    ) -> Option<(String, &Sym)> {
        if hidden.contains(name) {
            return None;
        }
        let own = format!("{module}.{name}");
        if let Some(sym) = self.symbols.get(&own) {
            return Some((own, sym));
        }
        let (target, _) = self.imports.get(module)?.get(name)?;
        Some((target.clone(), self.symbols.get(target)?))
    }
}

fn direct_import(original: &Record<ImportFact>, view: &ImportData) -> Option<FactId> {
    let ImportFact::Import(data) = &original.data else {
        return None;
    };
    (data.module_level_import
        && data.symbols_known
        && data.source_binding_unique == Some(true)
        && data.target_module == view.target_module
        && data.symbol == view.symbol)
        .then(|| original.id.clone())
}

pub(crate) struct Sites {
    pub calls: Vec<Record<CallFact>>,
    pub references: Vec<Record<ReferenceFact>>,
    pub dead: HashSet<String>,
    pub direct: Vec<DirectCall>,
    pub constructed: Vec<ConstructedCall>,
}

/// The sites of the sources of one module.
pub(crate) fn site_records(
    (module, binders): (&Module, &Binders),
    found: &Found<'_>,
    (context, methods): (&Context, &DirectMethods),
    evidence: &mut EvidenceMap,
) -> Sites {
    let mut reader = Reader {
        module,
        evidence_map: evidence,
        shadowed: Reader::shadowed(binders),
        writes: None,
    };
    let (mut calls, mut references, mut dead_sites) = (Vec::new(), Vec::new(), HashSet::new());
    let mut direct = Vec::new();
    let mut constructed = Vec::new();
    for source in &found.sources {
        let params = scope::parameters(source.node);
        let mut hidden = Bound::of(&source.node.body).names();
        hidden.extend(params.iter().cloned());
        let reading = Reading {
            context,
            module: &module.name,
            source,
            hidden: &hidden,
        };
        let uses = Uses::of(source.node);
        let stored = scope::stored(source.node, &reader, &params);
        let start = calls.len();
        for (call, dead) in &uses.calls {
            let record = call_record(&mut reader, &reading, (call, *dead), &stored);
            if *dead {
                dead_sites.extend(record.evidence_ids.iter().map(|id| id.as_str().to_owned()));
            } else if let Expr::Name(name) = call.func.as_ref() {
                direct.extend(reading.direct_call(name.id.as_str(), &record.id, call));
            }
            calls.push(record);
        }
        constructed.extend(methods.witness(source.node, &calls[start..], &uses.calls));
        for (name, _) in uses.names.iter().filter(|(_, dead)| !dead) {
            references.extend(reference(&mut reader, &reading, name));
        }
        references.extend(annotations(&mut reader, &reading));
    }
    Sites {
        calls,
        references,
        dead: dead_sites,
        direct,
        constructed,
    }
}

fn written_actuals(call: &ExprCall) -> Option<Vec<archkeel_facts::envelope::WrittenActual>> {
    let arguments = &call.arguments;
    let positional = arguments.args.iter().map(|expr| {
        (!matches!(expr, Expr::Starred(_)))
            .then_some((None, matches!(expr, Expr::StringLiteral(_))))
    });
    let keywords = arguments.keywords.iter().map(|argument| {
        let keyword = argument.arg.as_ref()?.as_str().to_owned();
        Some((
            Some(keyword),
            matches!(argument.value, Expr::StringLiteral(_)),
        ))
    });
    positional.chain(keywords).collect()
}

/// What the sites of one source read.
struct Reading<'a> {
    context: &'a Context,
    module: &'a str,
    source: &'a Source<'a>,
    hidden: &'a HashSet<String>,
}

impl Reading<'_> {
    fn direct_call(&self, name: &str, site: &FactId, call: &ExprCall) -> Option<DirectCall> {
        let (target, symbol) = self.lookup(name, self.hidden)?;
        let function = symbol.direct_function.as_ref()?;
        let import = if target == format!("{}.{name}", self.module) {
            None
        } else {
            let (_, import) = self.context.imports.get(self.module)?.get(name)?;
            Some(import.as_ref()?.clone())
        };
        Some((
            site.clone(),
            function.clone(),
            import,
            written_actuals(call),
        ))
    }

    /// The symbol that `name` means here. In a method a name that starts with `__` and does not
    /// end with it is mangled with the class name, so it is no symbol of the module.
    fn lookup(&self, name: &str, hidden: &HashSet<String>) -> Option<(String, &Sym)> {
        let mangled = name.starts_with("__") && !name.ends_with("__");
        if mangled && self.source.class_names.is_some() {
            return None;
        }
        self.context.resolve(name, self.module, hidden)
    }

    fn scope(&self) -> (ModuleName, String) {
        (ModuleName::new(self.module), self.source.qualname.clone())
    }
}

fn record<D>(
    reader: &mut Reader<'_, '_>,
    reading: &Reading<'_>,
    node: &impl Ranged,
    (title, data): (String, D),
) -> Record<D> {
    let module = reader.module;
    // The span, not the start: `f()()` and `f()` start at the same place.
    let (start, end) = (node.start().to_usize(), node.end().to_usize());
    let id = stable_id(
        "SITE",
        &[
            Part::Text(&reading.source.id),
            Part::Number(i64::try_from(start).unwrap_or(i64::MAX)),
            Part::Number(i64::try_from(end).unwrap_or(i64::MAX)),
            Part::Text(&title),
        ],
    );
    let mut subjects = vec![reading.source.qualname.clone(), module.name.clone()];
    subjects.sort();
    Record {
        id: FactId::new(id),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title,
        subjects,
        evidence_ids: vec![EvidenceId::new(reader.evidence(node))],
        fact_ids: Vec::new(),
        data,
    }
}

fn call_record(
    reader: &mut Reader<'_, '_>,
    reading: &Reading<'_>,
    (call, dead): (&ExprCall, bool),
    stored: &HashMap<TextSize, Stored<'_>>,
) -> Record<CallFact> {
    let expression = reader
        .text(Some(&call.func))
        .ok()
        .flatten()
        .unwrap_or_else(|| "<call>".to_owned());
    // A call that Python never runs is no met edge (AD-520).
    let target = match &*call.func {
        Expr::Name(name) if !dead => reading.lookup(name.id.as_str(), reading.hidden),
        _ => None,
    };
    let callee = target.filter(|(_, sym)| sym.class || sym.function);
    let targets: Vec<String> = callee.iter().map(|(name, _)| name.clone()).collect();
    let local_function = match &*call.func {
        Expr::Name(name) if !dead => {
            let unhidden = HashSet::new();
            reading
                .context
                .resolve(name.id.as_str(), reading.module, &unhidden)
                .is_some_and(|(_, symbol)| symbol.class || symbol.function)
                && scope::direct_local_function(reading.source.node, name.id.as_str())
        }
        _ => false,
    };
    let status = if local_function {
        Status::Decided
    } else {
        Status::of_candidates(targets.len(), true)
    };
    let mut data = CallData::new(expression.clone(), reading.scope(), status, targets);
    data.source_definition_id = Nullable::Value(FactId::new(reading.source.id.as_str()));
    data.reason = Some(match &callee {
        Some(_) => "plain name with a stable direct binding".to_owned(),
        None if dead => {
            "the call is under a constant-false test or after a statement that leaves".to_owned()
        }
        None if local_function => "callee is the sole direct local function binding".to_owned(),
        None => "callee is not a plain name of one symbol with a record".to_owned(),
    });
    if let Some((name, sym)) = callee.filter(|(_, sym)| sym.class) {
        data.construction = Nullable::Value(Construction {
            candidates_truncated: false,
            reason: "call of a class with a stable direct binding".to_owned(),
            status: Status::of_candidates(1, sym.constructible),
            targets: vec![name],
        });
        data.result_bindings = stored
            .get(&call.range().start())
            .map(|item| vec![result(reader, reading, item)]);
    }
    record(reader, reading, call, (expression, CallFact::Calls(data)))
}

/// The binding that `name = A()` stores.
fn result(reader: &mut Reader<'_, '_>, reading: &Reading<'_>, item: &Stored<'_>) -> ResultBinding {
    let crate::module::Location { line, column, .. } = reader.module.location(item.statement);
    let id = stable_id(
        "BIND",
        &[
            Part::Text(&reading.source.id),
            Part::Text(item.name),
            Part::Number(line),
            Part::Number(column),
        ],
    );
    ResultBinding {
        annotation: item.annotation.clone(),
        inferred_type: None,
        definition_contexts: Vec::new(),
        evidence_ids: vec![EvidenceId::new(reader.evidence(item.statement))],
        id: FactId::new(id),
        initializer: item.initializer.clone(),
        name: item.name.to_owned(),
        target_kind: "name".to_owned(),
    }
}

/// A read of a name that resolves to a symbol; a name that does not is no site.
fn reference(
    reader: &mut Reader<'_, '_>,
    reading: &Reading<'_>,
    name: &ExprName,
) -> Option<Record<ReferenceFact>> {
    let (target, _) = reading
        .context
        .resolve(name.id.as_str(), reading.module, reading.hidden)?;
    Some(site(
        reader,
        reading,
        name,
        (Use::Value, ReferenceContext::Value),
        target,
    ))
}

fn site(
    reader: &mut Reader<'_, '_>,
    reading: &Reading<'_>,
    name: &ExprName,
    (use_, context): (Use, ReferenceContext),
    target: String,
) -> Record<ReferenceFact> {
    let expression = name.id.to_string();
    let mut data = ReferenceData::new(
        expression.clone(),
        reading.scope(),
        (Status::Resolved, use_),
        vec![target],
    );
    data.source_definition_id = Nullable::Value(FactId::new(reading.source.id.as_str()));
    data.reference_context = Some(context);
    data.reason = Some("plain name with a stable direct binding".to_owned());
    record(
        reader,
        reading,
        name,
        (expression, ReferenceFact::References(data)),
    )
}

/// The names of the annotations of a def: read in the scope that holds the def, which is the
/// class body for a method and the module for a function.
fn annotations(reader: &mut Reader<'_, '_>, reading: &Reading<'_>) -> Vec<Record<ReferenceFact>> {
    let node = reading.source.node;
    let params = &node.parameters;
    let all = params
        .posonlyargs
        .iter()
        .chain(&params.args)
        .chain(&params.kwonlyargs)
        .map(|item| &item.parameter)
        .chain(params.vararg.as_deref())
        .chain(params.kwarg.as_deref());
    let written = all
        .filter_map(|parameter| parameter.annotation.as_deref())
        .chain(node.returns.as_deref());
    let mut held = reading.source.class_names.clone().unwrap_or_default();
    held.extend(scope::type_names(node));
    let mut found = Vec::new();
    for expression in written {
        let Expr::Name(name) = expression else {
            continue;
        };
        let Some((target, _)) = reading.lookup(name.id.as_str(), &held) else {
            continue;
        };
        let context = (Use::Type, ReferenceContext::Annotation);
        found.push(site(reader, reading, name, context, target));
    }
    found
}
