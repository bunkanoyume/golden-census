"""Planting a mutant in a repo-shaped copy of the subject and asking every
check to catch it.

`docs/mutants-format.md` is authoritative for the file format, the mechanics,
the table and the exit codes. Nothing in here knows what the subject is: a
check is either golden-census's own `compare` or a command the consumer wrote,
and a mutant is one `find`/`replace` on one of the subject's files.

Hand-planted mutants are re-planted by hand at every gate or not at all; this
module re-runs them from a file.

Three rules that are decisions rather than transcriptions of the format:

* **The cwd of a `command` check.** It is the mutants file's own directory —
  the consumer's scripts live beside the mutants file — UNLESS the command's
  first element after `<PYTHON>` is a path under `<ROOT>`, in which case it is
  `<ROOT>`, the mutated clone. "Under `<ROOT>`" means an absolute path inside
  the clone, or a relative path that names a file inside it. Both shapes are
  in the format's example: `run_differential.py` sits beside the mutants file,
  `examples/python-function/label_check.py` is a file inside the subject.
* **A `command` check runs under the census's built environment**, as every
  subject subprocess does, but with NO fixed-width TMPDIR: that width exists
  so the bytes a capture RECORDS are stable, which is `capture`'s business,
  and a check's verdict is FIRED or SILENT rather than a golden. A machine
  whose temp root is too wide for the census's pin can therefore still run
  the command checks. Its TMPDIR is a directory of its own instead, made
  under the run's scratch directory before it starts and removed when it
  ends, whatever the census pins or passes through: a check whose
  temporary files follow TMPDIR makes them there and never in the copy it
  runs in. Its name is the 8 characters `tempfile.mkdtemp` draws and
  nothing more, because a Unix socket a check makes under it has to fit a
  path of 103 characters.
* **The self-check runs before a run from the command line and not from
  inside `run_mutants`.** It is `cli.main`'s, decided there for every command
  at once. This function only plants and reports, so the self-check's own
  mutants arms (x, y, z, aa) can drive it directly without a self-check
  calling itself for ever.
"""

from __future__ import annotations

import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any, NamedTuple

from .capture import capture, read_capture
from .census import _git_failed, build_env, git_env, own_log
from .compare import diff_captures, identical, movement_rows, split_diffs
from .core import (
    MATCH_WIDTH,
    COMMAND_WORDS,
    EXIT_MOVED,
    EXIT_OK,
    DIFFERENCE,
    GIT_IDENTITY,
    GIT_NO_MAINTENANCE,
    GIT_UNTRACKED,
    QUOTE_SHORT,
    Layout,
    Placeholders,
    Refusal,
    Roots,
    ended,
    git_command,
    launch,
    load_toml,
    next_line,
    only_keys,
    printed_refusal,
    removed,
    strings,
    under,
    workspace,
)
from .manifest import Manifest, _stays_under
from .run import CLONE_LINE, subject_command

#: What a `fires` condition may be. `exit-nonzero` is the bare string; the
#: other two are one-key tables.
FIRES_SHAPES = ("exit-nonzero", "pattern", "absent")

#: The document authoritative for this file's keys, written once: every
#: refusal that sends a reader to it reads it from here, so the name moves in
#: one edit. It is the FULL path, under the `docs` directory of whichever
#: layout this package is in, because a refusal is read from any directory
#: and a name a reader cannot open is not a `next:`.
_FORMAT_DOC = os.path.join(Layout.detect().data, "docs", "mutants-format.md")


class Check(NamedTuple):
    name: str
    builtin: str | None = None
    golden: str | None = None                  # builtin = "compare"
    command: tuple[str, ...] = ()
    fires: str = ""                            # one of FIRES_SHAPES
    pattern: re.Pattern[str] | None = None
    absent: str | None = None


class Mutant(NamedTuple):
    name: str
    file: str                                  # relative to the subject root
    find: str
    replace: str
    expect: tuple[str, ...] = ()


class Mutants(NamedTuple):
    path: str
    directory: str
    checks: tuple[Check, ...]
    mutants: tuple[Mutant, ...]

    def mutant_named(self, name: str) -> Mutant | None:
        return next((m for m in self.mutants if m.name == name), None)


class Refused(NamedTuple):
    """The three texts of a refusal a comparator's capture raised, or
    printed and exited 2 for, or its comparison raised: its sentence, its
    `next` and its `about`; and `what` refused, the capture or the
    comparison, the one word every line about the refusal names it by.

    Texts and not the exception: a verdict is kept until the table prints,
    and the exception holds the capture's frames through its traceback and,
    for a written file that is not text, that file's bytes through its
    cause. The null mutant's refusal is built from these three and needs
    nothing else.
    """

    sentence: str
    next: str
    about: str
    what: str = "capture"

    @property
    def first_line(self) -> str:
        """The sentence's first line: what the verdict's detail quotes, cut,
        and what the table prints under the mutant's row, whole."""
        return (self.sentence.strip().splitlines() or ["(no text)"])[0]

    @property
    def ran(self) -> str:
        """The first line of the `about` block — the command the refusal's
        run ran, or was about to run, as `census.about_to_run` words it — or
        "" for a refusal with no block. The table prints no block, and a
        refusal over a child launched inside a run's window names its
        command there alone (`core._decoded`), so the table prints this
        line under the first."""
        return (self.about.splitlines() or [""])[0]


class Verdict(NamedTuple):
    check: str
    fired: bool
    detail: str
    #: The refusal a comparator's capture raised or printed, or its
    #: comparison raised: the verdict is then REFUSED, with `fired` False —
    #: the check gave no verdict, so it caught nothing and missed nothing.
    #: The detail quotes the refusal's first line for the table, and the
    #: null mutant needs the whole of it.
    refused: Refused | None = None
    #: What the check printed about the copy beyond its verdict, for the
    #: reader: a comparator's lines about pinned inputs, as its capture
    #: printed them. `_tell` prints them under a heading naming the copy.
    notes: tuple[str, ...] = ()


