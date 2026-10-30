"""Recording every row of a manifest into a directory.

This module owns the capture directory's on-disk format BOTH ways: the
`Recorder` that writes it and the `read_capture` that reads it sit beside each
other, so no `capture`<->`compare` import cycle is needed to reach either.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import functools
import json
import os
import pathlib
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from typing import Any, NamedTuple

from .census import (
    Census,
    about_to_run,
    describing,
    normalize_paths,
    own_log,
    path_pairs,
    state,
)
from .core import (
    LISTED,
    EXIT_OK,
    EXIT_REFUSED,
    DIFFERENCE,
    PATH_SOURCES,
    SKIP_EXTENSION,
    STREAM_ERR,
    STREAM_EXIT,
    STREAM_EXTENSIONS,
    STREAM_OUT,
    SURFACES_FILE,
    Made,
    PATH_START,
    Pending,
    Platform,
    Refusal,
    Roots,
    _capture_text,
    after_placeholder,
    attaching,
    first_difference,
    launch,
    left_behind,
    lines_of,
    path_forms,
    refuse_on_stderr,
    refusal_text,
    removed,
    row_key,
    signals_held,
    skip_line,
    temp_base,
    to_null,
    to_stderr,
)
from .manifest import (
    Input,
    Manifest,
    Surface,
    context,
)
from .run import (
    Place,
    RowRun,
    RunResult,
    Texts,
    _clear_written,
    place,
    recorded_texts,
    row_start,
    run_counter,
    run_row,
    run_subject,
    subject_command,
    surface_argv,
)


# ------------------------------------------------------------------ recording


#: What a surface records when its input's pinned tree could not be cloned.
#:
#: A FIXED sentence, because the reason is about the machine and a golden is
#: not. Git 2.54 says `fatal: repository '…' does not exist`; a machine with
#: no `git` says `git clone would not run: FileNotFoundError: [Errno 2] …`;
#: a machine with no network says something else again — so two machines
#: that BOTH skipped the input recorded two different goldens, and an error
#: quoting a local path put an absolute path into a `.skip` file, which the
#: contraband scan refuses: one input's clone failure then refused the whole
#: capture at exit 2 rather than skipping one input.
#:
#: The reason itself is not lost and is not normalized: it goes to the LOG,
#: twice — `[SKIP]  <input>: <why>` for the input and `[SKIP]
#: <input>/<surface>: <why>` for each of its surfaces — which is where the
#: skill file already tells an agent to read it. A DECLARED skip is the other
#: kind and keeps its own sentence: the manifest's author wrote it, it is the
#: same on every machine, and the reason IS the golden.
ENVIRONMENTAL_SKIP = "SKIP — the pinned tree is unavailable"


class Recorder:
    """Writes one capture directory and remembers what it wrote."""

    def __init__(self, out_dir: str, roots: Roots, census: Any) -> None:
        self.out_dir = out_dir
        self.roots = roots
        self.census = census
        #: Every file this capture wrote, in order: what the contraband scan
        #: reads and counts. Nothing here is taken back on a refusal —
        #: `out_dir` is a recording directory under the temp root, never the
        #: reader's `--out`, and a refused capture is removed with it, whole.
        self.written: list[str] = []
        self.surfaces: dict[str, dict[str, Any]] = {}
        self.skipped: list[tuple[str, str, str]] = []

    def _directory(self, subject_input: str) -> str:
        """`<out>/<input>`, made if it is not there: `out` and that one level,
        and nothing above them.

        `out` is a recording directory under the temp root. A root that a
        `[[setup]]` step or a row removed is not made again: the `OSError`
        is raised as it is."""
        directory = os.path.join(self.out_dir, subject_input)
        for level in (self.out_dir, directory):
            if not os.path.isdir(level):
                os.mkdir(level)
        return directory

    def _write(self, subject_input: str, surface: str, extension: str,
               text: str) -> None:
        directory = self._directory(subject_input)
        path = os.path.join(directory, f"{surface}.{extension}")
        self._claim(path)
        pathlib.Path(path).write_text(text, encoding="utf-8", newline="\n")
        self.written.append(path)

    def _claim(self, path: str) -> None:
        """Refuse a file this capture has already written.

        `written` is what the contraband scan reads and counts against the
        number of files it opened, so one path recorded twice reports more
        files read than exist and the scan's own `read != written` guard can
        never fire. The manifest loader refuses every `writes` that could
        reach here twice, which is what makes this refusal a DEFECT report
        rather than a rule a reader can break.
        """
        if path in self.written:
            raise Refusal(
                f"golden-census would write {os.path.basename(path)} twice "
                f"into {os.path.dirname(path)}: the second write would "
                "replace the first and the scan would count a file that is "
                "not on disk.",
                next="Report this as a golden-census defect, quoting the file name above: the "
                "manifest loader refuses every `writes` that can collide, so nothing in your "
                "files can cause it.")

    def record(self, subject_input: str, surface: str, result: RunResult,
               extension: str | None = None) -> None:
        self._put(subject_input, surface, result.tail, result.exit,
                  recorded_texts(result, self.census, self.roots,
                                 row_key(subject_input, surface), extension),
                  extension)

    def record_row(self, subject_input: str, surface: str,
                   row: RowRun) -> None:
        """One row `run.run_row` ran: its recorded texts, as they are."""
        self._put(subject_input, surface, row.tail, row.exit, row.recorded,
                  row.extension)

    def _put(self, subject_input: str, surface: str, tail: list[str],
             exit_code: int, texts: Texts, extension: str | None) -> None:
        """The one writer of a recorded run: its three streams, the file it
        wrote when it wrote one, and its `surfaces` entry."""
        census = self.census
        self._write(subject_input, surface, STREAM_OUT, texts.out)
        self._write(subject_input, surface, STREAM_ERR, texts.err)
        self._write(subject_input, surface, STREAM_EXIT, f"{exit_code}\n")
        if texts.written is not None:
            self._write(subject_input, surface, extension or "out",
                        texts.written)
        self.surfaces.setdefault(subject_input, {})[surface] = {
            "argv": [normalize_paths(a, census, self.roots) for a in tail],
            "status": "captured",
            "exit": exit_code,
        }

    def record_raw(self, subject_input: str, surface: str, out: str, err: str,
                   exit_code: int, argv: list[str]) -> None:
        """A record the caller has already reduced — a matrix's compaction —
        written with the census's `path` folds applied and nothing else.

        The path folds and not the regex or json-fields ones: those are scoped
        to named `<input>/<surface>` rows, and the text handed in here is a
        reduction of many runs, so there is no one row key to scope by. A
        tallies surface is ONE run of one row and goes through `record`. The
        paths are golden-census's own directories, which the contraband scan
        refuses in any file the capture writes — so without these folds a
        matrix row that printed the subject root would REFUSE the whole
        capture where a `run` row folds it to <REPO>.
        """
        self._write(subject_input, surface, STREAM_OUT,
                    normalize_paths(out, self.census, self.roots))
        self._write(subject_input, surface, STREAM_ERR,
                    normalize_paths(err, self.census, self.roots))
        self._write(subject_input, surface, STREAM_EXIT, f"{exit_code}\n")
        self.surfaces.setdefault(subject_input, {})[surface] = {
            "argv": argv, "status": "captured", "exit": exit_code,
        }

    def skip(self, subject_input: str, surface: str, reason: str,
             argv: Iterable[str] = (), logged: str | None = None) -> None:
        """Record a skipped surface, and say what it was.

        `reason` is what goes to DISK — the `.skip` file and `surfaces.json`
        — and `logged` is what goes to the log, defaulting to the same text,
        which is what a declared skip wants. They are two arguments because
        for an environmentally skipped surface they are two things: a fixed
        sentence on disk, because a golden carries nothing about the machine,
        and the reason in the log, because that is where a reader is told to
        look for it.
        """
        self._write(subject_input, surface, SKIP_EXTENSION,
                    reason.rstrip("\n") + "\n")
        self.surfaces.setdefault(subject_input, {})[surface] = {
            "argv": list(argv), "status": "skipped", "reason": reason,
        }
        self.skipped.append((subject_input, surface,
                             reason if logged is None else logged))

    def note_counts(self, subject_input: str, counts: dict[str, Any]) -> None:
        self.surfaces.setdefault(subject_input, {})["_counts"] = counts

    def finish(self) -> None:
        for subject_input, surfaces in self.surfaces.items():
            for surface, others in shared_invocations(surfaces).items():
                surfaces[surface]["shares_invocation_with"] = others
            path = os.path.join(self._directory(subject_input), SURFACES_FILE)
            self._claim(path)
            pathlib.Path(path).write_text(
                json.dumps(surfaces, indent=2, ensure_ascii=False,
                           sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
            self.written.append(path)


def recorded_extensions(subject_input: Input, surface: Surface) -> frozenset[str]:
    """The extensions `Recorder` writes `surface` under in `subject_input`'s
    directory — what `--force` may replace, decided by the manifest alone.

    The statement of what each kind's recording path writes, beside the
    writer: a `skip` row goes through `Recorder.skip` (`<surface>.skip`); a
    `run` row through `Recorder.record_row` with `surface.extension`, so the
    three streams and the file its `writes` names (`_record_surface`); a
    `tallies` row through `Recorder.record` with no extension, and a
    `matrix` row through `Recorder.record_raw` — the three streams alone,
    whatever their `writes`. And every surface of an input with `git` may be
    a `.skip`: `_record_everything` records each through `Recorder.skip`
    when that input's clone fails.
    """
    if surface.kind == "skip":
        known = {SKIP_EXTENSION}
    else:
        known = set(STREAM_EXTENSIONS)
        if surface.kind == "run" and surface.extension is not None:
            known.add(surface.extension)
    if subject_input.git:
        known.add(SKIP_EXTENSION)
    return frozenset(known)


def shared_invocations(entries: Mapping[str, Any]) -> dict[str, list[str]]:
    """`{surface: the other surfaces of this input recorded from the SAME
    argv}`, each list sorted, for the groups larger than one.

    Two rows of a manifest can price ONE invocation: a stdout surface and its
    `[stderr]` twin are a single command line run twice, so the pair reaches
    the goldens as two surfaces with identical bytes and, without this key,
    nothing recorded to say why — two copies of one run then read as two
    independent pieces of evidence. Naming the relation is the cheaper
    half of the choice: keeping both surfaces keeps a consumer's row ids in
    one-to-one correspondence with its goldens, and keeps the second run as a
    free determinism check, where collapsing them to one golden would drop
    both.

    DERIVED from what was recorded, never a list of row names: a surface that
    starts sharing an argv is named here with nobody editing a manifest, and
    one that STOPS sharing drops its key — which moves a golden, and is
    therefore a visible decision rather than a silent one.

    The recorded argv, so the comparison is over the argv a reader of
    `surfaces.json` sees: expanded, and folded through the census's `path`
    rows. Only `status == "captured"` entries take part — a `skipped` row
    recorded no run, and `_counts` is not a surface at all.
    """
    by_argv: dict[tuple[str, ...], list[str]] = {}
    for surface, entry in sorted(entries.items()):
        if not isinstance(entry, dict) or entry.get("status") != "captured":
            continue
        by_argv.setdefault(tuple(entry.get("argv", ())), []).append(surface)
    return {surface: [other for other in group if other != surface]
            for group in by_argv.values() if len(group) > 1
            for surface in group}


def read_capture(directory: str, what: str) -> dict[str, str]:
    """{relative path: text} for every file in a capture directory, or a
    refusal naming what the reader pointed at it.

    The READ side of what `Recorder` writes, and it lives beside it: the
    capture directory is the package's one data model — the golden IS the
    handoff — and three owners of one on-disk format is how a `surfaces.json`
    layout change turns `--force` into a refusal.

    A path that is not a directory REFUSES here, and `what` is the noun the
    sentence names it by: `--golden`, `--against`, the mutant's capture. It is
    one owner and not a guard at each call site, because a caller that forgot
    the guard got `{}` back — `os.walk` yields nothing for a path that is not
    a directory — and a comparison read `12 golden files, 0 new files` with
    every row `only-in-golden` and a `next:` line saying the change under test
    may not be behavior-neutral. A path golden-census cannot read a capture
    from is never an empty capture.
    """
    if not os.path.isdir(directory):
        raise Refusal(
            f"{what} names {directory}, which is not a directory. A path "
            "golden-census cannot read a capture from is not an empty "
            "capture: read as one it would report every recorded row as "
            "missing and call the subject changed.",
            next=f"Point {what} at a directory a capture wrote, or record one first with "
            "`capture --manifest M --out DIR`.")
    # Listed first, in its own words: the marker tests below read a listing
    # that fails as "no marker", and a directory golden-census cannot list
    # is not one that holds no capture.
    _listed(directory, functools.partial(_capture_unlistable, what=what))
    # The marker decides first: a directory that holds none — not even
    # behind a link — is no capture, whatever links it holds, and is refused
    # as that. Only in a capture is a link refused as a link.
    if (not is_capture_dir(directory, what)
            and not _marked_behind_link(directory, what)):
        # The same rule as the one above, one step further in: a directory
        # golden-census did not write a capture into is not an empty capture
        # either. Two empty folders read as `{}` and `{}` and compared
        # IDENTICAL at exit 0, so an agent that mistyped BOTH paths handed
        # back the word this tool exists to make trustworthy. A fresh capture
        # always carries the marker (`Recorder.finish`), so no passing run
        # changes.
        raise Refusal(
            f"{what} names {directory}, which holds no capture (no "
            "<input>/surfaces.json). A path golden-census cannot read a "
            "capture from is not an empty capture: read as one it would "
            "compare equal to any other nothing and call it IDENTICAL.",
            next=f"Point {what} at a directory a capture wrote, or record one first with "
            "`capture --manifest M --out DIR`.")
    _refuse_links(directory, what)
    files: dict[str, str] = {}
    unreadable: list[str] = []
    # `os.walk` skips a directory it cannot list unless told otherwise, and a
    # capture read without one of its inputs compared IDENTICAL over the rest.
    for dirpath, dirnames, filenames in os.walk(
            directory, onerror=functools.partial(_refuse_walk, what=what)):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            relative = os.path.relpath(path, directory)
            text, why = _capture_text(path)
            if text is None:
                unreadable.append(f"{relative} ({why})")
            else:
                files[relative] = text
    if unreadable:
        # ONE refusal and ONE sorted list, with each claim scoped to the kind
        # of entry it is true of. A file that is NOT TEXT was put there by
        # something else: every file a capture writes is UTF-8. A file that
        # could not be OPENED says nothing of the sort — a golden row whose
        # permissions were changed is exactly that — and a sentence telling
        # the reader to remove it destroys a committed golden.
        raise Refusal(
            f"{what} holds {len(unreadable)} file(s) golden-census cannot "
            "read. A file that is not text is not a row of this capture, "
            "because every file a capture writes is UTF-8 text. A file that "
            "cannot be read may be one golden-census wrote:\n    "
            + "\n    ".join(sorted(unreadable)),
            next="Remove each file named above as not text, and fix the "
            "permissions of each that cannot be read.")
    return files


def _refuse_walk(error: OSError, what: str) -> None:
    """`read_capture`'s walk met a directory it cannot list: the same refusal
    `is_capture_dir` gives one it cannot search. `what` is the flag that
    named the capture."""
    raise _entry_unsearchable(str(error.filename), error, what) from error


def _linked_entry(path: str, what: str, *, mid_run: bool = False) -> Refusal:
    """A symbolic link inside a capture directory: `Recorder` writes none. A
    linked directory is not entered by the walk, so its rows would count as
    absent; a linked file would be read through, so another file's bytes
    would stand for a row. `what` is the flag that named the capture.

    `mid_run` is a link `_swap_in` found after the rows ran: the guard of
    `--out` found none when the capture began, so the sentence says that and
    that the rows were recorded and not moved into place."""
    why_none = ("A capture golden-census wrote holds no link: read as part of "
                "it, a linked directory's rows would count as nothing and a "
                "linked file would stand in with another file's bytes, and "
                "either could read IDENTICAL.")
    if mid_run:
        return Refusal(
            f"{path} is a symbolic link that was not in {what} when the "
            "capture began; the rows were recorded and were not moved into "
            f"place. {why_none}",
            next="Remove the link, then capture again.")
    return Refusal(
        f"{what} names a capture holding {path}, which is a symbolic link. "
        f"{why_none}",
        next="Replace the link with what it points at, or point the command at the capture "
        "itself.")


def _refuse_links(directory: str, what: str, *, mid_run: bool = False) -> None:
    """Refuse the first symbolic link anywhere in the capture `directory`,
    top level first — the one rule for links, asked by `read_capture` of
    every capture it reads and by `guard_out_dir` of the whole of `--out`
    under `--force`. `os.walk` lists a link to a directory without entering
    it and hands over a link to a file to be read through: a capture read
    without one of its inputs, or with another file's bytes, compared
    IDENTICAL, so each refuses. A directory this walk cannot list is
    refused as unreadable (`_refuse_walk`, as in `read_capture`'s reading
    walk): a link inside it could not be seen, and under `--force --input`
    nothing else asks about an input the run does not select. `mid_run` is
    `_swap_in`'s asking, after the rows ran (`_linked_entry`)."""
    for dirpath, dirnames, filenames in os.walk(
            directory, onerror=functools.partial(_refuse_walk, what=what)):
        dirnames.sort()
        for name in dirnames + sorted(filenames):
            if os.path.islink(os.path.join(dirpath, name)):
                raise _linked_entry(os.path.join(dirpath, name), what,
                                    mid_run=mid_run)


