"""One pure function over a text, and the two constants the mutants edit.

Deterministic by construction: no clock, no filesystem, no random source, and
no set or dict of unknown order reaches the returned value — the ranking is
ordered by `(-count, word)`, which is a total order over the words of any
text, so two runs of one tree produce the same bytes. That is the whole
precondition `capture --twice` checks, stated here where it is kept.
"""

from __future__ import annotations

import re

#: A hyphen inside a word keeps the word whole: `well-known` is ONE token.
#: The comparator's mutant flips this to False, which splits every hyphenated
#: word in two and moves the counts of `fixtures/hyphens.txt` — and of no
#: other fixture, so the diff names the fixture as well as the key.
HYPHEN_JOINS = True

#: This build's own word. NO recorded surface carries it — the runner writes
#: only what `summarize` returns — so the comparator cannot see it move. It is
#: the second mutant's whole point, and `label_check.py` is the check that
#: does see it.
LABEL = "wordstats/1"

_JOINED = re.compile(r"[a-z]+(?:-[a-z]+)*")
_SPLIT = re.compile(r"[a-z]+")


def tokenize(text: str) -> list[str]:
    """The words of `text`, lower-cased, in the order they appear."""
    pattern = _JOINED if HYPHEN_JOINS else _SPLIT
    return pattern.findall(text.lower())


def summarize(text: str) -> dict[str, object]:
    """`{"tokens": N, "distinct": N, "ranked": [{"word": …, "count": …}, …]}`.

    `ranked` is ordered by descending count and then by the word, so equal
    counts never leave their order to a dict's insertion order.
    """
    tokens = tokenize(text)
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return {
        "tokens": len(tokens),
        "distinct": len(counts),
        "ranked": [{"word": word, "count": count} for word, count in ranked],
    }