class Row(NamedTuple):
    mutant: Mutant
    verdicts: tuple[Verdict, ...]

    def cell(self, name: str) -> str:
        """The table's word for check `name` on this mutant."""
        verdict = next(v for v in self.verdicts if v.check == name)
        if verdict.refused is not None:
            return "REFUSED"
        return "FIRED" if verdict.fired else "SILENT"

    @property
    def refusals(self) -> tuple[Verdict, ...]:
        """The checks whose capture or comparison of this mutant's copy
        refused."""
        return tuple(v for v in self.verdicts if v.refused is not None)

    @property
    def missed(self) -> tuple[Verdict, ...]:
        """The checks this mutant's `expect` names that stayed SILENT."""
        return tuple(v for v in self.verdicts
                     if v.check in self.mutant.expect and not v.fired
                     and v.refused is None)

    @property
    def unexpected(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts
                     if v.fired and v.check not in self.mutant.expect)

    @property
    def caught(self) -> bool:
        return any(v.fired for v in self.verdicts)

    @property
    def ok(self) -> bool:
        """A mutant passes when every check it expects fired AND something
        fired at all: a mutant no check catches is a hole in the net, whatever
        its `expect` says (or does not say). A check that REFUSED on it fails
        it too: no comparison was made, and a refusal is never a catch."""
        return not self.refusals and not self.missed and self.caught


# --------------------------------------------------------------------- loading


def _check_context(clone: str | None = None,
                   here: str | None = None) -> Placeholders:
    """The mutants file's ONE placeholder vocabulary: the names a `command`
    check and a `golden` may spell, and their values once there is a clone to
    run against.

    `load_mutants` builds it with no clone — the NAMES are all a load-time
    check needs — so an unknown token costs one sentence instead of a clone,
    a null mutant and a capture per row.

    `<HERE>` is this mutants file's own directory, which is already where a
    `command` check runs (see the module docstring's first rule) and is the
    only directory a consumer whose goldens live outside the subject can name.
    It is a name of this vocabulary and of the census's, and of no other.
    """
    return Placeholders({"ROOT": clone,
                         "PYTHON": sys.executable if clone is not None
                         else None,
                         "HERE": here})


#: The mutants file's own top-level tables, beside `load_mutants`.
_MUTANTS_KEYS = ("checks", "mutant")


def load_mutants(path: str) -> Mutants:
    """Read a mutants file and check every row of it, before anything runs.

    Every refusal names the offending check or mutant: a mutants file that no
    longer applies costs one sentence, not a clone and a capture per row.
    """
    path = os.path.abspath(path)
    # `load_toml` refuses an unfilled hole on the text it read, before the
    # parse; see `load_manifest` for why that order.
    document, _directory = load_toml(path, "mutants file")
    only_keys(document, _MUTANTS_KEYS, f"{path}: the mutants file",
              _FORMAT_DOC)

    checks = _checks(document, path)
    mutants = _mutant_rows(document, path)
    known = {check.name for check in checks}
    for mutant in mutants:
        for name in mutant.expect:
            if name not in known:
                raise Refusal(
                    f"{path}: mutant {mutant.name!r} expects the check "
                    f"{name!r}, which no [checks.<name>] table defines. The "
                    "whole list is " + ", ".join(sorted(known)) + ".",
                    next="Spell that `expect` entry with one of the check names listed above, or "
                    "add the [checks.<name>] table.")
    return Mutants(path, os.path.dirname(path), checks, mutants)


def _checks(document: dict[str, Any], path: str) -> tuple[Check, ...]:
    table = document.get("checks", {})
    if not isinstance(table, dict) or not table:
        raise Refusal(f"{path}: no [checks.<name>] tables — a mutants file with "
                      "no checks plants changes nobody looks for.",
                      next=f"Add one [checks.<name>] table per check; {_FORMAT_DOC} has "
                      "the shapes.")
    return tuple(_check(name, raw, path) for name, raw in table.items())


#: Every key `_check` reads, beside it. All four, not one set per kind: the
#: refusals below say a check is either a `builtin` or a `command`, with its
#: own reason, and that `fires` and `golden` each belong to one kind.
_CHECK_KEYS = ("builtin", "golden", "command", "fires")


def _check(name: str, raw: Any, path: str) -> Check:
    place = f"{path}: [checks.{name}]"
    if not isinstance(raw, dict):
        raise Refusal(f"{place}: must be a table",
                      next="Write that check as a [checks.<name>] table.")
    only_keys(raw, _CHECK_KEYS, place, _FORMAT_DOC)
    builtin = raw.get("builtin")
    command = raw.get("command")
    if (builtin is None) == (command is None):
        raise Refusal(f"{place}: a check is either `builtin = \"compare\"` or a "
                      "`command` with a `fires` condition — never both and "
                      "never neither.",
                      next="Give the check either `builtin = \"compare\"` or a `command` with a "
                      "`fires`, not both and not neither.")
    # A key of the other kind is read by nobody: the builtin's verdict is its
    # comparison and the command's is its `fires`.
    if builtin is not None and "fires" in raw:
        raise Refusal(
            f"{place}: `fires` is not read for a `builtin = \"compare\"` "
            "check. Its verdict is its comparison: FIRED when the capture "
            "is not IDENTICAL to `golden`. The key would sit in the file "
            "doing nothing.",
            next="Drop `fires` from this check, or replace `builtin` with a "
            "`command` to have a check that reads it.")
    if command is not None and "golden" in raw:
        raise Refusal(
            f"{place}: `golden` is not read for a `command` check. Its "
            "verdict is its `fires` condition. The key would sit in the file "
            "doing nothing.",
            next="Drop `golden` from this check, or replace `command` with "
            "`builtin = \"compare\"` to compare against that golden "
            "directory.")
    if builtin is not None:
        if builtin != "compare":
            raise Refusal(f"{place}: the only builtin check is `compare`, not "
                          f"{builtin!r}",
                          next="Write `builtin = \"compare\"`, or give the check a `command` "
                          "instead.")
        golden = raw.get("golden")
        if not isinstance(golden, str) or not golden:
            raise Refusal(f"{place}: the compare builtin needs a `golden` — the "
                          "golden directory a capture of the mutated copy is "
                          "compared against, in one of the three forms "
                          f"{_FORMAT_DOC} states.",
                          next="Add `golden = \"...\"`, the golden directory: relative to the "
                          "mutated copy, <HERE>/… beside this file, or absolute.")
        # Checked HERE, with the same vocabulary the expansion uses, and for
        # the same reason a check `command` is: a `golden` spelling a token
        # golden-census does not define has to refuse now, not after the
        # clone, the null mutant and a capture.
        _check_context().check(golden, f"{place} golden")
        return Check(name, builtin="compare", golden=golden)

    argv = strings(command, f"{place}: command")
    if not argv:
        raise Refusal(f"{place}: `command` is empty",
                      next="Write `command = [...]` with the argv the check runs.")
    # Here, and not in `_run_command`: a check command spelling `<WORK>` has
    # to refuse now, not after the subject has been cloned and the null mutant
    # run. The same vocabulary the expansion uses, so the two halves cannot
    # come to disagree about the names.
    for text in argv:
        _check_context().check(text, f"{path}: [checks.{name}] command")
    return _fires(name, raw.get("fires"), argv, place)