def _marked_behind_link(directory: str, what: str) -> bool:
    """Whether an entry of `directory` holds an input's record through a
    link — the entry is a link, or its `surfaces.json` is — which
    `is_capture_dir`, asking with `lstat`, does not count. Such a directory
    is a capture with a link in it, refused as that, never as holding no
    capture; a link to anything else leaves a directory that holds no
    marker what it was. `what` is the flag that named the capture."""
    try:
        entries = os.listdir(directory)
    except OSError:
        return False
    for entry in entries:
        path = os.path.join(directory, entry)
        marker = os.path.join(path, SURFACES_FILE)
        linked = stat.S_ISLNK(_entry_mode(directory, path, what))
        if os.path.isfile(marker) and (linked or os.path.islink(marker)):
            return True
    return False


# ------------------------------------------------------- the contraband scan
#
# A zero result is not a clean result: the normalizer is not trusted, it is
# checked, over every byte the capture wrote.


def home_root_pattern(root: str) -> re.Pattern[str]:
    """One home root's pattern: the root with a home under it, or the root
    itself where the root IS somebody's home.

    One rule for every root, rather than a shape decided per root. `/home` is
    a directory of homes and `/root` is a home, and the machine a golden is
    compared on cannot be asked which is which — the alternation matches both
    and needs no bit saying which kind a root is.

    A home root counts only where a path can start (`core.PATH_START`):
    `src/home/page.tsx` is a relative path that happens to hold `/home`. An
    option word glued in front of the root — `-I/home/ci/include`,
    `-isystem/home/ci/include` — is CONSUMED by the pattern rather than
    looked behind, so its length does not matter, and the token a hit
    reports carries the option: it still names the line and the path. A
    match right after a token the text was folded with is a path under a
    folded directory, which `scan_text` sets aside through
    `core.after_placeholder`.
    """
    return re.compile(PATH_START + r"(?:-[A-Za-z]+)?" + re.escape(root)
                      + r"(?:/[^/\s\"']+|\b)")


#: The label a contraband hit carries for each directory a census `path` row
#: can fold, by the row's `source` (`core.PATH_SOURCES`): the scan names a
#: hit by the directory it found, and the refusal's `next:` reads the same
#: table to name the `path` row that folds it.
SOURCE_HITS = {
    "root": "the subject root's absolute path",
    "work": "golden-census's work directory",
    "clone": "a clone root",
    "fixed-width-dir": "the subject's fixed-width TMPDIR",
}


def contraband_patterns(roots: Roots,
                        clones: Iterable[str] = ()) -> list[tuple[str, re.Pattern[str]]]:
    """Everything a golden may never contain. The system temp base is on the
    list deliberately: it is NOT folded away as a root, so any temp path the
    normalizer failed to recognize — the subject's own included, and the bare
    root itself, spelled with or without its closing `/` — fails the capture
    loudly instead of being committed.

    Every home root of every platform is named, whichever platform this run is
    on: a golden travels, and a set captured on one platform and compared on
    another is judged by one rule or by two. `core.Platform` owns the roots,
    the running user's own home among them where neither platform's layout
    covers it.

    Each directory is searched in every spelling `core.path_forms` names —
    the spellings `core.fold` folds — because a command that resolved its
    root prints the resolved one, and a sibling of it that the fold leaves
    alone (`<root>-old`) is contraband in either spelling.
    """
    home = os.path.expanduser("~")
    patterns = [("an absolute home path", home_root_pattern(root))
                for root in Platform.every_home_root()]
    patterns += [(SOURCE_HITS["root"], re.compile(re.escape(form)))
                 for form in path_forms(roots.root)]
    patterns += [(SOURCE_HITS["work"], re.compile(re.escape(form)))
                 for form in path_forms(roots.work)]
    if home and home != "/":
        patterns.append(("the running user's home directory",
                         re.compile(re.escape(home))))
    for clone in {*clones, roots.clone or ""}:
        if clone:
            patterns += [(SOURCE_HITS["clone"], re.compile(re.escape(form)))
                         for form in path_forms(clone)]
    if roots.fixed:
        patterns += [(SOURCE_HITS["fixed-width-dir"],
                      re.compile(re.escape(form)))
                     for form in path_forms(roots.fixed)]
    for base in {os.environ.get("TMPDIR") or "", tempfile.gettempdir()}:
        base = base.rstrip("/")
        if not base:
            continue
        for form in path_forms(base):
            # A path under the root (`/` and a character), or the root
            # itself, with or without its closing `/`: what follows it must
            # not continue a name, so `/tmp/scratchpad` is not the root
            # `/tmp/scratch`, and a closing full stop is not a name either.
            patterns.append(("an unnormalized temp path",
                             re.compile(re.escape(form)
                                        + r"(?:/\S|/?(?![\w-]|\.\w))")))
    return patterns


