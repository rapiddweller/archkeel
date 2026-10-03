# Collection protocol examples

Python and npm consume the same JSON files. The schema checks structure. The decoder also checks identities, references, scope and coverage.

`response-python.json` deliberately has partial capabilities. It is valid wire data; Core refuses to treat it as a complete Python profile.

Policy input and dangling evidence are negative cases. Neither may become a complete observation.
