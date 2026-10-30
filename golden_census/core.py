"""What every module of golden-census shares: the refusal, the roots, the
fixed-width temp directory, and the stream guards.

Nothing here knows what the subject is.
"""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import functools
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import tomllib
import unicodedata
import uuid
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from typing import Any, Literal, NamedTuple, overload

PROG = "golden-census"

#: The skill directory's name, derived from the command's. Two documents, two
#: audiences (`CLAUDE.md`): the README is found by its own name, the skill by
#: this one. Spelled as a literal in `core`, `docs` and `selftest` instead, it
#: would be five chances to disagree with the directory on disk.
SKILL_DIR = f"{PROG}-skill"

#: The two document SETS the parity check reads, as paths from the checkout
#: root; the last name of a path may carry `*`, which stands for any run of
#: characters in it. The human set is what a person reads; the agent set is
#: what an agent reads, and its first member is the file it reads first,
#: whole. `Layout` resolves each against its root and `docs` checks them.
HUMAN_SET = ("README.md", "docs/manual.md")
AGENT_SET = (f"{SKILL_DIR}/SKILL.md", f"{SKILL_DIR}/references/*.md")

#: The four directories golden-census itself knows the absolute path of, by the
#: `source` word a census `path` fold names them with — in `Roots`' own field
#: order, which is what `Roots.by_source` zips this against. One set, typed
#: once: retyped as that method's dict keys, the two can drift apart.
PATH_SOURCES = ("root", "work", "clone", "fixed-width-dir")

#: The three exit codes of every command: a pass or IDENTICAL, a FAIL or
#: differing rows (the subject moved), a REFUSED.
EXIT_OK = 0
EXIT_MOVED = 1
EXIT_REFUSED = 2

#: The rule a banner is fenced with, in every block golden-census prints.
RULE = "=" * 78

#: What a permitted movement with no stated reason is recorded as.
NO_ATTRIBUTION = "(no attribution)"

#: The git identity every commit golden-census makes is made under, given on the
#: command line: a machine with no `user.email` configured is not a reason for
#: a mutant to go unplanted or for the self-test to refuse. The fixture's
#: commits and the mutants' commits are the same identity BY CONSTRUCTION,
#: where three sites retyping it could not be.
GIT_IDENTITY = ("-c", "user.name=golden-census",
                "-c", "user.email=golden-census@invalid",
                "-c", "commit.gpgsign=false")

#: The configuration every git golden-census starts in a tree — the clone
#: of a pinned input, the subject's own checkout, the clone `mutants` plants
#: in — is given on its command line, so that what a checkout writes and
#: what `git status` lists are the repository's answer and not the global
#: configuration of the user running golden-census. The null device is
#: `core.excludesFile`, so no global ignore file hides an untracked file
#: (the repository's own `.gitignore` and `.git/info/exclude` still hold);
#: `core.autocrlf=false` and `core.eol=lf`, so no global setting turns the
#: line endings a checkout writes into `\r\n` (a `.gitattributes` of the
#: repository's own still does). The null device is also `core.hooksPath`, so
#: no hook of the repository's, and none a global `core.hooksPath` names,
#: runs in a git golden-census starts; and `core.fsmonitor=false`, so no
#: file-system monitor answers `git status` for it. Its one reader is
#: `git_command`.
GIT_SETTINGS = ("-c", f"core.excludesFile={os.devnull}",
                "-c", "core.autocrlf=false",
                "-c", "core.eol=lf",
                "-c", f"core.hooksPath={os.devnull}",
                "-c", "core.fsmonitor=false")

#: What every commit golden-census makes — the self-test's and the one
#: `mutants` makes in the clone it plants — is made with, so git starts no
#: background maintenance in a repository about to be removed: otherwise it
#: starts `git maintenance run --auto --detach` after the commit (`git gc
#: --auto` before git 2.29), which can hold `.git/objects/maintenance.lock`
#: while the tree is removed, and the removal ends in `not_removed`'s line.
#: `maintenance.auto=false` stops the first and `gc.auto=0` the second.
GIT_NO_MAINTENANCE = ("-c", "maintenance.auto=false", "-c", "gc.auto=0")

#: What every `git status` golden-census runs is asked with: the untracked
#: files listed, whatever a `status.showUntrackedFiles` of the user's says.
GIT_UNTRACKED = "--untracked-files=normal"


def git_command(*words: str) -> list[str]:
    """The argv of a git golden-census starts in a tree: `git`, then
    `GIT_SETTINGS`, then `words` — the options that name the repository,
    the subcommand and its arguments. The ONE place the settings go in, so
    `run._in_cache`, `census._git_checkout`, `mutants._git` and
    `proof._repo_of` cannot give them differently. The environment of the
    same gits is `census.git_env`'s."""
    return ["git", *GIT_SETTINGS, *words]


class Refusal(Exception):
    """A condition golden-census will not guess its way past.

    `next` is the ONE sentence the reader acts on — the command to run, the
    key to fix, the directory to point somewhere else. It is not a restatement
    of the message: the message says what is wrong, `next` says what to do
    about it, and a refusal that only says the first leaves the reader to
    invent the second. Every call of `Refusal`, or of a class the package
    defines under it, passes one; the self-check's `ss` arm walks the source
    and FAILS, naming the file and the line, on a call that does not.

    A default of `""` rather than a required argument, because the field is
    printed only when it is set: a caller outside this package that builds a
    `Refusal` from a message alone still gets a refusal, not a TypeError.

    `about` is the run this refusal INTERRUPTED — the command and the
    environment golden-census was about to use — filled in by `attaching`
    rather than by the raising site, because a refusal raised while a run is
    being built does not know it is inside one. It is set after construction
    for the same reason: the site that raises names what is wrong, and the
    site that was building the run names what the run was.
    """

    def __init__(self, message: str, next: str = "") -> None:
        super().__init__(message)
        self.next = next
        self.about = ""


class WouldNotStart(Refusal):
    """The refusal `launch` raises when a child would not START — the
    program is not there, or not executable.

    A `Refusal` like any other everywhere it is caught as one; a class of its
    own for the one caller that answers it differently from every other
    refusal a run can meet: the census's `vary` control, for which a surface
    that will not start here is a disclosed SKIP of the pin on this machine.
    The cause cannot tell the two apart — an `OSError` is behind this, behind
    a written path that could not be cleared and behind a written file that
    could not be read — and the sentence could only be matched as text.
    """


#: The word every refusal is printed under, and the opening of the line
#: that says what to do: `refusal_text` and `next_line` write them, and
#: `printed_refusal` reads them back.
_REFUSED = "REFUSED: "
_NEXT = "next: "


def refusal_text(refusal: Refusal, indent: str = "") -> str:
    """The one or two lines a refusal is printed as, WITHOUT a trailing newline.

    Every site that turns a refusal into text goes through here — the command
    line, the stderr fallback, the cost measurement, the self-check's runner
    and its two self-test callers, and the three in-band verdicts `capture`
    prints behind a two-space indent. Twelve sites would otherwise each decide
    the word `REFUSED`, some formatting an object and some building a bare
    string, and a field added to `Refusal` would reach only half of them. It
    reaches all twelve here, which is why the `next:` line is printed HERE and
    at no other site.

    `indent` is the margin the block sits behind, so the second line lines up
    under the first: `capture`'s three in-band verdicts pass two spaces, and a
    caller that prefixed the returned text itself would leave the `next:` line
    hanging in column zero under an indented `REFUSED:`.

    The `about` block goes last and behind the same margin as `next:`: the
    reader acts on the `next:` line, and what the run was about to be is
    evidence under it.
    """
    text = f"{indent}{_REFUSED}{refusal}"
    if refusal.next:
        text += "\n" + next_line(refusal.next, f"{indent}  ")
    if refusal.about:
        text += "\n" + "\n".join(f"{indent}  {line}"
                                 for line in refusal.about.splitlines())
    return text


def printed_refusal(text: str) -> tuple[str, str]:
    """The sentence and the `next` of the last refusal `refusal_text`
    printed in `text`, read back from the text.

    `capture`'s three in-band refusals — a contraband hit, a file the scan
    could not open, a scan control that will not fire — are printed and
    returned as exit 2, never raised, so a caller holding only what the
    capture printed reads them here. The lines printed directly above the
    refusal and further in than it — the hits, or the files it could not
    open, that its `next:` line points to — are the sentence's further
    lines, four spaces in, in the order printed, so whoever prints the
    sentence prints them above that `next:` line. A refusal printed with no
    `next:` line gives ""; a text with no refusal in it gives its last
    line, or `(no output)`, as the sentence."""
    lines = text.splitlines()
    marks = [i for i, line in enumerate(lines)
             if line.lstrip().startswith(_REFUSED)]
    if not marks:
        return (text.strip().splitlines() or ["(no output)"])[-1], ""
    at = marks[-1]
    depth = len(lines[at]) - len(lines[at].lstrip())
    first = at
    while (first > 0 and lines[first - 1].strip()
           and len(lines[first - 1]) - len(lines[first - 1].lstrip()) > depth):
        first -= 1
    quoted = [f"    {line.lstrip()}" for line in lines[first:at]]
    under = lines[at + 1].lstrip() if at + 1 < len(lines) else ""
    return ("\n".join([lines[at].lstrip().removeprefix(_REFUSED), *quoted]),
            under.removeprefix(_NEXT) if under.startswith(_NEXT) else "")


# ------------------------------------------------ the run a refusal stopped
#
# A refusal raised AFTER golden-census has built a command and an environment
# but BEFORE the child starts is the one place a reader has to reconstruct
# what was about to happen by hand. It carries it instead. So does a refusal
# raised over a child that RAN and was handed its record — the subject, a
# matrix row, a setup step, a counter, a `command` row's command, the
# `git status`, `git rev-parse` and `git log` of a `git-checkout` row, the
# command `probe` runs — and its block says `ran` of that child, never
# `about to run`.

#: What the block says where an environment does not exist. Two reasons, two
#: sentences: a refusal that comes before a run has a workspace, and the few
#: commands that deliberately run under golden-census's own environment.
NO_ENV_YET = "not built yet — this refusal comes before a run has one"
NO_ENV_BUILT = ("none — this command runs under golden-census's own "
                "environment rather than one a census built")


class Pending:
    """One run as it is being ASSEMBLED, for the refusal that stops it.

    Mutable on purpose. A run is built in steps — the placeholders are
    expanded, the environment is built, the child is launched — and what
    golden-census had in hand when it stopped is a different answer at each
    step. A record built once, at the end, could only be attached to the
    refusals that never happen.

    Three states, and `census.about_to_run` words the block's first line
    from them in one place: the argv as the manifest spells it; the argv
    expanded (`ran_as`); the child started and ended (`child_ended`).
    """

    def __init__(self, argv: Iterable[str], *,
                 without_env: str = NO_ENV_YET) -> None:
        self.argv: tuple[str, ...] = tuple(argv)
        #: Whether `argv`'s placeholders are resolved. Before a run's
        #: directories exist they cannot be, and a block printing `<WORK>` as
        #: though it were a path would tell the reader something untrue.
        self.expanded = False
        #: Whether the child was STARTED and has ENDED. `launch` alone says
        #: so, where `subprocess` handed the child's return code back: a
        #: program that would not start never ended, and a block saying
        #: `ran` of it would name a run that was not made.
        self.ran = False
        self.env: Mapping[str, str] | None = None
        self.without_env = without_env

    def ran_as(self, argv: Iterable[str],
               env: Mapping[str, str] | None = None) -> None:
        """The expanded argv, and the environment if there is one."""
        self.argv, self.expanded = tuple(argv), True
        if env is not None:
            self.env = env

    def child_ended(self) -> None:
        """The child was started and has ended, however it ended."""
        self.ran = True


@contextlib.contextmanager
def attaching(describe: Callable[[], str]) -> Iterator[None]:
    """Any refusal raised in here carries what the run was about to be.

    The INNERMOST description wins: a window inside a window is the narrower
    statement — one surface rather than one capture — and it is the one the
    reader needs. `describe` is a callable rather than a string because
    building the block folds every environment value, and a refusal is the
    rare case.
    """
    try:
        yield
    except Refusal as refused:
        if not refused.about:
            refused.about = describe()
        raise


# -------------------------------------------------------- launching a child
#
# How much of a child's output a refusal quotes, named once per value. WHICH
# of the two a site uses is that site's: a git failure's stderr is quoted at
# `QUOTE`, by `census._git_failed` — which `mutants`' `_head`, `clone_subject`
# and `plant` use too — and by `census._git_said`, and a `--porcelain`
# listing at
# `QUOTE_SHORT`, by `run._lists`, in `census`'s git checkout and in
# `mutants.plant`.

#: The wide quote: enough of a failed child's stderr to read the error.
QUOTE = 400

#: The short quote: a line that is evidence rather than an error — a
#: `--porcelain` listing, a version string, a precondition's own output.
QUOTE_SHORT = 200

#: How much of ONE LINE a printed row carries: a subject's version string, a
#: `census state` command's first line, a check's last log line, a hole
#: probe's output, a self-check arm's quoted refusal, the two texts of the
#: line `probe`'s clause 2 names. A display width, named once rather than
#: spelled as a literal at eleven sites beside a width of `probe`'s own.
#: `capture`'s `--twice` refusal keeps its wider `DRIFT` — that is one
#: block's own layout, decided there.
DIFFERENCE = 120

#: How much of the subject's revision line an OK row of `census` carries,
#: cut after the folds are applied.
REVISION_WIDTH = 100

#: How much of a mutant check's matched pattern a verdict quotes.
MATCH_WIDTH = 60

#: How many files or hits a refusal of `capture` lists under it, by count and
#: not by width: the contraband scan's unreadable files and its hits.
LISTED = 20

#: How many lines of one file's diff `compare` prints under its `[DIFF]` row,
#: by count; the rest is counted in a "more diff lines" line.
DIFF_LINES = 40

#: How many hits `probe` reports per stream of a run, by count.
HITS_PER_STREAM = 3

#: How many words of a git command `mutants` names a failed launch by, by
#: count.
COMMAND_WORDS = 3

#: The last sentence of a SKIP's reason when an arm could not be exercised
#: here: the arm is named as not run, and a reader is told it is not a pass.
DISCLOSED = "Disclosed, never a pass."