class ScanResult(NamedTuple):
    """What one contraband scan actually did.

    `read` is files READ, not files handed in: a loop that swallowed
    `OSError` and moved on would print the number of files WRITTEN beside
    `0 hit(s)`, and a file the scan never opened looks exactly like a file
    with nothing in it. A zero result is not a clean result.
    """

    hits: list[tuple[str, int, str, str]]
    read: int
    unreadable: list[tuple[str, str]]


def scan_text(name: str, text: str, patterns: list[tuple[str, re.Pattern[str]]],
              tokens: Collection[str]) -> list[tuple[str, int, str, str]]:
    """Every contraband hit in one text, as `(name, line, label, token)`.

    The line loop, once. `scan_contraband` reads files and `probe` reads a
    subprocess's streams, and both have to answer the same question the same
    way: evidence is `file:line` — or `run 1 stdout:line` — with the token
    quoted, never a boolean. `name` is whatever the caller calls the text,
    because a path and a stream are not the same word.

    A pattern that opens with `core.PATH_START` matches only where a path can
    start, and a match right after one of `tokens` (`core.after_placeholder`)
    does not start one: `<REPO>/home/x` is a path under the subject root.
    `tokens` are the fold tokens the caller folded `text` with — its own
    vocabulary, so `<BR>/home/x` from a subject is a hit. A match that opens
    with a glued option (`<REPO>-I/home/x`) is a hit too: a path under a
    folded directory continues it with `/`. A hit whose span lies inside a
    longer hit's span on the same line is not reported: the longer spelling
    of one occurrence wins.

    Lines are `core.lines_of`'s, split at `\n` alone, the one splitter for
    the texts golden-census records and compares: `str.splitlines` also breaks
    at a bare `\r`, a form feed and a vertical tab, which gives every line
    after one of them another number.
    """
    hits: list[tuple[str, int, str, str]] = []
    for number, line in enumerate(lines_of(text), 1):
        spans: list[tuple[int, int, str, str]] = []
        for label, pattern in patterns:
            anchored = pattern.pattern.startswith(PATH_START)
            found = next((match for match in pattern.finditer(line)
                          if not (anchored
                                  and line.startswith("/", match.start())
                                  and after_placeholder(line, match.start(),
                                                        tokens))),
                         None)
            if found:
                spans.append((found.start(), found.end(), label,
                              found.group(0)))
        # One occurrence is one hit: where a spelling lies inside a longer
        # one on the same line (`/tmp/x` inside `/private/tmp/x`), only the
        # longer is reported.
        hits += [(name, number, label, token)
                 for start, end, label, token in spans
                 if not any(other[0] <= start and end <= other[1]
                            and other[:2] != (start, end) for other in spans)]
    return hits


def scan_contraband(paths: Iterable[str], roots: Roots,
                    tokens: Collection[str],
                    clones: Iterable[str] = ()) -> ScanResult:
    """Every file in `paths` read and scanned; `tokens` are the fold tokens
    the files were written with (`scan_text`). Each file is read with
    `newline=""`, its line endings as written, so a `\r` stays inside the
    line it ends, as `core._capture_text` reads it for `compare`."""
    patterns = contraband_patterns(roots, clones)
    hits: list[tuple[str, int, str, str]] = []
    unreadable: list[tuple[str, str]] = []
    read = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append((path, f"{type(exc).__name__}: {exc}"))
            continue
        read += 1
        hits += scan_text(path, text, patterns, tokens)
    return ScanResult(hits, read, unreadable)


def contraband_control(roots: Roots) -> tuple[bool, str]:
    """The positive control for the scan above: a planted home path under
    EVERY home root the patterns name must be found, so an empty hit list
    means clean and not 'the scan never ran'.

    The plant goes in a directory made under the temp root. When the root
    will not take one, the `OSError` is raised as it is.

    The temp root is planted in each of its three shapes.

    One token per home root, in each of the two shapes the rule matches — a
    home under the root, and the root itself — because a plant in one shape
    leaves the other a rule nothing has ever shown firing, and a root planted
    only where the running platform lays its homes out proves the pattern for
    the platform this run is on and nothing about the platform it is not.
    Every token is built by concatenation from the record's root, so this file
    carries no absolute home path of its own for the scan to find.
    """
    # `dir=temp_base()`, like every other scratch directory the package
    # makes: without it this one follows `tempfile.gettempdir()`, which caches
    # the temp root at first use and so ignores a TMPDIR set later in the same
    # process — and a directory that does not live where golden-census says
    # its directories live is one the log's fold cannot fold.
    holder = tempfile.TemporaryDirectory(prefix="golden-census-contraband-",
                                         dir=temp_base())
    with holder as tmp:
        planted = os.path.join(tmp, "planted.out")
        tokens = [shape for root in Platform.every_home_root()
                  for shape in (root + "/" + "someone" + "/Developer/x", root)]
        # The temp root in the three shapes the rule matches: under it, bare,
        # and bare with its closing `/`. The bound — a longer name that
        # begins with the root is no hit — is arm `llllllll`'s, not planted
        # here: a temp root inside another temp root makes that name a path
        # under the outer one, and a control that wants it clean would fail.
        base = temp_base().rstrip("/")
        temp_tokens = [base + "/" + "x", base, base + "/"] if base else []
        pathlib.Path(planted).write_text(
            "clean line\n" + "".join(
                f"{token}\n" for token in tokens + temp_tokens),
            encoding="utf-8")
        scan = scan_contraband([planted], roots, frozenset())
    # Every planted LINE caught and the clean line not: a hit count alone
    # cannot say that one root's token was found twice and another's not at
    # all, which is the half-covered pattern set this control exists to catch.
    lines = {number for _name, number, _label, _found in scan.hits}
    planted_count = len(tokens) + len(temp_tokens)
    ok = (lines == set(range(2, planted_count + 2))
          and scan.read == 1 and not scan.unreadable)
    if ok:
        name, number, _label, _found = scan.hits[0]
        return ok, (f"the scan found all {planted_count} absolute paths it "
                    f"planted in a scratch file (first: line {number} of "
                    f"{name})")
    return ok, (f"the scan found {len(lines)} of the {planted_count} absolute "
                f"paths it planted in a scratch file: {len(scan.hits)} hit(s), "
                f"{scan.read} file(s) read, {len(scan.unreadable)} unreadable")


# --------------------------------------------------------- the odd surfaces


def tail_newline_marker(tail: str) -> str:
    """`yes` when a recorded refusal tail ended in a newline.

    The two pairs `splitlines() or [""]` cannot tell apart are `"abc"` /
    `"abc\\n"` and `""` / `"\\n"`; this is the one word that separates them.
    """
    return "yes" if tail.endswith("\n") else "no"


def _common_prefix_to_line_break(texts: list[str]) -> str:
    prefix = os.path.commonprefix(texts)
    cut = prefix.rfind("\n")
    return prefix[:cut + 1] if cut >= 0 else ""


def _matrix_stream(name: str, tail: str) -> list[str]:
    """One stream of one matrix row, as the lines the record holds: a
    sub-heading naming the stream and its final newline, then the stream's
    lines indented four spaces.

    `lines_of` cannot tell "abc" from "abc\n", and `or [""]` cannot tell ""
    from "\n": a stream that gained or lost its final newline would move no
    golden byte. The fact is recorded on the sub-heading, where it is one word
    and cannot be missed. A stream that printed nothing is the sub-heading
    and one blank indented line, so the record says it was recorded and was
    empty.
    """
    return ([f"  {name} tail-newline={tail_newline_marker(tail)}"]
            + ["    " + line for line in lines_of(tail) or [""]])


def record_matrix(manifest: Manifest, subject_input: Input, surface: Surface,
                  recorder: Recorder, roots: Roots, env: dict[str, str],
                  out: Any, *, writes: str | None = None) -> int:
    """Every row of a matrix surface, recorded as ONE compacted record.

    The shared usage block is stored once, in `.err`; each row's record carries
    only what follows it. A row's standard output is recorded the same way:
    the lines every row printed first are stored once, under the header of
    `.out`, and each row carries only what follows them. A change to any of
    them is a diff — the compaction hides nothing, it just stops storing one
    usage block several hundred times. The layout is written once, in
    `docs/manifest-format.md` under `matrix`.

    Every row is a subprocess, so no row can depend on golden-census's own
    interpreter state, and the pinned environment reaches all of them the one
    way.

    `writes` is the surface's expanded `writes`, or None: `<WRITES>` is
    valued in the rows' arguments, and the path is cleared ONCE, before the
    pool starts its rows — never per row inside it. Nothing is recorded from
    it: the record is the rows' stdout and stderr.

    Each row is launched inside a window of its own, over a `Pending` of
    its own, and not through the surface's: the rows run at once, so one
    record would say `ran` of a row that never started because another had
    ended, and it holds the surface's argv, not the row's. A refusal over a
    row — one that would not start, or one whose output is not UTF-8 — is
    given the block of THAT row's expanded argv.
    """
    table = context(roots, writes)
    where = f"{manifest.path}: [surfaces.{surface.name}] rows"
    prefix_args = (subject_command(manifest, roots)
                   + [table.expand(arg, where)
                      for arg in subject_input.args])

    def one(row: Any) -> tuple[str, int, str, str]:
        argv = prefix_args + [table.expand(arg, where) for arg in row.args]
        pending = Pending(argv)
        pending.ran_as(argv, env)
        with describing(pending, manifest.census, roots.root, roots.fixed):
            proc = launch(argv, f"matrix row {row.label!r}", cwd=roots.root,
                          env=env, pending=pending)
        return row.label, proc.returncode, proc.stdout, proc.stderr

    if writes is not None:
        _clear_written(writes, row_key(subject_input.name, surface.name),
                       str(surface.writes), roots.work)
    workers = os.cpu_count() or 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(one, surface.rows))
    records.sort(key=lambda record: record[0])

    out_prefix = _common_prefix_to_line_break([record[2] for record in records])
    prefix = _common_prefix_to_line_break([record[3] for record in records])
    lines = [f"pairs: {len(records)}",
             f"usage-prefix-lines: {prefix.count(chr(10))}",
             f"stdout-prefix-lines: {out_prefix.count(chr(10))}"]
    lines.extend("    " + line for line in lines_of(out_prefix))
    lines.append("")
    for label, code, printed, err in records:
        lines.append(f"{label} exit={code}")
        lines.extend(_matrix_stream("stderr", err.removeprefix(prefix)))
        lines.extend(_matrix_stream("stdout", printed.removeprefix(out_prefix)))
    recorder.record_raw(subject_input.name, surface.name,
                        "\n".join(lines) + "\n", prefix, 0,
                        list(surface.record_argv or ()))
    out.write(f"    {surface.name}: {len(records)} rows as subprocesses\n")
    # The compaction's own exit, which is the 0 it was recorded under: a row's
    # exit code is inside the record, and there is no single one to hand back.
    return EXIT_OK


def _is_rule(line: str, rule: str) -> bool:
    return len(line) >= 8 and set(line) == {rule}