def _fires(name: str, fires: Any, argv: tuple[str, ...], place: str) -> Check:
    if fires is None:
        raise Refusal(f"{place}: a `command` check needs a `fires` condition — "
                      "`\"exit-nonzero\"`, `{ pattern = <regex> }` or "
                      "`{ absent = <text> }`. Without one golden-census would be "
                      "deciding for the consumer what counts as caught.",
                      next="Add a `fires` condition saying what counts as caught for this check.")
    if fires == "exit-nonzero":
        return Check(name, command=argv, fires="exit-nonzero")
    if not isinstance(fires, dict) or len(fires) != 1:
        raise Refusal(f"{place}: `fires` is {fires!r}, which is not "
                      "\"exit-nonzero\" and not a one-key table `pattern` or "
                      "`absent`",
                      next="Write `fires` as \"exit-nonzero\", or as a one-key table { pattern = "
                      "... } or { absent = ... }.")
    if "pattern" in fires:
        pattern = fires["pattern"]
        if not isinstance(pattern, str):
            raise Refusal(f"{place}: `fires.pattern` must be a string",
                          next="Write `fires = { pattern = \"...\" }` with a string regular "
                          "expression.")
        try:
            compiled = re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            raise Refusal(f"{place}: `fires.pattern` does not compile: "
                          f"{exc}",
                          next="Fix that regular expression; it is compiled when the "
                          "mutants file is read, before a clone is made.") from exc
        return Check(name, command=argv, fires="pattern", pattern=compiled)
    if "absent" in fires:
        absent = fires["absent"]
        if not isinstance(absent, str) or not absent:
            raise Refusal(f"{place}: `fires.absent` must be the text a clean "
                          "run prints",
                          next="Write `fires = { absent = \"...\" }` with the text a clean run "
                          "prints.")
        return Check(name, command=argv, fires="absent", absent=absent)
    raise Refusal(f"{place}: `fires` names {sorted(fires)}, not `pattern` or "
                  "`absent`",
                  next="Write `fires` as \"exit-nonzero\", { pattern = ... } or { absent = ... }.")


#: Every key a [[mutant]] row reads, beside `_mutant_rows`.
_MUTANT_KEYS = ("name", "file", "find", "replace", "expect")


def _mutant_rows(document: dict[str, Any], path: str) -> tuple[Mutant, ...]:
    raw_rows = document.get("mutant", [])
    if not isinstance(raw_rows, list) or not raw_rows:
        raise Refusal(f"{path}: no [[mutant]] rows",
                      next="Add one [[mutant]] row per planted change: `file`, `find`, `replace` "
                      "and `expect`.")
    rows: list[Mutant] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise Refusal(f"{path}: every [[mutant]] must be a table",
                          next="Write each mutant as a [[mutant]] table.")
        name = str(raw.get("name", "")).strip()
        if not name:
            raise Refusal(f"{path}: a [[mutant]] has no `name`.",
                          next="Give every [[mutant]] a `name`; the results "
                          "table and every refusal use it.")
        if name in seen:
            raise Refusal(f"{path}: two [[mutant]] rows are both named "
                          f"{name!r}; a name is one row of the table.",
                          next="Rename one of the two rows.")
        seen.add(name)
        place = f"{path}: mutant {name!r}"
        only_keys(raw, _MUTANT_KEYS, place, _FORMAT_DOC)
        for key in ("file", "find", "replace"):
            if not isinstance(raw.get(key), str):
                raise Refusal(f"{place}: needs a `{key}` (a string)",
                              next="Add that key to the [[mutant]] row, as a string.")
        if not raw["find"]:
            raise Refusal(f"{place}: `find` is empty",
                          next="Write `find = \"...\"` with the exact text the mutant replaces.")
        rows.append(Mutant(name, str(raw["file"]), str(raw["find"]),
                           str(raw["replace"]),
                           strings(raw.get("expect", []),
                                   f"{place}: expect")))
    return tuple(rows)


# ------------------------------------------------------------------- the clone


def _git(words: list[str], what: str) -> subprocess.CompletedProcess[str]:
    """One git of `mutants`: `core.git_command`'s argv over `words`, so
    what the clone holds and what `git status` lists in it are the
    repository's answer and not the global configuration of the user
    running golden-census. A git that will not start is named by the first
    `COMMAND_WORDS` words of `git` and `words`."""
    named = f"{what}: `{' '.join(['git', *words][:COMMAND_WORDS])} …`"
    return launch(git_command(*words), named, env=git_env(named))


def _head(directory: str, what: str) -> str:
    proc = _git(["-C", directory, "rev-parse", "HEAD"], what)
    if proc.returncode != 0:
        # The reason is `census._git_failed`'s, cut at `QUOTE`, like every other
        # failed-git clause in this module.
        raise Refusal(_git_failed(f"{what}: `git rev-parse HEAD` in "
                                  f"{directory}", proc),
                      next="Run `git rev-parse HEAD` in that directory by hand; `mutants` needs a "
                      "subject in a git repository.")
    return proc.stdout.strip()


def _slug(name: str) -> str:
    kept = [char if (char.isalnum() or char in "-_") else "-" for char in name]
    return "".join(kept).strip("-") or "mutant"


def clone_subject(root: str, into: str, label: str) -> str:
    """A repo-shaped copy of the subject root at `into`, verified to be at the
    same commit.

    Repo-shaped and not a file copy: a subject that stamps its output with its
    commit needs a repository to read, and a bare copy produces a spurious diff
    on every stamped surface.
    """
    clone = os.path.join(into, _slug(label))
    proc = _git(["clone", "--local", "--quiet", root, clone],
                f"the clone for {label!r}")
    if proc.returncode != 0:
        raise Refusal(_git_failed(f"the clone for {label!r}: `git clone "
                                  "--local`", proc),
                      next="Run that clone by hand and fix what git reports; every mutant is "
                      "planted in a clone, never in the subject.")
    want = _head(root, f"the clone for {label!r}")
    got = _head(clone, f"the clone for {label!r}")
    if got != want:
        raise Refusal(f"the clone for {label!r} is at {got!r}, not the subject "
                      f"root's {want!r}; every check would be reading a "
                      "different tree from the one the mutant was measured on.",
                      next="Commit or stash the subject's working tree, then run `mutants` again: "
                      "`git clone --local` copies HEAD, not the working tree.")
    return clone


