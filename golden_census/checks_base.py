"""What every arm file stands on: where the package is, the bundled fixture
prepared as a working copy (`prepare_fixture`), the scratch roots a control
runs in, the second independent copy of a module
an arm rebinds an attribute of, the child that runs the command line with no
room for a file (`_without_file_room`), the recorder that collects a body's
check and skip rows, and the two readers more than one subject needs — the
refusal a call produces, and the absolute paths a text carries.

Under every `checks_*` module and under `selfcheck` itself, so a helper two
subjects share has one home and the import graph has no cycle in it.
"""

from __future__ import annotations

import ast
import contextlib
import errno
import functools
import importlib.util
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable, Container, Iterator
from typing import Any, NamedTuple

from .controls import CheckRow, SkipRow, census_controls
from .core import (
    ACTUAL,
    IMPORT_NAME,
    Layout,
    launch,
    package_dir,
    Refusal,
    refusal_text,
    Roots,
)
from .manifest import Manifest
from .proof import _package_argv, _repo_of
from .census import _git_failed

#: The package's own source, for the arms that walk it (ii, ss) and for the
#: patched-copy controls. Through `core.package_dir`, the one asker of where
#: the package is: an install that carries the package as a zip file has no
#: directory here, and every reader of this says so rather than raising.
PACKAGE = package_dir()


#: How a SELF-CHECK module is recognized, and the one thing every walk over
#: the package's own source needs to know about itself.
#:
#: An arm drives the mechanism it is about — it opens a process group, it
#: quotes the word `REFUSED: ` in an assertion — and a walk counting DECISIONS
#: or PRODUCERS must not read those as either. A naming RULE and not a list,
#: because a list is what a new arm file is silently left out of, and left out
#: it looks like a second decider.
_ARM_RUNNER = "selfcheck.py"
_ARM_PREFIX = "checks_"


def is_arm_module(name: str) -> bool:
    """Whether `name` is one of the self-check's own modules."""
    return name == _ARM_RUNNER or name.startswith(_ARM_PREFIX)


def arm_modules_named() -> str:
    """How a row's sentence names that set, so the walks and the sentence
    cannot drift apart."""
    return f"{_ARM_RUNNER} and every {_ARM_PREFIX}*.py"


def _control_roots() -> Roots:
    return Roots(root="/somewhere", work="/tmp/golden-census-x", clone=None)


# ------------------------------------------------ one decider per decision
#
# The arms below prove that a decision the package makes exists in ONE place.
# They read the package's own source, because "how many places decide this"
# is a fact about the code and not about any run of it.


def _ast_owners(tree: ast.AST) -> list[tuple[int, int, str]]:
    """`(first line, last line, name)` for every `def` in `tree`.

    One owner for the question every source-walking arm asks second: the walk
    finds a node, and the row it prints names the FUNCTION that node sits in,
    because "which function does this" is the claim, not "which file".
    """
    return [(node.lineno, node.end_lineno or node.lineno, node.name)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)]


def _owner_at(owners: list[tuple[int, int, str]], line: int) -> str:
    """The innermost `def` spanning `line`, or module level. `max` over the
    enclosing spans is the innermost one: a nested function starts later than
    the function it is written inside."""
    enclosing = [row for row in owners if row[0] <= line <= row[1]]
    return max(enclosing)[2] if enclosing else "(module level)"


