// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the Explorer assets and the style of the page (AD-606). Every colour comes from the
// tokens of the design system: no file writes a colour of its own, and no file redefines a token.

const TOKENS: &str = include_str!("../assets/tokens.css");

#[test]
fn every_script_hash_is_the_hash_of_its_embedded_bytes() {
    use sha2::{Digest, Sha256};
    let hash = |script: &str| super::markup::base64(&Sha256::digest(script.as_bytes()));
    assert_eq!(super::shell::THEME_HASH, hash(super::shell::THEME_SCRIPT));
    for (script, _, expected) in super::explorer::SCRIPTS {
        assert_eq!(expected, hash(script));
    }
}

/// The files that draw: the local style of the report and each Explorer asset except the vendored
/// ELK layout, which draws nothing.
const FILES: [(&str, &str); 10] = [
    ("report.css", include_str!("../assets/report.css")),
    (
        "explorer.css",
        include_str!("../assets/explorer/explorer.css"),
    ),
    (
        "explorer-theme.css",
        include_str!("../assets/explorer/explorer-theme.css"),
    ),
    (
        "flow.runtime.js",
        include_str!("../assets/explorer/flow.runtime.js"),
    ),
    ("flow.js", include_str!("../assets/explorer/flow.js")),
    (
        "report-canvas.js",
        include_str!("../assets/explorer/report-canvas.js"),
    ),
    (
        "report-scene.js",
        include_str!("../assets/explorer/report-scene.js"),
    ),
    (
        "report-layout.js",
        include_str!("../assets/explorer/report-layout.js"),
    ),
    (
        "report-graph-scene.js",
        include_str!("../assets/explorer/report-graph-scene.js"),
    ),
    (
        "report-graph-protocol.js",
        include_str!("../assets/explorer/report-graph-protocol.js"),
    ),
];

const NAMED: [&str; 19] = [
    "white", "black", "red", "green", "blue", "yellow", "orange", "gray", "grey", "purple", "pink",
    "silver", "navy", "teal", "lime", "maroon", "olive", "aqua", "fuchsia",
];

/// Each colour that a text writes itself: `#rgb` to `#rrggbbaa`, a colour function, or a named
/// colour as the value of a style property.
fn colours(text: &str, style: bool) -> Vec<String> {
    let mut found = Vec::new();
    let bytes = text.as_bytes();
    for (at, _) in text.match_indices('#') {
        let digits = bytes[at + 1..]
            .iter()
            .take_while(|b| b.is_ascii_hexdigit())
            .count();
        let after = bytes.get(at + 1 + digits).copied().unwrap_or(b' ');
        if [3, 4, 6, 8].contains(&digits)
            && !after.is_ascii_alphanumeric()
            && after != b'-'
            && after != b'_'
        {
            found.push(text[at..at + 1 + digits].to_owned());
        }
    }
    for function in ["rgb(", "rgba(", "hsl(", "hsla("] {
        found.extend(
            text.match_indices(function)
                .filter(|(at, _)| *at == 0 || !bytes[at - 1].is_ascii_alphanumeric())
                .map(|(_, f)| f.to_owned()),
        );
    }
    if style {
        for declaration in text.split([';', '{', '}']) {
            let value = declaration.split_once(':').map_or("", |(_, v)| v);
            found.extend(
                value
                    .split(|c: char| !c.is_ascii_alphanumeric() && c != '-')
                    .filter(|word| NAMED.contains(word))
                    .map(str::to_owned),
            );
        }
    }
    found
}

#[test]
fn no_file_of_the_page_writes_a_colour_of_its_own() {
    for (name, text) in FILES {
        let found = colours(text, name.ends_with(".css"));
        assert!(
            found.is_empty(),
            "{name} writes {found:?}: use a token of tokens.css"
        );
    }
}

#[test]
fn the_check_finds_each_kind_of_colour() {
    assert_eq!(
        colours("a{color:#fff;fill:#12ab34}", true),
        ["#fff", "#12ab34"]
    );
    assert_eq!(
        colours("a{background:rgba(1,2,3,.5);color:hsl(0 0% 0%)}", true),
        ["rgba(", "hsl("]
    );
    assert_eq!(
        colours("a{color:white;border:1px solid red}", true),
        ["white", "red"]
    );
    assert!(colours("#flow-data #x12 a{color:var(--ink)}", true).is_empty());
}

#[test]
fn no_explorer_file_redefines_a_token() {
    let tokens: Vec<&str> = TOKENS
        .split(['{', ';'])
        .filter_map(|part| part.trim().strip_prefix("--"))
        .filter_map(|part| part.split(':').next())
        .collect();
    assert!(tokens.contains(&"surface-0") && tokens.contains(&"space-4"));
    for (name, text) in FILES
        .iter()
        .filter(|(name, _)| name.starts_with("explorer"))
    {
        for token in &tokens {
            assert!(
                !text.contains(&format!("--{token}:")),
                "{name} redefines --{token}"
            );
        }
    }
}