def _unreadable(mutant: Mutant, exc: Exception, place: str) -> Refusal:
    """The refusal a mutant's `file` earns when it cannot be read.

    ONE owner, because the file is read in two trees — the subject root
    before the first clone, and the clone each mutant is planted in — and the
    two differ only in which tree to look in, which is `place`. Two copies of
    this sentence would be two sentences a reader could meet for one fault.
    """
    return Refusal(
        f"mutant {mutant.name!r}: {mutant.file!r} could not be read: "
        f"{type(exc).__name__}: {exc}",
        next=f"Check the path and the permissions of that file {place}.")


def _refuse_outside(mutant: Mutant, path: str, directory: str,
                    where_token: str) -> None:
    """A mutant's `file` that RESOLVES outside the tree it is opened in.

    `manifest._stays_under` reads the SPELLING the author wrote — relative, no
    `..` — which is the line they have to edit, and it is the whole rule for
    an ordinary name. It cannot see a link: `link.py` is one component and
    passes it, `os.path.isfile` follows the link and answers yes, and `plant`
    then opens the stranger's file it points at for WRITING. So the spelling
    is asked of the string and the DESTINATION is asked of the filesystem, by
    `core.under`; both are needed, because the first names the line to edit and
    only the second knows where it goes.

    ONE owner, because the same question is put to two trees — the subject
    root before the first clone, and the clone each mutant is planted in —
    which differ only in `directory` and in `where_token`.
    """
    if under(path, directory, strict=True):
        return
    raise Refusal(
        f"mutant {mutant.name!r}: {mutant.file!r} resolves to "
        f"{os.path.realpath(path)}, outside {where_token}. "
        "golden-census follows the path it is given and `plant` opens it for "
        "writing, so planting this mutant would edit a file outside the tree "
        "under test and leave it edited.",
        next=f"Point the mutant's `file` at a file under {where_token}; if it is a "
        "link, replace the link with the file itself.")


#: The `next:` of a git step of `plant` that failed: git's words are above it.
_AGAIN = "Run `mutants` again; if it repeats, fix what git reports above."


def plant(clone: str, mutant: Mutant) -> None:
    """Apply the edit inside the clone and commit it, so the tree is CLEAN at a
    new sha.

    Committed, because a dirty stamp is longer than a clean one and moves a
    stamped surface's size lines by itself. The identity is given on the
    command line: a machine with no `user.email` configured is not a reason for
    a mutant to go unplanted.
    """
    path = os.path.join(clone, mutant.file)
    # BEFORE the `isfile` test and before anything is opened: a committed
    # symlink is cloned as a symlink, `isfile` follows it, and the open below
    # is a WRITE. Asked of the clone and not of the subject root, because the
    # clone is the tree this function edits.
    _refuse_outside(mutant, path, clone,
                    "the clone golden-census made of the subject")
    # The clone is `git clone --local` of the subject, which copies the last
    # COMMIT: a file that is in the working tree and not in it is not here,
    # and this open was a `FileNotFoundError` traceback at exit 1.
    if not os.path.isfile(path):
        raise Refusal(
            f"mutant {mutant.name!r}: {mutant.file} is in the subject's "
            "working tree but not in the clone. `mutants` plants each mutant "
            "in a `git clone --local` of the subject, which copies the last "
            "COMMIT and not the working tree, so a file that was never "
            "committed is not there to edit.",
            next="Commit that file to the subject's repository and run `mutants` again, or "
            "point the mutant's `file` at one that is committed.")
    # `newline=""` on both halves: the default translates CRLF to LF on the way
    # in, and a subject file with CRLF endings would be rewritten wholesale —
    # a mutant that changes every line of a file is not one edit to one place.
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise _unreadable(mutant, exc,
                          "inside the clone golden-census made of the "
                          "subject") from exc
    count = text.count(mutant.find)
    if count != 1:                              # asserted here too: the clone
        raise Refusal(                          # is what the checks read
            f"mutant {mutant.name!r}: `find` occurs {count} times in the "
            f"CLONE's {mutant.file}, the file as committed",
            next=("Commit the edit `find` expects, or point `find` at text "
                  "that is committed, or drop the mutant." if count == 0 else
                  "Lengthen `find` until it matches exactly one site in the "
                  "committed file."))
    pathlib.Path(path).write_text(text.replace(mutant.find, mutant.replace),
                                  encoding="utf-8", newline="")
    proc = _git(["-C", clone, *GIT_IDENTITY, *GIT_NO_MAINTENANCE,
                 "commit", "-aq", "-m", f"mutant: {mutant.name}"],
                f"mutant {mutant.name!r}")
    if proc.returncode != 0:
        raise Refusal(_git_failed(f"mutant {mutant.name!r}: `git commit` in "
                                  "the clone", proc),
                      next=_AGAIN)
    status = _git(["-C", clone, "status", "--porcelain", GIT_UNTRACKED],
                  f"mutant {mutant.name!r}")
    if status.returncode != 0:
        raise Refusal(_git_failed(f"mutant {mutant.name!r}: `git status "
                                  "--porcelain` in the clone", status),
                      next=_AGAIN)
    if status.stdout.strip():
        # What the run knows: the edit was committed in a clone of its own,
        # every hook off and no global ignore file (`core.GIT_SETTINGS`), so
        # what git lists is the repository's doing; and the clone is gone
        # when `mutants` ends, so the reader reproduces it by hand.
        raise Refusal(f"mutant {mutant.name!r}: the clone is not clean after "
                      f"the commit of its edit to {mutant.file}: `git status "
                      f"--porcelain` lists "
                      f"{status.stdout.strip()[:QUOTE_SHORT]!r}. "
                      "golden-census committed the edit in a clone of its own "
                      "under the temp root, with every hook off and no global "
                      "ignore file, so what git lists comes from the "
                      "repository itself.",
                      next=f"Clone the subject by hand, make this mutant's "
                      f"edit to {mutant.file}, run `git commit -a` and then "
                      "`git status --porcelain` there: what it lists is the "
                      "cause, usually a .gitattributes rule that does not "
                      "round-trip that file, or two committed names this disk "
                      "reads as one. Fix it in the repository and run "
                      "`mutants` again.")


# ------------------------------------------------------------------ the checks


