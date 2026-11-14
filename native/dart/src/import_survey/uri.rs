// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Classify one literal directive URI of one package (AD-454, rule 4). The classification reads
//! only the text: the survey then looks up a local path in the selected sources.

use archkeel_snapshot::paths::{dirname, is_outside, join, normpath, within};

use crate::module::{dart_module_name, is_identifier};

/// What one URI names.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Uri {
    /// A `dart:` library, with its module `dart.<name>`.
    Builtin(String),
    /// A library of another package, with the package and the module `<package>.<path>`.
    External { package: String, module: String },
    /// A path relative to the snapshot root: a relative URI or a URI of the own package.
    Local(String),
    /// A path above the snapshot root, or above `lib` for the own package.
    Outside,
    /// A URI that the survey does not read, with the reason.
    Unsupported(&'static str),
}

/// Classify `uri` of a directive in the source `importer`. `own` is the package name of the root
/// `pubspec.yaml`, empty when there is none: then a `package:` URI is never local.
pub(crate) fn classify(importer: &str, uri: &str, own: &str) -> Uri {
    // A percent escape, a backslash and a NUL can name one file in more than one way.
    if uri.is_empty() || uri.contains(['\\', '\0', '?', '#', '%']) {
        return Uri::Unsupported(
            "the URI is empty or holds a query, a fragment, an escape or a backslash",
        );
    }
    let scheme = scheme(uri);
    match scheme.as_ref().map(|(head, rest)| (head.as_str(), *rest)) {
        Some(("dart", name)) if is_identifier(name) => Uri::Builtin(format!("dart.{name}")),
        Some(("dart", _)) => Uri::Unsupported("the dart: URI is not one library name"),
        Some(("package", rest)) => package(rest, own),
        Some(_) => Uri::Unsupported("the URI scheme is not dart: or package:"),
        None if uri.starts_with('/') => Uri::Unsupported("the URI is an absolute path"),
        None => {
            let joined = join(dirname(importer), uri);
            if is_outside(&joined) || joined.starts_with('/') {
                Uri::Outside
            } else {
                Uri::Local(joined)
            }
        }
    }
}

fn package(rest: &str, own: &str) -> Uri {
    let Some((name, path)) = rest.split_once('/') else {
        return Uri::Unsupported("the package: URI has no path");
    };
    if !is_identifier(name) || path.is_empty() || path.starts_with('/') {
        return Uri::Unsupported("the package: URI has no valid package name or path");
    }
    if name == own {
        let joined = normpath(&format!("lib/{path}"));
        return if within("lib", &joined) {
            Uri::Local(joined)
        } else {
            Uri::Outside
        };
    }
    let normalized = normpath(path);
    match dart_module_name(&normalized).filter(|_| !is_outside(&normalized)) {
        Some(module) => Uri::External {
            package: name.to_owned(),
            module: format!("{name}.{module}"),
        },
        None => Uri::Unsupported("the package: path is not a Dart module path"),
    }
}

/// The scheme and the rest of `uri`, when it starts with `ALPHA *( ALPHA / DIGIT / + / - / . ) :`
/// (RFC 3986). The scheme is in lower case, as Dart compares it.
fn scheme(uri: &str) -> Option<(String, &str)> {
    let (head, rest) = uri.split_once(':')?;
    let mut chars = head.chars();
    let valid = chars
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic())
        && chars.all(|c| c.is_ascii_alphanumeric() || matches!(c, '+' | '-' | '.'));
    valid.then(|| (head.to_ascii_lowercase(), rest))
}

/// Whether `rel` is the name of a generated Dart file that a build step writes.
pub(crate) fn generated(rel: &str) -> bool {
    rel.ends_with(".g.dart") || rel.ends_with(".freezed.dart")
}

#[cfg(test)]
#[path = "uri_tests.rs"]
mod tests;