/// The selectors of each rule of `explorer.css`, with the rules inside `@media` blocks.
fn selectors(css: &str) -> Vec<String> {
    let mut found = Vec::new();
    let mut head = String::new();
    let mut depth = 0usize;
    let mut comment = false;
    let mut chars = css.chars().peekable();
    while let Some(c) = chars.next() {
        if comment {
            if c == '*' && chars.peek() == Some(&'/') {
                chars.next();
                comment = false;
            }
            continue;
        }
        match c {
            '/' if chars.peek() == Some(&'*') => comment = true,
            '{' => {
                let text = head.trim().to_owned();
                if !text.starts_with('@') {
                    found.extend(text.split(',').map(|s| s.trim().to_owned()));
                }
                head.clear();
                depth += 1;
            }
            '}' => {
                depth = depth.saturating_sub(1);
                head.clear();
            }
            ';' if depth == 0 => head.clear(),
            _ => head.push(c),
        }
    }
    found.retain(|s| !s.is_empty());
    found
}

#[test]
fn every_explorer_rule_stays_inside_the_explorer() {
    let css = include_str!("../assets/explorer/explorer.css");
    let loose: Vec<String> = selectors(css)
        .into_iter()
        .filter(|s| !s.contains(".rp-explorer") && s != "from" && s != "to")
        .collect();
    assert!(
        loose.is_empty(),
        "explorer.css rules that can reach the rest of the report: {loose:?}"
    );
}

#[test]
fn explorer_spacing_and_radius_that_a_token_names_use_the_token() {
    let css = include_str!("../assets/explorer/explorer.css");
    for declaration in css.split([';', '{', '}']) {
        let Some((property, value)) = declaration.split_once(':') else {
            continue;
        };
        let property = property.trim();
        let (spacing, radius) = (
            [
                "padding", "margin", "gap", "top", "left", "right", "bottom", "inset",
            ]
            .iter()
            .any(|p| property == *p || property.starts_with(&format!("{p}-"))),
            property.starts_with("border") && property.contains("radius"),
        );
        if (!spacing && !radius) || value.contains("calc(") {
            continue;
        }
        let steps: &[&str] = if radius {
            &["4px", "8px", "12px"]
        } else {
            &["4px", "8px", "12px", "16px", "24px", "32px", "48px", "64px"]
        };
        for token in steps {
            let literal = value.split_whitespace().any(|word| word == *token);
            assert!(
                !literal,
                "{property}: {value} writes {token}: use a --space token"
            );
        }
    }
}

#[test]
fn the_layout_wraps_rows_only_for_boxes_without_a_layer_order() {
    let layout = include_str!("../assets/explorer/report-layout.js");
    // A chain or a set of boxes with no edge fills the view in rows; a layer order stays layered.
    assert!(layout.contains("\"elk.layered.wrapping.strategy\": \"MULTI_EDGE\""));
    assert!(layout.contains("!nodes.some((node) => node.id.startsWith(\"LAYER:\"))"));
}

// #1442, #1444: no sheet asks an unanswered question, repeats the 4.0.1 whole-run or observation
// lines, or fills a field with `None`, `unavailable` or `Nothing stated`. The shipped script is the
// one source of the sheets, so the lines cannot come back without this test failing.
#[test]
fn no_sheet_has_a_question_a_contradiction_or_a_filler_line() {
    let script = include_str!("../assets/explorer/flow.runtime.js");
    for banned in [
        "Does this fit the responsibility",
        "Source observation:",
        "Core projection:",
        "no scoped PASS",
        "no symbol count",
        "Symbol coverage",
        "Path unavailable",
        "Nothing stated in the contract",
        "no component-level verdict",
        "lexical inventory",
    ] {
        assert!(!script.contains(banned), "a sheet still says `{banned}`");
    }
    // A list with nothing in it is not drawn, so no list falls back to the word `None`.
    assert!(
        !script.contains(":\"None\""),
        "a sheet fills an empty list with None"
    );
    // The sheet of a component repeats no line of the whole run: only the card holds it.
    assert!(script.contains("if(component)return recordedChecks"));
}

// #1441: the owner of a module comes from the global assignments, so a module outside the level
// still has its owner on the sheet.
#[test]
fn the_sheet_of_a_module_reads_owners_from_the_global_assignments() {
    let script = include_str!("../assets/explorer/flow.runtime.js");
    assert!(script.contains("ATLAS.assignments.find(item=>item.id===id)"));
    assert!(
        !script.contains("UNKNOWN owner / outside this level\"")
            || script.contains("ATLAS.assignments.find")
    );
}

// #1443: the public names of a box are grouped by module with short names and a count, a long list
// of through-paths is folded behind a count, and many names fold behind the line that counts them.
#[test]
fn the_sheet_groups_provided_names_and_folds_long_lists() {
    let script = include_str!("../assets/explorer/flow.runtime.js");
    for needed in [
        "function atlasProvidesMarkup(",
        "function atlasRequiresMarkup(",
        "edge.through.length>2",
        "names.length>6",
        "Provides · ",
    ] {
        assert!(script.contains(needed), "the sheet lacks `{needed}`");
    }
    // The raw list of the through-paths is no longer printed in one line.
    assert!(!script.contains("`<p>Through: ${edge.through.map(esc).join(\", \")}</p>`"));
}