def check_cwd(check: Check, argv: list[str], clone: str, directory: str) -> str:
    """Where a `command` check runs: see the module docstring's first rule."""
    # The vocabulary is asked how it spells the interpreter, rather than the
    # token being typed beside the table that defines it: a rename there moves
    # this rule with it, where a literal would have gone on comparing against
    # a token nobody defines.
    python = _check_context().token("PYTHON")
    index = 1 if check.command and check.command[0] == python else 0
    if index >= len(argv):
        return directory
    first = argv[index]
    if os.path.isabs(first):
        return clone if under(first, clone, strict=True) else directory
    return clone if os.path.isfile(os.path.join(clone, first)) else directory


def run_check(check: Check, mutants: Mutants, manifest: Manifest, clone: str,
              scratch: str, out: Any) -> Verdict:
    """One check against one clone. FIRED or SILENT — or REFUSED, a
    comparator whose capture or comparison refused — with the detail that
    says why, never a raise the caller has to read as a verdict. The
    clone is read as it stands, the mutant planted or not. `out` is the
    run's own stream, which `core.removed` is handed for each directory the
    check made."""
    if check.builtin == "compare":
        return _run_compare(check, mutants, manifest, clone, scratch, out)
    return _run_command(check, mutants, manifest, clone, scratch, out)


def _capture_refused(check: Check, texts: Refused) -> Verdict:
    """The REFUSED verdict of a comparator whose capture refused — raised or
    printed, the one sentence, its detail the refusal's first line."""
    return Verdict(check.name, False, "the capture refused: "
                   f"{texts.first_line[:DIFFERENCE]}", texts)


def _run_compare(check: Check, mutants: Mutants, manifest: Manifest,
                 clone: str, scratch: str, out: Any) -> Verdict:
    """golden-census's own comparator: a whole capture of the mutated copy under
    the manifest, against the golden set the clone carries.

    IDENTICAL is SILENT — a row the manifest's `[[movements]]` permit
    counting as it counts in `compare` — and anything else — a differing
    row, or a row on one side only — is FIRED. A capture that refuses made
    no comparison, whether it raised its refusal or printed it and exited 2:
    the verdict is REFUSED, never FIRED, whatever the refusal names — the
    mutant or the machine — with its detail quoting the refusal's first
    line and the refusal's three texts carried on the verdict. So is a
    comparison that refuses — a moved row two `[[movements]]` rows name,
    which `compare` refuses too. Under the null mutant that REFUSED is
    what `_null_mutant` refuses the run on, in the refusal's own words;
    under a mutant, `_report` prints it and counts the mutant not caught.

    The directory the capture goes in is made under the run's scratch
    directory, under the temp root. When the root will not take it, that is
    about the run and not the mutant, as the golden directory's refusal is:
    its `OSError` is raised as it is, and no verdict is given.
    """
    raw = check.golden or ""
    where = f"{mutants.path}: [checks.{check.name}] golden"
    expanded = _check_context(clone, mutants.directory).expand(raw, where)
    # Three documented forms, ONE resolution. An expanded path that is already
    # absolute is used AS IT IS — which is what `<HERE>/…` and `<ROOT>/…` both
    # become, and what an absolute `golden` is; anything else is relative to
    # the mutated copy, which is what a bare path means.
    golden = (expanded if os.path.isabs(expanded)
              else os.path.join(clone, expanded))
    if not os.path.isdir(golden):
        form, resolves = _golden_form(raw)
        raise Refusal(f"check {check.name!r}: no golden directory at "
                      f"{raw!r} ({form}): {golden} is not a directory.",
                      next="Point `golden` at the directory the golden set "
                      f"is in: {resolves}.")
    into = tempfile.mkdtemp(prefix="golden-census-mutant-capture-",
                            dir=scratch)
    log = io.StringIO()
    try:
        verdict = _compared(check, manifest, clone, golden, into, log)
    finally:
        removed(into, out)
    # Every line the capture printed about a pinned input — the `clone:`
    # line, cloned or found in the cache, and the residue line under it —
    # whatever the verdict: the table prints none of the log. A directory
    # of the capture's that stayed is not in it: `core.left_behind` noted it
    # for the run's own `workspace`, which names it when the run ends.
    return verdict._replace(notes=tuple(
        line for line in log.getvalue().splitlines()
        if line.startswith(CLONE_LINE)))


def _compared(check: Check, manifest: Manifest, clone: str, golden: str,
              into: str, log: Any) -> Verdict:
    """The comparator's verdict on its capture of `clone` into `into`, the
    capture's lines written to `log`: `_run_compare`'s, which removes
    `into` afterwards."""
    # Only the capture: the golden directory's refusal and `read_capture`'s
    # below are about the run, and stay refusals of it. A capture that
    # raises has already taken back what it made.
    try:
        code = capture(manifest.with_root(clone), into, log)
    except Refusal as refused:
        return _capture_refused(check, Refused(str(refused), refused.next,
                                               refused.about))
    if code != 0:
        # The capture's in-band refusals: printed, and returned as exit 2 —
        # the one code other than 0 `capture` returns — never raised. A
        # refusal all the same, read back from what the capture printed,
        # the lines it quoted above it carried in the sentence, and with no
        # `about`: it printed none.
        return _capture_refused(check, Refused(*printed_refusal(log.getvalue()),
                                               ""))
    # The manifest's `[[movements]]` permit here as they do in `compare`:
    # a row the manifest attributes is not the mutant, and the count of
    # rows permitted is in both details, since a SILENT that owes itself
    # to a permitted row is a fact the reader of a FAIL line needs. A
    # moved row two of them name is refused, as `compare` refuses it: no
    # comparison was made, and the verdict is REFUSED like a capture's.
    diffs = diff_captures(read_capture(golden, "the golden set"),
                          read_capture(into, "the mutant's capture"))
    try:
        permitted, blocking = split_diffs(diffs, movement_rows(manifest))
    except Refusal as refused:
        texts = Refused(str(refused), refused.next, refused.about,
                        "comparison")
        return Verdict(check.name, False, "the comparison refused: "
                       f"{texts.first_line[:DIFFERENCE]}", texts)
    if not blocking:
        return Verdict(check.name, False, identical(len(permitted)))
    return Verdict(check.name, True,
                   f"{len(blocking)} differing row(s), first "
                   f"{blocking[0].path} ({blocking[0].kind})"
                   + (f" ({len(permitted)} permitted)" if permitted else ""))