def record_tallies(text: str, rule: str, verdict: re.Pattern[str],
                   failing: re.Pattern[str] | None = None
                   ) -> list[tuple[str, str, tuple[str, ...]]]:
    """(banner, verdict line, failing lines) per fenced group, in the order
    printed.

    A group is a banner fenced by two rules of `rule`. The verdict is the first
    line matching `verdict` before the next banner; a group with none records
    `<no tally line>` and never disappears. The failing lines are every line of
    the same span that `failing` matches — from the line's start, as `verdict`
    is matched — exactly as printed and in print order; with no `failing` they
    are always `()`.

    The rule character and the verdict regular expression are the surface's,
    not golden-census's.

    ONE rule for a transcript's line endings: a line is what `lines_of`
    splits on `"\\n"`, and the rule lines, `verdict` and `failing` are asked
    of each line with ONE trailing `"\\r"` set aside — `$` does not match
    before a `\\r`, and a rule line is a rule line whichever ending the
    transcript used. What is RECORDED keeps its bytes: the banner and the
    verdict line are stripped as they always were, and a failing line is
    recorded exactly as printed, its `\\r` included.
    """
    lines = lines_of(text)
    bare = [line.removesuffix("\r") for line in lines]
    banners = [index for index in range(1, len(lines) - 1)
               if _is_rule(bare[index - 1], rule)
               and _is_rule(bare[index + 1], rule) and lines[index].strip()]
    groups: list[tuple[str, str, tuple[str, ...]]] = []
    for position, index in enumerate(banners):
        stop = banners[position + 1] - 1 if position + 1 < len(banners) \
            else len(lines)
        span = range(index + 2, stop)
        found = next((lines[at].strip() for at in span
                      if verdict.match(bare[at])), "<no tally line>")
        caught = (() if failing is None
                  else tuple(lines[at] for at in span
                             if failing.match(bare[at])))
        groups.append((lines[index].strip(), found, caught))
    return groups


def record_tallies_surface(manifest: Manifest, subject_input: Input,
                           surface: Surface, recorder: Recorder, roots: Roots,
                           env: dict[str, str], out: Any, *,
                           writes: str | None = None,
                           pending: Pending | None = None) -> int:
    """One run whose stdout is reduced to the verdict line of every group,
    and, with `failing`, the lines of each group that pattern matches.

    `.err` is recorded EMPTY: the reduction is of stdout, and the run's
    stderr is not a golden here, by declaration. The reduced text is recorded
    through `Recorder.record` under this row's own key, so the census's folds
    reach it as they reach a `run` row's stdout — the `path` folds, and every
    `regex` fold whose scope takes this row.

    `writes` is the surface's expanded `writes`, or None: `<WRITES>` is
    valued in the argv and the path is cleared before the run, as a `run`
    row's is, and nothing is recorded from it — it is handed to
    `run_subject` as no written path at all.

    `pending`, when handed in, is the record the caller's `attaching`
    window describes a refusal from: it is given the expanded argv, as
    `run.run_row` gives a `run` row's, and handed to `run_subject`, whose
    `launch` says when the subject ended.
    """
    failing = surface.failing
    argv = surface_argv(manifest, subject_input, surface, roots, writes)
    if pending is not None:
        pending.ran_as(subject_command(manifest, roots) + argv, env)
    if writes is not None:
        _clear_written(writes, row_key(subject_input.name, surface.name),
                       str(surface.writes), roots.work)
    result = run_subject(manifest, argv, roots, env, pending=pending)
    groups = record_tallies(result.out, surface.rule, surface.verdict,
                            failing)
    # Joined and then ended with one newline, so zero groups record
    # `groups: 0` and a blank line — the bytes every tallies golden without
    # a group already holds.
    body = (f"groups: {len(groups)}\n"
            + "\n".join(f"{banner}: {found}"
                        + "".join(f"\n{line}" for line in caught)
                        for banner, found, caught in groups)
            + "\n")
    recorder.record(subject_input.name, surface.name,
                    result._replace(out=body, err=""))
    # The count is printed only when `failing` is set: a pattern that reaches
    # nothing records the same golden as no pattern at all, and this line is
    # where the run says which it was.
    caught_count = ("" if failing is None else
                    f"{sum(len(caught) for _b, _f, caught in groups)} "
                    "failing line(s), ")
    out.write(f"    {surface.name}: {len(groups)} group tallies, "
              f"{caught_count}exit {result.exit}\n")
    return result.exit


# ---------------------------------------------------------------- the guard
#
# `--out` is replaced only when it holds a capture and `--force` says so, and
# then only what that capture records. Re-baselining a floor is a deliberate
# act and not the shortest command form, and a mistyped `--out` must not
# delete what it names. Both are refusals.


def _marked(directory: str, what: str) -> bool:
    """Whether `directory` holds the marker `Recorder.finish` leaves, or the
    unreadable-directory refusal when that cannot be asked: a directory that
    exists but cannot be searched (`0644`) is not a directory without a
    marker. Asked
    with `lstat`: `Recorder.finish` writes a regular file, so a link named
    `surfaces.json` is no marker, and its directory is not an input's
    record. `what` is the flag that named the capture."""
    try:
        return stat.S_ISREG(os.lstat(os.path.join(directory, SURFACES_FILE)).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as error:
        raise _entry_unsearchable(directory, error, what) from error


def is_capture_dir(directory: str, what: str) -> bool:
    """True when `directory` looks like something golden-census wrote: at least
    one `<input>/surfaces.json`, the marker `Recorder.finish` leaves. A
    directory that cannot be listed is not one; an entry that cannot be
    searched is refused, never read as having no marker — and EVERY entry is
    asked, never only as far as the first marker, because a caller that
    reads on (`read_capture`, the stranger check) would otherwise meet the
    unreadable one silently or in the wrong words. An entry that is a
    symbolic link is no marker, whatever it points at: `Recorder` writes
    directories, and what a link points at is not what golden-census
    wrote. Each entry is asked with `lstat`, so a directory that lists but
    cannot be searched (`0644`) is refused as unreadable rather than read
    as holding no marker. `what` is the flag that named the capture."""
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return False
    marked = False
    for entry in entries:
        path = os.path.join(directory, entry)
        if (stat.S_ISDIR(_entry_mode(directory, path, what))
                and _marked(path, what)):
            marked = True
    return marked


def _entry_mode(directory: str, path: str, what: str) -> int:
    """`lstat`'s mode for `path`, an entry of `directory`, or 0 when it is
    gone; an entry that cannot be asked about is the unreadable-directory
    refusal naming `directory` — the `isdir`/`islink` answer, False, would
    read a directory without search permission as holding no capture. `what`
    is the flag that named the capture."""
    try:
        return os.lstat(path).st_mode
    except FileNotFoundError:
        return 0
    except OSError as error:
        raise _entry_unsearchable(directory, error, what) from error


def _entry_unsearchable(directory: str, error: OSError, what: str) -> Refusal:
    """A directory inside a capture directory exists and cannot be read —
    searched (`0644`) or listed (`0311`): what part of a capture it holds
    is unknowable, for `--out`, `--golden` and `--against` alike, whether it
    is an input's directory or one further in. `what` is the flag that named
    the capture."""
    return Refusal(
        f"{what} names a capture holding {directory}, which cannot be read "
        f"({type(error).__name__}: {error.strerror}), so golden-census cannot "
        "tell what of a capture it holds. A directory it cannot read is not an empty one.",
        next="Check the permissions on that directory, then run the command again.")


def _out_unlistable(directory: str, error: OSError) -> Refusal:
    """`--out` cannot be listed: whether it holds a capture is unknowable."""
    return Refusal(
        f"{directory} cannot be listed ({type(error).__name__}: "
        f"{error.strerror}), so golden-census cannot tell whether it "
        "already holds a capture. A directory it cannot read is not an "
        "empty one.",
        next="Check the permissions on that directory, or point --out at a path that does "
        "not exist yet — `capture` creates it.")


def _capture_unlistable(directory: str, error: OSError, what: str) -> Refusal:
    """A directory a reader named as a capture (`--golden`, `--against`)
    cannot be listed: whether it holds one is unknowable. Its own sentence,
    beside `--out`'s, because the next step differs: `--out` may point at a
    path that does not exist yet, a capture to read may not."""
    return Refusal(
        f"{what} names {directory}, which cannot be listed "
        f"({type(error).__name__}: {error.strerror}), so golden-census cannot "
        "tell whether it holds a capture. A directory it cannot read is not "
        "an empty one.",
        next=f"Check the permissions on that directory, or point {what} at a directory a "
        "capture wrote.")


def _listed(directory: str,
            unlistable: Callable[[str, OSError], Refusal]) -> list[str]:
    """`directory`'s entries, sorted, or the caller's refusal that it cannot
    be listed. `is_capture_dir` catches the same `OSError` and answers False;
    here the listing IS the answer, so there is nothing to fall back to, and
    each caller owns the sentence for what the directory is to it."""
    try:
        return sorted(os.listdir(directory))
    except OSError as error:
        raise unlistable(directory, error) from error


def capture_strangers(out_dir: str, inputs: tuple[str, ...],
                      manifest: Manifest) -> list[str]:
    """Every entry under a capture directory that THIS manifest's capture
    does not record, as sorted paths relative to it — the one answer to
    "what in here would `--force` replace".

    The manifest alone decides, exactly: a directory named for one of its
    inputs, holding `surfaces.json`, and in it `<surface>.<ext>` for each
    surface that input records (`Manifest.surfaces_for`) with `ext` one of
    the extensions `recorded_extensions` says that row's kind is written
    under. Anything else — a file at the top, a directory of an input the
    manifest no longer has (named whole), a directory with no regular
    `surfaces.json`, a link, a subdirectory, `s.out~`, the files of a
    surface removed from the manifest, changed to or from a skip, or whose
    `writes` changed — is not what this capture records, and `--force`
    removes none of it; the reader deletes it once.

    With `inputs`, only those inputs' directories are asked about: they are
    the only ones `--force --input` replaces. Each `surfaces.json` must
    still parse as a capture's record, read through `_capture_text` one file
    at a time, so a stranger that is not text is named rather than refused
    by a reader of the whole directory; one that cannot be read or parsed is
    refused naming IT, because a directory whose record is broken is not a
    capture golden-census can vouch for.
    """
    names = list(inputs) if inputs else _listed(out_dir, _out_unlistable)
    strangers: list[str] = []
    for name in names:
        directory = os.path.join(out_dir, name)
        marker = os.path.join(directory, SURFACES_FILE)
        if not os.path.lexists(directory):
            continue
        subject_input = manifest.input_named(name)
        if (subject_input is None or os.path.islink(directory)
                or not os.path.isdir(directory)
                or not _marked(directory, "--out")):
            strangers.append(name)
            continue
        text, why = _capture_text(marker)
        recorded: Any = None
        if text is not None:
            try:
                recorded = json.loads(text)
            except ValueError as unparsable:
                why = f"not JSON: {unparsable}"
        if not isinstance(recorded, dict):
            raise Refusal(
                f"{marker} cannot be read as a capture's record "
                f"({why or 'not a JSON object'}), so golden-census cannot tell "
                "which files beside it this capture records, and --force "
                "removes nothing it cannot account for.",
                next="Restore that file from version control, or point --out at a path that does "
                "not exist yet — `capture` creates it.")
        known = {surface.name: recorded_extensions(subject_input, surface)
                 for surface in manifest.surfaces_for(subject_input)}
        for entry in _listed(directory, functools.partial(_entry_unsearchable,
                                                          what="--out")):
            if entry == SURFACES_FILE:
                continue
            path = os.path.join(directory, entry)
            stem, dot, extension = entry.rpartition(".")
            if (os.path.islink(path) or not os.path.isfile(path) or not dot
                    or extension not in known.get(stem, ())):
                strangers.append(os.path.join(name, entry))
    return sorted(strangers)


def _refuse_strangers(out_dir: str, inputs: tuple[str, ...],
                      manifest: Manifest) -> None:
    """The stranger refusal: `--force` replaces a CAPTURE, and a file the
    capture there does not account for is not part of one. Asked by the guard
    before anything runs, and again by `_swap_in` right before the swap, so a
    file that appeared in `--out` during the run is named rather than
    removed."""
    strangers = capture_strangers(out_dir, inputs, manifest)
    if strangers:
        # The message names what was found and does not say which files a
        # reader may have left behind. The files of a surface removed from
        # the manifest, changed to or from a skip, or whose `writes` changed,
        # and the directory of an input removed, are strangers by the same
        # rule (`capture_strangers` lists them), but a sentence naming them
        # as the likely cause is a guess about what this reader did, and the
        # list below it is the fact.
        raise Refusal(
            f"{out_dir} holds {len(strangers)} "
            f"entr{'y' if len(strangers) == 1 else 'ies'} this capture does "
            "not record, and --force replaces a capture, never a file beside "
            "it:\n    " + "\n    ".join(strangers),
            next="Move those files out of the capture directory, then re-run "
            "with --force: --force replaces what this capture records and "
            "removes nothing else.")


class OutGuard(NamedTuple):
    """What `guard_out_dir` let through: a one-line note on `--out` for the
    log, and whether `--out` held a capture the run replaces."""
    note: str
    replaces: bool


def guard_out_dir(out_dir: str, force: bool, inputs: tuple[str, ...],
                  manifest: Manifest) -> OutGuard:
    """What `capture` is allowed to do to `--out`. Returns the note for the
    log and whether a prior capture is replaced, or refuses with the
    reason."""
    # BEFORE the `lexists` test, because a link is the more specific fact:
    # `os.path.isdir` FOLLOWS a link, so a link to a directory reads as a
    # directory here, and the swap would then move the LINK aside and put a
    # directory in its place — replacing what the reader named and leaving
    # what it points at as it was.
    if os.path.islink(out_dir):
        try:
            target = os.readlink(out_dir)
        except OSError as unreadable:
            target = (f"(a link golden-census cannot read: "
                      f"{type(unreadable).__name__}: {unreadable.strerror})")
        raise Refusal(
            f"{out_dir} is a symbolic link to {target}. --out names the "
            "directory a capture is written into, and golden-census does not "
            "write through a link: --force replaces that directory whole, and "
            "what a link points at is not what you named.",
            next="Point --out at the directory itself, or at a path that does not exist "
            "yet — capture creates it.")
    # `lexists`, not `exists`: a dangling symlink is something that is there,
    # and `os.makedirs` raises on it exactly as it does on a file. Treating
    # every non-directory as "new directory" turns `--out <a file>` into an
    # uncaught FileExistsError traceback — crashing is never the appropriate
    # choice, and a refusal costs one sentence.
    if os.path.lexists(out_dir) and not os.path.isdir(out_dir):
        raise Refusal(
            f"{out_dir} exists and is not a directory. --out names the "
            "directory a capture is written into; golden-census will not "
            "remove, truncate or write through something it did not make.",
            next="Point --out at a new directory, or remove that file yourself.")
    if not os.path.isdir(out_dir):
        return OutGuard("new directory", False)
    # A plain listing: no name is special. A folder golden-census is asked to
    # capture into holds only what golden-census wrote, and a file nobody can
    # account for is named rather than stepped over on a guess about what made
    # it — `--force` replaces this folder, and a list of names to skip never
    # ends.
    entries = _listed(out_dir, _out_unlistable)
    if not entries:
        return OutGuard("empty directory", False)
    # The marker decides first, as in `read_capture`: a directory that holds
    # none, not even behind a link, is refused naming every entry.
    if (not is_capture_dir(out_dir, "--out")
            and not _marked_behind_link(out_dir, "--out")):
        raise Refusal(
            f"{out_dir} is not empty and holds no <input>/surfaces.json, so "
            "it is not a capture: golden-census does not remove or "
            "overwrite a directory it did not write. It holds "
            f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}:\n    "
            + "\n    ".join(entries),
            next="Remove the file(s) named above, or point --out at a path "
            "that does not exist yet — `capture` creates it.")
    # Any link in the whole of --out, whatever `--force` and `--input` say:
    # the next `compare` would refuse the golden a capture left beside it,
    # and a reader told to pass --force would only meet this refusal next.
    _refuse_links(out_dir, "--out")
    if not force:
        raise Refusal(
            f"{out_dir} already holds a capture ({len(entries)} "
            f"entr{'y' if len(entries) == 1 else 'ies'}); replacing it takes "
            "--force.",
            next="Re-run with --force to replace it, and attribute every moved row in the "
            "hand-back report.")
    # Named here, before anything runs, in the same shape as the no-marker
    # refusal above, rather than removed with the capture.
    _refuse_strangers(out_dir, inputs, manifest)
    if inputs:
        return OutGuard(f"replacing input(s) {', '.join(inputs)} of a prior "
                        "capture under --force", True)
    return OutGuard("replacing a prior capture under --force", True)


