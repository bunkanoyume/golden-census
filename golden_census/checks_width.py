"""The arms over the temp root's WIDTH and over what a command's output costs.

One property, two questions. A capture pins its subject's TMPDIR to a
directory of a fixed width, so a machine whose own root is too wide can run
no capture — and must say so once, as a refusal about the machine, rather
than as a page of failed rows. And a command's output must be the same size
under any root and name no directory of the machine, which is what the
census's path folds are for.
"""

from __future__ import annotations

import contextlib
import errno
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from typing import Any, NamedTuple

from .census import (
    load_census,
)
from .cli import main
from .controls import CheckRow, SkipRow
from .core import (
    widest_root,
    ACTUAL,
    IMPORT_NAME,
    Layout,
    fixed_dir_refusal,
    fixed_dir_room,
    launch,
    make_fixed_dir,
    Platform,
    Refusal,
    refusal_text,
    require_cache_dir,
    temp_base,
    UNREPORTABLE,
)
from .docs import (
    PRICED,
    Invocation,
    measure,
)
from .proof import (
    _box,
    _env_as,
    _heard,
    _made_under,
    _one_line,
    _package_argv,
    _quietly,
    _scratch,
    _tmpdir_as,
)
from .checks_base import (
    PACKAGE,
    _rooted,
    _rows_of,
    prepare_fixture,
)
from .checks_census import (
    manifest_free_folds,
)
from .templates import shipped_templates

@contextlib.contextmanager
def _tmpdir_as_unguarded(root: str) -> Iterator[None]:
    """`_tmpdir_as` with its `finally` REMOVED — the counterfactual arm `qqq`
    is the control for, written out rather than described.

    Used by that arm and by nothing else. It is the window every arm would
    type by hand, restore included, and the one an arm types without a
    `finally`: an exception inside such a window leaves `TMPDIR` at the scratch
    value for every later `core.temp_base()` caller in the run — a self-check
    that then reports about a root nobody set.
    """
    was = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = root
    yield
    if was is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = was


def _raise_in_window(window: Callable[[str], Any], root: str) -> str | None:
    """`TMPDIR` after an exception is raised inside `window(root)`."""
    with contextlib.suppress(RuntimeError):
        with window(root):
            raise RuntimeError("planted inside the TMPDIR window")
    return os.environ.get("TMPDIR")


#: Temp roots the width arithmetic is asked about, the separator itself
#: first. Each is an absolute STRING: `fixed_dir_room` makes nothing and reads
#: no directory of one, which is what lets this arm ask about roots this
#: machine does not have — and about `/`, where making the directory is not
#: something a control may do.
_WIDTH_BASES = ("/", "/tmp", "/tmp/claude", "/private/var/folders/ab/cd",
                "/a" * 12)


def _width_arithmetic_control(check: CheckRow, skip: SkipRow) -> None:
    """(wwww) the leaf the width rule leaves room for is the right length."""
    label = ("wwww  the room `fixed_dir_room` leaves for a leaf name makes a "
             "path of EXACTLY the pinned width under every temp root, the "
             "separator itself included: `/` adds no separator of its own, so "
             "a rule that subtracted one for it left room for one character "
             "too few there and `make_fixed_dir` refused the path it built as "
             "a golden-census defect. Measured by asking `os.path.join` how "
             "long the path WOULD be; nothing is made, least of all under `/`")
    width = _fixture_width()
    if width is None:
        skip(label, f"{_no_fixture_census()} The pinned TMPDIR width is "
                    "read off it and is not spelled anywhere else in the "
                    "package. Nothing is claimed.")
        return
    lengths: dict[str, int] = {}
    for base in _WIDTH_BASES:
        normalized, room = fixed_dir_room(base, width)
        lengths[base] = len(os.path.join(normalized, "x" * room))
    # The pin is also read at a width where there is NO room, which is the
    # other side of the same arithmetic and the branch `make_fixed_dir`
    # refuses on: a root as wide as the pin leaves nothing for a leaf.
    _normalized, none_left = fixed_dir_room("/" + "w" * width, width)
    check(label,
          all(length == width for length in lengths.values()) and none_left < 1,
          f"{ACTUAL}a pin of {width} characters -> "
          + ", ".join(f"{base!r} makes {length}" for base, length in lengths.items())
          + f"; a root as wide as the pin leaves {none_left} character(s) for a "
          "leaf, which is the refusal branch")


#: The first pin arm `rrrrrrr` asks for. Its name is longer than the 64
#: characters two `uuid4().hex` hold under any root of fewer than 135
#: characters.
_WIDE_PIN = 200


def _wide_pin_control(check: CheckRow, skip: SkipRow) -> None:
    """(rrrrrrr) a wide `<FIXED-WIDTH-DIR:N>` is made at exactly its width,
    or refused, and either way leaves nothing behind.

    Run under a private root `proof._made_under` makes, so the listing it
    hands back is everything `make_fixed_dir` left. Three pins: 200
    characters; the root, a separator and a name as long as the file system
    takes, its limit asked of `os.pathconf` for that root and never stated;
    and one character wider. The first two must each be a directory of
    exactly the pinned width, removed here once measured; the third must be
    a `Refusal`, never an `OSError`, carrying the root, the width, the name's
    length and the operating system's reason for a name one character too
    long, with the `next:` line that names the census's pin. The second pin's
    name is longer than 64 characters under every root, so a name capped at
    two `uuid4().hex` is red here under every root the arm runs under.

    The private root is the temp root and 31 characters more. Where it is
    wider than `widest_root(_WIDE_PIN)`, a pin of 200 has no room under it
    and `make_fixed_dir` refuses it for the width alone: the arm SKIPs,
    naming the private root's width, before it makes anything.
    """
    label = ("rrrrrrr  `make_fixed_dir` under this arm's own temp root makes "
             "a directory of EXACTLY the pinned width for a pin of "
             f"{_WIDE_PIN} characters and for a pin whose name is the longest "
             "the file system takes, read from `os.pathconf` and never "
             "stated; a pin one character wider than that is ONE refusal "
             "naming the root, the width, the name's length and the "
             "operating system's reason, with a `next:` line, never a Python "
             "traceback; and nothing is left under the arm's root afterwards")
    reason = os.strerror(errno.ENAMETOOLONG)

    def made(root: str, width: int) -> tuple[bool, str]:
        try:
            path = make_fixed_dir(root, width)
        except (Refusal, OSError) as error:
            return False, (f"raised {type(error).__name__}: "
                           + _one_line(str(error), 300).replace(root, "<root>"))
        os.rmdir(path)
        return len(path) == width, f"made one of {len(path)} characters"

    def body() -> tuple[list[tuple[bool, str]], int, int | None]:
        root = temp_base()
        if fixed_dir_room(root, _WIDE_PIN)[1] < 1:
            return [], 0, len(root)
        name_max = os.pathconf(root, "PC_NAME_MAX")
        longest = len(os.path.join(root, "")) + name_max
        seen = [made(root, _WIDE_PIN), made(root, longest)]
        wider = longest + 1
        try:
            path = make_fixed_dir(root, wider)
        except Refusal as refusal:
            printed = refusal_text(refusal)
            seen.append((all(part in printed for part in (
                repr(root), f"exactly {wider} characters",
                f"a name of {name_max + 1} characters", reason,
                "next: Lower N in the census's `<FIXED-WIDTH-DIR:N>`.")),
                _one_line(printed, 600).replace(root, "<root>")))
        except OSError as error:
            seen.append((False, f"raised OSError: {error}".replace(
                root, "<root>")))
        else:
            os.rmdir(path)
            seen.append((False, f"made one of {len(path)} characters"))
        return seen, name_max, None

    (seen, name_max, too_wide), left = _made_under(temp_base(), body)
    if too_wide is not None:
        skip(label, f"this arm's own temp root is {too_wide} characters, "
                    f"wider than the {widest_root(_WIDE_PIN)} a pin of "
                    f"{_WIDE_PIN} needs; nothing was made and nothing is "
                    "claimed.")
        return
    check(label, all(ok for ok, _ in seen) and not left,
          f"{ACTUAL}a pin of {_WIDE_PIN} -> {seen[0][1]}; a pin whose name "
          f"is the file system's {name_max} -> {seen[1][1]}; one wider -> "
          f"{seen[2][1]}; left under the arm's root: {left or 'nothing'}",
          next="In `core.make_fixed_dir`, build the name from as many "
               "`uuid4().hex` as the pin's room takes, turn an `OSError` "
               "from `os.mkdir` other than `FileExistsError` into a "
               "`Refusal` naming the root, the width, the name's length and "
               "the error, and `os.rmdir` a directory it made before any "
               "refusal it raises.")


