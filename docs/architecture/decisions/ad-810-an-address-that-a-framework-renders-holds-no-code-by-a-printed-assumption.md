# AD-810: An address that a framework renders holds no code, by a printed assumption

Status: accepted (lead decision 2026-11-17 on #1662, the pattern of AD-788). Part of #880.
Closes #1662. It amends premise 4 of AD-540 and AD-792.

## Context
AD-792 reads an address that the scanned code writes (`el.href = t`, `setAttribute('href', t)`).
A framework outside the scan roots renders an address from data instead: `<a href={url}>` in JSX
or a template binding. The scanned code writes no address, it only gives a text. When the text is
`javascript:window.open=…`, a click on the link replaces the global `open` that another component
calls. No sound rule over the scanned code alone can decide it: the text can come from any data.
A rule that withholds every global proof for each bound address makes every React application
UNKNOWN.

## Decision
1. **Assumption.** The stated assumption of each TypeScript scan gains "and addresses that a
   framework renders from data hold no javascript: code" (`records.rs`). The text header, the JSON
   key `premise` and the report show it with the verdict.
2. **Guard on the scan** (`source_input.rs`, `code_address`; used by `script_code.rs`). A text holds a code address when it
   holds `javascript:`, `vbscript:` or `data:text/html` anywhere, in any letter case, also with a
   tab or a line end (or the escape `\t`, `\n`, `\r`, `\u0009`, `\u000a`, `\u000d`) inside it.
   Each string and template of the scanned sources is checked, also a template with substitutions
   (its raw text) and a JSX attribute. A hit is the direct form "a text that can run as code" of
   AD-460: it withholds every global proof and the gap names the place. The check before read only
   a `javascript:` text at the start of a string without substitutions.
3. **Guard on data files** (`script_outside.rs`, beside the writer guard of AD-788). Each JSON and YAML file below a scan root
   (without installed and hidden directories) is read as text. The first file that holds a code
   address withholds every global proof; each use gets the gap "Script global X can be replaced by
   a code address in a data file", which cites the use and the file and line. A file that the guard
   cannot read counts as such a file.

## Soundness
The guard reads what the scan and its data files hold; data from elsewhere (a server, a database,
a file outside the roots) stays under the assumption, and the assumption is printed with each
verdict, so no PASS rests on an unstated assumption. Inside the scan, a code address in a text is
no longer silent. A text built at run time (`['java', 'script:'].join('')`) is no visible evidence:
the assumption covers it when a framework renders it, and AD-792 reads it when the scanned code
writes it to an address.

## Price
No PASS turns UNKNOWN on graphql-js v16.15.0 and the TypeScript fixtures F, H, H-uml and L-nest
(see the PR). A string that mentions a code scheme in a message (`'javascript: is not allowed'`)
withholds the proofs too: the reading is lexical and over-matches on purpose.

## Tests
`tests/test_collector_false_pass_ts_framework_address.py`: a string, a template, upper case,
`vbscript:`, `data:text/html`, a JSX attribute, a JSON file and a YAML file each give UNKNOWN with
the place; a bound address and plain data give PASS under the printed assumption.
`native/typescript/src/source_input_tests.rs`: the text check.
