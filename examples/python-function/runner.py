"""The subject command for one Python function: `runner.py <out>`.

Reads every fixture in FIXTURES, calls the function over each, and writes the
answers — keyed by fixture path — as sorted-key JSON to <out>. That file is
golden-census's whole record; this script prints nothing on success, because its
stdout and stderr are recorded as goldens too and a line that moves is a diff.

Exit 0 when the file was written, 2 when the arguments are wrong (one usage
line on stderr), 1 on any failure (the exception's name and first line on
stderr, never a traceback). README.md beside the template says why each line
is here.
"""

from __future__ import annotations

import json
import os
import sys

#: The fixtures, relative to this file's own directory rather than to the
#: cwd, so the list reads the same whatever directory golden-census runs from.
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = ["fixtures/plain.txt", "fixtures/hyphens.txt"]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: runner.py <out>\n")
        return 2
    # Imported here rather than at the top so a module that will not import
    # is the one-line failure below, not a traceback.
    import wordstats
    results = {}
    for fixture in FIXTURES:
        path = os.path.join(HERE, fixture)
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except OSError as exc:
            # The fixture's own name, never its absolute path: stderr is a
            # golden, and a home directory in one is a golden of the machine.
            raise RuntimeError(f"fixture {fixture}: {exc.strerror}") from None
        results[fixture] = wordstats.summarize(text)
    with open(argv[1], "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(results, sort_keys=True, indent=2,
                                ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:  # noqa: BLE001 — every failure is one line, by design
        first = str(exc).splitlines()[0] if str(exc) else ""
        sys.stderr.write(f"{type(exc).__name__}: {first}\n")
        sys.exit(1)
