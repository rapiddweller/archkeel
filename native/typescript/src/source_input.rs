// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! TypeScript file names and module specifiers, as `source_input.py` classifies them.
//!
//! One table owns the file suffixes: discovery, resolution and parsing all read it.

/// The classic script host names, also reserved for UMD factory and root parameters.
pub(crate) const HOST_NAMES: [&str; 6] =
    ["exports", "module", "define", "window", "global", "self"];

/// `syntax.WALK_ROOTS`: roots that the file walk can publish through.
pub(crate) const WALK_ROOTS: [&str; 4] = ["window", "globalThis", "self", "frames"];

/// `ScriptRoot.TOP` and `ScriptRoot.PARENT`: the window outside a frame. A use and a write read
/// them as roots; a publication does not.
pub(crate) const FRAME_ROOTS: [&str; 2] = ["top", "parent"];

/// The other global names whose value is a window: the window that opened this one, and the
/// global object of Node.
pub(crate) const OTHER_WINDOWS: [&str; 2] = ["opener", "global"];

/// A global name whose value can be a window: a root, a frame root or another window. This is the
/// one list of such names; the write check of a script reads it.
pub(crate) fn is_window_name(name: &str) -> bool {
    is_script_root(name.as_bytes()) || FRAME_ROOTS.contains(&name) || OTHER_WINDOWS.contains(&name)
}

pub(crate) fn is_script_root(text: &[u8]) -> bool {
    WALK_ROOTS.iter().any(|root| root.as_bytes() == text)
}

/// The source category that one resolution pass enables.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SourceKind {
    TypeScript,
    Declaration,
    JavaScript,
    Json,
}

/// The loading format that a suffix or a package scope gives.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ModuleFormat {
    Esm,
    Cjs,
}

/// `FileSuffix`: a recognized suffix, or no suffix at all.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Suffix {
    Absent,
    Dts,
    Dmts,
    Dcts,
    Mjs,
    Mts,
    Cjs,
    Cts,
    Ts,
    Js,
    Tsx,
    Jsx,
    Json,
    JsonDeclaration,
}

use Suffix::*;

const PLAIN: [Suffix; 5] = [Ts, Tsx, Dts, Js, Jsx];
const ESM: [Suffix; 3] = [Mts, Dmts, Mjs];
const CJS: [Suffix; 3] = [Cts, Dcts, Cjs];
const JSX_FAMILY: [Suffix; 5] = [Tsx, Ts, Dts, Jsx, Js];
// Longest text first. `.d.json.ts` and the empty suffix are never found at the end of a name.
const RECOGNIZED: [Suffix; 12] = [Dmts, Dcts, Dts, Json, Mjs, Mts, Cjs, Cts, Tsx, Jsx, Ts, Js];

impl Suffix {
    pub(crate) fn text(self) -> &'static str {
        match self {
            Absent => "",
            Dts => ".d.ts",
            Dmts => ".d.mts",
            Dcts => ".d.cts",
            Mjs => ".mjs",
            Mts => ".mts",
            Cjs => ".cjs",
            Cts => ".cts",
            Ts => ".ts",
            Js => ".js",
            Tsx => ".tsx",
            Jsx => ".jsx",
            Json => ".json",
            JsonDeclaration => ".d.json.ts",
        }
    }

    pub(crate) fn source_kind(self) -> Option<SourceKind> {
        match self {
            Absent | Json => None,
            Dts | Dmts | Dcts | JsonDeclaration => Some(SourceKind::Declaration),
            Mjs | Cjs | Js | Jsx => Some(SourceKind::JavaScript),
            Mts | Cts | Ts | Tsx => Some(SourceKind::TypeScript),
        }
    }

    pub(crate) fn format_hint(self) -> Option<ModuleFormat> {
        match self {
            Dmts | Mjs | Mts => Some(ModuleFormat::Esm),
            Dcts | Cjs | Cts => Some(ModuleFormat::Cjs),
            _ => None,
        }
    }

    /// A source suffix without a format: the package scope decides the format.
    pub(crate) fn scoped_format(self) -> bool {
        self.source_kind().is_some() && self.format_hint().is_none()
    }

    /// The grammar without JSX; `<T>x` assertions exist only there.
    pub(crate) fn parser_typescript(self) -> bool {
        matches!(
            self.source_kind(),
            Some(SourceKind::TypeScript | SourceKind::Declaration)
        ) && self != Tsx
    }

    pub(crate) fn explicit_runtime(self) -> bool {
        matches!(self, Js | Mjs | Cjs)
    }

    /// The suffixes that shadow this one, best first.
    pub(crate) fn priority(self) -> &'static [Suffix] {
        match self {
            Dts | Ts | Js | Tsx | Jsx => &PLAIN,
            Dmts | Mjs | Mts => &ESM,
            Dcts | Cjs | Cts => &CJS,
            Absent | Json | JsonDeclaration => &[],
        }
    }

    fn family(self) -> &'static [Suffix] {
        match self {
            Absent | Dts | Ts | Js => &PLAIN,
            Tsx | Jsx => &JSX_FAMILY,
            Dmts | Mjs | Mts => &ESM,
            Dcts | Cjs | Cts => &CJS,
            Json => &[JsonDeclaration, Json],
            JsonDeclaration => &[],
        }
    }

    /// The suffixes that replace this one, when the pass reads only `kinds`.
    pub(crate) fn replacements(self, kinds: &[SourceKind]) -> Vec<Suffix> {
        self.family()
            .iter()
            .copied()
            .filter(|suffix| {
                let kind = if *suffix == Json {
                    Some(SourceKind::Json)
                } else {
                    suffix.source_kind()
                };
                kind.is_some_and(|kind| kinds.contains(&kind))
            })
            .collect()
    }
}

