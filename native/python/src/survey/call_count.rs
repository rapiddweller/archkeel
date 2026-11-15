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
use ruff_python_ast::Expr;

use super::binders::Binders;
use crate::module::Module;

/// Bindings that the survey proves once, and symbols with records.
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
    walk.visit_body(&module.tree.body);
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
            } else if matches!(&*call.func, Expr::Name(name) if builtin(name.id.as_str()) && self.binders.builtin_visible(name.id.as_str())) {
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
mod tests {
    use super::count;
    use crate::survey::binders::Binders;

    #[test]
    fn counts_nested_decorated_and_dynamic_calls() {
        let module = crate::test_module(
            "@decorate(factory())\ndef f(self, x):\n    return self.m(x()) + obj.m() + f()()\n",
            11,
        );
        let binders = Binders::of(&module.tree);
        let row = count(&module, &binders, &[], &super::Context::default());
        assert_eq!(row.calls_total, 7);
        assert_eq!(row.calls_unresolved, 7);
        assert_eq!(row.unresolved_self, 1);
        assert_eq!(row.unresolved_attribute, 1);
        assert_eq!(row.unresolved_dynamic, 1);
    }

    #[test]
    fn a_rebound_builtin_is_not_proven() {
        let module = crate::test_module("len = custom\nlen([])\n", 11);
        let binders = Binders::of(&module.tree);
        let row = count(&module, &binders, &[], &super::Context::default());
        assert_eq!((row.calls_builtin, row.calls_unresolved), (0, 1));
    }

    #[test]
    fn survey_counts_are_stable_when_input_order_changes() {
        let files = [
            ("src/app/__init__.py", ""),
            ("src/app/one.py", "def make():\n    return 1\n"),
            ("src/app/two.py", "from app.one import make\nimport json\ndef f():\n    make()\n    json.dumps({})\n    self.m()\n"),
        ];
        let first = crate::survey::targets::tests::surveyed(&files);
        let mut reverse = files;
        reverse.reverse();
        let second = crate::survey::targets::tests::surveyed(&reverse);
        assert_eq!(first.coverage.measures, second.coverage.measures);
        let rows = first.coverage.measures.unwrap();
        let row = rows
            .iter()
            .find(|row| row.module.as_str() == "app.two")
            .unwrap();
        assert_eq!(
            (
                row.calls_total,
                row.calls_resolved,
                row.calls_external,
                row.calls_unresolved
            ),
            (3, 1, 1, 1)
        );
    }

    #[test]
    fn adding_an_unproved_receiver_increases_only_the_unresolved_count() {
        let a = crate::test_module("def f(x):\n    return x\n", 11);
        let b = crate::test_module("def f(x):\n    return x.m()\n", 11);
        let before = count(&a, &Binders::of(&a.tree), &[], &super::Context::default());
        let after = count(&b, &Binders::of(&b.tree), &[], &super::Context::default());
        assert_eq!(after.calls_unresolved, before.calls_unresolved + 1);
        assert_eq!(after.unresolved_attribute, before.unresolved_attribute + 1);
    }

    #[test]
    fn unreadable_file_has_no_row() {
        let found = crate::survey::targets::tests::surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/broken.py", "def broken(:\n"),
        ]);
        assert_eq!(found.coverage.selected_files.len(), 2);
        assert_eq!(found.coverage.measures.unwrap().len(), 1);
        assert_eq!(found.coverage.files_parsed, 1);
    }

    #[test]
    fn each_call_class_has_one_count() {
        let found = crate::survey::targets::tests::surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/one.py", "def make():\n    pass\n"),
            (
                "src/app/two.py",
                "import app.one as mod\nfrom app.one import make\nimport json\ndef f(value):\n    make()\n    mod.make()\n    json.dumps({})\n    len(value)\n    value.method()\n    self.method()\n    value[0]()\n    factory()()\n",
            ),
        ]);
        let rows = found.coverage.measures.unwrap();
        let row = rows
            .iter()
            .find(|row| row.module.as_str() == "app.two")
            .unwrap();
        assert_eq!(
            (
                row.calls_total,
                row.calls_resolved,
                row.calls_external,
                row.calls_builtin
            ),
            (9, 2, 1, 1)
        );
        assert_eq!(
            (
                row.calls_unresolved,
                row.unresolved_self,
                row.unresolved_attribute,
                row.unresolved_name,
                row.unresolved_dynamic
            ),
            (5, 1, 1, 1, 2)
        );
    }

    #[test]
    fn a_partial_construction_keeps_its_own_class() {
        let found = crate::survey::targets::tests::surveyed(&[
            ("src/app/__init__.py", ""),
            (
                "src/app/one.py",
                "class C:\n    def __new__(cls):\n        pass\ndef f():\n    return C()\n",
            ),
        ]);
        let rows = found.coverage.measures.unwrap();
        let row = rows
            .iter()
            .find(|row| row.module.as_str() == "app.one")
            .unwrap();
        assert_eq!((row.calls_total, row.calls_partial), (1, 1));
    }

    #[test]
    fn a_proven_dead_site_does_not_gain_an_import_proof() {
        let found = crate::survey::targets::tests::surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/one.py", "def make():\n    pass\n"),
            (
                "src/app/two.py",
                "from app.one import make\nimport app.one as mod\ndef f():\n    if False:\n        make()\n        mod.make()\n        len([])\n",
            ),
        ]);
        let rows = found.coverage.measures.unwrap();
        let row = rows
            .iter()
            .find(|row| row.module.as_str() == "app.two")
            .unwrap();
        assert_eq!((row.calls_resolved, row.calls_unresolved), (0, 3));
    }
}
