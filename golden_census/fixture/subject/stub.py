"""The stub subject `python3 -m harness --selftest` drives.

Small on purpose and deliberately awkward in the four ways every real subject
is awkward: it prints an absolute path (its own working directory), it prints
a duration that moves every run, it writes a JSON export whose provenance
block carries the commit it was built from, and it refuses one flag
combination. Each of those is a census row in `census.toml` beside this file,
and each of those rows has a control that proves the row matters.

Two constants below are the mutants' sites (`mutants.toml`): `ROWS`, which
every recorded surface carries, and `SECRET`, which none of them does. The
first is what the comparator catches; the second is what a consumer's own
`command` check catches, and nothing else can.

Nothing here imports the harness, and the harness never imports this: it is
run as a subprocess, exactly as any other subject is.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

VERSION = "1.2.0"

#: The row count every recorded surface carries — the comparator's mutant.
ROWS = 3

#: Printed only by `--secret`, which no surface of the manifest runs — the
#: `command` check's mutant, invisible to the comparator by construction.
SECRET = "SECRET=ok"

_STARTED = time.perf_counter()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stub",
        description="A stub subject the harness's own --selftest drives. It "
                    "prints a report carrying its working directory and the "
                    "microseconds the scan took, writes a JSON export with a "
                    "provenance block, prints a fenced tally block, and "
                    "refuses one flag combination. This description is long "
                    "enough that argparse has to wrap it at the terminal "
                    "width, which is what the census's COLUMNS pin is for.")
    parser.add_argument("--version", action="store_true",
                        help="print the stub's version and exit, and nothing "
                             "else at all")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="write the export to PATH; the provenance block "
                             "carries the commit this tree is at")
    parser.add_argument("--tallies", action="store_true",
                        help="print the fenced group blocks a tallies surface "
                             "reduces to one verdict line each")
    parser.add_argument("--secret", action="store_true",
                        help="print the constant no recorded surface carries")
    parser.add_argument("--one", action="store_true",
                        help="the first half of the combination that composes "
                             "with nothing")
    parser.add_argument("--two", action="store_true",
                        help="the second half; naming both is the refusal")
    return parser


def commit(root: str) -> str:
    """The tree's short commit, or `unknown`. Read from git rather than
    stamped in, so a clone that commits a mutant carries a DIFFERENT sha and
    the census's json-fields fold has something real to fold away."""
    try:
        proc = subprocess.run(["git", "-C", root, "rev-parse", "--short",
                               "HEAD"], check=False, capture_output=True,
                              text=True)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return proc.stdout.strip() or "unknown"


def export(root: str) -> dict[str, object]:
    return {
        "provenance": {
            "engine": {"version": VERSION, "commit": commit(root),
                       "dirty": False},
        },
        "rows": ROWS,
        "names": ["alpha", "beta", "gamma"][:ROWS],
    }


def tallies() -> str:
    rule = "=" * 78
    return (f"{rule}\nTHE FIRST GROUP\n{rule}\n"
            "  a line the reduction drops\n"
            f"  {ROWS}/{ROWS} passed\n\n"
            f"{rule}\nTHE SECOND GROUP\n{rule}\n"
            "  1/1 passed\n")


def report(root: str) -> str:
    elapsed = int((time.perf_counter() - _STARTED) * 1_000_000)
    return (f"stub report\n  cwd: {root}\n  rows: {ROWS}\n"
            f"  scan finished in {elapsed}us\n")


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    root = os.getcwd()
    if args.one and args.two:
        sys.stderr.write("stub: error: --one and --two compose with nothing; "
                         "drop --two\n")
        return 2
    if args.version:
        sys.stdout.write(f"{VERSION}\n")
        return 0
    if args.secret:
        sys.stdout.write(f"{SECRET}\n")
        return 0
    if args.tallies:
        sys.stdout.write(tallies())
        return 0
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(export(root), indent=2,
                                    ensure_ascii=False) + "\n")
        sys.stdout.write(f"wrote {args.json}\n")
        return 0
    sys.stdout.write(report(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
