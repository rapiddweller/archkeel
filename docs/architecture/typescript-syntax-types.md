# TypeScript syntax port

The source component owns one frozen syntax DTO port and its nominal semantic domains. Existing DTOs move from parse.py into syntax.py; parser objects never cross that port. Only parse.py touches Tree-sitter, classifies node kinds at the input boundary, and handles unknown kinds conservatively. Collection consumes the typed syntax rather than comparing parser/protocol control strings or inferring a known category from arbitrary names.

Direct native comparison guards cover parse.py and collect.py. Independent Target intent pins seven semantic domains and eight critical DTO fields, and actual source mutation controls keep that intent fixed. Reserved path/package-prefix grammar remains explicitly tracked as the next coherent input-decoder increment under issue542.