def _golden_form(raw: str) -> tuple[str, str]:
    """Which of the three forms a `golden` was written in, and how that form
    resolves, for the refusal above: a reader told the path is wrong has to
    be told what it was resolved against — the form they wrote, not all
    three, which `docs/mutants-format.md` lists."""
    vocabulary = _check_context()
    here = vocabulary.token("HERE")
    if raw.startswith(here):
        return ("beside the mutants file",
                f"{here}/… is resolved against the directory this mutants "
                "file sits in")
    if raw.startswith(vocabulary.token("ROOT")) or os.path.isabs(raw):
        return "an absolute path", "an absolute path is used as it is"
    return ("relative to the mutated copy",
            "a bare path is resolved against the mutated copy, so the golden "
            "set has to be committed in the subject's own repository")


def _run_command(check: Check, mutants: Mutants, manifest: Manifest, clone: str,
                 scratch: str, out: Any) -> Verdict:
    """A consumer's check, run under the census's built environment with
    TMPDIR a directory of its own (the module docstring's second rule).

    The directory is made under the run's scratch directory, under the temp
    root; when it cannot be made, its `OSError` is raised as it is, as the
    comparator's directory's is. It is removed when the check ends, also
    when the check would not start, by `core.removed` on `out`: one that is
    still on disk when the command ends is named in the line every such
    directory is named in. The verdict stands."""
    table = _check_context(clone, mutants.directory)
    where = f"{mutants.path}: [checks.{check.name}] command"
    argv = [table.expand(arg, where) for arg in check.command]
    cwd = check_cwd(check, argv, clone, mutants.directory)
    env = build_env(manifest.census,
                    Roots(root=clone, work=scratch, clone=None, fixed=None))
    # The shortest name `mkdtemp` draws, 8 characters: a socket made under
    # this TMPDIR with `tempfile.mkdtemp()` and a name of one character
    # takes 14 more, and fits the 103 characters a Unix socket's path may
    # hold under a temp root of up to 49 — the widest a census's
    # `<FIXED-WIDTH-DIR:51>` lets a capture run under.
    own = tempfile.mkdtemp(prefix="", dir=scratch)
    env["TMPDIR"] = own
    # No deadline of its own: golden-census cannot know how long a check
    # should run, so the caller owns the deadline. A check that never returns
    # holds the run open until the caller's deadline ends it, and the process
    # group printed at the top of the log is what kills the tree it left.
    try:
        proc = launch(argv, f"check {check.name!r}", cwd=cwd, env=env)
    finally:
        removed(own, out)
    return _command_verdict(check, proc)


def _command_verdict(check: Check,
                     proc: subprocess.CompletedProcess[str]) -> Verdict:
    """What `check`'s `fires` condition says of the run `proc` ended."""
    # Each stream on its own, never the two joined: a stdout that does not
    # end with a newline would put its last line and stderr's first on one
    # line, where `^` cannot anchor stderr and a text can span the join.
    streams = (proc.stdout, proc.stderr)
    if check.fires == "exit-nonzero":
        return Verdict(check.name, proc.returncode != 0,
                       ended(proc.returncode))
    if check.fires == "pattern" and check.pattern is not None:
        found = (check.pattern.search(streams[0])
                 or check.pattern.search(streams[1]))
        return Verdict(check.name, found is not None,
                       f"{ended(proc.returncode)}, pattern "
                       + (f"matched {found.group(0)[:MATCH_WIDTH]!r}" if found
                          else "did not match"))
    absent = all((check.absent or "") not in stream for stream in streams)
    return Verdict(check.name, absent, f"{ended(proc.returncode)}, {check.absent!r} "
                   + ("absent" if absent else "present"))


# -------------------------------------------------------------------- the run


def _chosen(mutants: Mutants, only: tuple[str, ...]) -> tuple[Mutant, ...]:
    if not only:
        return mutants.mutants
    # Every name is checked before the refusal speaks, not the first alone:
    # `--only` repeats, and a reader told of one misspelling at a time runs
    # once per typo. The bad names keep the command line's order, each once;
    # the file's names follow one per line, because a mutant's name is a
    # phrase — the shipped example's are a clause long — and a clause quoted
    # inside a sentence is lost in it.
    missing = [name for name in dict.fromkeys(only) if mutants.mutant_named(name) is None]
    if missing:
        raise Refusal("--only " + ", ".join(repr(name) for name in missing)
                      + f": no [[mutant]] has that name.\n  {mutants.path} has\n  "
                      + "\n  ".join(repr(m.name) for m in mutants.mutants),
                      next=f"Use --only with any of the names in "
                      f"{os.path.basename(mutants.path)}, or drop --only to plant every "
                      "mutant in the file.")
    wanted = set(only)
    return tuple(m for m in mutants.mutants if m.name in wanted)


def preflight(manifest: Manifest, chosen: tuple[Mutant, ...]) -> None:
    """Every mutant still applies, checked against the subject root before the
    first clone.

    A mutant whose `find` has moved is a REFUSAL naming it, never a silent
    pass: a table of SILENT rows that is really a table of edits nobody made
    would read as a hole in the net.
    """
    root = manifest.subject.root
    for mutant in chosen:
        # BEFORE anything asks the filesystem about it: `os.path.join`
        # discards `root` when the second element is absolute and the
        # filesystem resolves `..` without comment, so a `file` that leaves
        # the subject root resolves to a stranger's file — and `plant` opens
        # whatever path it is given for WRITING. The condition is
        # `manifest._stays_under`'s, the same one a `[files]` key obeys.
        _stays_under(mutant.file, "a mutant's `file`", "the subject root",
                     f"mutant {mutant.name!r}")
        path = os.path.join(root, mutant.file)
        # The spelling above, the DESTINATION here, and this one before any
        # clone is made: a committed link whose target is outside the root
        # passes the spelling rule and is followed by every call below.
        _refuse_outside(mutant, path, root, "the subject root")
        if not os.path.isfile(path):
            raise Refusal(f"mutant {mutant.name!r}: {mutant.file!r} is not a "
                          f"file of the subject root ({path}).",
                          next="Point the mutant's `file` at a path inside the subject root, "
                          "relative to it.")
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise _unreadable(mutant, exc, "under the subject root") from exc
        count = text.count(mutant.find)
        if count != 1:
            raise Refusal(
                f"mutant {mutant.name!r}: `find` occurs {count} times in "
                f"{mutant.file}, and a mutant is one edit to one place.",
                next=("Re-plant the mutant on the text that file holds now, "
                      "or drop it." if count == 0 else
                      "Lengthen `find` until it matches exactly one site in "
                      "that file."))


