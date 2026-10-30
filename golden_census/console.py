"""The command as a reader runs it: the console script's target, and what
`python3 -m golden_census` calls.

`cli` reads the command line and runs every command. Two of them run the
package's own checks — `--selfcheck` the arms, `--selftest` the groups over
the bundled fixture — and both import `cli`, to exercise it. So `cli` imports
neither, and this module, above all three, hands `cli.main` the two runners.
No module of the package imports this one but `__main__`.

Run as a script — `python3 -m golden_census.console …` — it runs `main`, as
the console script does: without the guard at the bottom, that command ran
the module's body, printed nothing and exited 0.
"""

from __future__ import annotations

from . import cli
from .selfcheck import selfcheck
from .selftest import selftest


def main(argv: list[str] | None = None) -> int:
    """One command, start to finish: `cli.main`, handed what `--selfcheck`
    and `--selftest` run."""
    return cli.main(argv, selfcheck=selfcheck, selftest=selftest)


if __name__ == "__main__":
    raise SystemExit(main())