/// `classify_file`: the longest known suffix, no suffix, or `None` for an unsupported suffix.
pub(crate) fn classify_file(name: &str) -> Option<Suffix> {
    let longest = RECOGNIZED
        .iter()
        .copied()
        .filter(|suffix| name.ends_with(suffix.text()))
        .max_by_key(|suffix| suffix.text().len());
    if longest.is_some() {
        return longest;
    }
    let base = name.rsplit('/').next().unwrap_or(name);
    (!base.contains('.')).then_some(Absent)
}

/// `split_file`: the stem and a recognized suffix; an unsupported name has no family.
pub(crate) fn split_file(name: &str) -> Option<(&str, Suffix)> {
    match classify_file(name)? {
        Absent => None,
        suffix => Some((&name[..name.len() - suffix.text().len()], suffix)),
    }
}

/// `config._shadowed`: a sibling with the same stem and a higher-priority suffix wins.
pub(crate) fn shadowed(path: &str, known: &dyn Fn(&str) -> bool) -> bool {
    let Some((stem, suffix)) = split_file(path) else {
        return false;
    };
    let group = suffix.priority();
    let position = group.iter().position(|item| *item == suffix).unwrap_or(0);
    group[..position].iter().any(|better| {
        known(&format!("{stem}{}", better.text()))
            && !(*better == Dts && matches!(suffix, Js | Jsx))
    })
}

/// `SpecifierKind`, in the order of the Python pattern.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum SpecifierKind {
    Current,
    Parent,
    CurrentPath,
    ParentPath,
    Absolute,
    Node,
    Scoped,
    Imports,
    Bare,
}

#[derive(Clone, Debug)]
pub(crate) struct Specifier {
    pub kind: SpecifierKind,
    pub name: String,
    pub package: String,
    pub typed_name: String,
    pub directory_only: bool,
}

// `module.builtinModules` of Node 22, plus the names that exist only with the `node:` prefix.
const BUILTINS: &[&str] = &[
    "_http_agent",
    "_http_client",
    "_http_common",
    "_http_incoming",
    "_http_outgoing",
    "_http_server",
    "_stream_duplex",
    "_stream_passthrough",
    "_stream_readable",
    "_stream_transform",
    "_stream_wrap",
    "_stream_writable",
    "_tls_common",
    "_tls_wrap",
    "assert",
    "assert/strict",
    "async_hooks",
    "buffer",
    "child_process",
    "cluster",
    "console",
    "constants",
    "crypto",
    "dgram",
    "diagnostics_channel",
    "dns",
    "dns/promises",
    "domain",
    "events",
    "fs",
    "fs/promises",
    "http",
    "http2",
    "https",
    "inspector",
    "inspector/promises",
    "module",
    "net",
    "os",
    "path",
    "path/posix",
    "path/win32",
    "perf_hooks",
    "process",
    "punycode",
    "querystring",
    "readline",
    "readline/promises",
    "repl",
    "stream",
    "stream/consumers",
    "stream/promises",
    "stream/web",
    "string_decoder",
    "sys",
    "timers",
    "timers/promises",
    "tls",
    "trace_events",
    "tty",
    "url",
    "util",
    "util/types",
    "v8",
    "vm",
    "wasi",
    "worker_threads",
];
const SCHEME_ONLY: [&str; 4] = ["sea", "sqlite", "test", "test/reporters"];

