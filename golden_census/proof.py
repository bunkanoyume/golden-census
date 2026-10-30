"""How proof code makes scratch and runs a throwaway subject.

What it holds: the environment and TMPDIR windows every arm opens (`_env_as`,
`_tmpdir_as`), the window that keeps the clone cache in an arm's box
(`_cache_in`), the scratch box under the root `core.temp_base()` names
(`_box`), the private-root listing four arms shared (`_made_under`), one run
of `main` with its printing kept (`_quietly`), whether `chmod` bites on this
machine (`_chmod_bites`, with `_opens` as the file probe), the fault control
(n) plants (`_FaultOnFirstWrite`), the throwaway subject, census and manifest
the loader controls are pointed at (`_scratch` and the three `_STUB_*`), the
one line a row's detail is cut to (`_one_line`, `_NO_VERDICT`), and the
`git init` + one commit every arm that needs a throwaway repository shares
(`_repo_of`, whose phrase for a git that would not start is
`_command_phrase` unless a caller names its own), and the two halves of an
arm that starts the package as a child: the argv that makes the child say
which copy it imported (`_package_argv`) and the reader that sets that line,
and the interpreter's startup noise before it, apart from the child's own
text (`_heard`).

Nothing here decides anything about golden-census: it is the floor the arms
(`selfcheck.py`) and the seven groups (`selftest.py`) both stand on. That is
why it imports `core` and nothing else in the package — a module below both
readers can never close a cycle with either.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping
from typing import NamedTuple, TypeVar

from . import SAID_WHERE, SAY_WHERE_OPTION
from .census import git_env
from .core import (
    GIT_IDENTITY,
    GIT_NO_MAINTENANCE,
    QUOTE,
    SURFACES_FILE,
    Platform,
    WouldNotStart,
    git_command,
    launch,
    temp_base,
)


T = TypeVar("T")


@contextlib.contextmanager
def _env_as(values: Mapping[str, str | None]) -> Iterator[None]:
    """Each variable set — or unset, for a None — inside the block, and
    whatever it was outside it, restored in a `finally`.

    ONE window for the four arms that would each type their own: the TMPDIR
    window below, arm `o`'s two-variable save/restore, arm `mm-rr`'s planted
    pair and arm `qqq`'s own. A window typed without the `finally` leaves the
    variable mutated for every later reader in the run, which is a self-check
    that reports about a root nobody set; `_tmpdir_as_unguarded` is that
    window, kept as arm `qqq`'s control. Restored, not popped, when there was a
    value: an unset variable and one set to the same directory are
    different states and `core.temp_base()` reads both.
    """
    was = {name: os.environ.get(name) for name in values}
    for name, value in values.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    try:
        yield
    finally:
        for name, value in was.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _tmpdir_as(root: str) -> contextlib.AbstractContextManager[None]:
    """`TMPDIR` is `root` inside the block and whatever it was outside it —
    the window `_made_under`, the priced roots and the planted one share."""
    return _env_as({"TMPDIR": root})


@contextlib.contextmanager
def _cache_in(box: str) -> Iterator[str]:
    """The clone cache under `<box>/cache-home` inside the block, on either
    platform: HOME and XDG_CACHE_HOME both planted, since on Linux the
    variable wins over HOME. Yields the directory `Platform.cache_dir` then
    names. `Platform.detect` is read first: it keeps its first answer, and
    the home roots in it must be the reader's.
    """
    platform = Platform.detect()
    home = os.path.join(box, "cache-home")
    with _env_as({"HOME": home, "XDG_CACHE_HOME": home}):
        yield platform.cache_dir()


def _box(prefix: str) -> tempfile.TemporaryDirectory[str]:
    """A scratch directory for an arm, under the root `core.temp_base()`
    names.

    `dir=` is the whole point and it is why this exists rather than every
    call site passing it: `tempfile.gettempdir()` caches its answer on the
    FIRST call of a process and never re-reads `TMPDIR`, so a box opened
    without `dir=` lands under whatever root happened to be current when some
    earlier code asked — `capture.contraband_patterns` asks during arm `f`,
    long before the first `_tmpdir_as` window. A box opened inside such a
    window without `dir=` would land under the OUTER root and be invisible to
    the leak listing that is the arm's whole claim.
    """
    return tempfile.TemporaryDirectory(prefix=prefix, dir=temp_base())


def _made_under(base: str, body: Callable[[], T]) -> tuple[T, list[str]]:
    """Run `body` under a PRIVATE temp root and report what it left there.

    Four arms — `n`, `q`, `t`, `kk` — ask the same question, and asking it of
    the SHARED temp root means list it before, list it after, subtract. That
    reads any directory another process happened to make during the body as a
    leak of golden-census's, and it is one observation of one piece of shared
    state transcribed four times. Under a private root there is nothing to
    subtract: everything in it was made by `body`, so the answer is the whole
    listing and a concurrent process cannot appear in it. `--selfcheck` run
    twice at once is the control for that.

    `TMPDIR` is `_tmpdir_as`'s for the duration, because `core.temp_base()` —
    which every scratch directory in the package asks — reads it. The
    variable is restored BEFORE the root is removed: the listing is taken
    inside the window and the tree is not.
    """
    root = tempfile.mkdtemp(prefix="golden-census-private-", dir=base)
    try:
        with _tmpdir_as(root):
            result = body()
            return result, sorted(os.listdir(root))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _quietly(main: Callable[[list[str]], int], argv: list[str]
             ) -> tuple[int, str]:
    """`(exit code, everything printed)` for one run of the real `main`."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _opens(path: str) -> None:
    """The probe the file sites hand `_chmod_bites`: open `path` for reading
    and close it, leaving no handle behind."""
    with open(path, "rb"):
        pass


