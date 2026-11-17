# AD-790 Written empty Python bodies keep declarations out

**Status.** Accepted. Part of #880 and #1537.

**Reason.** A placeholder rule finds an implementation that has no body. A protocol
method or an abstract declaration is not an implementation.

**Decision.** The Python collector records a sole `pass`, ellipsis or docstring, and
a docstring followed by `pass` or ellipsis, as an empty body. It uses the lexical owner.
A method of `typing.Protocol` or `typing_extensions.Protocol` is a declaration when
import facts resolve the base. A stub file is a declaration. A function decorated with
`abc.abstractmethod` or `typing.overload` is a declaration, including an abstract
method of an `ABCMeta` class. These declarations are not placeholder implementations.
The current reader withholds these decorated functions rather than resolving them.

The reader withholds a site when a class base or decorator is not resolved, when a
name has multiple binders, or when the class has a keyword or decorator it cannot read.
It recognizes unshadowed builtin static, class and property decorators. Other decorators
stay unread. The capability remains partial because a lone raise and other forms need
more proof. An unread site never makes absence PASS.

**Alternative.** Treat every protocol method as an empty implementation. PEP 544 uses
these bodies to declare the protocol. That interpretation reports a false violation.

**Checks.** `tests/test_cli_python_placeholder.py` checks the seen forms, protocol
imports, abstract and unread declarations. `tests/test_cli_fixture_matrix.py` checks
that the F-architecture protocol declaration does not introduce a violation.
