"""Entry point for `python3 -m golden_census` and
`python3 golden_census/__main__.py`.

Nothing above the guard may need a Python newer than 3.9: this file is the
one the old interpreter actually reaches, so it is the one that has to be
readable by it. Only `os` and `sys`, and no syntax the floor does not have.
"""

import os
import sys

# Run as a plain script, `sys.path[0]` is THIS directory, not the package's
# parent, so the absolute import below would not resolve. Under `-m` the
# package is already importable and the insert never happens.
if not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# THE FLOOR, checked before the import below and not after it.
# `golden_census.core` imports `tomllib`, which arrived in 3.11: without this
# check a 3.9 or a 3.10 dies four frames deep in a traceback ending
# `ModuleNotFoundError: No module named 'tomllib'` at exit 1 — a stack about an
# import, for a reader whose problem is an interpreter. A refusal is one
# sentence naming the floor and the interpreter that was actually found, and
# exits 2 like every other refusal. `bin/golden-census` holds the same floor a
# step earlier, for the reader who never types an interpreter; this holds it
# for the reader who does. The console script
# `golden-census = golden_census.console:main` reaches neither —
# `requires-python = ">=3.11"` is what refuses that install.
#
# The `noqa` is the rule being wrong about this one file: UP036 reads
# `target-version = "py311"` and calls a 3.11 test outdated, which is true
# of every file the floor already guarantees — and false of THIS one, the
# only module a pre-3.11 interpreter ever reaches.
if sys.version_info < (3, 11):        # noqa: UP036 — see above
    FOUND = ".".join(str(part) for part in sys.version_info[:3])
    # UTF-8 for the dash below, set as `cli.main` sets it for everything
    # else: `reconfigure` is 3.7's, so the old interpreter has it.
    sys.stdout.reconfigure(encoding="utf-8", errors="surrogateescape")
    sys.stdout.write(
        "REFUSED: golden-census needs Python 3.11 or newer and this is Python "
        + FOUND + " (" + sys.executable + "). It reads the manifest, the "
        "census and the mutants file with `tomllib`, which arrived in 3.11.\n"
        "  next: Re-run under Python 3.11 or newer — `bin/golden-census` "
        "locates one itself.\n")
    raise SystemExit(2)

from golden_census.console import main  # noqa: E402  — the path and the floor come first

raise SystemExit(main())