def _tmpdir_window_control(check: CheckRow) -> None:
    """(qqq) an exception inside a `_tmpdir_as` window leaves `TMPDIR` as it
    found it — set back to its old value, or unset when it was unset."""
    label = ("qqq  an exception raised inside a `_tmpdir_as` window leaves "
             "TMPDIR exactly as it found it — restored to its previous value, "
             "and UNSET again when there was none, which are different states "
             "and `core.temp_base()` reads both; the same raise inside the "
             "window this one replaced, whose restore sat after the `yield` "
             "instead of in a `finally`, leaves TMPDIR at the scratch value "
             "for every later caller in the run, which is how this row is "
             "known to be able to go red")
    was = os.environ.get("TMPDIR")
    planted = os.path.join(os.sep, "planted-tmpdir-that-is-never-made")
    known = os.path.join(os.sep, "a-known-tmpdir")
    with _env_as({"TMPDIR": known}):
        set_case = _raise_in_window(_tmpdir_as, planted)
        os.environ.pop("TMPDIR", None)
        unset_case = _raise_in_window(_tmpdir_as, planted)
        os.environ["TMPDIR"] = known
        control = _raise_in_window(_tmpdir_as_unguarded, planted)
    check(label,
          set_case == known and unset_case is None and control == planted
          and os.environ.get("TMPDIR") == was,
          f"{ACTUAL}TMPDIR was {known!r} -> {set_case!r} after the raise; "
          f"unset -> {unset_case!r}; the unguarded window left "
          f"{control!r} (the control); the ambient TMPDIR is "
          f"{os.environ.get('TMPDIR')!r}, as it was: "
          f"{os.environ.get('TMPDIR') == was}",
          next="`_tmpdir_as` restores in a `finally`. A window that restores "
               "after its `yield` is skipped by any exception, and every "
               "`core.temp_base()` caller after it reads the scratch root.")


# ------------------------------------------------------- the two temp roots
#
# A command's output must not depend on how wide this machine's temp root is,
# and must name no directory of it. Every line golden-census prints about the
# machine goes through the census's own path folds for that reason
# (`census.own_log`), and a fold that stopped folding would be invisible: the
# output still reads correctly on the machine that produced it.
#
# So one command is run under two temp roots of different widths and the
# question is asked of the BYTES: the same size, and no absolute path rooted
# at the separator in either block. The counterfactual is the control — the
# same block with the fold undone carries the root and is a different size.
#
# What is measured is owned in CODE, `docs.PRICED`: no document is the subject
# of this, because a document that were would make every figure in it a thing
# a change had to preserve.

#: The command `eee` prices under two roots, and why that one: `capture`'s
#: output moved furthest with the temp root's width, so it is the cheapest
#: single command that can still go red.
_TWO_ROOT_ARM = "`capture`"

#: The one command no two-root arm prices: `--selfcheck`'s own arms quote the
#: scratch directories they plant in their detail lines, BY DESIGN — those
#: paths are the evidence that a control ran, not a leak of the machine.
_UNPRICED_UNDER_TWO_ROOTS = "`--selfcheck`"


def _fixture_width() -> int | None:
    """The `<FIXED-WIDTH-DIR:N>` the bundled fixture's census pins, or None
    when there is no bundled census to read it off — which is what an
    installed copy carrying only the package is.

    ONE reader for three callers, each of which would otherwise carry its own
    `isfile` plus `load_census`.
    """
    fixture = Layout.detect().fixture
    if fixture is None or not os.path.isfile(
            os.path.join(fixture, "census.toml")):
        return None
    return load_census(os.path.join(fixture, "census.toml")).fixed_width


def _no_fixture_census() -> str:
    """The absence `_fixture_width`'s None stands for: `Layout`'s one
    sentence when the package holds no fixture directory, and the census
    named in that directory when the directory is there; each caller adds
    what did not run because of it."""
    layout = Layout.detect()
    if layout.fixture is None:
        return layout.inside_absent("the bundled fixture's census")
    return f"there is no readable census.toml in {layout.fixture}."


def _wide_root() -> int | None:
    """The widest temp root a capture can still run under, read off the
    bundled fixture's census rather than typed here.

    A capture makes a TMPDIR of exactly the pinned width, and the shortest
    path it can make under a root is the root, a separator and one character —
    so the widest root that still fits is the pin minus two. Read off the
    census rather than typed beside a `_width_sentence` that already reads it,
    because two statements of one piece of arithmetic drift: a fixture that
    repins its width moves both of these. None when there is no fixture census
    to read, which is what an installed copy is.
    """
    width = _fixture_width()
    return None if width is None else widest_root(width)


def _wide_root_refusal() -> Refusal | None:
    """The refusal `--selftest` owes a temp root too wide for the width the
    bundled fixture's census pins, or None when the root fits.

    Asked ONCE, up front, before the CONTROLS group and before anything is
    made — so no group ever meets the condition. The width rule keeps its one
    owner: `core.fixed_dir_room` decides it and `core.fixed_dir_refusal`
    words it, for `capture` and for here alike, and this asks that owner
    rather than restating the arithmetic.

    Why up front rather than row by row. The root's width is a statement
    about the MACHINE — true before the first arm runs, unchanged by every
    one of them, and fixable only by pointing TMPDIR somewhere else.
    Reported as rows it reads as a broken program: two red CAPTURE rows, a
    COMPARE that then runs against a capture directory nothing made, and a bare
    `FileNotFoundError` sitting above the one sentence that says what to do.
    The CAPTURE group's row still reports a
    SUBJECT-level refusal — a manifest the example cannot load, a subject
    that will not run — as a row, because that one is about the very thing
    the row is testing.
    """
    width = _fixture_width()
    if width is None:
        return None                 # no bundled census, so nothing to ask
    base, room = fixed_dir_room(temp_base(), width)
    return None if room >= 1 else fixed_dir_refusal(base, width)