def _chmod_bites(path: str, probe: Callable[[str], object]) -> bool:
    """Whether `chmod 000` takes `path` away from `probe` on this machine.

    It does not for root. ONE question, answered and put back: the original
    mode is restored before this returns, so nothing is left unreadable or
    unlistable, and an arm that needs the plant for its own run applies
    `chmod 000` itself when the answer is yes. The verdict and the SKIP
    sentence stay each arm's.
    """
    mode = stat.S_IMODE(os.stat(path).st_mode)
    os.chmod(path, 0o000)
    try:
        probe(path)
    except OSError:
        return True
    finally:
        os.chmod(path, mode)
    return False


@contextlib.contextmanager
def _mode_as(path: str, mode: int, after: int = 0o755) -> Iterator[None]:
    """`path` at `mode` inside the block and at `after` on every way out —
    the plant an arm makes once `_chmod_bites` has said it can."""
    os.chmod(path, mode)
    try:
        yield
    finally:
        os.chmod(path, after)


class _CutOnLastLine(io.StringIO):
    """A standard output whose reader stops one line early: it keeps every
    line before `capture complete` and raises `error` on that one — by
    default what a closed pipe raises. A `StringIO`, so `fileno()` raises and
    no descriptor of this process is ever redirected on its account."""

    def __init__(self, error: OSError | None = None) -> None:
        super().__init__()
        self.error = error if error is not None else BrokenPipeError(32, "Broken pipe")

    def write(self, text: str) -> int:
        if text == "  capture complete\n":
            raise self.error
        return super().write(text)


class _FaultOnFirstWrite:
    """An `out` that snapshots the temp root and raises on the first write.

    Used by control (n) only. `capture` writes nothing until both temp
    directories exist, so this is a fault planted exactly in the window where
    they would leak.
    """

    def __init__(self) -> None:
        self.at_fault: list[str] = []
        self.raised = ""

    def write(self, text: str) -> int:
        # `temp_base()` and not a root remembered at construction: the arm
        # runs the capture under a PRIVATE temp root (`_made_under`), and
        # what the fault must see is that root's contents.
        self.at_fault = sorted(os.listdir(temp_base()))
        raise RuntimeError(f"planted fault at {text.strip()[:30]!r}")


# ------------------------------------------------------------ scratch files
#
# A throwaway subject, census and manifest the loader controls can be pointed
# at. They are written into a temporary directory and removed with it; nothing
# here is a fixture anybody commits.

_STUB_SUBJECT = '''\
import argparse

parser = argparse.ArgumentParser(
    prog="stub",
    description="a stub subject golden-census writes for its own controls; this "
                "description is long enough that argparse has to wrap it at "
                "the terminal width, which is the whole point of the pin")
parser.add_argument("--flag", help="a flag whose help text is also long enough "
                                   "to be wrapped at the pinned width")
parser.parse_args()
print("stub ok")
'''

#: The `[environment]` table every scratch census opens with, written once.
_STUB_ENVIRONMENT = '''\
[environment]
inherit     = false
passthrough = ["PATH"]
'''