# -------------------------------------------------------------------- capture


#: The prefix of the directory a finished capture is copied into beside
#: `--out` before the swap: a dot, so no listing of a reader's tree shows it
#: by default, and `mkdtemp`'s, so it names a directory that did not exist.
STAGE_PREFIX = ".golden-census-capture-"


class _Stage:
    """One capture's directories and what has happened to them.

    `recorded` is where the rows are recorded — under the temp root, in a
    container `scratch` that `_capture_once` makes, so no subject ever
    sees anything new beside `--out`; the second capture of `--twice` hands
    its own. `path` is the directory beside `--out` that `_swap_in` makes at
    the END and copies `recorded` into, so the move into place is a rename
    within `--out`'s file system. `made` is the ledger of `--out`'s parents,
    and of `--out` itself under `--input`, taken back unless the swap ran.
    `swapped` says it ran. `hold` carries the one signal hold from the
    swap's renames through the removal of the stage: `_swap_in` enters it,
    `_unstage` releases it. Whether `path` holds the reader's previous
    capture is never carried here: `_unstage` reads it off the disk — a
    `retired/` that is not empty — when it cleans up.
    """

    def __init__(self, made: Made, recorded: str = "") -> None:
        self.scratch = ""
        self.recorded = recorded
        self.path = ""
        self.made = made
        self.swapped = False
        self.hold = contextlib.ExitStack()


def _say(out: Any, line: str) -> None:
    """One line of the capture log from a `finally`, where a closed standard
    output must not replace the exception already on its way out."""
    try:
        out.write(line)
    except (OSError, ValueError):
        pass


def _holds_previous(path: str) -> bool:
    """Whether the stage at `path` holds a previous golden: its `retired/`
    exists and is not empty. Read off the disk, every time."""
    retired = os.path.join(path, "retired")
    try:
        return os.path.isdir(retired) and bool(os.listdir(retired))
    except OSError:
        return True    # it cannot be read, so it cannot be shown empty


def _landing(out_dir: str, inputs: tuple[str, ...], replaces: bool) -> None:
    """The check that a capture can be landed in `--out`: a refusal when it
    cannot, and the file system left as it was found either way.

    `--out`'s missing parents are made in a `core.Made` ledger and a
    directory is made and removed beside `--out` — the pair under a signal
    hold, so no signal leaves it made — which is what the swap will need at
    the end; an `--out` that exists has to be writable (the swap moves it,
    or renames into it); and under `--force --input` (`replaces`) each input
    directory it will move has to be writable too. The ledger is taken back
    whatever the answer. Asked twice: by `guard_capture` before anything
    runs, where a capture that could not land is refused before it costs
    anything, and by `_staged` at run time, with the parents it keeps for
    the swap already made.
    """
    parent = os.path.dirname(os.path.abspath(out_dir))
    made = Made()
    unwritable = ""
    error: OSError | None = None
    try:
        try:
            made.makedirs(parent)
        except OSError as failed:
            unwritable, error = failed.filename or parent, failed
        if error is None:
            try:
                with signals_held():
                    os.rmdir(tempfile.mkdtemp(prefix=STAGE_PREFIX, dir=parent))
            except OSError as failed:
                # `mkdtemp`'s own attempt is a random name; the directory it
                # could not write in is the parent.
                unwritable, error = parent, failed
        moved = [out_dir] if os.path.isdir(out_dir) else []
        if replaces:
            moved += [os.path.join(out_dir, name) for name in inputs
                      if os.path.isdir(os.path.join(out_dir, name))]
        for directory in moved:
            if error is None and not os.access(directory, os.W_OK):
                unwritable, error = directory, PermissionError(13, "Permission denied")
    finally:
        made.undo()
    if error is not None:
        raise Refusal(
            f"--out {out_dir} cannot be recorded into: golden-census moves a "
            "finished capture into place from a new directory beside --out, "
            f"and it cannot write {unwritable} ({type(error).__name__}: "
            f"{error.strerror}). No row of the capture ran.",
            next="Make that directory writable, or point --out at a path whose parent you can "
            "write.") from error


@contextlib.contextmanager
def _staged(out_dir: str, out: Any, inputs: tuple[str, ...],
            replaces: bool) -> Iterator[_Stage]:
    """One capture's directories, from the check that `--out` can be landed
    in to their removal on every exit (`_unstage`).

    The check is `_landing`'s, asked again here at run time — `guard_capture`
    asked it before anything ran — and it comes FIRST, before the workspace,
    the preconditions and the version run, with `--out`'s missing parents
    made into the stage's own `core.Made` ledger ahead of it, so they stay
    made for the swap. Anything that stops the check takes back the parents
    it made.
    """
    made = Made()
    try:
        # A parent that cannot be made is met again by `_landing`, which
        # names it.
        with contextlib.suppress(OSError):
            made.makedirs(os.path.dirname(os.path.abspath(out_dir)))
        _landing(out_dir, inputs, replaces)
    except BaseException:
        made.undo()
        raise
    stage = _Stage(made)
    refused: Refusal | None = None
    try:
        yield stage
    except Refusal as refusal:
        refused = refusal
        raise
    finally:
        _unstage(stage, out, refused)