def _width_sentence(base: str, wide: int) -> str:
    """The sentence `capture` itself refuses a too-wide temp root with, for the
    width the bundled fixture's census pins."""
    width = _fixture_width()
    if width is None:
        return (f"the temp root {base!r} is {len(base)} characters, wider "
                f"than the {wide} a capture needs.")
    return f"{fixed_dir_refusal(base, width)}."


class _Priced(NamedTuple):
    """One temp root, and what each row it priced cost under it."""

    root: str
    measured: dict[str, tuple[int, int, int]]
    blocks: dict[str, str]

    @property
    def width(self) -> int:
        return len(self.root.rstrip(os.sep)) or 1


def _price_under(root: str, priced: tuple[Invocation, ...],
                 keys: set[str] | None = None) -> tuple[_Priced | None, str]:
    """Every command of `priced` — or the `keys` named — run with `root` as
    TMPDIR, or `(None, why not)`.

    The fixture is prepared UNDER that root, because the question is whether
    the root's width reaches the text: a fixture prepared somewhere else would
    put the manifest, the subject and the `--out` directory under the other
    root and measure nothing at all.

    The absence is the None and the sentence `_second_root` two functions
    below already hands back, for the same reason: a measurement that could not be made is a
    disclosed SKIP in the caller's own row and never a refusal of the run. A
    SKIP carries no `next`, so the sentence is the whole of it.
    """
    with _tmpdir_as(root):
        with _box("golden-census-tworoot-") as box:
            prepared = prepare_fixture(box)
            if prepared.path is None:
                return None, prepared.why
            blocks: dict[str, str] = {}
            measured = measure(priced, prepared.path, box, blocks, keys)
            return _Priced(root, measured, blocks), ""


@contextlib.contextmanager
def _second_root(wide: int) -> Iterator[tuple[str | None, bool, str]]:
    """A scratch temp root of exactly `wide` characters, whether this made
    it, and why not: `(root, made, "")` or `(None, False, why not)`.

    Two cases no arm may confuse: a machine whose own root is already `wide`,
    or one character short of it, has no room under it for a
    narrower directory and is measured under its own root, which the row says;
    a machine whose root is WIDER than `wide` can run no capture at all, so
    there is no second width to price at and the arm is a disclosed SKIP
    rather than a red row about a measurement it could not make.

    On leaving, the root is removed only where `made` says this made it: the
    temp root itself is never made here, however TMPDIR spells it, so no
    comparison of two spellings of it decides a removal.
    """
    here = temp_base()
    normalized, room = fixed_dir_room(here, wide)
    if len(normalized) > wide:
        yield None, False, (f"a capture cannot run here: "
                            f"{_width_sentence(normalized, wide)} There is no "
                            "second temp-root width to price at on this machine, so "
                            "nothing was made and nothing is claimed.")
        return
    if room < 1:
        root, made = normalized, False
    else:
        try:
            root, made = make_fixed_dir(here, wide), True
        except Refusal as refused:
            yield None, False, (f"a {wide}-character scratch root could not be "
                                f"made here: {refused} Nothing is claimed.")
            return
    try:
        yield root, made, ""
    finally:
        if made:
            shutil.rmtree(root, ignore_errors=True)


def _figures(priced: _Priced, key: str) -> str:
    """The lines and characters of one priced block with its process-group
    number written as `<PGID>`: the number is this process's id, a few digits
    that differ from run to run and say nothing of the temp root, so a figure
    that counted them would move with the machine's id and not with the
    command."""
    got = priced.measured.get(key)
    return ("never measured" if got is None
            else f"{got[1]} lines, "
                 f"{len(_same_pgid(priced.blocks.get(key, '')))} characters")


#: The digits of the process-group line, for the cross-root comparison only.
#: A pgid is this machine's, this second — two runs minutes apart can get one
#: of four digits and one of five — and what these arms compare is a CHARACTER
#: count, so one command could measure a character apart under two roots for a
#: reason that is not the root.
_GROUP_DIGITS = re.compile(r"(?m)^(process group )\d+( .*?)-\d+$")


def _same_pgid(text: str) -> str:
    """One priced block with its process-group line's number replaced."""
    return _GROUP_DIGITS.sub(r"\1<PGID>\2-<PGID>", text)


def _with_group(priced: _Priced, number: int) -> _Priced:
    """`priced` as it would have been measured in a process whose group id
    was `number`: the number rewritten in every block's process-group line,
    and each block's character count taken again."""
    blocks = {key: _GROUP_DIGITS.sub(rf"\g<1>{number}\g<2>-{number}", text)
              for key, text in priced.blocks.items()}
    measured = {key: (got[0], got[1], len(blocks.get(key, "")))
                for key, got in priced.measured.items()}
    return _Priced(priced.root, measured, blocks)


def _two_root_verdict(key: str, first: _Priced,
                      second: _Priced) -> tuple[bool, str]:
    """Whether one command costs the same under two temp roots, and the
    sentence that says so: the figures equal with the run's process-group id
    standing in for itself, and NO absolute path rooted at the separator in
    either block."""
    left_text = _same_pgid(first.blocks.get(key, ""))
    right_text = _same_pgid(second.blocks.get(key, ""))
    a, b = first.measured.get(key), second.measured.get(key)
    figures = (a is not None and b is not None
               and a[:2] == b[:2] and len(left_text) == len(right_text))
    left, right = _rooted(left_text), _rooted(right_text)
    ok = figures and not left and not right
    return ok, (f"{first.width} characters -> {_figures(first, key)}, "
                f"rooted path(s) {left[:2] or 'none'}; {second.width} "
                f"characters -> {_figures(second, key)}, rooted path(s) "
                f"{right[:2] or 'none'}; equal with the process group id "
                f"standing in for itself={figures}")


def _unfolded(priced: _Priced, key: str) -> str:
    """One priced block as a tool with NO header fold would have printed
    it: every `<TMPROOT>` written back out as the root it was measured under.

    The counterfactual, derived from the bytes rather than simulated. It is a
    lower bound — the fold also folds the subject root — and a lower bound
    that already moves the count is all this control needs.
    """
    token = _work_placeholder()
    return _same_pgid(priced.blocks.get(key, "")).replace(
        token, priced.root.rstrip(os.sep))


def _work_placeholder() -> str:
    """The token the bundled fixture's census folds the temp root to, read off
    that census rather than typed: a census that renames it moves this with
    it."""
    for row in manifest_free_folds():
        if row.source == "work" and row.placeholder:
            return row.placeholder
    return ""