#: The stub census: the environment and one pin, whose `vary` control runs
#: `_subject/help` — so a scratch manifest loaded with it must record that
#: row, as `_STUB_MANIFEST` does.
_STUB_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "terminal width"
disposition = "pin"
variable    = "COLUMNS"
value       = "80"
finding     = "argparse wraps --help at $COLUMNS"
control     = { shape = "vary", surface = "_subject/help", value = "40" }
'''

#: A `path` fold for golden-census's own work directory, for a scratch census
#: whose rows print it — one row, planted by every arm that needs it.
_STUB_WORK_FOLD = '''
[[input]]
name        = "golden-census's own work directory"
disposition = "fold"
kind        = "path"
source      = "work"
placeholder = "<WORK>"
finding     = "a row's output names the directory the run wrote into"
'''

#: A scratch census with no pin: the environment and the work directory's
#: fold, for a manifest that records no `_subject/help` row for the stub pin's
#: `vary` control to run — its surfaces print the work directory, and none
#: reads the pinned variable.
_STUB_WORK_CENSUS = _STUB_ENVIRONMENT + _STUB_WORK_FOLD

def _root_fold(finding: str, before: str = "") -> str:
    """A `path` fold for the subject root, for a scratch census that needs
    one; `finding` is the row's `finding` text, and `before` is text a
    template puts ahead of the `finding` line (a `{scope}` it fills in)."""
    return f'''
[[input]]
name        = "the subject root's absolute path"
disposition = "fold"
kind        = "path"
source      = "root"
placeholder = "<REPO>"
{before}finding     = "{finding}"
'''


#: A `path` fold for the subject root, for a scratch census that needs one.
_STUB_ROOT_FOLD = _root_fold(
    "the checkout is a different directory on every machine")


def _fixed_pin(width: int, finding: str,
               name: str = "the subject's temp root, and its width") -> str:
    """A `pin` of the subject's TMPDIR to `<FIXED-WIDTH-DIR:{width}>` under
    the built-in control, for a scratch census; `finding` and `name` are the
    row's own, because each arm's row says why it pins."""
    return f'''
[[input]]
name        = "{name}"
disposition = "pin"
variable    = "TMPDIR"
value       = "<FIXED-WIDTH-DIR:{width}>"
finding     = "{finding}"
control     = {{ shape = "builtin", name = "fixed-width-dir" }}
'''


def _fixed_fold(finding: str) -> str:
    """The `path` fold of the directory `_fixed_pin` pins, to
    `<ENGINE-TMPDIR>`, for a scratch census whose rows print it."""
    return f'''
[[input]]
name        = "the fixed-width temp directory"
disposition = "fold"
kind        = "path"
source      = "fixed-width-dir"
placeholder = "<ENGINE-TMPDIR>"
finding     = "{finding}"
'''


def _planted_script(path: str, text: str) -> str:
    """`text` written at `path` and made executable: a planted git or a
    planted command on a PATH of the arm's own. Returns `path`."""
    pathlib.Path(path).write_text(text, encoding="utf-8")
    os.chmod(path, 0o755)
    return path


def _subject(name: str, command: str = '["<PYTHON>", "stub.py"]',
             root: str = ".") -> str:
    """The `[subject]` table a scratch manifest opens with, written once:
    `name`, `root`, `command` as the TOML array it spells, and the
    `census.toml` beside it."""
    return f'''\
[subject]
name    = "{name}"
root    = "{root}"
command = {command}
census  = "census.toml"
'''


_STUB_MANIFEST = _subject("stub") + '''
[inputs._subject]
args     = []
surfaces = ["help"]

[surfaces.help]
args = ["--help"]
'''

#: A mutants file `mutants.load_mutants` reads and `mutants.preflight` passes:
#: its one mutant names a `find` the stub subject holds once. The stub's
#: directory is no git repository, so a `mutants` that reaches `run_mutants`
#: with it ends at the refusal of the first clone and starts no subject.
_STUB_MUTANTS = '''\
[checks.comparator]
builtin = "compare"
golden  = "golden"

