// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shell of the report page: the policy, the theme script, the style and the top bar (AD-496).
//! The files are the design system of the owner; the page loads no other resource.

use super::markup::{base64, escape};

const TOKENS: &str = include_str!("../assets/tokens.css");
const BUNDLE: &str = include_str!("../assets/bundle.css");
const LOCAL: &str = include_str!("../assets/report.css");
const LIGHT: &str = include_str!("../assets/theme-light.css");
/// The one script of the page: the theme switch of the design system, byte for byte.
pub(super) const THEME_SCRIPT: &str = include_str!("../assets/archkeel-theme.js");
/// `script-src` hash of `THEME_SCRIPT` (SHA-256, base64). A test compares it with the file.
pub(super) const THEME_HASH: &str = "7Nxpcda8Ma/3b9a9tVfzi2nq7DW881vYvx7B8kWdOUQ=";
const GEIST: &[u8] = include_bytes!("../assets/Geist-Variable.woff2");
const MONO: &[u8] = include_bytes!("../assets/JetBrainsMono-Variable.woff2");

fn font(family: &str, weight: &str, bytes: &[u8]) -> String {
    format!(
        "@font-face{{font-family:\"{family}\";font-weight:{weight};font-style:normal;\
font-display:block;src:url(data:font/woff2;base64,{}) format(\"woff2\");}}",
        base64(bytes)
    )
}

/// The whole style: the fonts, the tokens, the components and the local rules. Without the script
/// the theme follows the system, and print is always light.
fn style() -> String {
    let mut css = font("Geist", "100 900", GEIST);
    css.push_str(&font("JetBrains Mono", "100 800", MONO));
    for part in [TOKENS, "\n", BUNDLE, "\n", LOCAL] {
        css.push_str(part);
    }
    css.push_str(&format!(
        "@media (prefers-color-scheme:light){{html:not([data-theme]){{{LIGHT}color-scheme:light}}}}\
@media print{{:root,[data-theme]{{{LIGHT}color-scheme:light}}}}"
    ));
    css
}

fn toggle() -> String {
    let button = |theme: &str, label: &str, icon: &str, pressed: bool| {
        format!(
            "<button class=\"ak-seg__btn ui\" type=\"button\" data-ak-theme=\"{theme}\" \
aria-pressed=\"{pressed}\"><svg class=\"ak-icon\" viewBox=\"0 0 16 16\" aria-hidden=\"true\">{icon}</svg>{label}</button>"
        )
    };
    let sun = "<circle cx=\"8\" cy=\"8\" r=\"2.6\"/><path d=\"M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1\"/>";
    let moon = "<path d=\"M13.2 9.6A5.4 5.4 0 0 1 6.4 2.8a5.4 5.4 0 1 0 6.8 6.8z\"/>";
    format!(
        "<div class=\"ak-seg\" role=\"group\" aria-label=\"Theme\">{}{}</div>",
        button("light", "Light", sun, false),
        button("dark", "Dark", moon, true)
    )
}

/// The start of the page up to the opening of `main`.
pub(super) fn start(subject: &str) -> String {
    format!(
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n\
<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; \
font-src data:; img-src data:; script-src 'sha256-{THEME_HASH}'; base-uri 'none'; form-action 'none'\">\n\
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\
<title>ArchKeel report</title>\n<script>{THEME_SCRIPT}</script>\n<style>{}</style>\n</head>\n\
<body class=\"ak-root body\">\n<header class=\"rp-top\"><p class=\"h3 rp-word\">ArchKeel<i>.</i></p>\
<p class=\"body-sm rp-subject\">{}</p>{}</header>\n<main class=\"rp-main\">\n",
        style(),
        escape(subject),
        toggle()
    )
}

/// The end of the page.
pub(super) const END: &str = "</main>\n</body></html>\n";