def _two_root_control(check: CheckRow, skip: SkipRow) -> None:
    """(eee) the control that the two-root pricing can go red.

    ONE command, run under both roots, plus the positive control: the same
    command read through a copy whose header fold does nothing carries the
    temp root's absolute path and costs a different number of characters under
    each root.
    """
    label = ("eee  the " + _TWO_ROOT_ARM + " command — the one whose output "
             "moved furthest with the temp root's width — costs the SAME "
             "under two temp roots of different widths, and neither block "
             "carries a path rooted at the separator; the same two blocks "
             "with the header fold undone differ in size and leak both roots, "
             "which is how this row is known to be able to go red")
    wide = _wide_root()
    if wide is None:
        skip(label, f"{_no_fixture_census()} There is no pinned width to "
                    "price at and no fixture to run the command against. "
                    "Nothing is claimed.")
        return
    keys = {_TWO_ROOT_ARM}
    with _second_root(wide) as (second, made, why):
        if second is None:
            skip(label, why)
            return
        own = not made
        # `prepare_fixture`'s answer is the ONE owner of "can a fixture be
        # built here": a `shutil.which("git")` of this arm's own would be a
        # second, and the next arm to forget it is the fault this stage is
        # about.
        here, here_why = _price_under(temp_base(), PRICED, keys)
        there, there_why = _price_under(second, PRICED, keys)
    if here is None or there is None:
        skip(label, here_why or there_why)
        return
    ok, detail = _two_root_verdict(_TWO_ROOT_ARM, here, there)
    # The figures are the root's alone: both blocks, as a process with a
    # one-digit group id and as one with a nine-digit group id would have
    # measured them, read alike — in the figures and in the sizes below.
    short_group, long_group = (
        [(_figures(moved, _TWO_ROOT_ARM), len(_unfolded(moved, _TWO_ROOT_ARM)))
         for moved in (_with_group(one, number) for one in (here, there))]
        for number in (7, 123456789))
    flat = [_unfolded(one, _TWO_ROOT_ARM) for one in (here, there)]
    flat_sizes = [len(one) for one in flat]
    flat_rooted = [len(_rooted(one)) for one in flat]
    # The counterfactual has to be a real one: a machine whose own root is
    # the second width has one width, not two, and writing the token back
    # gives the same text twice. There the control is the LEAK — the same
    # blocks unfolded carry the temp root's absolute path — and the row says
    # which half it could exercise.
    went_red = (flat_sizes[0] != flat_sizes[1] if not own
                else all(flat_rooted))
    check(label, ok and went_red and bool(_work_placeholder())
          and short_group == long_group,
          f"{ACTUAL}{detail}"
          + (" (this machine's own root, so the two widths are the same and "
             "only the bytes are compared)" if own else "")
          + f"; the same blocks with {_work_placeholder()} written back out "
          f"as the root each was measured under are {flat_sizes[0]} and "
          f"{flat_sizes[1]} characters and carry {flat_rooted[0]} and "
          f"{flat_rooted[1]} rooted path(s), which is what this row would "
          "measure without the fold; both blocks' figures and sizes with "
          "a one-digit and with a nine-digit process group id are "
          f"{'equal' if short_group == long_group else 'NOT equal'}")


def _two_root_skip_control(check: CheckRow, skip: SkipRow) -> None:
    """(vv) arm `eee` under a temp root WIDER than a capture can run under
    files a disclosed SKIP, not a FAIL about a measurement it could not make.

    The two cases must stay apart: "the root is exactly as wide as a capture
    allows" and "the root is wider" treated as one case runs a capture under a
    root where no capture can run and goes red — so `--selfcheck` is red, and
    every command REFUSES, `compare --against` included, which needs no temp
    directory and runs at any width.
    """
    wide = _wide_root()
    label = ("vv  arm eee under a temp root WIDER than a capture can run "
             "under is a disclosed SKIP carrying the width sentence `capture` "
             "refuses with, never a FAIL about a measurement it could not "
             "make: a machine whose root is too wide for any capture must "
             "still be able to run `compare --against`, which makes no temp "
             "directory")
    if wide is None:
        skip(label, f"{_no_fixture_census()} The pinned TMPDIR width is "
                    "read off it, so the width this arm plants one character "
                    "past is not known here. Nothing is claimed.")
        return
    # The assertion is CONDITIONAL, not dropped. Arm `eee` has a precondition
    # of its own — `git`, to put the fixture in a repository — and without it
    # `eee` skips for THAT reason under any temp root, wide or not. Asserted
    # unconditionally, this arm demands a width sentence that is not going to
    # be there and goes red: an absent optional tool must produce a disclosed
    # SKIP and never a red row, and a red row in a machine's one `--selfcheck`
    # is what that machine is told about golden-census.
    missing = [what for what, absent in (
        ("`git` is not on PATH.", shutil.which("git") is None),) if absent]
    if missing:
        skip(label, f"arm eee cannot reach the branch this arm is about: "
                    f"{' '.join(missing)} So eee files its own precondition "
                    "SKIP under EVERY temp root and the width sentence is "
                    "not what it would carry; the width branch is "
                    "unexercised here and nothing is claimed about it — on a "
                    "machine with both, this row asserts it.")
        return
    # What this arm plants in TMPDIR: a root of exactly one character more
    # than the widest a capture can run under, the narrowest width at which
    # no capture can run. No directory is made, and none is needed — the
    # branch under test returns BEFORE the arm touches the filesystem, which
    # is the property being asserted. A real directory of that width cannot
    # be made on every machine anyway: `census.FIXED_DIR_WIDTH` is two wider
    # than macOS's own 49-character root, so the shortest path under that root
    # is already the pinned width.
    planted = "/" + "w" * wide
    with _tmpdir_as(planted):
        try:
            rows, skips = _rows_of(_two_root_control)
        except Exception as exc:          # arm eee raising is this row's red
            if isinstance(exc, UNREPORTABLE):
                raise
            rows, skips = [(f"raised {type(exc).__name__}", False, str(exc),
                            "")], []
    kinds = ["check"] * len(rows) + ["skip"] * len(skips)
    why = skips[0][1] if skips and not rows else ""
    check(label,
          kinds == ["skip"] and planted in why
          and f"{wide + 1} characters" in why
          and "compare --against" in why,
          f"{ACTUAL}planted TMPDIR={planted!r} ({len(planted)} characters, "
          "made: no — the arm returns before it makes anything); rows "
          f"{kinds}, text {_one_line(why, 190)!r}"
          + (f", first row {rows[0][0] + ': ' + _one_line(rows[0][2], 190)!r}"
             if rows else ""))


@contextlib.contextmanager
def _cwd_and_tmpdir_as(cwd: str, root: str) -> Iterator[None]:
    """The process's working directory is `cwd` and `TMPDIR` is `root` inside
    the block, and each is what it was outside it, put back in a `finally`:
    `_tmpdir_as`'s window with the working directory added, for the arms
    that spell a temp root relative to it."""
    was = os.getcwd()
    os.chdir(cwd)
    try:
        with _tmpdir_as(root):
            yield
    finally:
        os.chdir(was)


