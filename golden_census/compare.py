"""Comparing a golden set against a fresh capture or a recorded one.

The manifest's `[[movements]]` are merged with the `--allow-diff` rows, so the
committed attribution table and a stage's temporary one are read through one
function.

Normalization happens at capture time, never here: `compare` is a byte
comparison of two directories of already-normalized files. `--against` reads
BOTH sides off disk and normalizes NEITHER, so a fold change shows up as a diff
rather than being applied retroactively to the golden.
"""

from __future__ import annotations

import contextlib
import difflib
import fnmatch
import json
import shlex
import sys
from typing import Any, NamedTuple

from .capture import capture, read_capture
from .census import own_log
from .core import (
    DIFF_LINES,
    EXIT_MOVED,
    EXIT_OK,
    DIFFERENCE,
    NO_ATTRIBUTION,
    RULE,
    Refusal,
    SKIP_EXTENSION,
    SURFACES_FILE,
    bad_byte,
    first_difference,
    lines_of,
    printable_text,
    next_line,
    workspace,
)
from .manifest import Manifest, command_context


class Diff(NamedTuple):
    path: str
    kind: str            # "changed" | "only-in-golden" | "only-in-new"
    detail: str


def diff_captures(golden: dict[str, str], new: dict[str, str]) -> list[Diff]:
    diffs: list[Diff] = []
    for path in sorted(set(golden) | set(new)):
        if path not in new:
            diffs.append(Diff(path, "only-in-golden", ""))
            continue
        if path not in golden:
            diffs.append(Diff(path, "only-in-new", ""))
            continue
        if golden[path] == new[path]:
            continue
        # The hunk walks `core.lines_of`, the census's one line rule, so its
        # header counts the lines every other reader counts and a `\r` stays
        # in the line it ends. A hunk line `core.printable_text` rejects —
        # one holding a `\r`, a form feed or another character Python reads
        # as a line boundary, or an ESC, a BEL or another control character
        # — is written as its marker and its text quoted with `!r`: printed
        # raw, a terminal shows no such byte, the printer's own split of the
        # detail would cut the line in two, and an escape sequence would act
        # on the terminal and could hide the rows and the verdict after it.
        lines = [line[:1] + printable_text(line[1:])
                 for line in difflib.unified_diff(
                     lines_of(golden[path]), lines_of(new[path]),
                     fromfile=f"golden/{path}", tofile=f"new/{path}",
                     lineterm="", n=3)]
        if len(lines) > DIFF_LINES:
            lines = lines[:DIFF_LINES] + [
                f"... +{len(lines) - DIFF_LINES} more diff lines"]
        # `lines_of` cannot tell "abc" from "abc\n" — so two files differing
        # in their final newline alone reach here with an EMPTY hunk: a
        # verdict with no evidence, where every other row names the byte. The
        # sentence comes from `core.first_difference`, the one owner of "the
        # first difference between two texts", and not from a second walk of
        # the same two strings here.
        diffs.append(Diff(path, "changed",
                          "\n".join(lines)
                          or _no_line_detail(golden[path], new[path])))
    return diffs


def _no_line_detail(golden: str, new: str) -> str:
    """The one-line detail for two differing texts whose hunk is empty.

    The hunk and `first_difference` walk the same `lines_of`, so an empty
    hunk means every line agrees and the two texts differ in their final
    newline alone: `first_difference` names which one has it.
    """
    moved = first_difference(golden, new, DIFFERENCE)
    return moved.said() if moved is not None else ""