# ------------------------------------------ the names a capture directory owns
#
# What `capture.Recorder` writes under `<out>/<input>/`, and therefore what a
# surface's `writes` may never be recorded as. They live HERE and not beside
# the `Recorder` because the rule that enforces them is the MANIFEST loader's,
# and the import direction is capture -> manifest -> census -> core: a
# constant in `capture` is a constant the loader cannot read. One owner, so
# the name the loader refuses and the name the recorder writes cannot drift
# apart.

#: The three files every surface is recorded as, whatever it wrote, each named
#: once: the stdout stream, the stderr stream, the exit code.
STREAM_OUT = "out"
STREAM_ERR = "err"
STREAM_EXIT = "exit"

#: All three. A `writes` recorded under one of them lands on a golden written
#: three lines earlier, and the surface whose stream it replaced has no golden
#: at all.
STREAM_EXTENSIONS = (STREAM_OUT, STREAM_ERR, STREAM_EXIT)

#: The extension a SKIPPED surface is recorded under — the one file that row
#: writes, holding the reason — the suffix `compare` reads a both-sides skip
#: by, and therefore a name of the recorded namespace that `writes` may not be
#: recorded as, beside `STREAM_EXTENSIONS` and `SURFACES_FILE`. Nothing else:
#: three facts share this spelling and this constant is one of them. The other
#: two are the surface KIND (`manifest.SURFACE_KINDS`) and the manifest key
#: that makes a surface that kind (`skip = "<the reason>"`), and facts sharing
#: a spelling are not one fact.
SKIP_EXTENSION = "skip"

#: The per-input index `Recorder.finish` writes, and the marker that says a
#: directory is a capture at all. A surface named `surfaces` whose `writes`
#: ends `.json` is recorded as this file: the same collision as a stream
#: extension, against the record rather than against a golden.
SURFACES_FILE = "surfaces.json"


def folded_name(name: str) -> str:
    """A recorded name as golden-census compares it: case-folded and
    canonically decomposed, the way the file systems it runs on compare
    names — on a case-insensitive one `<surface>.OUT` IS `<surface>.out` and
    a written `.JSON` is a `.json`, and on one that also ignores Unicode
    normalization, as macOS's do, `é` written as one character IS `e`
    followed by a combining accent. The Unicode Standard's canonical
    caseless match: decomposed, case-folded, decomposed again. `ß` and `ss`
    are one name here because `str.casefold` makes them one, whether or not
    a file system does. Every comparison of a surface name or a recorded
    extension asks this."""
    return unicodedata.normalize(
        "NFD", unicodedata.normalize("NFD", name).casefold())


def row_key(input_name: str, surface_name: str) -> str:
    """A row's key, `<input>/<surface>`: what a census `scope` lists and a
    `vary` control's `surface` names, and what a fold's refusal and a SKIP
    line quote. Composed here and nowhere else, so every key is the one
    spelling `split_row_key` takes apart."""
    return f"{input_name}/{surface_name}"


def split_row_key(key: str) -> tuple[str, str]:
    """`(input name, surface name)` of a key `row_key` composed. It splits at
    the key's one `/`: the manifest loader refuses a separator in an input's
    or a surface's name (`manifest._one_component`)."""
    input_name, _sep, surface_name = key.partition("/")
    return input_name, surface_name


# ------------------------------------------------- the run's process group
#
# golden-census keeps no clock, so the exit that ends a hung run is the
# CALLER's — and a caller that kills golden-census outright, or a crash that
# kills it, leaves every subject, child and grandchild it started running.
# From outside, a crash looks like a hang: the orphans hold golden-census's
# stdout open, so the pipe never closes.
#
# One process group per run is what makes that recoverable. golden-census
# never changes its OWN group — its caller may signal that group, and a
# terminal's Ctrl-C reaches it only there — so it starts one idle ANCHOR
# process in a group of its own and every child joins that group. The group
# is printed before anything runs, because a line printed after the hang is a
# line nobody gets, and it is swept on every exit this process can see. Since
# golden-census is not a member, the sweep never signals golden-census.

#: What the anchor runs: a process that does nothing and waits to be
#: signaled. It exists to OWN the group — a group with no member is not a
#: group, and the pgid of a subject that has already exited names nothing
#: (worse, it can be recycled). `signal.pause()` rather than a sleep because
#: the anchor must outlive any subject, and a sleep is a clock.
#:
#: It runs ISOLATED (`start_anchor`): under a plain `-c` the directory
#: golden-census was started in is first on `sys.path`, and a `signal.py`
#: there would run inside the anchor in golden-census's own environment.
ANCHOR = "import signal\nsignal.pause()\n"


def start_anchor() -> subprocess.Popen[bytes]:
    """Start the anchor in a process group of its own: ONE spelling of the
    launch, used by `anchored` and by the self-check arm that builds a copy
    of the mechanism. `-I` keeps the working directory, the user site and
    every `PYTHON*` variable out of the anchor; `cwd="/"` leaves it holding no
    directory of the reader's open."""
    return subprocess.Popen(                           # noqa: S603 — see ANCHOR
        [sys.executable, "-I", "-c", ANCHOR], process_group=0, cwd="/",
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)

#: The group `launch` puts every child in, or None outside a run. ONE writer,
#: `cli.main` through `anchored`, and ONE reader, `launch` — the same shape as
#: every other fact this module owns. Threaded as a parameter instead it would
#: cross twenty call sites in nine modules, most of them several frames below
#: `main`, and every frame in between would be a place to forget it: exactly
#: the sprawl `launch` exists to prevent for its own refusal clause.
_RUN_GROUP: int | None = None


def group_line(pgid: int) -> str:
    """The one line a run that launches anything opens with.

    It carries the kill command ITSELF, not a description of one, because the
    reader of a stuck run is an agent that must be able to hand the line to a
    person unchanged. The number is not a path and is never folded: a folded
    group id kills nothing.
    """
    return (f"process group {pgid} — if this run hangs or crashes, stop "
            f"everything it started with: kill -- -{pgid}\n")


class RunGroup:
    """One run's process group: the anchor that holds it open, and the sweep
    that closes it.

    The sweep is idempotent because two things call it — a signal handler and
    the exit path underneath it — and a group swept twice must not turn the
    second `waitpid` into a crash on the way out.
    """

    def __init__(self, anchor: subprocess.Popen[bytes], pgid: int) -> None:
        self.anchor = anchor
        self.pgid = pgid
        self.swept = False

    def sweep(self) -> str:
        """SIGTERM the whole group, anchor included, then SIGCONT it, and reap
        the anchor.

        The SIGCONT is for a group a child stopped: a stopped process does not
        act on SIGTERM until it is continued, and the reap would wait forever.

        The reap is not tidiness. An unreaped anchor is a zombie, and a zombie
        keeps the group alive: on macOS, `killpg(pgid, 0)` on a group holding
        one answers `PermissionError`, not `ProcessLookupError`, so a swept
        group still probes as running. Nothing here asks that question — a group is
        proved empty by what its members were holding, never by a signal —
        but a zombie left behind would make the pgid unrecyclable and the
        printed line misleading.
        """
        if self.swept:
            return "already swept"
        self.swept = True
        outcome = "swept"
        try:
            os.killpg(self.pgid, signal.SIGTERM)
            os.killpg(self.pgid, signal.SIGCONT)
        except (ProcessLookupError, PermissionError) as exc:
            outcome = f"nothing to sweep ({type(exc).__name__})"
        with contextlib.suppress(OSError):
            self.anchor.wait()
        return outcome


@contextlib.contextmanager
def anchored(out: Any) -> Iterator[RunGroup]:
    """The run's group: started, named on the first line of `out`, swept on
    every exit this process sees.

    Nested runs are why the previous group and the previous handlers are
    RESTORED rather than cleared: `main` is called in this process by the cost
    measurement and by two self-check arms, and an inner run that cleared the
    group would send the outer run's remaining children into no group at all.

    `process_group=0` and not `start_new_session`: a new session would also
    detach the anchor from the terminal, and a terminal that can no longer
    reach the run is a run Ctrl-C cannot stop.
    """
    global _RUN_GROUP
    try:
        anchor = start_anchor()
    except (OSError, ValueError) as exc:
        raise Refusal(
            f"this run's process group could not be started: "
            f"{type(exc).__name__}: {exc}. {PROG} puts every child it starts "
            "in one group and prints the command that kills that group before "
            "anything runs; without it a crashed run leaves orphans nobody "
            "can find.",
            next="Report this as a golden-census defect, quoting the line "
            "above; nothing in your command line or files can cause "
            "it.") from exc
    group = RunGroup(anchor, os.getpgid(anchor.pid))
    was, _RUN_GROUP = _RUN_GROUP, group.pgid
    restore = _handlers(group)
    try:
        # INSIDE the `try`, so the `finally` sweeps whatever the write does: a
        # standard output already closed raises `BrokenPipeError` on this very
        # line, and a write above the `try` would leave the anchor paused
        # forever.
        out.write(group_line(group.pgid))
        out.flush()  # an arm's StringIO and a file alike: the line lands before anything runs
        yield group
    finally:
        _RUN_GROUP = was
        try:
            group.sweep()
        finally:
            restore()


def _handlers(group: RunGroup) -> Callable[[], None]:
    """Install the SIGINT and SIGTERM handlers that sweep `group`, and hand
    back the function that puts the previous ones back.

    SIGTERM's default action ends the process without unwinding, so the exit
    path's sweep would never run and the group would be exactly the orphans
    the printed line exists for. The handler sweeps and then raises
    `SystemExit`, which unwinds through `anchored`'s own `finally` — the
    second sweep is the idempotent one.

    `signal.signal` raises `ValueError` off the main thread. A run that
    reaches here from a worker keeps the sweep it has and files no handler:
    the group is still swept on the way out.
    """
    previous: list[tuple[int, Any]] = []

    def handle(number: int, _frame: Any) -> None:
        group.sweep()
        raise SystemExit(128 + number)

    for number in (signal.SIGINT, signal.SIGTERM):
        try:
            previous.append((number, signal.signal(number, handle)))
        except ValueError:
            break

    def restore() -> None:
        for number, was in previous:
            with contextlib.suppress(ValueError):
                signal.signal(number, was)

    return restore


@overload
def launch(argv: list[str], what: str, *, cwd: str | None = ...,
           env: Mapping[str, str] | None = ..., stdin: Any = ...,
           stdout: Any = ..., text: Literal[True] = ...,
           pending: Pending | None = ...
           ) -> subprocess.CompletedProcess[str]: ...


@overload
def launch(argv: list[str], what: str, *, cwd: str | None = ...,
           env: Mapping[str, str] | None = ..., stdin: Any = ...,
           stdout: Any = ..., text: Literal[False],
           pending: Pending | None = ...
           ) -> subprocess.CompletedProcess[bytes]: ...


def launch(argv: list[str], what: str, *, cwd: str | None = None,
           env: Mapping[str, str] | None = None,
           stdin: Any = subprocess.DEVNULL,
           stdout: Any = None,
           text: bool = True,
           pending: Pending | None = None
           ) -> subprocess.CompletedProcess[Any]:
    """Run a child and hand back what it did, or refuse naming it.

    "A child process that would not launch is a refusal naming it" is ONE
    clause, here, rather than one per `subprocess.run` call site — a clause
    per site is a clause a site can be missing. `what` is the whole phrase the
    sentence opens with — `[[setup]]
    'fixture'`, `the precondition command 'git'`, `the subject` — because the
    callers each name the thing they were launching differently and the
    sentence is theirs, not this function's.

    There is no `timeout` to pass, here or anywhere: golden-census cannot know
    how long a subject should run — a subject that drives a telescope runs for
    hours — so it keeps no clock and the CALLER owns the deadline. A caller
    whose deadline kills golden-census leaves the tree behind, and the process
    group printed at the top of every run's log is how that tree is found.

    This is the ONE site that puts a child in that group, which is why the
    group is a module fact read here rather than an argument every caller
    passes: a child started outside the group is a child the sweep cannot
    reach, and there is no call site left that could start one.

    A child reads nothing from golden-census's own standard input. `stdin`
    is the null device unless the caller passes one, so a child that reads
    meets end of file at once, whatever golden-census itself was started
    with — a file, a pipe, the null device, or a descriptor that is
    closed. It is decided HERE, once, for the reason the group is: a
    clause per call site is a clause a site can be missing, and a missing
    one is a census control whose verdict follows the shell the command
    was typed in. `stdin=None` is `subprocess`'s word for "inherit the
    parent's", and no call site outside the self-check's own modules
    passes `stdin` at all; arm `vvvvvv` walks the package for one that
    does.

    `text` and `stdout` exist because the runs this clause did NOT cover
    do not want the default: the census's `drift` control compares BYTES (a
    renderer's output is not text), and the self-check's closed-pipe arms
    hand a child a standard output of their own. Without them those would
    keep a `subprocess.run` of their own, which is exactly how a call site
    comes to be missing the clause.

    A text run is decoded as UTF-8 and never by the locale's encoding. The
    locale is a fact about the machine, and a subject that prints a non-ASCII
    byte would otherwise record one golden under a UTF-8 locale and another —
    or a decode error — under `LANG=C`, which is a golden about the shell the
    capture was started from. `None` for a bytes run, because naming an
    encoding at all is what puts `subprocess.run` into text mode, and the
    `drift` control is comparing bytes on purpose.

    Decoding is STRICT, and a byte that is not UTF-8 is a refusal naming the
    offset rather than a traceback: `errors="replace"` would record a golden
    of a substitute character in place of what the subject printed, and the
    whole program is a statement about what the subject printed. A subject
    whose output is not text at all is a `text=False` surface, which this
    function already takes.

    No newline is translated. The child is always run for BYTES and a text
    run is decoded here, by `_decoded`, because `subprocess.run`'s text mode
    is universal-newlines mode: it turns `\\r\\n` and a lone `\\r` into `\\n`
    before golden-census sees a byte, and a line ending is a byte of the
    golden like any other.

    `pending`, when handed in, is the record the caller's `attaching` window
    describes a refusal from, and it is told HERE that the child ended: after
    `subprocess` handed the return code back and before a byte is decoded.
    So a refusal over a child that ran — this function's own, of a byte that
    is not UTF-8, or the caller's, of how the child ended or of what it
    printed — carries a block that opens `ran`, and the refusal of a child
    that would not start carries one that opens `about to run`.
    """
    streams: dict[str, Any] = ({"stdout": subprocess.PIPE,
                                "stderr": subprocess.PIPE} if stdout is None
                               else {"stdout": stdout,
                                     "stderr": subprocess.PIPE})
    stopped: list[int] = []
    try:
        with subprocess.Popen(argv, cwd=cwd,
                              env=dict(env) if env is not None else None,
                              stdin=stdin, process_group=_RUN_GROUP,
                              **streams) as child:
            if _RUN_GROUP is not None:
                threading.Thread(target=_end_if_stopped, daemon=True,
                                 args=(child.pid, _RUN_GROUP, stopped)).start()
            try:
                out, err = child.communicate()
            except BaseException:
                child.kill()
                raise
            proc = subprocess.CompletedProcess(argv, child.poll() or 0, out, err)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WouldNotStart(f"{what} would not run: "
                      f"{type(exc).__name__}: {exc}.",
                      next="Check that the program named above is on PATH and executable, "
                      "then run the command again.") from exc
    if pending is not None:
        pending.child_ended()
    if stopped:
        raise _stop_refusal(what, stopped[0])
    if not text:
        return proc
    return _decoded(proc, what, argv if pending is None else None)