def _unstage(stage: _Stage, out: Any, refused: Refusal | None) -> None:
    """Remove every directory `stage` made, and say what could not be.

    The temp-root recording goes first, when it is still there: with no
    hold when the swap never reached its renames — nothing beside `--out`
    depends on it; once they ran, `_swap_in` has removed it after the copy,
    and only what that removal left goes here, inside the swap's hold. The
    stage beside `--out` goes in ONE `rmtree` under the signal hold
    `_swap_in` took before its renames (or one taken here when they never
    ran), released only after it, so no signal lands between a replaced
    `--out` and the removal of what it replaced.
    What the stage holds is read off the disk: when the swap did not run
    and its `retired/` still holds the previous golden, it is kept and
    named as holding it; after a swap, what is left of a `retired/` is the
    REPLACED golden, and is named as that. A directory of the stage that
    stayed is handed to `core.left_behind`, ahead of those lines. Nothing is
    written inside the hold: the lines, and the undo of `--out`'s parents
    when the swap did not run, come after it.

    A signal the hold deferred is delivered when it ends, and its exception
    then replaces the one on its way out — a refusal the reader has not
    seen. So when anything escapes the cleanup while `refused` was leaving,
    that refusal is written here, after the lines; otherwise it is left to
    the caller that prints every refusal, and nothing is printed twice.
    """
    left: list[str] = []
    notes: list[str] = []
    escaped = True
    try:
        try:
            if stage.scratch and os.path.lexists(stage.scratch):
                shutil.rmtree(stage.scratch, ignore_errors=True)
                if os.path.lexists(stage.scratch):
                    left.append(stage.scratch)
        finally:
            with stage.hold:
                stage.hold.enter_context(signals_held())
                if stage.path:
                    if stage.swapped or not _holds_previous(stage.path):
                        shutil.rmtree(stage.path, ignore_errors=True)
                    if not os.path.lexists(stage.path):
                        pass                                    # removed whole
                    elif stage.swapped and _holds_previous(stage.path):
                        notes.append(f"  a staging directory could not be fully "
                                     f"removed: {stage.path} — what is left in it "
                                     "is the REPLACED golden, not a whole one\n")
                    elif _holds_previous(stage.path):
                        notes.append(f"  a staging directory was kept: {stage.path} "
                                     "— the previous golden is under its retired/\n")
                    else:
                        left.append(stage.path)
        escaped = False
    finally:
        if not stage.swapped:
            stage.made.undo()
        for path in left:
            left_behind(path, out)
        for note in notes:
            _say(out, note)
        if escaped and refused is not None:
            _say(out, refusal_text(refused) + "\n")


def _put_back(done: list[tuple[str, str, str]]) -> tuple[list[str], list[str]]:
    """Reverse every move of `done` that took place, newest first, and say
    `(paths now holding the new capture, places a prior capture is stranded
    at)`. Each move was written down before its rename, so whether it
    happened is read off the disk: a retirement happened when the retired
    copy exists; a placement happened when the new capture has left the
    stage (its destination may hold a reader's files otherwise)."""
    now_new: list[str] = []
    stranded: list[str] = []
    for kind, moved_to, moved_from in reversed(done):
        happened = (os.path.lexists(moved_to) if kind == "retired"
                    else not os.path.lexists(moved_from))
        if not happened:
            continue
        try:
            os.rename(moved_to, moved_from)
        except OSError:
            (now_new if kind == "placed" else stranded).append(moved_to)
    return now_new, stranded


def _swap_in(stage: _Stage, out_dir: str, inputs: tuple[str, ...],
             manifest: Manifest, replaces: bool) -> None:
    """Move the recorded capture into place: all of `--out`, or with `inputs`
    each named input's directory, whole.

    It is copied into a new directory beside `--out` first, so each move is a
    rename within one file system, and the temp-root recording is removed
    once copied. When `--out` held a prior capture (`replaces`), it must
    still be there and the stranger check runs again, just before the
    renames, so a file that appeared in `--out` during the run — or during
    the copy — is refused rather than replaced; then each target is renamed
    into the stage's `retired/` — as `retired/0` for the whole of `--out`,
    `retired/<input>` for an input — and the new one renamed in after it:
    the reader's old capture replaced, never edited. Otherwise nothing is
    moved aside: a plain rename into a path that is no longer new or empty
    fails, and that is the refusal.

    The renames, their put-back and the refusal they lead to run under the
    signal hold `stage.hold` carries, which `_unstage` releases only after
    the stage is removed: a signal is delivered when all of it is done,
    never between two renames nor between the swap and the cleanup. Each
    move is written down before its rename, and anything that still stops
    the swap — an `OSError` — puts back every move that took place
    (`_put_back`), then refuses naming the input that failed, each path that
    now holds the new capture and each place a prior capture could not be
    put back from; any other exception is raised again.
    """
    done: list[tuple[str, str, str]] = []
    now_new: list[str] = []
    stranded: list[str] = []
    target, failing = out_dir, "--out"
    try:
        # Held until the path is recorded, so no signal leaves a stage
        # nobody will remove.
        with signals_held():
            stage.path = tempfile.mkdtemp(prefix=STAGE_PREFIX,
                                          dir=os.path.dirname(os.path.abspath(out_dir)))
        copy = os.path.join(stage.path, "capture")
        shutil.copytree(stage.recorded, copy)
        if stage.scratch:
            # Copied, so no longer needed — and removed here, outside the
            # hold below, which covers the renames and the stage alone.
            shutil.rmtree(stage.scratch, ignore_errors=True)
        retired = os.path.join(stage.path, "retired")
        os.makedirs(retired)
        if replaces:
            if not os.path.isdir(out_dir):
                raise Refusal(
                    f"--out {out_dir} held a prior capture when this capture began "
                    "and is gone now, so there is nothing to replace, and "
                    "golden-census does not guess where the new capture belongs.",
                    next="Find out what removed --out during the run, then capture again; the "
                    "rows recorded here were not moved into place.")
            # A link or a stranger that appeared during the run — or the
            # copy — is refused as the guard would have refused it.
            _refuse_links(out_dir, "--out", mid_run=True)
            _refuse_strangers(out_dir, inputs, manifest)
        if inputs:
            stage.made.makedirs(out_dir)
        moves = ([(name, os.path.join(copy, name), os.path.join(out_dir, name))
                  for name in inputs] if inputs else [("0", copy, out_dir)])
        stage.hold.enter_context(signals_held())
        try:
            for name, new, target in moves:
                failing = f"input {name}" if inputs else "--out"
                if replaces and os.path.lexists(target):
                    old = os.path.join(retired, name)
                    done.append(("retired", old, target))
                    os.rename(target, old)
                done.append(("placed", target, new))
                os.rename(new, target)
            # Still inside the hold: a signal waiting on it is delivered
            # when it ends, and must find the swap already done.
            stage.swapped = True
        except BaseException:
            now_new, stranded = _put_back(done)
            raise
    except OSError as failed:
        said = (f"the new capture could not be moved into place at {target} "
                f"({failing}; {type(failed).__name__}: {failed.strerror or failed})")
        if not now_new and not stranded:
            said += ", so nothing was replaced."
            try:
                held = sorted(os.listdir(target)) if not replaces else []
            except OSError:
                held = []
            if held:
                # A path that was new or empty when the guard looked, and is
                # neither now: what is there is what the reader needs.
                said += (f" {target} is no longer new or empty: it holds "
                         + ", ".join(held) + ".")
                raise Refusal(
                    said,
                    next="Move what is there out of --out, or point --out at a path that "
                    "does not exist yet, and capture again.") from failed
        else:
            said += "."
            if now_new:
                said += " These now hold the new capture: " + ", ".join(now_new) + "."
            if stranded:
                said += (" The prior capture could not be put back and is at: "
                         + ", ".join(stranded) + " — golden-census has left it there"
                         + (" (each named after its input)." if inputs else "."))
        raise Refusal(
            said,
            next="Make --out and the directory it is in writable, on one file system, and "
            "capture again.") from failed


class Guarded(NamedTuple):
    """What `guard_capture` let through: the inputs a capture records, each
    name once; the guard's one-line note on `--out` for the log; and whether
    this capture REPLACES one — `--out` held a capture when the command
    started, so the guard let it through under `--force`. Decided once, from
    what stood there then: a capture the subject puts into `--out` during
    the census's controls is not replaced — the rename into a path that is
    no longer new or empty fails, and that is the refusal (`_swap_in`)."""
    inputs: tuple[str, ...]
    note: str
    replaces: bool


def guard_capture(manifest: Manifest, out_dir: str, inputs: tuple[str, ...],
                  force: bool) -> Guarded:
    """Every check `capture` makes of its `--input` names and its `--out`
    before anything runs, in that order: the names are asked of the manifest
    first because the guard of `--out` reads them; then `guard_out_dir`;
    then `_landing`, that a capture can be landed in `--out`. Needs the
    manifest and the file system and nothing else, so `cli.main` calls it
    above the census's controls for the `capture` command and hands
    `capture` what it returns; `capture` calls it itself when it is handed
    nothing.
    """
    # A name given twice is one input: `_swap_in` moves each named input's
    # directory once, and a second move of the same name would find the new
    # capture already in place and retire it.
    inputs = tuple(dict.fromkeys(inputs))
    for name in inputs:
        if manifest.input_named(name) is None:
            raise Refusal(f"--input {name!r} names no [inputs.<name>] table",
                          next="Spell --input with one of the [inputs.<name>] table names in that "
                          "manifest, or drop the flag to record every input.")
    note, replaces = guard_out_dir(out_dir, force, inputs, manifest)
    _landing(out_dir, inputs, replaces)
    return Guarded(inputs, note, replaces)


def _to_null_if_real(stream: Any) -> None:
    """Point `stream` at the null device where it has a descriptor — a real
    pipe — and leave a stream in memory, which has none to redirect."""
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return
    to_null(descriptor)


