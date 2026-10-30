"""wordstats: the example subject golden-census freezes.

One pure function, `summarize`, re-exported here so the runner's `import
wordstats` is all the manifest's `command` needs. `tokenize.py` carries the
function and the two constants the two mutants edit.
"""

from __future__ import annotations

from .tokenize import HYPHEN_JOINS, LABEL, summarize, tokenize

__all__ = ["HYPHEN_JOINS", "LABEL", "summarize", "tokenize"]