def _second_root_owned_control(check: CheckRow) -> None:
    """(eeeeeee) `_second_root` removes only a directory it made, however
    TMPDIR spells the temp root.

    Where the temp root is as wide as `_second_root` is asked for, or one
    character short of it, there is no room under it and the root itself is
    handed back. Two boxes one character apart are planted under this arm's
    own scratch, each holding a file, and each is named in TMPDIR three
    ways: its absolute path, its name relative to the working directory, and
    its absolute path with `/.` appended — the two spellings `os.path.abspath`
    rewrites. The width asked for is the widest root a capture runs under,
    so the boxes are 48 and 49 characters where the scratch leaves room, and
    the narrowest pair the scratch allows where it does not: the branch
    `_second_root` takes is decided by the root's width against the width
    asked for, never by the pin itself. The control asks, under the narrower
    box, for a root two characters wider than it: `_second_root` makes that
    directory and hands it back as made, and it is there inside the block
    and gone after it, so this row can see a removal.
    """
    label = ("eeeeeee  `_second_root` asked for a root as wide as the temp "
             "root, or one character wider, hands back the temp root itself, "
             "says it did not make it and removes "
             "nothing: two boxes one character apart under this arm's own "
             "scratch, each holding a file, are named in TMPDIR as their "
             "absolute path, relative to the working directory and with `/.` "
             "appended, and every box and its file are there afterwards; a "
             "root it did make is handed back as made and is gone afterwards, "
             "which is how this row is known to be able to see a removal; the "
             "working directory and TMPDIR are put back after each")
    was = (os.getcwd(), os.environ.get("TMPDIR"))
    entries: list[str] = []
    held = True
    with _box("golden-census-own-") as box:
        scratch = os.path.realpath(box)
        wide = max(_wide_root() or 0, len(scratch) + 3)

        def shown(path: str | None) -> str:
            return repr(path).replace(scratch, "<box>")

        for width in (wide - 1, wide):
            name = "b" * (width - len(scratch) - 1)
            path = os.path.join(scratch, name)
            kept = os.path.join(path, "kept")
            for spelling, root in (("absolute", path),
                                   ("relative", name),
                                   ("with /. appended", path + "/.")):
                os.makedirs(path, exist_ok=True)
                pathlib.Path(kept).write_text("kept\n", encoding="utf-8")
                with _cwd_and_tmpdir_as(scratch, root):
                    with _second_root(wide) as (got, made, _why):
                        pass
                there = os.path.isfile(kept)
                back = (os.getcwd(), os.environ.get("TMPDIR")) == was
                good = got == path and not made and there and back
                held = held and good
                entries.append(
                    f"{width}-character box, {spelling} -> "
                    + ("as the label says" if good else
                       f"handed back {shown(got)}, made={made}, the file "
                       f"there afterwards={there}, the working directory and "
                       f"TMPDIR put back={back}"))
        narrow = os.path.join(scratch, "b" * (wide - len(scratch) - 2))
        os.makedirs(narrow, exist_ok=True)
        with _cwd_and_tmpdir_as(scratch, os.path.basename(narrow)):
            with _second_root(wide + 1) as (got, made, _why):
                inside = got is not None and os.path.isdir(got)
        gone = got is not None and not os.path.lexists(got)
        back = (os.getcwd(), os.environ.get("TMPDIR")) == was
        good = made and inside and gone and back
        held = held and good
        entries.append(
            f"a root it made under the {wide - 1}-character box -> "
            + ("as the label says" if good else
               f"handed back {shown(got)}, made={made}, there inside the "
               f"block={inside}, gone afterwards={gone}, the working "
               f"directory and TMPDIR put back={back}"))
    check(label, held, ACTUAL + "; ".join(entries),
          next="In `checks_width._second_root`, hand back the temp root with "
               "`made` False whatever TMPDIR's spelling, and remove on leaving "
               "only the directory `make_fixed_dir` made.")


#: Set in the child arm `rrr` starts, before that child runs the
#: `--selftest` it planted a wide temp root for. In a healthy build the
#: nested run refuses before its own CONTROLS group and no arm ever sees this
#: set; in a REGRESSED one it is what stops the nesting at one level instead
#: of planting a wider root and starting another child. It is the arm's own
#: flag, never a mode: nothing but the arm reads it, and only its child sets
#: it.
_IN_WIDE_ROOT_ARM = False

#: The child of arm `rrr`: the command line's `--selftest`, run through
#: `console.main` as the console script runs it, with `_IN_WIDE_ROOT_ARM` set
#: first. A child and not a call: the runner of `--selftest` is handed to
#: `cli.main` by `console.main`, and `console` imported by this module would
#: be the import cycle arm `bbbbbbbb` refuses.
_WIDE_SELFTEST = (
    "import sys\n"
    f"from {IMPORT_NAME} import checks_width, console\n"
    "checks_width._IN_WIDE_ROOT_ARM = True\n"
    "sys.exit(console.main(['--selftest']))\n")


def _wide_root_dir(box: str, wide: int) -> str:
    """A REAL directory under `box` whose path is too wide for a capture to
    run under: one character past `wide` where there is room for it, and the
    shortest path `box` allows where there is not.

    Made, unlike arm `vv`'s planted name, and for the opposite reason. `vv`'s
    subject returns before it touches the filesystem, so a name is the whole
    fact; this arm's subject is an entry that went on to MAKE things under
    the root, and a root it could not have made them under would prove
    nothing. Under a temp root already at or past the limit — macOS's own is
    49 characters — no path under `box` can be as short as `wide + 1`, and a
    longer one is just as far past the limit; the arm's detail line says
    which case this machine gave.
    """
    leaf = "w" * max(1, wide + 1 - len(box) - 1)
    path = os.path.join(box, leaf)
    os.mkdir(path, 0o700)
    return path


def _selftest_wide_root_control(check: CheckRow, skip: SkipRow) -> None:
    """(rrr) `--selftest` under a temp root wider than a capture accepts is
    ONE refusal at exit 2, not a page of red rows about golden-census.

    The CAPTURE group's row catches a `Refusal` and reports it as a row, which is right
    for a subject that will not run and wrong for the environment: unasked, a
    root one character too wide becomes two red CAPTURE rows, a COMPARE against
    a capture directory nothing made, and `FileNotFoundError` printed above the
    sentence naming the fix.
    """
    label = ("rrr  `--selftest` under a temp root WIDER than a capture can "
             "run under is ONE refusal, naming the root and the width the "
             "census pins, at exit 2 — with no `[FAIL]` row and no exception "
             "class anywhere on the page: the root's width is a statement "
             "about the machine, and a tool that reports it as failed "
             "rows says the program is broken when the environment is")
    wide = _wide_root()
    if wide is None:
        skip(label, f"{_no_fixture_census()} The pinned TMPDIR width is "
                    "read off it, so the width this arm plants one character "
                    "past is not known here. Nothing is claimed.")
        return
    if _IN_WIDE_ROOT_ARM:
        skip(label, "this is the CONTROLS group of the `--selftest` this arm "
                    "itself planted a wide root for, which is reached only "
                    "when the refusal under test did NOT happen. One level "
                    "is the measurement and the outer row reports it; "
                    "nothing is claimed here.")
        return
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(PACKAGE)
    with _box("golden-census-wide-") as scratch:
        planted = _wide_root_dir(scratch, wide)
        env["TMPDIR"] = planted
        ran = launch(_package_argv("-P", "-c", _WIDE_SELFTEST),
                     "the wide-root arm's `--selftest`", env=env, cwd=scratch,
                     stdin=subprocess.DEVNULL)
    heard = _heard(ran.stderr)
    code, text = ran.returncode, ran.stdout + heard.own
    lines = text.splitlines()
    refusals = [line for line in lines if line.startswith("REFUSED: ")]
    failed = [line for line in lines if line.startswith("  [FAIL]")]
    # The two tokens a traceback or a bare exception class puts on the page.
    # `Error:` catches the `FileNotFoundError: …` line this arm exists for
    # without catching the word `error` in any sentence golden-census writes.
    tokens = [token for token in ("Traceback", "Error:") if token in text]
    check(label,
          code == 2 and len(refusals) == 1 and not failed and not tokens
          and planted in refusals[0] and "next: " in text
          and not heard.not_from(PACKAGE),
          f"{ACTUAL}planted TMPDIR={planted!r} ({len(planted)} characters, "
          f"the census pins {wide + 2}), exit {code}, {len(lines)} line(s), "
          f"{len(failed)} [FAIL] row(s), {len(refusals)} REFUSED line(s) "
          f"{[_one_line(line, 100) for line in refusals[:2]]}, exception "
          f"token(s) {tokens or 'none'}{heard.not_from(PACKAGE)}",
          next="Run `TMPDIR=<a directory of more than "
               f"{wide} characters> python3 -m golden_census --selftest`: "
               "the "
               "width belongs to the machine, so `--selftest` has to ask it "
               "once before its first group rather than let every group "
               "meet it.")