def _end_if_stopped(pid: int, pgid: int, stopped: list[int]) -> None:
    """The watcher `launch` starts beside `communicate`: wait until child
    `pid` stops or exits, and when it stopped, record the signal and end the
    group the way the sweep does so `communicate` returns.

    `WNOWAIT` leaves the child for `communicate` to reap; `WEXITED` ends this
    thread when the child exits on its own, and `ChildProcessError` when it was
    reaped first.
    """
    try:
        # typeshed declares `os.waitid` off macOS; CPython has it here.
        info = os.waitid(os.P_PID, pid,  # type: ignore[attr-defined]
                         os.WSTOPPED | os.WEXITED | os.WNOWAIT)
    except ChildProcessError:
        return
    if info is None or info.si_code != os.CLD_STOPPED:
        return
    stopped.append(info.si_status)
    for number in (signal.SIGTERM, signal.SIGCONT):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, number)


#: The refusal of a child that stopped, which a read from the terminal does:
#: `{what}` is the phrase `launch` opens its sentences with.
TTY_STOP_SAID = ("{what} stopped on a read from the terminal: golden-census "
                 "gives every child an empty standard input, so the read was "
                 "of /dev/tty (a password, a passphrase, a host-key question, "
                 "an editor), and a stopped child cannot be ended by the "
                 "process-group line; golden-census ended the group itself.")
TTY_STOP_NEXT = ("Give the command its input as an argument or a file, or "
                 "turn its prompt off (GIT_TERMINAL_PROMPT=0, SSH_ASKPASS, a "
                 "credential helper), and run again.")
OTHER_STOP_SAID = ("{what} was stopped by signal {number} ({name}) and a "
                   "stopped child cannot be ended by the process-group line; "
                   "golden-census ended the group itself.")
OTHER_STOP_NEXT = ("Find what stopped the subject (a stop it sent itself, a "
                   "job-control stop from the terminal, a debugger) and run "
                   "again without it.")


def _stop_refusal(what: str, number: int) -> Refusal:
    """The refusal of a child that was stopped by signal `number`."""
    if number in (signal.SIGTTIN, signal.SIGTTOU):
        return Refusal(TTY_STOP_SAID.format(what=what), next=TTY_STOP_NEXT)
    return Refusal(OTHER_STOP_SAID.format(
        what=what, number=number, name=signal.Signals(number).name),
        next=OTHER_STOP_NEXT)


def _decoded(proc: subprocess.CompletedProcess[bytes], what: str,
             argv: list[str] | None) -> subprocess.CompletedProcess[str]:
    """`proc` with each captured stream decoded as strict UTF-8, or the
    refusal naming the stream that failed, the byte and its offset in that
    stream. Its `next:` names what a reader can do: make the command print
    UTF-8 there, or wrap it so the raw bytes go to a file under `<WORK>`
    and a text dump of them is printed — no surface records bytes.

    `bytes.decode` and not a text-mode `subprocess.run`, because only the
    decode is wanted: no newline is translated. `launch` is the one caller.

    The sentence names the command — `argv` — only where no block will: a
    launch handed a `Pending` is made inside a window whose block names the
    argv under `ran:`, folded, and `launch` passes None for it, so the
    command is spelled once, in the folded form, and never again unfolded
    here. A table that prints the refusal without its block, `mutants`',
    prints that block's first line under it (`mutants.Refused.ran`).
    """
    decoded: list[str | None] = []
    for stream, data in (("standard output", proc.stdout),
                         ("standard error", proc.stderr)):
        try:
            decoded.append(None if data is None else data.decode("utf-8"))
        except UnicodeDecodeError as exc:
            named = "" if argv is None else f" The command was {' '.join(argv)}"
            raise Refusal(
                f"{what} ran and printed a byte no UTF-8 decoder can read: "
                f"0x{exc.object[exc.start]:02x} at byte offset {exc.start} of "
                f"its {stream} ({exc.reason}).{named}",
                next=f"Make that command print UTF-8 on its {stream}, or wrap "
                "it so it writes the raw bytes to a file under <WORK> and "
                "prints a text dump of them instead.") from exc
    return subprocess.CompletedProcess(proc.args, proc.returncode, *decoded)


def child_fault(refusal: Refusal) -> str:
    """`ExcName: message` — the OSError behind a `launch` refusal.

    The callers that do NOT raise catch the refusal rather than the
    exception, and the exception is still what their line says: `launch`
    raises `from exc`, so the cause is the original `OSError`. One sentence
    for a child that would not start, and each caller keeps the line shape it
    prints the fault in.
    """
    cause = refusal.__cause__
    if cause is None:
        return str(refusal)
    return f"{type(cause).__name__}: {cause}"


def unpunctuated(said: str) -> str:
    """`said` without the spaces it ends on and then ONE trailing period or
    colon, and nothing else: the sentence that quotes it goes on after it
    with `closed`'s period, a quote can end on its own period or on a colon
    whose child printed nothing, and a child's own `?`, `!`, `,` or `;`
    stays in the quote, because the quote is what the child printed."""
    said = said.rstrip(" ")
    return said[:-1] if said.endswith((".", ":")) else said


def closed(quote: str) -> str:
    """`quote` with the period that ends the sentence about it, unless the
    quote already ends on `?` or `!`, which closes a sentence itself."""
    return quote if quote.endswith(("?", "!")) else quote + "."


def with_next(said: str, refusal: Refusal) -> str:
    """`said` — a quote of `refusal` — and, where the refusal carries advice,
    ` — next: <the advice>` after it as a second clause; `said` as it is
    where the refusal has none.

    `refusal_text` prints the `next:` line of a refusal that is printed as
    itself. A refusal quoted inside a line of another kind, a SKIP's reason,
    a row's detail or a `(not run: …)` clause, has no such line, and the
    advice it carries is told here or not at all. The punctuation `said`
    ends on is dropped when a clause follows it, and the advice goes in
    without the period it ends on (`unpunctuated`), so the sentence that
    holds the clause closes it once.
    """
    advice = unpunctuated(refusal.next)
    return f"{unpunctuated(said)} — {next_line(advice, '')}" if advice else said


def ended(returncode: int) -> str:
    """How a child ended, from the return code `launch` hands back: `exited
    <code>`, or `was ended by signal <N>`.

    `subprocess` gives the exit code of a child that exited, which is never
    negative, and `-N` for a child that signal `N` ended. That child did not
    exit and no exit code `-N` exists, so a sentence that prints the return
    code after the word "exited" is false of it. ONE clause, here, for every
    sentence that says how a child ended.

    It speaks of the child golden-census STARTED and of no other: a shell
    that ran a program a signal ended, and then exited 143 itself, exited
    143. Whether the child left a core file is not in the return code, and
    the clause says nothing of it.
    """
    if returncode < 0:
        return f"was ended by signal {-returncode}"
    return f"exited {returncode}"


# --------------------------------------------------------------- the hole token
#
# Beside `TOKEN_RE`, and for the reason the two belong together: a consumer's
# file carries exactly two kinds of `<…>`, and both are checked before
# anything runs. A placeholder is a name golden-census RESOLVES; a hole is a
# fact only the project knows, which golden-census never guesses. The token
# lives here and not in `templates.py`: there, `census`, `manifest`, `mutants`
# and `probe` would each import the scaffolder to read a consumer's file —
# four module-level edges for one regular expression.

#: What a hole looks like. Narrow on purpose — a name is a word a shell and a
#: TOML key can both carry — so that a document quoting the SHAPE of a hole in
#: prose (`<<HOLE:NAME>>` with a placeholder name) is a hole like any other and
#: is caught by the parity check rather than slipping through as decoration.
HOLE_RE = re.compile(r"<<HOLE:([A-Za-z][A-Za-z0-9_]*)>>")


def holes_in(text: str) -> tuple[str, ...]:
    """Every hole `text` spells, once each, in the order they first appear.

    The order is the file's, not the alphabet's, because it is the order a
    refusal names them in and the order the reader fills them in: the first
    hole of a manifest is the one at the top of the file.
    """
    return tuple(dict.fromkeys(HOLE_RE.findall(text)))


def spelled(name: str) -> str:
    """A hole name as it is written in a file."""
    return f"<<HOLE:{name}>>"


def _hole_refusal(names: Sequence[str], where: str) -> Refusal:
    return Refusal(
        f"{where} still carries the unfilled hole(s) "
        + ", ".join(spelled(name) for name in names)
        + f". `{PROG} init` writes a template's holes IN PLACE, and "
        "golden-census never guesses one: a hole is a fact about this project "
        "that "
        "only this project knows.",
        next=f"Fill {spelled(names[0])} with this project's own value — and "
             "every other hole named above — then run the command again.")


def refuse_holes_in(text: str, where: str) -> None:
    """`text` still spells a hole → REFUSED naming the hole and `where`."""
    names = holes_in(text)
    if names:
        raise _hole_refusal(names, where)


# ------------------------------------------------- reading a consumer's file


def _read_source(path: str, unreadable: str, hole_named: str,
                 holes: bool) -> str:
    """The text of a consumer's file, hole-checked, or a refusal naming it.

    ONE read where each loader would do two — the hole check opening the file
    and the parser opening it again a line later — and ONE verdict on a file
    that is not UTF-8, which is otherwise a `UnicodeDecodeError` traceback out
    of `tomllib.load` at every one of them.

    Two names, because the two sentences name the file differently: a parse or
    read failure is the LOADER's sentence, prefix and all,
    while a hole is the READER's and says `the census file <path>` whatever
    prefix the loader carries.

    A file that would not OPEN says so, and does not borrow the parser's
    sentence: nothing was parsed. `does not parse: PermissionError` with a
    `next:` reading "fix the TOML error the parser names above" sends a reader
    to look for a syntax error in a file whose bytes golden-census never saw.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise Refusal(f"{unreadable} cannot be read: "
                      f"{type(exc).__name__}: {exc}",
                      next="Check that the file is there and that this run may read it; "
                      "golden-census reads every consumer file before anything "
                      "runs.") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Refusal(f"{unreadable} is not UTF-8 text: "
                      f"{type(exc).__name__}: {exc}",
                      next="Save that file as UTF-8; golden-census reads every consumer file as "
                      "text before it parses it.") from exc
    if holes:
        refuse_holes_in(text, hole_named)
    return text


def load_toml(path: str, what: str, *, prefix: str = "",
              holes: bool = True) -> tuple[dict[str, Any], str]:
    """`(the parsed document, the directory it sits in)`, or a refusal naming
    the file.

    The three loaders — manifest, census, mutants — share this one body:
    absolutize, `isfile`, open `rb`, `tomllib.load`, refuse by name. `what` is
    the file's own word ("manifest", "census file", "mutants file") and
    `prefix` — `census <path>: `, the opening every other census refusal has —
    is the whole of how a prefixed file is named: `census <path>: does not
    parse`, `census <path>: no such file`, `census <path>: is not a file` (a
    path that exists — a directory, say), where the manifest, which has no
    prefix, says `the manifest <path> does not parse`, and `no manifest at
    <path>` for both of the last two. The read and decode sentences are
    `_read_source`'s, built as the name, a space and the verb, so the prefix
    reaches it without its trailing space.

    The HOLE check is the same rule and rides here rather than at three call
    sites, each of which would type the loader's `what` word a second time and
    open the file a second time. It names the file the way the hole refusal
    names it — `the census file <path>`, prefix or no prefix — because that
    sentence is the reader's and not the loader's.
    `load_template` passes `holes=False`: a template is the one file whose
    holes are the point.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        if prefix and os.path.exists(path):
            raise Refusal(f"{prefix}is not a file",
                          next=f"Point the path above at the {what} itself.")
        raise Refusal(f"{prefix}no such file" if prefix
                      else f"no {what} at {path}",
                      next="Check the path above and point it at the file that is there.")
    named = prefix.rstrip() if prefix else f"the {what} {path}"
    text = _read_source(path, named, f"the {what} {path}", holes)
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise Refusal(f"{named} does not parse: "
                      f"{type(exc).__name__}: {exc}",
                      next="Fix the TOML error the parser names above; the file is read "
                      "before anything runs.") from exc
    return document, os.path.dirname(path)


