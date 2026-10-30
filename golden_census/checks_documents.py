"""The arms over the package's LAYOUT and its documents: which layout an
install is in, what a checkout missing a document owes the reader, what a
bundled fixture that cannot be copied, or that an install keeps read-only,
is to the self-test, and what `pyproject.toml` promises about what ships.
"""

from __future__ import annotations

import json
import io
import os
import pathlib
import shutil
import stat
import tomllib
import types

from .controls import CheckRow, SkipRow
from .core import (
    ACTUAL,
    data_in,
    fixed_dir_room,
    IMPORT_NAME,
    Layout,
    Refusal,
    SHIPPED,
    SKILL_DIR,
    temp_base,
)
from .docs import (
    PRICED,
    command_surface,
    live_parity,
    measure,
    packaging_problems,
)
from .proof import (
    _box,
)
from .templates import (
    NEUTRAL,
    load_template,
    template_dir,
)
from .checks_base import (
    _READ_ONLY_DIRECTORY,
    _READ_ONLY_FILE,
    _fresh_module,
    _modes_planted,
    _rows_of,
    _writable_copy,
    prepare_fixture,
)
from .checks_width import (
    _fixture_width,
)


#: The priced invocations that read a capture already on disk, and those that
#: read none — each the CHEAPEST of its half, by argv length. Read off
#: `docs.PRICED` by the token they spell rather than typed here, so a list
#: that renames its rows moves this arm with it; and cheapest, because the
#: shortest argv that reads no capture is `--version`, while the longest
#: would be `--selfcheck` — this file, measured from inside itself.
def _cheapest(spelling: bool) -> str | None:
    rows = [one for one in PRICED
            if ("<AGAINST>" in one.argv) is spelling]
    return min(rows, key=lambda one: len(one.argv)).key if rows else None


_AGAINST_KEY = _cheapest(True)
_NO_AGAINST_KEY = _cheapest(False)


def _reference_capture_control(check: CheckRow, skip: SkipRow) -> None:
    """(yyyy) the reference capture runs for the SELECTED entries."""
    label = ("yyyy  the reference capture a `<AGAINST>` measurement reads is "
             "made when a SELECTED entry spells the token and NOT when the "
             "keys exclude every entry that does: asked of the whole priced "
             "list instead, pricing one command that reads nothing ran a full "
             "capture of the fixture anyway — the most expensive thing the "
             "measurement does, done for a measurement that never reads it")
    if _AGAINST_KEY is None or _NO_AGAINST_KEY is None:
        skip(label, "the priced list has no `<AGAINST>` entry, or none "
                    "without one, so the two halves this arm compares are not "
                    "both there. Nothing is claimed.")
        return
    # The two halves are "no capture was made" and "one was", and under a temp
    # root too wide for the census's pin NO capture can be made at all — so
    # both halves read the same and the first would pass for a reason that is
    # about the machine. Disclosed as a SKIP, never as a pass and never as a
    # red row about a measurement this root cannot make.
    width = _fixture_width()
    root, room = fixed_dir_room(temp_base(), width) if width else ("", 1)
    if room < 1:
        skip(label, f"no capture can run under the temp root {root!r}, which "
                    f"is {len(root)} characters: the fixture's census pins the "
                    f"subject's TMPDIR to {width}, so the half that asserts a "
                    "reference capture WAS made cannot be exercised here and "
                    "the other half would pass for a reason about this "
                    "machine. Nothing was made and nothing is claimed.")
        return
    made: dict[str, bool] = {}
    for why, keys in (("keys that exclude it", {_NO_AGAINST_KEY}),
                      ("keys that include it", {_AGAINST_KEY})):
        with _box("golden-census-reference-") as box:
            prepared = prepare_fixture(box)
            if prepared.path is None:
                # A missing requirement of ONE self-test, disclosed as this
                # row's own SKIP. It is not a statement about the run: the
                # self-tests after this one carry their own preconditions and
                # go on to report them.
                skip(label, prepared.why)
                return
            measure(PRICED, prepared.path, box, None, keys)
            made[why] = os.path.isdir(os.path.join(box, "reference-capture"))
    check(label, made["keys that exclude it"] is False
          and made["keys that include it"] is True,
          f"{ACTUAL}pricing {_NO_AGAINST_KEY} alone and "
          f"{_AGAINST_KEY} alone -> " + "; ".join(
              f"{why} -> the reference capture was "
              + ("made" if was else "not made") for why, was in made.items()))