#: Tripwire: the sentence after a `..` refusal's head, as a reader reads it,
#: typed here so a reworded `core._DOTDOT` turns uuuuuu and zzzzzzz red.
_DOTDOT_SAID = ("after a symbolic link, `..` names the parent of the link's "
                "target, not the directory the path spells before it, so the "
                "path can name a directory other than the one it spells.")


def _unusable_root_control(check: CheckRow, skip: SkipRow) -> None:
    """(uuuuuu) a temp root no directory can be made in, a relative one,
    and one spelled with `..`, is ONE refusal, raised before anything runs
    — never a traceback, never a `[FAIL]  !` row — for every command that
    makes a directory under the root, and for no other.

    Three roots are planted in a box under the real one — a path with nothing
    there, a regular file, a directory of mode 0555 — and `census --manifest
    M` runs in process under each, through the real `main` and the census's
    own controls. Each refusal carries the reason the operating system gives
    for its plant — no such file, not a directory, permission denied — so a
    sentence that states one reason for all three is red. Under the first,
    `capture`, `compare`, `mutants`, `probe`, `--selftest --manifest M` and
    `--selfcheck --manifest` naming a path with nothing there run too, each
    held to the same one refusal: the check precedes the manifest load and
    every argument refusal, so no file they name has to exist, and a command
    the check stopped covering meets a DIFFERENT refusal, never a nested
    self-check. `init` and `compare --against`, which make nothing under the
    temp root, must not meet it. `init` is held to what this install makes
    of it, read from `shipped_templates`, the owner the template arms ask:
    carrying a template, it exits 0 with no refusal; carrying none, it exits
    2 with its OWN refusal — the one `shipped_templates` raised — and names
    no TMPDIR. So `init` gated by the check is red in both states.

    Then `census` runs with TMPDIR unset while `tempfile.tempdir` is pinned
    to the path with nothing there, and with it empty while it is pinned to
    the regular file, so `tempfile.gettempdir()` returns each: the refusal
    names that root, the operating system's reason for it and which of the
    two TMPDIR is. `tempfile.tempdir` is put back in a `finally` and the row
    asks that it was: a pin left behind turns no other row red. The branch
    where `gettempdir` itself finds no directory is not reached here: it
    needs every candidate `gettempdir` tries, `/tmp` among them, to refuse a
    file.

    Then `census` runs with the box as the working directory and TMPDIR
    `relative-root`, `./relative-root` and `relative-root/../relative-root`:
    a directory there that holds one file and that this user can write in,
    so only its being relative can refuse it; the third holds a `..` as
    well, and the relative refusal, checked first, is the one it meets.
    Each is the one refusal naming the value as given, and its
    `next:` line asks for an absolute path; `relative-root` holds its one
    file afterwards, and the working directory and TMPDIR are put back after
    each, inside `_cwd_and_tmpdir_as`. Then the same `census` under the box
    itself — a root this run can write in — spelled as its absolute path,
    with `/./`, with a doubled slash and with a closing slash, is not
    refused and leaves nothing there: the box lists afterwards exactly what
    it listed before. Each of those three spellings is absolute and names
    the box whatever the working directory and whatever links it crosses.
    Last, `capture` with an `--out` in the box, under the box spelled with
    `/../` and as `<box>/link/..`, where `link` names `<box>/real/sub`: the
    second is `<box>/real` to the operating system and `<box>` to
    `os.path.normpath`, the shape in which a directory is made in one and
    written to in the other. Each is the one refusal naming the value as
    given, with a `next:` line that asks for the path spelled without `..`,
    and neither the box nor `<box>/real` holds anything new afterwards, the
    `--out` directory included.
    """
    label = ("uuuuuu  a TMPDIR no directory can be made in — a path with "
             "nothing there, a regular file, a directory this user may not "
             "write in — is ONE refusal at exit 2 naming TMPDIR, its value "
             "and the reason the operating system gave, with a `next:` line, "
             "raised before any control runs: never a Python traceback, never "
             "a `[FAIL]  !` row, and nothing is made at that path; under the "
             "first, `capture`, `compare`, `mutants`, `probe`, `--selftest "
             "--manifest M` and `--selfcheck --manifest M` meet the same "
             "refusal, while `init` and `compare --against`, which make "
             "nothing under the temp root, do not — `init` exits 0 with no "
             "refusal where this install carries a template, and where it "
             "carries none exits 2 with its own refusal that there is no "
             "template; with TMPDIR unset while Python's "
             "`tempfile.gettempdir()` answers the first path, and with it "
             "empty while it answers the second, `census` is that refusal "
             "naming the root Python returned, the reason and which of the "
             "two TMPDIR is, and Python's `tempfile.tempdir` is put back "
             "afterwards; a TMPDIR relative to the working directory — "
             "`relative-root` and `./relative-root`, a directory there this "
             "user can write in — is ONE refusal at exit 2 naming the value "
             "as given and saying golden-census does not take a relative "
             "temp root, with a `next:` line that asks for an absolute path, "
             "raised before any control runs, nothing is made in it, and the "
             "working directory and TMPDIR are put back after each; "
             "`relative-root/../relative-root`, relative and spelled with "
             "`..`, is that same relative refusal and never the one about "
             "`..`, and the working directory and TMPDIR are put back after "
             "it; `census` under a root it can write in, spelled as its "
             "absolute path, with `/./`, with a doubled slash and with a "
             "closing slash, is not refused and leaves nothing there; and "
             "`capture` under that root spelled with `/../`, and as "
             "`<box>/link/..` "
             "where `link` names `<box>/real/sub` (the operating system "
             "reads `<box>/real`), is ONE refusal at exit 2 naming the value "
             "as given and saying golden-census does not take a temp root "
             "spelled with `..`, with a `next:` line that asks for the "
             "absolute path spelled without `..`, raised before any control "
             "runs: never a Python traceback, and nothing is made in the box "
             "or in `<box>/real`, its `--out` directory included")

    def run(argv: list[str]) -> tuple[int, str]:
        """One command in process, or the exception it raised as its text."""
        try:
            return _quietly(main, argv)
        except Exception as exc:          # a traceback IS the defect this row
            if isinstance(exc, UNREPORTABLE):   # is about, so it is reported
                raise
            return -1, f"raised {type(exc).__name__}: {exc}"

    def refused_once(result: tuple[int, str], needle: str) -> bool:
        """The shape the row asserts of a run under an unusable root, whose
        one refusal carries `needle`: the root and the reason. Its `next:`
        line points TMPDIR at a directory and offers no short-root advice,
        which can name the root that just failed."""
        code, text = result
        lines = text.splitlines()
        refusals = [line for line in lines if line.startswith("REFUSED: ")]
        rows = [line for line in lines if line.startswith("  [")]
        return (code == 2 and len(refusals) == 1
                and needle in refusals[0]
                and "\n  next: Point TMPDIR at " in text
                and "you can write in, then run the command again." in text
                and Platform.detect().short_root_advice not in text
                and not rows
                and "Traceback" not in text and "Error:" not in text)

    def said(result: tuple[int, str]) -> str:
        """`exit N, '<line>'`: the first line that is a refusal, a failing
        row or a raise; else the last line printed; else `(nothing)`."""
        code, text = result
        lines = [line for line in text.splitlines() if line.strip()]
        first = next((line for line in lines
                      if line.startswith(("REFUSED: ", "  [FAIL]", "raised "))),
                     lines[-1] if lines else "(nothing)")
        return f"exit {code}, {_one_line(first, 110)!r}"

    with _box("golden-census-noroot-") as box:
        manifest = _scratch(os.path.join(box, "subject"))
        nowhere = os.path.join(box, "nowhere")
        missing = os.path.join(box, "no-root")
        a_file = os.path.join(box, "a-file")
        pathlib.Path(a_file).write_text("", encoding="utf-8")
        read_only = os.path.join(box, "read-only")
        os.mkdir(read_only)
        os.chmod(read_only, 0o555)
        planted = {"nothing there": missing, "a regular file": a_file,
                   "a directory of mode 0555": read_only}
        unplanted = ""
        if os.access(read_only, os.W_OK):
            # A user the mode bits do not bind — root — can write in it, so
            # the plant is not one; the other two still are.
            del planted["a directory of mode 0555"]
            unplanted = ("; the mode-0555 directory is writable by this user "
                         "(os.access), so it is no plant and nothing is "
                         "claimed of it")
        seen: list[tuple[str, tuple[int, str], bool]] = []
        # Whether this install carries a template, asked of the owner the
        # template arms ask: `init` is held to a different answer in each.
        no_template: Refusal | None = None
        try:
            shipped_templates()
        except Refusal as refused:
            no_template = refused
        # What the operating system answers when a directory is made under
        # each plant: the reason the refusal must carry, not one it guesses.
        reason = {missing: os.strerror(errno.ENOENT),
                  a_file: os.strerror(errno.ENOTDIR),
                  read_only: os.strerror(errno.EACCES)}
        for kind, root in planted.items():
            with _tmpdir_as(root):
                result = run(["census", "--manifest", manifest])
            seen.append((f"census under {kind}", result, refused_once(
                result, f"(TMPDIR is {root!r}): {reason[root]}. ")))
        gated = {
            "capture": ["capture", "--manifest", manifest,
                        "--out", os.path.join(box, "out")],
            "compare": ["compare", "--manifest", manifest,
                        "--golden", nowhere],
            "mutants": ["mutants", "--manifest", manifest,
                        "--mutants", nowhere],
            "probe": ["probe", "--", sys.executable, "-c",
                      "import sys; open(sys.argv[1], 'w').write('x')",
                      "<WRITES>"],
            "--selftest --manifest M": ["--selftest", "--manifest", manifest],
            "--selfcheck --manifest M": ["--selfcheck", "--manifest",
                                         nowhere],
        }
        with _tmpdir_as(missing):
            for name, argv in gated.items():
                result = run(argv)
                seen.append((f"{name} there", result, refused_once(
                    result, f"(TMPDIR is {missing!r}): {reason[missing]}. ")))
            result = run(["init", os.path.join(box, "project")])
            if no_template is None:
                ok = result[0] == 0 and "REFUSED: " not in result[1]
            else:
                ok = (result[0] == 2 and "TMPDIR is" not in result[1]
                      and refusal_text(no_template) in result[1])
            seen.append(("init there", result, ok))
            result = run(["compare", "--manifest", manifest,
                          "--golden", nowhere, "--against", nowhere])
            seen.append(("compare --against there", result,
                         result[0] == 2 and "TMPDIR is" not in result[1]))
        # TMPDIR unset while `tempfile.gettempdir()` answers the path with
        # nothing there, then empty while it answers the regular file: the
        # root the refusal names is the one Python returned, the reason is
        # the operating system's for that root, and the sentence says which
        # of the two TMPDIR is.
        answered = tempfile.tempdir
        try:
            for state, value, root in (("unset", None, missing),
                                       ("empty", "", a_file)):
                tempfile.tempdir = root
                with _env_as({"TMPDIR": value}):
                    result = run(["census", "--manifest", manifest])
                seen.append((f"census with TMPDIR {state}", result,
                             refused_once(result, f"root {root!r}: "
                                          f"{reason[root]}. TMPDIR is "
                                          f"{state}, so ")))
        finally:
            tempfile.tempdir = answered
        put_back = tempfile.tempdir is answered
        # A relative TMPDIR that names a directory this user can write in,
        # from the box as the working directory: only its being relative
        # can refuse it, and its one file is all it holds afterwards.
        relative = os.path.join(box, "relative-root")
        os.mkdir(relative)
        pathlib.Path(relative, "kept").write_text("kept\n", encoding="utf-8")
        outside = (os.getcwd(), os.environ.get("TMPDIR"))
        for spelling in ("relative-root", "./relative-root",
                         "relative-root/../relative-root"):
            with _cwd_and_tmpdir_as(box, spelling):
                result = run(["census", "--manifest", manifest])
            back = (os.getcwd(), os.environ.get("TMPDIR")) == outside
            seen.append((f"census with TMPDIR {spelling!r} from the box"
                         + ("" if back else ", the working directory and "
                            "TMPDIR put back=False"),
                         result, back and refused_once(
                             result, "golden-census does not take a relative "
                             f"temp root (TMPDIR is {spelling!r}): a relative "
                             "path names a different directory")
                         and "\n  next: Point TMPDIR at the absolute path "
                         "of a directory you can write in, then run the "
                         "command again." in result[1]))
        kept = os.listdir(relative) == ["kept"]
        parent, name = os.path.split(box)
        real = os.path.join(box, "real")
        os.makedirs(os.path.join(real, "sub"))
        os.symlink(os.path.join(real, "sub"), os.path.join(box, "link"))
        before = set(os.listdir(box))
        for spelling, root in (
                ("", box), (" with /./", f"{parent}/./{name}"),
                (" with a doubled slash", f"{parent}//{name}"),
                (" with a closing slash", f"{box}/")):
            with _tmpdir_as(root):
                result = run(["census", "--manifest", manifest])
            left = sorted(set(os.listdir(box)) - before)
            seen.append((f"census under a root it can write in{spelling}",
                         result, result[0] in (0, 1)
                         and "TMPDIR is" not in result[1] and not left))
        # `<box>/link/..` is `<box>/real` to the operating system and
        # `<box>` to `os.path.normpath`: a directory made there by a run the
        # value reached lands in `real`, beside `sub`.
        for spelling, root, out in (
                (" with /../", f"{box}/../{name}", "out-dotdot"),
                (" through a link with /.. after it", f"{box}/link/..",
                 "out-link")):
            here = set(os.listdir(box)) | set(os.listdir(real))
            with _tmpdir_as(root):
                result = run(["capture", "--manifest", manifest,
                              "--out", os.path.join(box, out)])
            made = sorted((set(os.listdir(box)) | set(os.listdir(real)))
                          - here)
            seen.append((f"capture under the box spelled{spelling}"
                         + (f", made {made}" if made else ""),
                         result, not made and refused_once(
                             result, "golden-census does not take a temp "
                             f"root spelled with `..` (TMPDIR is {root!r}): {_DOTDOT_SAID}")
                         and "\n  next: Point TMPDIR at the absolute path, "
                         "spelled without `..`, of a directory you can write "
                         "in, then run the command again." in result[1]))
        untouched = (not os.path.lexists(missing)
                     and os.path.isfile(a_file) and os.path.getsize(a_file) == 0
                     and os.listdir(read_only) == [])
        os.chmod(read_only, 0o755)
    check(label,
          all(ok for _, _, ok in seen) and untouched and put_back and kept,
          ACTUAL + "; ".join(f"{what} -> {said(result)}, as wanted={ok}"
                                 for what, result, ok in seen)
          + f"; left under the root it can write in: {left or 'nothing'}"
          + f"; the planted paths as they were={untouched}{unplanted}"
          + f"; tempfile.tempdir put back={put_back}"
          + f"; the relative root holds its one file alone={kept}",
          next="`cli.main` calls `core.require_temp_root` first, inside "
               "`anchored`, for every command `cli.needs_temp_root` names; "
               "`require_temp_root` refuses a TMPDIR `os.path.isabs` calls "
               "relative, and one holding a `..` component, before it tries "
               "anything, and removes the directory it made: a command "
               "reaching `mkdtemp` or `make_fixed_dir` under an unusable "
               "root without it crashes or files a `[FAIL]  !` row about the "
               "machine, one under a relative root resolves it against "
               "whichever working directory it is in, one under `..` after a "
               "link makes its directories where the operating system "
               "resolves the link and writes where Python spells the path, "
               "and a command that makes nothing there must not be gated.")