def read_text(path: str) -> str | None:
    """The text of a file, or None when it cannot be read as UTF-8.

    For the readers whose absence is a verdict and not a refusal — a
    template's source file the parity check names, a scaffolded file the
    self-test compares, a README an arm reads CHECKED lines out of. ONE
    function, where `templates` and `selfcheck` would each carry a
    byte-identical copy.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def bad_byte(undecodable: UnicodeDecodeError) -> str:
    """`0x.. at byte offset N (reason)` — the byte a strict UTF-8 decode of a
    FILE stopped at, its offset from the file's first byte, and the decoder's
    own reason.

    ONE owner for the two readers that say it: `_capture_text`, of a file in
    a capture directory or one a surface wrote, and `compare.read_allow`, of
    an `--allow-diff` table. The offset is the exception's `start`, which
    counts from the first byte of what was decoded, so both hand over an
    exception raised by decoding the WHOLE file in one call. A printed
    stream's sentence is `_decoded`'s, which names the stream.
    """
    return (f"0x{undecodable.object[undecodable.start]:02x} at byte offset "
            f"{undecodable.start} ({undecodable.reason})")


def _capture_text(path: str) -> tuple[str | None, str]:
    """One recorded file's text, or `(None, why not)`.

    A capture directory holds text: every file in it is written by `Recorder`,
    UTF-8 and `newline="\n"`. One that is not — a binary file somebody
    dropped in, an editor's backup, a `.DS_Store` — would be a
    `UnicodeDecodeError` traceback out of `compare`, out of `mutants`'
    comparison and out of `capture --twice`, and crashing is never the
    appropriate choice.

    The absence is RETURNED rather than raised, so the caller finishes its
    walk and names every such file in one refusal. A reader who unpacks a Mac
    tarball has one `._<name>` beside every golden, and the whole list is what
    they need to act once.

    The two absences keep their own words, because the caller says different
    things about them: a file that could not be DECODED is not a row of this
    capture, and a file that could not be OPENED may be one.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as unreadable:
        return None, (f"cannot be read: {type(unreadable).__name__}: "
                      f"{unreadable.strerror}")
    try:
        return raw.decode("utf-8"), ""
    except UnicodeDecodeError as undecodable:
        return None, "not text: " + bad_byte(undecodable)


def load_rows(path: str, named: str) -> list[Any]:
    """The rows of a GENERATED include file — a JSON array, or the `rows` array
    of a TOML document — or a refusal naming it.

    The fifth loader, through the three seams the other four have: one read,
    the hole check, the placeholder check. Without them an include row
    spelling `<<HOLE:ARG>>` loads and is refused mid-capture, from inside a
    thread pool, as an unknown PLACEHOLDER — the wrong sentence about the
    wrong rule at the wrong time.

    `named` is the whole phrase the sentences name the file with (`<manifest>:
    [surfaces.flags] rows: include <path>`), not a bare word, because this
    file is identified by the surface that includes it and not by a kind of
    its own. The row-shape refusals stay with the caller: what a row must
    look like is the manifest's rule, not this function's.
    """
    text = _read_source(path, named, named, True)
    try:
        if path.endswith(".json"):
            rows = json.loads(text)
        else:
            rows = tomllib.loads(text).get("rows", [])
    except (ValueError, tomllib.TOMLDecodeError) as exc:
        raise Refusal(f"{named} does not parse: "
                      f"{type(exc).__name__}: {exc}",
                      next="Fix the error above in that generated row file, or "
                      "regenerate it.") from exc
    return rows if isinstance(rows, list) else []


def strings(value: Any, where: str) -> tuple[str, ...]:
    """A list of strings, or a refusal naming the key. ONE copy, where the
    three loaders would each carry a byte-identical `_strings` of their
    own."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise Refusal(f"{where}: must be a list of strings",
                      next="Write that key as a list of strings, [\"a\", \"b\"].")
    return tuple(value)


def table(document: Mapping[str, Any], key: str, where: str, *,
          label: str | None = None) -> dict[str, Any]:
    """The table `key` names — an absent key is an empty one — or a refusal
    naming it.

    `label` is the bracketed name the sentence prints when it differs from the
    key: `[surfaces.help]` for the `help` entry of a `[surfaces]` table.
    """
    value = document.get(key, {})
    if not isinstance(value, dict):
        raise Refusal(f"{where}: [{label or key}] must be a table",
                      next="Write that key as a table.")
    return value


def only_keys(raw: Mapping[str, Any], allowed: tuple[str, ...], where: str,
              document: str) -> None:
    """Every key of this table is one golden-census reads, or a refusal naming
    the ones that are not.

    ONE copy, beside `strings` and `table`, because all three loaders ask it of
    every table they read and a key rule written three times is a key rule that
    drifts twice. `allowed` is declared beside the code that READS those keys,
    so a key gained there and not here is a key the loader reads and this
    refuses — the loud direction, and the reason the tuple sits where it does.

    Every unknown key is named, sorted, and so is every key the table takes: a
    reader with two misspellings fixes both in one pass, and the list of what
    the table takes is the answer to the question a misspelling asks. No cap
    and no "did you mean" — a classifier is a rule the reader then has to know.
    """
    unknown = sorted(set(raw) - set(allowed))
    if not unknown:
        return
    # Refused, not skipped, because a key nobody reads is a key doing
    # nothing, and a misspelled one is a key doing nothing under the name of
    # one that would. The message says what was found and what the table
    # takes and gives no reason: the reader of a refusal needs the fix.
    raise Refusal(
        f"{where} carries "
        + ("a key" if len(unknown) == 1 else f"{len(unknown)} keys")
        + " golden-census does not read: " + ", ".join(unknown)
        + ". That table takes " + ", ".join(sorted(allowed)) + ".",
        next=f"Fix the spelling, or delete that key. {document} is "
        "authoritative for every key of this table.")


#: The two faults this package re-raises wherever it catches broadly, because
#: they are not a verdict about anything: the interpreter has run out of a
#: resource, and the next line of golden-census code is as likely to hit the
#: same
#: wall as the one that raised. Reporting them as a result would print a row
#: about the machine while claiming to describe the code.
UNREPORTABLE: tuple[type[BaseException], ...] = (MemoryError, RecursionError)


# ------------------------------------------------------------------ the report
#
# `probe` prints the same block for its five clauses, and nothing about a
# report is about the self-check: `core` is where the things every module
# shares live, and a printed block is one of them.


def skip_line(what: str) -> str:
    """The opening of every per-row `[SKIP]` line — two spaces, the bracket,
    two spaces — and what was skipped, with no newline.

    ONE producer, so an agent matching `  [SKIP]  ` at the start of a line
    finds every skipped row: a `Report`'s SKIP pair, a capture's surface
    declared unrunnable, and a capture's whole input whose pinned tree could
    not be cloned. `compare`'s summary of the rows skipped on both sides is
    a line about many rows, not a row, and keeps its own shape.
    """
    return f"  [SKIP]  {what}"


#: What a check row's detail opens with when it reports what was measured: the
#: `Report` prints a detail as given, so each arm spells the prefix through
#: this one name.
ACTUAL = "actual: "


class Report:
    """One printed block: a banner fenced by two rules, a `[PASS]`/`[FAIL]`
    line and its 11-space detail line per row, the lines the row TOLD under
    its detail at the same margin, the `[SKIP]` pairs after them, and the
    `N/M passed` tally with its `REFUSED after row N` and SKIPPED suffixes.

    The self-check and every self-test group are instances — ONE printer, so
    a second copy cannot drift from this one. `guard` is part of the format
    for the same reason: `[FAIL]  !` for a raise belongs to every block, and
    a block without it whose body raises takes the whole run with it and
    reports nothing at all.

    `quiet` is the one knob on that format, and it is the whole of the
    difference between a block somebody ASKED for and a block that runs in
    front of a command they asked for: quiet, the block prints its verdict
    and nothing else — the failing rows, the tally, the disclosed SKIPs.
    A reader who typed `capture` wants the capture's log; a control that
    passed has nothing to tell them, while a control that FAILED and a SKIP
    that was never exercised both do, so neither is ever dropped.
    """

    def __init__(self, out: Any, banner: str, quiet: bool = False) -> None:
        self.out = out
        self.banner = banner
        #: Print the verdict alone, the tally carrying the banner's words.
        #: Set by `controls.census_check` in front of `capture`, `compare`
        #: and `mutants`, the commands nobody asked a block of.
        self.quiet = quiet
        self.rows: list[tuple[str, bool, str, str, tuple[str, ...]]] = []
        self.skipped: list[tuple[str, str]] = []
        #: True once a body handed to `guard` raised a `Refusal`. The tally
        #: says so: a block that refused stopped, and `N/N passed` alone reads
        #: as a clean run of N controls when it is a clean run of the N that
        #: got to run.
        self.refused = False

    def check(self, label: str, ok: bool, detail: str, *,
              next: str = "", told: tuple[str, ...] = ()) -> None:
        """One row. `next` is the sentence printed under a FAIL — the same
        field a `Refusal` carries, for the same reason, and printed only when
        the row is red: a PASS has nothing for the reader to do.

        `told` is what the control's own runs printed that qualifies its
        verdict without deciding it — a `vary` control's `clone:` lines —
        one line each, printed under the detail at its margin, PASS or FAIL,
        wherever the row is printed: a reader who trusts the verdict reads
        them beside it. A quiet block prints no passing row, and so none of
        its lines either; the command after it prints its own.
        """
        self.rows.append((label, ok, detail, next, told))

    def skip(self, label: str, reason: str) -> None:
        self.skipped.append((label, reason))

    def raised(self, exc: BaseException) -> None:
        """A `[FAIL]  !` row for something that raised instead of reporting."""
        self.check("!  a control raised instead of reporting a verdict — every "
                   "control after it did not run",
                   False, f"{ACTUAL}{type(exc).__name__}: {exc}")

    def guard(self, body: Callable[[], None]) -> None:
        """Run `body`; a raise becomes a `[FAIL]  !` row rather than an abort.

        A `Refusal` is re-raised: it is a statement about the RUN, and its
        caller prints it as the REFUSED line under the rows. Everything else
        is a statement about the CODE, and a block that aborted has reported
        nothing at all. `UNREPORTABLE` is re-raised too — see `core`.
        """
        try:
            body()
        except Refusal:
            self.refused = True
            raise
        except Exception as exc:
            if isinstance(exc, UNREPORTABLE):
                raise
            self.raised(exc)

    def _write_row(self, label: str, ok: bool, detail: str,
                   next_: str, told: tuple[str, ...]) -> None:
        self.out.write(f"  [{'PASS' if ok else 'FAIL'}]  {label}\n"
                       f"           {detail}\n")
        for line in told:
            self.out.write(f"           {line}\n")
        if next_ and not ok:
            self.out.write(next_line(next_, " " * 11) + "\n")

    def _write_skips(self) -> None:
        for label, reason in self.skipped:
            self.out.write(f"{skip_line(label)}\n           {reason}\n")

    def _write_tally(self, failed: int) -> None:
        """The one line both shapes end on, written in one place so the loud
        block and the quiet one can never state the count two ways."""
        # The quiet shape has no banner above it, so the noun goes on the
        # line: `3/3 census controls passed`, the banner's own words.
        noun = f" {self.banner.lower()}" if self.quiet else ""
        self.out.write(f"  {len(self.rows) - failed}/{len(self.rows)}{noun} "
                       "passed")
        if self.refused:
            # A block whose body raised a `Refusal` prints no row for it —
            # the refusal is a statement about the RUN and its caller prints
            # it under the rows — so a bare `N/N passed` would read as a clean
            # run of everything. The tally says where it stopped instead.
            self.out.write(f", REFUSED after row {len(self.rows)}")
        if self.skipped:
            self.out.write(f", {len(self.skipped)} arm(s) SKIPPED (disclosed, "
                           "never a pass)")
        self.out.write("\n")

    def finish(self) -> int:
        """Print the block and return how many rows FAILED.

        ONE order in the quiet shape, whatever happened: the failing rows,
        the tally, the SKIPs — so a reader who has learned where the verdict
        sits finds it in the same place on a run that went red as on one that
        did not, and the sentence a caller writes under it (the refusal that
        stops the command) is always the last thing printed.
        """
        failed = [row for row in self.rows if not row[1]]
        if self.quiet:
            self.out.write("\n")
            for row in failed:
                self._write_row(*row)
            if failed:
                self.out.write("\n")
            self._write_tally(len(failed))
            self._write_skips()
            return len(failed)
        self.out.write(f"\n{RULE}\n{self.banner}\n{RULE}\n")
        for row in self.rows:
            self._write_row(*row)
        self._write_skips()
        self.out.write("\n")
        self._write_tally(len(failed))
        return len(failed)


class Roots(NamedTuple):
    """Every absolute path the normalizer folds away."""

    root: str
    work: str
    clone: str | None = None
    #: The fixed-width TMPDIR the subject runs under, or None outside a
    #: capture (the self-check's controls do not always run a subject).
    fixed: str | None = None

    def by_source(self, source: str) -> str | None:
        """The directory a census `path` fold's `source` word names.

        Zipped against `PATH_SOURCES` rather than re-typed as dict keys: a
        field added to this record without a `source` word for it makes the
        zip refuse, where two hand-kept lists could drift apart.
        """
        return dict(zip(PATH_SOURCES, self, strict=True))[source]


def path_forms(path: str) -> tuple[str, ...]:
    """Every spelling of `path` a command can print: as given, and as
    `os.path.realpath` gives it — macOS serves /tmp and /private/tmp as one
    directory, and a command that resolved its path prints the form it was
    not handed. Deduplicated, in that order. `fold` replaces these, and the
    census's capture-time overlap test looks for them."""
    return tuple(dict.fromkeys((path, os.path.realpath(path))))


#: Where a directory's NAME ENDS, as a lookahead after the directory: at the
#: end of the text, at a `/`, or at any character that cannot continue the
#: name. What continues a name is a word character or a `-` — so
#: `<root>-old`, `<root>2` and `<root>_x` are OTHER directories, which `fold`
#: leaves alone for the contraband scan to refuse — while a `.` ends it:
#: `<root>.` at a sentence's end, `<root>.bak` and a path a command derived
#: from its output path by adding an extension (`<WRITES>.json`) all fold.
NAME_ENDS = r"(?![\w-])"

#: Where a PATH CAN START, as a lookbehind: not after a character that can
#: be inside a path name — a word character, `.`, `~`, `-` — so a home root
#: counts where a word can start, or right after an option word that begins
#: with `-` (`capture.home_root_pattern` consumes the option: `-I/home/ci`,
#: `-isystem/home/ci`), while `src/home/page.tsx` and `foo-I/home/x` are
#: relative paths. A path right after a fold token — `<REPO>/home/x`, a path
#: under a folded root — does not start there either; which tokens a text was
#: folded with is its caller's vocabulary, which a pattern cannot know, so
#: `after_placeholder` decides it.
PATH_START = r"(?<![\w.~-])"


def after_placeholder(text: str, at: int, tokens: Collection[str]) -> bool:
    """True when the text before `at` ends with one of `tokens`, the fold
    tokens the caller folded this text with, so what starts at `at`
    continues a folded directory rather than starting a path of its own:
    `<REPO>/home/x` names `home/x` under the subject root, while
    `<string>/home/x` or `<BR>/home/x` is an absolute path after a tag the
    subject printed. The caller's vocabulary decides, never a token's shape,
    and the text is not copied."""
    return text.endswith(tuple(tokens), 0, at)