def _inside_absent_ends(scratch: str, neither: str
                        ) -> dict[str, tuple[bool, str]]:
    """`Layout.inside_absent` over the two absences arm ooo plants, each as
    (whether the sentence names the planted package path, what it says after
    that path). `neither` is a planted package directory that holds none; `a
    file` is a plain file planted under `scratch` as the package path, which
    is no directory."""
    plain = os.path.join(scratch, "file", IMPORT_NAME)
    os.makedirs(os.path.dirname(plain))
    pathlib.Path(plain).write_text("# planted\n", encoding="utf-8")
    ends: dict[str, tuple[bool, str]] = {}
    for shape, package in (("neither", neither), ("a file", plain)):
        _head, named, tail = Layout.for_package(package).inside_absent(
            "the bundled fixture").partition(package)
        ends[shape] = (named == package, tail)
    return ends


def _shipped_layout_control(check: CheckRow) -> None:
    """(ooo) the data is found in BOTH layouts — beside the package in a
    checkout, under it in a wheel — and absent from both it is still a path a
    sentence can name.

    The sentence for what is not INSIDE the package says what
    `Layout.for_package` measured, so the arm plants both kinds of that
    absence: the package carrying neither, a directory that holds none, and
    a package path that is no directory, a plain file. Each must name its
    path and say its own clause and not the other's."""
    label = ("ooo  the shipped data is found in both layouts an install can "
             "have: `templates/` BESIDE the package, which is a checkout, and "
             "`" + IMPORT_NAME + "/" + SHIPPED + "/templates/`, which is "
             "what a wheel's "
             "force-include rows write — each planted here as a directory "
             "tree and asked of `core.data_in`; a package carrying neither "
             "answers with the CHECKOUT's path, so the refusal can name the "
             "directory it looked in. The control is the base's lookup, "
             "beside-only: it answers the wheel layout with a directory that "
             "is not there. `core.Layout.for_package`, the one decider of "
             "which layout a run is in, answers each plant the same "
             "directory, says `shipped` for the wheel alone, answers None "
             "for the package carrying neither and names that package's "
             "checkout directory in its one absence sentence; its one "
             "sentence for what is not INSIDE the package names the package "
             "carrying neither and says it `holds none`, and names a package "
             "path planted as a plain file and says it `is not a directory`, "
             "never `holds none`")
    with _box("golden-census-layout-") as scratch:
        made: dict[str, str] = {}
        for shape, parts in (("checkout", ("templates", "_neutral")),
                             ("wheel", (IMPORT_NAME, SHIPPED, "templates",
                                        "_neutral")),
                             ("neither", (IMPORT_NAME,))):
            root = os.path.join(scratch, shape)
            os.makedirs(os.path.join(root, *parts))
            os.makedirs(os.path.join(root, IMPORT_NAME), exist_ok=True)
            pathlib.Path(os.path.join(root, *parts, "template.toml")).write_text(
                "# planted\n", encoding="utf-8")
            made[shape] = os.path.join(root, IMPORT_NAME)
        answers = {shape: data_in(package, "templates")
                   for shape, package in made.items()}
        # The beside-only lookup, written out rather than remembered: one
        # line, beside the package, whatever is there. It is what `data_in` is
        # the difference from, and on the wheel layout it names nothing.
        base = {shape: os.path.join(os.path.dirname(package), "templates")
                for shape, package in made.items()}
        found = {shape: os.path.isdir(os.path.join(answer, "_neutral"))
                 for shape, answer in answers.items()}
        # The record over the same three plants. Asked AFTER the per-path
        # answers so that a `Layout` deciding a different directory from
        # `data_in` — the two-decider drift this record exists to close —
        # is a red row naming both.
        layouts = {shape: Layout.for_package(package)
                   for shape, package in made.items()}
        agrees = {shape: layouts[shape].templates == (
                      answers[shape] if found[shape] else None)
                  for shape in made}
        shipped = {shape: layouts[shape].shipped for shape in made}
        sentence = layouts["neither"].absent("templates/")
        inside = _inside_absent_ends(scratch, made["neither"])
        check(label,
              found == {"checkout": True, "wheel": True, "neither": False}
              and answers["checkout"] == base["checkout"]
              and answers["wheel"] != base["wheel"]
              and not os.path.exists(base["wheel"])
              and answers["neither"] == base["neither"]
              and all(agrees.values())
              and shipped == {"checkout": False, "wheel": True,
                              "neither": False}
              and layouts["wheel"].data == os.path.join(made["wheel"], SHIPPED)
              and layouts["checkout"].data == layouts["checkout"].root
              and layouts["neither"].root in sentence
              and "templates/" in sentence
              and inside == {"neither": (True, " holds none."),
                             "a file": (True, " is not a directory.")},
              ACTUAL
              + "; ".join(
                  f"{shape} -> ...{answers[shape][len(scratch):]} "
                  f"(holds _neutral: {found[shape]})" for shape in made)
              + "; the beside-only lookup answers the wheel layout with "
              f"...{base['wheel'][len(scratch):]}, which exists: "
              f"{os.path.exists(base['wheel'])}; Layout agrees "
              f"{agrees}, shipped {shipped}, the absence sentence names "
              f"...{layouts['neither'].root[len(scratch):]}: "
              f"{layouts['neither'].root in sentence}; the sentence for what "
              "is not inside the package -> " + "; ".join(
                  f"{shape}: names its path {named}, then says {tail!r}"
                  for shape, (named, tail) in inside.items()),
              next="`core.data_in` reads the wheel layout when the package "
                   "holds a `core.SHIPPED` directory and the checkout layout "
                   "otherwise, and `core.Layout.for_package` reads every field "
                   "through it; `pyproject.toml`'s force-include rows and "
                   "`core.SHIPPED` spell the same directory name and have to "
                   "agree. `core.Layout.inside_absent` says `is not a "
                   "directory` when `Layout.is_directory`, which "
                   "`for_package` asks of `os.path.isdir` once, is False, and "
                   "`holds none` only of a directory.")