def chosen_and_checked(manifest: Manifest, mutants: Mutants,
                       only: tuple[str, ...]) -> tuple[Mutant, ...]:
    """The mutants a run will plant, after the two refusals that only read
    files: an `--only` name no mutant has, and a mutant whose `find` no longer
    occurs exactly once. Nothing is run, so `cli.main` calls this above the
    census's controls and hands the result to `run_mutants` as `chosen`."""
    chosen = _chosen(mutants, only)
    preflight(manifest, chosen)
    return chosen


def run_mutants(manifest: Manifest, mutants: Mutants, out: Any,
                only: tuple[str, ...] = (),
                chosen: tuple[Mutant, ...] | None = None) -> int:
    """Plant every mutant, run every check, print the table. Returns an exit
    code: 0 when every mutant was caught by every check it expects, 1 otherwise.
    A refusal is raised, and the command line turns it into exit 2.
    `chosen`, when given, is `chosen_and_checked`'s result and is used as it
    is; otherwise the mutants are chosen and checked here.

    The self-check that precedes a run is `cli.main`'s (the module docstring's
    third rule), which is why the self-check's own arms can drive this
    function directly.
    """
    if chosen is None:
        chosen = chosen_and_checked(manifest, mutants, only)
    out.write(own_log(
        f"\nMUTANTS  {_display(mutants.path)}  ({len(chosen)} mutants, "
        f"{len(mutants.checks)} checks)\n",
        manifest.census, manifest.subject.root))

    # No census is passed to `core.workspace`, so no fixed-width directory is
    # made: a check's verdict is FIRED or SILENT rather than a golden (the
    # module docstring's second rule), the captures a `compare` check runs
    # make their own, and a `command` check gets a TMPDIR of its own.
    with workspace(None, "golden-census-mutants-", manifest.subject.root,
                   out=out) as roots:
        scratch = roots.work
        _null_mutant(manifest, mutants, scratch, out)
        rows = [_one_mutant(manifest, mutants, mutant, scratch, out)
                for mutant in chosen]
        return _report(manifest, mutants, rows, out)


def _display(path: str) -> str:
    """A path as a reader of the report can type it: relative to the working
    directory when it is under it, absolute when it is not."""
    # Not `census.own_log`'s job: that decides whether a path is FOLDED to a
    # token, this decides whether a path the reader will type is relative or
    # absolute — two questions, not one fact.
    relative = os.path.relpath(path, os.getcwd())
    return path if relative.startswith("..") else relative


def runs_in_the_clone(manifest: Manifest, clone: str, scratch: str) -> None:
    """Every ABSOLUTE element of `[subject] command` names a file of the CLONE,
    or the whole run is refused before a single check.

    A `mutants` run is worth what its captures are worth, and a capture is
    worth nothing when the argv prefix it runs reaches back into the tree
    golden-census was invoked in: the planted change is never executed, every
    check is SILENT, the null mutant is SILENT too — it has nothing to compare
    against — and a net that has stopped catching prints exactly what a clean
    one prints.

    ABSOLUTE is the whole test, and the other two spellings are why. A
    relative element is passed as the author wrote it and resolves against the
    cwd of the run, which is the clone, so it names the clone by construction;
    judging it here would resolve it against golden-census's OWN working
    directory instead, and a run started from the subject's checkout would be
    refused for a path that was never used. A `<HERE>` element is absolute but
    `Manifest.with_root` has already re-anchored it — onto the clone when the
    manifest sits inside the subject, and onto the manifest's own directory,
    which is outside the subject root, when it does not. So neither can reach
    this, and what is left is an absolute path typed into the manifest, which
    names one machine's checkout and can be re-anchored onto nothing. Measured
    on both shapes and on the consumer manifest that has the outside one: the
    entry point lands under the clone or outside the subject root every time,
    and no element reaches the refusal. So the refusal's positive control is
    the absolute path, and it is arm `oooo`'s red half.
    """
    argv = subject_command(manifest.with_root(clone),
                           Roots(root=clone, work=scratch))
    for element in argv:
        if not os.path.isabs(element) or not os.path.exists(element):
            continue
        if (not under(element, manifest.subject.root, strict=True)
                or under(element, clone, strict=True)):
            continue
        # The `next:` names one form, the relative path this element already
        # has under the subject root, because that always loads. `<HERE>/…`
        # is the other form golden-census carries onto the copy, for a file
        # that sits beside the manifest; the reader wrote an absolute path,
        # and an absolute path into one machine's checkout is not a path
        # golden-census can carry, so the message does not offer it as one.
        raise Refusal(
            f"[subject] command names {element}, which is a file of the "
            f"subject root ({manifest.subject.root}) and not of the copy "
            f"under test ({clone}): this runs in your tree, not the clone. "
            "Every check would be reading a subject the mutant was never "
            "planted in, and a net that has stopped catching prints what a "
            "clean one prints.",
            next="Spell that element relative to [subject] root, as "
            f"{os.path.relpath(element, manifest.subject.root)!r}; "
            "golden-census carries a relative path onto the copy.")


def _uncommitted(manifest: Manifest) -> str:
    """The sentence naming what the working tree holds that the clone, a
    copy of the last commit, does not carry; empty when git says nothing.

    Asked only here and only after the null mutant fired: a dirty tree is
    common and is not a fault. It is a fact that explains a null mutant that
    fired, and the reader of this refusal is the one it helps. A git that
    exits non-zero, or prints nothing, adds nothing: nothing is guessed, and
    a git that will not run is not a second refusal."""
    try:
        proc = _git(["-C", manifest.subject.root, "status", "--porcelain"],
                    "the null mutant's `git status`")
    except Refusal:
        return ""
    lines = proc.stdout.splitlines() if proc.returncode == 0 else []
    if not lines:
        return ""
    shown = ", ".join(f"`{line}`" for line in lines[:5])
    more = f", and {len(lines) - 5} more" if len(lines) > 5 else ""
    return (f" `git status --porcelain` in the subject root lists "
            f"{len(lines)} path(s) the clone, a copy of the last commit, "
            f"does not carry as they are: {shown}{more}.")