def fold(text: str, pairs: Iterable[tuple[str, str]]) -> str:
    """`text` with every path in `pairs` replaced by its token.

    The one fold ALGORITHM: each path in every spelling `path_forms` names;
    longest first, so a path inside another — an output file under the
    work directory, a clone under the cache directory — is not half-replaced. Three
    callers share it — `census`'s path normalizer, its own-log `<PYTHON>` pass
    and `probe`'s fold of a run's output — where a fix to one copy would miss
    two. The VOCABULARIES stay each caller's: which directories fold to which
    tokens is a census's or a probe's business, and this function never
    chooses one.

    Deduplicated by first occurrence rather than through a set, so two
    tokens for one path resolve the same way on every run.

    A directory is folded only where its name ends (`NAME_ENDS`): the path
    followed by `-old` or `2` names another directory, and a token there
    would be a guess the contraband scan then could not see; followed by a
    `.`, as in `<path>.json`, it is folded. The token goes
    in through a function, so it is never read as a replacement template.
    """
    forms = [(form, token) for path, token in pairs
             for form in path_forms(path)]
    for path, token in sorted(dict.fromkeys(forms),
                              key=lambda pair: -len(pair[0])):
        def replacement(_match: re.Match[str], token: str = token) -> str:
            return token

        text = re.sub(re.escape(path) + NAME_ENDS, replacement, text)
    return text


# ------------------------------------------------- the fixed-width TMPDIR


def fixed_dir_room(base: str, width: int) -> tuple[str, int]:
    """`(normalized base, characters left for the leaf name)`.

    Arithmetic on a string: it makes nothing, and it reads the working
    directory only to resolve a relative `base` (`os.path.abspath`), which no
    command passes: every caller hands it an absolute literal or `temp_base()`,
    and `require_temp_root` refuses a relative TMPDIR first. It is the ONLY
    place the width rule is decided. That matters because the rule has
    to be exercisable on widths this machine may not have — a control that
    could only test the refusal by building a 60-character directory passes on
    a short temp root and RAISES on every other machine.

    The separator is asked of `os.path.join`, the same function
    `make_fixed_dir` builds the path with, rather than subtracted as a
    constant 1. A root that IS the separator adds none — `os.path.join("/",
    leaf)` is `"/" + leaf` — so the constant was one too many there and only
    there, and `make_fixed_dir` raised its own "report this as a
    golden-census defect" refusal over a path one character short.
    """
    base = os.path.abspath(base).rstrip("/") or "/"
    return base, width - len(os.path.join(base, ""))


def widest_root(width: int) -> int:
    """The widest temp root a directory of exactly `width` characters can be
    made under: the root, one separator and at least one character of name.
    The ONE place the "less two" is written; `fixed_dir_room` decides the
    same rule for a real root, this states it for a width.

    Two statements of one rule, kept apart on purpose: the census control
    `controls._fixed_width_control` asks `fixed_dir_room` on constructed
    roots and holds the boundary it finds against this number, so either
    statement moving alone turns that control red. Derived from
    `fixed_dir_room`, this would agree with it by construction, and the
    control would ask the owner what the owner says."""
    return width - 2


def fixed_dir_refusal(base: str, width: int) -> Refusal:
    """The refusal a too-wide temp root earns, with the command to run it
    under taken from `Platform`: the advice is one platform's, and the reader
    is on whichever platform this is."""
    base, _room = fixed_dir_room(base, width)
    widest = widest_root(width)
    # The rule and the way out, and no cause. The rule is the width because
    # the subject prints temp paths through a fixed-width slice, and under a
    # wider root the slice records half a path that no fold recognizes; the
    # census pins the width so the machine does not decide that. A root of
    # exactly `width` characters leaves no room for a name, which is why the
    # figure printed is `widest`, two less. Why the root is wide is a fact
    # the run does not hold: a TMPDIR set inside this machine's own temp
    # root is one cause, and naming it here would be a guess about this
    # reader's setup.
    return Refusal(
        f"the temp root {base!r} is {len(base)} characters long; a capture "
        f"needs a root of at most {widest}, because the census pins the "
        f"subject's TMPDIR to {width} characters. (`compare --against` "
        "needs no temp directory and runs at any width.)",
        next="Run the same command with "
        f"{Platform.detect().short_root_advice}, or point TMPDIR at any "
        f"directory of at most {widest} characters.")