def _layout_from_package_control(check: CheckRow, skip: SkipRow) -> None:
    """(eeeeeeeee) the layout is the PACKAGE's own: a `_shipped/` inside it
    makes it a wheel, whatever stands beside it.

    Four plants, each asked `core.data_in` for `templates`. A wheel-shaped
    package with a `templates/` planted BESIDE it, holding a stray
    `_neutral/manifest.toml` whose first line is a marker: the answer is the
    `_shipped` path, and `init --list` through that package, run by a copy of
    `templates` whose `Layout.detect` reads the plant, lists the shipped
    template's summary and does not stop at the stray. A checkout-shaped
    package, no `_shipped`, with its `templates/` beside it: the beside path.
    A wheel-shaped package with no templates at all: the `_shipped` path, the
    directory a reader should look in.
    """
    label = ("eeeeeeeee  in a wheel-shaped package a stray templates/ beside "
             "it is never read, the shipped one is, and in a checkout the one "
             "beside the package is: the layout is the package's own")
    try:
        real = template_dir(NEUTRAL)
        summary = load_template(real).summary
    except Refusal as refused:
        skip(label, f"{refused} There is no template to plant, so no layout "
                    "can be asked. Nothing is claimed.")
        return
    with _box("golden-census-layout-own-") as scratch:
        package = {shape: os.path.join(scratch, shape, IMPORT_NAME)
                   for shape in ("wheel", "checkout", "bare")}
        for path in package.values():
            os.makedirs(path)
        shipped = os.path.join(package["wheel"], SHIPPED, "templates")
        stray = os.path.join(scratch, "wheel", "templates", NEUTRAL)
        beside = os.path.join(scratch, "checkout", "templates")
        os.makedirs(stray)
        os.makedirs(os.path.join(package["bare"], SHIPPED))
        _writable_copy(real, os.path.join(shipped, NEUTRAL))
        _writable_copy(real, os.path.join(beside, NEUTRAL))
        pathlib.Path(stray, "manifest.toml").write_text(
            "# the stray, which is never read\n", encoding="utf-8")
        answers = {shape: data_in(path, "templates")
                   for shape, path in package.items()}
        copy = _fresh_module("templates")
        listed = io.StringIO()
        stopped = ""
        if copy is not None:
            copy.Layout = types.SimpleNamespace(
                detect=lambda: Layout.for_package(package["wheel"]))
            try:
                copy.init(None, None, True, listed)
            except Refusal as refused:
                stopped = str(refused)
    line = f"{NEUTRAL} \u2014 {summary}"
    wanted = {"wheel": shipped, "checkout": beside,
              "bare": os.path.join(package["bare"], SHIPPED, "templates")}
    check(label,
          copy is not None and answers == wanted
          and line in listed.getvalue()
          and not stopped,
          ACTUAL + "; ".join(
              f"{shape} -> ...{answers[shape][len(scratch):]} (wanted "
              f"...{wanted[shape][len(scratch):]})" for shape in package)
          + "; `init --list` through the wheel-shaped package listed the "
          f"shipped summary: {line in listed.getvalue()}"
          + (f", and stopped: {stopped[:150]!r}" if stopped else ""),
          next="`core.data_in` decides the layout from the package: where "
               "`<package>/" + SHIPPED + "` is a directory the data is read "
               "from it alone, and otherwise from beside the package alone.")