/// `classify_specifier`: classify the reserved syntax once; the rest is open input data.
pub(crate) fn classify_specifier(text: &str) -> Specifier {
    let kind = if text == "." {
        SpecifierKind::Current
    } else if text == ".." {
        SpecifierKind::Parent
    } else if text.starts_with("./") {
        SpecifierKind::CurrentPath
    } else if text.starts_with("../") {
        SpecifierKind::ParentPath
    } else if text.starts_with('/') {
        SpecifierKind::Absolute
    } else if text.starts_with("node:") {
        SpecifierKind::Node
    } else if text.starts_with('@') {
        SpecifierKind::Scoped
    } else if text.starts_with('#') {
        SpecifierKind::Imports
    } else {
        SpecifierKind::Bare
    };
    let name = match kind {
        SpecifierKind::Node => &text["node:".len()..],
        _ => text,
    };
    let parts: Vec<&str> = text.split('/').collect();
    let package = if kind == SpecifierKind::Scoped {
        parts[..parts.len().min(2)].join("/")
    } else {
        parts[0].to_owned()
    };
    let typed_name = if kind == SpecifierKind::Scoped && parts.len() > 1 {
        // `replace("/", "__", 1)[1:]`: drop the `@` after the first slash became `__`.
        text.replacen('/', "__", 1)[1..].to_owned()
    } else {
        text.to_owned()
    };
    Specifier {
        kind,
        name: name.to_owned(),
        package,
        typed_name,
        directory_only: text.ends_with('/'),
    }
}

impl Specifier {
    pub(crate) fn relative_path(&self) -> bool {
        matches!(
            self.kind,
            SpecifierKind::CurrentPath | SpecifierKind::ParentPath
        )
    }

    pub(crate) fn relative(&self) -> bool {
        self.relative_path() || matches!(self.kind, SpecifierKind::Current | SpecifierKind::Parent)
    }

    pub(crate) fn builtin(&self) -> bool {
        BUILTINS.contains(&self.name.as_str())
            || (self.kind == SpecifierKind::Node && SCHEME_ONLY.contains(&self.name.as_str()))
    }

    /// Whether `package` is a registry-shaped name; a project alias such as `@/lib` is not.
    pub(crate) fn npm_package(&self) -> bool {
        let shaped = |name: &str| {
            let mut chars = name.chars();
            chars
                .next()
                .is_some_and(|first| first.is_ascii_alphanumeric())
                && chars.all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
        };
        match self.kind {
            SpecifierKind::Scoped => self
                .package
                .strip_prefix('@')
                .and_then(|rest| rest.split_once('/'))
                .is_some_and(|(scope, name)| shaped(scope) && shaped(name)),
            SpecifierKind::Bare => shaped(&self.package),
            _ => false,
        }
    }
}

// File types that a bundler loads itself; the match is case-sensitive.
const ASSET_SUFFIXES: &[&str] = &[
    ".css", ".scss", ".sass", ".less", ".styl", ".pcss", ".svg", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".avif", ".ico", ".bmp", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".webm",
    ".mp3", ".wav", ".ogg", ".json",
];
const ASSET_QUERIES: &[&str] = &["url", "raw", "inline", "worker", "sharedworker"];

/// `posixpath.splitext`: the extension of the last component; leading dots do not count.
pub(crate) fn splitext(path: &str) -> (&str, &str) {
    let slash = path.rfind('/').map_or(0, |index| index + 1);
    let Some(dot) = path.rfind('.').filter(|dot| *dot >= slash) else {
        return (path, "");
    };
    if path[slash..dot].chars().all(|c| c == '.') {
        return (path, "");
    }
    (&path[..dot], &path[dot..])
}

/// `classify_asset`: the path of a specifier that a bundler loads as an asset, else `None`.
///
/// A query alone never turns a source file (`./w.ts?worker`) into an asset.
pub(crate) fn classify_asset(specifier: &str) -> Option<&str> {
    let (path, query) = specifier.split_once('?').unwrap_or((specifier, ""));
    if ASSET_SUFFIXES.contains(&splitext(path).1) {
        return Some(path);
    }
    let queried = !query.is_empty() && query.split('&').any(|key| ASSET_QUERIES.contains(&key));
    let source = classify_file(path).and_then(Suffix::source_kind);
    (queried && source.is_none()).then_some(path)
}

#[cfg(test)]
#[path = "source_input_tests.rs"]
mod tests;

/// The options that can map a name to a file of the project (#976, #988).
#[derive(Clone, Copy)]
pub(crate) struct Reach {
    /// `paths` or `baseUrl` is set.
    pub aliased: bool,
    /// A type root may lie inside the project.
    pub type_roots: bool,
}
