use pyo3::types::PyModuleMethods;
use ruff_python_ast::{PythonVersion, Stmt, visitor};
use ruff_python_parser::{Mode, ParseOptions, parse_unchecked};
use serde::Serialize;

#[derive(Serialize)]
pub struct Batch {
    status: &'static str,
    complete: bool,
    reason: Option<&'static str>,
    target_python_version: String,
    semantic_status: &'static str,
    unknown: Vec<&'static str>,
    imports: Vec<ImportOccurrence>,
}

#[derive(Serialize)]
struct ImportOccurrence {
    form: &'static str,
    module: Option<String>,
    name: String,
    alias: Option<String>,
    level: u32,
    line: usize,
    column: usize,
    end_line: usize,
    end_column: usize,
    semantic_status: &'static str,
}

struct ImportCollector {
    line_starts: Vec<usize>,
    imports: Vec<ImportOccurrence>,
}

impl ImportCollector {
    fn position(&self, offset: usize) -> (usize, usize) {
        let line_index = self.line_starts.partition_point(|start| *start <= offset) - 1;
        (line_index + 1, offset - self.line_starts[line_index])
    }

    fn add_alias(
        &mut self,
        form: &'static str,
        module: Option<String>,
        level: u32,
        alias: &ruff_python_ast::Alias,
    ) {
        let start = alias.range.start().to_u32() as usize;
        let end = alias.range.end().to_u32() as usize;
        let (line, column) = self.position(start);
        let (end_line, end_column) = self.position(end);
        self.imports.push(ImportOccurrence {
            form,
            module,
            name: alias.name.to_string(),
            alias: alias.asname.as_ref().map(ToString::to_string),
            level,
            line,
            column,
            end_line,
            end_column,
            semantic_status: "UNKNOWN",
        });
    }
}

impl<'a> visitor::Visitor<'a> for ImportCollector {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(import) => {
                for alias in &import.names {
                    self.add_alias("import", None, 0, alias);
                }
            }
            Stmt::ImportFrom(import) => {
                for alias in &import.names {
                    self.add_alias(
                        "from",
                        import.module.as_ref().map(ToString::to_string),
                        import.level,
                        alias,
                    );
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }
}

fn target_version(value: &str) -> Option<PythonVersion> {
    PythonVersion::iter().find(|version| version.to_string() == value)
}

fn unknown_batch(target: String, reason: &'static str) -> Batch {
    Batch {
        status: "UNKNOWN",
        complete: false,
        reason: Some(reason),
        target_python_version: target,
        semantic_status: "UNKNOWN",
        unknown: vec![reason],
        imports: Vec::new(),
    }
}

pub fn collect_import_batch(source: &str, target: &str) -> Batch {
    let Some(target_version) = target_version(target) else {
        return unknown_batch(target.to_owned(), "unsupported_target_version");
    };
    let parsed = parse_unchecked(
        source,
        ParseOptions::from(Mode::Module).with_target_version(target_version),
    );
    if !parsed.errors().is_empty() {
        return unknown_batch(target.to_owned(), "syntax_error");
    }
    if !parsed.unsupported_syntax_errors().is_empty() {
        return unknown_batch(target.to_owned(), "unsupported_syntax");
    }
    let Some(parsed) = parsed.try_into_module() else {
        return unknown_batch(target.to_owned(), "not_a_module");
    };

    let mut line_starts = vec![0];
    line_starts.extend(
        source
            .bytes()
            .enumerate()
            .filter_map(|(index, byte)| (byte == b'\n').then_some(index + 1)),
    );
    let mut collector = ImportCollector {
        line_starts,
        imports: Vec::new(),
    };
    for stmt in &parsed.syntax().body {
        visitor::Visitor::visit_stmt(&mut collector, stmt);
    }
    collector.imports.sort_by_key(|item| {
        (
            item.line,
            item.column,
            item.end_line,
            item.end_column,
            item.name.clone(),
        )
    });
    Batch {
        status: "COMPLETE",
        complete: true,
        reason: None,
        target_python_version: target.to_owned(),
        semantic_status: "UNKNOWN",
        unknown: vec!["target_resolution", "reexport_semantics"],
        imports: collector.imports,
    }
}

pub fn collect_import_batch_json(source: &str, target: &str) -> Result<String, serde_json::Error> {
    serde_json::to_string(&collect_import_batch(source, target))
}

#[pyo3::pyfunction(name = "collect_import_batch_json")]
fn py_collect_import_batch_json(source: &str, target: &str) -> String {
    collect_import_batch_json(source, target)
        .expect("serializing an import batch to JSON cannot fail")
}

#[pyo3::pymodule]
fn _core(module: &pyo3::Bound<'_, pyo3::types::PyModule>) -> pyo3::PyResult<()> {
    module.add_function(pyo3::wrap_pyfunction!(
        py_collect_import_batch_json,
        module
    )?)?;
    Ok(())
}