def _checkout_missing_document_control(check: CheckRow) -> None:
    """(uuu) a CHECKOUT missing a document FAILS the parity row; the same
    absence in an install is the disclosed SKIP — the layout decides, so a
    wrong `SKILL_DIR` in this repository cannot pass as "what an install
    looks like"."""
    label = ("uuu  DOCS PARITY on a planted checkout — `pyproject.toml` beside "
             "the package, no README.md and no `" + SKILL_DIR + "/` — reports "
             "TWO [FAIL] rows whose detail names the checkout and the missing "
             "set member, and no SKIP; the SAME package with the `pyproject.toml` "
             "removed, which is a layout carrying no documents, reports two SKIPs "
             "and no row — the control that the layout, not the absence, "
             "decides the verdict")
    with _box("golden-census-checkout-") as box:
        outcomes: dict[str, tuple[list[tuple[str, bool, str, str]],
                                  list[tuple[str, str]]]] = {}
        for shape in ("checkout", "install"):
            root = os.path.join(box, shape)
            package = os.path.join(root, IMPORT_NAME)
            os.makedirs(package)
            if shape == "checkout":
                pathlib.Path(os.path.join(root, "pyproject.toml")).write_text(
                    "# planted\n", encoding="utf-8")
            outcomes[shape] = _parity_rows_of(package)
    checkout_rows, checkout_skips = outcomes["checkout"]
    install_rows, install_skips = outcomes["install"]
    check(label,
          len(checkout_rows) == 2 and not checkout_skips
          and all(not ok for _l, ok, _d, _n in checkout_rows)
          and all("missing from this checkout" in detail
                  for _l, _ok, detail, _n in checkout_rows)
          and any(f"{SKILL_DIR}/SKILL.md" in detail
                  for _l, _ok, detail, _n in checkout_rows)
          and not install_rows and len(install_skips) == 2,
          f"{ACTUAL}checkout -> {len(checkout_rows)} row(s) "
          f"{[ok for _l, ok, _d, _n in checkout_rows]}, "
          f"{len(checkout_skips)} skip(s); install -> {len(install_rows)} "
          f"row(s), {len(install_skips)} skip(s); the checkout's details: "
          + " | ".join(detail[:80] for _l, _ok, detail, _n in checkout_rows),
          next="`core.Layout.checkout` is `pyproject.toml` beside the package "
               "and nothing shipped under it; `docs.live_parity` chooses FAIL "
               "over SKIP on it. Parity is a development check.")


def _parity_rows_of(package: str) -> tuple[list[tuple[str, bool, str, str]],
                                            list[tuple[str, str]]]:
    """DOCS PARITY's rows and skips over a planted package, collected."""
    return _rows_of(lambda check, skip: live_parity(
        command_surface(), check, skip, package=package))


#: The words arm sssssss's two stand-ins for `_repo_of` put in their answer,
#: which the absence's sentence must carry.
_PLANTED_GIT = "planted by arm sssssss"