# ---------------------------------------- a cache spelled with `..` (zzzzzzz)

#: Which variable each platform reads the cache directory from when both
#: are set to an absolute path: the arm's own statement, held against the
#: refusal's sentence.
_CACHE_VARIABLE = {"darwin": "HOME", "linux": "XDG_CACHE_HOME"}


def _cache_dotdot_control(check: CheckRow, skip: SkipRow) -> None:
    """(zzzzzzz) a cache directory spelled with `..` is ONE refusal, made
    before anything is made.

    In this process, in a box: a directory `real/a/b` and a link `lnk` to
    it. With HOME and XDG_CACHE_HOME each spelled `<box>/lnk/../<name>` —
    which the operating system takes to `<box>/real/a/<name>` and Python's
    `os.path.abspath` to `<box>/<name>` — and again each spelled
    `<box>/lnk/..`, which ends in the component, `core.require_cache_dir`
    raises a `Refusal` naming the variable this platform reads the cache
    from and its value as given, with a `next:` line, and makes nothing at
    either place the path can name. Spelled `<box>/lnk/<name>`, through the
    same link without `..`, the same call raises nothing.

    SKIPPED, nothing claimed, on a platform the arm names no variable for.
    """
    label = ("zzzzzzz  a cache directory spelled with `..` is ONE refusal "
             "with a `next:` line, before anything is made: "
             "`require_cache_dir` under a HOME and an XDG_CACHE_HOME spelled "
             "through a symbolic link and then `..`, with a name after it "
             "and with none, names the variable this platform reads the "
             "cache from and its value as given, and makes nothing where the "
             "operating system resolves the path nor where Python spells it; "
             "the same spelled through the link without `..` is taken")
    platform = Platform.detect()
    variable = _CACHE_VARIABLE.get(platform.name)
    if variable is None:
        skip(label, f"the arm names no cache variable for the platform "
                    f"{platform.name!r}. Nothing is claimed.")
        return
    with _box("golden-census-dotdot-") as box:
        os.makedirs(os.path.join(box, "real", "a", "b"))
        os.symlink(os.path.join("real", "a", "b"), os.path.join(box, "lnk"))
        spellings = {
            "a name after it": {
                "HOME": os.path.join(box, "lnk", "..", "home"),
                "XDG_CACHE_HOME": os.path.join(box, "lnk", "..", "xdg")},
            "none after it": {
                "HOME": os.path.join(box, "lnk", ".."),
                "XDG_CACHE_HOME": os.path.join(box, "lnk", "..")}}
        printed: dict[str, str] = {}
        for name, spelled in spellings.items():
            with _env_as(spelled):
                try:
                    require_cache_dir()
                except Refusal as refused:
                    printed[name] = refusal_text(refused)
                else:
                    printed[name] = ""
        made = sorted(name for name in os.listdir(box)
                      if name not in ("real", "lnk"))
        made += sorted(os.path.join("real", "a", name)
                       for name in os.listdir(os.path.join(box, "real", "a"))
                       if name != "b")
        plain = {"HOME": os.path.join(box, "lnk", "home"),
                 "XDG_CACHE_HOME": os.path.join(box, "lnk", "xdg")}
        with _env_as(plain):
            try:
                require_cache_dir()
            except Refusal as refused:
                taken = refusal_text(refused)
            else:
                taken = ""

    def refused_as(name: str) -> bool:
        """Spelling `name` was ONE refusal naming the variable, its value as
        given, and the `next:` line."""
        lines = printed[name].splitlines()
        return (printed[name].startswith(
                    f"REFUSED: golden-census does not take a cache directory "
                    f"spelled with `..` ({variable} is "
                    f"{spellings[name][variable]!r}): {_DOTDOT_SAID}")
                and len(lines) == 2
                and lines[1] == f"  next: Run the same command with "
                                f"{variable} spelled without `..`.")

    check(label,
          all(refused_as(name) for name in spellings)
          and not made and not taken,
          f"{ACTUAL}"
          + "; ".join(f"spelled with `..` and {name} -> "
                      f"{_one_line(said, 400).replace(box, '<box>') or 'no refusal'}"
                      for name, said in printed.items())
          + f"; made {made}; spelled without `..` -> "
          f"{_one_line(taken, 200).replace(box, '<box>') or 'taken'}")