[[mutant]]
name    = "a site the stub holds"
file    = "stub.py"
find    = "stub ok"
replace = "a planted site"
expect  = ["comparator"]
'''


def _scratch(box: str, manifest_text: str = _STUB_MANIFEST,
             census_text: str = _STUB_CENSUS,
             extra: dict[str, str] | None = None) -> str:
    """Write a throwaway subject, census and manifest into `box`, made if it
    is not there yet. Returns the manifest path."""
    os.makedirs(box, exist_ok=True)
    files = {"stub.py": _STUB_SUBJECT, "census.toml": census_text,
             "manifest.toml": manifest_text}
    files.update(extra or {})
    for name, text in files.items():
        pathlib.Path(os.path.join(box, name)).write_text(text, encoding="utf-8")
    return os.path.join(box, "manifest.toml")


def _plant_marker(golden: str) -> None:
    """Give a scratch golden directory the marker a real capture carries.

    `read_capture` refuses a directory that holds no capture, so an arm whose
    plant is a bare `mkdir` would meet THAT refusal instead of the one it is
    about. The marker is what `Recorder.finish` writes, so the plant is a
    capture directory rather than a directory the test was allowed to pass.
    """
    inner = os.path.join(golden, "_subject")
    os.makedirs(inner, exist_ok=True)
    pathlib.Path(os.path.join(inner, SURFACES_FILE)).write_text("{}\n", encoding="utf-8")


#: What a row's detail says when the log carried no verdict line at all.
_NO_VERDICT = "(no verdict line in the log)"


def _one_line(text: str, limit: int = 200, *, needles: tuple[str, ...] = (),
              empty: str = "") -> str:
    """A command's log as ONE line, for a row's detail.

    With no `needles` every non-blank line is kept: the whole text IS the
    verdict, which is what a refusal's own sentence is. With them, only the
    lines that carry one — a self-test row's detail is evidence, and a banner
    and a directory path say nothing about what the command decided.
    """
    lines = [line.strip() for line in text.strip().splitlines()
             if line.strip() and (not needles
                                  or any(needle in line for needle in needles))]
    return " | ".join(lines)[:limit] or empty


def _command_phrase(argv: list[str]) -> str:
    """The phrase a git command refuses with when it would not START:
    `git` and its subcommand, past any leading `-C <dir>` or `-c <key=value>`
    pair — the two option shapes `_repo_of` writes — so no scratch path and
    no identity setting stands where the command's name should.

    It names the command and not the caller: the same absence reaches
    `--selftest`, which refuses, and a self-test that files a disclosed SKIP,
    and a phrase carrying one caller's name would be wrong in the other's
    row. The caller puts its own name in front of what it prints.
    """
    rest = argv[1:]
    while len(rest) > 1 and rest[0] in ("-C", "-c"):
        rest = rest[2:]
    return f"`{' '.join([*argv[:1], *rest[:1]])} …`"


def _repo_of(root: str, message: str,
             what: Callable[[list[str]], str] = _command_phrase
             ) -> tuple[int, str, str]:
    """`git init`, `git add -A` and one commit of `message` in `root`, so the
    directory is a clean repository at one sha.

    ONE helper for a loop every caller that needs a throwaway repository
    shares — the mutants arms' subjects, the bundled fixture's copy, the
    clone cache's origin and the git arm's own repository — each with its own
    verdict on a failure. The verdicts stay each caller's, which is why this
    returns `(0, "", "")` on success and `(exit, the command's first four
    words, stderr)` for the first command that failed rather than deciding a
    sentence. `what` is the phrase `launch` opens its refusal with when a git
    will not START: `_command_phrase`'s by default, or the caller's own when it
    passes one (the git arm does).

    The commit starts no background maintenance (`core.GIT_NO_MAINTENANCE`
    says why): otherwise the arm's box can fail to be removed. Each command
    runs as `core.git_command` builds it, so the reader's global git
    configuration (an ignore file naming a file of the arm's, `core.autocrlf`)
    does not decide what the commit holds; `what` and the returned words are
    of the command without those settings.
    """
    for argv in (["git", "init", "--quiet", root],
                 ["git", "-C", root, "add", "-A"],
                 ["git", "-C", root, *GIT_IDENTITY, *GIT_NO_MAINTENANCE,
                  "commit", "-qm", message]):
        proc = launch(git_command(*argv[1:]), what(argv), env=git_env(what(argv)))
        if proc.returncode != 0:
            return (proc.returncode, " ".join(argv[:4]),
                    proc.stderr.strip()[:QUOTE])
    return 0, "", ""


# ----------------------------------------------- a child that runs the package
#
# Two pieces, independent: the argv of a child that runs the package makes it
# say which copy it imported, and the reader of what that child printed. Every
# site keeps its own `launch` call, with its own working directory,
# environment and standard input; neither piece starts a process.


def _package_argv(*after: str, python: str | None = None) -> list[str]:
    """The argv of a child that runs the package: the interpreter, the option
    that makes the package print, on standard error and before anything else,
    the directory it was imported from (`golden_census.SAY_WHERE_OPTION`),
    and `after` — `"-m", IMPORT_NAME, …` or `"-c", code, …`, as the site
    spells it. `python` is another interpreter than the one running the
    self-check (arm `uu`'s below-the-floor one).

    The option and not a variable, so it is in the argv a site passes and no
    site's environment needs a key: `-X` reaches the child's own interpreter
    and no process the child starts.
    """
    return [python if python is not None else sys.executable,
            "-X", SAY_WHERE_OPTION, *after]


class _Heard(NamedTuple):
    """A child's standard error, split at the line `_package_argv` makes the
    package print.

    `where` is the directory the child printed, or None when it printed no
    such line. `own` is everything after that line: the child's own text,
    and all of it when there is no line. `noise` is everything before it:
    what the interpreter printed while its site files ran, before the
    package was imported.
    """

    where: str | None
    own: str
    noise: str

    def not_from(self, expected: str) -> str:
        """`""` when the child imported the package from `expected`, else the
        clause, opening `; `, that a row's detail carries: the child printed
        no such line, so the package did not start or another package did,
        or the directory it did import from. A row holds when this is
        empty."""
        if self.where is None:
            return ("; the child printed no package directory line, so the "
                    "package did not start, or another package did")
        if self.where != expected:
            return (f"; the child imported the package from {self.where}, "
                    f"not from {expected}")
        return ""


def _heard(stderr: str) -> _Heard:
    """`stderr` split into the child's directory line, its own text and the
    noise before the line. No pattern and no list: the interpreter runs its
    site files before it imports the package, so whatever came before the
    line is the interpreter's and whatever came after is the child's."""
    if stderr.startswith(SAID_WHERE):
        start = 0
    else:
        found = stderr.find("\n" + SAID_WHERE)
        if found < 0:
            return _Heard(None, stderr, "")
        start = found + 1
    end = stderr.find("\n", start)
    if end < 0:
        end = len(stderr) - 1
    return _Heard(stderr[start + len(SAID_WHERE):end], stderr[end + 1:],
                  stderr[:start])


# ------------------------------------------- an interpreter that prints at startup


#: The probe's answer for the default call, kept for the life of the process:
#: the seven arms that read a child's output alone ask the same question of
#: the same interpreter and environment, and one process asks it once.
_NOISE_SEEN: list[tuple[str, str] | None] = []

_NOISE_QUOTE = 80


def _startup_noise(env: Mapping[str, str] | None = None,
                   python: str | None = None) -> tuple[str, str] | None:
    """What the interpreter prints before any program runs: None when
    `python -c pass` writes nothing on either stream, else the stream's name
    (`standard error` or `standard output`) and the text.

    A `.pth` file, a `sitecustomize.py` or a `usercustomize.py` that prints
    puts its line in every child, golden-census's own included; an arm that
    reads a child's output as the child's alone cannot tell it from the
    child's. The default call (`env` and `python` both None) runs once and
    keeps its answer; a call naming either runs every time, because the
    answer is that environment's. An interpreter that cannot be started
    answers with the error's text on standard error: no arm can start its
    child either.
    """
    default = env is None and python is None
    if default and _NOISE_SEEN:
        return _NOISE_SEEN[0]
    saw: tuple[str, str] | None = None
    try:
        done = launch([python if python is not None else sys.executable,
                       "-c", "pass"], "the start-up probe", env=env,
                      text=False)
    except WouldNotStart as exc:
        saw = ("standard error", str(exc))
    else:
        for name, data in (("standard error", done.stderr),
                           ("standard output", done.stdout)):
            text = data.decode("utf-8", errors="surrogateescape")
            if text:
                saw = (name, text)
                break
    if default:
        _NOISE_SEEN.append(saw)
    return saw


# The reason is the SKIP's and the arm's own label stays what it asserts: an
# arm passes this text to `skip` and never rewrites its label around it.
def _startup_noise_reason(noise: tuple[str, str]) -> str:
    """The sentence a SKIP carries when `_startup_noise` found something,
    with the stream's name and the first line of the text, cut at 80
    characters. It is the SKIP's reason and the arm's own label stays what
    the arm asserts; the words live here once, for the seven arms."""
    stream, text = noise
    first = (text.splitlines() or [""])[0][:_NOISE_QUOTE]
    return (f"The interpreter running this self-check prints at startup: "
            f"`python3 -c pass` wrote `{first}` on {stream}. That comes from "
            "Python's own site files, not from golden-census, and this arm "
            "reads a child's output as the child's alone, so it is not run. "
            "Find the file with `python3 -m site`: a `.pth`, "
            "`sitecustomize.py` or `usercustomize.py` in a directory it "
            "lists. Delete or repair it, and run the self-check again.")
