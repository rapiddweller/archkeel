# AD-1007 A call-owner rule can select one function body

A `call_owner` source can name a top-level Python function. A matching module keeps precedence.
The linked Python collector counts calls while it walks the module. The model compares that
count with the exact call sites of the function. A missing function, target or exact call holds
the verdict at UNKNOWN. The count includes calls in nested definitions and decorators, so an
unproved nested call holds the verdict too. Saved replies do not carry this proof.

Counting the visible call records alone can miss calls outside admitted bodies. Counting the
whole module would let unrelated calls hold a function rule. The function count includes calls in
defaults and annotations, so those calls can also hold the verdict. The call-owner tests cover
missing inputs, direct and open calls, nested calls and module precedence.