def make_fixed_dir(base: str, width: int) -> str:
    """A fresh directory under `base` whose absolute path is EXACTLY `width`
    characters long.

    A subject that slices its child's stderr at a fixed width does so before
    golden-census sees it, so the width of the temp root — not the subject's
    behavior — decides what reaches the golden. Pinning the width moves that
    decision out of the machine and into the census.

    The name is as long as the pin asks, from as many `uuid4().hex` as it
    takes, and the file system says whether it can be made: its limit on a
    name is its own, so it is measured by `os.mkdir` here and not stated
    anywhere, least of all by the census loader, which cannot know it. A
    name the operating system calls too long (`ENAMETOOLONG`) is the
    census's own: a refusal naming the base, the width, the name's length
    and the operating system's answer, whose `next:` line asks for a lower
    N. Any other `OSError` but `FileExistsError` is a root that stopped
    taking directories after `require_temp_root` made one there for this
    command, and is raised as it is. The two are told apart by the
    operating system's answer and by nothing else: the name's length is
    the one thing a census decides about the directory. A directory made
    here and not handed back is removed here, before the refusal is raised:
    no caller ever holds it.
    """
    base, room = fixed_dir_room(base, width)
    if room < 1:
        raise fixed_dir_refusal(base, width)
    for _ in range(64):
        leaf = "".join(uuid.uuid4().hex
                       for _hex in range(room // 32 + 1))[:room]
        path = os.path.join(base, leaf)
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            continue
        except OSError as error:
            if error.errno != errno.ENAMETOOLONG:
                raise
            raise Refusal(
                f"could not make a directory of exactly {width} characters "
                f"under {base!r}, a name of {room} characters: "
                f"{error.strerror or error}",
                next="Lower N in the census's "
                "`<FIXED-WIDTH-DIR:N>`.") from None
        if len(path) != width:      # asserted, never assumed
            os.rmdir(path)
            raise Refusal(
                f"made {path!r} at {len(path)} characters, not the required "
                f"{width}",
                next="Report this as a golden-census defect: the width rule "
                "is its own arithmetic, and nothing in your files can cause "
                "it.")
        return path
    raise Refusal(
        f"could not make a fresh {width}-character directory under "
        f"{base!r} in 64 attempts",
        next=f"Check that {base!r} is writable and has space, then run the command again.")


def temp_base() -> str:
    return os.environ.get("TMPDIR") or tempfile.gettempdir()


#: Why a path spelled with `..` is refused, for the temp root and the cache
#: directory alike: the sentence after the variable and its value.
_DOTDOT = ("after a symbolic link, `..` names the parent of the link's target, "
           "not the directory the path spells before it, so the path can name "
           "a directory other than the one it spells.")


def require_temp_root() -> None:
    """Refuse a relative temp root, one spelled with `..`, and one no
    directory can be made in, before anything runs.

    The ONE check of the root `temp_base` names; `cli.main` is its only
    caller, ahead of every command `cli.needs_temp_root` says makes a
    directory under it. It TRIES — one directory made and removed — so what
    the refusal reports is the answer the operating system gave, not a guess
    from a mode bit. It repairs nothing: no root is created and no root but
    the one `temp_base` names is tried, because a capture under a root the
    reader did not name is bound to a machine nobody chose.

    A set TMPDIR that `os.path.isabs` calls relative is refused FIRST, by
    its value alone, before anything is tried: golden-census starts children
    in directories of their own (`cwd=`), and a relative path names a
    different directory in each. So is an absolute one holding a `..`
    component: after a symbolic link the operating system takes `..` to the
    parent of the link's target, while Python's spelling of a path under the
    root drops it with the name before it (`os.path.normpath` in `own_log`'s
    fold; `os.path.abspath` in `tempfile.mkdtemp`'s answer, from Python
    3.12), so a directory is made in one place and written to, folded and
    removed in another. Nothing is made and the path is not resolved, so
    each sentence names the value as given, and its `next:` line asks for
    an absolute path, or for one spelled without `..`. An absolute path
    spelled with `/./`, a doubled slash or a closing slash names one
    directory whatever the working directory and whatever links it
    crosses, and is taken.

    Every other sentence is chosen by what raised, never by TMPDIR alone. A set
    TMPDIR is returned by `temp_base` unread, so only making the directory
    can fail, and the sentence names the value. An unset or empty one sends
    `temp_base` to `tempfile.gettempdir()`, which either raises, finding no
    candidate it can write a file in — then there is no root to name — or
    returns one it has written a file in. Making a directory under THAT root
    fails when the root changed after `gettempdir` answered, which caches
    its answer for the life of the process, and that sentence names the root
    it returned. Every value is printed with `!r`: a TMPDIR holding a quote
    or a newline stays one quoted value on one line.

    `temp_base` stays a reader of a string: the width arithmetic and the
    display folds ask it about roots that need not exist, and a check there
    would refuse them.
    """
    value = os.environ.get("TMPDIR")
    absent = "unset" if value is None else "empty"  # read only when not value

    def refused(sentence: str, directory: str = "any directory") -> Refusal:
        """`sentence` with the `next:` line of all five refusals, which
        differ only in `directory`: what it asks TMPDIR to point at. The
        root is unusable here, so the platform's short-root advice, which
        can name that very root, is not offered; the too-wide root's
        refusal above keeps it."""
        return Refusal(sentence, next=f"Point TMPDIR at {directory} you can "
                       "write in, then run the command again.")

    if value and not os.path.isabs(value):
        raise refused(
            "golden-census does not take a relative temp root (TMPDIR is "
            f"{value!r}): a relative path names a different directory for "
            "each child golden-census starts in a directory of its own.",
            "the absolute path of a directory")
    if value and ".." in value.split(os.sep):
        raise refused(
            "golden-census does not take a temp root spelled with `..` "
            f"(TMPDIR is {value!r}): {_DOTDOT}",
            "the absolute path, spelled without `..`, of a directory")
    try:
        root = temp_base()
    except OSError as exc:
        # Only `tempfile.gettempdir()` raises here, so TMPDIR is unset or
        # empty: `temp_base` returns a set one without reading the disk.
        raise refused(
            "golden-census could not make a directory under its temp root: "
            f"TMPDIR is {absent}, and Python's `tempfile.gettempdir()` found no "
            f"directory it could write in ({exc.strerror or exc}). This "
            "command's scratch directories go under the temp root, and "
            "golden-census does not create one.") from None
    try:
        made = tempfile.mkdtemp(prefix="golden-census-root-", dir=root)
    except OSError as exc:
        raise refused(
            f"{_not_made_under_root(exc)} This command's scratch directories "
            "go there, and golden-census does not create that root or try "
            "another.") from None
    remove_tree(made)


def _not_made_under_root(exc: OSError) -> str:
    """The sentence `require_temp_root`'s refusal of a root no directory
    can be made in opens with: the root, and the operating system's reason
    for `exc`. A set TMPDIR is named as given; an unset or empty one names
    the root Python's `tempfile.gettempdir()` returned, which it caches for
    the life of the process, and says which of the two TMPDIR is."""
    value = os.environ.get("TMPDIR")
    if value:
        return ("golden-census could not make a directory under its temp root "
                f"(TMPDIR is {value!r}): {exc.strerror or exc}.")
    absent = "unset" if value is None else "empty"
    return ("golden-census could not make a directory under its temp root "
            f"{temp_base()!r}: {exc.strerror or exc}. TMPDIR is {absent}, so "
            "that root is the one Python's `tempfile.gettempdir()` returned.")


def require_cache_dir() -> None:
    """Refuse a cache directory that cannot be made or written in, before
    the clone that needs it is made: the ONE check of `Platform.cache_dir`,
    called by `run.Place._ask_cache` alone, once per run, right before the
    run's first clone. A `HOME` that is set and is not an
    absolute path — the empty string among them — is refused first: a
    relative one names a different home from every working directory. An
    unset `HOME` is `os.path.expanduser`'s own fallback, the account's
    home. Then the variable `Platform.cache_spelled` names, when it is set,
    is refused when its value holds a `..` component, by
    `require_temp_root`'s rule for TMPDIR: after a symbolic link the
    operating system takes `..` to the parent of the link's target, while
    `run.clone_input`'s `os.path.abspath` and Python's `tempfile.mkdtemp`
    drop it with the name before it, so the cache would be made in one
    directory and the clone kept in another. Nothing is made and the path
    is not resolved. Then it TRIES — makes the directory where it is
    missing, and makes and removes one inside it — so the refusal reports
    the operating system's answer. No other directory is tried: the temp
    root is emptied by the operating system.
    """
    home = os.environ.get("HOME")
    if home is not None and not os.path.isabs(home):
        raise Refusal(
            f"HOME is {home!r}, not an absolute path. golden-census takes "
            "only an absolute HOME for the home its cache directory is under.",
            next="Run the same command with HOME set to an absolute path.")
    platform = Platform.detect()
    variable, value = platform.cache_spelled()
    if value is not None and ".." in value.split(os.sep):
        raise Refusal(
            "golden-census does not take a cache directory spelled with `..` "
            f"({variable} is {value!r}): {_DOTDOT}",
            next=f"Run the same command with {variable} spelled without "
            "`..`.")
    cache = platform.cache_dir()
    names = (f"{platform.cache_variable} or HOME" if platform.cache_variable
             else "HOME")
    try:
        os.makedirs(cache, exist_ok=True)
        made = tempfile.mkdtemp(prefix="golden-census-cache-", dir=cache)
    except OSError as exc:
        raise Refusal(
            "golden-census could not write in its cache directory "
            f"{cache!r}: {exc.strerror or exc}. The clones of this "
            "manifest's pinned inputs are kept there, and nowhere else.",
            next="Make that directory one you can write in, or run the same "
            f"command with {names} pointing at a directory you can write "
            "in.") from None
    remove_tree(made)


def next_line(next: str, indent: str) -> str:
    """The ONE line that says what to do about a red verdict.

    Five producers, four margins: `refusal_text` behind the caller's margin
    plus two spaces, `Report.finish` behind eleven, `compare`'s and
    `mutants`' exit-1 verdicts — which are neither a `Refusal` nor a `Report`
    row — behind two, and `with_next`, which says a refusal's advice inside
    a sentence behind no margin. The WORDING is one decision here and the
    indent stays each caller's, because where a block sits on the page is
    the block's business. No trailing newline: four of the five are building
    a longer string.
    """
    return f"{indent}{_NEXT}{next}"


#: What a `Difference` says when the texts differ in nothing a line holds.
FINAL_NEWLINE = "the files differ in their final newline"


class Difference(NamedTuple):
    """The first difference between two texts.

    `line` is the 1-based number of the line that moved, with `first` and
    `second` sliced to the caller's width — or None, and then the texts differ
    in their FINAL NEWLINE and `tail` says which of the two carries it. Two
    fields rather than one because a caller lays the two cases out
    differently: one names a line and quotes both, the other names no line at
    all.
    """

    line: int | None
    first: str
    second: str
    tail: Literal["", "first", "second"] = ""

    def said(self) -> str:
        """The final-newline case as ONE line, for a caller with room for one.

        Empty for a difference that names a line: that one is the caller's to
        lay out, and this sentence would say nothing it does not already show.
        """
        if self.line is not None or not self.tail:
            return ""
        return f"{FINAL_NEWLINE}; the {self.tail} has it"


def _final_newline(one: str, other: str) -> Literal["", "first", "second"]:
    """Which of two texts ends in a newline the other does not, or ""."""
    ends, other_ends = one.endswith("\n"), other.endswith("\n")
    return "" if ends == other_ends else ("first" if ends else "second")


def lines_of(text: str) -> list[str]:
    """`text` as its lines: split on `"\\n"` alone, the final newline ending
    the last line rather than starting an empty one, and `[]` for `""`.

    The ONE line splitter for texts golden-census records and compares.
    `str.splitlines` also breaks at `\\r`, a form feed, a vertical tab and the
    Unicode separators, so a reader walking its lines is blind to a change of
    line ending and records half of a line holding one of the others. Here a
    `\\r` stays inside the line it ends, where a walk can name it.
    """
    return text.removesuffix("\n").split("\n") if text else []


def printable_text(text: str) -> str:
    """`text` with every LINE that holds a character `str.isprintable`
    rejects replaced by that line's `!r` spelling, and every other line
    unchanged.

    The ONE rule for text golden-census prints that a subject, a golden or
    a child wrote. A terminal ACTS on some characters instead of showing
    them — an escape sequence can move the cursor up and erase the rows and
    the verdict printed above — so a line that holds one is printed in its
    `!r` spelling, where the character reads as `\\x1b`. `isprintable`
    rejects the C0 and C1 controls, among them ESC and BEL, the characters
    `str.splitlines` breaks a line at, and the other non-printing
    characters and separators; a line holding any of them is quoted whole.
    Tab is kept: it is the one control character an ordinary line holds, a
    printed one is harmless, and quoting it would turn every indented line
    into a quoted one. Lines are split on `"\\n"` alone, as `lines_of` does,
    so a multi-line text keeps its lines and each line's own newline.
    """
    return "\n".join(
        line if all(char == "\t" or char.isprintable() for char in line)
        else repr(line)
        for line in text.split("\n"))


def _windows(first: str, second: str, width: int) -> tuple[str, str]:
    """Two differing lines cut to `width` characters each, the cut placed
    where they differ.

    The head of each line when the heads differ; otherwise a window of each,
    opened by `…`, around the first character that differs — a change of line
    ending sits at the END of a line, and a head cut of a line longer than
    the width would quote two equal strings under a verdict that they differ.
    """
    if first[:width] != second[:width]:
        return first[:width], second[:width]
    at = next((index for index, (left, right)
               in enumerate(zip(first, second, strict=False))
               if left != right), min(len(first), len(second)))
    start = max(at - width // 2, 0)
    return ("…" + first[start:start + width - 1],
            "…" + second[start:start + width - 1])


def first_difference(one: str, other: str, width: int, *,
                     absent: str | None = None) -> Difference | None:
    """The first difference between two texts, or None when this cannot name
    one.

    Three callers share the rule "two texts must be byte-identical; name what
    moved" — `probe`'s clause 2 at `DIFFERENCE` characters and eleven spaces,
    `capture`'s `--twice` at `capture.DRIFT` and four, and `compare`'s `[DIFF]`
    detail — where copies of it drift apart line by line. The WIDTH stays each
    caller's, and so does the layout: unifying those is a separate, semantic
    choice this does not make.

    The walk is over `lines_of`, not `splitlines`: a line keeps the `\\r` a
    CRLF text ends it with, so `"a\\r\\n"` against `"a\\n"` names line 1 as
    `'a\\r'` and `'a'` rather than coming back empty over a real byte
    difference — and a determinism guard that returns "no difference" over
    one is a false clean from the guard whose whole job is to refuse one. What
    no line walk can see — `"abc"` against `"abc\\n"` — is the final newline,
    named HERE and not by each caller. The line walk runs first, because a
    text that also moved a line moved it for a reason a reader can act on.
    The two lines are cut to the width by `_windows`, around the byte that
    differs when the heads are equal.

    `absent` is what a caller calls a line the shorter text does not have.
    `capture` passes `'(absent)'` and reports the pair, because a row that
    gained or lost a line is what it is refusing about; `probe` leaves it None
    and gets None back, then says the shorter is a prefix of the longer. That
    is the whole difference between the two, and it stays the caller's.
    """
    left, right = lines_of(one), lines_of(other)
    for number in range(max(len(left), len(right))):
        first = left[number] if number < len(left) else absent
        second = right[number] if number < len(right) else absent
        if first is None or second is None:
            return None
        if first != second:
            return Difference(number + 1, *_windows(first, second, width))
    tail = _final_newline(one, other)
    return Difference(None, "", "", tail) if tail else None


@contextlib.contextmanager
def workspace(census: Any, prefix: str, root: str, *, out: Any,
              note: Callable[[str, int], None] | None = None
              ) -> Iterator[Roots]:
    """The scratch directories a run makes, and their removal.

    ONE decision: make the fixed-width directory FIRST — so a temp root too
    wide for the census's pin refuses before anything at all is made — then a
    work directory under the temp root, build the `Roots`, and remove BOTH in
    `finally`. Transcribed at each call site instead, it is the half-copies
    that leak: a refusal on the way out leaving a `golden-census-compare-*`
    behind, a capture that raised leaving a pair.

    Each directory is removed only where the directory it was made in still
    resolves where it did when it was made (`made_in_place`): a setup step or
    a row that relinked the temp root, or a level above it, has moved the
    directory golden-census made, and what its path leads to now is not
    golden-census's to remove. That directory is left where it went.

    `census` is a `Census` or None; None means no fixed-width directory, which
    is what `compare`'s and `mutants`' work halves want. `prefix` is the
    caller's own `mkdtemp` prefix — nothing reads them back, but a directory
    left behind by a crash names the command that made it.

    `note` is the ONE stated exception: `census --manifest M` tolerates a temp
    root too wide for the pin, because its state block is what the reader came
    for and it runs no subject. It is called with the normalized root and the
    pinned width, and the caller writes its own sentence; without it a too-wide
    root refuses here, by the same arithmetic every other caller refuses with.

    `out` is where the command writes its verdict. The outermost
    `workspace` open holds `_LEFT` while it is open: every directory
    golden-census made that stayed after its removal in that time, whoever
    removed it, is noted there by `left_behind`, and when this `workspace`
    has removed its own two, each noted directory still on disk is named on
    `out` in `not_removed`'s line, in the order they stayed. A
    directory removed later by the removal of the directory it was in — a
    copy `mutants` checked, inside its work directory — is gone by then and
    is not named. A nested `workspace` — a `vary` control's place, a
    capture `compare` or `mutants` makes — names nothing itself.

    A root that will not take the work directory raises its `OSError` as
    it is, as `make_fixed_dir` does: `require_temp_root` made a directory
    there for this command, so the root changed while it ran.
    """
    global _LEFT
    width = None if census is None else census.fixed_width
    fixed: str | None = None
    work: str | None = None
    outermost = _LEFT is None
    if outermost:
        _LEFT = []
    try:
        if width is not None:
            base, room = fixed_dir_room(temp_base(), width)
            if room >= 1:
                fixed = make_fixed_dir(temp_base(), width)
                _made(fixed)
            elif note is not None:
                note(base, width)
            else:
                raise fixed_dir_refusal(base, width)
        work = tempfile.mkdtemp(prefix=prefix, dir=temp_base())
        _made(work)
        yield Roots(root=root, work=work, clone=None, fixed=fixed)
    finally:
        for directory in (work, fixed):
            if directory is not None:
                if made_in_place(directory):
                    removed(directory, out)
                _MADE_IN.pop(directory, None)
        if outermost:
            left = _LEFT or []
            _LEFT = None
            for path in left:
                if os.path.lexists(path):
                    _write_left(path, out)


def not_removed(path: str) -> str:
    """The ONE line naming a directory golden-census made that is still on
    disk when the command ends, unfolded, so the reader can delete it by
    the path printed: written by `left_behind`, and by `workspace` for what
    `left_behind` noted, by the self-test for its own box, and by
    nothing else."""
    return (f"  a directory golden-census made could not be removed: {path} "
            "— delete it by hand and name it in your report\n")


def removed(path: str, out: Any) -> bool:
    """`remove_tree(path)`, and when anything of `path` stayed,
    `left_behind(path, out)`.

    A leftover is a fact about the disk and not about the subject: the line
    changes no verdict and no exit code. It never raises, for
    `remove_tree`'s reason: it runs in a `finally`, and a standard output
    that refuses the line must not replace what is on its way out."""
    gone = remove_tree(path)
    if not gone:
        left_behind(path, out)
    return gone


def left_behind(path: str, out: Any) -> None:
    """`path`, a directory golden-census made that stayed after its removal,
    named in `not_removed`'s line: noted in `_LEFT` while a `workspace` is
    open, for the outermost one to name if it is still on disk when that
    `workspace` ends; written on `out`, the stream the command writes its
    verdict on, at once when none is open, because nothing removes it
    later. Never raises: it runs in a `finally`."""
    if _LEFT is not None:
        _LEFT.append(path)
    else:
        _write_left(path, out)


def _write_left(path: str, out: Any) -> None:
    """`not_removed`'s line for `path` on `out`; a standard output that
    refuses it is passed over, for `removed`'s reason."""
    with contextlib.suppress(OSError, ValueError):
        out.write(not_removed(path))


#: Every directory golden-census made that stayed after its removal while a
#: `workspace` was open, in the order they stayed; None while none is open.
#: The outermost `workspace` sets it and names what of it is still on disk
#: when it ends; its one other writer is `left_behind`.
_LEFT: list[str] | None = None


#: Where the directory each scratch directory `workspace` made was made in —
#: the temp root — resolved when it was made, by the scratch directory's path,
#: for as long as `workspace` holds it. Its one writer is `_made`; its one
#: reader is `made_in_place`.
_MADE_IN: dict[str, str] = {}


def _made(directory: str) -> None:
    """Note where the directory `directory` was made in resolves now, the
    moment `workspace` has made it and before anything runs in it."""
    _MADE_IN[directory] = os.path.realpath(os.path.dirname(directory))


def made_in_place(directory: str) -> bool:
    """Whether the directory `directory` is in still resolves where it
    resolved when `workspace` made `directory`: the levels ABOVE a scratch
    directory, the temp root's own, asked as `under` asks the levels below.

    The temp root may be reached through a link of the reader's own — `/tmp`
    on macOS — so no level above is refused for being a link: what is asked
    is whether the levels lead where they led when the directory was made.
    A setup step or a row that relinks the temp root, or any level above it,
    makes the answer False, and the directory golden-census made is then
    somewhere else. A directory `workspace` does not hold has nothing noted,
    and the answer is True: nothing is known that moved it.
    """
    made = _MADE_IN.get(directory)
    return (made is None
            or os.path.realpath(os.path.dirname(directory)) == made)


def remove_tree(path: str) -> bool:
    """Remove a directory golden-census made, whatever a subject left in it,
    and say whether it is gone.

    A subject can leave a directory it made read-only — a module cache does
    — and `shutil.rmtree` cannot empty a directory it may not write. `path`
    and every directory under it are made writable first, top down, so each
    is writable before the walk lists it; a symbolic link is never followed,
    `path` included, so nothing it leads to is changed. What `path` is, is
    asked of `os.lstat` before any mode changes: a file put in the
    directory's place may be a hard link to a file of the reader's, and its
    mode is that file's. Then the tree is removed — or, where a subject put
    a link or a file in the directory's place, that one name is unlinked,
    and what a link leads to is kept.

    It never raises: it runs in `workspace`'s `finally`, where an exception
    would replace the outcome of every command with a traceback. A path that
    is not there, a directory whose mode cannot be changed and a directory
    the walk cannot list are passed over; what could not be reached stays on
    disk, and the answer is False.
    """
    try:
        directory_at_path = stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        directory_at_path = False
    if directory_at_path:
        with contextlib.suppress(OSError):
            os.chmod(path, 0o700)
        for directory, names, _files in os.walk(path):
            for name in names:
                child = os.path.join(directory, name)
                if not os.path.islink(child):
                    with contextlib.suppress(OSError):
                        os.chmod(child, 0o700)
    if os.path.islink(path) or not os.path.isdir(path):
        with contextlib.suppress(OSError):
            os.unlink(path)
    else:
        shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)

# -------------------------------------------------- a path inside a directory

#: The one character a component cannot carry whatever the platform, because
#: it is what ends a path for the operating system underneath: a name holding
#: it is not a name a file system can hold, and `os` raises `ValueError` about
#: it far from the file that spelled it. ONE owner, asked as part of the
#: question each caller already puts — is this a component? — by
#: `manifest._one_component`, `manifest._stays_under` and `templates._files`,
#: and never as the first entry of a list of forbidden characters, which every
#: other byte a file system takes would have to be checked against.
NOT_IN_A_COMPONENT = "\0"


def under(path: str, directory: str, *, strict: bool) -> bool:
    """Whether `path` RESOLVES inside `directory`, as the file system answers:
    the one rule.

    Both sides through `os.path.realpath`, so a link is followed to where it
    leads — a link inside that leads out is outside — and a tree reached
    through a linked directory, `/tmp` on macOS, is the same tree as the one
    reached without it. The two real paths are compared as strings first, and
    where they say inside they are right. Where they say outside, the file
    system is asked: `os.stat` of the directory against each level of the
    path's real path that exists, by `os.path.samestat`. Two spellings that
    name one directory are one directory — a link whose target spells it in
    another case, on a file system that folds case — and only the file system
    knows which spellings it folds, so golden-census keeps no rule of its own
    about them: where it does not fold, the two spellings are two directories
    and the answer is outside. A path that does not exist yet is answered by
    the levels of it that do. A `directory` that does not exist cannot be
    asked, and the strings' answer stands.

    `strict` says whether `directory` itself counts: True asks for a path
    strictly below it, False accepts the directory too, under any spelling.
    It has no default, because a wrong default flips the boundary for every
    caller that did not say which one it meant. The walk is
    `resolved_below`, which hands back the relative path as well.

    A rule about the SPELLING of a path is a different question, and
    `manifest._stays_under` and `templates._inside` ask it: what they are
    handed need not exist yet, so there is nothing to follow.
    """
    below = resolved_below(path, directory)
    return below is not None and not (strict and below == os.curdir)


def resolved_below(path: str, directory: str) -> str | None:
    """`path` written relative to `directory` by `under`'s rule — `.` for the
    directory itself — or None when it resolves outside.

    The relative path is taken from the level the answer was found at: the
    real directory where the strings agree, and otherwise the level of the
    path's real path that the file system named as the directory. Taken
    between the two spellings instead, a path inside a directory spelled in
    another case would read as `../` and the directory's other spelling, and
    `Manifest.with_root` would re-anchor `<HERE>` outside the copy it was
    handed.
    """
    real_directory = os.path.realpath(directory).rstrip(os.sep)
    real_path = os.path.realpath(path)
    if real_path.rstrip(os.sep) == real_directory:
        return os.curdir
    if real_path.startswith(real_directory + os.sep):
        return os.path.relpath(real_path, real_directory or os.sep)
    try:
        identity = os.stat(real_directory)
    except OSError:
        return None
    level = real_path
    while True:
        try:
            if os.path.samestat(os.stat(level), identity):
                return os.path.relpath(real_path, level)
        except OSError:
            pass
        parent = os.path.dirname(level)
        if parent == level:
            return None
        level = parent

# ------------------------------------------ what a command made, and its undo


class Made:
    """Everything one command brought into being, so a refusal can undo it.

    Two owners keep one: `init`, which writes the neutral three and then a
    template's own files, and a refusal in the second pass used to leave the
    first pass's files on disk — where the next `init` refused them as
    already existing; and `capture._staged`, for the parents of `--out` it
    had to make to stage a capture beside it, and for `--out` itself when
    `--input` records into one that was not there.

    EXACTLY what it made, and never a directory tree it found: `init` may be
    pointed at a checkout full of somebody's work, `capture` at a directory
    whose parents hold somebody else's, and undoing a failed run must not be
    able to reach a byte that was already there. A directory is made one
    level at a time and each level recorded the moment it exists, so a path
    that fails partway is undone as far as it got.
    """

    def __init__(self) -> None:
        self.files: list[str] = []
        #: Deepest first, which is the order they can be removed in.
        self.directories: list[str] = []

    def makedirs(self, path: str) -> None:
        """`os.makedirs(path, exist_ok=True)`, one level at a time, each level
        recorded the moment it is made — so a failure partway (a component
        too long, a parent that is a file) leaves the ledger holding exactly
        the levels already made, and `undo` removes them."""
        missing: list[str] = []
        walk = os.path.abspath(path)
        while not os.path.isdir(walk):
            missing.append(walk)
            parent = os.path.dirname(walk)
            if parent == walk:
                break
            walk = parent
        for level in reversed(missing):
            try:
                os.mkdir(level)
            except FileExistsError:
                if not os.path.isdir(level):
                    raise
                continue
            self.directories.insert(0, level)

    def undo(self) -> None:
        """Remove what was made, files first. Errors are swallowed: this runs
        under a refusal that is already being reported, and a second failure
        on the way out would replace the sentence the reader needs with one
        about the cleanup."""
        for path in self.files:
            with contextlib.suppress(OSError):
                os.remove(path)
        for path in self.directories:
            with contextlib.suppress(OSError):
                os.rmdir(path)


# -------------------------------------------------- where the package's data is
#
# One asker off `__file__`, where a resolver in each module that reads the
# package's data would give its own answer to "the file is not there". ONE
# absence policy over it, too: a disclosed SKIP in an arm, a `Refusal` in a
# command, never a raise. WHERE the
# data goes when golden-census ships is answered here too, in TWO layouts:
# beside the package in a checkout, inside it under `SHIPPED` in a wheel.
# `data_in` is where the two are tried, once, for every caller; `Layout` is
# where "which layout is this run in, and what does it therefore carry" is
# decided, once, for every reader.


def package_dir(*parts: str) -> str:
    """The package's own directory, joined with `parts`.

    The one reader of this module's `__file__`. What lives here is code and
    the bundled fixture the self-test runs against; what lives BESIDE it is
    the data an install has to carry — see `Layout`.
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


#: The IMPORT name — the package directory's own name, read off the directory
#: rather than typed a second time. `PROG` is the COMMAND (`golden-census`,
#: hyphenated); `python3 -m golden-census` cannot import, and a literal
#: `"golden_census"` planted in an arm is a literal that can agree with
#: `pyproject.toml` while the directory on disk has moved — the false-clean
#: arm `sss` exists to catch. One owner, derived.
IMPORT_NAME = os.path.basename(package_dir())


#: The directory a WHEEL puts the data in, under the package. A checkout
#: keeps `templates/`, `examples/`, `docs/`, the skill, the README and the
#: license beside the package; a wheel cannot — `site-packages/templates/`
#: is a generic top-level name that would collide with any other package
#: shipping one — so `pyproject.toml`'s `force-include` rows copy them to
#: `golden_census/_shipped/` instead, in the checkout's own shape, with
#: nothing moving in the repository. The name is spelled HERE and in those
#: rows, and arm `ooo` plants both layouts.
SHIPPED = "_shipped"


def data_in(package: str, *parts: str) -> str:
    """`parts` under `package`'s data, in the layout the PACKAGE says it is
    in.

    Two layouts, one asker, decided from the package and from nothing beside
    it. A package that holds a `SHIPPED` directory is a wheel, and only the
    path under `SHIPPED` is read. Any other package is a checkout, and only
    the path beside the package is read: in a wheel `dirname(package)` is
    `site-packages`, where a stray `templates/` of another program must never
    stand in for golden-census's own. The package directory is a PARAMETER so
    that a control can plant both layouts and ask the same question of each:
    `Layout.for_package` below is the one caller, and `Layout.detect` is how
    the real package is read.

    Whether or not the data is there, the path the layout would have read
    comes back — not None and not a raise — because a caller that cannot find
    its data has to be able to NAME the directory it looked in: "there is no
    template at <dir>: `init` has nothing to write from" is a sentence a
    reader can act on, and an empty list is not.
    """
    if os.path.isdir(os.path.join(package, SHIPPED)):
        return os.path.join(package, SHIPPED, *parts)
    return os.path.join(os.path.dirname(package), *parts)


def set_members(root: str, paths: Sequence[str]) -> tuple[str, ...]:
    """Every file under `root` that `paths` names, in the order they name
    them: a path as it stands, or, where its last name carries `*`, the files
    of that directory the name matches, sorted, a dot-file never among them.
    A directory that cannot be listed matches nothing."""
    found: list[str] = []
    for path in paths:
        directory, name = os.path.split(os.path.join(root, path))
        if "*" not in name:
            if os.path.isfile(os.path.join(directory, name)):
                found.append(os.path.join(directory, name))
            continue
        shape = re.compile(re.escape(name).replace(r"\*", "[^/]*"))
        try:
            listed = sorted(os.listdir(directory))
        except OSError:
            continue
        found += [os.path.join(directory, entry) for entry in listed
                  if shape.fullmatch(entry) and not entry.startswith(".")
                  and os.path.isfile(os.path.join(directory, entry))]
    return tuple(found)


@dataclasses.dataclass(frozen=True)
class Layout:
    """Which layout this run is in — a checkout or a wheel — decided ONCE,
    and what that layout carries, as a path per file or None.

    `data_in` answers per PATH, correctly. "Is this an install, and what is
    therefore absent" is the question above it, and re-derived from an absence
    at each of six sites it is six sentences and — for the worked example's
    subject root — a different answer in the wheel layout. This record is the
    one derivation. It is a record and not a flag because the
    two layouts do not differ by one bit: a wheel carries the documents
    under `_shipped` and not `pyproject.toml`, so the packaging row is the
    one that cannot run there — a question a boolean cannot answer and a
    field per document can.

    `root` is the directory the package sits in: the checkout top, or
    `site-packages`. `data` is the directory `templates/` and `examples/`
    travel in — `root` in a checkout, `<package>/_shipped` in a wheel — and
    `shipped` says which. `readme` to `pyproject` are the path when the
    layout carries that file and None when it does not; `absent` is the ONE
    sentence a disclosed SKIP says about such a None, naming the one
    directory a reader of this repository would go looking in — what did NOT
    run because of it is each arm's own clause, after it. `human` and `agent`
    are the exception: the paths that exist of `HUMAN_SET` and `AGENT_SET`
    under `data`, empty where the layout carries none of them.

    `fixture` and `source` are INSIDE the package, which every install
    carries and a package run from a zip file carries as no directory at
    all: `fixture` is the bundled fixture's directory or None; `source` is
    False when the package directory lists no `.py` file or is no directory
    at all, and True when listing it fails otherwise, so the walk that reads
    the source names that fault. `is_directory` is whether the package path
    is a directory, asked once of `os.path.isdir`. `inside_absent` is the
    one sentence about either absence, each arm's own clause after it, and
    it says which of the two was measured: a package path that is no
    directory, or a directory that holds none.
    """

    package: str
    root: str
    data: str
    shipped: bool
    readme: str | None
    skill: str | None
    human: tuple[str, ...]
    agent: tuple[str, ...]
    example: str | None
    templates: str | None
    pyproject: str | None
    fixture: str | None
    source: bool
    is_directory: bool

    @staticmethod
    def for_package(package: str) -> Layout:
        """The layout around `package`, every field asked of `data_in`. The
        package is a parameter so a control can plant a checkout, a wheel and
        an empty package and ask the same question of each; `detect` is the
        real one."""
        root = os.path.dirname(package)
        data = os.path.dirname(data_in(package, "templates"))

        def found(test: Callable[[str], bool], *parts: str) -> str | None:
            path = data_in(package, *parts)
            return path if test(path) else None

        def lists_source() -> bool:
            try:
                return any(name.endswith(".py") for name in os.listdir(package))
            except (NotADirectoryError, FileNotFoundError):
                return False
            except OSError:
                return True

        fixture = os.path.join(package, "fixture")
        return Layout(package=package, root=root, data=data,
                      shipped=data != root,
                      readme=found(os.path.isfile, "README.md"),
                      skill=found(os.path.isfile, SKILL_DIR, "SKILL.md"),
                      human=set_members(data, HUMAN_SET),
                      agent=set_members(data, AGENT_SET),
                      example=found(os.path.isdir, "examples",
                                    "python-function"),
                      templates=found(os.path.isdir, "templates"),
                      pyproject=found(os.path.isfile, "pyproject.toml"),
                      fixture=fixture if os.path.isdir(fixture) else None,
                      source=lists_source(),
                      is_directory=os.path.isdir(package))

    @staticmethod
    def detect() -> Layout:
        """The layout THIS package is in, computed once per process."""
        return _detected()

    @property
    def checkout(self) -> bool:
        """True in the repository's own layout: `pyproject.toml` beside the
        package and the data not shipped under it. Parity is a development
        check: only here is a missing document a defect."""
        return self.pyproject is not None and not self.shipped

    def absent(self, what: str) -> str:
        """The one sentence about a file this layout does not carry, naming
        the directory `data_in` read; a checkout's is `missing`."""
        return (f"{what} is not in this layout: {self.data} holds none.")

    def inside_absent(self, what: str) -> str:
        """The one sentence about what this layout does not carry INSIDE the
        package — the bundled fixture, the package's source: it names the
        package path and says what `for_package` measured there — that the
        path is not a directory, or, when it is one, that it holds none.
        `absent` is the one about a file beside it."""
        measured = "holds none" if self.is_directory else "is not a directory"
        return (f"{what} is not inside the package in this layout: "
                f"{self.package} {measured}.")

    def missing(self, what: str) -> str:
        """The one sentence about a file a CHECKOUT should carry and does
        not — a FAIL's detail, never the install's absence sentence."""
        return (f"{what} is missing from this checkout: {self.root} holds "
                "pyproject.toml beside the package, so the document belongs "
                "here — this is not an install's absence.")


@functools.cache
def _detected() -> Layout:
    return Layout.for_package(package_dir())


#: What each platform golden-census runs on carries, typed ONCE: the roots
#: user homes live under, the advice two refusals give — a temp root too
#: wide for the census's pin, and one no directory can be made in — and
#: where the user's cache directory is: under the home, and the variable
#: that names it instead, `""` where the platform has none.
#: `Platform.for_platform` derives every field from this row, so a field is
#: written here or nowhere.
_PLATFORMS: dict[str, tuple[tuple[str, ...], str, str, str]] = {
    "darwin": (("/Users",), "TMPDIR=$(getconf DARWIN_USER_TEMP_DIR)",
               "Library/Caches", ""),
    "linux": (("/home", "/root"), "TMPDIR=/tmp", ".cache", "XDG_CACHE_HOME"),
}


def _home_root(home: str | None) -> str:
    """The root the running user's home sits under, or `""` where that root is
    `/` — which as a home root is a pattern matching every absolute path there
    is. `home` is `expanduser("~")` where the caller names none.

    One derivation, read by the platform's own roots and by every platform's
    at once, so the two cannot disagree about where this machine's homes live.
    """
    running = os.path.dirname(
        home if home is not None else os.path.expanduser("~"))
    return "" if running == "/" else running


@dataclasses.dataclass(frozen=True)
class Platform:
    """Which platform this run is on, decided ONCE, and the two facts that
    differ with it: where user homes live, and what a reader is told to do
    about a temp root that is too wide or that no directory can be made in.

    A record and not `if sys.platform`, for the reason `Layout` is a record
    and not a flag: the NAME is a parameter, so a control plants both
    platforms and asks the same question of each. That is the only way a
    self-check running on one platform can claim anything about the other — a
    fact spelled as a literal at the site that reads it is a fact about the
    machine that line was written on, and a clean self-check there says
    nothing at all about the machine it was not.

    `home_roots` is read by the contraband scan and `short_root_advice` by
    the width refusal and by `require_temp_root`'s; `cache_home` and
    `cache_variable` by `cache_dir` alone. `detect` is the real platform,
    read once.
    """

    name: str
    home_roots: tuple[str, ...]
    short_root_advice: str
    cache_home: str
    cache_variable: str

    def cache_spelled(self) -> tuple[str, str | None]:
        """The variable `cache_dir` builds the cache directory from, and its
        value as set: `cache_variable` where the platform names one and its
        value is an absolute path (the XDG Base Directory specification
        passes a relative one over), else `HOME` — whose value is None where
        it is unset and `os.path.expanduser` falls back to the account's
        home. Read from the environment at every call."""
        named = (os.environ.get(self.cache_variable, "")
                 if self.cache_variable else "")
        if os.path.isabs(named):
            return self.cache_variable, named
        return "HOME", os.environ.get("HOME")

    def cache_dir(self) -> str:
        """The directory golden-census keeps its clone cache in: `PROG` under
        the platform's cache directory — the value of the variable
        `cache_spelled` names where that is `cache_variable`, else
        `cache_home` under `os.path.expanduser("~")`. Read from the
        environment at every call, so a control that plants HOME and the
        variable moves it.
        """
        variable, named = self.cache_spelled()
        if variable == "HOME" or named is None:
            named = os.path.join(os.path.expanduser("~"), self.cache_home)
        return os.path.join(named, PROG)

    @staticmethod
    def for_platform(name: str, home: str | None = None) -> Platform:
        """The platform `name` carries, with `home` the running user's home
        directory — `expanduser("~")` where the caller names none.

        `home` is a parameter for the reason `name` is: the layout neither
        platform's roots cover is the one a control has to plant, and on any
        one machine there is exactly one home to read. The home's own root
        joins `home_roots` when it is a third — `/export/home/bob` gives
        `/export/home` — and a home whose root is `/` adds none, because `/`
        as a home root is a pattern that matches every absolute path there is.
        """
        if name not in _PLATFORMS:
            known = " and ".join(repr(each) for each in sorted(_PLATFORMS))
            raise Refusal(
                f"golden-census has no record of the platform {name!r}; it "
                f"carries {known}. Where user homes live and what a "
                "too-wide temp root is told to do are facts about the "
                "platform, and a run that guessed at them would write the "
                "guess into a golden.",
                next=f"Run golden-census on a platform it carries ({known}); a "
                "capture made under a guess is not a record of anything.")
        roots, advice, cache_home, variable = _PLATFORMS[name]
        running = _home_root(home)
        if running and running not in roots:
            roots = (*roots, running)
        return Platform(name=name, home_roots=roots,
                        short_root_advice=advice, cache_home=cache_home,
                        cache_variable=variable)

    @staticmethod
    def every_home_root(home: str | None = None) -> tuple[str, ...]:
        """Every platform's home roots at once, the running user's own among
        them where it is a third.

        What one platform lays out is `home_roots`; what a GOLDEN is judged
        against is this. A golden travels, and a set recorded on one platform
        and compared on another is judged by one rule or by two — and two is a
        difference between machines that the reader is left to explain.
        """
        running = _home_root(home)
        return tuple(dict.fromkeys(
            [root for name in sorted(_PLATFORMS) for root in _PLATFORMS[name][0]]
            + ([running] if running else [])))

    @staticmethod
    def detect() -> Platform:
        """The platform THIS run is on, read once per process."""
        return _detected_platform()


@functools.cache
def _detected_platform() -> Platform:
    return Platform.for_platform(sys.platform)

# ------------------------------------------------------------- placeholders


#: What a placeholder looks like. Narrow on purpose: `a < b and c > d` is not
#: a token (no spaces), and `<flagmatrix_pairs()>` IS one — which is why the
#: keys a manifest may spell are checked against a list rather than assumed
#: from the shape. `record_argv` is the one string golden-census never expands,
#: so a consumer's `<…>` word there is recorded, not resolved.
TOKEN_RE = re.compile(r"<[A-Za-z][A-Za-z0-9_:.()-]*>")


def expand(text: str, ctx: Mapping[str, str | None], where: str = "") -> str:
    """Replace every `<TOKEN>` the context defines, refusing on one it does not.

    The refusal names the offending key AND the token: a manifest that spells
    `<TMP>` where golden-census defines `<WORK>` costs one sentence, before the
    first run, and the sentence says which row to fix.
    """
    place = where or "the manifest"

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        name = token[1:-1]
        if name not in ctx:
            raise Refusal(
                f"{place}: {token} is not a placeholder golden-census defines "
                "here. The whole list is "
                + ", ".join(f"<{k}>" for k in ctx) + ".",
                next="Spell the token as one of the names listed above.")
        value = ctx[name]
        if value is None:
            raise Refusal(
                f"{place}: {token} has no value in this run — the row that "
                "spells it is asking for a directory this capture never made.",
                next="Drop that token from the row, or run the command that makes the directory it "
                "names.")
        return value

    return TOKEN_RE.sub(replace, text)


def check_tokens(text: str, allowed: tuple[str, ...], where: str) -> None:
    """The load-time half of `expand`: every token is one golden-census knows.

    A manifest is read before anything is run, so an unknown placeholder is
    caught with the other manifest errors and not ten minutes into a capture,
    when the value it would have expanded to first exists.
    """
    for match in TOKEN_RE.finditer(text):
        name = match.group(0)[1:-1]
        if name not in allowed:
            raise Refusal(
                f"{where}: {match.group(0)} is not a placeholder golden-census "
                "defines here. The whole list is "
                + ", ".join(f"<{k}>" for k in allowed) + ".",
                next="Spell the token as one of the names listed above.")


class Placeholders(NamedTuple):
    """ONE loader's placeholder vocabulary: the names a string of that file may
    spell, and their values once a run exists to have any.

    Built once per loader and carried, so the load-time half — every token is
    one golden-census knows, checked before anything runs — and the run-time
    half cannot become two vocabularies. Hand-typed at each site instead —
    six spellings across `manifest`, `census`, `mutants` and `docs` — the two
    halves drift apart, and the load-time one stops being a check: a census
    pin spelling `<TMP>` loads and refuses mid-capture, a mutants check
    command spelling `<WORK>` loads and refuses after the null clone is
    made.

    Both halves are `expand` and `check_tokens` above — one mechanism, one
    wording — so a refusal reads the same whichever half found it.
    """

    values: Mapping[str, str | None]

    @property
    def names(self) -> tuple[str, ...]:
        """The vocabulary, in the order a refusal lists it."""
        return tuple(self.values)

    def also(self, more: Mapping[str, str | None]) -> Placeholders:
        """This vocabulary with more names — `writes`'s `<input>` and
        `<surface>`, a census control's `<FIXTURE>`. The wider table is built
        FROM the narrower one and never typed beside it.
        """
        return Placeholders({**self.values, **more})

    def token(self, name: str) -> str:
        """How one of THIS vocabulary's names is spelled in a file.

        For the two rules that compare a consumer's string against a token
        rather than expanding it: `mutants.check_cwd` asks which argument is
        the script when the first one is the interpreter. Typing `"<PYTHON>"`
        beside the vocabulary that defines the name would leave that rule
        comparing against a token nobody defines as soon as the vocabulary
        drops or renames it — silently, and only for consumers whose check
        commands start with the interpreter.

        A name this vocabulary does not carry is a defect in golden-census and
        not in anybody's file, and it says so.
        """
        if name not in self.values:
            raise Refusal(
                f"golden-census asked this vocabulary how it spells {name!r}, "
                "which it does not define. The whole list is "
                + ", ".join(f"<{k}>" for k in self.values) + ".",
                next="Report this as a golden-census defect: nothing in your files can "
                     "cause it.")
        return f"<{name}>"

    def check(self, text: str, where: str) -> None:
        """Every token of `text` is one this vocabulary defines."""
        check_tokens(text, self.names, where)

    def expand(self, text: str, where: str) -> str:
        """Every token of `text` replaced by its value, refusing on one this
        vocabulary does not define or has no value for in this run."""
        return expand(text, self.values, where)


class _Unspelled:
    """`roots_vocabulary`'s default for `writes`: this vocabulary does not
    spell `<WRITES>` at all — the census's case — as distinct from a
    `<WRITES>` whose value is None in this run, which the manifest's spells
    and refuses as "has no value" rather than as an unknown token."""


UNSPELLED = _Unspelled()


def roots_vocabulary(roots: Roots | None, *,
                     writes: str | None | _Unspelled = UNSPELLED) -> Placeholders:
    """The names a consumer's file may spell for the run's directories and
    interpreter — `<ROOT>`, `<WORK>`, `<CLONE>`, `<PYTHON>` — with their
    values once a run exists to have any, and None before one does.

    The DATA of two loaders' vocabularies, typed once: the census adds
    `<HERE>`, and the manifest `<WRITES>` and — in `[subject] command` alone —
    `<HERE>` of its own, each through `Placeholders.also` or the `writes=`
    slot, and neither types the four again. `<WRITES>` sits
    between `<CLONE>` and `<PYTHON>` because the order is the order a refusal
    lists the whole vocabulary in, and that sentence is a consumer's. `mutants`' vocabulary
    (`<ROOT>`, `<PYTHON>`, `<HERE>`) is a different set and stays its own.
    """
    values: dict[str, str | None] = {
        "ROOT": roots.root if roots is not None else None,
        "WORK": roots.work if roots is not None else None,
        "CLONE": roots.clone if roots is not None else None,
    }
    if not isinstance(writes, _Unspelled):
        values["WRITES"] = writes
    values["PYTHON"] = sys.executable if roots is not None else None
    return Placeholders(values)


# ------------------------------------------------------------ stream guards


def in_utf8(stream: Any, errors: str | None = None,
            line_buffering: bool | None = None) -> None:
    """Make `stream` write UTF-8, whatever `PYTHONIOENCODING` or the locale
    says: golden-census writes UTF-8 on standard output and on standard
    error, and this is the one place that says so.

    Called BEFORE the first write to the stream, a zero-length one included:
    an encoding that opens with a byte-order mark — `utf-16`, `utf-32`,
    `utf-8-sig` — writes the mark on the first write, and a stream
    reconfigured after that is the mark followed by UTF-8.

    `errors` is the error handler, and None keeps the one the stream has: it
    is named either way, because `reconfigure` with an encoding and no
    handler sets `strict`. `line_buffering` None keeps the stream's.

    A stream that is None, closed, or no text wrapper is left as it is and
    nothing is raised: `usable` and `to_stderr` answer for those.
    """
    if not hasattr(stream, "reconfigure"):
        return
    try:
        stream.reconfigure(encoding="utf-8",
                           errors=stream.errors if errors is None else errors,
                           line_buffering=line_buffering)
    except (AttributeError, ValueError, OSError):
        pass


def usable(stream: Any) -> bool:
    """True when `stream` can actually be written to.

    CPython sets `sys.stdout` to None when the interpreter is started with
    file descriptor 1 closed (`golden-census capture >&-`), and a stream closed
    later raises `ValueError` on write — so the probe is a zero-length write
    and not a `None` test, which would see only half of it.
    """
    if stream is None:
        return False
    try:
        stream.write("")
    except (AttributeError, ValueError, OSError):
        return False
    return True


def to_stderr(text: str) -> bool:
    """Write `text` and a newline to stderr, flushed, and say whether it got
    there — the one writer to the stream that may still be open.

    Flushed here, so a stderr closed under the run fails HERE — where the
    caller can answer it — and not in the interpreter's own flush at exit.
    When stderr is closed too, the exit code is the whole message.
    """
    try:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    except (AttributeError, ValueError, OSError):
        return False
    return True


#: The signals `signals_held` defers: the two a terminal or a caller's
#: deadline sends, and the two `anchored` sweeps on.
HELD_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM})


