// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compiler options that module resolution reads, as `config._options` reads them.
//!
//! Every value that this reader does not understand becomes a problem. A problem makes the
//! settings partial, and a partial setting resolves nothing: the collector invents no evidence.

use serde_json::{Map, Value};

use crate::layer::Layer;
use crate::options_target::{detection_kind, target_kind};
pub use crate::options_target::{Detection, Target};

const CONFIG_DIRECTORY: &str = "${configDir}";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModuleKind {
    None,
    CommonJs,
    Amd,
    System,
    Umd,
    Es6,
    Es2015,
    Es2020,
    Es2022,
    EsNext,
    Node16,
    Node18,
    Node20,
    NodeNext,
    Preserve,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Resolution {
    Node10,
    Classic,
    Node16,
    NodeNext,
    Bundler,
}

/// What the resolver reads; explicit values only, as the compiler keeps them.
#[derive(Clone, Debug, Default)]
pub struct Options {
    pub module: Option<ModuleKind>,
    pub module_resolution: Option<Resolution>,
    pub target: Option<Target>,
    /// The snapshot-relative directory of `baseUrl`.
    pub base_url: Option<String>,
    /// The `paths` patterns with their targets, in file order.
    pub paths: Vec<(String, Vec<String>)>,
    /// The directory that the targets are relative to: `baseUrl`, else the config that sets them.
    pub paths_base: String,
    pub unmodeled: Vec<String>,
    pub json_modules: Option<bool>,
    /// The `lib` values, each once; `None` when the option is not set.
    pub libs: Option<Vec<String>>,
    pub no_lib: bool,
    /// A `lib` value that the pinned compiler does not know, or `libReplacement`.
    pub lib_unmodeled: bool,
    pub module_detection: Option<Detection>,
}

const NODE16_MODULES: [ModuleKind; 3] =
    [ModuleKind::Node16, ModuleKind::Node18, ModuleKind::Node20];

impl Options {
    /// The emit mode after the compiler's target-dependent default.
    pub fn emit_module(&self) -> ModuleKind {
        match (self.module, self.target) {
            (Some(module), _) => module,
            (None, None | Some(Target::Es3 | Target::Es5)) => ModuleKind::CommonJs,
            (None, Some(_)) => ModuleKind::Es2015,
        }
    }

    /// The compiler's target when none is set: by the module, and ES5 without one.
    pub fn module_default_target(&self) -> Target {
        match self.module {
            Some(ModuleKind::Node16 | ModuleKind::Node18) => Target::Es2022,
            Some(ModuleKind::Node20) => Target::Es2023,
            Some(ModuleKind::NodeNext) => Target::EsNext,
            _ => Target::Es5,
        }
    }

    /// Whether a source file without `import` or `export` still is a global script. Under `force`
    /// and under the Node module modes the compiler treats every source file as a module.
    pub fn scripts_are_global(&self) -> bool {
        self.module_detection != Some(Detection::Force)
            && !NODE16_MODULES.contains(&self.emit_module())
            && self.emit_module() != ModuleKind::NodeNext
    }

    /// The effective resolution mode.
    pub fn resolution(&self) -> Resolution {
        if let Some(resolution) = self.module_resolution {
            return resolution;
        }
        let emit = self.emit_module();
        if NODE16_MODULES.contains(&emit) {
            return Resolution::Node16;
        }
        match emit {
            ModuleKind::CommonJs => Resolution::Node10,
            ModuleKind::NodeNext => Resolution::NodeNext,
            ModuleKind::Preserve => Resolution::Bundler,
            _ => Resolution::Classic,
        }
    }

    /// Whether JSON resolves: the explicit setting, else Node20, NodeNext or Bundler.
    pub fn resolve_json(&self) -> bool {
        self.json_modules.unwrap_or_else(|| {
            matches!(
                self.emit_module(),
                ModuleKind::Node20 | ModuleKind::NodeNext
            ) || self.resolution() == Resolution::Bundler
        })
    }
}

fn module_kind(name: &str) -> Option<ModuleKind> {
    Some(match name {
        "none" => ModuleKind::None,
        "commonjs" => ModuleKind::CommonJs,
        "amd" => ModuleKind::Amd,
        "system" => ModuleKind::System,
        "umd" => ModuleKind::Umd,
        "es6" => ModuleKind::Es6,
        "es2015" => ModuleKind::Es2015,
        "es2020" => ModuleKind::Es2020,
        "es2022" => ModuleKind::Es2022,
        "esnext" => ModuleKind::EsNext,
        "node16" => ModuleKind::Node16,
        "node18" => ModuleKind::Node18,
        "node20" => ModuleKind::Node20,
        "nodenext" => ModuleKind::NodeNext,
        "preserve" => ModuleKind::Preserve,
        _ => return None,
    })
}

fn resolution_kind(name: &str) -> Option<Resolution> {
    Some(match name {
        "node10" | "node" => Resolution::Node10,
        "classic" => Resolution::Classic,
        "node16" => Resolution::Node16,
        "nodenext" => Resolution::NodeNext,
        "bundler" => Resolution::Bundler,
        _ => return None,
    })
}

// Settings that affect module resolution without a native interpretation.
const UNMODELED: [&str; 8] = [
    "rootDirs",
    "moduleSuffixes",
    "customConditions",
    "resolvePackageJsonExports",
    "resolvePackageJsonImports",
    "preserveSymlinks",
    "allowArbitraryExtensions",
    "noDtsResolution",
];
const BOOLEAN_OPTIONS: [&str; 10] = [
    "allowJs",
    "checkJs",
    "resolveJsonModule",
    "noLib",
    "libReplacement",
    "resolvePackageJsonExports",
    "resolvePackageJsonImports",
    "preserveSymlinks",
    "allowArbitraryExtensions",
    "noDtsResolution",
];
const STRING_OPTIONS: [&str; 3] = ["baseUrl", "declarationDir", "outDir"];
const STRING_LIST_OPTIONS: [&str; 6] = [
    "customConditions",
    "moduleSuffixes",
    "rootDirs",
    "lib",
    "types",
    "typeRoots",
];
// The compiler's option names (TypeScript 5.9.3); an unknown one is a configuration error.
const KNOWN_OPTIONS: &str = "all allowArbitraryExtensions allowImportingTsExtensions allowJs \
allowSyntheticDefaultImports allowUmdGlobalAccess allowUnreachableCode allowUnusedLabels \
alwaysStrict assumeChangesOnlyAffectDirectDependencies baseUrl charset checkJs composite \
customConditions declaration declarationDir declarationMap diagnostics \
disableReferencedProjectLoad disableSizeLimit disableSolutionSearching \
disableSourceOfProjectReferenceRedirect downlevelIteration emitBOM emitDeclarationOnly \
emitDecoratorMetadata erasableSyntaxOnly esModuleInterop exactOptionalPropertyTypes \
experimentalDecorators explainFiles extendedDiagnostics forceConsistentCasingInFileNames \
generateCpuProfile generateTrace ignoreDeprecations importHelpers importsNotUsedAsValues \
incremental init inlineSourceMap inlineSources isolatedDeclarations isolatedModules jsx \
jsxFactory jsxFragmentFactory jsxImportSource keyofStringsOnly lib libReplacement \
listEmittedFiles listFiles mapRoot module moduleDetection moduleResolution moduleSuffixes \
newLine noCheck noEmit noEmitHelpers noEmitOnError noErrorTruncation \
noFallthroughCasesInSwitch noImplicitAny noImplicitOverride noImplicitReturns noImplicitThis \
noImplicitUseStrict noLib noPropertyAccessFromIndexSignature noResolve noStrictGenericChecks \
noUncheckedIndexedAccess noUncheckedSideEffectImports noUnusedLocals noUnusedParameters out \
outDir outFile paths plugins preserveConstEnums preserveSymlinks preserveValueImports \
preserveWatchOutput pretty project reactNamespace removeComments resolveJsonModule \
resolvePackageJsonExports resolvePackageJsonImports rewriteRelativeImportExtensions rootDir \
rootDirs skipDefaultLibCheck skipLibCheck sourceMap sourceRoot strict strictBindCallApply \
strictBuiltinIteratorReturn strictFunctionTypes strictNullChecks strictPropertyInitialization \
stripInternal suppressExcessPropertyErrors suppressImplicitAnyIndexErrors target traceResolution \
tsBuildInfoFile typeRoots types useDefineForClassFields useUnknownInCatchVariables \
verbatimModuleSyntax version";

/// `config._normalized`: the lower-case text of a string option, else the empty text.
fn normalized(options: &Map<String, Value>, key: &str) -> String {
    options
        .get(key)
        .and_then(Value::as_str)
        .map_or_else(String::new, str::to_lowercase)
}

fn is_string_list(value: &Value) -> bool {
    value
        .as_array()
        .is_some_and(|items| items.iter().all(Value::is_string))
}

/// Whether a lower-case option text is a value of its enumeration.
type Accepts = fn(&str) -> bool;

/// `config._invalid`: name unknown options and refuse malformed values.
pub fn invalid(options: &Map<String, Value>) -> Vec<String> {
    let mut found: Vec<String> = options
        .keys()
        .filter(|name| !KNOWN_OPTIONS.split(' ').any(|known| known == name.as_str()))
        .map(|name| format!("Unknown compiler option '{name}'."))
        .collect();
    let enums: [(&str, Accepts); 4] = [
        ("module", |name| module_kind(name).is_some()),
        ("moduleResolution", |name| resolution_kind(name).is_some()),
        ("moduleDetection", |name| {
            matches!(name, "auto" | "legacy" | "force")
        }),
        ("target", |name| target_kind(name).is_some()),
    ];
    for (name, accepted) in enums {
        let present = options.get(name).is_some_and(|value| !value.is_null());
        if present && !accepted(&normalized(options, name)) {
            found.push(format!(
                "Compiler option 6046: argument for '{name}' is not valid."
            ));
        }
    }
    for (name, value) in options {
        let name = name.as_str();
        if value.is_null() {
            continue;
        }
        if BOOLEAN_OPTIONS.contains(&name) && !value.is_boolean() {
            found.push(format!("Compiler option 5024: '{name}' must be a boolean."));
        } else if STRING_OPTIONS.contains(&name) && !value.is_string() {
            found.push(format!("Compiler option 5024: '{name}' must be a string."));
        } else if STRING_LIST_OPTIONS.contains(&name) && !is_string_list(value) {
            found.push(format!(
                "Compiler option 5024: '{name}' must be a list of strings."
            ));
        }
    }
    found
}

/// `config._paths`: the patterns in file order; a malformed entry is a problem.
pub fn paths(raw: &Map<String, Value>, problems: &mut Vec<String>) -> Vec<(String, Vec<String>)> {
    let Some(value) = raw.get("paths").filter(|value| !value.is_null()) else {
        return Vec::new();
    };
    let Some(entries) = value.as_object() else {
        problems.push("Compiler option 5024: 'paths' must be an object.".to_owned());
        return Vec::new();
    };
    let mut patterns = Vec::new();
    for (pattern, targets) in entries {
        if pattern.matches('*').count() > 1 || !is_string_list(targets) {
            problems.push(format!(
                "Compiler option 5061: paths pattern '{pattern}' is not valid."
            ));
        } else {
            let targets = targets.as_array().into_iter().flatten();
            patterns.push((
                pattern.clone(),
                targets
                    .filter_map(Value::as_str)
                    .map(str::to_owned)
                    .collect(),
            ));
        }
    }
    patterns
}

/// `raw.get(name) not in (None, False)`: a zero counts as false, an empty list as set.
fn replaced(raw: &Map<String, Value>, name: &str) -> bool {
    match raw.get(name) {
        None | Some(Value::Null | Value::Bool(false)) => false,
        Some(Value::Number(number)) => number.as_f64() != Some(0.0),
        Some(_) => true,
    }
}

// `raw.get(name) not in (None, False, [])`: Python also counts a zero as false.
fn declared(raw: &Map<String, Value>, name: &str) -> bool {
    match raw.get(name) {
        None | Some(Value::Null | Value::Bool(false)) => false,
        Some(Value::Array(items)) => !items.is_empty(),
        Some(Value::Number(number)) => number.as_f64() != Some(0.0),
        Some(_) => true,
    }
}

/// `config._options`: the settings of one layer, with the problems of the pairs that the
/// compiler refuses.
pub fn build(layer: &Layer, problems: &mut Vec<String>) -> Options {
    let raw = &layer.compiler;
    let paths = paths(raw, problems);
    let mut unmodeled: Vec<String> = UNMODELED
        .iter()
        .filter(|name| declared(raw, name))
        .map(|name| (*name).to_owned())
        .collect();
    if paths
        .iter()
        .any(|(_, targets)| targets.iter().any(|t| t.contains(CONFIG_DIRECTORY)))
    {
        unmodeled.push("paths with ${configDir}".to_owned());
    }
    let options = Options {
        module: module_kind(&normalized(raw, "module")),
        module_resolution: resolution_kind(&normalized(raw, "moduleResolution")),
        target: target_kind(&normalized(raw, "target")),
        base_url: layer.base_url.clone(),
        paths,
        paths_base: layer
            .base_url
            .clone()
            .unwrap_or_else(|| layer.paths_directory.clone()),
        unmodeled,
        json_modules: raw.get("resolveJsonModule").and_then(Value::as_bool),
        libs: None,
        no_lib: raw.get("noLib") == Some(&Value::Bool(true)),
        // `types` and `typeRoots` only add globals to the catalog (AD-274); a replacement lib can
        // change what a lib name means.
        lib_unmodeled: replaced(raw, "libReplacement"),
        module_detection: detection_kind(&normalized(raw, "moduleDetection")),
    };
    let lib = raw.get("lib").is_some_and(|value| !value.is_null());
    if raw.get("noLib") == Some(&Value::Bool(true)) && lib {
        problems.push("Compiler option 5053: 'lib' cannot be specified with 'noLib'.".to_owned());
    }
    pair_problem(&options, problems);
    options
}

// TS5110 and TS5095: the compiler refuses these pairs, so it observes no resolution.
fn pair_problem(options: &Options, problems: &mut Vec<String>) {
    let emit = options.emit_module();
    let kind = options.resolution();
    let node16 = NODE16_MODULES.contains(&emit);
    let esm = matches!(
        emit,
        ModuleKind::Es6
            | ModuleKind::Es2015
            | ModuleKind::Es2020
            | ModuleKind::Es2022
            | ModuleKind::EsNext
            | ModuleKind::Preserve
    );
    if kind == Resolution::Node16 && !node16 {
        problems.push(
            "Compiler option 5110: 'module' must be node16 with this moduleResolution.".into(),
        );
    } else if kind == Resolution::NodeNext && emit != ModuleKind::NodeNext {
        problems.push(
            "Compiler option 5110: 'module' must be nodenext with this moduleResolution.".into(),
        );
    } else if kind == Resolution::Bundler && !esm {
        problems.push(
            "Compiler option 5095: 'bundler' needs 'module' preserve or es2015 or later.".into(),
        );
    } else if (node16 || emit == ModuleKind::NodeNext)
        && kind
            != if emit == ModuleKind::NodeNext {
                Resolution::NodeNext
            } else {
                Resolution::Node16
            }
    {
        let name = match emit {
            ModuleKind::Node16 => "node16",
            ModuleKind::Node18 => "node18",
            ModuleKind::Node20 => "node20",
            _ => "nodenext",
        };
        problems.push(format!(
            "Compiler option 5110: 'moduleResolution' must follow 'module' {name}."
        ));
    }
}

#[cfg(test)]
#[path = "options_tests.rs"]
mod tests;