def capture(manifest: Manifest, out_dir: str, out: Any,
            inputs: tuple[str, ...] = (), force: bool = False,
            twice: bool = False, *, landed_note: bool = False,
            guarded: Guarded | None = None) -> int:
    """Record every row of `manifest`. Returns a process exit code.

    The rows are recorded under the temp root and moved into place by
    `_swap_in` as the LAST thing this function does — after every row, the
    contraband scan and its control, and `--twice`'s agreement — and
    `capture complete` is printed only after it. What is promised: a refusal,
    a non-zero code or a raise before the swap leaves `--out` byte for byte
    as it was; a swap that fails puts `--out` back, and where it cannot, the
    refusal names every path that now holds the new capture and where the
    old one is. With `landed_note` — passed by the `capture` command alone,
    whose reader named `--out` — anything that stops it after the swap says
    on stderr that `--out` holds the new capture; `compare` and `mutants`
    capture into a directory of their own that no reader named, and say
    nothing of it.

    `--twice` records the whole set a second time into a scratch directory and
    REFUSES naming the first differing row and its first differing line: two
    captures of an unchanged subject must be byte-identical before a manifest
    counts as complete.

    The second capture goes into a directory golden-census MAKES, under the
    temp root and beside the two `core.workspace` makes, rather than into a
    `<out>.twice` beside the reader's `--out`. A path derived from the
    reader's is a path golden-census does not own: the guard refused a
    `<out>.twice` that carried a stranger's file and the `finally` removed it
    anyway, `--force` replaced one that held a capture and then removed that,
    and no spelling of the removal fixes a directory that should never have
    been chosen. Made here, it is removed here. The directory beside `--out`
    the swap uses is `mkdtemp`'s too — a name that did not exist — so it can
    never hold a reader's file either.

    `guarded` is what `guard_capture` returned for this `out_dir`, these
    `inputs` and this `force`, when the caller asked it before starting
    anything; `None` asks it here. It is asked once either way, and whether
    this capture replaces one is its answer, not the disk's after the runs.
    """
    # Before the clone and before the first run: a refusal costs nothing here
    # and everything after ten minutes of capturing.
    inputs, out_note, replaces = (guarded if guarded is not None
                                  else guard_capture(manifest, out_dir, inputs, force))
    stage: _Stage | None = None
    try:
        with _staged(out_dir, out, inputs, replaces) as stage:
            code = _capture_once(manifest, out_dir, stage, out, inputs, out_note)
            if code != 0:
                return code
            if twice:
                second = _Stage(Made())
                try:
                    # Held until the path is recorded, inside the `try` whose
                    # `finally` removes it.
                    with signals_held():
                        second.recorded = tempfile.mkdtemp(prefix="golden-census-twice-",
                                                           dir=temp_base())
                    out.write(own_log(f"\n  --twice: a second capture into "
                                      f"{second.recorded}\n", manifest.census,
                                      manifest.subject.root))
                    # `force=False`: the directory is fresh and empty, so the
                    # guard's own rule holds honestly. Passing True told it to
                    # adopt a directory that never needed adopting.
                    code = _capture_once(
                        manifest, second.recorded, second, out, inputs,
                        guard_out_dir(second.recorded, False, inputs,
                                      manifest).note)
                    if code != 0:
                        return code
                    # Both read whole: this run recorded both, from the same
                    # inputs, so each holds exactly the rows asked twice.
                    first = read_capture(stage.recorded, "--twice's first capture")
                    again = read_capture(second.recorded, "--twice's second capture")
                    _refuse_on_drift(first, again)
                    out.write(f"  --twice: {len(first)} files, byte-identical\n")
                finally:
                    if second.recorded:
                        removed(second.recorded, out)
            _swap_in(stage, out_dir, inputs, manifest, replaces)
        # The one line written after the swap, so the one write that can meet a
        # reader who stopped a line early, or a standard output that refuses
        # the write, with the new capture already in place: the work landed,
        # and that reader is told so where they are looking.
        try:
            out.write("  capture complete\n")
        except OSError as error:
            if not landed_note:
                # `compare` and `mutants` capture into a directory no reader
                # named and have a verdict still to write: their caller's
                # refusal for a standard output that failed stands.
                raise
            _to_null_if_real(out)
            # A reader who stopped reading chose to: the capture is done and
            # exits 0. A write refused is a fault of where the output went: a
            # refusal at exit 2, which still says the capture landed.
            closed = isinstance(error, BrokenPipeError)
            said = (to_stderr("standard output closed as the capture completed: "
                              "--out holds the new capture.") if closed
                    else refuse_on_stderr(Refusal(
                        f"standard output refused a write ({error}) as the capture "
                        "completed, so its last line is missing or cut short; --out holds the "
                        "new capture.",
                        next="Nothing needs capturing again. Send the next "
                             "command's output to a file that can be written, "
                             "and read the file.")))
            # `2>&1` closed stderr with it: the line has nowhere to go, and
            # stderr's descriptor — when it has one — is pointed at the null
            # device too, so the interpreter's flush at exit cannot fail.
            if not said:
                _to_null_if_real(sys.stderr)
            if not closed:
                return EXIT_REFUSED
    except BaseException:
        # Anything that stops this function after the swap — a signal the
        # hold deferred, delivered as the stage is removed, or one while the
        # last line is written — ends it with no `capture complete`, and a
        # reader cannot otherwise tell a stop before the swap from one after.
        if landed_note and stage is not None and stage.swapped:
            to_stderr("interrupted after the capture landed: --out holds the new capture.")
        raise
    return EXIT_OK


#: How much of a differing line the `--twice` refusal prints. A display
#: width, and this refusal's own: `probe`'s clause 2 shows `core.DIFFERENCE`
#: behind eleven spaces, and unifying the two would be a change to what both
#: blocks look like rather than to where the rule lives.
DRIFT = 160


def _refuse_on_drift(first: dict[str, str], second: dict[str, str]) -> None:
    for path in sorted(set(first) | set(second)):
        left, right = first.get(path), second.get(path)
        if left == right:
            continue
        if left is None or right is None:
            raise Refusal(
                f"two captures of one subject differ: {path} exists in only "
                "one of them. A row golden-census records only sometimes is not "
                "a golden.",
                next="Run `census --manifest M` and read its `census state` "
                "block: something around the subject decides whether that "
                "row is recorded, and no census row names it yet.")
        # The RULE is `core.first_difference`, shared with `probe`'s clause
        # 2 and `compare`'s `[DIFF]` detail; this is only the LAYOUT, which is
        # four spaces and `DRIFT` here and eleven and `core.DIFFERENCE` there.
        # `absent` is what a line the shorter capture does not have is called:
        # a row that gained or lost a line is what this refusal is about, so
        # the pair is reported rather than skipped.
        #
        # The texts are known to differ by the time this runs. Two texts with
        # the same `lines_of` and the same final newline are the same bytes,
        # so a `None` back cannot come from a real difference: it would be a
        # fault of `first_difference` itself. It is still refused rather than
        # passed — falling through the loop instead is how a guard whose
        # whole job is to refuse a drift printed `byte-identical` over one.
        moved = first_difference(left, right, DRIFT, absent="(absent)")
        if moved is None:
            where = ("in bytes no line carries; golden-census could not "
                     "name the line. Report this as a golden-census defect.")
        elif moved.line is not None:
            where = (f"line {moved.line}\n    first:  {moved.first!r}\n"
                     f"    second: {moved.second!r}")
        else:
            where = moved.said()
        raise Refusal(
            f"two captures of one subject differ: {path} {where}\n  "
            "Something around the subject moves and no census row folds or "
            "pins it.",
            next="Add the census row that pins or folds what moved, then "
            "capture again; the `census state` block of `census --manifest M` "
            "usually names it.")


def _capture_once(manifest: Manifest, out_dir: str, stage: _Stage, out: Any,
                  inputs: tuple[str, ...], out_note: str) -> int:
    """One whole capture into `stage.recorded`, inside one `run.place` and the
    `core.workspace` it enters: the fixed-width directory made first — so a
    temp root too wide for the census's pin refuses without having created
    anything at all — the work directory under the temp root, and both
    removed in `finally`. One decision in one place, rather than that
    lifecycle transcribed at every site that needs it. `out_dir` is what the
    log names: the directory the reader asked for, which the recording is
    moved into only when the caller has seen it succeed."""
    census = manifest.census
    base_tmp = temp_base()
    wanted = set(inputs)
    running = [row for row in manifest.inputs
               if not wanted or row.name in wanted]

    def fold_with(fixed: str | None) -> Callable[[str], str]:
        """`fold` over the place's fixed-width directory `fixed`."""
        def fold(text: str) -> str:
            """This command's own log, through the census's `path` rows."""
            return own_log(text, census, manifest.subject.root, fixed)
        return fold

    def opened(roots: Roots) -> None:
        """The header: once the place's directories exist, before the
        preconditions."""
        fold = fold_with(roots.fixed)
        out.write(fold(f"capture -> {out_dir}  [{out_note}]\n"))
        out.write(fold(f"  subject: {manifest.subject.name} at "
                       f"{manifest.subject.root}\n"))
        if roots.fixed is not None:
            out.write(f"  subject TMPDIR: {len(roots.fixed)} characters "
                      f"(pinned at {census.fixed_width})\n")
        for note in census.notes:
            out.write(f"  census note: {note}\n")

    # The fixed-width directory the outermost window folds, once there is one.
    fixed: str | None = None

    def built(roots: Roots, env: dict[str, str]) -> None:
        """The state block, the subject's `version` and the staging
        directory: once the environment is built, before the `[files]`."""
        # From here the capture's own block shows the environment as built,
        # folded as a row's is: a refusal through the outermost window — the
        # `[files]` a file system will not write — comes after `run.place`
        # built it.
        nonlocal fixed
        capturing.env, fixed = env, roots.fixed
        state(census, roots, env, out)
        if manifest.subject.version:
            table = context(roots)
            pending = Pending(tuple(manifest.subject.command)
                              + manifest.subject.version)
            pending.env = env
            with describing(pending, census, manifest.subject.root, roots.fixed):
                argv = [table.expand(arg, f"{manifest.path}: [subject] version")
                        for arg in manifest.subject.version]
                pending.ran_as(subject_command(manifest, roots) + argv, env)
                version = run_subject(manifest, argv, roots, env,
                                      pending=pending)
            out.write(f"  subject version: {version.out.strip()[:DIFFERENCE]!r} "
                      f"(exit {version.exit})\n")

        # Made HERE, after this command's first line and under the temp root: the
        # workspace's two directories are the only ones present when the first
        # line is written, and nothing beside `--out` exists while a subject runs.
        if not stage.recorded:
            # Held until the path is on the stage, where `_unstage` finds it.
            with signals_held():
                stage.scratch = tempfile.mkdtemp(prefix="golden-census-capture-",
                                                 dir=base_tmp)
            stage.recorded = os.path.join(stage.scratch, "capture")

    # The widest window, and the outermost: `workspace` makes the fixed-width
    # directory, and a temp root too wide for the census's pin refuses there —
    # before a run has directories to expand a placeholder against or an
    # environment to build. The block says both halves are missing rather than
    # leaving them out, and prints the command as the manifest spells it,
    # which is the one part that exists; `built` gives it the environment and
    # the fixed-width directory the moment there are both. A refusal from
    # inside `_record_everything` has already been given a narrower
    # description and keeps it.
    capturing = Pending(manifest.subject.command)
    # `fixed` is bound later, inside `built`, so `describing` cannot take it at
    # entry and the window stays a lambda that reads it when a refusal asks.
    with attaching(lambda: about_to_run(capturing, census,
                                        manifest.subject.root, fixed)), \
            place(manifest, "golden-census-", out,
                  rows=[(row, surface) for row in running
                        for surface in manifest.surfaces_for(row)],
                  opened=opened, built=built) as where:
        code = _record_everything(manifest, stage, out, running, where,
                                  fold_with(where.roots.fixed), capturing)
        # The rows have ended. A refusal from here on — `run.place`'s,
        # over a clone they left not clean — interrupted no run: the
        # block under it opens `ran:` over the last row that ran, which
        # `_record_everything` gave it, and never `about to run` over a run
        # that was not made. Where no row ran, it opens over the subject's
        # command alone.
        if not capturing.ran:
            capturing.ran_as(subject_command(manifest, where.roots))
            capturing.child_ended()
        return code