def _null_mutant(manifest: Manifest, mutants: Mutants, scratch: str,
                 out: Any) -> None:
    """Every check on the UNMUTATED clone. Any FIRED is a refusal of the whole
    run naming the check: its verdicts on the real mutants would mean nothing,
    and a table of FIREDs from a check that always fires is worse than no
    table. A REFUSED — a capture's or a comparison's refusal — is refused
    in its own words, by `_refused_on_null`, which names every other check
    that fired or refused there."""
    clone = clone_subject(manifest.subject.root, scratch, "null")
    try:
        # Here and not in `preflight`: the refusal is about the clone, so it
        # needs one to name, and the first clone a run makes is this one.
        runs_in_the_clone(manifest, clone, scratch)
        verdicts = [_tell(manifest, "the null mutant",
                          run_check(check, mutants, manifest, clone, scratch,
                                    out), out)
                    for check in mutants.checks]
    finally:
        removed(clone, out)
    fired = [v for v in verdicts if v.fired]
    reported = [v for v in verdicts if v.fired or v.refused is not None]
    for verdict in reported:
        if verdict.refused is not None:
            raise _refused_on_null(verdict.check, verdict.refused,
                                   [v for v in reported if v is not verdict])
    if fired:
        raise Refusal(
            "the null mutant — the unmutated copy — was reported by "
            + ", ".join(f"{v.check} ({v.detail})" for v in fired)
            + ". A check that fires on an unchanged subject says nothing about "
            "a mutant, so the whole run is refused rather than printing a "
            "column of FIREDs that mean nothing."
            + _uncommitted(manifest),
            next="Fix the check(s) named above so they are silent on an unchanged subject, then "
            "run `mutants` again.")
    out.write("  null mutant: "
              + ", ".join(f"{v.check} SILENT" for v in verdicts) + "\n\n")


def _refused_on_null(check: str, refused: Refused,
                     others: list[Verdict]) -> Refusal:
    """The run's refusal when a comparator's capture or comparison refused
    on the UNMUTATED copy: its own reason, whole, with its own `next` and
    its own `about`, named by `refused.what`.

    The check is not what is wrong — the capture of an unchanged subject
    would not run, or its comparison would not be made, for a reason the
    refusal names — so the check's fix is not the reader's next step, and
    a first line cut to fit a table cell is not the reason. It explains the
    most of any check that fired, so it is the run's refusal, and the
    others are named in it.
    """
    also = ("; the null mutant was also reported by "
            + ", ".join(f"{v.check} ({v.detail})" for v in others)
            if others else "")
    result = Refusal(
        f"the null mutant — the unmutated copy — was reported by {check} "
        f"because its {refused.what} of that copy refused, for a reason of "
        f"the {refused.what}'s own and not of the check{also}. The "
        f"{refused.what} refused: {refused.sentence}",
        next=refused.next)
    result.about = refused.about
    return result


def _one_mutant(manifest: Manifest, mutants: Mutants, mutant: Mutant,
                scratch: str, out: Any) -> Row:
    clone = clone_subject(manifest.subject.root, scratch, mutant.name)
    try:
        plant(clone, mutant)
        return Row(mutant, tuple(
            _tell(manifest, f"mutant {mutant.name!r}",
                  run_check(check, mutants, manifest, clone, scratch, out),
                  out)
            for check in mutants.checks))
    finally:
        removed(clone, out)


def _tell(manifest: Manifest, which: str, verdict: Verdict,
          out: Any) -> Verdict:
    """`verdict`'s `notes`, written at once under a heading naming `which`
    copy and the check, the block ended by a blank line and folded by
    `own_log`; nothing for a verdict with none. Returns `verdict`: each
    check's block is written as that check ends, so a refusal later on the
    same copy or on a later one loses nothing already printed."""
    if verdict.notes:
        out.write(own_log(
            f"  {which}, check {verdict.check!r}:\n"
            + "".join(f"  {line}\n" for line in verdict.notes) + "\n",
            manifest.census, manifest.subject.root))
    return verdict


# ------------------------------------------------------------------ the table


def _report(manifest: Manifest, mutants: Mutants, rows: list[Row],
            out: Any) -> int:
    """The table, the tally and a FAIL line for every mutant that did not
    pass; returns the exit code.

    A REFUSED cell is followed, under its row, by the refusal's first line,
    whole, and under that by its block's first line, the command, when it
    carries a block (`Refused.ran`), both folded by `own_log`: either can
    name a directory of the run. A mutant with a REFUSED cell is never
    counted caught, so a run that holds one exits 1."""
    names = [check.name for check in mutants.checks]
    name_width = max([len("mutant")] + [len(r.mutant.name) for r in rows]) + 2
    widths = [max(len(name), len("SILENT")) + 2 for name in names]
    header = ("  " + "mutant".ljust(name_width)
              + "".join(n.ljust(w) for n, w in zip(names, widths, strict=True)))
    out.write(header.rstrip() + "\n")
    for row in rows:
        cells = "".join(row.cell(name).ljust(width)
                        for name, width in zip(names, widths, strict=True))
        notes = [f"({v.check}: unexpected)" for v in row.unexpected]
        notes += [f"({v.check}: expected, SILENT)" for v in row.missed]
        if not row.caught and not row.refusals:
            notes.append("(no check fired)")
        line = "  " + row.mutant.name.ljust(name_width) + cells
        out.write((line + ("  " + "  ".join(notes) if notes else "")).rstrip()
                  + "\n")
        for verdict in row.refusals:
            if verdict.refused is not None:
                ran = verdict.refused.ran
                out.write(own_log(f"    {verdict.check}: the "
                                  f"{verdict.refused.what} refused: "
                                  f"{verdict.refused.first_line}\n"
                                  + (f"      {ran}\n" if ran else ""),
                                  manifest.census, manifest.subject.root))

    passed = [row for row in rows if row.ok]
    out.write(f"\n  {len(passed)}/{len(rows)} mutants caught by every check "
              "they expect\n")
    if len(passed) == len(rows):
        return EXIT_OK
    for row in rows:
        if row.ok:
            continue
        why = "; ".join(
            [f"{v.check} REFUSED (its {v.refused.what} of the mutated copy "
             "refused, so it gave no verdict)"
             for v in row.refusals if v.refused is not None]
            + [f"{v.check} expected to fire and stayed SILENT ({v.detail})"
               for v in row.missed]
            or ["no check fired: the mutant is a hole in the net, not a fault "
                "of the subject"])
        out.write(f"  FAIL  {row.mutant.name} — {why}\n")
    refused = any(row.refusals for row in rows)
    out.write(next_line(
        "for each FAIL above, either widen the check so it sees the change — "
        "a surface the manifest does not record yet is the usual cause — or "
        "retire the mutant with a stated reason. An uncaught mutant is a hole "
        "in the net, not a fault of the subject."
        + (" A REFUSED is neither caught nor missed: run `compare` on a copy "
           "of the subject with that mutant applied — a refusal the mutant "
           "causes comes back there whole, and one that does not came from "
           "the machine during this run — and act on it before counting the "
           "mutant." if refused else ""), "  ") + "\n")
    return EXIT_MOVED