def _named(node: ast.expr) -> str:
    """The name `node` spells — `Refusal` for both `Refusal` and
    `core.Refusal` — or `""` when it spells none."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _call_sites(source: str, name: str, called: Container[str]) -> list[str]:
    """`file:line in owner()` for every CALL in `source` of a function whose
    name is in `called`, by an `ast` walk.

    A call and not a mention: `from .selfcheck import selfcheck` names it and
    decides nothing, and a text search cannot tell the two apart. The owner
    is the innermost enclosing `def`, because the question a walking arm
    answers is which FUNCTION makes the call, not which file it sits in.
    """
    tree = ast.parse(source, filename=name)
    owners = _ast_owners(tree)
    return sorted(f"{name}:{node.lineno} in {_owner_at(owners, node.lineno)}()"
                  for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and _named(node.func) in called)


def _census_rows(manifest: Manifest, roots: Roots
                 ) -> tuple[list[tuple[str, bool, str, str]], list[tuple[str, str]]]:
    """`_rows_of` over one manifest's census controls under `roots`: the rows
    and the skips `census_controls` files for it."""
    return _rows_of(lambda check, skip: census_controls(
        manifest.census, manifest, roots, check, skip))


def _walk_package(sites: Callable[[str, str], list[str]],
                  package: str = PACKAGE
                  ) -> tuple[dict[str, str], list[str], str]:
    """`(source by file name, every site the walk found, the reason it could
    not be done)` over every module beside this one, or beside `package`.

    Every arm that walks the package's source asks the same two things first:
    read every `.py` file of the package, and say in one sentence why not when
    it cannot, naming the file it stopped at. A package run from a zip file
    carries no source beside the module, and an arm that reported that as a
    clean walk would be the false clean these arms exist to refuse. An arm
    that wants only the sources passes a `sites` that collects nothing.
    `package` is another directory only for arm `cccccccc`, which plants a
    file the walk cannot read in a scratch copy.
    """
    layout = Layout.detect()
    if not layout.source:
        return {}, [], (layout.inside_absent("a `.py` source file")
                        + " Nothing was read and nothing is claimed.")
    sources: dict[str, str] = {}
    found: list[str] = []
    name = ""
    try:
        for name in sorted(os.listdir(package)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(package, name), encoding="utf-8") as handle:
                sources[name] = handle.read()
            found += sites(sources[name], name)
    except (OSError, SyntaxError, ValueError) as exc:
        at = f" at {name}" if name else ""
        return {}, [], (f"the package's own source could not be walked{at} "
                        f"({type(exc).__name__}: {exc}). What was read is "
                        "not used, and nothing is claimed.")
    return sources, sorted(found), ""


def _walk_for_plant(sites: Callable[[str, str], list[str]], label: str,
                    skip: SkipRow, planted_in: str, control: str
                    ) -> tuple[dict[str, str], list[str]] | None:
    """`(source by file name, every site the walk found)`, or `None` after
    `skip` recorded the SKIP of `label`.

    The walk can fail (`_walk_package`'s reason), and the module the arm
    plants its control into, `planted_in`, can be missing from what was read:
    either is a disclosed SKIP, the second saying that the `control` named
    ("planted-<control> control") cannot be built.
    """
    sources, found, why = _walk_package(sites)
    if why:
        skip(label, why)
        return None
    if planted_in not in sources:
        skip(label, f"{planted_in} was not found beside this module, so the "
                    f"planted-{control} control cannot be built. Nothing is "
                    "claimed.")
        return None
    return sources, found


def _capture_broke(check: CheckRow, label: str, why: str) -> None:
    """The red row of an arm whose planted stub subject golden-census's own
    capture would not record.

    The arm measures what a capture, a comparison or a `mutants` run does
    over that subject, and it has nothing to measure when the capture itself
    refuses or exits non-zero: a defect in the capture, which an arm that
    SKIPPED would hide behind a disclosed SKIP. `why` is what the capture
    said, quoted in the detail. A reason that is the machine's — no `git`, a
    repository that could not be made — stays the arm's SKIP.
    """
    check(label, False, f"{ACTUAL}{why}",
          next="golden-census's own capture of this arm's planted subject "
               "refused or exited non-zero, so the arm had nothing to "
               "measure. Fix the capture first: the detail quotes what it "
               "said, and every arm that records a stub subject measures "
               "again once it records one.")


def _fresh_module(name: str) -> Any | None:
    """A second, independent copy of one module of this package, or None when
    this install carries no importable source for it.

    The positive control behind every arm that asserts something one of the
    package's own rules decides: rebind an ATTRIBUTE of the copy to the narrow
    rule and watch the row go red. An attribute and not a patched SOURCE, which
    would couple an arm to an exact line of `probe.py` — rewording that line
    breaks the control rather than the thing it controls — and which an install
    carrying the package as a zip file cannot build at all: there is no `.py`
    to read there, and the raise takes every arm after it with it.

    The copy is executed from the SAME spec the real module was, so its
    relative imports resolve against the real package and nothing but the
    rebinding differs. It is not registered in `sys.modules`: the copy is the
    arm's and no other importer should get it.
    """
    try:
        spec = importlib.util.find_spec(f"{__package__}.{name}")
    except (ImportError, ValueError):
        return None
    if spec is None or spec.loader is None:
        return None
    copy = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(copy)
    except (OSError, ImportError):
        return None
    return copy


# ------------------------------------------- a command line with no file room
#
# A write that fails as on a full disk, planted plainly: a child whose files
# may hold no byte (`RLIMIT_FSIZE` 0), so its first write to a file raises
# `File too large` at whatever site makes it. Arms dddddddd and qqqqqqq run
# the real command line in it.

#: What the first write of a `_NO_FILE_ROOM` child raises.
_NO_FILE_ROOM_ERROR = OSError(errno.EFBIG, os.strerror(errno.EFBIG))

#: The child. `sys.argv[1]` names what is cut out of the package before the
#: command runs: `none`; `unanswered`, `cli._unanswered` handing the error
#: back, which is `cli.main` with that answer cut out; `undo`, `Made.undo`
#: undoing nothing, so what a refusal would have taken back stays in view.
_NO_FILE_ROOM = (
    "import resource, sys\n"
    "resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))\n"
    f"from {IMPORT_NAME} import cli, console, core\n"
    "def handed_back(error):\n"
    "    raise error\n"
    "if sys.argv[1] == 'unanswered':\n"
    "    cli._unanswered = handed_back\n"
    "if sys.argv[1] == 'undo':\n"
    "    core.Made.undo = lambda self: None\n"
    "sys.exit(console.main(sys.argv[2:]))\n")


def _without_file_room(cut: str, argv: list[str], what: str,
                       cwd: str) -> subprocess.CompletedProcess[str]:
    """One run of the real command line `argv` in a `_NO_FILE_ROOM` child,
    `cut` cut out first, with this package first on its import path. The
    child says which copy it imported (`_package_argv`); each caller reads
    that off the standard error it gets back (`proof._heard`)."""
    return launch(_package_argv("-P", "-c", _NO_FILE_ROOM, cut, *argv), what,
                  env=dict(os.environ, PYTHONPATH=os.path.dirname(PACKAGE)),
                  cwd=cwd)


# ------------------------------------------------------ the bundled fixture


def _writable_copy(source: str, destination: str) -> None:
    """Copy the directory `source` to `destination`, then give the owner's
    write bit to every directory and file of the copy.

    A copy golden-census makes of its own data — the bundled fixture, the
    shipped templates — is the self-test's to write in, whatever modes the
    install keeps (a Nix store, a read-only site-packages): `shutil.copytree`
    keeps the source's modes, the directories' included, and nothing here
    changes a mode of `source`. A mode that cannot be changed is left as it
    is, as `core.remove_tree` leaves one: the write that meets it fails,
    naming the path in the operating system's words. A mode is no byte any
    golden records, so no verdict moves with it.

    The `OSError` `copytree` raises is the caller's.
    """
    shutil.copytree(source, destination)
    for directory, _names, files in os.walk(destination):
        for path in (directory, *(os.path.join(directory, name)
                                  for name in files)):
            with contextlib.suppress(OSError):
                os.chmod(path, stat.S_IMODE(os.stat(path).st_mode)
                         | stat.S_IWUSR)


#: Arms ttttttt's and bbbb's plant: the modes an install that cannot be
#: written gives the bundled fixture and the templates — every directory at
#: 0555, every file at 0444.
_READ_ONLY_DIRECTORY = 0o555
_READ_ONLY_FILE = 0o444


@contextlib.contextmanager
def _modes_planted(planted: dict[str, int], before: dict[str, int],
                   probe: str) -> Iterator[bool]:
    """Put each path of `planted` at its mode, and yield whether the plant
    bites: whether the directory `probe` could NOT be made, which root can
    make in a 0555 directory. Each path of `before` is put back at its mode
    in a `finally`, on every way out. Arms ttttttt and bbbb plant an
    install's read-only modes with it."""
    try:
        for path, mode in planted.items():
            os.chmod(path, mode)
        try:
            os.mkdir(probe)
        except OSError:
            yield True
        else:
            os.rmdir(probe)
            yield False
    finally:
        for path, mode in before.items():
            os.chmod(path, mode)


class Fixture(NamedTuple):
    """A prepared fixture, or the reason there is none.

    `path` is the copy's directory when one was made and None when it was
    not. `why` is the WHOLE sentence saying what was missing and what that
    left behind, with no command's name in front of it, and `next` is what to
    do about it. A caller prints `why` as it stands and adds nothing: a
    disclosure of what was made is a fact about the attempt, and the function
    that made the attempt is the one that knows it.

    An absence is RETURNED and never raised, because the callers want three
    different things from it: `--selftest` cannot run at all and refuses,
    while a self-test that needs a fixture files a disclosed SKIP and lets
    the self-tests after it run. A raise here makes one caller's sentence the
    whole run's verdict, and the type makes a caller that ignores the absence
    a checker error rather than a wrong sentence.
    """

    path: str | None
    why: str
    next: str


def prepare_fixture(box: str) -> Fixture:
    """A working copy of the bundled fixture, its subject in a git repository.

    The subject is a repository because the census carries a `git-checkout`
    precondition and the stub reads its own commit — both of which a real
    subject does, and neither of which a bare directory of files can satisfy.

    The copy is `_writable_copy`'s, so a fixture an install keeps read-only
    is a copy `git init` can write in.

    No `Refusal` escapes this function, the one `core.launch` raises for a
    `git` that will not start included, and no `OSError` from the copy, the
    one a fixture holding a file or a directory this user cannot read
    raises: the absences are the return value.
    """
    if shutil.which("git") is None:
        return Fixture(
            None,
            "`git` is not on PATH. The bundled fixture's census carries a "
            "git-checkout precondition and its mutants need `git clone "
            "--local`, so nothing here can be measured; nothing was made and "
            "nothing is claimed.",
            "Install git, or run `--selfcheck`, which needs none.")
    layout = Layout.detect()
    if layout.fixture is None:
        return Fixture(
            None,
            layout.inside_absent("the bundled fixture") + " The self-test "
            "measures golden-census against a subject that ships with it; "
            "nothing was made and nothing is claimed.",
            "Run `--selftest` from a checkout of golden-census, or run "
            "`--selfcheck`, which needs no fixture.")
    fixture = os.path.join(box, "fixture")
    try:
        _writable_copy(layout.fixture, fixture)
    except OSError as error:
        # `copytree` raises a fault in reading the fixture's own directory as
        # it is, and gathers every fault below it into ONE `shutil.Error`,
        # each entry the text of the `OSError` it caught: either way what is
        # quoted is the operating system's answer, naming its path.
        said = ("; ".join(entry[2] for entry in error.args[0])
                if isinstance(error, shutil.Error) else str(error))
        return Fixture(
            None, f"the bundled fixture {layout.fixture} could not be copied: "
            f"{said}. Whatever part of the copy was made went into the "
            f"scratch directory {box}; nothing is claimed.",
            "The operating system's answer above says what stopped the copy "
            "(a path it could not read, or no room for a file); fix that, "
            "or run `--selfcheck`, which needs no fixture.")
    try:
        code, head, stderr = _repo_of(os.path.join(fixture, "subject"),
                                      "the bundled fixture")
    except Refusal as refused:
        # `_repo_of` runs git through `core.launch`, which refuses when the
        # program will not START — a different fault from a git that ran and
        # exited non-zero, and an absence of the same kind to every caller.
        return Fixture(None, f"{refused} The fixture copy, all that was "
                       "made, went into the scratch directory "
                       f"{box}; nothing is claimed.", refused.next)
    if code != 0:
        # `_repo_of` hands back the exit, the command's first words and its
        # stderr; `_git_failed` words them as it words every failed git.
        failed = _git_failed(f"`{head}`", subprocess.CompletedProcess(
            [head], code, "", stderr))
        return Fixture(
            None, f"{failed}. The fixture copy, all that was made, went "
            f"into the scratch directory {box}; nothing is claimed.",
            "Run that git command by hand in a scratch directory; the "
            "self-test builds a repository of its own and cannot start "
            "without one.")
    return Fixture(fixture, "", "")


def _refused_by(body: Callable[[], object],
                render: Callable[[Refusal], str] = str, *,
                unrefused: str = "NOT REFUSED") -> str:
    """The refusal `body` raises, as `render` writes it, or `unrefused` when
    it raised none.

    A refusal is the whole subject of the arms below, so what they compare is
    the sentence a reader would see and not an exception type. `unrefused` is
    the caller's word because some arms PRINT it — a load that went through
    reads `LOADED` in their detail, and a cut to one shared word would move
    that line.
    """
    try:
        body()
    except Refusal as refused:
        return render(refused)
    return unrefused


# The whole block `body` refuses with — the sentence AND the `next:` line
# under it — or a verdict saying it did not refuse. Beside the bare
# `_refused_by` rather than instead of it, because the two answer different
# questions. `str(Refusal)` is the message, which is what an arm about WHAT
# WENT WRONG compares; the `next:` line is produced at exactly one site
# (`core.refusal_text`) and is what an arm about the WAY FORWARD has to read.
# An arm that asserted a way forward against the message alone would go red
# however good the sentence was.
_printed_refusal = functools.partial(_refused_by, render=refusal_text)


def _rows_of(body: Callable[[CheckRow, SkipRow], object]
             ) -> tuple[list[tuple[str, bool, str, str]], list[tuple[str, str]]]:
    """Every row `body` reports, as `(label, ok, detail, next)`, and every
    skip, as `(label, reason)`.

    A recorder rather than a `Report`, because what its callers ask of a row
    is a field — whether it passed, what its detail or its `next` sentence
    says — which the printed block shows only in part. What `body` returns is
    not kept, and neither is what a row `told`: an arm that asks about those
    lines reads them where a reader does, in a `Report`'s printed block.
    """
    rows: list[tuple[str, bool, str, str]] = []
    skips: list[tuple[str, str]] = []

    def check(label: str, ok: bool, detail: str, *, next: str = "",
              told: tuple[str, ...] = ()) -> None:
        rows.append((label, ok, detail, next))

    def skip(label: str, reason: str) -> None:
        skips.append((label, reason))

    body(check, skip)
    return rows, skips


#: A path spelled from the root: the start of a line or a space, then an
#: `os.sep` and something. `docs/mutants-format.md` and `<input>/<surface>` are
#: not rooted paths and must not be read as ones, which is why the separator
#: has to OPEN the token rather than merely appear inside it.
_ROOTED_RE = re.compile(r"(?<![^\s])" + re.escape(os.sep) + r"\S+")


def _rooted(text: str) -> list[str]:
    """Every root-anchored path `text` spells, in order.

    A rooted path is a fact about the machine: it moves the token count of a
    priced block and it carries a home directory into whatever the reader
    pastes. Naming them is how an arm says which one leaked.
    """
    return _ROOTED_RE.findall(text)
