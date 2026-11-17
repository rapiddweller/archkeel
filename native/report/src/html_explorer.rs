// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Explorer of the report page (AD-606): the 4.0.1 ArchQ Explorer, its scripts byte for byte,
//! with the 5.0 design tokens. The page writes the data of the frame as one JSON block; the
//! scripts read it and draw As-Is, Target and Diff for the system and for each component.

use serde_json::Value;

const SECTION: &str = include_str!("../assets/explorer/explorer.html");
const RULES: &str = include_str!("../assets/explorer/explorer.css");
const THEME: &str = include_str!("../assets/explorer/explorer-theme.css");

/// The scripts of the Explorer in load order: the source, the attributes of the tag and the
/// `script-src` hash (SHA-256, base64). A test compares each hash with its file.
pub(super) const SCRIPTS: [(&str, &str, &str); 8] = [
    (
        include_str!("../assets/explorer/elkjs-0.12.0.bundled.js"),
        " data-elkjs-version=\"0.12.0\"",
        "EiLkT5U853Rq8jgB5yNwj45vQ2uLN3pqX8dVLzSjB7M=",
    ),
    (
        include_str!("../assets/explorer/report-graph-protocol.js"),
        " data-report-asset=\"graph-protocol\"",
        "0mbKdgpJXx3vHuvytbhN9Dm0to/wVtXxAeABjzy8+sw=",
    ),
    (
        include_str!("../assets/explorer/report-graph-scene.js"),
        " data-report-asset=\"graph-scene\"",
        "d8GBv87ONHFHtGM4xwsCXIw+8qpYSH/fnXa1rKJnis8=",
    ),
    (
        include_str!("../assets/explorer/report-atlas-deviations.js"),
        " data-report-asset=\"atlas-deviations\"",
        "t9i713t+C3uT5BNqUhiqutYe+WUOG7J8sDiQY4fHtQk=",
    ),
    (
        include_str!("../assets/explorer/report-scene.js"),
        " data-report-asset=\"scene\"",
        "i1HdKRdTKI9deir80/QaZKwvlOrd7yjfT/7L+mULqW8=",
    ),
    (
        include_str!("../assets/explorer/report-layout.js"),
        " data-report-asset=\"layout\"",
        "78brj+8BnVEHQEXUZgf6q/rPRFWGqPHv5QWqFqT9cPI=",
    ),
    (
        include_str!("../assets/explorer/flow.runtime.js"),
        " data-report-asset=\"flow\"",
        "Azk5KqDIkuSW6ian3fvzCEbdU1a2VbUWksc8ImnEpO8=",
    ),
    (
        include_str!("../assets/explorer/report-canvas.js"),
        " data-report-asset=\"canvas\"",
        "FSFPN/L55CI2uw4kxFol9ISZP70AgfJn8TyGlIZ6zFA=",
    ),
];

/// The `script-src` sources of the Explorer scripts.
pub(super) fn sources() -> String {
    SCRIPTS
        .iter()
        .map(|(_, _, hash)| format!(" 'sha256-{hash}'"))
        .collect()
}

/// The style of the Explorer: the 4.0.1 rules, then the 5.0 tokens for their variables.
pub(super) fn style() -> String {
    format!("{RULES}\n{THEME}")
}

/// The section: the markup of the Explorer, its data and its scripts. A `<` in the data is
/// written as `<`, so no text of the frame can close the data block.
pub(super) fn section(payload: &Value) -> String {
    let data = payload.to_string().replace('<', "\\u003c");
    let scripts: String = SCRIPTS
        .iter()
        .map(|(source, attributes, _)| format!("<script{attributes}>{source}</script>\n"))
        .collect();
    format!(
        "<div class=\"rp-explorer\"><button class=\"theme-toggle\" type=\"button\" hidden \
aria-label=\"Switch to light theme\">&#9728;</button>\n{SECTION}<script id=\"flow-data\" \
type=\"application/json\">{data}</script>\n{scripts}</section></div>\n"
    )
}
