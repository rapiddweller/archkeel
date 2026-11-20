// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Count every call, including calls outside an admitted symbol body.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::Target;
use archkeel_facts::identity::evidence_id;
use archkeel_facts::measures::FileMeasures;
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::Status;
use archkeel_facts::{CallFact, FactData, ImportFact, Record, SymbolFact};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Decorator, Expr, Stmt};

use super::binders::Binders;
use crate::module::Module;

#[derive(Default)]
pub(super) struct Context {
    imports: HashMap<String, HashMap<String, (String, bool, bool)>>,
    symbols: HashSet<String>,
    dead_sites: HashSet<String>,
}

impl Context {
    pub(super) fn new(
        imports: &[Record<ImportFact>],
        targets: &[Target],
        sole: &HashSet<String>,
        ambiguous: &HashSet<String>,
        symbols: &[Record<SymbolFact>],
        dead_sites: &HashSet<String>,
    ) -> Self {
        let symbols = symbols
            .iter()
            .filter(|item| matches!(item.data, SymbolFact::Function(_) | SymbolFact::Class(_)))
            .filter_map(|item| item.data.fields().qualified_name.map(str::to_owned))
            .collect();
        let mut found = Self {
            imports: HashMap::new(),
            symbols,
            dead_sites: dead_sites.clone(),
        };
        let targets: HashMap<_, _> = targets
            .iter()
            .map(|target| (target.import_id(), target))
            .collect();
        for item in imports {
            let data = item.data.data();
            if !sole.contains(item.id.as_str())
                || ambiguous.contains(item.id.as_str())
                || data.under_type_checking
            {
                continue;
            }
            let Some(binding) = &data.binding else {
                continue;
            };
            let Some(target) = targets.get(&item.id).copied() else {
                continue;
            };
            let external = matches!(target, Target::External { .. } | Target::Builtin { .. });
            if !external && !matches!(target, Target::Local { .. }) {
                continue;
            }
            let module = data.target_module.as_str();
            if data.symbol.is_none()
                && module.contains('.')
                && binding == module.split('.').next().unwrap_or("")
            {
                continue;
            }
            let name = data
                .symbol
                .as_ref()
                .map_or_else(|| module.to_owned(), |symbol| format!("{module}.{symbol}"));
            found
                .imports
                .entry(data.source_module.as_str().to_owned())
                .or_default()
                .insert(binding.clone(), (name, external, data.symbol.is_none()));
        }
        found
    }
}

pub(super) fn count(
    module: &Module,
    binders: &Binders,
    calls: &[Record<CallFact>],
    context: &Context,
    function_call_counts: &mut Vec<(String, u64)>,
) -> FileMeasures {
    let sites: HashMap<&str, &Record<CallFact>> = calls
        .iter()
        .filter_map(|call| call.evidence_ids.first().map(|id| (id.as_str(), call)))
        .collect();
    let mut walk = Calls {
        module,
        binders,
        context,
        unique: binders.unique(),
        sites,
        row: FileMeasures {
            file: module.rel.clone(),
            module: archkeel_facts::ids::ModuleName::new(&module.name),
            ..FileMeasures::default()
        },
    };
    for statement in &module.tree.body {
        let before = walk.row.calls_total;
        walk.visit_stmt(statement);
        if let Stmt::FunctionDef(function) = statement {
            function_call_counts.push((
                format!("{}.{}", module.name, function.name),
                walk.row.calls_total.saturating_sub(before),
            ));
        }
    }
    walk.row
}

struct Calls<'a> {
    module: &'a Module,
    binders: &'a Binders,
    context: &'a Context,
    unique: HashSet<String>,
    sites: HashMap<&'a str, &'a Record<CallFact>>,
    row: FileMeasures,
}

impl<'a> Visitor<'a> for Calls<'_> {
    fn visit_decorator(&mut self, decorator: &'a Decorator) {
        // Evaluating the expression and applying its result are separate calls.
        self.row.calls_total += 1;
        self.unresolved(&decorator.expression);
        visitor::walk_decorator(self, decorator);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Call(call) = expr {
            self.row.calls_total += 1;
            let location = self.module.location(call);
            let id = evidence_id(
                &self.module.rel,
                location.line,
                location.end_line,
                location.column,
            );
            let proof = self
                .sites
                .get(id.as_str())
                .and_then(|site| match &site.data {
                    CallFact::Calls(data)
                        if matches!(&*call.func, Expr::Name(_))
                            && data.status == Status::Resolved
                            && !data.targets.is_empty() =>
                    {
                        Some(data)
                    }
                    _ => None,
                });
            let withheld = self.context.dead_sites.contains(id.as_str());
            let imported = match &*call.func {
                Expr::Name(name) => self.import(name.id.as_str(), None),
                Expr::Attribute(attr) => match &*attr.value {
                    Expr::Name(name) => self.import(name.id.as_str(), Some(attr.attr.as_str())),
                    _ => None,
                },
                _ => None,
            };
            if withheld {
                self.unresolved(&call.func);
            } else if proof.is_some_and(|data| matches!(&data.construction, Nullable::Value(item) if item.status == Status::PartiallyResolved)) {
                self.row.calls_partial += 1;
            } else if proof.is_some() || imported == Some(false) {
                self.row.calls_resolved += 1;
            } else if imported == Some(true) {
                self.row.calls_external += 1;
            } else if literal_method(&call.func)
                || matches!(&*call.func, Expr::Name(name) if builtin(name.id.as_str()) && self.binders.builtin_visible(name.id.as_str()))
            {
                self.row.calls_builtin += 1;
            } else {
                self.unresolved(&call.func);
            }
        }
        visitor::walk_expr(self, expr);
    }
}