def read_allow(path: str | None) -> list[tuple[str, str]]:
    """The permitted-movement table as (pattern, attribution) rows.

    A line whose first non-blank character is `#` is a comment, and a blank
    line is skipped; every other line is one row, `path :: attribution`,
    whole — a `#` inside it is part of it, so `path :: fixed in #42` keeps
    `#42`, and a comment written after a bare path makes that path match
    nothing. A line with no `::`, or nothing after it, reads
    `(no attribution)`.

    A row is an EXACT surface path (`acceptance/acceptance.out`) unless it
    carries a glob character, in which case it is an explicit `fnmatch` pattern
    (`_engine/costpin-*`). Never a prefix match: a bare row `acceptance` would
    silently permit every file under `acceptance/`, and an attribution table
    whose rows permit more than they name is not an attribution table.

    A file that cannot be opened and a file that is not UTF-8 text are each
    a refusal naming the path as the reader typed it, written with `repr` so
    a path that holds a newline stays on one line, raised before a row is
    read; the second names the byte and its offset through `core.bad_byte`.
    """
    if path is None:
        return []
    rows: list[tuple[str, str]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as unreadable:
        # Every user-supplied path refuses at 2: `cli.main` reads the table
        # above the census's controls, so a mistyped path costs no run of the
        # subject, and again once they have run, so a table the subject removed
        # is refused, never an uncaught FileNotFoundError at exit 1.
        raise Refusal(
            f"--allow-diff names a file this run cannot read: {path!r} "
            f"({unreadable.strerror}), so every moved row would count as "
            "blocking.",
            next="Point --allow-diff at a readable table, or drop the flag "
                 "to compare against the manifest's [[movements]] rows "
                 "alone.") from unreadable
    except UnicodeDecodeError as undecodable:
        # The same rule for a table that opens and does not decode: a
        # sentence at 2 where the decoder's exception would leave at 1, which
        # is also the exit code of a comparison that found a moved row.
        raise Refusal(
            f"--allow-diff names a file that is not UTF-8 text: {path!r} "
            f"({bad_byte(undecodable)}). The permitted-movement table is "
            "read whole, as UTF-8 text, before anything is compared, so no "
            "row of it was read and nothing was compared.",
            next="Save that file as UTF-8, or drop the flag to permit only "
                 "the movements the manifest's own [[movements]] rows "
                 "name.") from undecodable
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prefix, _sep, reason = line.partition("::")
        rows.append((prefix.strip(), reason.strip() or NO_ATTRIBUTION))
    return rows


_GLOB_CHARS = "*?["


def _names(pattern: str, path: str) -> bool:
    """Whether the row `pattern` permits the moved row `path`: the ONE
    matcher, an exact path or an explicit `fnmatch` pattern."""
    if any(char in pattern for char in _GLOB_CHARS):
        return fnmatch.fnmatchcase(path, pattern)
    return path == pattern


def allowed_for(path: str, rows: list[tuple[str, str]]) -> str | None:
    for pattern, reason in rows:
        if _names(pattern, path):
            return reason
    return None


def unused_rows(diffs: list[Diff], allow: list[tuple[str, str]]) -> list[str]:
    """The rows of `allow` that permit none of `diffs`, in the order of
    `allow`: a `[[movements]]` or `--allow-diff` row whose movement did not
    happen is stale, and a verdict that says nothing of it reads as though
    every row were doing work."""
    return [pattern for pattern, _reason in allow
            if not any(_names(pattern, diff.path) for diff in diffs)]


def movement_rows(manifest: Manifest) -> list[tuple[str, str]]:
    """The manifest's `[[movements]]` as `(path, attribution)` rows: the
    table `compare` and `mutants`' comparator both permit movements by."""
    return [(row.path, row.attribution) for row in manifest.movements]


def split_diffs(diffs: list[Diff], allow: list[tuple[str, str]]
                ) -> tuple[list[tuple[Diff, str]], list[Diff]]:
    """`(permitted, each with its attribution; blocking)` — the ONE owner of
    which moved rows are permitted, and why. A row is permitted when a row
    of `allow` names it, whatever the attribution says: an empty one never
    reaches here (`manifest._movements` refuses it, and `read_allow` reads
    it as `(no attribution)`).

    A moved row that two rows of `allow` name — two globs, or a glob and
    an exact path, from the manifest's `[[movements]]` or `--allow-diff` —
    is refused, naming it and every row that names it with its
    attribution: it would be permitted under one attribution and never
    the other, which is why two rows with one `path` string are refused
    when the manifest is read. The sentence is `compare`'s and `mutants`'
    both: `mutants`' comparator prints its first line under the mutant's
    row, where no attribution is printed."""
    permitted: list[tuple[Diff, str]] = []
    blocking: list[Diff] = []
    for diff in diffs:
        naming = [(pattern, reason) for pattern, reason in allow
                  if _names(pattern, diff.path)]
        if len(naming) > 1:
            raise Refusal(
                f"{diff.path} moved, and {len(naming)} rows that permit "
                "movements name it: "
                + " and ".join(f"{pattern!r}, attributed {reason!r}"
                               for pattern, reason in naming)
                + ". golden-census would print only the first row's "
                "attribution and say nothing of the others.",
                next="Keep one row that names it, with an attribution that "
                "gives every reason it moved: narrow the glob, or drop the "
                "row a glob already covers.")
        if naming:
            permitted.append((diff, naming[0][1]))
        else:
            blocking.append(diff)
    return permitted, blocking


def only_new_surfaces(blocking: list[Diff], manifest: Manifest,
                      golden: dict[str, str]) -> bool:
    """Whether every blocking row is a surface the manifest names and the
    golden does not record — the reader added a row and compared against a
    golden captured before it, so the act is `capture --force`, and the
    permits of the general `next:` are all wrong for them.

    True when each of `blocking` is one of two things. An `only-in-new` file
    `<input>/<surface>.<ext>`, where the manifest has that input and that
    surface in it and the golden's `<input>/surfaces.json` does not list the
    surface. Or a `changed` `<input>/surfaces.json` of an input with at least
    one row of the first kind. Anything else — a surface file that changed,
    an `only-in-golden` row, a file of a surface the golden does list or the
    manifest does not name — is False.

    The recorded list is read from `golden`, the text `read_capture` already
    returned, and not from disk again: `capture` owns the file's format, and
    this reads one key of it, the surface names, from text it was handed. A
    `surfaces.json` that does not parse as an object is False.
    """
    listed: dict[str, Any] = {}
    unrecorded: set[str] = set()
    changed: set[str] = set()
    for diff in blocking:
        name, slash, entry = diff.path.partition("/")
        subject_input = manifest.input_named(name)
        if not slash or subject_input is None:
            return False
        if diff.kind == "changed" and entry == SURFACES_FILE:
            changed.add(name)
            continue
        stem, dot, _extension = entry.rpartition(".")
        if (diff.kind != "only-in-new" or not dot
                or stem not in {surface.name for surface
                                in manifest.surfaces_for(subject_input)}):
            return False
        if name not in listed:
            try:
                listed[name] = json.loads(golden[f"{name}/{SURFACES_FILE}"])
            except (KeyError, ValueError):
                return False
        if not isinstance(listed[name], dict) or stem in listed[name]:
            return False
        unrecorded.add(name)
    return changed <= unrecorded


def only_dropped_surfaces(blocking: list[Diff], manifest: Manifest,
                          golden: dict[str, str]) -> bool:
    """Whether every blocking row is a surface the golden records and the
    manifest no longer names — the reader removed a row and compared against
    a golden captured before, so the act is `capture --force`, and the
    permits of the general `next:` are all wrong for them. The mirror of
    `only_new_surfaces`.

    True when each of `blocking` is one of two things. An `only-in-golden`
    file `<input>/<surface>.<ext>`, where the manifest has that input, the
    golden's `<input>/surfaces.json` lists the surface, and the manifest does
    not name it among that input's surfaces. Or a `changed`
    `<input>/surfaces.json` of an input with at least one row of the first
    kind. Anything else — a surface file that changed, an `only-in-new` row,
    a file of a surface the manifest still names or the golden does not list,
    a file under an input the manifest does not name — is False.

    The recorded list is read from `golden`, the text `read_capture` already
    returned, and not from disk again. A `surfaces.json` that does not parse
    as an object is False.
    """
    listed: dict[str, Any] = {}
    dropped: set[str] = set()
    changed: set[str] = set()
    for diff in blocking:
        name, slash, entry = diff.path.partition("/")
        subject_input = manifest.input_named(name)
        if not slash or subject_input is None:
            return False
        if diff.kind == "changed" and entry == SURFACES_FILE:
            changed.add(name)
            continue
        stem, dot, _extension = entry.rpartition(".")
        if (diff.kind != "only-in-golden" or not dot
                or stem in {surface.name for surface
                            in manifest.surfaces_for(subject_input)}):
            return False
        if name not in listed:
            try:
                listed[name] = json.loads(golden[f"{name}/{SURFACES_FILE}"])
            except (KeyError, ValueError):
                return False
        if not isinstance(listed[name], dict) or stem not in listed[name]:
            return False
        dropped.add(name)
    return changed <= dropped


def identical(permitted: int) -> str:
    """The verdict of a comparison with no blocking row: `IDENTICAL`, and how
    many movements it permitted when there were any. `compare` prints it and
    `mutants`' comparator reports it as a SILENT verdict's detail."""
    return "IDENTICAL" + (f" ({permitted} permitted "
                          f"movement{'' if permitted == 1 else 's'})"
                          if permitted else "")


def read_sides(golden_dir: str, against: str | None) -> None:
    """`--golden`, then `--against` when it is given, each read whole by
    `capture.read_capture` — the one owner of what a capture directory is —
    in the order the parser declares them, and refused as it refuses them.
    Needs the file system and nothing else, so `cli.main` calls it above the
    census's controls for the `compare` command, where a refusal costs no
    run of the subject. What it read is not kept: `compare` reads both again
    where it compares, so its verdict is of the golden as it stands then."""
    read_capture(golden_dir, "--golden")
    if against is not None:
        read_capture(against, "--against")


def override_line(manifest: Manifest, command: tuple[str, ...]) -> str:
    """The `command:` line of the COMPARE block: `compare --command`'s argv,
    shell-quoted, with `<PYTHON>` and `<HERE>` resolved. `<ROOT>`, `<WORK>`
    and `<CLONE>` take their values in a run, and are printed as typed. The
    caller folds the line through the census, as the header's other lines
    are."""
    spelled = {name: f"<{name}>" for name in ("ROOT", "WORK", "CLONE")}
    table = command_context(here=manifest.here).also(
        {**spelled, "PYTHON": sys.executable})
    return "  command: " + shlex.join(
        table.expand(arg, "compare --command") for arg in command)


def compare(manifest: Manifest, golden_dir: str, against: str | None,
            allow_rows: list[tuple[str, str]] | None, out: Any,
            command: tuple[str, ...] = ()) -> int:
    """Compare a golden set against a fresh capture or a recorded one.

    The self-check that precedes a comparison is `cli.main`'s: this function
    compares, and does not decide when the controls run.

    `allow_rows` is the `--allow-diff` table as `read_allow` returned it, or
    `None` for no table: the caller reads it above the census's controls to
    refuse it, and again below them to hand it here, beside the golden this
    function reads again; this function reads none.

    Both directories a reader names are refused by `capture.read_capture`,
    which is the one owner of "a path golden-census cannot read a capture from
    is not an empty capture". A second `isdir` here is what let `--against` go
    unguarded while `--golden` was checked: one rule stated twice is one rule
    a reader can fall through. `cli.main` has `read_sides` read both above
    the census's controls, so a path they refuse costs no run of the subject;
    they are read again here.

    `command` is `compare --command`'s argv, empty when the flag was not
    given. `manifest` already carries it (`Manifest.with_command`, applied by
    `cli.main` before the census's controls), so the fresh capture ran it;
    this function names it in the block. The golden is the
    manifest's record whichever command ran: `surfaces.json` holds the
    arguments after the command and never the command itself, so the
    override moves no byte there, and the rows compare as they always do.
    """
    # Both attribution tables, as rows: the manifest's arrive with the
    # manifest, and the `--allow-diff` table's arrive read — `read_allow` is
    # called by the caller, below the census's controls. Merged for
    # permitting; kept apart for the `unused:` line, which names the table
    # the stale row is in.
    manifest_rows = movement_rows(manifest)
    file_rows = list(allow_rows or [])
    allow = manifest_rows + file_rows

    golden = read_capture(golden_dir, "--golden")

    # The temp directory this function makes for a fresh capture is removed
    # by `core.workspace`, in `finally` and not on the way out of the success
    # path: a refusal, a non-zero capture or a raise anywhere below must not
    # leave a `golden-census-compare-*` behind.
    # No census is passed, so no fixed-width directory is made: this function
    # runs no subject itself, and `capture` makes its own.
    with contextlib.ExitStack() as scratch:
        if against is not None:
            new = read_capture(against, "--against")
            label = against
        else:
            roots = scratch.enter_context(
                workspace(None, "golden-census-compare-", manifest.subject.root,
                          out=out))
            code = capture(manifest, roots.work, out)
            if code != 0:
                return code
            new = read_capture(roots.work, "the fresh capture")
            label = f"a fresh capture of {manifest.subject.name}"

        moved = diff_captures(golden, new)
        permitted, blocking = split_diffs(moved, allow)

        # The two header lines go through the census's OWN path folds
        # (`census.own_log`), the way every golden and every other command's
        # header lines do: an absolute path here would name a directory of
        # this machine, and would make this command's output track the width
        # of the machine's temp root — 15 characters on one machine, 49 under
        # macOS's per-user one — for a reason that is about the machine and
        # not about golden-census.
        census = manifest.census
        out.write("\n" + RULE + "\nCOMPARE\n  golden: "
                  + own_log(golden_dir, census, manifest.subject.root)
                  + "\n  new:    "
                  + own_log(label, census, manifest.subject.root)
                  # `--against` reads a recorded capture, so no census control
                  # and no contraband scan ran here; the line stands beside
                  # the verdict so a reader quoting IDENTICAL from this block
                  # does not take the controls as having run.
                  + ("\n  --against: no census control and no contraband "
                     "scan ran here; quote the ones from the capture that "
                     "made that directory." if against is not None else "")
                  + ("\n" + own_log(override_line(manifest, command), census,
                                    manifest.subject.root)
                     if command else "")
                  + "\n" + RULE + "\n")
        out.write(f"  {len(golden)} golden files, {len(new)} new files\n")
        # The rows that are a `.skip` on BOTH sides, named and never counted
        # alone: `IDENTICAL` says the two recorded reasons matched and says
        # nothing about the surface, which ran on neither side. A row whose
        # two `.skip` texts DIFFER is named here as well AND is a [DIFF]
        # below — this line says what did not run, not whether the two agree.
        # Printed only when there are any: a line saying zero is noise in the
        # common case.
        suffix = f".{SKIP_EXTENSION}"
        both_skipped = sorted(path[:-len(suffix)] for path in golden
                              if path.endswith(suffix) and path in new)
        # A summary of many rows, not a row: the one `[SKIP]` line
        # `core.skip_line` does not open, and its four spaces after the
        # bracket are its own shape, lined up with `[ALLOWED]` and `[DIFF]`.
        if both_skipped:
            out.write(f"  [SKIP]    {len(both_skipped)} row(s) are a skip on "
                      "both sides, so nothing ran to compare: "
                      + ", ".join(both_skipped) + "\n")
        for diff, reason in permitted:
            out.write(f"  [ALLOWED] {diff.path} — {reason}\n")
        for diff in blocking:
            out.write(f"  [DIFF]    {diff.path} ({diff.kind})\n")
            if diff.detail:
                for line in diff.detail.splitlines():
                    out.write(f"      {line}\n")
        # A row that permitted nothing, named beside the verdict it
        # qualifies: `IDENTICAL (1 permitted movement)` over two rows reads
        # as though both were doing work. Named by the table it is in, so
        # the reader opens the manifest for one and the allow file for the
        # other; manifest rows first, as `allow` orders them.
        for source, rows in (("[[movements]]", manifest_rows),
                             ("--allow-diff", file_rows)):
            for pattern in unused_rows(moved, rows):
                out.write(f"  unused: {source} row {pattern!r} permits a "
                          "movement that did not happen\n")
        if not blocking:
            out.write(f"\n  {identical(len(permitted))}\n")
            return EXIT_OK
        general = (
            "Each [DIFF] row above is a change nobody attributed. "
            "For an intended change, pass --allow-diff with a file "
            "holding one line per row, `<path> :: <attribution>`. "
            "That permits the change for this comparison only. For "
            "a row that may differ from one comparison to the next, "
            "such as a version or a date, add a [[movements]] row "
            "to the manifest instead; that permits the row in every "
            "comparison from now on. When the new bytes are what "
            "the subject should do from now on, capture again with "
            "--force and commit the golden. A change that was not "
            "intended shows that the code change was not "
            "behavior-neutral.")
        # Chosen from facts this run holds: a row the manifest gained or
        # lost since the golden was captured is not a change to attribute.
        advice = ("Every [DIFF] row above is a surface the manifest names "
                  "and the golden does not record, because the golden was "
                  "captured from a manifest without those rows. To record "
                  "them, run capture --force and commit the golden with "
                  "the manifest row."
                  if only_new_surfaces(blocking, manifest, golden)
                  else "Every [DIFF] row above is a surface the golden "
                  "records and the manifest no longer names. To stop "
                  "recording them, run capture --force and commit the "
                  "golden with the manifest."
                  if only_dropped_surfaces(blocking, manifest, golden)
                  else general)
        out.write(f"\n  {len(blocking)} differing row(s)\n"
                  + next_line(advice, "  ") + "\n")
        return EXIT_MOVED