def _record_everything(manifest: Manifest, stage: _Stage, out: Any,
                       running: list[Input], where: Place,
                       fold: Callable[[str], str], capturing: Pending) -> int:
    """Every row, into `stage.recorded`. The `core.workspace` that `run.place`
    enters owns the two scratch directories `where.roots` names; the
    recording's is removed by `capture._staged` for the first capture and by
    `capture` itself for `--twice`'s second.

    `capturing` is the capture's outermost description of a run. It says the
    subject ran from the first input whose rows ran: a refusal at the next
    input's clone — the cache directory's — is over a capture that has
    already run a subject, and a block reading `about to run` would be false
    of it."""
    census = manifest.census
    roots = where.roots
    recorder = Recorder(stage.recorded, roots, census)
    # Every row through `recorder`, then the contraband scan; a refusal out of
    # here leaves `--out` alone, because nothing was recorded there.
    for subject_input in running:
        out.write(f"  input {subject_input.name}\n")
        entered = where.enter(subject_input)
        recorder.roots = entered.roots
        if entered.unavailable is not None:
            for surface in manifest.surfaces_for(subject_input):
                # The constant to DISK and the reason to the LOG: what the
                # clone failure said is a fact about this machine, and every
                # line that carries it is a line nobody commits.
                recorder.skip(subject_input.name, surface.name,
                              ENVIRONMENTAL_SKIP,
                              logged=f"{ENVIRONMENTAL_SKIP}: "
                                     f"{entered.unavailable}")
            # ONE shape for one meaning, from its one producer
            # `core.skip_line`, which the self-check and every per-surface
            # SKIP use: `[SKIP]  <what>: <why>`. An agent matching the
            # bracketed form used to read a whole input that was never
            # captured as a clean run.
            out.write(skip_line(f"{subject_input.name}: "
                                f"{entered.unavailable}") + "\n")
            continue
        last = _record_input(manifest, subject_input, recorder, out, where,
                             fold)
        if last is not None:
            # A surface whose own record was never given an argv — a matrix,
            # whose rows each carry a record of their own — has no row to
            # name: the subject's command alone is what ran.
            capturing.ran_as(last.argv if last.expanded
                             else subject_command(manifest, where.roots))
            capturing.child_ended()

    recorder.roots = roots
    recorder.finish()
    return _scan(recorder, roots, where.clones, stage.recorded, out, fold)


#: What a surface that recorded nothing is said to be, under its own row.
#:
#: Such a row is three files holding an exit code and two empty streams, and a
#: comparison of it passes against any other capture that records nothing —
#: including one taken from a subject that no longer produces the surface at
#: all. The capture is not refused: recording nothing is a fact about the
#: subject and a legitimate golden. It is disclosed, once, where the reader
#: cannot take the row for a recording.
SILENT_SURFACE = ("      records nothing: both streams are empty and no file "
                  "is written, so a comparison of this row passes against "
                  "any capture that also records nothing\n")

#: What a surface with a `counter` is said to be, under its own row, when
#: its run wrote no file: the counter is handed the written file, so it did
#: not run, no `counts` line follows and no `_counts` is recorded. Said
#: because the row would otherwise read as one with no counter at all.
UNCOUNTED = ("      counter not run: the run wrote no file for it to count, "
             "so no counts are recorded for this row; read the row's "
             ".exit and .err for why\n")

#: What an input whose every surface failed is said to be, after its rows.
#:
#: Each exit code is already on its own row, and a reader who looks at every
#: one of them learns this; the line exists because a reader who looks at the
#: tally does not. A golden records a failing subject as faithfully as a
#: working one, so this is never a refusal — but a whole input failing is
#: usually the fixture and not the subject, and that is worth one line.
FAILING_INPUT = ("    every surface of this input exits non-zero — the rows "
                 "above record a subject that is failing\n")


def _record_input(manifest: Manifest, subject_input: Input, recorder: Recorder,
                  out: Any, where: Place,
                  fold: Callable[[str], str]) -> Pending | None:
    """Every surface of one input, recorded; the record of the last surface
    that ran, or None when none did."""
    roots = recorder.roots
    #: Every surface of this input that RAN, by the code it exited with. A
    #: `skip` surface is absent because nothing ran to exit anything, which is
    #: why an input of nothing but skips earns no line below.
    exits: list[int] = []
    last: Pending | None = None
    for surface in manifest.surfaces_for(subject_input):
        if surface.kind == "skip":
            recorder.skip(subject_input.name, surface.name,
                          surface.reason or "(no reason)")
            continue
        # The window every refusal raised while this surface's run is being
        # built travels through. The argv opens as the manifest spells it and
        # is replaced by the expanded one the moment there is one, so a
        # `<WRITES>` with no value, an `env` the census pins, or a subject
        # that would not launch each say what golden-census was about to run
        # and what it was about to run it under — the one thing a reader of
        # such a refusal otherwise reconstructs by hand.
        pending = Pending(tuple(manifest.subject.command)
                          + subject_input.args + surface.args)
        pending.env = where.env
        with describing(pending, manifest.census, roots.root, roots.fixed):
            exits.append(_record_surface(manifest, subject_input, surface,
                                         recorder, out, where, fold, pending))
        last = pending
    if exits and all(code != 0 for code in exits):
        out.write(fold(FAILING_INPUT))
    return last


def _record_surface(manifest: Manifest, subject_input: Input, surface: Surface,
                    recorder: Recorder, out: Any, where: Place,
                    fold: Callable[[str], str],
                    pending: Pending) -> int:
    """One surface of one input, recorded; its exit code back.

    A function of its own so the caller's `attaching` window has a body to
    wrap: the window has to enclose every step from the written path to the
    child, and a `with` around a loop body reads as though it wrapped the
    loop.
    """
    roots = recorder.roots
    if surface.kind in ("matrix", "tallies"):
        writes, row_env = row_start(where, subject_input, surface, pending)
        if surface.kind == "matrix":
            return record_matrix(manifest, subject_input, surface, recorder,
                                 roots, row_env, out, writes=writes)
        return record_tallies_surface(manifest, subject_input, surface,
                                      recorder, roots, row_env, out,
                                      writes=writes, pending=pending)
    row = run_row(where, subject_input, surface, pending)
    recorder.record_row(subject_input.name, surface.name, row)
    out.write(f"    {surface.name}: exit {row.exit}\n")
    # Whether the run put no byte anywhere: the test `SILENT_SURFACE` states.
    # Asked of the run and not of the files on disk, because the three files
    # are always written — the question is whether the subject said anything,
    # and an `.exit` file holding a number is not the subject speaking. A
    # written file is asked whether it was written (`None` is none), not
    # whether it holds a byte: an empty one is a file the golden holds.
    if not row.raw.out and not row.raw.err and row.raw.written is None:
        out.write(fold(SILENT_SURFACE))
    if surface.counter and row.raw.written is None:
        out.write(fold(UNCOUNTED))
    elif surface.counter:
        counts = run_counter(manifest, surface, row.writes, roots, row.env)
        recorder.note_counts(subject_input.name, counts)
        out.write(f"      counts {counts}\n")
        if subject_input.expect_counts is not None:
            agree = counts == subject_input.expect_counts
            out.write(f"      expect_counts {subject_input.expect_counts} — "
                      f"{'AGREES' if agree else 'DIFFERS'}\n")
    return row.exit


def _contraband_next(census: Census,
                     hits: list[tuple[str, int, str, str]]) -> str:
    """The `next:` of the contraband refusal, for the hits it found.

    A hit on a directory golden-census knows the path of — one of
    `SOURCE_HITS` — whose `source` no `path` row of the census names is
    folded by adding that row, and the sentence says which. Any other hit —
    a home path, a temp path, a sibling of a directory a `path` row does
    fold — takes a `regex` fold, which a `path` row cannot stand in for.
    """
    folded = {row.source for row in census.folds_of("path")}
    found = {label for _path, _number, label, _token in hits}
    lacking = [source for source in PATH_SOURCES
               if SOURCE_HITS[source] in found and source not in folded]
    regex = (" a `path` row folds one of the four directories golden-census "
             "itself knows the path of (" + ", ".join(PATH_SOURCES)
             + ") and nothing else.")
    if not lacking:
        return ("Stop the subject printing the path where you can; "
                "otherwise add the census `regex` fold that names the "
                "directory quoted above, then capture again. A `path` "
                "fold cannot name it:" + regex)
    said = " ".join(f"Add a census `path` row with `source = \"{source}\"`: "
                    f"it folds {SOURCE_HITS[source]}, quoted above, and this "
                    "census has none." for source in lacking)
    if found - {SOURCE_HITS[source] for source in lacking}:
        said += (" For any other line quoted above, stop the subject "
                 "printing the path where you can; otherwise add the census "
                 "`regex` fold that names its directory:" + regex)
    return said + " Then capture again."


def _scan(recorder: Recorder, roots: Roots, clones: list[str], recorded: str,
          out: Any, fold: Callable[[str], str]) -> int:
    """The contraband scan over everything the capture wrote, and its own
    positive control.

    Each of the three refusals below exits **2**, not 1. Exit 1 reads as "a
    row differs", and nothing was compared here: a contraband hit, a file the
    scan could not open and a positive control that will not go red are all
    statements about the RUN, not about the subject, and the CLI contract
    gives that word one code. `compare` returns 2 for a failed self-check for
    the same reason.

    The two-space margin is handed to `refusal_text` rather than prefixed onto
    what it returns: a refusal is two lines, and prefixing only reaches the
    first — the `next:` line would hang in column zero under an indented
    `REFUSED:`.
    """
    control_ok, control_detail = contraband_control(roots)
    # The tokens the census's `path` rows folded with, under each clone an
    # input ran in as well: the one builder `normalize_paths` folds through.
    tokens = frozenset(token for clone in (None, *clones)
                       for _path, token in path_pairs(
                           recorder.census, roots._replace(clone=clone)))
    scan = scan_contraband(recorder.written, roots, tokens, clones)
    written_count = len(recorder.written)
    out.write(f"\n  contraband scan: {written_count} files written, "
              f"{scan.read} read, {len(scan.hits)} hit(s)\n")
    # Folded like the headers: the control names the scratch file it planted
    # the home paths in, and that file sits under the temp root. It is the
    # sixth line a command prints about the machine, and three of the priced
    # rows cannot price the same under two temp roots while it is unfolded.
    out.write(fold(f"  contraband positive control: "
                   f"{'PASS' if control_ok else 'FAIL'} — {control_detail}\n"))
    if not control_ok:
        out.write(refusal_text(Refusal(
            "the contraband scan cannot be shown to fire; a clean result from "
            "it would prove nothing.",
            next="Run `--selfcheck` and read arm f: the scan's own control is broken, and "
            "nothing about this capture is claimed until it goes red on the planted "
            "path."), indent="  ") + "\n")
        return EXIT_REFUSED
    if scan.unreadable or scan.read != written_count:
        for path, why in scan.unreadable[:LISTED]:
            out.write(f"    {os.path.relpath(path, recorded)}: {why}\n")
        out.write(refusal_text(Refusal(
            f"the scan read {scan.read} of {written_count} files it wrote; a "
            "file it could not open is not a file with nothing in it.",
            next="Check the permissions on the file(s) listed above and capture "
            "again."), indent="  ") + "\n")
        return EXIT_REFUSED
    if scan.hits:
        for path, number, label, found in scan.hits[:LISTED]:
            out.write(f"    {os.path.relpath(path, recorded)}:{number} "
                      f"{label}: {found}\n")
        out.write(refusal_text(Refusal(
            "the capture would commit an absolute path.",
            next=_contraband_next(recorder.census, scan.hits)), indent="  ")
            + "\n")
        return EXIT_REFUSED
    for skipped_input, skipped_surface, why in recorder.skipped:
        out.write(skip_line(f"{row_key(skipped_input, skipped_surface)}: {why}")
                  + "\n")
    return EXIT_OK