@contextlib.contextmanager
def signals_held() -> Iterator[None]:
    """SIGINT and SIGTERM held for the length of the block, and delivered the
    moment it ends — none is swallowed.

    For the short windows where a signal can only make things worse, and
    exactly these: the `mkdtemp` and `rmdir` of `capture`'s up-front probe
    beside `--out`; the `mkdtemp` of the stage beside `--out`, of the
    temp-root recording and of `--twice`'s second capture, each until its
    path is recorded where it is removed; and ONE hold from the swap's rename
    pairs, with their put-back, through the one `rmtree` of the stage after
    them — taken by `capture._swap_in` and released by `capture._unstage`, so
    no signal lands between a replaced `--out` and the removal of what it
    replaced. The workspace's directories under the temp root are made
    unheld: a signal right after one leaves a directory under the temp root,
    never anything beside `--out`. Nothing inside a hold writes to a stream:
    a full pipe would block there, and a caller's deadline would have no
    effect. `pthread_sigmask` holds for the
    calling thread, which is enough because golden-census runs no other
    thread at any of these points (the matrix pool is joined long before).

    The mask is QUERIED first, by a call that blocks nothing, and changed
    inside the `try`: `pthread_sigmask` is a wrapper that blocks first and
    converts its result after, so a handler running during that conversion
    raises before an assignment of its result — which would leave the
    signals blocked for the rest of the process, and inherited by every
    child it starts.
    """
    was = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    try:
        signal.pthread_sigmask(signal.SIG_BLOCK, HELD_SIGNALS)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, was)


def to_null(fd: int) -> None:
    """Point file descriptor `fd` at the null device: after a reader closed
    it, so the interpreter's flush at exit has nowhere to fail."""
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, fd)
    finally:
        os.close(null)


def refuse_on_stderr(refusal: Refusal) -> bool:
    """Say why, on the one stream that may still be open, and say whether it
    got there. It takes the `Refusal` itself and not a bare string, so this
    stream's sentence is built by the one printer every other stream's is."""
    return to_stderr(refusal_text(refusal))
