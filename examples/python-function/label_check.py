"""The `command` check of `mutants.toml`: the constant no surface carries.

`summarize` never returns `wordstats.LABEL`, so the runner never writes it and
no golden holds it — the comparator is blind to a change there. This script is
what sees it: it prints the label, and the check is `fires = { absent =
"wordstats/1" }`, so a mutated clone whose label moved prints something else
and the check FIRES.

It is a committed script rather than an inline `python3 -c …` because
`golden-census mutants` runs a check in the MUTATED COPY only when the first
argument after the interpreter is a real file inside that copy
(`docs/mutants-format.md`, "where a check runs"). An inline expression would
run beside the mutants file and import the UNMUTATED package — a check that is
SILENT forever and reads as a pass.

Prints one line, exits 0. The verdict is the text, not the code.
"""

from __future__ import annotations

import os
import sys

# Stated rather than relied on: a script's own directory is already
# `sys.path[0]`, but $PYTHONSAFEPATH (or `python -P`) removes it, and this
# script's whole job is to import the package beside it.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wordstats  # noqa: E402 — after the path line above, by design

sys.stdout.write(f"label {wordstats.LABEL}\n")
