# AD-154 Incomplete ownership names its module

Report unowned and overlapping modules as FACTs carrying file, scope and competing
owners. They explain missing scope proof; they are not completed evaluator receipts.
Known violations still take precedence.

Only AST-empty Python initializers are exempt from ownership proof. Blank-file
assignment retains its separate compatibility rule. Guidance can show `exact_modules`
as a remedy without choosing the owner.

[Coverage proof](../../../tests/test_inside_rule_coverage.py).