def _git_wont_start(root: str, message: str) -> tuple[int, str, str]:
    """Arm sssssss's stand-in for `_repo_of`: a git that will not START,
    which `core.launch` refuses."""
    raise Refusal(f"`git` would not start ({_PLANTED_GIT}).",
                  next="Put a `git` on PATH.")


def _git_exits_1(root: str, message: str) -> tuple[int, str, str]:
    """Arm sssssss's stand-in for `_repo_of`: a git that ran and exited 1,
    as `_repo_of` hands it back (exit, first words, stderr)."""
    return 1, "git init --quiet", _PLANTED_GIT


#: Arm sssssss's two stand-ins for `_repo_of`, one at a time, over a fixture
#: that copies: the two absences `prepare_fixture` returns after the copy.
_REPO_STAND_INS = (("a git that will not start", _git_wont_start),
                   ("a git that exits 1", _git_exits_1))


def _unreadable_fixture_control(check: CheckRow, skip: SkipRow) -> None:
    """(sssssss) a machine whose `git` cannot put the bundled fixture in a
    repository is an absence `prepare_fixture` returns, never a traceback.

    The plant is a package of the arm's own and never the bundled fixture: a
    `fixture/` holding `manifest.toml` and `subject/stub.py`. The function
    is called on a second copy of `checks_base` whose `Layout` answers
    `detect` with `Layout.for_package` over the planted package, and whose
    `_repo_of` is replaced by the two stand-ins `_REPO_STAND_INS` names:
    attributes of the copy, so neither the real module nor the command line
    knows of them.

    Each sentence names the box in the past tense, `went into the scratch
    directory <box>`: every caller removes its box on the way out, so a
    sentence saying the copy IS there would be false.

    A `git` that is not on PATH is a disclosed SKIP, because
    `prepare_fixture` returns that absence before it reaches the copy.
    """
    label = ("sssssss  `prepare_fixture` over a planted package's fixture, "
             "with `_repo_of` standing in for a git that will not start and "
             "then for one that exits 1, each RETURNS the absence, a fixture "
             "of no path, and raises nothing, its sentence carrying the "
             "stand-in's words and saying the fixture copy, all that was "
             "made, `went into the scratch directory` it was made in")
    copy = _fresh_module("checks_base")
    if copy is None:
        skip(label, "this install carries no importable `checks_base` source "
                    "to build a second copy from, so no planted fixture can "
                    "be pointed at. Nothing is claimed.")
        return
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so `prepare_fixture` returns that "
                    "absence before it copies anything and the copy this arm "
                    "plants a fault in is never reached. Nothing is claimed.")
        return
    with _box("golden-census-fixture-copy-") as scratch:
        package = os.path.join(scratch, IMPORT_NAME)
        fixture = os.path.join(package, "fixture")
        os.makedirs(os.path.join(fixture, "subject"))
        for name in ("manifest.toml", os.path.join("subject", "stub.py")):
            pathlib.Path(os.path.join(fixture, name)).write_text(
                "# planted\n", encoding="utf-8")
        copy.Layout = types.SimpleNamespace(
            detect=lambda: Layout.for_package(package))
        said: dict[str, str] = {}
        wrong: list[str] = []
        for shape, stand_in in _REPO_STAND_INS:
            copy._repo_of = stand_in
            box = os.path.join(scratch, f"box-{len(said)}")
            os.mkdir(box)
            try:
                prepared = copy.prepare_fixture(box)
                said[shape] = (f"absent: {prepared.why}"
                               if prepared.path is None
                               else f"a fixture at {prepared.path}")
            except (OSError, Refusal) as error:
                prepared = None
                said[shape] = f"raised {type(error).__name__}: {error}"
            if not (prepared is not None and prepared.path is None
                    and _PLANTED_GIT in prepared.why
                    and "The fixture copy, all that was made, went into the "
                    f"scratch directory {box};" in prepared.why):
                wrong.append(shape)
    check(label, not wrong,
          ACTUAL + "; ".join(f"{shape} -> {text}"
                             for shape, text in said.items()).replace(
                                 scratch, "<box>")
          + (f"; WRONG: {wrong}" if wrong else ""),
          next="In `checks_base.prepare_fixture`, the two absences after "
               "`_repo_of` say the fixture copy went into the scratch "
               "directory of the box.")