impl Calls<'_> {
    fn unresolved(&mut self, func: &Expr) {
        self.row.calls_unresolved += 1;
        match func {
            Expr::Name(_) => self.row.unresolved_name += 1,
            Expr::Attribute(attr) if matches!(&*attr.value, Expr::Name(name) if name.id.as_str() == "self") => {
                self.row.unresolved_self += 1
            }
            Expr::Attribute(_) => self.row.unresolved_attribute += 1,
            _ => self.row.unresolved_dynamic += 1,
        }
    }

    fn import(&self, binding: &str, attribute: Option<&str>) -> Option<bool> {
        if !self.unique.contains(binding) {
            return None;
        }
        let (target, external, module) =
            self.context.imports.get(&self.module.name)?.get(binding)?;
        let name = match attribute {
            Some(attribute) if *module => format!("{target}.{attribute}"),
            Some(_) => return None,
            None if !module => target.clone(),
            None => return None,
        };
        if *external || self.context.symbols.contains(&name) {
            Some(*external)
        } else {
            None
        }
    }
}

/// Public methods shared by the supported Python versions on exact builtin literals.
/// Names, constructors and formatted strings can produce user-defined receiver types.
fn literal_method(callee: &Expr) -> bool {
    let Expr::Attribute(attr) = callee else {
        return false;
    };
    let methods = match &*attr.value {
        Expr::StringLiteral(_) => {
            "capitalize casefold center count encode endswith expandtabs find \
            format format_map index isalnum isalpha isascii isdecimal isdigit isidentifier islower \
            isnumeric isprintable isspace istitle isupper join ljust lower lstrip maketrans \
            partition removeprefix removesuffix replace rfind rindex rjust rpartition rsplit \
            rstrip split splitlines startswith strip swapcase title translate upper zfill"
        }
        Expr::List(_) => "append clear copy count extend index insert pop remove reverse sort",
        Expr::Tuple(_) => "count index",
        Expr::Dict(_) => "clear copy fromkeys get items keys pop popitem setdefault update values",
        Expr::Set(_) => {
            "add clear copy difference difference_update discard intersection \
            intersection_update isdisjoint issubset issuperset pop remove symmetric_difference \
            symmetric_difference_update union update"
        }
        _ => return false,
    };
    methods
        .split_ascii_whitespace()
        .any(|name| name == attr.attr.as_str())
}

#[expect(
    clippy::too_many_lines,
    reason = "the fixed builtin set is independent of the interpreter"
)]
fn builtin(name: &str) -> bool {
    matches!(
        name,
        "ArithmeticError"
            | "AssertionError"
            | "AttributeError"
            | "BaseException"
            | "BlockingIOError"
            | "BrokenPipeError"
            | "BufferError"
            | "BytesWarning"
            | "ChildProcessError"
            | "ConnectionAbortedError"
            | "ConnectionError"
            | "ConnectionRefusedError"
            | "ConnectionResetError"
            | "DeprecationWarning"
            | "EOFError"
            | "EnvironmentError"
            | "Exception"
            | "FileExistsError"
            | "FileNotFoundError"
            | "FloatingPointError"
            | "FutureWarning"
            | "GeneratorExit"
            | "IOError"
            | "ImportError"
            | "ImportWarning"
            | "IndentationError"
            | "IndexError"
            | "InterruptedError"
            | "IsADirectoryError"
            | "KeyError"
            | "KeyboardInterrupt"
            | "LookupError"
            | "MemoryError"
            | "ModuleNotFoundError"
            | "NameError"
            | "NotADirectoryError"
            | "NotImplementedError"
            | "OSError"
            | "OverflowError"
            | "PendingDeprecationWarning"
            | "PermissionError"
            | "ProcessLookupError"
            | "RecursionError"
            | "ReferenceError"
            | "ResourceWarning"
            | "RuntimeError"
            | "RuntimeWarning"
            | "StopAsyncIteration"
            | "StopIteration"
            | "SyntaxError"
            | "SyntaxWarning"
            | "SystemError"
            | "SystemExit"
            | "TabError"
            | "TimeoutError"
            | "TypeError"
            | "UnboundLocalError"
            | "UnicodeDecodeError"
            | "UnicodeEncodeError"
            | "UnicodeError"
            | "UnicodeTranslateError"
            | "UnicodeWarning"
            | "UserWarning"
            | "ValueError"
            | "Warning"
            | "ZeroDivisionError"
            | "abs"
            | "all"
            | "any"
            | "ascii"
            | "bin"
            | "bool"
            | "bytearray"
            | "bytes"
            | "callable"
            | "chr"
            | "classmethod"
            | "compile"
            | "complex"
            | "delattr"
            | "dict"
            | "dir"
            | "divmod"
            | "enumerate"
            | "eval"
            | "exec"
            | "filter"
            | "float"
            | "format"
            | "frozenset"
            | "getattr"
            | "globals"
            | "hasattr"
            | "hash"
            | "hex"
            | "id"
            | "input"
            | "int"
            | "isinstance"
            | "issubclass"
            | "iter"
            | "len"
            | "list"
            | "locals"
            | "map"
            | "max"
            | "memoryview"
            | "min"
            | "next"
            | "object"
            | "oct"
            | "open"
            | "ord"
            | "pow"
            | "print"
            | "property"
            | "range"
            | "repr"
            | "reversed"
            | "round"
            | "set"
            | "setattr"
            | "slice"
            | "sorted"
            | "staticmethod"
            | "str"
            | "sum"
            | "super"
            | "tuple"
            | "type"
            | "vars"
            | "zip"
    )
}

#[cfg(test)]
#[path = "call_count_tests.rs"]
mod tests;