def _modes_under(found: dict[str, int], package: str) -> str:
    """Arm ttttttt's detail: each planted path, relative to the planted
    package, and the octal mode `os.stat` gave it."""
    return ", ".join(f"{os.path.relpath(path, package)} {mode:o}"
                     for path, mode in found.items())


def _read_only_fixture_control(check: CheckRow, skip: SkipRow) -> None:
    """(ttttttt) a bundled fixture an install keeps read-only is copied into
    a fixture golden-census can write in, its subject a git repository.

    The plant is a package of the arm's own, as arm sssssss's is: a
    `fixture/` holding `manifest.toml` and `subject/stub.py`, every
    directory put at 0555 and every file at 0444 — the modes of a Nix store
    or a read-only site-packages, which `shutil.copytree` keeps. The
    function is called on a second copy of `checks_base` whose `Layout`
    answers `detect` with `Layout.for_package` over the planted package;
    `_repo_of` is the real one, so the `git init` the copy must allow runs.

    The planted modes are asked when the function returns, so a fix that
    makes the bundled fixture writable rather than its copy is red, and
    again once a `finally` has put them back: a mode left read-only is red
    here, where the box's removal would reset it and say nothing.

    Root writes in a 0555 directory: where a directory can be made inside
    the planted fixture, the plant does not bite and the arm is a disclosed
    SKIP. So is a `git` that is not on PATH, because `prepare_fixture`
    returns that absence before it copies anything.
    """
    label = ("ttttttt  `prepare_fixture` over a planted package whose "
             "fixture is read-only — every directory at 0555 and every file "
             "at 0444, an install's modes — RETURNS a fixture with a path, "
             "its subject holding the `.git` directory `git init` made; "
             "every directory and file of the copy outside `.git` carries "
             "the owner's write bit, while every planted path is still at "
             "its read-only mode when the function returns; and each "
             "planted path is back at its own mode afterwards, asked of "
             "`os.stat` once the plant is undone")
    copy = _fresh_module("checks_base")
    if copy is None:
        skip(label, "this install carries no importable `checks_base` source "
                    "to build a second copy from, so no planted fixture can "
                    "be pointed at. Nothing is claimed.")
        return
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so `prepare_fixture` returns that "
                    "absence before it copies anything and the read-only "
                    "fixture this arm plants is never copied. Nothing is "
                    "claimed.")
        return
    with _box("golden-census-fixture-read-only-") as scratch:
        package = os.path.join(scratch, IMPORT_NAME)
        fixture = os.path.join(package, "fixture")
        subject = os.path.join(fixture, "subject")
        os.makedirs(subject)
        files = [os.path.join(fixture, "manifest.toml"),
                 os.path.join(subject, "stub.py")]
        for name in files:
            pathlib.Path(name).write_text("# planted\n", encoding="utf-8")
        planted = {path: _READ_ONLY_FILE for path in files}
        planted.update({subject: _READ_ONLY_DIRECTORY,
                        fixture: _READ_ONLY_DIRECTORY})
        before = {path: stat.S_IMODE(os.stat(path).st_mode)
                  for path in planted}
        copy.Layout = types.SimpleNamespace(
            detect=lambda: Layout.for_package(package))
        box = os.path.join(scratch, "box")
        os.mkdir(box)
        probe = os.path.join(fixture, "probe")
        prepared = None
        said = ""
        on_return: dict[str, int] = {}
        with _modes_planted(planted, before, probe) as bites:
            if bites:
                try:
                    prepared = copy.prepare_fixture(box)
                    said = (f"absent: {prepared.why} | next: {prepared.next}"
                            if prepared.path is None
                            else f"a fixture at {prepared.path}")
                except (OSError, Refusal) as error:
                    said = f"raised {type(error).__name__}: {error}"
                on_return = {path: stat.S_IMODE(os.stat(path).st_mode)
                             for path in planted}
        if not said:
            skip(label, "a directory could be made inside the planted "
                        "fixture at 0555, which is what running as root "
                        "looks like, so no copy of it can be refused. The "
                        "modes were put back and nothing is claimed.")
            return
        # Asked AFTER the block that puts the modes back, so a plant left
        # read-only is a red entry here and not a silent reset by the box's
        # removal.
        after = {path: stat.S_IMODE(os.stat(path).st_mode)
                 for path in planted}
        lacking: list[str] | None = None
        repository = False
        if prepared is not None and prepared.path is not None:
            repository = os.path.isdir(
                os.path.join(prepared.path, "subject", ".git"))
            lacking = []
            for directory, names, names_of_files in os.walk(prepared.path):
                names[:] = [name for name in names if name != ".git"]
                for path in (directory, *(os.path.join(directory, name)
                                          for name in names_of_files)):
                    if not os.stat(path).st_mode & stat.S_IWUSR:
                        lacking.append(os.path.relpath(path, prepared.path))
        still = all(on_return.get(path) == mode
                    for path, mode in planted.items())
    check(label, (prepared is not None and prepared.path is not None
                  and repository and lacking == [] and still
                  and after == before),
          (ACTUAL + f"{said}; subject's .git "
           f"{'present' if repository else 'absent'}; paths of the copy "
           "without the owner's write bit "
           f"{'none walked' if lacking is None else sorted(lacking)}; "
           "planted modes "
           f"on return {_modes_under(on_return, package)}; afterwards "
           f"{_modes_under(after, package)}, before "
           f"{_modes_under(before, package)}").replace(
               os.path.realpath(scratch), "<box>").replace(scratch, "<box>"),
          next="Copy the fixture in `checks_base.prepare_fixture` with "
               "`checks_base._writable_copy`, and there, after "
               "`shutil.copytree`, give every directory and file of the COPY "
               "the owner's write "
               "bit (`os.chmod` over `os.walk` of the copy, never of the "
               "bundled fixture), so the `git init` that follows can write "
               "in it. A mode not back at its own value is this arm's "
               "fault: the plant puts it back in a `finally`.")


def _packaging_control(check: CheckRow, skip: SkipRow) -> None:
    """(sss) `pyproject.toml`'s two packaging tables, read with `tomllib` and
    held to what the documents promise: every sdist include pattern anchored,
    every wheel force-include target
    under `<core.IMPORT_NAME>/<core.SHIPPED>/`. A disclosed SKIP where the file
    is absent, which is an install."""
    label = ("sss  pyproject.toml, read with tomllib: every sdist include "
             "pattern is ANCHORED with a leading `/` — hatchling matches an "
             "unanchored name at any depth, so an unanchored package or docs "
             "name ships every directory of that name wherever it sits — "
             "and every wheel force-include target lands "
             "under `" + IMPORT_NAME + "/" + SHIPPED + "/`, the directory "
             "`core.data_in` "
             "looks in, so the TOML and the code spell one name; the same "
             "document with one pattern unanchored FAILS naming it, and with "
             "one force-include target moved to `<package>/_data/` FAILS "
             "naming "
             "that, which is how this row is known to be able to go red")
    layout = Layout.detect()
    if layout.pyproject is None:
        skip(label, layout.absent("pyproject.toml")
                    + " The packaging tables are the repository's; nothing "
                    "was read and nothing is claimed.")
        return
    with open(layout.pyproject, "rb") as handle:
        document = tomllib.load(handle)
    live = packaging_problems(document)
    # Two plants over a copy of the live document, so the controls read the
    # same shape the live row does.
    unanchored = json.loads(json.dumps(document))
    unanchored["tool"]["hatch"]["build"]["targets"]["sdist"]["include"][0] = \
        IMPORT_NAME
    loose = packaging_problems(unanchored)
    moved = json.loads(json.dumps(document))
    moved["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"][
        "templates"] = f"{IMPORT_NAME}/_data/templates"
    misplaced = packaging_problems(moved)
    check(label,
          live == [] and len(loose) == 1 and f"{IMPORT_NAME!r}" in loose[0]
          and "not anchored" in loose[0]
          and len(misplaced) == 1 and "_data" in misplaced[0]
          and f"{IMPORT_NAME}/{SHIPPED}/" in misplaced[0],
          f"{ACTUAL}live {live or 'no problem'}; one pattern unanchored -> "
          f"{loose}; one target under _data -> {misplaced}",
          next="Anchor every `[tool.hatch.build.targets.sdist] include` "
               "pattern with a leading `/`, and point every force-include "
               f"row at {IMPORT_NAME}/{SHIPPED}/…, the name `core.SHIPPED` "
               "holds.")
