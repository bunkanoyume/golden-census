"""The arms over `capture` and `compare`: the `--out` guard, the allow file,
the unreadable-file refusal, the capture marker, the temp-directory cleanup,
the comparator's own scratch directory, and the invocation two surfaces
share.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import functools
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import signal
import stat
import sys
from collections.abc import Callable, Iterable, Iterator

from .checks_base import (
    _census_rows,
    _control_roots,
    _fresh_module,
    _printed_refusal,
)
from .capture import (
    ENVIRONMENTAL_SKIP,
    FAILING_INPUT,
    Recorder,
    SILENT_SURFACE,
    SOURCE_HITS,
    UNCOUNTED,
    STAGE_PREFIX,
    _contraband_next,
    capture,
    contraband_patterns,
    guard_out_dir,
    read_capture,
    scan_contraband,
    scan_text,
    shared_invocations,
    tail_newline_marker,
)
from .census import (
    FIXED_DIR_WIDTH,
    UNDECODED_NEXT,
    git_env,
    preconditions,
)
from .cli import build_parser, main
from .compare import (
    allowed_for,
    compare,
    diff_captures,
    identical,
    read_allow,
)
from .core import (
    widest_root,
    ACTUAL,
    DIFFERENCE,
    GIT_IDENTITY,
    GIT_NO_MAINTENANCE,
    GIT_UNTRACKED,
    Difference,
    FINAL_NEWLINE,
    first_difference,
    fixed_dir_refusal,
    fixed_dir_room,
    git_command,
    launch,
    path_forms,
    Platform,
    QUOTE,
    Refusal,
    refusal_text,
    remove_tree,
    Report,
    Roots,
    SKIP_EXTENSION,
    SURFACES_FILE,
    temp_base,
    under,
    UNREPORTABLE,
    with_next,
    workspace,
)
from .controls import (
    CheckRow,
    SkipRow,
    manifest_controls,
)
from .manifest import Manifest, load_manifest
from .mutants import Mutant, clone_subject, plant as plant_mutant
from .probe import Handed, _first_difference as _probe_first_difference
from .checks_process import _probe_precondition
from .checks_mutants import (
    _mutant_box,
    _mutants_run,
)
from .proof import (
    _FaultOnFirstWrite,
    _STUB_CENSUS,
    _STUB_ENVIRONMENT,
    _STUB_MANIFEST,
    _STUB_WORK_CENSUS,
    _STUB_ROOT_FOLD,
    _STUB_WORK_FOLD,
    _box,
    _cache_in,
    _chmod_bites,
    _env_as,
    _fixed_pin,
    _made_under,
    _mode_as,
    _NO_VERDICT,
    _CutOnLastLine,
    _one_line,
    _opens,
    _startup_noise,
    _startup_noise_reason,
    _plant_marker,
    _planted_script,
    _quietly,
    _repo_of,
    _scratch,
    _subject,
    _tmpdir_as,
)
from . import run as run_module
from .run import (
    _in_cache,
    _residue,
    clone_input,
    place,
    repository_folder,
    resolved_address,
)

def _out_guard_control(check: CheckRow) -> None:
    """(j) `--out` is never removed wholesale. Six arms, because the guard
    has to say yes as well as no."""
    verdicts: list[str] = []
    said: dict[str, str] = {}
    with _box("golden-census-out-") as scratch:
        manifest = load_manifest(_scratch(scratch))
        fresh = os.path.join(scratch, "fresh")
        stranger = os.path.join(scratch, "stranger")
        os.makedirs(stranger)
        pathlib.Path(os.path.join(stranger, "notes.txt")).write_text(
            "somebody's work\n", encoding="utf-8")
        # A prior capture of THIS manifest's input: `--force` replaces what
        # the manifest records, and a directory named for no input of it is
        # a stranger.
        prior = os.path.join(scratch, "prior")
        _plant_marker(prior)
        # A plain FILE at --out reaches `os.makedirs`, which raises an
        # uncaught FileExistsError unless the guard catches it first; --force
        # must not buy past it either, so the arm carries force=True.
        a_file = os.path.join(scratch, "a-file")
        pathlib.Path(a_file).write_text("x\n", encoding="utf-8")
        # A directory that exists and cannot be LISTED. The guard's answer
        # comes from the listing, so there is nothing to fall back to and an
        # unguarded `os.listdir` was a PermissionError traceback at exit 1.
        unlistable = os.path.join(scratch, "unlistable")
        os.makedirs(unlistable)
        listing_plant = "chmod 000"
        if _chmod_bites(unlistable, os.listdir):
            os.chmod(unlistable, 0o000)
        else:
            # Running as root, `chmod 000` leaves the directory listable, and
            # the container this branch is headed for runs as root. Disclosed
            # in the row's own detail; the other five cases still stand.
            listing_plant = "chmod 000 stayed listable here"
        # A LINK to a directory. `os.path.isdir` follows it, so before the
        # guard's own test it read as a directory and `shutil.rmtree` raised
        # `Cannot call rmtree on a symbolic link` at exit 1. `--force` must
        # not buy past it either, so this case carries force=True.
        link_target = os.path.join(scratch, "link-target")
        os.makedirs(link_target)
        a_link = os.path.join(scratch, "a-link")
        os.symlink(link_target, a_link)
        cases = [("new", fresh, False),
                 ("stranger", stranger, True),
                 ("prior", prior, False),
                 ("prior+force", prior, True),
                 ("file+force", a_file, True),
                 ("symlink+force", a_link, True)]
        if listing_plant == "chmod 000":
            cases.append(("unlistable", unlistable, False))
        for label, path, force in cases:
            try:
                verdicts.append(
                    f"{label}={guard_out_dir(path, force, (), manifest).note}")
            except Refusal as refusal:
                # The box as well as the path: the link case's refusal names
                # the link's TARGET, which is a second directory of this
                # machine, and a row read on another machine names neither.
                whole = str(refusal).replace(path, "<dir>").replace(
                    scratch, "<box>")
                said[label] = whole
                verdicts.append(
                    f"{label}=REFUSED({_one_line(whole, 90)})")
        os.chmod(unlistable, 0o700)
    # The stranger's refusal NAMES what it found. A sentence that said only
    # "not empty" left the reader to go looking for a file golden-census had
    # already listed, and the file it names is exactly what to delete.
    names_it = "notes.txt" in said.get("stranger", "")
    # The unlistable directory is a REFUSAL naming the reason, never a
    # traceback. `not built` is the disclosed shape where root made the plant
    # impossible.
    listed = (listing_plant != "chmod 000"
              or ("cannot be listed" in said.get("unlistable", "")
                  and "is not an empty one" in said.get("unlistable", "")))
    # The link's refusal names the link AND what it points at: a reader told
    # only that their --out is a link still has to go and look at what it
    # resolves to, which is the fact that made the answer surprising.
    both_named = ("is a symbolic link to" in said.get("symlink+force", "")
                  and "link-target" in said.get("symlink+force", ""))
    # The row: `capture` refuses to remove an --out directory it did not
    # write and NAMES every entry it found there, refuses to overwrite a prior
    # capture without --force, and refuses an --out that is a FILE, an --out
    # that is a symbolic LINK — naming the link and its target — and an --out
    # it cannot LIST rather than crashing on any of them; a new directory and
    # an explicit --force are allowed. The `actual:` line carries each verdict.
    check("j  `capture` refuses an --out it did not write, a prior capture "
          "without --force, a file, a symbolic link and a directory it "
          "cannot list; a new directory and --force are allowed",
          len(verdicts) == len(cases) and verdicts[0] == "new=new directory"
          and verdicts[1].startswith("stranger=REFUSED") and names_it
          and verdicts[2].startswith("prior=REFUSED")
          and verdicts[3].startswith("prior+force=replacing")
          and verdicts[4].startswith("file+force=REFUSED")
          and verdicts[5].startswith("symlink+force=REFUSED") and both_named
          and listed,
          f"{ACTUAL}{verdicts}; the stranger's refusal names the planted "
          f"notes.txt: {names_it}; the unlistable directory is a refusal "
          f"naming the reason: {listed}; the link refusal names the link "
          f"and its target: {both_named}"
          + ("" if listing_plant == "chmod 000"
             else f" (not exercised: {listing_plant})"))


#: Arm `ffffff`'s subject: `mode` beside it says what each run does — `good`
#: writes text for every input, `bad` writes bytes no decoder reads for input
#: `y`, `leak` prints an absolute home path, `drop` also leaves a file inside
#: `old/` (the arm's `--out`), `list` prints its own root's listing, and
#: `again` prints other words than `good`.
_STAGED_SUBJECT = """\
import os, sys

if sys.argv[1] == "--version":
    print("staged 1")
    raise SystemExit(0)
root = os.path.dirname(os.path.abspath(__file__))
mode = open(os.path.join(root, "mode")).read().strip()
name, written = sys.argv[1], sys.argv[2]
data = b"\\xff\\xfe" if mode == "bad" and name == "y" else b"fine\\n"
open(written, "wb").write(data)
if mode == "drop":
    open(os.path.join(root, "old", "dropped.txt"), "w").write("the subject's\\n")
if mode == "list":
    print(sorted(os.listdir(root)))
else:
    print("/home/someone/x" if mode == "leak" else ("again " if mode == "again" else "ok ") + name)
"""

#: Two inputs over one surface that writes a file; `{kind}` is what the
#: `--input` case replaces to record the surface as a declared skip first.
_STAGED_MANIFEST = _subject("staged") + """\
version = ["--version"]

[inputs.x]
args     = ["x"]
surfaces = ["s"]

[inputs.y]
args     = ["y"]
surfaces = ["s"]

[surfaces.s]
{kind}
"""

_STAGED_RUN = 'args   = ["<WRITES>"]\nwrites = "<WORK>/<input>-<surface>.txt"'
_STAGED_SKIP = 'kind = "skip"\nskip = "not recorded yet"'
_STAGED_TALLIES = ('kind    = "tallies"\nargs    = ["<WRITES>"]\n'
                   'writes  = "<WORK>/<input>-<surface>.txt"\nverdict = "^ok "')

#: No control row: this arm calls `capture.capture` directly, and what it
#: measures is where the capture lands, not the census.
_STAGED_CENSUS = _STUB_ENVIRONMENT + _STUB_ROOT_FOLD + _STUB_WORK_FOLD


def _tree_bytes(directory: str) -> dict[str, bytes] | None:
    """Every file under `directory` as `{relative path: bytes}`, or None for
    a directory that is not there."""
    if not os.path.isdir(directory):
        return None
    found: dict[str, bytes] = {}
    for at, dirs, files in os.walk(directory):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(at, name)
            with open(path, "rb") as handle:
                found[os.path.relpath(path, directory)] = handle.read()
    return found


def _staged_capture_control(check: CheckRow) -> None:
    """(ffffff) `capture` records its rows under the temp root and moves them
    into place beside `--out` only when every step has passed.

    Each case is a wrong shape this arm holds `capture` away from: a refused
    `--force` leaving `--out` EMPTY; a contraband refusal, which RETURNS 2
    rather than raising, leaving a marked capture `compare` accepts; `--force
    --input X` leaving X's stale files beside its new ones; `--force` removing
    a reader's file without a word — including one the subject's own run
    dropped into `--out`, or `s.out~` beside a recorded name; a `surfaces.json`
    that does not parse making every recorded file a "stranger"; a subject that
    lists its own root recording the staging directory's random name; an
    unwritable parent ending in a traceback after the preconditions and the
    version have run; `--force` deleting an input directory and the files of
    surfaces the manifest no longer has, and a tallies row's `writes` file;
    `compare` reading a capture whose last input it could not read as IDENTICAL
    over the rest.
    Every case runs under the private temp root `proof._made_under` lists, so a
    leaked temp-root recording directory is seen as well as a stage left
    beside an `--out`.

    What the row asserts, case by case: a `--force` refused mid-run leaves
    the old golden byte for byte, a contraband refusal leaves a fresh `--out`
    absent and an old golden byte for byte, `--force --input X` replaces X's
    directory whole and leaves every other input's bytes; `--force` REFUSES,
    naming it and removing nothing, what THIS manifest does not record — a
    file at the top or inside an input, a `.skip` beside a surface the
    manifest runs (one that was a skip included) and `.out` beside one it
    skips, `s.out~` beside a written file and beside a surface that writes
    nothing, a link named like a recorded file, the files of a surface
    removed from the manifest or whose `writes` extension changed, the
    directory of an input it no longer has, a tallies row's `writes` file, an
    input whose `surfaces.json` is a link, and one the subject's own run
    dropped into `--out`; it refuses a `surfaces.json` it cannot parse, and a
    symbolic link anywhere in a capture at `--out` whatever `--force` and
    `--input` say, while a directory holding no marker is refused as no
    capture whatever links it holds; `compare` refuses two captures whose
    last input cannot be read, or captures that hold a symbolic link — an
    input directory or a file — never IDENTICAL, and cut on its capture's
    last line leaves the closed pipe to its caller; a subject listing its own
    root records no staging directory, so `--force --twice` then `compare` is
    IDENTICAL; an unwritable parent is refused before the subject's version
    runs; and no `STAGE_PREFIX*` is left beside any `--out`, nor anything
    under the temp root. The `actual:` line names each case that did not
    hold.
    """
    label = ("ffffff  `capture` records its rows under the temp root and "
             "moves them into place beside --out only when every step has "
             "passed")
    said: dict[str, str] = {}
    held: dict[str, bool] = {}
    untested: list[str] = []
    left: list[str] = []

    def body() -> None:
        """Every case, under the private temp root `_made_under` lists."""
        with _box("golden-census-staged-") as box:
            path = _scratch(box, manifest_text=_STAGED_MANIFEST.replace(
                                "{kind}", _STAGED_RUN),
                            census_text=_STAGED_CENSUS,
                            extra={"stub.py": _STAGED_SUBJECT, "mode": "good\n"})

            def manifest_as(name: str, kind: str, *swaps: tuple[str, str]) -> str:
                """The staged manifest with `{kind}` filled and each swap made,
                written as `<box>/<name>.toml`."""
                text = _STAGED_MANIFEST.replace("{kind}", kind)
                for old_text, new_text in swaps:
                    text = text.replace(old_text, new_text)
                where = os.path.join(box, f"{name}.toml")
                pathlib.Path(where).write_text(text, encoding="utf-8")
                return where

            skip_path = manifest_as("skip", _STAGED_SKIP)

            def run(where: str, mode: str, *, manifest: str = path,
                    inputs: tuple[str, ...] = (), force: bool = False,
                    twice: bool = False) -> str:
                """One capture: `exit N`, the refusal, or what it raised — with
                the log kept."""
                pathlib.Path(os.path.join(os.path.dirname(manifest), "mode")).write_text(
                    mode + "\n", encoding="utf-8")
                log = io.StringIO()
                try:
                    code = capture(load_manifest(manifest), where, log, inputs,
                                   force, twice)
                    verdict = f"exit {code}"
                except Refusal as refused:
                    verdict = "REFUSED: " + str(refused).replace(box, "<box>")
                except OSError as raised:
                    verdict = f"RAISED {type(raised).__name__}: {raised}".replace(box, "<box>")
                said[f"{os.path.basename(where)} log"] = log.getvalue()
                return verdict

            def refused_naming(key: str, *names: str) -> bool:
                return (said[key].startswith("REFUSED: ")
                        and all(name in said[key] for name in names))

            def compared(golden: str, against: str | None, *,
                         manifest: str = path) -> str:
                """One `compare`: `exit N` and its verdict line, or the refusal."""
                verdict = io.StringIO()
                try:
                    code = compare(load_manifest(manifest), golden, against, None, verdict)
                except Refusal as refused:
                    return "REFUSED: " + str(refused).replace(box, "<box>")
                return f"exit {code}, " + _one_line(
                    verdict.getvalue(), 80, needles=("IDENTICAL", "DIFF"))

            def planted_case(where: str, recorded_by: str, forced_by: str,
                             planted: str, named: str, directory: str = "") -> None:
                """A capture by one manifest, a file planted in it (or none),
                and `--force` by another: refused naming `named`, every byte
                of the golden kept."""
                golden = os.path.join(box, directory or where.replace(" ", "-"))
                run(golden, "good", manifest=recorded_by)
                if planted:
                    pathlib.Path(os.path.join(golden, planted)).write_text(
                        "a reader's\n", encoding="utf-8")
                kept = _tree_bytes(golden)
                said[where] = run(golden, "good", manifest=forced_by, force=True)
                held[where] = (refused_naming(where, "this capture does not record",
                                              f"\n    {named}")
                               and _tree_bytes(golden) == kept)

            # (a) the old golden survives a `--force` refused mid-run.
            old = os.path.join(box, "old")
            said["good"] = run(old, "good")
            before = _tree_bytes(old)
            said["bad --force"] = run(old, "bad", force=True)
            held["old golden kept"] = (said["good"] == "exit 0" and bool(before)
                                       and _tree_bytes(old) == before
                                       and said["bad --force"].startswith("REFUSED: "))
            held["version ran"] = "subject version" in said["old log"]

            # (a2) a file the subject's own run drops into --out under --force is
            # refused by the second stranger check, before anything is moved.
            said["drop --force"] = run(old, "drop", force=True)
            dropped = _tree_bytes(old) or {}
            held["dropped file refused"] = (
                refused_naming("drop --force", "this capture does not record",
                               "\n    dropped.txt")
                and dropped.pop("dropped.txt", None) is not None
                and dropped == before)
            # Gone already when the second check is missing: the swap took it.
            if os.path.lexists(os.path.join(old, "dropped.txt")):
                os.remove(os.path.join(old, "dropped.txt"))

            # (b) contraband: into a fresh --out, and over an existing golden.
            fresh = os.path.join(box, "fresh")
            said["leak fresh"] = run(fresh, "leak")
            said["leak --force"] = run(old, "leak", force=True)
            held["contraband"] = (said["leak fresh"] == "exit 2"
                                  and not os.path.lexists(fresh)
                                  and said["leak --force"] == "exit 2"
                                  and _tree_bytes(old) == before)

            # (c) `--force --input x` replaces x's directory whole — a new
            # directory holding the new words — and leaves y's bytes; a
            # surface that was a skip and is now a run leaves its `.skip`,
            # which this manifest's capture does not record: named, kept.
            partial = os.path.join(box, "partial")
            said["partial"] = run(partial, "good")
            other = _tree_bytes(os.path.join(partial, "y"))
            x_was = os.stat(os.path.join(partial, "x")).st_ino
            said["--input x"] = run(partial, "again", inputs=("x",), force=True)
            x_now = _tree_bytes(os.path.join(partial, "x")) or {}
            held["input replaced"] = (said["partial"] == "exit 0"
                                      and said["--input x"] == "exit 0"
                                      and x_now.get("s.out") == b"again x\n"
                                      and os.stat(os.path.join(partial, "x")).st_ino != x_was
                                      and bool(other)
                                      and _tree_bytes(os.path.join(partial, "y")) == other)
            from_skip = os.path.join(box, "from-skip")
            run(from_skip, "good", manifest=skip_path)
            kept = _tree_bytes(from_skip)
            said["skip to run"] = run(from_skip, "good", inputs=("x",), force=True)
            held["skip to run"] = (
                refused_naming("skip to run", "this capture does not record",
                               "\n    " + os.path.join("x", "s.skip"))
                and _tree_bytes(from_skip) == kept)

            # (d) files this capture does not record, decided by the manifest
            # alone: a file at the top or inside an input, `s.out~`, a `.skip`
            # beside a surface it runs and `.out` beside one it skips, the file
            # of a written surface since removed from the manifest or whose
            # `writes` extension changed, and `s.out~` beside a surface that
            # writes nothing; a link named like a recorded file is named too.
            x = functools.partial(os.path.join, "x")
            elsewhere = 'args = ["<WORK>/elsewhere.txt"]'
            removed = manifest_as("writes-removed", elsewhere)
            changed = manifest_as("writes-extension-changed",
                                  'args   = ["<WRITES>"]\nwrites = "<WORK>/<input>-<surface>.dat"')
            nowrite = manifest_as("nowrite", elsewhere)
            for where, recorded_by, forced_by, planted, named, *directory in (
                    ("stranger top", path, path, "README.md", "README.md"),
                    ("stranger inside", path, path, x("notes.txt"), x("notes.txt")),
                    ("stranger backup", path, path, x("s.out~"), x("s.out~")),
                    ("skip beside captured", path, path, x("s.skip"), x("s.skip")),
                    ("out beside skipped", skip_path, skip_path, x("s.out"), x("s.out")),
                    ("writes removed", path, removed, "", x("s.txt")),
                    ("writes extension changed", path, changed, "", x("s.txt")),
                    ("backup beside a surface writing nothing", nowrite, nowrite,
                     x("s.out~"), x("s.out~"), "backup-beside-nothing-written")):
                planted_case(where, recorded_by, forced_by, planted, named, *directory)
            golden = os.path.join(box, "linked")
            run(golden, "good")
            os.remove(os.path.join(golden, "x", "s.out"))
            os.symlink("s.err", os.path.join(golden, "x", "s.out"))
            said["a link named s.out"] = run(golden, "good", force=True)
            held["a link named s.out"] = (
                refused_naming("a link named s.out", "--out names a capture holding",
                               os.path.join("linked", "x", "s.out") + ", which is a "
                               "symbolic link")
                and os.path.islink(os.path.join(golden, "x", "s.out")))
            # (d3) the manifest alone decides: an input it no longer has is
            # named whole, a surface it no longer has by its files, and a
            # tallies row's `writes` file — which no tallies row records —
            # by name.
            no_y = manifest_as("no-y", _STAGED_RUN,
                               ('[inputs.y]\nargs     = ["y"]\nsurfaces = ["s"]\n\n', ""))
            renamed = manifest_as("renamed", _STAGED_RUN, ('"s"', '"r"'),
                                  ("[surfaces.s]", "[surfaces.r]"))
            tallies = manifest_as("tallies", _STAGED_TALLIES)
            for where, recorded_by, forced_by, planted, named in (
                    ("removed input", path, no_y, "", "y"),
                    ("removed surface", path, renamed, "", x("s.out")),
                    ("tallies writes", tallies, tallies, x("s.txt"), x("s.txt"))):
                planted_case(where, recorded_by, forced_by, planted, named)
            corrupt = os.path.join(box, "corrupt")
            run(corrupt, "good")
            record = os.path.join(corrupt, "x", SURFACES_FILE)
            with open(record, "r+", encoding="utf-8") as handle:
                handle.truncate(5)
            kept = _tree_bytes(corrupt)
            said["truncated record"] = run(corrupt, "good", force=True)
            held["truncated record"] = (
                refused_naming("truncated record",
                               os.path.join("corrupt", "x", SURFACES_FILE),
                               "cannot be read as a capture's record")
                and _tree_bytes(corrupt) == kept)

            # (e) an unwritable parent, asked of `_chmod_bites` first.
            parent = os.path.join(box, "readonly")
            os.makedirs(parent)
            if _chmod_bites(parent, os.listdir):
                with _mode_as(parent, 0o555):
                    said["readonly"] = run(os.path.join(parent, "out"), "good")
                log = said.get("out log", "")
                held["unwritable parent"] = (
                    refused_naming("readonly", "cannot be recorded into")
                    and "subject version" not in log and "capture ->" not in log)
            else:
                untested.append("the unwritable parent")

            # (g) `compare` over two captures whose LAST input cannot be read
            # — only listed (0311) — refuses naming it, never IDENTICAL over
            # the inputs it could read.
            compared_a = os.path.join(box, "compared-a")
            compared_b = os.path.join(box, "compared-b")
            run(compared_a, "good")
            run(compared_b, "good")
            for where, mode in (("compare, last input at 0311", 0o311),):
                unread = [os.path.join(compared_a, "y"), os.path.join(compared_b, "y")]
                if not _chmod_bites(unread[0], os.listdir):
                    untested.append(f"the {where}")
                    continue
                for one in unread:
                    os.chmod(one, mode)
                try:
                    said[where] = compared(compared_a, compared_b)
                finally:
                    for one in unread:
                        os.chmod(one, 0o755)
                held[where] = refused_naming(where, "cannot be read",
                                             os.path.join("compared-a", "y"))

            # (g2) `compare` over two captures whose input `x` is a symbolic
            # link to a copy of it: the walk refuses the link, naming it; and
            # with every input linked, the top level's link test runs before
            # the marker test and names the link too — never "0 golden files,
            # 0 new files IDENTICAL", nor "holds no capture" while the marker
            # is there behind the link.
            for where, linked in (("compare, one input a link", ("x",)),
                                  ("compare, every input a link", ("x", "y"))):
                pair = []
                for side in ("a", "b"):
                    golden = os.path.join(box, f"{where.replace(' ', '-').replace(',', '')}-{side}")
                    run(golden, "good")
                    for name in linked:
                        moved = golden + f"-{name}-target"
                        os.rename(os.path.join(golden, name), moved)
                        os.symlink(moved, os.path.join(golden, name))
                    pair.append(golden)
                said[where] = compared(pair[0], pair[1])
            held["compare, one input a link"] = refused_naming(
                "compare, one input a link", "--golden names a capture holding",
                os.path.join("compare-one-input-a-link-a", "x") + ", which is a symbolic link")
            held["compare, every input a link"] = refused_naming(
                "compare, every input a link", "is a symbolic link",
                os.path.join("compare-every-input-a-link-a", "x"))

            # (g3) a link to a FILE inside a capture is refused by `compare`,
            # naming it — never read through to another file's bytes; and
            # `capture --force` refuses an input directory that is a link,
            # named like an input of the manifest, whatever `--input` names,
            # and names the link when every input is one.
            pair = []
            for side in ("a", "b"):
                golden = os.path.join(box, f"compare-a-linked-file-{side}")
                run(golden, "good")
                target = golden + "-s.out"
                os.rename(os.path.join(golden, "x", "s.out"), target)
                os.symlink(target, os.path.join(golden, "x", "s.out"))
                pair.append(golden)
            said["compare, a linked file"] = compared(pair[0], pair[1])
            held["compare, a linked file"] = refused_naming(
                "compare, a linked file", "is a symbolic link",
                os.path.join("compare-a-linked-file-a", "x", "s.out"))
            for where, linked, selected in (("--input y beside a linked x", ("x",), ("y",)),
                                            ("--force, every input a link", ("x", "y"), ())):
                golden = os.path.join(box, where.replace(" ", "-").replace(",", ""))
                run(golden, "good")
                for name in linked:
                    os.rename(os.path.join(golden, name), golden + f"-{name}")
                    os.symlink(golden + f"-{name}", os.path.join(golden, name))
                said[where] = run(golden, "good", inputs=selected, force=True)
                held[where] = (refused_naming(where, "--out names a capture holding",
                                              os.path.join(os.path.basename(golden), "x")
                                              + ", which is a symbolic link")
                               and all(os.path.islink(os.path.join(golden, name))
                                       for name in linked))
            # Under --force every link in the whole of --out is refused,
            # whatever --input names: a linked file inside an input it does
            # not select, and a top-level link named like no input.
            for where, planted in (("--input y, a linked file in x", os.path.join("x", "s.out")),
                                   ("--input y, a top-level link", "notes")):
                golden = os.path.join(box, where.replace(" ", "-").replace(",", ""))
                run(golden, "good")
                target = golden + "-target"
                pathlib.Path(target).write_text("elsewhere\n", encoding="utf-8")
                if os.path.lexists(os.path.join(golden, planted)):
                    os.remove(os.path.join(golden, planted))
                os.symlink(target, os.path.join(golden, planted))
                said[where] = run(golden, "good", inputs=("y",), force=True)
                held[where] = (refused_naming(where, "--out names a capture holding",
                                              os.path.join(os.path.basename(golden), planted)
                                              + ", which is a symbolic link")
                               and os.path.islink(os.path.join(golden, planted)))
            # A directory that is no capture is refused as that, whatever
            # links it holds — the marker decides first, and a link in a
            # project folder is not a link in a capture.
            project = os.path.join(box, "not-a-capture")
            os.makedirs(project)
            pathlib.Path(os.path.join(project, "notes")).write_text(
                "somebody's\n", encoding="utf-8")
            os.symlink(box, os.path.join(project, "x"))     # named like an input
            said["compare --golden, no capture holding a link"] = compared(project, None)
            held["compare --golden, no capture holding a link"] = (
                refused_naming("compare --golden, no capture holding a link",
                               "holds no capture")
                and "symbolic link" not in said["compare --golden, no capture holding a link"])
            said["--out, no capture holding a link"] = run(project, "good")
            held["--out, no capture holding a link"] = (
                refused_naming("--out, no capture holding a link",
                               "holds no <input>/surfaces.json", "\n    notes", "\n    x")
                and "symbolic link" not in said["--out, no capture holding a link"])
            # A link in a capture is refused as a link WITHOUT --force too:
            # never "pass --force" first and the link only on the next try.
            golden = os.path.join(box, "link-without-force")
            run(golden, "good")
            os.symlink(os.path.join(box, "mode"), os.path.join(golden, "notes"))
            said["a link without --force"] = run(golden, "good")
            held["a link without --force"] = (
                refused_naming("a link without --force", "--out names a capture holding",
                               os.path.join("link-without-force", "notes")
                               + ", which is a symbolic link")
                and "already holds a capture" not in said["a link without --force"])
            # (h) a link named `surfaces.json` is refused as a link, naming
            # it, and left as it was.
            # A capture of ONE input, so no other input's real marker makes it
            # a capture: its only marker is the link, which still counts —
            # "directly or through a link" — so the link is what is refused,
            # never the input named as holding no marker.
            golden = os.path.join(box, "linked-marker")
            run(golden, "good", manifest=no_y)
            outside = os.path.join(box, "linked-marker.json")
            shutil.copyfile(os.path.join(golden, "x", SURFACES_FILE), outside)
            os.remove(os.path.join(golden, "x", SURFACES_FILE))
            os.symlink(outside, os.path.join(golden, "x", SURFACES_FILE))
            said["linked marker"] = run(golden, "good", manifest=no_y, force=True)
            held["linked marker"] = (
                refused_naming("linked marker", "--out names a capture holding",
                               os.path.join("linked-marker", "x", SURFACES_FILE)
                               + ", which is a symbolic link")
                and os.path.islink(os.path.join(golden, "x", SURFACES_FILE)))

            # `compare` whose reader stops on its capture's last line: the
            # capture's own "landed" handling is the `capture` command's, so
            # the closed pipe reaches `compare`'s caller — whose refusal is
            # exit 2 — and nothing is said about --out.
            pathlib.Path(os.path.join(box, "mode")).write_text("good\n", encoding="utf-8")
            cut_err = io.StringIO()
            with contextlib.redirect_stderr(cut_err):
                try:
                    cut_said = "exit " + str(compare(load_manifest(path), old, None, None,
                                                     _CutOnLastLine()))
                except BrokenPipeError:
                    cut_said = "raised BrokenPipeError"
            said["compare cut on its capture's last line"] = (
                f"{cut_said}, stderr {_one_line(cut_err.getvalue(), DIFFERENCE, empty='empty')}")
            held["compare cut on its capture's last line"] = (
                cut_said == "raised BrokenPipeError" and not cut_err.getvalue())

            # (f) a subject that lists its own root, with --out inside that root:
            # no staging directory exists there while it runs, so the golden
            # carries no random name and a fresh `compare` agrees with it.
            lister = os.path.join(box, "lister")
            listed_path = _scratch(lister, manifest_text=_STAGED_MANIFEST.replace(
                                       "{kind}", _STAGED_RUN),
                                   census_text=_STAGED_CENSUS,
                                   extra={"stub.py": _STAGED_SUBJECT, "mode": "list\n"})
            listed_out = os.path.join(lister, "out")
            run(listed_out, "list", manifest=listed_path)
            said["list --force --twice"] = run(listed_out, "list",
                                               manifest=listed_path, force=True,
                                               twice=True)
            said["list compare"] = compared(listed_out, None, manifest=listed_path)
            recorded_listing = (_tree_bytes(listed_out) or {}).get(
                os.path.join("x", "s.out"), b"")
            held["listing"] = (said["list --force --twice"] == "exit 0"
                               and said["list compare"].startswith("exit 0")
                               and STAGE_PREFIX.encode() not in recorded_listing
                               and b"'out'" in recorded_listing)
            left[:] = [os.path.relpath(os.path.join(at, name), box)
                    for at, dirs, files in os.walk(box) for name in dirs + files
                    if name.startswith(STAGE_PREFIX)]

    _result, leaked = _made_under(temp_base(), body)
    check(label,
          all(held.values()) and held["version ran"] and not left
          and not leaked and len(held) == 34 - len(untested),
          ACTUAL + "; ".join(
              f"{why} -> {_one_line(said[why], 150)}"
              for why in ("good", "bad --force", "drop --force", "leak fresh",
                          "leak --force", "partial", "--input x", "skip to run",
                          "stranger top",
                          "stranger inside", "stranger backup",
                          "skip beside captured", "out beside skipped",
                          "writes removed", "writes extension changed",
                          "backup beside a surface writing nothing",
                          "a link named s.out", "removed input", "removed surface",
                          "tallies writes", "compare, last input at 0311",
                          "compare, one input a link",
                          "compare, every input a link", "compare, a linked file",
                          "--input y beside a linked x", "--force, every input a link",
                          "--input y, a linked file in x", "--input y, a top-level link",
                          "compare --golden, no capture holding a link",
                          "--out, no capture holding a link", "a link without --force",
                          "compare cut on its capture's last line", "linked marker",
                          "truncated record", "readonly",
                          "list --force --twice", "list compare") if why in said)
          + "; " + ", ".join(f"{why}={ok}" for why, ok in held.items())
          + f"; staging directories left {left}; left under the private temp "
          f"root {[one[:30] for one in leaked]}"
          + ("; not exercised here — a `chmod` plant where `chmod 000` leaves a "
             "directory listable: " + ", ".join(untested) if untested else ""),
          next="`capture._staged` checks --out can be landed in and owns every "
               "directory a capture makes, `capture._swap_in` is the only "
               "thing that moves the recording into place, and "
               "`capture.capture_strangers` says what this capture records; "
               "if the old golden is gone, the swap has stopped being the "
               "last thing `capture` does.")


def _allow_control(check: CheckRow) -> None:
    """(k) an allow row permits the surface it NAMES and not its siblings."""
    rows = [("acceptance", "a bare directory name"),
            ("acceptance/acceptance.out", "the exact surface"),
            ("_subject/costpin-*", "an explicit glob")]
    bare = allowed_for("acceptance/acceptance.out", rows[:1])
    named = allowed_for("acceptance/acceptance.out", rows[1:2])
    sibling = allowed_for("acceptance/report.out", rows[1:2])
    glob = allowed_for("_subject/costpin-04-graph.out", rows[2:])
    check("k  an allowed-movement row permits the surface it NAMES and not its "
          "siblings; a bare directory name permits nothing; a glob row permits "
          "what the glob says",
          bare is None and named == "the exact surface" and sibling is None
          and glob == "an explicit glob",
          f"{ACTUAL}bare={bare!r}, exact={named!r}, sibling={sibling!r}, "
          f"glob={glob!r}")


def _unreadable_control(check: CheckRow, roots: Roots) -> None:
    """(l) the scan numbers the line of a hit as `core.lines_of` does."""
    with _box("golden-census-unread-") as scratch:
        readable = os.path.join(scratch, "readable.out")
        # Two lines `lines_of` keeps whole, `x\ry` and `\v\fz`, that
        # `str.splitlines` breaks into five, then the box's own absolute
        # path, which the scan finds under the temp root: line 3, not 6.
        pathlib.Path(readable).write_text(f"x\ry\n\v\fz\n{scratch}\n",
                                          encoding="utf-8", newline="")
        scan = scan_contraband([readable], roots, frozenset())
    lines = sorted({line for _path, line, _label, _token in scan.hits})
    check("l  the contraband scan numbers a hit's line as `core.lines_of` "
          "does, so a path after a bare `\\r`, a vertical tab and a form "
          "feed is on line 3 and not 6",
          scan.read == 1 and not scan.unreadable and lines == [3],
          f"{ACTUAL}{scan.read} read of 1, hits on line(s) {lines}")


#: Arm `m`'s subject: a matrix row `row <label>` prints a shared banner line
#: on standard output, then `<label>-out` (and the word `word.txt` holds,
#: for the `ends` row), and the shared usage line and its label on standard
#: error. The final newline of each stream is there only when the label is
#: `ends`; the `silent` row prints nothing after the shared lines.
_MARKER_SUBJECT = '''\
import sys

if sys.argv[1] == "row":
    label = sys.argv[2]
    end = "\\n" if label == "ends" else ""
    word = " " + open("word.txt").read().strip() if label == "ends" else ""
    sys.stdout.write("banner\\n" + ("" if label == "silent"
                                     else label + "-out" + word + end))
    sys.stderr.write("usage: stub\\n" + label + end)
    raise SystemExit(2)
'''

_MARKER_MANIFEST = _subject("marker") + '''
[inputs._subject]
args     = []
surfaces = ["tails"]

[surfaces.tails]
kind    = "matrix"
include = "rows.json"
'''

_MARKER_ROWS = ('[{"label": "bare", "args": ["row", "bare"]}, '
                '{"label": "ends", "args": ["row", "ends"]}, '
                '{"label": "silent", "args": ["row", "silent"]}]\n')

#: The record arm `m` expects of that subject, written out by hand: the
#: banner is the one stdout line every row printed, so it is stored once under
#: the header; the `silent` row's standard output is empty and says so.
_MARKER_RECORD = (
    "pairs: 3\n"
    "usage-prefix-lines: 1\n"
    "stdout-prefix-lines: 1\n"
    "    banner\n"
    "\n"
    "bare exit=2\n"
    "  stderr tail-newline=no\n"
    "    bare\n"
    "  stdout tail-newline=no\n"
    "    bare-out\n"
    "ends exit=2\n"
    "  stderr tail-newline=yes\n"
    "    ends\n"
    "  stdout tail-newline=yes\n"
    "    ends-out one\n"
    "silent exit=2\n"
    "  stderr tail-newline=no\n"
    "    silent\n"
    "  stdout tail-newline=no\n"
    "    \n")


def _marker_control(check: CheckRow) -> None:
    """(m) a matrix row's output is recorded, both streams: the tail's
    newline marker has `no` as a value the recorder can actually produce, a
    row's standard output is in the record and compared, and the lines every
    row printed are stored once.

    The helper is asked of the two pairs `splitlines() or [""]` collapses,
    and a real capture of a matrix surface whose rows differ only in the
    final newline, or in nothing but what they print, is read back: the
    record is written out by hand and compared whole, then the word one row
    prints on standard output is changed and `compare` must say so.
    """
    marks = {tail: tail_newline_marker(tail)
             for tail in ("abc\n", "abc", "", "\n")}
    with _box("golden-census-marker-") as box:
        manifest = load_manifest(_scratch(
            box, manifest_text=_MARKER_MANIFEST, census_text=_STUB_WORK_CENSUS,
            extra={"stub.py": _MARKER_SUBJECT, "rows.json": _MARKER_ROWS,
                   "word.txt": "one\n"}))
        golden = os.path.join(box, "golden")
        code = capture(manifest, golden, io.StringIO())
        record = _recorded_bytes(golden, "tails.out", "tails.err").get(
            "tails.out", b"").decode("utf-8", "replace")
        unchanged = io.StringIO()
        same_code = compare(manifest, golden, None, None, unchanged)
        # Only what the `ends` row prints on standard output changes: its
        # exit code, its standard error and every other row are as they were.
        pathlib.Path(os.path.join(box, "word.txt")).write_text(
            "two\n", encoding="utf-8")
        moved = io.StringIO()
        moved_code = compare(manifest, golden, None, None, moved)
    moved_rows = [line.strip() for line in moved.getvalue().split("\n")
                  if "tails.out" in line]
    check("m  a matrix row's output is recorded: the tail newline of each "
          "stream is a value the recorder produces (`no` as well as `yes`), "
          "an empty standard output is recorded as empty, the lines every "
          "row printed on standard output are stored once, and a row whose "
          "standard output changes turns `compare` red",
          marks == {"abc\n": "yes", "abc": "no", "": "no", "\n": "yes"}
          and code == 0 and record == _MARKER_RECORD
          and same_code == 0 and "IDENTICAL" in unchanged.getvalue()
          and moved_code == 1 and bool(moved_rows),
          f"{ACTUAL}{marks}; a capture of three matrix rows -> exit {code}, "
          f"record {record!r}; compared as captured -> exit {same_code}; "
          "the `ends` row printing another word on standard output -> "
          f"compare exit {moved_code}, row(s) {moved_rows}")


#: What a stranger's directory beside `--out` holds, and the bytes the arm
#: reads back out of it.
_STRANGER = "somebody else's capture\n"


def _plant_beside(out_dir: str, capture_dir: bool) -> str:
    """A directory at the path `--twice` used to derive from `--out`, holding
    something of a reader's. `capture_dir` gives it the marker, which is what
    `--force` used to buy its way past."""
    beside = out_dir.rstrip("/") + ".twice"
    inner = os.path.join(beside, "demo")
    os.makedirs(inner, exist_ok=True)
    name = SURFACES_FILE if capture_dir else "notes.txt"
    pathlib.Path(os.path.join(inner, name)).write_text(_STRANGER, encoding="utf-8")
    return os.path.join(inner, name)


def _twice_scratch_control(check: CheckRow) -> None:
    """(qqqq) `--twice` captures into a directory golden-census made."""
    label = ("qqqq  `capture --twice` records its second capture into a "
             "directory it MAKES under the temp root, and removes that one: a "
             "directory of a reader's at `<out>.twice` — the path the second "
             "capture used to be derived from — survives byte for byte, with "
             "and without --force and whether or not it carries a capture "
             "marker, and the scratch directory is gone when the run ends")
    base_tmp = temp_base()
    read_back: dict[str, str] = {}
    logs: dict[str, str] = {}

    def body() -> None:
        with _box("golden-census-twicedir-") as box:
            manifest = load_manifest(_scratch(box))
            out_dir = os.path.join(box, "out")
            for why, force, marker in (("a stranger's directory", False, False),
                                       ("a capture of somebody else's under "
                                        "--force", True, True)):
                planted = _plant_beside(out_dir, marker)
                log = io.StringIO()
                code = capture(manifest, out_dir, log, (), force, True)
                # The VERDICT and the scratch directory's PREFIX, never the
                # path: this arm's detail is read on any machine, and the
                # directory it names sits under that machine's temp root.
                said = log.getvalue()
                logs[why] = (
                    f"exit {code}, "
                    + ("byte-identical" if "byte-identical" in said
                       else _one_line(said, DIFFERENCE, needles=("REFUSED",),
                                      empty="(no verdict)"))
                    + ", a second capture into "
                    + ("golden-census-twice-*" if "golden-census-twice-" in said
                       else "(no scratch directory named)"))
                try:
                    with open(planted, encoding="utf-8") as handle:
                        read_back[why] = handle.read()
                except OSError as gone:
                    read_back[why] = f"({type(gone).__name__})"

    # A private root, so the listing after the run IS what the run left there:
    # the scratch directory the second capture writes into is made under the
    # temp root like every other, and a leak of it would show up here.
    _result, left = _made_under(base_tmp, body)
    survived = all(text == _STRANGER for text in read_back.values())
    green = all(one.startswith("exit 0, byte-identical") for one in logs.values())
    # The directory has to have been MADE, or "it survived" is a claim about a
    # run that never opened a second capture at all.
    made = all("golden-census-twice-*" in one for one in logs.values())
    check(label, survived and green and made and not left,
          ACTUAL + "; ".join(f"{why} -> {logs[why]}, the planted file reads "
                                 f"{read_back[why]!r}" for why in logs)
          + f"; {len(left)} directory(ies) left under the private temp root "
          f"{[one[:26] for one in left]}")


#: A manifest with two inputs over one surface, so a `--input` capture is a
#: partial one and `--out` keeps rows the second capture does not record.
_TWO_INPUT_MANIFEST = _STUB_MANIFEST.replace(
    "[inputs._subject]", "[inputs.other]") + '''
[inputs._subject]
args     = []
surfaces = ["help"]
'''


def _twice_partial_control(check: CheckRow) -> None:
    """(rrrr) `--twice` with `--input` compares the selected rows."""
    label = ("rrrr  `capture --twice --input NAME` compares the rows of the "
             "SELECTED input on both sides — each of the two captures records "
             "the one input — and the full `--twice` still compares every "
             "row")
    verdicts: dict[str, str] = {}
    counts: dict[str, int] = {}
    with _box("golden-census-partial-") as box:
        manifest = load_manifest(_scratch(box, manifest_text=_TWO_INPUT_MANIFEST))
        out_dir = os.path.join(box, "out")
        for why, inputs, force in (("every input", (), False),
                                   ("one of two", ("_subject",), True)):
            log = io.StringIO()
            code = capture(manifest, out_dir, log, inputs, force, True)
            said = log.getvalue()
            files = [line for line in said.splitlines()
                     if "files, byte-identical" in line]
            counts[why] = (int(files[0].split()[1]) if files else -1)
            verdicts[why] = (f"exit {code}, byte-identical" if files
                             else f"exit {code}: "
                             + _one_line(said, DIFFERENCE, needles=("REFUSED",),
                                         empty="(no verdict)"))
    # The two counts are the arm's evidence that the narrowing NARROWS: four
    # files for one input's single surface, eight for both inputs'. Equal
    # counts would mean the second run compared the whole capture and passed
    # for some other reason.
    narrowed = counts.get("one of two", 0) * 2 == counts.get("every input", 0)
    green = all(one.endswith("byte-identical") for one in verdicts.values())
    check(label, green and narrowed,
          ACTUAL + "; ".join(f"{why} -> {verdicts[why]} over "
                                 f"{counts[why]} file(s)" for why in verdicts))


#: A subject whose output gains a final newline on the second run and on no
#: other byte: the smallest drift `splitlines` cannot see.
_TAIL_SUBJECT = '''\
import os, sys

mark = os.path.join(os.environ["GOLDEN_CENSUS_TAIL"], "ran")
first = not os.path.exists(mark)
open(mark, "w").write("ran")
sys.stdout.write("stub ok" if first else "stub ok\\n")
'''

#: A census whose one row RUNS nothing: the subject alternates on its run
#: count, so a `vary` or `drift` control would spend runs of its own and the
#: capture would meet whichever half the control left behind.
_TAIL_CENSUS = _STUB_ENVIRONMENT.replace('["PATH"]', '["PATH", "GOLDEN_CENSUS_TAIL"]') + '''
[[input]]
name        = "locale"
disposition = "state"
variables   = ["LANG"]
finding     = "recorded so a capture that moves under another locale can be attributed"
'''

_TAIL_MANIFEST = _subject("tail") + '''
[inputs._subject]
args     = []
surfaces = ["report"]

[surfaces.report]
args = []
'''


def _final_newline_control(check: CheckRow) -> None:
    """(ssss) a drift confined to the final newline is seen everywhere."""
    label = ("ssss  a difference confined to the FINAL NEWLINE is named by "
             "`core.first_difference` and by all three of its readers: "
             "`capture --twice` REFUSES over a subject that gains one on its "
             "second run, where `splitlines` alone reported `byte-identical` "
             "at exit 0; `compare`'s `[DIFF]` row carries a one-line detail "
             "where the unified diff is empty; and `probe`'s clause 2 says it "
             "through the same function rather than through a copy of its own. "
             "The control is a one-line change, which still names its line")
    # The two texts, and the ordinary moved line beside them: a rule that fired
    # on everything would be no better than one that fired on nothing.
    tail = first_difference("abc", "abc\n", DIFFERENCE)
    same = first_difference("abc\n", "abc\n", DIFFERENCE)
    line = first_difference("abc\n", "abd\n", DIFFERENCE)
    detail = diff_captures({"i/report.out": "abc"},
                           {"i/report.out": "abc\n"})[0].detail
    said = _probe_first_difference("abc", "abc\n")

    with _box("golden-census-tail-") as box:
        manifest = load_manifest(_scratch(box, manifest_text=_TAIL_MANIFEST,
                                          census_text=_TAIL_CENSUS,
                                          extra={"stub.py": _TAIL_SUBJECT}))
        log = io.StringIO()
        # The REFUSAL, caught here: `capture` raises it and `cli.main` is what
        # turns one into the printed sentence and exit 2. An arm that drove
        # the command line instead would run this file inside itself.
        try:
            with _env_as({"GOLDEN_CENSUS_TAIL": box}):
                code = capture(manifest, os.path.join(box, "out"), log, (),
                               False, True)
            refused = _one_line(log.getvalue(), DIFFERENCE,
                                needles=("byte-identical",),
                                empty="(no verdict)")
        except Refusal as drift:
            code, refused = 2, _one_line(refusal_text(drift), DIFFERENCE)

    check(label,
          tail == Difference(None, "", "", "second")
          and same is None and line is not None and line.line == 1
          and FINAL_NEWLINE in detail and "second has it" in detail
          and FINAL_NEWLINE in said
          and code == 2 and FINAL_NEWLINE in refused,
          f"{ACTUAL}'abc' against 'abc\\n' -> {tail}; two equal texts -> "
          f"{same}; a moved line -> {line}; the [DIFF] detail -> {detail!r}; "
          f"probe's clause 2 -> {said!r}; `capture --twice` over a subject "
          f"that gains one -> exit {code}: {refused}")


#: Arm `aaaaaa`'s subject. It writes BYTES, so what it prints is exactly what
#: it means to print: `mode.txt` beside it says `crlf`, `lf`, or `alternate`
#: (CRLF on the first run, LF on every later one). A matrix row — argv
#: `row <label>` — prints a shared usage line and a tail ending in `\r\n`
#: on standard error, and `out <label>\r\n` on standard output.
_CR_SUBJECT = '''\
import sys

mode = open("mode.txt").read().strip()
if sys.argv[1] == "row":
    sys.stdout.buffer.write(b"out " + sys.argv[2].encode() + b"\\r\\n")
    sys.stderr.buffer.write(b"usage: stub\\n" + sys.argv[2].encode() + b"\\r\\n")
    raise SystemExit(2)
if mode == "alternate":
    mode = "lf" if open("ran.txt", "a+").tell() else "crlf"
    open("ran.txt", "a").write("ran")
crlf = mode == "crlf"
sys.stdout.buffer.write(b"a\\r\\nb\\r" if crlf else b"a\\nb\\n")
sys.stderr.buffer.write(b"e\\r\\n" if crlf else b"e\\n")
with open(sys.argv[1], "wb") as handle:
    handle.write(b"x\\r\\n" if crlf else b"x\\n")
'''

_CR_MANIFEST = _subject("cr") + '''
[inputs._subject]
args     = []
surfaces = ["report", "flags"]

[surfaces.report]
args   = ["<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"

[surfaces.flags]
kind    = "matrix"
include = "rows.json"
'''

_CR_ROWS = ('[{"label": "one", "args": ["row", "one"]}, '
            '{"label": "two", "args": ["row", "two"]}]\n')


def _cr_box(box: str, name: str, mode: str) -> Manifest:
    """A scratch subject of arm `aaaaaa` in `box/name`, set to `mode`."""
    where = os.path.join(box, name)
    return load_manifest(_scratch(
        where, manifest_text=_CR_MANIFEST, census_text=_STUB_WORK_CENSUS,
        extra={"stub.py": _CR_SUBJECT, "mode.txt": mode,
               "rows.json": _CR_ROWS}))


def _recorded_bytes(golden: str, *names: str) -> dict[str, bytes]:
    """Each named file of `golden/_subject`, read back as BYTES."""
    found: dict[str, bytes] = {}
    for name in names:
        path = os.path.join(golden, "_subject", name)
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                found[name] = handle.read()
    return found


def _line_ending_control(check: CheckRow) -> None:
    """(aaaaaa) a line ending is a byte of the golden like any other.

    `launch` runs the child for bytes and decodes them itself, and the
    written file is read with `newline=""`, so a `\\r` the subject printed or
    wrote reaches the golden. The readers that split a recorded text into
    lines split it with `core.lines_of`, on `"\\n"` alone, so a change of
    line ending alone is QUOTED with its `\\r` in `compare`'s hunk and NAMED
    by its line by `--twice` — and the two reductions keep a line's `\\r`: a
    matrix tail line, and a `tallies` failing line, while a `tallies` rule,
    `verdict` and `failing` see each line with one trailing `\\r` set aside.
    The hunk is numbered by the same rule, so a bare `\\r`, a form feed or a
    `\\x85` inside a line leaves it one line, quoted with its byte, and a
    change of ending beside a change of text shows both. A line longer than `first_difference`'s
    width is quoted around the byte that differs, so its `\\r` is not cut
    away.
    """
    label = ("aaaaaa  a line ending is recorded as the bytes the subject "
             "wrote: `\\r\\n` and a lone `\\r` on stdout, on stderr and in a "
             "written file reach the golden byte for byte; the same subject "
             "printing `\\n` instead is a [DIFF] whose hunk shows line 1 "
             "as `-'a\\r'` against `+a`, and `--twice` over a subject that alternates the "
             "two REFUSES naming line 1 and its `\\r`; a matrix tail line keeps its "
             "`\\r` on standard output and on standard error; "
             "a `tallies` transcript written with `\\r\\n` records the same "
             "groups and verdict lines as the LF one, its failing lines with "
             "their `\\r`; in `compare`'s hunk a line holding a bare `\\r`, "
             "a `\\x0c` or a `\\x85` is ONE line, quoted with its byte, under a header that "
             "counts the lines `core.lines_of` counts, and a change of line "
             "ending beside a change of visible text shows both; on a "
             "150-character line `core.first_difference` quotes the tail that "
             "holds the `\\r`")
    with _box("golden-census-line-ending-") as box:
        manifest = _cr_box(box, "claim", "crlf")
        golden = os.path.join(box, "claim", "golden")
        claim_code = capture(manifest, golden, io.StringIO())
        recorded = _recorded_bytes(golden, "report.out", "report.err",
                                   "report.txt", "flags.out")
        pathlib.Path(os.path.join(box, "claim", "mode.txt")).write_text("lf", encoding="utf-8")
        compared = io.StringIO()
        compare_code = compare(manifest, golden, None, None, compared)
        printed = [line.strip() for line in compared.getvalue().split("\n")]
        twice = _cr_box(box, "twice", "alternate")
        try:
            twice_code = capture(twice, os.path.join(box, "twice", "out"),
                                 io.StringIO(), (), False, True)
            twice_said = f"exit {twice_code}"
        except Refusal as drift:
            twice_said = _one_line(refusal_text(drift), DIFFERENCE)
        _crlf_code, crlf_tallies, _crlf_log = _tallies_pair(
            box, "tallies-crlf", "x, y", "x, y", failing=True,
            transcript_text=_TALLIES_TRANSCRIPT.replace("\n", "\r\n"))
    wanted = {"report.out": b"a\r\nb\r", "report.err": b"e\r\n",
              "report.txt": b"x\r\n"}
    tail_kept = (b"one exit=2\n  stderr tail-newline=yes\n    one\r\n"
                 b"  stdout tail-newline=yes\n    out one\r\n"
                 in recorded.get("flags.out", b""))
    named = "-'a\\r'" in printed and "+a" in printed
    hunks = {case: diff_captures({"i/report.out": golden_text},
                                 {"i/report.out": new_text})[0].detail
             for case, golden_text, new_text in (
                 ("a bare \\r", "a\nb\nc: 3\r9\nd\n", "a\nb\nc: 3\nd\n"),
                 ("a \\x0c", "a\nb\nc: 3\x0c9\nd\n", "a\nb\nc: 3\nd\n"),
                 ("a \\x85", "a\nb\nc: 3\x859\nd\n", "a\nb\nc: 3\nd\n"),
                 ("an ending beside a text change", "a\nb\nc\nd\ne\n",
                  "a\r\nb\nc\nd\nE\n"))}
    wanted_hunks = {
        "a bare \\r": "--- golden/i/report.out\n+++ new/i/report.out\n"
                      "@@ -1,4 +1,4 @@\n a\n b\n-'c: 3\\r9'\n+c: 3\n d",
        "a \\x0c": "--- golden/i/report.out\n+++ new/i/report.out\n"
                   "@@ -1,4 +1,4 @@\n a\n b\n-'c: 3\\x0c9'\n+c: 3\n d",
        "a \\x85": "--- golden/i/report.out\n+++ new/i/report.out\n"
                   "@@ -1,4 +1,4 @@\n a\n b\n-'c: 3\\x859'\n+c: 3\n d",
        "an ending beside a text change":
            "--- golden/i/report.out\n+++ new/i/report.out\n"
            "@@ -1,5 +1,5 @@\n-a\n+'a\\r'\n b\n c\n d\n-e\n+E"}
    twice_named = (twice_said.startswith("REFUSED: ")
                   and "line 1" in twice_said and "\\r'" in twice_said)
    long_moved = first_difference("x" * 150 + "\r\n", "x" * 150 + "\n",
                                  DIFFERENCE)
    long_detail = (f"golden {long_moved.first!r}, new {long_moved.second!r}"
                   if long_moved is not None else "(no difference)")
    long_named = "x\\r', new '…x" in long_detail
    crlf_wanted = ("groups: 2\nALPHA: 9/10 passed\n  [FAIL]  b\r\n"
                   "           actual: x, y\r\nBETA: 3/3 passed\n")
    check(label,
          claim_code == 0
          and all(recorded.get(name) == value for name, value in wanted.items())
          and tail_kept and compare_code == 1 and named and twice_named
          and crlf_tallies == crlf_wanted and hunks == wanted_hunks
          and long_named,
          f"{ACTUAL}capture exit {claim_code}, recorded "
          + ", ".join(f"{name}={recorded.get(name)!r}" for name in wanted)
          + f", the matrix tail kept its CR={tail_kept}; the LF change -> "
          f"compare exit {compare_code}, the hunk shows -'a\\r' and +a="
          f"{named}; `--twice` over "
          f"alternating endings -> {twice_said}; the CRLF tallies record "
          f"{crlf_tallies!r}; the hunks of a bare \\r, a \\x0c, a \\x85 and an "
          "ending beside a text change -> "
          + "; ".join(f"{case}: {hunk.split(chr(10))[2:]}"
                      for case, hunk in hunks.items()
                      if hunk != wanted_hunks[case])
          + ("as wanted" if hunks == wanted_hunks else "")
          + "; the 150-character line's difference ends "
          f"{long_detail[-72:]!r}",
          next="`core.launch` decodes a child's bytes in `core._decoded` "
               "with no newline translation, `run.run_subject` reads "
               "the written file with `newline=\"\"`, and `core.lines_of` is "
               "the one line splitter of `first_difference`, "
               "`compare.diff_captures`' hunk, `record_tallies` and "
               "`record_matrix`; `core._windows` cuts a "
               "long line around the byte that differs. Read the detail for "
               "which of them went wrong.")


#: The subject of arm `ttttttttt`: it prints, byte for byte, the file
#: `body.txt` beside it.
_RAW_SUBJECT = '''\
import sys

sys.stdout.buffer.write(open("body.txt", "rb").read())
'''

_RAW_MANIFEST = _subject("raw", '["<PYTHON>", "subject.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["says"]

[surfaces.says]
args = []
'''

#: What the golden says and what the changed subject says: they differ in
#: line 3 alone, which holds an erase-line sequence and a BEL, and line 2
#: holds a tab.
_RAW_GOLDEN = "first\n\ttabbed\nplain\n"
_RAW_CHANGED = "first\n\ttabbed\nrow\x1b[2K\x07gone\n"

#: What a child prints on standard error: an OSC 52 sequence, which asks a
#: terminal to set its clipboard.
_RAW_SAID = "\x1b]52;c;QUJD\x07"

_RAW_CHILD_CENSUS = _STUB_WORK_CENSUS + '''
[[input]]
name        = "the planted command exits 0"
disposition = "precondition"
check       = "command"
command     = ["<PYTHON>", "<ROOT>/child.py"]
expect      = "exit 0"
finding     = "planted: a capture depends on what this command made"
'''


def _control_characters_control(check: CheckRow) -> None:
    """(ttttttttt) a character a terminal acts on is printed in its `!r`
    spelling, never raw.

    `compare` quoted a hunk line with `!r` only where `str.splitlines`
    would break it, so an escape sequence of a subject, or of a committed
    golden, reached a person's terminal, where cursor-up and erase-line
    sequences can hide the rows and the verdict that follow. A line of
    `compare`'s hunk and a child's standard error that a refusal quotes
    are written through `core.printable_text`. The plant is a golden and
    a capture that differ in a line holding `\\x1b[2K` and `\\x07`, beside
    a line holding a tab, and a command precondition whose child prints an
    OSC 52 sequence to standard error and exits 3.
    """
    label = ("ttttttttt  a diff line or a quoted child output holding "
             "ESC, BEL or another control character is printed in its !r "
             "spelling and never raw, while tab and an ordinary line pass "
             "unchanged")
    with _box("golden-census-raw-control-") as box:
        where = os.path.join(box, "diff")
        path = _scratch(where, manifest_text=_RAW_MANIFEST,
                        census_text=_STUB_WORK_CENSUS,
                        extra={"subject.py": _RAW_SUBJECT,
                               "body.txt": _RAW_GOLDEN})
        golden = os.path.join(where, "golden")
        capture(load_manifest(path), golden, io.StringIO())
        pathlib.Path(os.path.join(where, "body.txt")).write_text(
            _RAW_CHANGED, encoding="utf-8")
        compared = io.StringIO()
        code = compare(load_manifest(path), golden, None, None, compared)
        shown = compared.getvalue()
        refusing = os.path.join(box, "refusing")
        said_path = _scratch(
            refusing, census_text=_RAW_CHILD_CENSUS,
            extra={"child.py": _ABOUT_CHILD.format(
                printed="", said=_RAW_SAID, ends="sys.exit(3)")})
        try:
            capture(load_manifest(said_path), os.path.join(refusing, "out"),
                    io.StringIO())
            quoted = "(not refused)"
        except Refusal as refused:
            quoted = refusal_text(refused)
    spelled = repr("row\x1b[2K\x07gone")
    shown_lines = [line.strip(" ") for line in shown.split("\n")]
    diff_safe = ("\x1b" not in shown and "\x07" not in shown
                 and "+" + spelled in shown_lines
                 and "\ttabbed" in shown_lines and "first" in shown_lines)
    said_safe = ("\x1b" not in quoted and "\x07" not in quoted
                 and repr(_RAW_SAID) in quoted)
    check(label, code == 1 and diff_safe and said_safe,
          f"{ACTUAL}compare exit {code}; the diff holds no raw ESC or BEL, "
          f"holds +{spelled} and prints the tab line as it is={diff_safe}; "
          "the refusal over the child's standard error holds no raw ESC or "
          f"BEL and holds {repr(_RAW_SAID)}={said_safe}; the diff: "
          f"{_one_line(shown, 3 * DIFFERENCE)!r}; the refusal: "
          f"{_one_line(quoted, 3 * DIFFERENCE)!r}",
          next="`core.printable_text` quotes a line that holds a character "
               "`str.isprintable` rejects; `compare.diff_captures` writes "
               "its hunk lines through it and `census._stderr_text` the "
               "text of a child's standard error.")


#: Arm `cccccc`'s subject. `mode.txt` beside it names what it writes to its
#: `.json` file: `took` a duration that moves every run, `prov` the same
#: beside a commit that moves too, `root` the subject root's own path,
#: `err` a small document and the same duration on standard error, and
#: `none`, `lf`, `crlf` one small document with that final newline.
_JSON_SUBJECT = '''\
import json
import os
import sys

mode = open("mode.txt").read().strip()
took = f"{os.getpid()}us"
tails = {"none": "", "lf": "\\n", "crlf": "\\r\\n"}
if mode == "took":
    text = json.dumps({"took": took}) + "\\n"
elif mode == "prov":
    document = {"prov": {"commit": format(os.getpid(), "x")}, "took": took}
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\\n"
elif mode == "root":
    text = json.dumps({"root": os.getcwd()}) + "\\n"
elif mode == "err":
    text = json.dumps({"a": 1}) + "\\n"
else:
    text = json.dumps({"a": 1}, indent=2) + tails[mode]
with open(sys.argv[1], "w", encoding="utf-8", newline="") as handle:
    handle.write(text)
print("wrote")
if mode == "err":
    print(f"took {took}", file=sys.stderr)
'''

_JSON_MANIFEST = _subject("json") + '''
[inputs._subject]
args     = []
surfaces = ["report"]

[surfaces.report]
args   = ["<WRITES>"]
writes = "<WORK>/<input>-<surface>.json"
'''

#: The census every case starts from: the two directories the row prints.
_JSON_CENSUS = _STUB_ENVIRONMENT + _STUB_ROOT_FOLD + _STUB_WORK_FOLD

#: A `regex` fold over every row, for the duration the subject writes.
_JSON_DURATION_FOLD = '''
[[input]]
name        = "a duration the subject writes"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>\\b\\d+us\\b)'
placeholder = "<DUR>"
scope       = "*"
finding     = "the subject writes how long it took, which moves every run"
control     = { sample = "took 12us", moved = "took 15us" }
'''

#: A `json-fields` fold of the commit the subject stamps, and its fixtures.
_JSON_COMMIT_FOLD = '''
[[input]]
name          = "the commit the subject stamps"
disposition   = "fold"
kind          = "json-fields"
paths         = ["prov"]
fields        = ["commit"]
placeholder   = "<SHA>"
serialization = { indent = 2, ensure_ascii = false }
finding       = "the subject stamps a commit that moves every run"
control       = { sample = "sample.json", moved = "moved.json" }

[fixtures]
dir = "fixtures"
'''


def _json_case(box: str, name: str, mode: str, census_text: str, *,
               twice: bool = False, then: str = "", extension: str = "json"
               ) -> tuple[str, bytes, str]:
    """Capture arm `cccccc`'s subject in `box/name` under `census_text`:
    `(what happened, the recorded .json as BYTES, the log)`. With `then`, the
    subject is switched to that mode and the golden compared against a fresh
    capture, and what happened is the comparison's exit and its `[DIFF]`
    detail. `extension` is the one `writes` ends with, spelled as given."""
    where = os.path.join(box, name)
    os.makedirs(os.path.join(where, "fixtures"))
    for leaf, commit in (("sample.json", "aaaaaaa"), ("moved.json", "bbbbbbb")):
        pathlib.Path(os.path.join(where, "fixtures", leaf)).write_text(
            json.dumps({"prov": {"commit": commit}}, indent=2) + "\n", encoding="utf-8")
    manifest = load_manifest(_scratch(
        where, manifest_text=_JSON_MANIFEST.replace(
            "<surface>.json", f"<surface>.{extension}"),
        census_text=census_text,
        extra={"stub.py": _JSON_SUBJECT, "mode.txt": mode}))
    golden = os.path.join(where, "golden")
    log = io.StringIO()
    try:
        said = f"exit {capture(manifest, golden, log, (), False, twice)}"
    except Refusal as refused:
        return _one_line(refusal_text(refused).replace(box, "<box>"), 240), \
            b"", log.getvalue()
    leaf = f"report.{extension}"
    recorded = _recorded_bytes(golden, leaf).get(leaf, b"")
    if then:
        pathlib.Path(os.path.join(where, "mode.txt")).write_text(then, encoding="utf-8")
        compared = io.StringIO()
        code = compare(manifest, golden, None, None, compared)
        said = f"compare exit {code}: " + _one_line(
            compared.getvalue(), 200, needles=("[DIFF]", "final newline"))
    return said, recorded, log.getvalue()


def _json_regex_control(check: CheckRow) -> None:
    """(cccccc) a `.json` written file goes through the ONE door every
    recorded text goes through, and keeps its final newline as written.

    `normalize_json` applies the `json-fields` folds and their round trip
    first, then `normalize_text` under the row's key — every in-scope `regex`
    fold and the capture-time root-overlap refusal, then the `path` folds —
    and appends the file's trailing line endings exactly as the subject wrote
    them. A `writes` ending `.JSON` is a `.json` (`core.folded_name`).
    A `.json` file sees every in-scope `regex` fold, so `--twice` is
    byte-identical over a token a census row folds, and the final newline is
    the one the subject wrote, so a subject that loses or changes one is a
    [DIFF].
    """
    label = ("cccccc  a `regex` fold reaches a written `.json` file: a "
             "duration folded to <DUR> there as in stdout, and in the "
             "recorded standard error, `--twice` "
             "byte-identical over it, the same beside a `json-fields` fold "
             "of a moving commit, and a row-scoped fold whose group splits "
             "the subject root in the `.json` REFUSED naming the row; the "
             "file's final newline is recorded as written — none, `\\n` or "
             "`\\r\\n`, with and without a `json-fields` row — and a file "
             "that gains one is a [DIFF] naming the final newline; a `writes` "
             "ending `.JSON` gets the `json-fields` fold too")
    with _box("golden-census-json-") as box:
        duration = _JSON_CENSUS + _JSON_DURATION_FOLD
        fields = duration + _JSON_COMMIT_FOLD
        claim, claim_json, _ = _json_case(box, "claim", "took", duration)
        on_stderr, _, _ = _json_case(box, "err", "err", duration)
        recorded_err = _recorded_bytes(os.path.join(box, "err", "golden"),
                                       "report.err").get("report.err")
        twice, _, twice_log = _json_case(box, "twice", "took", duration,
                                         twice=True)
        prov, prov_json, _ = _json_case(box, "prov", "prov", fields)
        upper, upper_json, _ = _json_case(box, "upper", "prov", fields,
                                          extension="JSON")
        root_fold = f'''
[[input]]
name        = "a fold that splits the subject root"
disposition = "fold"
kind        = "regex"
pattern     = '{re.escape(box)}/(?P<volatile>[^/"]+)'
placeholder = "<SPLIT>"
scope       = ["_subject/report"]
finding     = "planted: its group takes the root's last component"
control     = {{ sample = "x", moved = "y" }}
'''
        root, _, _ = _json_case(box, "root", "root", _JSON_CENSUS + root_fold)
        tails = {(mode, bool(census)): _json_case(
                     box, f"{mode}-{bool(census)}", mode,
                     _JSON_CENSUS + census)[1]
                 for mode in ("none", "lf", "crlf")
                 for census in ("", _JSON_COMMIT_FOLD)}
        gained, _, _ = _json_case(box, "gained", "none", _JSON_CENSUS,
                                  then="lf")
    body = b'{\n  "a": 1\n}'
    tail_ok = all(tails[(mode, fields_row)] == body + ending
                  for mode, ending in (("none", b""), ("lf", b"\n"),
                                       ("crlf", b"\r\n"))
                  for fields_row in (False, True))
    check(label,
          claim == "exit 0" and claim_json == b'{"took": "<DUR>"}\n'
          and on_stderr == "exit 0" and recorded_err == b"took <DUR>\n"
          and twice == "exit 0" and "byte-identical" in twice_log
          and prov == "exit 0"
          and prov_json == (b'{\n  "prov": {\n    "commit": "<SHA>"\n  },\n'
                            b'  "took": "<DUR>"\n}\n')
          and upper == "exit 0" and upper_json == prov_json
          and root.startswith("REFUSED: ")
          and "would rewrite the subject root" in root
          and "_subject/report" in root
          and tail_ok and gained.startswith("compare exit 1")
          and FINAL_NEWLINE in gained,
          f"{ACTUAL}the duration -> {claim}, {claim_json!r}; on standard error -> "
          f"{on_stderr}, {recorded_err!r}; --twice -> "
          f"{twice}, byte-identical={'byte-identical' in twice_log}; beside "
          f"a json-fields fold -> {prov}, {prov_json!r}; the same written as "
          f".JSON -> {upper}, {upper_json!r}; a row-scoped fold "
          f"splitting the root -> {_one_line(root, 150)}; the tails "
          + ", ".join(f"{mode}{'+fields' if row else ''}={recorded[-3:]!r}"
                      for (mode, row), recorded in tails.items())
          + f"; no newline against one -> {gained}",
          next="`census.normalize_json` applies `_json_parts` (the "
               "json-fields folds and the round trip) and then "
               "`normalize_text` under the row's key, and appends the "
               "file's own trailing line endings; `Recorder.record` passes "
               "the key. Read the detail for which went wrong.")


def _path_flags(parser: argparse.ArgumentParser, command: str = ""
                ) -> list[tuple[str, argparse.ArgumentParser, argparse.Action]]:
    """`(subcommand, its parser, the flag's action)` for every flag `parser`
    and every subcommand's parser under it declare a path, read off each
    parser's own `paths` and the table the parser dispatches on."""
    found = [(command, parser, action)
             for action in getattr(parser, "paths", [])]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found += _path_flags(sub, name)
    return found


def _main_said(main: Callable[[list[str]], int], argv: list[str]
               ) -> tuple[int | str | None, str]:
    """`(exit, standard output)` of one command line through `main`, with
    what argparse may print on standard error kept off the self-check's."""
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return _quietly(main, argv)
    except SystemExit as left:
        return left.code, "argparse exited before `main` read the flags"


#: The flags that must name a path, each as `cli._Parser.named` names it:
#: behind its subcommand, and alone for the one declared before any. Arm
#: `tttt` holds the parser's declaration (`path=True`) to this set both
#: ways, so a flag that lost its declaration, or one that gained it, is a
#: red row. It is the expected value of that one assertion, read by no
#: other check.
_MUST_BE_PATHS = frozenset({
    "--manifest", "capture --manifest", "capture --out",
    "compare --manifest", "compare --golden", "compare --against",
    "compare --allow-diff", "census --manifest",
    "mutants --manifest", "mutants --mutants", "probe --census", "init dir"})


def _not_a_directory_control(check: CheckRow) -> None:
    """(tttt) a path that is not a directory is not an empty capture, and an
    empty value is no path.

    The second half runs every flag the parser declares a path through the
    real `main`, with the command's other required flags given a path that
    is not there, so a run that is not refused for its empty value ends at
    the manifest's load and starts nothing. Each flag is also given that
    path, which is the control: a rule that refused every value of the flag
    would pass every other assertion of the half. The flags the parser
    declares a path must be `_MUST_BE_PATHS`, no more and no fewer: a
    flag that lost its declaration would leave the half one flag fewer
    to run, and still green.
    """
    label = ("tttt  `--golden` and `--against` each refuse at 2, before "
             "anything is compared, when the path is missing, when it names "
             "a FILE, and when it names a directory that HOLDS NO CAPTURE: "
             "`read_capture` owns all three, so neither flag can be the "
             "one somebody forgot to guard. Unguarded, a mistyped `--against` "
             "read `{}` off `os.walk` and reported every recorded row as "
             "only-in-golden at exit 1, and two mistyped paths that both "
             "happened to be empty directories compared IDENTICAL at exit 0 "
             "\u2014 the word this tool exists to make trustworthy, over nothing "
             "at all. A real capture directory still reads. Every flag the "
             "parser declares a path, given an empty or a white-space value, "
             "is ONE `REFUSED:` naming the flag behind its subcommand and "
             "saying it was given an empty or white-space value, with ONE "
             "`next:` naming it, at "
             "exit 2 and with no process-group line; two such flags on one "
             "command line are both named in each of the two lines; and "
             "the same flag given a path is not refused for an empty value "
             "\u2014 which flags name a path is read from the parser, and "
             "they are exactly the flags `_MUST_BE_PATHS` names, none of "
             "those missing from the parser's and none more, the detail "
             "naming them as the parser declares them")
    verdicts: dict[str, str] = {}
    with _box("golden-census-notdir-") as box:
        manifest = load_manifest(_scratch(box))
        good = os.path.join(box, "out")
        code = capture(manifest, good, io.StringIO(), (), False, False)
        a_file = os.path.join(box, "a-file")
        pathlib.Path(a_file).write_text("x\n", encoding="utf-8")
        absent = os.path.join(box, "absent")
        # A directory that exists and holds nothing golden-census wrote. Two
        # of them used to compare equal, which is the case this pair adds.
        empty = os.path.join(box, "empty")
        os.mkdir(empty)
        for why, golden_dir, against in (
                ("--against missing", good, absent),
                ("--against a file", good, a_file),
                ("--against holds no capture", good, empty),
                ("--golden missing", absent, good),
                ("--golden a file", a_file, good),
                ("--golden holds no capture", empty, good),
                ("both real", good, good)):
            log = io.StringIO()
            try:
                verdict = f"exit {compare(manifest, golden_dir, against, None, log)}"
                rows = [line for line in log.getvalue().splitlines()
                        if "golden files" in line]
                verdict += f", {rows[0].strip() if rows else '(no count line)'}"
            except Refusal as refused:
                # The box's path is replaced, not printed: this row is read on
                # any machine, and the directory it would name is this one's.
                # The sentence is cut at its first clause, and the rule it
                # states is reported as a flag beside it: four whole refusals
                # on one line say the same thing four times.
                whole = str(refused).replace(box, "<box>")
                verdict = ("REFUSED: " + whole.split(". ")[0] + "; the rule "
                           + ("named" if "not an empty capture" in whole
                              else "NOT NAMED"))
            verdicts[why] = verdict
    refused_well = all(
        verdicts[why].startswith("REFUSED: ") and why.split()[0] in verdicts[why]
        and verdicts[why].endswith("the rule named")
        for why in verdicts if why != "both real")
    compares = verdicts["both real"].startswith("exit 0")
    flags: list[str] = []
    declared: set[str] = set()
    wrong: list[str] = []
    with _box("golden-census-empty-path-") as box:
        absent = os.path.join(box, "absent")
        runs: list[tuple[list[str], list[str]]] = []
        for command, parser, action in _path_flags(build_parser()):
            # A positional is given its value alone, and named by its metavar.
            given = ([next(name for name in action.option_strings
                           if name.startswith("--"))]
                     if action.option_strings else [])
            flag = given[0] if given else str(action.metavar)
            named = f"{command} {flag}".strip()
            flags.append(f"`{named}`")
            declared.add(named)
            head = [command] if command else []
            for other in parser._actions:
                if (other.required and other.option_strings
                        and other is not action):
                    head += [other.option_strings[-1], absent]
            runs += [(head + given + [""], [named]),
                     (head + given + ["  "], [named]),
                     (head + given + [absent], [])]
        runs.append((["compare", "--manifest", absent, "--golden", absent,
                      "--against", "", "--allow-diff", ""],
                     ["compare --against", "compare --allow-diff"]))
        for argv, emptied in runs:
            said_code, printed = _main_said(main, argv)
            lines = printed.splitlines()
            refusals = [line for line in lines if line.startswith("REFUSED:")]
            nexts = [line for line in lines
                     if line.strip().startswith("next: ")]
            if emptied:
                ok = (said_code == 2 and len(refusals) == 1
                      and len(nexts) == 1
                      and "given an empty or white-space value" in refusals[0]
                      and all(f"`{named}`" in refusals[0]
                              and f"`{named}`" in nexts[0] for named in emptied)
                      and "process group" not in printed)
            else:
                ok = "empty value" not in printed
            if not ok:
                wrong.append(
                    f"{' '.join(map(repr, argv)).replace(box, '<box>')} -> "
                    f"exit {said_code}, process-group line "
                    f"{'printed' if 'process group' in printed else 'none'}, "
                    + _one_line(printed.replace(box, "<box>"), 110,
                                needles=("REFUSED:", "next:"),
                                empty=_NO_VERDICT))
    undeclared = sorted(_MUST_BE_PATHS - declared)
    unlisted = sorted(declared - _MUST_BE_PATHS)
    check(label, code == 0 and refused_well and compares and bool(flags)
          and not wrong and not undeclared and not unlisted,
          ACTUAL + "; ".join(f"{why} -> {verdicts[why]}" for why in verdicts)
          + f"; {len(flags)} flag(s) the parser declares a path \u2014 "
          f"{', '.join(flags) or 'none'} \u2014 each given an empty value "
          "and a path, and the pair `compare --against` and `compare "
          f"--allow-diff` given empty values; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}; flags that must be a path "
          f"and are not declared one: {', '.join(undeclared) or 'none'}; "
          f"declared a path and not among those: "
          f"{', '.join(unlisted) or 'none'}")


def _empty_value_control(check: CheckRow) -> None:
    """(jjjjjjjj) the `init` directory, `probe --writes-env` and `compare
    --command` refuse an empty or white-space value, as the path flags do,
    each saying what golden-census reads from the flag.

    `init ""` wrote the three files into the working directory and named no
    directory, `init "  "` made a directory named two spaces, and `probe
    --writes-env ""` ran the probe it would have run without the flag and
    passed `5/5`. `compare --command ""` was refused as a path, which only
    its first element names. Each is run from inside an empty box through
    the real `main`: one `REFUSED:` and one `next:` naming the flag, exit 2,
    no process-group line, and the box still empty afterwards. The control
    is the same three commands given a value: `init` writes its files, and
    `probe` and `compare` are not refused for an empty value.
    """
    label = ("jjjjjjjj  `init` given an empty or white-space directory, "
             "`probe --writes-env` given an empty or white-space name, and "
             "`compare --command` given an empty or white-space element, is "
             "ONE `REFUSED:` and ONE `next:` naming it, at exit 2, with no "
             "process-group line and nothing written, the refusal saying what "
             "golden-census reads from the flag — a path, a variable's name, "
             "a command; the same three given a value are not refused for an "
             "empty value. Unguarded, `init \"\"` wrote three files into the "
             "working directory and `probe --writes-env \"\"` passed `5/5` as "
             "though the flag were absent")
    planted: list[tuple[list[str], str, str]] = [
        (["init", ""], "init dir", "reads a path from it"),
        (["init", "  "], "init dir", "reads a path from it"),
        (["probe", "--writes-env", "", "--", "sh", "<WRITES>"],
         "probe --writes-env", "reads an environment variable's name from it"),
        (["probe", "--writes-env", "  ", "--", "sh", "<WRITES>"],
         "probe --writes-env", "reads an environment variable's name from it"),
        (["compare", "--manifest", "absent", "--golden", "absent",
          "--command", ""], "compare --command", "reads a command from it"),
        (["compare", "--manifest", "absent", "--golden", "absent",
          "--command", "x", "--command", "  "], "compare --command",
         "reads a command from it")]
    wrong: list[str] = []
    with _box("golden-census-empty-value-") as box, contextlib.chdir(box):
        for argv, named, reads in planted:
            said_code, printed = _main_said(main, argv)
            lines = printed.splitlines()
            refusals = [line for line in lines if line.startswith("REFUSED:")]
            nexts = [line for line in lines
                     if line.strip().startswith("next: ")]
            left = sorted(os.listdir(box))
            if not (said_code == 2 and len(refusals) == 1 and len(nexts) == 1
                    and "given an empty or white-space value" in refusals[0]
                    and reads in refusals[0]
                    and f"`{named}`" in refusals[0]
                    and f"`{named}`" in nexts[0]
                    and "process group" not in printed and not left):
                wrong.append(
                    f"{' '.join(map(repr, argv))} -> exit {said_code}, "
                    f"{'process-group line printed, ' if 'process group' in printed else ''}"
                    f"left {left or 'nothing'}, "
                    + _one_line(printed, 110, needles=("REFUSED:", "next:"),
                                empty=_NO_VERDICT))
        named_code, named_said = _main_said(main, ["init", "named"])
        written = sorted(os.listdir(os.path.join(box, "named"))) \
            if os.path.isdir(os.path.join(box, "named")) else []
        probe_code, probe_said = _main_said(
            main, ["probe", "--writes-env", "OUT", "--", "true"])
        command_code, command_said = _main_said(
            main, ["compare", "--manifest", "absent", "--golden", "absent",
                   "--command", "x"])
    controls_hold = (named_code == 0 and "manifest.toml" in written
                     and "empty or white-space" not in probe_said
                     and "empty or white-space" not in command_said)
    check(label, not wrong and controls_hold,
          ACTUAL + f"not as the row says: {'; '.join(wrong) or 'none of the six'}"
          f"; `init named` exit {named_code}, wrote {written or 'nothing'}; "
          f"`probe --writes-env OUT` exit {probe_code}, "
          + ("refused for an empty value" if "empty or white-space" in probe_said
             else "not refused for an empty value")
          + f"; `compare --command x` exit {command_code}, "
          + ("refused for an empty value"
             if "empty or white-space" in command_said
             else "not refused for an empty value"))


#: The stub manifest plus one and two DECLARED skip surfaces, for arm `ttttt`.
#: A declared skip is the manifest author's own sentence, the same on every
#: machine, so two captures of it agree — which is the silence this arm is
#: about.
_ONE_SKIP_MANIFEST = _STUB_MANIFEST.replace(
    'surfaces = ["help"]', 'surfaces = ["help", "unrunnable"]') + '''
[surfaces.unrunnable]
kind = "skip"
skip = "needs an index store this machine has not got"
'''

_TWO_SKIP_MANIFEST = _ONE_SKIP_MANIFEST.replace(
    'surfaces = ["help", "unrunnable"]',
    'surfaces = ["help", "unrunnable", "unbuildable"]') + '''
[surfaces.unbuildable]
kind = "skip"
skip = "needs a toolchain this machine has not got"
'''


def _both_skipped_control(check: CheckRow) -> None:
    """(ttttt) `compare` names the rows that are a `.skip` on BOTH sides.

    A skipped surface records one file, and two captures that both skipped it
    hold the same text and compare equal — so the summary said `IDENTICAL`
    with no line saying nothing had run. Since an environmental skip records
    one FIXED sentence the case is easier to hit, not harder: two machines
    that both failed to clone an input agree on every byte of it.

    The verdict does not move and the exit code does not move. What the line
    adds is the sentence `IDENTICAL` cannot say: those rows ran on neither
    side, so the word is about two recorded reasons and not about a surface.

    The third case is the control — with no skip anywhere the line is not
    printed at all — and the fourth is the other half of the rule: a row whose
    two reasons DIFFER is named here AND is a `[DIFF]`, because this line says
    what did not run and never whether the two agree.

    The `unrunnable.skip` this arm plants and reads is spelled by hand rather
    than from `core.SKIP_EXTENSION`: an arm that only asks the owner cannot
    notice the owner moved, and this one is the tripwire for that suffix.
    """
    label = ("ttttt  `compare` prints one disclosed line naming the rows that "
             "are a skip on BOTH sides, with the `.skip` suffix cut, sorted "
             "and counted — only when there are any, and without moving the "
             "verdict or the exit code; a row whose two recorded reasons "
             "DIFFER is named there AND is a `[DIFF]`, because the line says "
             "what did not run and not whether the two agree")
    verdicts: dict[str, str] = {}
    codes: dict[str, int] = {}
    with _box("golden-census-both-skipped-") as box:
        plants = (("one skip", _ONE_SKIP_MANIFEST),
                  ("two skips", _TWO_SKIP_MANIFEST),
                  ("no skip", _STUB_MANIFEST))
        changed_golden = ""
        changed_new = ""
        for key, text in plants:
            where = os.path.join(box, key.replace(" ", "-"))
            path = _scratch(where, manifest_text=text)
            manifest = load_manifest(path)
            golden = os.path.join(where, "golden")
            capture(manifest, golden, io.StringIO())
            new = os.path.join(where, "new")
            shutil.copytree(golden, new)
            log = io.StringIO()
            codes[key] = compare(manifest, golden, new, None, log)
            verdicts[key] = log.getvalue()
            if key == "one skip":
                changed_golden, changed_new = golden, new

        # The same pair with ONE side's recorded reason rewritten: the row is
        # a real difference AND a row that ran on neither side.
        pathlib.Path(os.path.join(changed_new, "_subject", "unrunnable.skip")).write_text(
            "a different sentence entirely\n", encoding="utf-8")
        log = io.StringIO()
        manifest = load_manifest(os.path.join(box, "one-skip",
                                              "manifest.toml"))
        codes["a changed reason"] = compare(manifest, changed_golden,
                                            changed_new, None, log)
        verdicts["a changed reason"] = log.getvalue()

    def line_of(key: str) -> str:
        return next((one.strip() for one in verdicts[key].splitlines()
                     if one.strip().startswith("[SKIP]")), "")

    one, two = line_of("one skip"), line_of("two skips")
    changed = verdicts["a changed reason"]
    check(label,
          one == ("[SKIP]    1 row(s) are a skip on both sides, so nothing "
                  "ran to compare: _subject/unrunnable")
          and two == ("[SKIP]    2 row(s) are a skip on both sides, so "
                      "nothing ran to compare: _subject/unbuildable, "
                      "_subject/unrunnable")
          and "IDENTICAL" in verdicts["one skip"] and codes["one skip"] == 0
          and codes["two skips"] == 0
          # The control: no skip anywhere, no line.
          and line_of("no skip") == "" and codes["no skip"] == 0
          and "_subject/unrunnable" in line_of("a changed reason")
          and "[DIFF]    _subject/unrunnable.skip" in changed
          and codes["a changed reason"] == 1,
          ACTUAL + "; ".join(
              f"{key} -> exit {codes[key]}, "
              f"{line_of(key) or '(no [SKIP] line)'}"
              for key in verdicts)
          + f"; the changed reason is also a [DIFF]: "
          f"{'[DIFF]    _subject/unrunnable.skip' in changed}",
          next="`compare` reads the rows present in BOTH captures whose path "
               "ends in `core.SKIP_EXTENSION`. If the `no skip` case now "
               "prints a line, the condition has gone and the common case has "
               "a line saying zero; if the others do not, a comparison can "
               "say IDENTICAL again with nothing having run on either side.")


#: The bytes macOS writes at the head of a `.DS_Store`, cut just past the
#: first that is not UTF-8. A reader gets a file of this kind by opening a
#: golden directory in Finder, and 0xff at byte offset 9 is where its decode
#: stops.
_NOT_UTF8 = b"\x00\x00\x00\x01Bud1\x00\xff\xfe\x80"

#: A mutants file whose comparator reads a golden directory beside the mutants
#: file — `<HERE>/…` is used as it is — so this arm can plant one without
#: committing anything into the throwaway repository.
_PLANTED_GOLDEN_MUTANTS = """\
[checks.comparator]
builtin = "compare"
golden  = "<HERE>/planted-golden"

[[mutant]]
name    = "the version string"
file    = "tool.py"
find    = 'VERSION = "1.0"'
replace = 'VERSION = "9.9"'
expect  = ["comparator"]
"""


def _plant_bytes(directory: str, name: str) -> None:
    os.makedirs(directory, exist_ok=True)
    pathlib.Path(os.path.join(directory, name)).write_bytes(_NOT_UTF8)


def _verdict(run: Callable[[], int], box: str) -> str:
    """What one command did, WHOLE, with the arm's own box unnamed.

    The refusal entire, and its `next:` with it: the evidence is the list of
    files it names and the sentence that says what to do about each kind, and
    a row that read its conditions off a truncated copy would be asking about
    a string whose end it cut off. The caller truncates what it DISPLAYS and
    nothing it decides on.
    """
    try:
        return f"exit {run()}"
    except Refusal as refused:
        return ("REFUSED: " + str(refused).replace(box, "<box>")
                + "\n  " + refused.next.replace(box, "<box>"))


def _undecodable_control(check: CheckRow) -> None:
    """(uuuu) a file in a capture directory that is not UTF-8 text — whatever
    it is called."""
    label = ("uuuu  a file in a capture directory that is not UTF-8 is a "
             "REFUSAL naming the file and the byte offset, never a traceback, "
             "from `compare`, the command that reads one — and `capture "
             "--force` names the same file inside an input as one this capture "
             "does not record, without reading it; a `.DS_Store`, which macOS writes the moment "
             "somebody opens a golden directory in Finder, is refused by the "
             "SAME sentence and the same byte, because NO FILE NAME IS "
             "SPECIAL on any platform; and a folder holding TWO such files is "
             "ONE refusal naming BOTH, sorted, because a reader who unpacked "
             "a Mac tarball has one beside every golden and must not pay a "
             "delete-and-rerun round for each. A golden row golden-census DID "
             "write, with its permissions taken away, stands in that same "
             "list and is NOT called somebody else's: it is named as one that "
             "cannot be READ, and the `next:` sends the reader to its "
             "permissions rather than telling them to delete a committed "
             "golden")
    verdicts: dict[str, str] = {}

    with _box("golden-census-undecodable-") as box:
        manifest = load_manifest(_scratch(box))
        good = os.path.join(box, "out")
        capture(manifest, good, io.StringIO(), (), False, False)

        # (1) `compare`, over a golden set carrying the file.
        planted = os.path.join(box, "planted")
        shutil.copytree(good, planted)
        _plant_bytes(planted, "not-text.out")
        verdicts["compare"] = _verdict(
            lambda: compare(manifest, planted, good, None, io.StringIO()), box)

        # (2) the same bytes under the name a desktop leaves behind. It is
        # refused exactly as (1) is: a golden folder holds only what
        # golden-census wrote, and a rule that stepped over one name would be
        # a rule that differs by platform — which is what made this half red
        # on Linux, where the skip list was empty.
        finder = os.path.join(box, "finder")
        shutil.copytree(good, finder)
        _plant_bytes(finder, ".DS_Store")
        verdicts["a .DS_Store"] = _verdict(
            lambda: compare(manifest, finder, good, None, io.StringIO()), box)

        # (3) TWO of them in one folder: one refusal, both named, sorted.
        both = os.path.join(box, "both")
        shutil.copytree(good, both)
        _plant_bytes(both, "not-text.out")
        _plant_bytes(both, "._help.out")
        verdicts["two in one folder"] = _verdict(
            lambda: compare(manifest, both, good, None, io.StringIO()), box)

        # (4) a real golden row this capture WROTE, with its permissions
        # taken away. The refusal has to name it without claiming something
        # else put it there, because something else did not.
        blocked_from = os.path.join(box, "blocked")
        shutil.copytree(good, blocked_from)
        blocked_row = os.path.join(blocked_from, "_subject", "help.out")
        unreadable_plant = "chmod 000"
        if _chmod_bites(blocked_row, _opens):
            os.chmod(blocked_row, 0o000)
        else:
            # Running as root, `chmod 000` leaves the file readable, and the
            # container this branch is headed for runs as root. The plant
            # cannot be built there; it is disclosed in the row's own detail
            # and the other plants still stand.
            unreadable_plant = "chmod 000 stayed readable here"
        verdicts["a golden row chmod 000"] = (
            _verdict(lambda: compare(manifest, blocked_from, good, None,
                                     io.StringIO()), box)
            if unreadable_plant == "chmod 000"
            else f"not exercised: {unreadable_plant}")
        os.chmod(blocked_row, 0o600)

        # (5) `capture --force --twice --input` over a golden carrying the file
        # inside the input it replaces: a stranger, named before anything
        # runs and never opened — `--twice` compares the two captures this
        # run recorded and reads nothing of `--out`.
        _plant_bytes(os.path.join(good, "_subject"), "not-text.out")
        verdicts["capture --force"] = _verdict(
            lambda: capture(manifest, good, io.StringIO(), ("_subject",),
                            True, True), box)

    def refuses(why: str, names: tuple[str, ...]) -> bool:
        """That command REFUSED, naming every planted file and the byte."""
        said = verdicts[why]
        return (said.startswith("not exercised")
                or ("REFUSED" in said
                    and "is not a row of this capture" in said
                    and "byte offset 9" in said
                    and all(name in said for name in names)))

    # Each command with the name IT planted. `mutants` reads a golden set of
    # its own and is arm `xxxxx`, an arm of its own because it needs `git`:
    # a half that counted an absent tool as a pass would pass loudest on the
    # machines where the untested path matters.
    named = [why for why, names in (("compare", ("not-text.out",)),)
             if refuses(why, names)]
    # `capture --force`'s own condition: the stranger refusal, naming the
    # file by its path inside the input — never read, so no byte offset.
    forced = verdicts["capture --force"]
    stranger = ("REFUSED" in forced and "this capture does not record" in forced
                and os.path.join("_subject", "not-text.out") in forced
                and "byte offset" not in forced)
    # No name is special: the same bytes under the name a desktop writes are
    # refused by the same sentence. This half and the one above are each
    # other's positive control — a rule that stepped over either would make
    # the other's verdict a statement about the name rather than the bytes.
    special = refuses("a .DS_Store", (".DS_Store",))
    # The unreadable row: named, named as one that CANNOT BE READ and not as
    # not-text, and the `next:` sends the reader to its permissions instead of
    # telling them to remove it. `not exercised` is the disclosed shape where
    # the plant could not be built.
    blocked_said = verdicts["a golden row chmod 000"]
    blocked_ok = (blocked_said.startswith("not exercised")
                  or ("REFUSED" in blocked_said
                      and "_subject/help.out (cannot be read:" in blocked_said
                      and "_subject/help.out (not text:" not in blocked_said
                      and "fix the permissions of each that cannot be read"
                      in blocked_said))
    # ONE refusal, BOTH named, and `._help.out` sorts before `not-text.out`.
    said_both = verdicts["two in one folder"]
    order = (said_both.index("._help.out") < said_both.index("not-text.out")
             if "._help.out" in said_both and "not-text.out" in said_both
             else False)
    two = (refuses("two in one folder", ("._help.out", "not-text.out"))
           and "2 file(s)" in said_both and order)
    check(label, len(named) == 1 and stranger and special and two and blocked_ok,
          ACTUAL + "; ".join(f"{why} -> {_one_line(verdicts[why], 260)}"
                                 for why in verdicts)
          + f"; the two-file refusal names both, sorted: {two}; the "
          f"chmod-000 golden row is named as unreadable and the `next:` sends "
          f"the reader to its permissions: {blocked_ok}")


def _mutants_undecodable_control(check: CheckRow, skip: SkipRow) -> None:
    """(xxxxx) `mutants`' comparator refuses a file in the golden set it reads
    that is not UTF-8 text.

    The same rule as `uuuu`'s other halves and a command of its own, because
    `mutants` plants each mutant in a clone and so needs `git`. Held inside
    `uuuu` the half became the string `not exercised` on a machine with no
    `git`, and the row passed with one of its commands unrun — which is the
    one shape a self-check must never have: an absent optional tool is a
    disclosed SKIP, never a pass.
    """
    label = ("xxxxx  `mutants`' comparator reads a golden set the way "
             "`compare` does, and REFUSES a file in it that is not UTF-8 "
             "text — naming the file and the byte offset, never a traceback")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH and `mutants` clones the subject "
                    "before its comparator reads anything; nothing was made "
                    "and nothing is claimed.")
        return
    with _box("golden-census-undecodable-mutants-") as box:
        path, why = _mutant_box(box)
        if path is None:
            skip(label, f"{why}; nothing was made and nothing is claimed.")
            return
        pathlib.Path(os.path.join(box, "planted.toml")).write_text(
            _PLANTED_GOLDEN_MUTANTS, encoding="utf-8")
        _plant_marker(os.path.join(box, "planted-golden"))
        _plant_bytes(os.path.join(box, "planted-golden", "_subject"),
                     "rows.out")
        code, said = _mutants_run(load_manifest(path), box, "planted.toml")
        # The whole refusal, not its first sentence: the file names ARE the
        # evidence and they come after it.
        verdict = f"exit {code}: " + said.replace(box, "<box>")
    check(label,
          "REFUSED" in verdict and "is not a row of this capture" in verdict
          and "byte offset 9" in verdict and "rows.out" in verdict,
          ACTUAL + _one_line(verdict, 260),
          next="`core._capture_text` is the one reader of a recorded "
               "file's text, and `read_capture` is the one place the refusal "
               "is written; `mutants`' comparator reaches both through the "
               "golden set it is pointed at. If this row went red with a "
               "traceback, a second reader of that directory has appeared.")


#: The subject arm `ppppp` runs: it writes the file its second argument names
#: and prints a line that moves with `COLUMNS`, which is what the stub
#: census's own control varies. The first argument says what to write.
_WRITTEN_FILE_SUBJECT = '''\
import os
import sys

mode, target = sys.argv[1], sys.argv[2]
if mode == "binary":
    with open(target, "wb") as handle:
        handle.write(b"SQLite format 3\\x00\\xff\\xfe binary body\\n")
else:
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("one recorded line\\n")
print("rows at", os.environ.get("COLUMNS"))
'''

#: One surface that writes a file, run over an input whose single argument is
#: what the subject should write. `writes` is spelled as the manifest spells
#: it — the refusal quotes this value and never the expanded path.
_WRITTEN_FILE_MANIFEST = _subject("writes") + '''
[inputs._subject]
args     = ["{mode}"]
surfaces = ["database"]

[surfaces.database]
args   = ["<WRITES>"]
writes = "<WORK>/<input>-<surface>.db"
'''


#: Two rows, the SECOND refusing: `hello` records its files before
#: `database` writes bytes golden-census cannot decode. What the refusal
#: leaves in `--out` is the question.
_HALFWAY_MANIFEST = _subject("writes") + '''
[inputs._subject]
args     = []
surfaces = ["hello", "database"]

[surfaces.hello]
args   = ["text", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"

[surfaces.database]
args   = ["binary", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.db"
'''



def _written_not_text_control(check: CheckRow) -> None:
    """(ppppp) a file a SURFACE writes that golden-census cannot record is a
    refusal naming the row and the file.

    `capture` records text: a written file is read, normalized and compared
    line by line. Before this rule the read was an unguarded
    `open(..., encoding="utf-8")` and a subject that wrote a database, an
    archive or an image ended the capture with a `UnicodeDecodeError`
    traceback at exit 1 — a stack of golden-census's own frames in answer to
    a manifest a reader could fix in one line.

    The control is the same surface writing text, because a guard that
    refuses a good file is not a stricter guard.

    The same refusal one row LATE — after a first row has written its files
    — leaves `--out` as the capture found it, because the rows were recorded
    beside it: a fresh `--out` is never made and a pre-existing empty one
    stays empty, never a half-written directory the next capture refuses to
    adopt as its own.
    """
    label = ("ppppp  a file a surface writes that is not UTF-8 text is "
             "REFUSED at 2 — naming the row, the `writes` value as the "
             "manifest spells it and the byte that stopped the decode, with "
             "a `next:` that names the dump pattern and no directory of this "
             "machine anywhere in it — while the same surface writing text "
             "records it; the same "
             "refusal after a first row was recorded leaves `--out` as the "
             "capture found it — a fresh one gone, an empty one empty")
    verdicts: dict[str, str] = {}
    recorded = ""
    leaked = False
    with _box("golden-census-written-") as box:
        for mode in ("binary", "text"):
            where = os.path.join(box, mode)
            path = _scratch(
                where,
                manifest_text=_WRITTEN_FILE_MANIFEST.replace("{mode}", mode),
                census_text=_STUB_WORK_CENSUS,
                extra={"stub.py": _WRITTEN_FILE_SUBJECT})
            out = os.path.join(box, f"{mode}-out")
            log = io.StringIO()
            # Caught rather than left to propagate: a refusal out of a control
            # ends the whole self-check at this row, and this arm's red has to
            # be a FAIL row so the arms after it still run.
            code, said = -1, ""
            try:
                code = capture(load_manifest(path), out, log)
                verdicts[mode] = f"exit {code}"
            except Refusal as refused:
                said = refusal_text(refused)
                leaked = leaked or box in said
                verdicts[mode] = said.replace(box, "<box>")
            if mode == "text" and code == 0:
                recorded = read_capture(out, "--out").get(
                    "_subject/database.db", "")
        halfway = os.path.join(box, "halfway")
        halfway_path = _scratch(halfway, manifest_text=_HALFWAY_MANIFEST,
                                census_text=_STUB_WORK_CENSUS,
                                extra={"stub.py": _WRITTEN_FILE_SUBJECT})
        # What each `--out` holds after the refusal, as relative paths:
        # `None` for a directory that is not there.
        left: dict[str, list[str] | None] = {}
        halfway_said: dict[str, str] = {}
        for case, make in (("fresh", False), ("empty", True)):
            out = os.path.join(box, f"halfway-{case}")
            if make:
                os.makedirs(out)
            try:
                code = capture(load_manifest(halfway_path), out, io.StringIO())
                halfway_said[case] = f"exit {code}"
            except Refusal as refused:
                halfway_said[case] = _one_line(
                    refusal_text(refused).replace(box, "<box>"), 60)
            left[case] = (sorted(os.path.relpath(os.path.join(at, name), out)
                                 for at, dirs, files in os.walk(out)
                                 for name in dirs + files)
                          if os.path.isdir(out) else None)

    binary = verdicts["binary"]
    check(label,
          binary.startswith("REFUSED: ")
          # The row and the file as the MANIFEST spells it: a refusal carrying
          # an absolute temp path is a line about this machine.
          and "_subject/database writes <WORK>/<input>-<surface>.db" in binary
          and "not text: 0xff at byte offset 16" in binary
          and "text DUMP" in binary and "ORDER BY" in binary
          and not leaked
          and verdicts["text"] == "exit 0"
          and recorded == "one recorded line\n"
          and all(said.startswith("REFUSED: _subject/database writes")
                  for said in halfway_said.values())
          and left["fresh"] is None and left["empty"] == [],
          ACTUAL + "; ".join(f"{mode} -> {_one_line(text, 200)}"
                                 for mode, text in verdicts.items())
          + f"; the recorded text row: {recorded!r}; the refusal named the "
          f"arm's own box: {leaked}; the second row refusing after the "
          f"first recorded -> {halfway_said}, a fresh --out left "
          f"{left['fresh']}, an empty one left {left['empty']}",
          next="`run.run_subject` reads the written file and routes the "
               "reason to `core._capture_text`, which owns both sentences. "
               "If the first plant is a traceback again, that guard has gone; "
               "if the second is refused, a surface writing ordinary text is "
               "no longer recordable.")


#: Arm `bbbbbb`'s subject: argv is the input's mode (`ok` writes the file,
#: `fail` writes nothing and exits 3), then the surface's kind, then — for
#: every kind — the `<WRITES>` path, which only an `ok` run row writes to.
_CLEARED_SUBJECT = '''\
import sys

mode, kind = sys.argv[1], sys.argv[2]
if kind == "tallies":
    print("========\\nG\\n========\\n1/1 passed")
elif kind == "row":
    sys.stderr.write("usage: stub\\n" + sys.argv[3] + "\\n")
    raise SystemExit(2)
elif mode == "ok":
    open(sys.argv[3], "w").write('{"from": "ok"}\\n')
    print("wrote")
else:
    print("failed, wrote nothing", file=sys.stderr)
    raise SystemExit(3)
'''

#: Two inputs sharing ONE `writes` path — `a` writes it, `b` does not — and a
#: `tallies` and a `matrix` surface that each spell `<WRITES>` with a
#: `writes` of their own. `{writes}` is what the load plants replace.
_CLEARED_MANIFEST = _subject("cleared") + '''
[inputs.a]
args     = ["ok"]
surfaces = ["s", "t", "m"]

[inputs.b]
args     = ["fail"]
surfaces = ["s"]

[surfaces.s]
args   = ["run", "<WRITES>"]
writes = "{writes}"

[surfaces.t]
kind    = "tallies"
args    = ["tallies", "<WRITES>"]
writes  = "<WORK>/<input>-<surface>.txt"
rule    = "="
verdict = '^\\d+/\\d+ passed$'

[surfaces.m]
kind    = "matrix"
include = "rows.json"
writes  = "<WORK>/<input>-<surface>.txt"
'''

_CLEARED_ROWS = ('[{"label": "one", "args": ["row", "one", "<WRITES>"]}, '
                 '{"label": "two", "args": ["row", "two", "<WRITES>"]}]\n')

#: The `[files]` entry that seeds the shared path before any row runs.
_SEEDED_FILE = '''
[files."out.json"]
lines = ['{"from": "a [files] entry"}']
'''


def _cleared_capture(box: str, name: str, *, writes: str = "<WORK>/out.json",
                     extra: str = "", inputs: tuple[str, ...] = ()
                     ) -> tuple[str, dict[str, str]]:
    """Capture arm `bbbbbb`'s subject in `box/name`: `(what happened, the
    recorded files of the capture)`. A refusal — at load or during the
    capture — is what happened, and nothing is recorded."""
    where = os.path.join(box, name)
    path = _scratch(where, manifest_text=_CLEARED_MANIFEST.replace(
                        "{writes}", writes) + extra,
                    census_text=_STUB_WORK_CENSUS,
                    extra={"stub.py": _CLEARED_SUBJECT,
                           "rows.json": _CLEARED_ROWS})
    out = os.path.join(where, "out")
    try:
        code = capture(load_manifest(path), out, io.StringIO(), inputs)
    except Refusal as refused:
        return refusal_text(refused).replace(box, "<box>"), {}
    return f"exit {code}", read_capture(out, "--out")


#: Arm `bbbbbb`'s link plants: a setup step makes `{link}` a link to a
#: directory of the arm's own, or to the file in it — replacing `<WORK>`
#: itself when `{link}` is `<WORK>` — and input `b` — which writes nothing —
#: has the `writes` path `{writes}`, which leads through the link to where a
#: file of the reader's already is.
_LINKED_MANIFEST = _subject("cleared") + """
[[setup]]
name    = "link"
command = ["<PYTHON>", "<HERE>/link.py", "{link}"]

[inputs.b]
args     = ["fail"]
surfaces = ["s"]

[surfaces.s]
args   = ["run", "<WRITES>"]
writes = "{writes}"
needs  = ["link"]
"""


def _linked_capture(box: str, name: str, link: str, writes: str, *,
                    to_file: bool = False, inner: str = "",
                    by_row: bool = False
                    ) -> tuple[str, list[str], str, dict[str, str]]:
    """Capture arm `bbbbbb`'s link plant in `box/<name>`: `(what happened,
    what the directory the link leads to holds after, what its file reads,
    the recorded files of the capture)`. The link, made at `link`, leads to
    `box/away-<name>` — or, with `to_file`, to the `out.json` in it — which
    holds `out.json` before the capture starts; with `inner`, the file is
    planted in `box/away-<name>/<inner>` instead, and that directory is the
    one listed after. A link is made only where nothing is, so the setup
    step first removes the empty directory at `link` when there is one: that
    is how it puts a link where `<WORK>` was. With `by_row`, no setup step
    makes the link: the row's own command does (`_ROW_LINKED_MANIFEST`). The
    capture's temp root is
    `box` itself: `core.remove_tree` follows no link, `path` included, and
    unlinks a link it finds where `<WORK>` was."""
    away = os.path.join(box, f"away-{name}")
    held = os.path.join(away, inner) if inner else away
    os.makedirs(held)
    kept = os.path.join(held, "out.json")
    pathlib.Path(kept).write_text("the reader's own\n", encoding="utf-8")
    target = kept if to_file else away
    where = os.path.join(box, name)
    manifest = _ROW_LINKED_MANIFEST if by_row else _LINKED_MANIFEST
    path = _scratch(where, manifest_text=manifest.replace(
                        "{link}", link).replace("{writes}", writes),
                    census_text=_STUB_WORK_CENSUS,
                    extra={"stub.py": _CLEARED_SUBJECT,
                           "link.py": "import os, sys\n"
                                      "if os.path.isdir(sys.argv[1]):\n"
                                      "    os.rmdir(sys.argv[1])\n"
                                      f"os.symlink({target!r}, sys.argv[1])\n"})
    out = os.path.join(where, "out")
    recorded: dict[str, str] = {}
    try:
        with _tmpdir_as(box):
            code = capture(load_manifest(path), out, io.StringIO(), ())
        said = f"exit {code}"
        recorded = read_capture(out, "--out")
    except Refusal as refused:
        said = (refusal_text(refused).replace(os.path.realpath(box), "<box>")
                .replace(box, "<box>"))
    return (said, sorted(os.listdir(held)),
            pathlib.Path(kept).read_text(encoding="utf-8")
            if os.path.isfile(kept) else "", recorded)


#: Arm `bbbbbb`'s plant of a row's own link: the subject is `link.py`, and
#: input `b`'s row makes `{link}` — its argument — a link to a directory of
#: the arm's own, then writes nothing; its `writes` path `{writes}` leads
#: through that link.
_ROW_LINKED_MANIFEST = _subject("cleared", '["<PYTHON>", "link.py"]') + """
[inputs.b]
args     = []
surfaces = ["s"]

[surfaces.s]
args   = ["{link}"]
writes = "{writes}"
"""

def _first_sentence(text: str) -> str:
    """`text` up to the end of its first sentence or its first line, whole: a
    detail quotes a refusal's own words without cutting one."""
    head, stop, _ = text.partition("\n")[0].partition(". ")
    return head + stop.rstrip()


def _cleared_path_control(check: CheckRow) -> None:
    """(bbbbbb) a written file is the one THIS run wrote.

    `run._clear_written` removes whatever is at a row's `writes` path
    immediately before the row runs, so a row that writes nothing records
    no written file — whatever an earlier row sharing the path, a `[files]`
    entry or a setup step left there. A `tallies` and a `matrix` surface
    value `<WRITES>` from their own `writes` and clear it the same way,
    recording nothing from it. The removal cannot reach outside `<WORK>`:
    the loader holds the spelling of `writes` to `<WORK>/` and its rest to
    `manifest._stays_under`, and `_clear_written` refuses a path whose
    directory resolves outside `<WORK>` — which a plant makes with a setup
    step that links `<WORK>/d` to a directory of the arm's own. The test is
    of the directory, not of the path: the next plant's setup step makes
    `<WORK>/out.json` itself a link to a file of the arm's own, and the
    removal unlinks the link, inside `<WORK>`, and leaves the file. Last, a
    row's OWN command makes the link,
    after `_clear_written` asked: `<WORK>/d` a link to a directory of the
    arm's own that holds a file at the `writes` path; `<WORK>/out.json`, the
    `writes` path itself, a link to a file of the arm's own; and `<WORK>/d`
    a link to a directory of the arm's own that holds no file at the
    `writes` path. Each capture is refused after the row ran, and nothing is
    recorded from the path.
    """
    label = ("bbbbbb  a written file is recorded only when THIS run wrote "
             "it: two inputs sharing one `writes` path, the second writing "
             "nothing, record no `.json` for the second — nor does a row "
             "whose path a `[files]` entry seeded — while the first alone "
             "still records its own; a `tallies` and a `matrix` surface "
             "spelling `<WRITES>` with a `writes` capture at exit 0; and a "
             "`writes` of `<WORK>/../escape.json` or `<WORK>escape.json` is "
             "REFUSED when the manifest is read, naming `writes`, quoting it "
             "as the manifest spells it, with a `next:` naming `<WORK>/`; "
             "and a `writes` of `<WORK>/d/out.json` after a setup step made "
             "`<WORK>/d` a link to a directory outside is REFUSED, naming the "
             "row and where the path resolves, and the file already there is "
             "untouched; and a `writes` of `<WORK>/out.json` that a setup "
             "step made a link to a file outside is no refusal: the capture "
             "runs, records no written file for that row, and the file the "
             "link leads to is untouched; and a `writes` of "
             "`<WORK>/d/out.json` after the row's own command made `<WORK>/d` "
             "a link to a directory outside is REFUSED after the row ran, "
             "naming the row and where the path resolves, and the file there "
             "is untouched; and so is a `writes` of `<WORK>/out.json` that "
             "the row's own command made a link to a file outside, the file "
             "untouched; and the refusal after the row ran is made where no "
             "file is at the path it resolves to")
    with _box("golden-census-cleared-") as box:
        shared, shared_files = _cleared_capture(box, "shared")
        seeded, seeded_files = _cleared_capture(box, "seeded",
                                                extra=_SEEDED_FILE,
                                                inputs=("b",))
        alone, alone_files = _cleared_capture(box, "alone", inputs=("a",))
        climbs, _ = _cleared_capture(box, "climbs",
                                     writes="<WORK>/../escape.json")
        glued, _ = _cleared_capture(box, "glued", writes="<WORK>escape.json")
        linked, away, kept, _ = _linked_capture(
            box, "linked", "<WORK>/d", "<WORK>/d/out.json")
        filed, away_filed, kept_filed, filed_files = _linked_capture(
            box, "filed", "<WORK>/out.json", "<WORK>/out.json", to_file=True)
        after, away_after, kept_after, _ = _linked_capture(
            box, "after", "<WORK>/d", "<WORK>/d/out.json", by_row=True)
        last, away_last, kept_last, _ = _linked_capture(
            box, "last", "<WORK>/out.json", "<WORK>/out.json", to_file=True,
            by_row=True)
        bare, _, _, _ = _linked_capture(
            box, "bare", "<WORK>/d", "<WORK>/d/out.json", inner="x",
            by_row=True)
    tallies = shared_files.get("a/t.out", "")
    matrix = shared_files.get("a/m.out", "")
    after_ran = "\n  ran: " in after
    last_ran = "\n  ran: " in last
    bare_ran = "\n  ran: " in bare
    plants = ((climbs, "<WORK>/../escape.json"), (glued, "<WORK>escape.json"))
    refused = [said for said, spelled in plants
               if said.startswith("REFUSED: ") and "`writes`" in said
               and repr(spelled) in said
               and "<WORK>/" in said.partition("next:")[2]]
    check(label,
          shared == "exit 0" and "b/s.json" not in shared_files
          and shared_files.get("b/s.exit") == "3\n"
          and seeded == "exit 0" and "b/s.json" not in seeded_files
          and alone == "exit 0"
          and alone_files.get("a/s.json") == '{"from": "ok"}\n'
          and tallies == "groups: 1\nG: 1/1 passed\n"
          and matrix.startswith("pairs: 2\n")
          and len(refused) == 2
          and linked.startswith("REFUSED: b/s writes <WORK>/d/out.json, "
                                "which resolves to <box>/away-linked/"
                                "out.json, outside golden-census's work "
                                "directory.")
          and away == ["out.json"] and kept == "the reader's own\n"
          and filed == "exit 0" and "b/s.json" not in filed_files
          and away_filed == ["out.json"]
          and kept_filed == "the reader's own\n"
          and after.startswith("REFUSED: b/s writes <WORK>/d/out.json, "
                               "which resolves to <box>/away-after/"
                               "out.json once the row has run, outside "
                               "golden-census's work directory.")
          and after_ran
          and away_after == ["out.json"]
          and kept_after == "the reader's own\n"
          and last.startswith("REFUSED: b/s writes <WORK>/out.json, which "
                              "resolves to <box>/away-last/out.json once the "
                              "row has run, outside golden-census's work "
                              "directory.")
          and last_ran
          and away_last == ["out.json"]
          and kept_last == "the reader's own\n"
          and bare.startswith("REFUSED: b/s writes <WORK>/d/out.json, "
                              "which resolves to <box>/away-bare/out.json "
                              "once the row has run, outside golden-census's "
                              "work directory.")
          and bare_ran,
          f"{ACTUAL}the shared path -> {shared}, b/s.json recorded="
          f"{'b/s.json' in shared_files}, b/s.exit="
          f"{shared_files.get('b/s.exit')!r}; the seeded path -> {seeded}, "
          f"b/s.json recorded={'b/s.json' in seeded_files}; a alone -> "
          f"{alone}, a/s.json={alone_files.get('a/s.json')!r}; the tallies "
          f"record {tallies!r}; the matrix record opens "
          f"{matrix.split(chr(10))[0]!r}; `<WORK>/../escape.json` -> "
          f"{_first_sentence(climbs)} | next: "
          f"{_first_sentence(climbs.partition('next:')[2].strip())}; "
          f"`<WORK>escape.json` -> {_first_sentence(glued)} | next: "
          f"{_first_sentence(glued.partition('next:')[2].strip())}; each quoted as "
          f"written with a `next:` naming <WORK>/: {len(refused)} of 2; "
          f"through a linked `<WORK>/d` -> {_first_sentence(linked)} | the "
          f"directory it leads to holds {away}, its file reads {kept!r}; "
          f"`<WORK>/out.json` itself a link to a file -> "
          f"{_first_sentence(filed)} | b/s.json recorded="
          f"{'b/s.json' in filed_files}, the directory it leads into holds "
          f"{away_filed}, its file reads {kept_filed!r}; "
          f"`<WORK>/d` linked by the row's own command -> "
          f"{_first_sentence(after)} | the refusal's block says "
          f"`ran:`={after_ran}; the directory it leads to holds "
          f"{away_after}, its file reads {kept_after!r}; `<WORK>/out.json` "
          f"made a link to a file by the row's own command -> "
          f"{_first_sentence(last)} | the refusal's block says "
          f"`ran:`={last_ran}; the directory it leads into holds "
          f"{away_last}, its file reads {kept_last!r}; `<WORK>/d` linked "
          f"by the row's own command to a directory with no file at the "
          f"path -> {_first_sentence(bare)} | the refusal's block says "
          f"`ran:`={bare_ran}",
          next="`run._clear_written` is called by `run_subject` before "
               "the child starts, and by `record_tallies_surface` and "
               "`record_matrix` before their runs; `manifest._surface` "
               "holds `writes` to `<WORK>/` and hands its rest to "
               "`_stays_under`; `_clear_written` asks `core.under` of the "
               "path's directory, through `run._outside`, before it removes "
               "anything; "
               "`run_subject` asks `run._outside` again after the subject "
               "ran, of the path with every link on it followed, before it "
               "reads the written file. Read the detail for which went "
               "wrong.")


#: Arm `zzzzz`'s subject: it prints whatever `transcript.txt` beside it holds,
#: so the arm rewrites the transcript between two captures and nothing else.
#: Byte for byte, so arm `aaaaaa`'s CRLF transcript reaches `record_tallies`
#: with its line endings.
_TALLIES_SUBJECT = '''\
import sys

with open("transcript.txt", "rb") as handle:
    sys.stdout.buffer.write(handle.read())
'''

#: Two fenced groups: ALPHA with one standing failure and its evidence line,
#: BETA clean. `{evidence}` is the one thing the arm moves.
_TALLIES_TRANSCRIPT = '''\
==========
ALPHA
==========
  [PASS]  a
  [FAIL]  b
           actual: {evidence}
9/10 passed
==========
BETA
==========
3/3 passed
'''

_TALLIES_MANIFEST = _subject("tallies") + '''
[inputs._subject]
args     = []
surfaces = ["tallies"]

[surfaces.tallies]
kind    = "tallies"
rule    = "="
verdict = '^\\s*\\d+/\\d+ passed\\s*$'
{failing}'''

#: What the fold case adds to the census below: one `regex` fold
#: scoped to the tallies row itself, the timing an evidence line can carry.
_TALLIES_FOLD = '''
[[input]]
name        = "a timing on an evidence line"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>\\b\\d+ms\\b)'
placeholder = "<DURATION>"
scope       = ["_subject/tallies"]
finding     = "a failing row's evidence line carries how long it took"
control     = { sample = "took 12ms", moved = "took 15ms" }
'''

#: A census has at least one row; this one's is the subject root's own fold.
_TALLIES_CENSUS = _STUB_ENVIRONMENT + _STUB_ROOT_FOLD


def _tallies_pair(box: str, name: str, before: str, after: str, *,
                  failing: bool, fold: bool = False,
                  transcript_text: str = _TALLIES_TRANSCRIPT
                  ) -> tuple[int, str, str]:
    """Capture the tallies subject with `before` as its evidence into a
    golden, rewrite the evidence to `after`, capture again, and compare the
    two recorded directories. `transcript_text` is what the subject prints,
    `{evidence}` in it being the one thing that moves.

    `(the compare's exit, the golden's recorded .out, the first capture's
    log)`. `capture.capture` is called directly, so the census's controls do
    not run here: what this arm is about is the RECORD, and the scratch
    census has nothing a control would add to it.
    """
    where = os.path.join(box, name)
    line = "failing = '^\\s*(?:\\[FAIL\\]|actual:)'\n" if failing else ""
    transcript = os.path.join(where, "transcript.txt")
    path = _scratch(
        where, manifest_text=_TALLIES_MANIFEST.replace("{failing}", line),
        census_text=_TALLIES_CENSUS + (_TALLIES_FOLD if fold else ""),
        extra={"stub.py": _TALLIES_SUBJECT,
               "transcript.txt": transcript_text.replace("{evidence}",
                                                         before)})
    manifest = load_manifest(path)
    golden, new = os.path.join(where, "golden"), os.path.join(where, "new")
    log = io.StringIO()
    capture(manifest, golden, log)
    pathlib.Path(transcript).write_text(
        transcript_text.replace("{evidence}", after), encoding="utf-8")
    capture(manifest, new, io.StringIO())
    compared = io.StringIO()
    code = compare(manifest, golden, new, None, compared)
    recorded = read_capture(golden, "--golden").get("_subject/tallies.out", "")
    return code, recorded, log.getvalue() + compared.getvalue()


#: What arm `zzzzz` plants to be refused when the manifest is READ, before a
#: row runs: (the case, the text of the manifest replaced, its replacement).
#: The repeat count is one past what `re` accepts, which it refuses with an
#: OverflowError rather than a `re.error`; the list would compile, spelled
#: into a pattern, as a character class.
_TALLIES_LOAD_PLANTS: tuple[tuple[str, str, str], ...] = (
    ("a `failing` past the repeat limit", "{failing}",
     "failing = 'a{4294967296}'\n"),
    ("a `failing` that is a list", "{failing}", "failing = ['x']\n"),
    ("a `verdict` that does not compile", "verdict = '^", "verdict = '(^"),
)


def _tallies_failing_control(check: CheckRow) -> None:
    """(zzzzz) a `tallies` surface with `failing` records each group's
    matching lines under its verdict line, so a failing row whose EVIDENCE
    moved while its name and its count stood still is a `[DIFF]`.

    The blindness it closes is shown on the same two transcripts: without
    `failing` they compare IDENTICAL, which is also the proof that the plant
    kept its names and its tallies still. Without the key the record is
    today's bytes exactly, and so is a transcript with no group at all —
    `groups: 0` and a blank line, spelled out below. A line is what ends in
    a newline and nothing else: an evidence line holding a form feed is
    recorded whole. The recorded lines go through `Recorder.record` under
    the row's own key, so a `regex` fold scoped to the row reaches them, and
    the capture log says how many lines the pattern caught. Both patterns
    are compiled when the manifest is read: one that does not compile — past
    `re`'s repeat limit included — or is not a string is refused there,
    naming the table and the key.

    Each case calls `capture.capture` directly, so the scratch census's
    controls do not run.
    """
    label = ("zzzzz  a `tallies` surface with `failing` records every line of "
             "a group matching it under that group's verdict line, exactly as "
             "printed, so an evidence line that grew while the failing row's "
             "name and the tally stood still is a [DIFF] — where the same two "
             "transcripts WITHOUT `failing` compare IDENTICAL; without the key "
             "the record is byte-for-byte what it was, with two groups and "
             "with none; an evidence line holding a form feed is recorded "
             "whole, so a change after the form feed is a [DIFF]; the "
             "recorded lines pass through a `regex` fold "
             "scoped to the row; the capture log counts the lines the pattern "
             "caught; and a `failing` past `re`'s repeat limit, a `failing` "
             "that is not a string and a `verdict` that does not compile are "
             "each REFUSED when the manifest is read, naming the table and "
             "the key")
    with _box("golden-census-tallies-failing-") as box:
        claim, recorded, claim_log = _tallies_pair(
            box, "claim", "x, y", "x, y, z", failing=True)
        blind, plain, plain_log = _tallies_pair(
            box, "blind", "x, y", "x, y, z", failing=False)
        folded, _folded_record, _fold_log = _tallies_pair(
            box, "fold", "x, y (12ms)", "x, y (15ms)", failing=True, fold=True)
        # A form feed INSIDE the evidence line: the text after it is part of
        # the line, and a change there is a change to the record.
        formfeed, fed, _fed_log = _tallies_pair(
            box, "formfeed", "x\x0cy", "x\x0cz", failing=True)
        _none_code, nothing, _none_log = _tallies_pair(
            box, "none", "", "", failing=False,
            transcript_text="no group was fenced in this run\n")
        loads: dict[str, str] = {}
        for case, old, new in _TALLIES_LOAD_PLANTS:
            where = os.path.join(box, f"load-{len(loads)}")
            path = _scratch(
                where, manifest_text=_TALLIES_MANIFEST.replace(old, new)
                .replace("{failing}", ""),
                census_text=_TALLIES_CENSUS,
                extra={"stub.py": _TALLIES_SUBJECT,
                       "transcript.txt": _TALLIES_TRANSCRIPT})
            loads[case] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")
    at_load = "it is compiled when the manifest is read"
    overflow, listed, verdict = loads.values()
    refused_at_load = (
        overflow.startswith("REFUSED: ")
        and "[surfaces.tallies]: `failing` does not compile" in overflow
        and at_load in overflow
        and listed.startswith("REFUSED: ")
        and "[surfaces.tallies]: `failing` must be a string" in listed
        and verdict.startswith("REFUSED: ")
        and "[surfaces.tallies]: `verdict` does not compile" in verdict
        and at_load in verdict)
    wanted = ("groups: 2\nALPHA: 9/10 passed\n  [FAIL]  b\n"
              "           actual: x, y\nBETA: 3/3 passed\n")
    today = "groups: 2\nALPHA: 9/10 passed\nBETA: 3/3 passed\n"
    # Hand-spelled: the count, then the blank line a golden with no group has
    # always carried.
    no_group = "groups: 0\n\n"
    diffs = [line.strip() for line in claim_log.splitlines()
             if line.strip().startswith("[DIFF]")]
    counted = "2 group tallies, 2 failing line(s)" in claim_log
    check(label,
          recorded == wanted and claim == 1 and len(diffs) == 1
          and "_subject/tallies.out" in diffs[0]
          and blind == 0 and plain == today and folded == 0
          and nothing == no_group and refused_at_load
          and formfeed == 1 and "           actual: x\x0cy\n" in fed
          and counted and "failing line(s)" not in plain_log,
          f"{ACTUAL}the record with `failing` {recorded!r}; the grown "
          f"evidence -> compare exit {claim}, {diffs}; the same transcripts "
          f"without `failing` -> compare exit {blind}, record {plain!r}; "
          f"12ms against 15ms under the scoped fold -> compare exit {folded}; "
          f"no group at all -> record {nothing!r}; "
          f"an evidence line holding a form feed, changed after it -> "
          f"compare exit {formfeed}, record {fed!r}; "
          f"the log counts the caught lines={counted}, and without the key "
          f"says nothing of them={'failing line(s)' not in plain_log}; "
          + "; ".join(f"{case} -> "
                      f"{_one_line(text.partition('[surfaces.')[2] or text, 90)}"
                      for case, text in loads.items()),
          next="`capture.record_tallies` finds the lines and "
               "`capture.record_tallies_surface` writes them under each "
               "verdict line and records the body through `Recorder.record`; "
               "`manifest._tallies_pattern` compiles both patterns at load. "
               "Read the detail for which went wrong.")


def _cleanup_control(check: CheckRow, skip: SkipRow,
                     manifest: Manifest | None) -> None:
    """(n) `capture` removes its temp directories even when it does not reach
    the end. The fault is planted where it bites: the FIRST write happens after
    both directories exist."""
    label = "n  the temp-directory cleanup arm"
    if manifest is None:
        skip(label, "no --manifest was given, so there is no capture to fault "
                    "in the window this arm guards. Nothing was made and "
                    "nothing is claimed.")
        return
    base_tmp = temp_base()
    width = manifest.census.fixed_width
    first = manifest.inputs[0].name
    fault = _FaultOnFirstWrite()
    expected = 1 if width is None else 2
    narrow = ""

    def body() -> None:
        """The capture, under whatever private root `_made_under` made."""
        nonlocal narrow
        if width is not None:
            normalized, room = fixed_dir_room(temp_base(), width)
            if room < 1:
                narrow = (f"the private temp root {normalized!r} this arm "
                          f"runs under is {len(normalized)} characters, so "
                          "`capture` refuses before making anything (see the "
                          "census's fixed-width-dir control); there is no "
                          "leak window to exercise here. Nothing was made and "
                          "nothing is claimed.")
                return
        try:
            capture(manifest, os.path.join(box, "out"), fault, (first,),
                    False, False)
        except RuntimeError as planted:
            fault.raised = str(planted)
        except Refusal as refused:
            # The reader's manifest or census refused the capture: a
            # statement about the RUN, which the census's own controls,
            # run after this walk, make again and end the run on. Escaping
            # here it would print as this arm's `!` row — the code's fault
            # for the census's — so it is this arm's disclosed SKIP instead.
            narrow = ("the capture of this manifest refused before the fault "
                      "could be planted, so there is no leak window to "
                      f"exercise here: {with_next(str(refused).split('. ')[0], refused)}. "
                      "The census's own controls below make the same "
                      "refusal and end the run on it. Nothing is claimed.")

    # The box sits OUTSIDE the private root, so what the private root holds is
    # exactly what the capture made — nothing to subtract, and no directory
    # another process makes during the body can be counted as a leak of this
    # one's.
    with _box("golden-census-clean-") as box:
        _result, leaked = _made_under(base_tmp, body)
    if narrow:
        skip(label, narrow)
        return
    during = fault.at_fault
    check("n  a capture that raises after making its temp directories still "
          "removes them: the planted fault sees them present and the temp root "
          "is left exactly as it was found",
          len(during) == expected and not leaked and fault.raised != "",
          f"{ACTUAL}{len(during)} of {expected} directory(ies) present at the "
          f"fault {[d[:22] for d in during]}, {len(leaked)} left behind "
          f"{leaked}, fault {fault.raised[:40]!r}")


def _workspace_removal_control(check: CheckRow, skip: SkipRow) -> None:
    """(qqqqqq) `core.workspace` removes its work directory whatever a subject
    left in it.

    A subject can leave a directory it made read-only — a module cache does —
    and `shutil.rmtree(ignore_errors=True)` then leaves the work directory
    under the temp root in silence. The red half plants the same tree in a box
    and removes it that plain way, so the plant is shown to defeat a removal
    that does not first make each directory writable. The link to a directory
    outside the work directory is what `core.remove_tree` must neither follow
    nor change.
    """
    label = ("qqqqqq  a work directory a subject left a read-only directory in "
             "is removed with the workspace, a directory outside it that a "
             "link inside it names keeps its mode, and the same planted tree "
             "is still there after a plain shutil.rmtree")
    base_tmp = temp_base()
    with _box("golden-census-removal-box-") as box:
        outside = os.path.join(box, "outside")
        os.makedirs(outside)
        if not _chmod_bites(outside, os.listdir):
            skip(label, "`chmod 000` left a directory listable — this run is "
                        "likely root — so a read-only directory cannot stop a "
                        "removal here. Nothing is claimed.")
            return

        def plant(work: str) -> None:
            """The subject's leftovers: a read-only module cache, and a link to
            a read-only directory outside `work`."""
            module = os.path.join(work, "cache", "mod")
            os.makedirs(module)
            pathlib.Path(module, "f").write_text("cached\n", encoding="utf-8")
            os.chmod(module, 0o555)
            os.symlink(outside, os.path.join(work, "out"))

        def left_read_only() -> None:
            """The planted tree, left in a workspace's work directory."""
            with workspace(None, "golden-census-removal-", box,
                           out=io.StringIO()) as roots:
                plant(roots.work)

        with _mode_as(outside, 0o555, 0o700):
            _none, left = _made_under(base_tmp, left_read_only)
            outside_mode = stat.S_IMODE(os.stat(outside).st_mode)
            planted = os.path.join(box, "planted")
            os.makedirs(planted)
            plant(planted)
            shutil.rmtree(planted, ignore_errors=True)
            survived = os.path.lexists(planted)
            removed = remove_tree(planted)
    check(label,
          not left and outside_mode == 0o555 and survived and removed,
          f"{ACTUAL}{len(left)} left behind {left}, the outside directory at "
          f"{oct(outside_mode)}; a plain shutil.rmtree left the plant "
          f"{'there' if survived else 'gone'}, remove_tree then {removed}")


#: Arm `t`'s label: its check row and its SKIP are one claim.
_T_LABEL = ("t  `compare` removes the temp capture directory it makes even "
            "when the capture refuses: no golden-census-compare-* is left "
            "behind")


def _compare_leak_control(check: CheckRow, skip: SkipRow) -> None:
    """(t) `compare` makes a capture directory of its own and removes it on
    every path: a refusal on the way must leave no `golden-census-compare-*`
    behind.

    The scratch manifest pins an impossible fixed-width TMPDIR, so the capture
    refuses in exactly the window a leak would happen in. `compare` is called
    directly: the self-check belongs to `cli.main`, so driving the comparator
    from inside a control does not run this file inside itself.
    """
    base_tmp = temp_base()
    census_text = _STUB_CENSUS + _fixed_pin(
        5, "planted: no temp root is short enough to hold a 5-character path",
        name="an impossible temp width")
    # The box sits OUTSIDE the private root `_made_under` makes, so the
    # listing IS what `compare` left behind.
    with _box("golden-census-cmpleak-") as box:
        golden = os.path.join(box, "golden")
        _plant_marker(golden)
        refusal = ""
        try:
            manifest = load_manifest(_scratch(box, census_text=census_text))
        except Refusal as refused:
            skip(_T_LABEL,
                 f"the scratch manifest would not load: {refused}. Nothing is "
                 "claimed.")
            return

        def body() -> str:
            try:
                compare(manifest, golden, None, None, io.StringIO())
            except Refusal as refused:
                return str(refused)
            return ""

        refusal, leaked = _made_under(base_tmp, body)
    check(_T_LABEL,
          "needs a root of at most" in refusal and not leaked,
          f"{ACTUAL}capture refused={refusal[:60]!r}, {len(leaked)} left "
          f"behind {leaked}")


def _allow_asked(path: str) -> tuple[str, str, str]:
    """`(what was raised, its sentence, its next)` for one call of
    `compare.read_allow`: `Refusal`, the name of the class of any other
    exception, or `nothing` for a table that was read."""
    try:
        read_allow(path)
    except Refusal as refused:
        return "Refusal", str(refused), refused.next
    except Exception as exc:              # noqa: BLE001 — the arm's subject
        if isinstance(exc, UNREPORTABLE):
            raise
        return type(exc).__name__, str(exc), ""
    return "nothing", "", ""


def _allow_shown(said: str, box: str) -> str:
    """One sentence of an `--allow-diff` arm's detail: its first 160
    characters and, of a longer one, its last 60, the box folded."""
    line = _one_line(said.replace(box, "<box>"), len(said), empty="(nothing)")
    return line if len(line) <= 220 else f"{line[:160]} … {line[-60:]}"


def _allow_file_control(check: CheckRow) -> None:
    """(ppp) an `--allow-diff` table that cannot be opened is a refusal of
    the reader's, naming the path as it was typed.

    `compare.read_allow` is asked here, itself, for a path that names no
    file and for one that names a directory. Each is a refusal that names
    the path as it was handed over — spelled with a `.` component, so one
    resolved before it was printed is a different string, and written with
    `repr`, so the path that holds a newline stays on one line — and the
    operating system's own reason for that fault, and carries a `next`. The
    control is a table that is there, which is read.

    WHEN the command line reads the table is row `ccccccc`'s.
    """
    label = ("ppp  an `--allow-diff` table that cannot be opened — a path "
             "that names no file, and a directory — is ONE refusal of "
             "`compare.read_allow` naming that path as it was typed and the "
             "operating system's reason, with a `next:`; the control is a "
             "table that is there, which is read")
    with _box("golden-census-allowfile-") as box:
        folder = os.path.join(box, ".", "a-directory")
        os.makedirs(folder)
        there = os.path.join(box, ".", "allow.txt")
        pathlib.Path(there).write_text("_subject/help.out :: a row\n",
                                       encoding="utf-8")
        asked = [(name, path, os.strerror(fault), _allow_asked(path))
                 for name, path, fault in (
                     ("a path that names no file",
                      os.path.join(box, ".", "no-such\nallow.txt"),
                      errno.ENOENT),
                     ("a directory", folder, errno.EISDIR))]
        control = _allow_asked(there)
    check(label,
          all(kind == "Refusal" and f": {path!r} ({reason})" in said
              and bool(after)
              for _name, path, reason, (kind, said, after) in asked)
          and control[0] == "nothing",
          ACTUAL
          + "; ".join(f"{name} raised {kind} {_allow_shown(said, box)!r}, "
                      f"wanted its reason {reason!r}, next= "
                      f"{'yes' if after else 'NO'}"
                      for name, _path, reason, (kind, said, after) in asked)
          + f"; the table that is there raised {control[0]} "
            f"{_allow_shown(control[1], box)!r}",
          next="`compare.read_allow` answers the `OSError` its one `open` "
               "raises with a refusal naming the path as typed, written with "
               "`repr`, and the error's `strerror`.")


#: An `--allow-diff` table saved as Latin-1, under 400 comment lines: its `é`
#: is the ONE byte 0xe9, and the newline after it is no continuation byte, so
#: a strict UTF-8 decode stops there — past the first buffer a read made line
#: by line would decode, and past the head of the file.
_ALLOW_NOT_TEXT = (b"# a comment line that permits nothing\n" * 400
                   + "_subject/help.out :: café\n".encode("latin-1"))

#: An `--allow-diff` table cut short inside a character: it ends in the first
#: two of the three bytes that spell `€`, so the decoder's exception spans
#: both, and its first byte and its last are different bytes.
_ALLOW_CUT_SHORT = b"_subject/help.out :: caf\xe2\x82"

#: An `--allow-diff` table whose one bad byte is on a COMMENT line, under a
#: comment line that holds `é` as the two bytes UTF-8 spells it with: a reader
#: that decodes the rows alone reads this table, and an offset counted in
#: characters is one less than the offset the file holds the byte at.
_ALLOW_BAD_COMMENT = (b"# caf\xc3\xa9\n"
                      b"# caf\xe9\n"
                      b"_subject/help.out :: a row\n")

#: The refusal of a table that is not UTF-8 text, as `compare.read_allow`
#: writes it: what its sentence opens with, ahead of the path; what it closes
#: with, after `core.bad_byte`'s phrase; and its `next`, whole.
_ALLOW_SAID_FIRST = "--allow-diff names a file that is not UTF-8 text: "
_ALLOW_SAID_LAST = ("The permitted-movement table is read whole, as UTF-8 "
                    "text, before anything is compared, so no row of it was "
                    "read and nothing was compared.")
_ALLOW_NEXT = ("Save that file as UTF-8, or drop the flag to permit only "
               "the movements the manifest's own [[movements]] rows name.")


def _allow_not_text_control(check: CheckRow) -> None:
    """(wwwwww) an `--allow-diff` table that is not UTF-8 text is a refusal
    of the reader's, naming the byte and its offset, held whole.

    `compare.read_allow` is asked here, itself. The sentence wanted is built
    from its opening words, the path as handed over — spelled with a `.`
    component, and written with `repr` — the byte, the offset the file holds it at, the reason
    Python's decoder gives for the same bytes, and its closing words; the
    `next` is compared entire. One word more, such as the name of an
    encoding nobody measured, is a different string.

    Three tables: a byte under 400 comment lines, which a read that is not
    whole does not reach; a character cut short at the file's end, named by
    the FIRST of the bytes the decoder's exception spans, in a file whose
    name holds a newline, which `repr` keeps on one line; and a byte on a
    comment line under a line that spells `é` with two bytes, which a reader
    that decodes only the rows reads, and whose offset counted in characters
    is one short.

    Two controls. The first table saved as UTF-8 is read. And a path `open`
    will not take — one holding a NUL character, which no command line can
    hold — leaves as the `ValueError` `open` raised: `UnicodeDecodeError` is
    a `ValueError`, and a clause written for the parent would hand
    `core.bad_byte` an exception that names no byte.

    WHEN the command line reads the table is row `ccccccc`'s.
    """
    label = ("wwwwww  an `--allow-diff` table holding a byte that is not "
             "UTF-8 is ONE refusal of `compare.read_allow`, whole: "
             f"`{_ALLOW_SAID_FIRST}`, the file as it was typed and quoted by "
             "`repr`, the byte, "
             "the offset IN BYTES the file holds it at and the decoder's "
             f"own reason, then `{_ALLOW_SAID_LAST}`, its `next:` line "
             f"`{_ALLOW_NEXT}` and no word more — for a byte under 400 "
             "comment lines, for the first byte of a character cut short "
             "at the file's end, and for a byte on a comment line under a "
             "line that holds a two-byte character; the control is the "
             "first table saved as UTF-8, which is read, and a path `open` "
             "will not take leaves as the `ValueError` `open` raised, "
             "never called a file that is not UTF-8 text")
    with _box("golden-census-allow-not-text-") as box:
        tables = [("a byte under 400 comment lines", "allow-latin-1.txt",
                   _ALLOW_NOT_TEXT, b"\xe9"),
                  ("a character cut short", "allow-cut\nshort.txt",
                   _ALLOW_CUT_SHORT, b"\xe2"),
                  ("a byte on a comment line", "allow-bad-comment.txt",
                   _ALLOW_BAD_COMMENT, b"\xe9")]
        asked: list[tuple[str, str, tuple[str, str, str]]] = []
        for name, leaf, raw, byte in tables:
            path = os.path.join(box, ".", leaf)
            pathlib.Path(path).write_bytes(raw)
            try:
                raw.decode("utf-8")
                reason = "(the decoder read these bytes)"
            except UnicodeDecodeError as undecodable:
                reason = undecodable.reason
            asked.append((name,
                          f"{_ALLOW_SAID_FIRST}{path!r} (0x{byte[0]:02x} at "
                          f"byte offset {raw.index(byte)} ({reason})). "
                          f"{_ALLOW_SAID_LAST}",
                          _allow_asked(path)))
        unopened = _allow_asked(os.path.join(box, "allow-latin-1.txt\0"))
        saved = os.path.join(box, "allow-utf-8.txt")
        pathlib.Path(saved).write_text(_ALLOW_NOT_TEXT.decode("latin-1"),
                                       encoding="utf-8")
        rows: list[tuple[str, str]] | str
        try:
            rows = read_allow(saved)
        except Refusal as refused:
            rows = f"Refusal: {refused}"
    check(label,
          all(got == ("Refusal", wanted, _ALLOW_NEXT)
              for _name, wanted, got in asked)
          and rows == [("_subject/help.out", "café")]
          and unopened[0] == "ValueError",
          ACTUAL
          + "; ".join(
              f"{name} raised {kind} {_allow_shown(said, box)!r}, "
              + ("the sentence wanted" if said == wanted else
                 f"WANTED {_allow_shown(wanted, box)!r}")
              + ", next= "
              + ("the line wanted" if after == _ALLOW_NEXT else
                 repr(_allow_shown(after, box)) if after else "NO")
              for name, wanted, (kind, said, after) in asked)
          + "; the first table saved as UTF-8 -> "
            f"{_allow_shown(rows, box) if isinstance(rows, str) else rows!r}"
            f"; a path holding a NUL character raised {unopened[0]} "
            f"{_allow_shown(unopened[1], box)!r}",
          next="`compare.read_allow` answers the `UnicodeDecodeError` its one "
               "read raises — that class and not its parent `ValueError` — "
               "with a refusal naming the path as typed, written with `repr`, and "
               "`core.bad_byte`'s phrase, whose byte and offset are both the "
               "exception's `start`, of ONE read of the whole file.")


#: An `--allow-diff` table: an attribution holding `#`, a comment line
#: indented and carrying `::`, a comment written after a bare path, and a
#: path with nothing after its `::`.
_ALLOW_TABLE = """\
fixtures/results.out :: fixed in issue #42
  # a comment :: it permits nothing
fixtures/other.out   # a note
fixtures/bare.out ::
"""

#: A `[[movements]]` row whose `attribution` line is filled in per case.
_MOVEMENT_ROW = """
[[movements]]
path = "_subject/help.out"
{attribution}
"""

#: Two `[[movements]]` rows: the first permits `_subject/help.out` for
#: "the first reason"; the second's `path` is `{second}` and its
#: `attribution` line is `{attribution}`, both filled in per case.
_TWO_MOVEMENT_ROWS = _MOVEMENT_ROW.format(
    attribution='attribution = "the first reason"') + """
[[movements]]
path = "{second}"
{attribution}
"""

#: The cases of two `[[movements]]` rows: (case, the second row's `path`,
#: its `attribution` line, the two attributions the refusal names, or None
#: where the two rows load).
_TWO_MOVEMENT_CASES = (
    ("one path twice", "_subject/help.out",
     'attribution = "the second reason"',
     "'the first reason' and 'the second reason'"),
    ("one path twice, one reason", "_subject/help.out",
     'attribution = "the first reason"',
     "'the first reason' and 'the first reason'"),
    ("one path twice, no second reason", "_subject/help.out", "",
     "'the first reason' and '(no attribution)'"),
    ("two paths", "_subject/help.err", 'attribution = "the second reason"',
     None),
)

#: The cases whose one repeated `path` is not on rows 1 and 2: (case, every
#: row's `path` in order, and the two rows the refusal names). Each row's
#: attribution is `row N`, so the two the refusal quotes are the pair's own.
#: Rows 1 and 3 hold the second number to the second row; rows 2 and 4 hold
#: the first number to the first.
_SPREAD_MOVEMENT_CASES = (
    ("rows 1 and 3", ("_subject/help.out", "_subject/help.err",
                      "_subject/help.out"), (1, 3)),
    ("rows 2 and 4", ("_subject/help.err", "_subject/help.out",
                      "_subject/help.exit", "_subject/help.out"), (2, 4)),
)


def _allow_comment_control(check: CheckRow) -> None:
    """(nnnnnn) a `#` inside an `--allow-diff` line is part of it, an empty
    or blank `attribution` is refused when the manifest is read, and a
    verdict counts permitted movements only when there are some.

    Two `[[movements]]` rows whose `path` is the same string are refused
    when the manifest is read, naming both rows by their number and both
    attributions, whether the two attributions differ, are the same, or the
    second is left out; two rows whose `path` strings differ load, which is
    the control. The refusal names the rows by their own numbers: three rows
    whose repeated `path` is on rows 1 and 3 are refused as rows 1 and 3,
    and four whose repeated `path` is on rows 2 and 4 as rows 2 and 4, each
    with those rows' attributions.

    A comment is a line whose first non-blank character is `#`, so `fixed
    in issue #42` reaches the `[ALLOWED]` line whole; a comment written
    after a bare path is part of that path, which then permits nothing —
    loud, a `[DIFF]`, never a silent permission. An `attribution` that is
    empty or blank would permit its row for no stated reason, so the
    manifest is refused; an absent one reads `(no attribution)`. A clean
    comparison reads `IDENTICAL`, the line a reader quotes, and one that
    permitted a movement says how many. A comparison of two captures that
    differ in two rows, one a `[[movements]]` row permits and one nothing
    does, lists the first once as `[ALLOWED]` and the second once as `[DIFF]`
    and ends at exit 1, whether or not git is on the machine. The same two
    captures compared under the same row and a glob, `_subject/*.out`, that
    names `help.out` too, are REFUSED, naming the moved row and both rows
    with their attributions.
    """
    label = ("nnnnnn  `--allow-diff` keeps a `#` inside a line (`fixed in "
             "issue #42`), skips a line that starts with `#`, and a comment "
             "after a bare path makes it permit nothing; a `[[movements]]` "
             "`attribution` that is empty or blank is REFUSED at load naming "
             "the path, and an absent one still loads as (no attribution); "
             "two `[[movements]]` rows whose `path` is the same string are "
             "REFUSED at load naming both rows' numbers and attributions — "
             "two attributions that differ, the same one twice, or the "
             "second left out — and three or four rows whose one repeated "
             "`path` is on rows 1 and 3, or on rows 2 and 4, are REFUSED "
             "naming those two numbers and those two rows' attributions, "
             "while two rows whose `path` strings differ load; "
             "a verdict reads `IDENTICAL` alone when no movement was "
             "permitted and names the count when one was; a comparison with "
             "one permitted row and one blocking row lists each once, the "
             "first as [ALLOWED] and the second as [DIFF], and exits 1; and "
             "the same comparison under that row and a glob that names the "
             "same moved row is REFUSED, naming the moved row and both rows "
             "with their attributions")
    with _box("golden-census-allow-comment-") as box:
        table = os.path.join(box, "allow.txt")
        pathlib.Path(table).write_text(_ALLOW_TABLE, encoding="utf-8")
        rows = read_allow(table)
        loads = {}
        for case, attribution in (("empty", 'attribution = ""'),
                                  ("blank", 'attribution = "   "'),
                                  ("absent", "")):
            path = _scratch(os.path.join(box, case),
                            manifest_text=_STUB_MANIFEST + _MOVEMENT_ROW.format(
                                attribution=attribution))
            loads[case] = _printed_refusal(
                functools.partial(load_manifest, path),
                unrefused="LOADED").replace(box, "<box>")
            if case == "absent" and loads[case] == "LOADED":
                loads[case] += " " + repr(load_manifest(path).movements[0]
                                          .attribution)
        for number, (case, second, attribution, _) in enumerate(
                _TWO_MOVEMENT_CASES, start=1):
            path = _scratch(os.path.join(box, f"pair-{number}"),
                            manifest_text=_STUB_MANIFEST
                            + _TWO_MOVEMENT_ROWS.format(
                                second=second, attribution=attribution))
            loads[case] = _printed_refusal(
                functools.partial(load_manifest, path),
                unrefused="LOADED").replace(box, "<box>")
            if loads[case] == "LOADED":
                loads[case] += f" {len(load_manifest(path).movements)} rows"
        for case, paths, _pair in _SPREAD_MOVEMENT_CASES:
            path = _scratch(os.path.join(box, case.replace(" ", "-")),
                            manifest_text=_STUB_MANIFEST + "".join(
                                f'\n[[movements]]\npath = "{one}"\n'
                                f'attribution = "row {number}"\n'
                                for number, one in enumerate(paths, start=1)))
            loads[case] = _printed_refusal(
                functools.partial(load_manifest, path),
                unrefused="LOADED").replace(box, "<box>")
        # Two captures that differ in `help.out`, which the manifest permits,
        # and in `unrunnable.skip`, which nothing does.
        mixed = os.path.join(box, "mixed")
        manifest = load_manifest(_scratch(
            mixed, manifest_text=_ONE_SKIP_MANIFEST + _MOVEMENT_ROW.format(
                attribution='attribution = "help text moved on purpose"')))
        golden, new = os.path.join(mixed, "golden"), os.path.join(mixed, "new")
        capture(manifest, golden, io.StringIO())
        shutil.copytree(golden, new)
        with open(os.path.join(new, "_subject", "help.out"), "a",
                  encoding="utf-8") as moved:
            moved.write("a line the subject never printed\n")
        pathlib.Path(os.path.join(new, "_subject", "unrunnable.skip")).write_text(
            "a different sentence entirely\n", encoding="utf-8")
        said = io.StringIO()
        mixed_code = compare(manifest, golden, new, None, said)
        mixed_rows = [one.strip() for one in said.getvalue().splitlines()]
        # The same two captures, `help.out` named by its row and by a glob.
        overlapping = load_manifest(_scratch(
            os.path.join(box, "overlap"),
            manifest_text=_ONE_SKIP_MANIFEST + _MOVEMENT_ROW.format(
                attribution='attribution = "help text moved on purpose"')
            + '\n[[movements]]\npath = "_subject/*.out"\n'
              'attribution = "every stdout moved"\n'))
        try:
            compare(overlapping, golden, new, None, io.StringIO())
            overlap = "not refused"
        except Refusal as named_twice:
            overlap = refusal_text(named_twice)
    refused = [loads["empty"], loads["blank"]]
    verdicts = (identical(0), identical(1))
    allowed_rows = [one for one in mixed_rows if one.startswith("[ALLOWED]")]
    diff_rows = [one for one in mixed_rows if one.startswith("[DIFF]")]
    check(label,
          rows == [("fixtures/results.out", "fixed in issue #42"),
                   ("fixtures/other.out   # a note", "(no attribution)"),
                   ("fixtures/bare.out", "(no attribution)")]
          and allowed_for("fixtures/other.out", rows) is None
          and all(one.startswith("REFUSED: ")
                  and "[[movements]] '_subject/help.out' has an empty or "
                      "blank `attribution`" in one
                  and "\n  next: " in one for one in refused)
          and loads["absent"] == "LOADED '(no attribution)'"
          and all(loads[case].startswith("REFUSED: ")
                  and "[[movements]] rows 1 and 2 both name "
                      f"'_subject/help.out', attributed {named}. "
                  in loads[case]
                  and "\n  next: " in loads[case]
                  for case, _, _, named in _TWO_MOVEMENT_CASES if named)
          and all(loads[case].startswith("REFUSED: ")
                  and f"[[movements]] rows {first} and {second} both name "
                      f"{paths[first - 1]!r}, attributed 'row {first}' and "
                      f"'row {second}'. " in loads[case]
                  for case, paths, (first, second) in _SPREAD_MOVEMENT_CASES)
          and loads["two paths"] == "LOADED 2 rows"
          and verdicts == ("IDENTICAL", "IDENTICAL (1 permitted movement)")
          and mixed_code == 1
          and len(allowed_rows) == 1 and "_subject/help.out" in allowed_rows[0]
          and len(diff_rows) == 1 and "_subject/unrunnable.skip" in diff_rows[0]
          and overlap.startswith(
              "REFUSED: _subject/help.out moved, and 2 rows that permit "
              "movements name it: '_subject/help.out', attributed 'help text "
              "moved on purpose' and '_subject/*.out', attributed 'every "
              "stdout moved'. ")
          and "\n  next: " in overlap,
          f"{ACTUAL}rows {rows}; the bare path with a comment permits "
          f"{allowed_for('fixtures/other.out', rows)!r}; "
          + "; ".join(f"{case} -> {_one_line(text, 160)}"
                      for case, text in loads.items())
          + f"; verdicts with 0 and 1 permitted {verdicts!r}; one permitted row "
          f"and one blocking row -> exit {mixed_code}, {allowed_rows!r} and "
          f"{diff_rows!r}; the same under that row and a glob naming "
          f"help.out -> {_one_line(overlap, 200)}")


def _shared_invocation_control(check: CheckRow) -> None:
    """(ttt) `shares_invocation_with` is DERIVED at capture, from the recorded
    argv, and only for surfaces that actually share one.

    Two manifest rows can price ONE invocation — a stdout surface and its
    `[stderr]` twin — and without this key the pair reaches a golden as two
    surfaces with identical bytes and nothing saying why, which a later reader
    counts as two independent pieces of evidence. The plant here is that pair,
    plus the two
    negatives the derivation has to get right: a surface with a DIFFERENT argv
    (no key), and a SKIPPED surface carrying the shared argv (no key either —
    it recorded no run, so it shares no invocation).

    Through `Recorder.finish` and the bytes it writes, not through the helper
    alone: what a consumer's golden carries is the JSON, and its key order
    (`argv`, `exit`, `shares_invocation_with`, `status`) is `sort_keys=True`'s,
    not this arm's opinion.
    """
    label = ("ttt  `shares_invocation_with` is derived at capture from the "
             "RECORDED argv: two surfaces of one input run from the same "
             "command line each name the other in `surfaces.json`, sorted; a "
             "surface with a different argv carries no key, and a SKIPPED "
             "surface carrying the shared argv carries none either, because "
             "it recorded no run. The plant is that four-surface input; the "
             "control is the SAME input with the twin removed, where the "
             "group falls to one and the key disappears — which is how this "
             "row is known to be able to go red")
    with _box("golden-census-shared-") as box:
        recorder = Recorder(box, Roots(root=box, work=box, clone=None), None)
        recorder.surfaces["only"] = {
            "twin-out": {"argv": ["--select", "x"], "status": "captured",
                         "exit": 0},
            "twin-err": {"argv": ["--select", "x"], "status": "captured",
                         "exit": 0},
            "alone": {"argv": ["--select", "y"], "status": "captured",
                      "exit": 0},
            "unrun": {"argv": ["--select", "x"], "status": "skipped",
                      "reason": "declared unpinned"},
            "_counts": {"nodes": 3},
        }
        planted = json.loads(json.dumps(recorder.surfaces["only"]))
        recorder.finish()
        with open(os.path.join(box, "only", SURFACES_FILE),
                  encoding="utf-8") as handle:
            text = handle.read()
        written = json.loads(text)
    keyed = {name: entry.get("shares_invocation_with")
             for name, entry in written.items() if isinstance(entry, dict)}
    # The on-disk key ORDER, read back as pairs: what a consumer's golden
    # carries is `sort_keys=True`'s order, not this arm's opinion of it.
    pairs = json.loads(text, object_pairs_hook=list)
    ordered = [key for name, entry in pairs if name == "twin-out"
               for key, _value in entry]
    # The control: the same derivation over the same input with the twin
    # REMOVED. The group falls to one and the key is gone — a derivation that
    # named something regardless could not make this row green.
    del planted["twin-err"]
    control = shared_invocations(planted)
    check(label,
          keyed == {"twin-out": ["twin-err"], "twin-err": ["twin-out"],
                    "alone": None, "unrun": None, "_counts": None}
          and ordered == ["argv", "exit", "shares_invocation_with", "status"]
          and control == {},
          f"{ACTUAL}{keyed}; the twin's keys in the file, in order: "
          f"{ordered}; the same input with the twin removed -> "
          f"{control or 'no key at all'}",
          next="`capture.shared_invocations` groups the input's `captured` "
               "entries by their recorded argv and gives every member of a "
               "group larger than one the OTHER members, sorted; "
               "`Recorder.finish` writes what it returns. A row that starts "
               "or stops sharing a command line moves the golden, which is "
               "the point.")


# ---------------------------------------------- the three disclosure lines
#
# A capture log states what was recorded row by row, and three facts are
# invisible in that list: a surface that put no byte anywhere, a surface
# whose counter did not run because its run wrote no file, and an input
# whose every surface failed. None is a refusal — each is a legitimate
# golden — and each is a thing a reader who skims the exit codes misses.

#: A subject with three switches: whether it says anything, what it exits
#: with, and whether it writes an EMPTY file at the path after `--touch`.
#: That is the whole of what the three lines are decided from, so the
#: plants below are the same script under eight manifests.
_QUIET_SUBJECT = '''\
import sys

if "--say" in sys.argv:
    print("one byte")
if "--touch" in sys.argv:
    open(sys.argv[sys.argv.index("--touch") + 1], "w").close()
sys.exit(int(sys.argv[sys.argv.index("--exit") + 1])
         if "--exit" in sys.argv else 0)
'''

#: A census with no pin and no fold: this arm is about the LOG, and a pin
#: would bring a control that names a surface these manifests do not have.
_QUIET_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the interpreter this capture was taken under"
disposition = "state"
finding     = "an interpreter change moves what a subject prints"
commands    = [["<PYTHON>", "-c", "pass"]]
'''


#: The counter of the plants whose surface name opens `counted`: it is
#: handed the written file and prints how many bytes it holds.
_QUIET_COUNTER = ("import json, sys\n"
                  "print(json.dumps({'bytes': len(open(sys.argv[1]).read())}))\n")


def _quiet_manifest(surfaces: dict[str, list[str]]) -> str:
    """A manifest over the planted subject carrying exactly these surfaces;
    a surface whose arguments spell `<WRITES>` writes `<WORK>/<name>.txt`,
    and one whose name opens `counted` is handed to `_QUIET_COUNTER`."""
    body = "".join(f"\n[surfaces.{name}]\nargs = {json.dumps(args)}\n"
                   + (f'writes = "<WORK>/{name}.txt"\n'
                      if "<WRITES>" in args else "")
                   + ('counter = ["<PYTHON>", "<HERE>/counter.py", "<WRITES>"]\n'
                      if name.startswith("counted") else "")
                   for name, args in surfaces.items())
    return _subject("quiet", '["<PYTHON>", "subject.py"]') + f'''
[inputs.only]
args     = []
surfaces = {json.dumps(list(surfaces))}
''' + body


def _quiet_capture(box: str, manifest_text: str,
                   census_text: str = _QUIET_CENSUS) -> tuple[int, str]:
    """`(the capture's exit code, its log)` for one plant."""
    _scratch(box, manifest_text=manifest_text, census_text=census_text,
             extra={"subject.py": _QUIET_SUBJECT,
                    "counter.py": _QUIET_COUNTER})
    log = io.StringIO()
    code = capture(load_manifest(os.path.join(box, "manifest.toml")),
                   os.path.join(box, "out"), log)
    return code, log.getvalue()


def _disclosure_control(check: CheckRow) -> None:
    """(eeee) the three lines a capture log owes a reader, and their
    controls."""
    label = ("eeee  a capture log discloses the three facts its rows hide: a "
             "surface that records nothing — both streams empty, no file — "
             "says so under its own row, a surface with a `counter` whose "
             "run wrote no file says under its own row that the counter did "
             "not run, and an input whose every surface exits non-zero says "
             "so after its rows. None is a refusal and none moves an exit "
             "code. The controls are the same plants with ONE byte printed, "
             "with ONE surface exiting 0 and with the counted file written, "
             "and they print no such line; nor does a surface whose one "
             "output is an EMPTY file it wrote, while one that names a file "
             "it never writes still prints the first")
    plants: dict[str, dict[str, list[str]]] = {
        "silent": {"quiet": []},
        "silent control": {"loud": ["--say"]},
        "empty file": {"empty": ["--touch", "<WRITES>"]},
        "unwritten": {"never": ["<WRITES>"]},
        "uncounted": {"counted": ["--say", "<WRITES>"]},
        "uncounted control": {"counted": ["--say", "--touch", "<WRITES>"]},
        "failing": {"one": ["--say", "--exit", "3"],
                    "two": ["--say", "--exit", "4"]},
        "failing control": {"one": ["--say", "--exit", "3"],
                            "two": ["--say"]},
    }
    logs: dict[str, tuple[int, str]] = {}
    for name, surfaces in plants.items():
        with _box("golden-census-disclose-") as box:
            # The work fold, for the plant that writes: its `writes` path
            # is under `<WORK>`, which `surfaces.json` names.
            logs[name] = _quiet_capture(
                box, _quiet_manifest(surfaces),
                _QUIET_CENSUS + (_STUB_WORK_FOLD
                                 if name in ("empty file", "unwritten",
                                             "uncounted",
                                             "uncounted control")
                                 else ""))
    silent_line, failing_line = SILENT_SURFACE.strip(), FAILING_INPUT.strip()
    uncounted_line = UNCOUNTED.strip()
    said = {name: (silent_line in text, uncounted_line in text,
                   failing_line in text)
            for name, (_code, text) in logs.items()}
    codes = {name: code for name, (code, _text) in logs.items()}
    # The exit codes stay what the subject chose: the disclosure is a line in
    # the log and never a verdict, so a capture of a subject that fails every
    # surface still records it and still exits 0.
    counted = "counts {'bytes': 0}" in logs["uncounted control"][1]
    ok = (said["silent"] == (True, False, False)
          and said["silent control"] == (False, False, False)
          and said["empty file"] == (False, False, False)
          and said["unwritten"] == (True, False, False)
          and said["uncounted"] == (False, True, False)
          and said["uncounted control"] == (False, False, False)
          and counted
          and said["failing"] == (False, False, True)
          and said["failing control"] == (False, False, False)
          and set(codes.values()) == {0}
          and "exit 3" in logs["failing"][1])
    check(label, ok,
          ACTUAL + "(records-nothing line, counter-not-run line, "
          f"every-surface-failed line) per plant — {said}; the counted "
          f"control's counter ran={counted}; capture exit codes {codes}; the "
          f"failing plant's own rows kept their codes="
          f"{'exit 3' in logs['failing'][1]}")


#: A manifest with both shapes of SKIP a capture prints: one surface declared
#: unrunnable, and one whole input pinned to a tree that cannot be cloned.
#:
#: The `git` value is a bare name and not a path, so git's own message quotes
#: no directory of this machine: the reason is written into the input's `.skip`
#: files, and an absolute path there is what the contraband scan refuses.
_SKIP_MANIFEST = _subject("quiet", '["<PYTHON>", "subject.py"]') + '''
[inputs.only]
args     = []
surfaces = ["quiet", "unrunnable"]

[inputs.pinned]
git      = "no-such-repository-anywhere"
sha      = "0000000000000000000000000000000000000000"
args     = []
surfaces = ["quiet"]

[surfaces.quiet]
args = ["--say"]

[surfaces.unrunnable]
skip = "needs a real index store; recorded as SKIP, never a pass"
'''

#: The clone fold the pinned input needs. Without it the capture refuses at
#: the contraband scan rather than reaching the lines this arm is about.
_SKIP_CENSUS = _QUIET_CENSUS + '''
[[input]]
name        = "an input's clone directory"
disposition = "fold"
kind        = "path"
source      = "clone"
placeholder = "<CLONE>"
finding     = "a clone lands under a fresh temp directory named for this run alone"
'''


#: What the planted `git` of `_clone_that_fails` prints for a clone, and the
#: step the reason of a skipped pinned input then names: the clone's.
_PLANTED_CLONE_STEP = "git clone exited 128: "

#: How the two arms' details say whether the `git` was planted.
_PLANTED_SAID = {True: "the clone failed under the planted git",
                 False: "no git here, nothing planted"}


@contextlib.contextmanager
def _clone_that_fails(box: str) -> Iterator[bool]:
    """A `git` ahead of the real one on PATH whose `clone` fails as git's own
    does for a repository that does not exist — `fatal: repository
    '<address>' does not exist`, exit 128 — and that hands every other
    command to the real one. Yields whether it was planted: on a machine with
    no `git` nothing is, and the pinned input's road is the launch refusal
    every time.

    The pinned input of `_SKIP_MANIFEST` then takes ONE road in every run: the
    clone is the step that fails, whatever this machine's network, its
    working directory or its git's version would have made of the address.
    The cache is the box's own (`_cache_in`), so no earlier run's directory
    can stand where the clone is made and turn the failure into a
    `git checkout` of a clone nobody made."""
    real = shutil.which("git")
    if real is None:
        yield False
        return
    where = os.path.join(box, "clone-fails")
    os.makedirs(where)
    _planted_script(
        os.path.join(where, "git"),
        '#!/bin/sh\nplanted() { while [ "$1" = -c ]; do shift 2; done; '
        'if [ "$1" = clone ]; then '
        'echo "fatal: repository \'$3\' does not exist" >&2; exit 128; fi; '
        '}\nplanted "$@"\n'
        f'exec {json.dumps(real)} "$@"\n')
    with _env_as({"PATH": where + os.pathsep + os.environ.get("PATH", "")}):
        yield True


#: The two shapes a capture's SKIP lines used to take, as they were printed:
#: `SKIP ` at the head of a line and `SKIPPED — ` anywhere in one. `[SKIP]`
#: does not start with `SKIP `, so the first needle cannot match the shape
#: that replaced it — which is what arm `ddddd` plants a list to show.
def _bare_shaped(lines: Iterable[str]) -> list[str]:
    """Every line of `lines` printed in one of the two bare SKIP shapes."""
    return [line for line in lines
            if line.startswith("SKIP ") or "SKIPPED — " in line]


#: What `_bare_shaped` is asked of before its zero result is believed: two
#: lines it must return and one it must not. A list of needles that matched
#: nothing is a clean result and a broken pattern spelled the same way.
_BARE_CONTROL = ("SKIPPED — x", "SKIP a/b: x", "[SKIP]  a/b: x")


def _skip_shape_control(check: CheckRow) -> None:
    """(ddddd) a capture's own SKIP lines are `[SKIP]`-shaped, like every
    other SKIP golden-census prints.

    Report hygiene asks an agent for "every disclosed `[SKIP]`, by name and
    reason". A capture printed two other shapes — `SKIP <input>/<surface>: …`
    for a declared-unrunnable surface, and `SKIPPED — <reason>` for a whole
    input whose pinned tree could not be cloned — so an agent matching the
    bracketed form read a clean run over rows that were never captured. That
    is exactly the failure the skill's "a SKIP reported as a pass is worse
    than no check at all" exists to prevent.

    ONE shape for one meaning: `[SKIP]  <what>: <why>`, the `<what>` being
    `<input>/<surface>` for a surface and `<input>` for a whole input.

    The SHAPE is the whole claim, so the shape is the whole test. What the
    reason SAYS belongs to whatever produced it — git, the network, the
    operating system — and an arm that quoted it asserted another program's
    wording: without `git` the reason is the launch refusal, which names
    `git` and not the repository, and the row went red over a line that was
    correctly shaped and correctly disclosed. This way the arm passes on a
    machine with `git` and on one without, and on the second it exercises
    the path that machine actually takes. Where a `git` is on PATH, one is
    planted ahead of it that fails the clone (`_clone_that_fails`), so the
    reason names the clone step in every run: the road is asserted by the
    step the reason names, and the words after it are the plant's.
    """
    label = ("ddddd  a capture prints its own SKIPs in the SAME bracketed "
             "shape the self-check does, `  [SKIP]  ` at the start of the "
             "line — `[SKIP]  <input>/<surface>: <why>` "
             "for a surface declared unrunnable and `[SKIP]  <input>: <why>` "
             "for a whole input whose pinned tree could not be cloned, each "
             "carrying a reason, whatever that reason turns out to say — so "
             "an agent matching `  [SKIP]  ` at the start of a line finds "
             "every one of them; and neither "
             "bare shape (`SKIP <input>/` or `SKIPPED —`) is printed anywhere "
             "in the log, which a planted list of all three shapes shows the "
             "needles can still tell apart; and over a `git` planted to fail "
             "its clone, the reason is the clone's in every run")
    with _box("golden-census-skip-shape-") as box, _cache_in(box), \
            _clone_that_fails(box) as planted:
        code, text = _quiet_capture(box, _SKIP_MANIFEST, _SKIP_CENSUS)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # The two SKIP lines are matched UNSTRIPPED: the opening — two spaces,
    # the bracket, two spaces — is the shape `core.skip_line` owns, and a
    # stripped line cannot tell two leading spaces from four. The bare-shape
    # needles below read the stripped lines.
    surface_prefix = "  [SKIP]  only/unrunnable: "
    input_prefix = "  [SKIP]  pinned: "
    surface_line = next((line for line in text.splitlines()
                         if line.startswith(surface_prefix)), "")
    input_line = next((line for line in text.splitlines()
                       if line.startswith(input_prefix)), "")
    bare = _bare_shaped(lines)
    # The zero result above, with a positive control under it: the same
    # needles over a list holding both old shapes and the one that replaced
    # them return the two and not the third.
    caught = _bare_shaped(_BARE_CONTROL)
    needles_work = caught == list(_BARE_CONTROL[:2])
    reason_given = bool(input_line.removeprefix(input_prefix).strip())
    clone_step = (not planted
                  or input_line.removeprefix(input_prefix).startswith(_PLANTED_CLONE_STEP))
    check(label,
          code == 0 and bool(surface_line) and bool(input_line) and not bare
          and needles_work and reason_given and clone_step
          and "recorded as SKIP, never a pass" in surface_line,
          f"{ACTUAL}capture exit {code}; the surface -> "
          f"{_one_line(surface_line, 95)!r}; the input -> "
          f"{_one_line(input_line, 95)!r} (carries a reason: {reason_given}; "
          f"{_PLANTED_SAID[planted]}"
          f"={clone_step}); bare-shaped line(s) {[_one_line(line, 60) for line in bare]}, and "
          f"over the planted list {list(_BARE_CONTROL)} the same needles "
          f"return {caught}",
          next="Print both from `capture` through `core.skip_line`, as "
               "`[SKIP]  <what>: <why>`. A second "
               "shape for one meaning costs an agent the run it was reading: "
               "report hygiene asks for every disclosed `[SKIP]` by name and "
               "reason, and a line that does not carry the bracket is one it "
               "will not find.")


def _environmental_skip_control(check: CheckRow) -> None:
    """(ooooo) an environmentally skipped surface records a FIXED sentence,
    and the reason goes to the log.

    Two kinds of skip, recorded two ways. A `skip = "…"` row is the author's
    own sentence, the same on every machine, and the reason IS the golden. An
    input pinned to a tree that could not be cloned is skipped for a reason
    that came from git, the network or the operating system — different text
    on every machine, committed into a `.skip` file and into `surfaces.json`,
    so two machines that BOTH skipped the input recorded two different
    goldens. Worse, an error quoting a local path put an absolute path into a
    file the contraband scan reads, and one input's clone failure refused the
    whole capture at exit 2.

    The same `_SKIP_MANIFEST` arm `ddddd` uses, read from the other side:
    `ddddd` asks what the LOG says, this asks what the DISK holds. It needs
    no `git` — with it and without it the reasons differ and the recorded
    files must not. Where a `git` is on PATH, one is planted ahead of it that
    fails the clone (`_clone_that_fails`), so the reason names the clone
    step in every run. The box's own clone cache is listed after the
    capture: the clone that failed made no tree, so the folders made for it
    are gone and the cache directory is empty.
    """
    label = ("ooooo  a surface skipped because its input's pinned tree could "
             "not be cloned records ONE fixed sentence — in its `.skip` file "
             "and in `surfaces.json`'s `reason` — while the reason itself "
             "goes to the log twice, on the input's `[SKIP]` line and on the "
             "surface's; a DECLARED skip still records the manifest's own "
             "sentence, because that one is the same on every machine and is "
             "the golden. A reason from git, the network or the operating "
             "system is a fact about this machine, and no two machines that "
             "both skipped the input may record two different goldens; the "
             "reason is the clone's in every run over a `git` planted to fail "
             "its clone; and the clone that failed leaves the cache directory "
             "empty, no folder made for it left behind, and keeps a "
             "`golden-census-trees` it did not make")
    with _box("golden-census-envskip-") as box, _cache_in(box) as cache, \
            _clone_that_fails(box) as planted:
        code, text = _quiet_capture(box, _SKIP_MANIFEST, _SKIP_CENSUS)
        left = ([os.path.relpath(os.path.join(where, name), cache)
                 for where, dirs, files in os.walk(cache)
                 for name in dirs + files]
                if os.path.isdir(cache) else None)
        # A cache whose `golden-census-trees` was there before the clone:
        # only the folder this call made goes.
        before = os.path.join(box, "kept-cache")
        os.makedirs(os.path.join(before, "golden-census-trees"))
        clone_input(before, "no-such-repository-anywhere", "0" * 40,
                    io.StringIO())
        kept = [os.path.relpath(os.path.join(where, name), before)
                for where, dirs, files in os.walk(before)
                for name in dirs + files]
        out_dir = os.path.join(box, "out")
        pinned = os.path.join(out_dir, "pinned")
        skips = sorted(name for name in os.listdir(pinned)
                       if name.endswith("." + SKIP_EXTENSION)
                       ) if os.path.isdir(pinned) else []
        recorded = {}
        for name in skips:
            with open(os.path.join(pinned, name), encoding="utf-8") as handle:
                recorded[name] = handle.read()
        marker = os.path.join(pinned, SURFACES_FILE)
        reasons = []
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8") as handle:
                reasons = sorted(
                    entry["reason"] for entry in json.load(handle).values()
                    if isinstance(entry, dict) and "reason" in entry)
        declared = ""
        declared_path = os.path.join(out_dir, "only",
                                     f"unrunnable.{SKIP_EXTENSION}")
        if os.path.isfile(declared_path):
            with open(declared_path, encoding="utf-8") as handle:
                declared = handle.read()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    input_line = next(
        (line for line in lines if line.startswith("[SKIP]  pinned: ")), "")
    surface_line = next(
        (line for line in lines
         if line.startswith("[SKIP]  pinned/quiet: ")), "")
    fixed = ENVIRONMENTAL_SKIP + "\n"
    # The reason reaches BOTH log lines and NEITHER file: the two halves are
    # each other's control, because a change that dropped the reason
    # altogether would satisfy the file half on its own.
    beyond = [line for line in (input_line, surface_line)
              if line and line.split(": ", 1)[-1].strip()
              not in ("", ENVIRONMENTAL_SKIP)]
    clone_step = (not planted or input_line.removeprefix("[SKIP]  pinned: ")
                  .startswith(_PLANTED_CLONE_STEP))
    check(label,
          code == 0 and bool(skips) and clone_step
          and all(one == fixed for one in recorded.values())
          and reasons == [ENVIRONMENTAL_SKIP] * len(reasons) and bool(reasons)
          and len(beyond) == 2
          and declared.strip() == "needs a real index store; recorded as SKIP, "
                                  "never a pass"
          and left == [] and kept == ["golden-census-trees"],
          f"{ACTUAL}capture exit {code}; {len(skips)} recorded .skip file(s) "
          f"{skips} holding {sorted(set(recorded.values()))}; "
          f"surfaces.json reason(s) {sorted(set(reasons))}; the input's log "
          f"line -> {_one_line(input_line, 90)!r}; the surface's log line -> "
          f"{_one_line(surface_line, 90)!r}; {len(beyond)} of the 2 log lines "
          f"carry text beyond the fixed sentence; "
          f"{_PLANTED_SAID[planted]}"
          f"={clone_step}; the declared skip still "
          f"records {_one_line(declared.strip(), 60)!r}; the cache directory "
          f"holds {left}, one that held `golden-census-trees` holds {kept}",
          next="Record `capture.ENVIRONMENTAL_SKIP` and nothing appended, "
               "and pass the reason to `Recorder.skip`'s `logged` argument. "
               "A golden that carries what git said on one machine is a "
               "golden no second machine can reproduce.")


def _kept_cache_control(check: CheckRow, skip: SkipRow) -> None:
    """(uuuuu) a git step that fails inside a cache directory that ALREADY
    existed names that directory in the LOG.

    The clone cache is deliberately persistent — the next capture does not
    re-clone — and deliberately trusted: a directory holding a `.git` is
    taken as a clone, whatever state that `.git` is in. A temp cleaner that
    half-removes one leaves every later capture skipping the input with a
    sentence from git that names neither the cache nor what to do, and that
    input's whole set of rows is missing from the capture.

    The reason goes to the LOG only — a `.skip` file and `surfaces.json` hold
    the fixed `ENVIRONMENTAL_SKIP` — which is what lets the sentence name an
    absolute directory at all.

    The rotted cache is a `.git` directory with nothing in it, so the first
    git a kept clone meets, `git config --get remote.origin.url`, is the
    one that fails there; every case after it fails at the checkout.

    The control is the SAME failure on a base with no cache in it: a real
    repository cloned fresh, whose checkout of a commit it does not have
    fails exactly as the rotted cache's does. It has to be a clone that
    SUCCEEDS, because a clone that fails never reaches the sentence and a
    control that cannot go red is not a control. The third case is that same
    base a second time, where the clone this arm just made IS the cache.
    The fourth is a clone of the origin's own commit, kept, with a line
    appended to its committed file: the sentence names the clone, counts
    and quotes what `git status --porcelain` lists, its leading space
    included, says to delete the directory with no condition — nothing
    else brings the input back, whoever wrote into it — and then says a
    row or a setup step that wrote those paths must write them under
    `<WORK>`, or a later capture skips the input again. The fifth is
    a clone this call makes that a hook leaves not clean: the same listing
    and no advice, because no row has run in it and the directory is this
    run's own. The sixth is a `git status` that fails: its exit and its
    stderr, and never a count of paths it did not list.

    The kept clone's first capture, at the origin's own commit, is taken,
    and its `clone:` line names the commit by its full id. An address spelled
    relative to the manifest's directory is cloned from that directory
    (`where`), never from golden-census's own working directory.

    Two half-made folders follow, at the place of the origin's own commit:
    one with a file and no `.git`, one whose `.git` is an empty file — a
    clone cut short. `git clone` refuses each in its own words, and the
    reason goes on, without the period git ended on, to name the folder and
    say to delete it. An EMPTY folder at the place of the absent commit
    takes the clone, which is then this run's own: the checkout that fails
    there is git's words alone, as on a fresh clone. An EMPTY folder where
    the clone itself fails, against an address that is no repository, is
    git's words alone too, the same words as that clone with no folder
    there: the folder did not cause it, and it is still there, still
    empty, afterwards.
    """
    label = ("uuuuu  a git step that fails inside a clone cache golden-census "
             "kept from an earlier run names that directory in the log and "
             "says to delete it, after the fault and not in front of it — "
             "while the SAME failure against a tree this run cloned itself "
             "carries no such sentence, because a directory golden-census "
             "made this run is not one to send the reader to delete; and a "
             "kept clone a run wrote into names the clone, quotes what `git "
             "status --porcelain` lists, says to delete that directory and "
             "capture again, and where a row that wrote those paths must "
             "write them — "
             "while a clone this run made that is not clean carries the "
             "listing and no advice, and a `git status` that fails says so; "
             "a clone taken logs a `clone:` line naming the commit by its "
             "full id; an address spelled relative to the manifest's "
             "directory, which is not golden-census's working directory, is "
             "cloned from there; a clone's folder there before this run "
             "with a file "
             "and no `.git` directory in it, or with an empty `.git` file, "
             "is SKIPPED in git's own words, without the period they end "
             "on, then a sentence naming that folder and saying to delete "
             "it, while an EMPTY folder there takes the clone, and a "
             "checkout that then fails is SKIPPED in git's words alone, as "
             "is a clone that fails into an EMPTY folder, word for word as "
             "with no folder there, the folder still there and still empty "
             "after it")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so every case of this arm would "
                    "fail at the launch refusal and none could be told from "
                    "another by its reason; nothing was made and nothing is "
                    "claimed.")
        return
    reasons: dict[str, str] = {}
    with _box("golden-census-kept-cache-") as box:
        # A repository to clone: the control needs a clone that SUCCEEDS and a
        # checkout that fails. Nothing here reaches a network.
        origin = os.path.join(box, "origin")
        os.makedirs(origin)
        pathlib.Path(os.path.join(origin, "a.txt")).write_text(
            "one line of a throwaway repository\n", encoding="utf-8")
        try:
            code, head, stderr = _repo_of(origin, "the origin")
        except Refusal as refused:
            # A `git` that will not START, which `shutil.which` cannot see.
            skip(label, f"{refused}; nothing was made and nothing is "
                        "claimed.")
            return
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        # A sha no repository has, so every case fails at the checkout and the
        # only difference between them is where the tree came from.
        absent = "0" * 40
        sha = launch(["git", "-C", origin, "rev-parse", "HEAD"],
                     "git rev-parse", env=git_env()).stdout.strip()
        # The folder the origin's address is kept under, and the pin, are
        # new on every run: the reasons name them as `<repo>` and `<sha>`.
        folder = repository_folder(resolved_address(origin, None))

        def masked(why: str, folder: str = folder, sha: str = sha) -> str:
            """A reason with this run's scratch paths named, not quoted —
            the commit id whole or cut: a git message quoted to the width
            can end on a prefix of it. `folder` and `sha` are the origin's
            unless the case names another repository's."""
            why = why.replace(box, "<box>").replace(folder, "<repo>")
            return re.sub(r"[0-9a-f]{7,40}",
                          lambda hit: "<sha>" if sha.startswith(hit.group())
                          else hit.group(), why)
        rotted = os.path.join(box, "rotted")
        os.makedirs(os.path.join(rotted, "golden-census-trees", folder,
                                 absent, ".git"))
        fresh = os.path.join(box, "fresh")
        os.makedirs(fresh)
        for key, base in (("a rotted cache", rotted),
                          ("a fresh clone", fresh),
                          ("that clone, kept", fresh)):
            _, why = clone_input(base, origin, absent, io.StringIO())
            reasons[key] = masked(why)
        # A kept clone at the origin's own commit, with a line appended to its
        # committed file: not clean, and the listing keeps git's leading space.
        dirty = os.path.join(box, "dirty")
        os.makedirs(dirty)
        logged = io.StringIO()
        tree, why = clone_input(dirty, origin, sha, logged)
        reasons["the clone: line"] = masked(logged.getvalue())
        # The origin by a path relative to the directory the manifest sits
        # in, `where`, which is not this process's working directory: the
        # clone runs in `where`, so the address names the origin there.
        beside = os.path.join(box, "beside")
        os.makedirs(beside)
        relative, why = clone_input(beside, os.path.relpath(origin, box), sha,
                                    io.StringIO(), where=box)
        reasons["an address relative to the manifest's directory"] = (
            "a tree taken" if relative is not None else masked(why))
        if tree is not None:
            with open(os.path.join(tree, "a.txt"), "a",
                      encoding="utf-8") as appended:
                appended.write("appended by a row\n")
            _, why = clone_input(dirty, origin, sha, io.StringIO())
        reasons["that clone, written into"] = masked(why)
        # A clone this call makes that is not clean on checkout carries the
        # listing and no advice: no row has run in it, and the directory is
        # this run's own. Nothing runs in the clone to make it so, since no
        # hook runs in a git golden-census starts: the repository itself
        # holds a file with `\r\n` line endings committed before a
        # `.gitattributes` of `* text` was, so git's check of the work tree
        # normalizes the file and finds that it differs from the blob. (Not
        # `text=auto`: git leaves a file alone whose blob in the index
        # already has a carriage return.)
        crlf = os.path.join(box, "crlf")
        os.makedirs(crlf)
        pathlib.Path(crlf, "crlf.txt").write_bytes(b"a\r\nb\r\n")
        _repo_of(crlf, "the crlf origin")
        pathlib.Path(crlf, ".gitattributes").write_text("* text\n",
                                                        encoding="utf-8")
        for words in (("add", ".gitattributes"), (*GIT_IDENTITY, *GIT_NO_MAINTENANCE,
                                      "commit", "-qm", "two")):
            launch(git_command("-C", crlf, *words), "git",
                   env=git_env("git"))
        crlf_sha = launch(["git", "-C", crlf, "rev-parse", "HEAD"],
                          "git rev-parse", env=git_env()).stdout.strip()
        unclean = os.path.join(box, "unclean")
        os.makedirs(unclean)
        _, why = clone_input(unclean, crlf, crlf_sha, io.StringIO())
        reasons["a fresh clone, not clean"] = masked(
            why, repository_folder(resolved_address(crlf, None)), crlf_sha)
        # A `git status` that fails lists nothing, so its reason is its own
        # and never a count: a `git` in front of the real one fails `status`.
        failing = os.path.join(box, "failing")
        os.makedirs(failing)
        _planted_script(
            os.path.join(failing, "git"),
            '#!/bin/sh\nfor word in "$@"; do if [ "$word" = status ]; then '
            'echo "fatal: planted" >&2; exit 128; fi; done\n'
            f'exec {json.dumps(shutil.which("git"))} "$@"\n')
        with _env_as({"PATH": failing + os.pathsep + os.environ.get("PATH", "")}):
            _, why = clone_input(failing, origin, sha, io.StringIO())
        reasons["a git status that fails"] = masked(why)
        # Two half-made folders at the place of the origin's own commit.
        for key, name, dot_git in (("a folder with no .git", "halfmade",
                                    False),
                                   ("an empty .git file", "emptied", True)):
            place = os.path.join(box, name, "golden-census-trees", folder,
                                 sha)
            os.makedirs(place)
            pathlib.Path(os.path.join(place, "a.txt")).write_text(
                "half\n", encoding="utf-8")
            if dot_git:
                pathlib.Path(os.path.join(place, ".git")).write_text(
                    "", encoding="utf-8")
            _, why = clone_input(os.path.join(box, name), origin, sha,
                                 io.StringIO())
            reasons[key] = masked(why)
        # An EMPTY folder at the place of the absent commit: the clone is
        # made into it, so the checkout that fails is this run's own tree.
        vacant = os.path.join(box, "empty", "golden-census-trees", folder,
                               absent)
        os.makedirs(vacant)
        _, why = clone_input(os.path.join(box, "empty"), origin, absent,
                             io.StringIO())
        reasons["an empty folder"] = masked(why)
        # An EMPTY folder where the clone itself fails, against an address
        # that is no repository: the failure is the clone's own, so the
        # reason is git's words alone, as it is with no folder there, and
        # the folder is still there and still empty after it.
        nowhere = os.path.join(box, "nowhere")
        unmade = os.path.join(box, "unmade", "golden-census-trees",
                              repository_folder(nowhere), sha)
        os.makedirs(unmade)
        for key, name in (("a clone that fails", "unfound"),
                          ("an empty folder, the clone failing", "unmade")):
            _, why = clone_input(os.path.join(box, name), nowhere, sha,
                                 io.StringIO())
            reasons[key] = masked(why.replace(repository_folder(nowhere),
                                              "<repo>"))
        left = (f"still there, holding {sorted(os.listdir(unmade))}"
                if os.path.isdir(unmade) else "gone")

    sentence = "golden-census kept from an earlier run"
    rotted_said = reasons["a rotted cache"]
    kept_said = reasons["that clone, kept"]
    check(label,
          sentence in rotted_said
          and "<box>/rotted/golden-census-trees/<repo>/" + absent in rotted_said
          and "Delete that directory and capture again" in rotted_said
          # The fault FIRST and the cache sentence after it: the reader gets
          # what went wrong, then what to do about it.
          and "git config" in rotted_said
          and rotted_said.index("git config") < rotted_said.index(sentence)
          and sentence not in reasons["a fresh clone"]
          and sentence in kept_said
          # The two halves are one text plus the sentence: anything else and
          # the arm would be comparing two different failures.
          and kept_said.startswith(reasons["a fresh clone"])
          and reasons["that clone, written into"] == (
              "the clone at <box>/dirty/golden-census-trees/<repo>/<sha> is not "
              "clean: `git status --porcelain` lists 1 line, ' M a.txt'. "
              "Delete that directory and capture again. If a row or a setup "
              "step of this manifest wrote those paths, it must write them "
              "under <WORK> instead, or a later capture skips this input "
              "again.")
          and reasons["a fresh clone, not clean"] == (
              "the clone at <box>/unclean/golden-census-trees/<repo>/<sha> is not "
              "clean: `git status --porcelain` lists 1 line, ' M crlf.txt'")
          and reasons["a git status that fails"] == (
              "git status --porcelain exited 128: fatal: planted")
          and reasons["the clone: line"] == (
              "  clone: <box>/origin @ <sha>, clean\n")
          and reasons["an address relative to the manifest's directory"]
          == "a tree taken"
          and all(reasons[key].startswith("git clone exited ")
                  and not reasons[key].partition("; this input's")[0]
                  .endswith((".", ":"))
                  and reasons[key].endswith(
                      f"; this input's clone folder <box>/{name}/golden-"
                      "census-trees/<repo>/<sha> was there before this run, "
                      "with no `.git` directory in it. Delete that "
                      "directory and capture again.")
                  for key, name in (("a folder with no .git", "halfmade"),
                                    ("an empty .git file", "emptied")))
          and reasons["an empty folder"] == reasons["a fresh clone"]
          and reasons["a clone that fails"].startswith("git clone exited ")
          and reasons["an empty folder, the clone failing"]
          == reasons["a clone that fails"]
          and left == "still there, holding []",
          ACTUAL + "; ".join(f"{key} -> {_one_line(why, 400)}"
                                 for key, why in reasons.items())
          + f"; the empty folder after the clone failed into it -> {left}",
          next="`run.clone_input` reads whether the cache existed ONCE, "
               "before the clone, and appends the sentence through one local "
               "function. If the fresh case now carries it, that guard has "
               "gone and golden-census is telling readers to delete a "
               "directory it made itself this run; if the kept case does not, "
               "a rotted cache is a silent skip again. A half-made folder is "
               "read at the same moment, as the folder without a `.git` "
               "directory, and a failed `git clone` goes through the same "
               "local function, which drops the period git ended on "
               "(`core.unpunctuated`); an EMPTY folder is not `found`, so a "
               "clone made into it is this run's own and a clone that fails "
               "there is git's words alone and leaves the folder as it was. "
               "The `clone:` line names HEAD by "
               "`git rev-parse HEAD`'s whole answer.")


def _address_folder_control(check: CheckRow, skip: SkipRow) -> None:
    """(bbbbbbbbb) a pinned input's cache folder is named from its address as
    git resolves it, and a kept clone is taken only from the address asked
    for.

    `run.repository_folder` once named the folder from the `git` value as
    spelled, and a kept clone was taken on its `checkout` and a HEAD that
    began with the pin alone. Two manifests in two directories that both pin
    `../lib` shared one folder, and so did `…/alice/tool-x` and
    `…/alice-tool/x`: the second capture recorded the first repository's
    tree under its own address with `clean` in the log, at exit 0.

    Repository A has one commit; repository B is a clone of A with one more,
    so both hold A's commit, the pin. First two manifest directories,
    `p1/m` and `p2/m`, beside `p1/lib` (a clone of A) and `p2/lib` (a clone
    of B): each asks `clone_input` for `../lib` at A's commit under ONE
    cache, and both are taken, under two folders, each `clone:` line reading
    the address as spelled and each tree's `remote.origin.url` naming its own
    `lib`. Then, under a second cache, `alice/tool-x` (a clone of A) and
    `alice-tool/x` (a clone of B), whose absolute addresses differ only in a
    character the folder name replaces: the first is taken, the second is
    SKIPPED with the sentence naming the folder and both addresses, and
    nothing is deleted. A SKIP where `git` is not on PATH.
    """
    label = ("bbbbbbbbb  a pinned input's cache folder is named from its "
             "address as git resolves it, so two manifests that pin one "
             "relative path from two directories get two folders, each with "
             "its own clone: line; and a kept clone whose remote.origin.url "
             "is not the address asked for is never taken, the input skipped "
             "naming the folder and both addresses, where two absolute "
             "addresses that differ only in characters the folder name "
             "replaces meet one folder")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no repository can be made or "
                    "cloned; nothing was made and nothing is claimed.")
        return

    def step(what: str, *words: str) -> tuple[int, str]:
        proc = launch(git_command(*words), what, env=git_env(what))
        return proc.returncode, proc.stderr.strip()[:DIFFERENCE]

    with _box("golden-census-address-") as box:
        first = os.path.join(box, "a")
        os.makedirs(first)
        pathlib.Path(first, "a.txt").write_text("one line\n", encoding="utf-8")
        code, head, stderr, sha = _committed(first, "A")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        second = os.path.join(box, "b")
        code, stderr = step("git clone", "clone", "--quiet", first, second)
        if code == 0:
            pathlib.Path(second, "b.txt").write_text("two\n", encoding="utf-8")
            code, stderr = step("git add", "-C", second, "add", "-A")
        if code == 0:
            code, stderr = step("git commit", "-C", second, *GIT_IDENTITY,
                                *GIT_NO_MAINTENANCE, "commit", "-qm", "B")
        if code != 0:
            skip(label, f"a git that made the second repository exited "
                        f"{code}: {stderr}; nothing was made and nothing is "
                        "claimed.")
            return
        for parent, source in (("p1", first), ("p2", second),
                               ("alice", first), ("alice-tool", second)):
            os.makedirs(os.path.join(box, parent, "m" if parent[0] == "p"
                                     else ""), exist_ok=True)
            code, stderr = step(
                "git clone", "clone", "--quiet", source,
                os.path.join(box, parent, "lib" if parent[0] == "p"
                             else "tool-x" if parent == "alice" else "x"))
            if code != 0:
                skip(label, f"`git clone` exited {code}: {stderr}; nothing "
                            "was made and nothing is claimed.")
                return
        taken: list[tuple[str | None, str, str, str]] = []
        cache = os.path.join(box, "cache-one")
        for parent in ("p1", "p2"):
            log = io.StringIO()
            tree, why = clone_input(cache, "../lib", sha, log,
                                    where=os.path.join(box, parent, "m"))
            origin = ""
            if tree is not None:
                proc = launch(git_command("-C", tree, "config", "--get",
                                          "remote.origin.url"),
                              "git config", env=git_env("git config"))
                origin = proc.stdout.strip()
            taken.append((tree, why, log.getvalue(), origin))
        cache = os.path.join(box, "cache-two")
        tool = os.path.join(box, "alice", "tool-x")
        other = os.path.join(box, "alice-tool", "x")
        kept, kept_why = clone_input(cache, tool, sha, io.StringIO())
        folder = (os.path.basename(os.path.dirname(kept)) if kept else "-")
        before = sorted(os.listdir(kept)) if kept else []
        wrong, wrong_why = clone_input(cache, other, sha, io.StringIO())
        after = sorted(os.listdir(kept)) if kept else []

    def masked(text: str) -> str:
        return (text.replace(os.path.realpath(box), "<box>")
                .replace(box, "<box>").replace(folder, "<repo>")
                .replace(sha, "<sha>"))
    (tree_one, why_one, log_one, url_one), (tree_two, why_two, log_two,
                                            url_two) = taken
    wanted = f"  clone: ../lib @ {sha}, clean\n"
    wanted_skip = (
        "the clone kept at <box>/cache-two/golden-census-trees/<repo>/<sha> "
        "was cloned from '<box>/alice/tool-x', not from "
        "'<box>/alice-tool/x': both addresses name this one cache folder. "
        "Delete that directory and capture again, or give one of the two "
        "repositories an address whose letters and digits differ from the "
        "other's.")
    said = masked(wrong_why)
    check(label,
          tree_one is not None and tree_two is not None
          and os.path.dirname(tree_one) != os.path.dirname(tree_two)
          and log_one == wanted and log_two == wanted
          and url_one.endswith(os.sep.join(("", "p1", "lib")))
          and url_two.endswith(os.sep.join(("", "p2", "lib")))
          and kept is not None and not kept_why
          and wrong is None and said == wanted_skip
          and after == before and bool(before),
          f"{ACTUAL}`../lib` from p1/m -> {tree_one!r} {why_one!r} "
          f"{log_one!r} {url_one!r}; from p2/m -> {tree_two!r} {why_two!r} "
          f"{log_two!r} {url_two!r}; the first absolute address -> "
          f"{kept!r} {masked(kept_why)!r}; the second -> {wrong!r} "
          f"{_one_line(said, 500)!r}; the kept clone holds {before} before "
          f"and {after} after",
          next="`run.clone_input` hands `git clone` `resolved_address`, "
               "names the folder from it, and asks the "
               "kept clone `git config --get remote.origin.url` before its "
               "checkout; an answer that is not the resolved address is "
               "that input SKIPPED, naming the folder and both addresses, "
               "and nothing is deleted.")


# ---------------------------------------- the clone cache's home (jjjjjjj)

#: Arm `jjjjjjj`'s manifest: the stub with one input that pins nothing, `local`,
#: ahead of the stub's own, pinned to `{git}` at `{sha}` or to nothing where
#: both are empty.
_CACHE_HOME_MANIFEST = _STUB_MANIFEST.replace(
    '[inputs._subject]\nargs     = []\nsurfaces = ["help"]\n',
    '[inputs.local]\nargs     = []\nsurfaces = ["help"]\n\n'
    '[inputs._subject]\nargs     = []\nsurfaces = ["help"]\n{pin}')

#: The repository-location variables arm `jjjjjjj` hands the process, each
#: with the path it takes in the upper repository `{upper}`.
_LOCATIONS = {
    "GIT_DIR": "{upper}/.git",
    "GIT_WORK_TREE": "{upper}",
    "GIT_OBJECT_DIRECTORY": "{upper}/.git/objects",
    "GIT_COMMON_DIR": "{upper}/.git",
}

#: A `git` that notes which of the `_LOCATIONS` variables each run it is
#: given meets, and the value of `GIT_TERMINAL_PROMPT` it meets, one line a
#: run and none for the question that asks git which variables name a
#: repository, and hands the run on to the real `git`.
_NOTING_GIT = """\
#!/bin/sh
if [ "$1 $2" != "rev-parse --local-env-vars" ]; then
  seen=
  for name in {names}; do
    if printenv "$name" > /dev/null; then seen="$seen $name"; fi
  done
  echo "seen:$seen prompt:${{GIT_TERMINAL_PROMPT-unset}}" >> {notes}
fi
exec {real} "$@"
"""

#: Arm `jjjjjjj`'s manifest of two inputs that pin one repository at one
#: commit, so a place that enters both enters one clone.
_TWIN_MANIFEST = _STUB_MANIFEST.replace(
    '[inputs._subject]\nargs     = []\nsurfaces = ["help"]\n',
    '[inputs.first]\nargs     = []\nsurfaces = ["help"]\n{pin}\n'
    '[inputs.second]\nargs     = []\nsurfaces = ["help"]\n{pin}')

#: The rule that names a repository's folder in the cache, by examples spelled
#: here and not computed: an address, and the folder it is kept under.
_REPOSITORY_FOLDERS = (
    ("https://github.com/o/r.git", "https---github.com-o-r.git"),
    ("git@host:o/r_1", "git-host-o-r_1"),
    ("/a b/é", "-a-b--"),
    ("a.b_c-d", "a.b_c-d"),
)


def _cache_home_control(check: CheckRow, skip: SkipRow) -> None:
    """(jjjjjjj) the clone cache lives where `core.Platform.cache_dir` says,
    each clone at `<cache>/golden-census-trees/<repository>/<sha>`, and no
    git step in it reaches a repository above it.

    Every case runs under a temp root in the box and under `_cache_in`,
    the cache inside the work tree of an UPPER repository holding the pin,
    whose HEAD, branch and index the arm compares. In order: a first clone
    through `run.place` under a private temp root and an inherited
    `GIT_INDEX_FILE` naming the upper index; the same clone taken again;
    the second repository's clone made under an inherited
    `GIT_CONFIG_PARAMETERS` that names the remote, which the clone keeps;
    the clone hollowed, its files removed and folders kept. Then a clone
    made with `GIT_DIR`, `GIT_WORK_TREE`,
    `GIT_OBJECT_DIRECTORY` and `GIT_COMMON_DIR` set to the upper
    repository's paths, behind a `git` that notes which of the four each
    run is handed, under a caller's own `GIT_TERMINAL_PROMPT=1`: the clone
    is taken, none of the four runs was handed one, each was handed
    `GIT_TERMINAL_PROMPT=0`, and the upper repository's
    `.git` holds the same bytes. Then the
    layout, under a cache of its own: two
    manifests whose input has one name and pins two different repositories,
    and a third pinning the first one's repository at its commit again, so
    the cache holds two clones and nothing beside the `golden-census-trees`
    folder, the probe of `core.require_cache_dir` removed; `clone_input`
    twice over one pin, handed a `before_clone` that notes each call, which
    is called for the first and not for the second; a place that enters two
    inputs pinning one repository at one commit, whose `clones` lists the
    one clone once. The rule that
    names a repository's folder, by four addresses spelled in this module.
    Then the question the cache is asked, by `cli.main`: with a FILE where
    the cache directory goes, `census` over a manifest whose `vary` control
    clones and `capture` of both its inputs are refused at exit 2 and
    `census` with no such control and `capture --input local` over the
    input that pins nothing are not; the same `census` over a manifest
    without a pin is not; and `census` and `capture --input local`, under a cache
    directory that can be written and is not there, make no folder.
    """
    label = ("jjjjjjj  a pinned input's clone is made at `<cache>/golden-"
             "census-trees/<repository>/<sha>` under the cache directory "
             "`Platform.cache_dir` names, leaving nothing under the temp "
             "root, and is taken again on the next run; two manifests that "
             "name one input and pin two repositories each get a clone and "
             "neither meets the other's, two pinning one repository at one "
             "commit share one, and the cache holds nothing beside "
             "`golden-census-trees`; a repository's folder is its address "
             "with every character that is not an ASCII letter, a digit, "
             "`.`, `_` or `-` made `-`; a hollowed cache is a SKIP that "
             "names the folder and says to delete it, while a repository "
             "above the cache keeps its HEAD, its branch and its index, "
             "under an inherited GIT_INDEX_FILE too, and its whole `.git` "
             "while GIT_DIR, GIT_WORK_TREE, GIT_OBJECT_DIRECTORY and "
             "GIT_COMMON_DIR name it, none of which reaches any of the four "
             "runs of git a clone takes, each of which is handed "
             "GIT_TERMINAL_PROMPT set to 0 where the caller set it to 1, "
             "while configuration "
             "git takes from the environment reaches every step, so a clone "
             "made under `clone.defaultRemoteName=kept` names its one remote "
             "`kept`; `run.clone_input` calls its `before_clone` for the clone "
             "it makes and never for the tree it finds, and a place that "
             "enters two inputs pinning one repository at one commit lists "
             "their one clone once in `Place.clones`; a cache "
             "directory that cannot be written is refused at exit 2, naming "
             "it, right before the first clone, so that a `vary` control "
             "that clones is refused naming the control and the run and a "
             "`capture` of every input is refused after the rows of the "
             "input that pins nothing, its block opening `ran:`, with "
             "`--out` not made, while a `census` with no `vary` control over "
             "the pin, "
             "`capture --input` over the input that pins nothing and the "
             "same command over a manifest that pins no input are not "
             "refused, and under a cache that can be written and is not "
             "there they make no folder")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no clone can be made and no "
                    "case of this arm can be told from another; nothing was "
                    "made and nothing is claimed.")
        return
    found: dict[str, object] = {}
    with _box("golden-census-cache-home-") as box:
        origins = []
        for name, text in (("origin", "one line of a throwaway repository\n"),
                           ("second", "a line of a second repository\n")):
            repository = os.path.join(box, name)
            os.makedirs(repository)
            pathlib.Path(os.path.join(repository, "a.txt")).write_text(
                text, encoding="utf-8")
            code, head, stderr = _repo_of(repository, f"the {name}")
            if code != 0:
                skip(label, f"`{head}` exited {code}: "
                            f"{stderr[:DIFFERENCE]}; nothing was made and "
                            "nothing is claimed.")
                return
            origins.append((repository, launch(
                ["git", "-C", repository, "rev-parse", "HEAD"],
                "git rev-parse").stdout.strip()))
        (origin, sha), (second, second_sha) = origins
        upper = os.path.join(box, "upper")
        for argv in (["git", "clone", "--quiet", origin, upper],
                     ["git", "-C", upper, *GIT_IDENTITY, *GIT_NO_MAINTENANCE,
                      "commit", "-qm", "upper", "--allow-empty"]):
            proc = launch(git_command(*argv[1:]), " ".join(argv[:2]), env=git_env())
            if proc.returncode != 0:
                skip(label, f"`{' '.join(argv[:4])}` exited "
                            f"{proc.returncode}: {proc.stderr[:DIFFERENCE]}; "
                            "nothing is claimed.")
                return
        index = os.path.join(upper, ".git", "index")

        def upper_state() -> tuple[str, str, bytes]:
            """The upper repository's HEAD, its branch and its index."""
            return (launch(["git", "-C", upper, "rev-parse", "HEAD"],
                           "git rev-parse", env=git_env()).stdout.strip(),
                    launch(["git", "-C", upper, "branch", "--show-current"],
                           "git branch", env=git_env()).stdout.strip(),
                    pathlib.Path(index).read_bytes())
        before = upper_state()

        def pinned(where: str, git: str, commit: str,
                   census: str = _STUB_CENSUS) -> str:
            """A manifest under `<box>/<where>`: `local`, which pins
            nothing, and the stub's input pinned to `git` at `commit`."""
            return _scratch(
                os.path.join(box, where), census_text=census,
                manifest_text=_CACHE_HOME_MANIFEST.format(
                    pin=f'git = "{git}"\nsha = "{commit}"\n'))
        manifest = load_manifest(pinned("subject", origin, sha))
        again = load_manifest(pinned("again", origin, sha))
        other = load_manifest(pinned("other", second, second_sha))
        # No `vary` control over the pin, so a `census` of it clones nothing.
        plain = pinned("plain", origin, sha, _QUIET_CENSUS)
        bare = _scratch(
            os.path.join(box, "bare"),
            manifest_text=_CACHE_HOME_MANIFEST.format(pin=""))

        def entered(of: Manifest = manifest) -> tuple[str | None, str | None]:
            """The clone `run.place` hands the pinned input of `of`, and its
            SKIP reason."""
            subject_input = of.input_named("_subject")
            assert subject_input is not None
            with place(of, "golden-census-cache-home-", io.StringIO(),
                       rows=[(subject_input, of.surfaces["help"])]) as where:
                got = where.enter(subject_input)
            return got.roots.clone, got.unavailable

        def read(clone: str | None) -> str:
            """The committed file of a clone, or why it cannot be read."""
            try:
                return pathlib.Path(clone or "", "a.txt").read_text(
                    encoding="utf-8")
            except OSError as blocked:
                return f"{type(blocked).__name__}"

        def capturing(plan: str, out: str, *more: str) -> tuple[int, str]:
            """`capture` of `plan` into `<box>/<out>`, as `cli.main` runs it."""
            return _quietly(main, ["capture", "--manifest", plan, "--out",
                                   os.path.join(box, out), *more])
        # Every case runs under a temp root of the box's own, so a clone
        # that goes anywhere but the cache directory still stays in the box.
        scratch = os.path.join(box, "tmp")
        os.makedirs(scratch)
        with _tmpdir_as(scratch), _cache_in(upper) as cache:
            clone = os.path.join(cache, "golden-census-trees",
                                 repository_folder(
                                     resolved_address(origin, None)), sha)
            with _env_as({"GIT_INDEX_FILE": index}):
                found["first"], found["left"] = _made_under(temp_base(),
                                                            entered)
            found["again"] = entered()
            for folder, _dirs, files in os.walk(clone):
                for name in files:
                    os.unlink(os.path.join(folder, name))
            found["hollowed"] = entered()
            found["upper"] = upper_state() == before
        # The variables that name a repository, all four set to the upper
        # repository's paths: none reaches any of the runs of git a clone
        # takes, and the upper repository's `.git` is as it was. A step that
        # names its own `--git-dir` is not moved by `GIT_DIR`, so the runs
        # are asked what they were handed. The caller's own
        # `GIT_TERMINAL_PROMPT=1` is planted beside them: each run is handed
        # `0` all the same.
        noting = os.path.join(box, "noting")
        os.makedirs(noting)
        notes = os.path.join(box, "notes.txt")
        _planted_script(os.path.join(noting, "git"), _NOTING_GIT.format(
            names=" ".join(_LOCATIONS), notes=json.dumps(notes),
            real=json.dumps(shutil.which("git"))))
        upper_git = _tree_bytes(os.path.join(upper, ".git"))
        with _tmpdir_as(scratch), \
                _cache_in(os.path.join(box, "located")) as located, \
                _env_as({**{name: where.format(upper=upper)
                            for name, where in _LOCATIONS.items()},
                         "GIT_TERMINAL_PROMPT": "1"}), \
                _env_as({"PATH": noting + os.pathsep
                         + os.environ.get("PATH", "")}):
            there, _why = clone_input(located, origin, sha, io.StringIO())
        found["named by four variables, taken"] = there is not None
        found["named by four variables, seen by"] = (
            pathlib.Path(notes).read_text(encoding="utf-8").splitlines()
            if os.path.isfile(notes) else None)
        found["upper .git, named by four variables"] = (
            upper_git is not None
            and _tree_bytes(os.path.join(upper, ".git")) == upper_git)
        # The layout: three manifests, one input name, a cache of their own.
        with _tmpdir_as(scratch), _cache_in(os.path.join(box, "shared")) as kept:
            one = entered()
            # Configuration git takes from the environment reaches the
            # clone: under `clone.defaultRemoteName=kept` the new clone's
            # one remote is named `kept`, where a dropped variable leaves
            # git's own `origin`.
            with _env_as({"GIT_CONFIG_PARAMETERS":
                          "'clone.defaultRemoteName=kept'"}):
                two = entered(other)
            found["remote"] = launch(["git", "-C", two[0] or box, "remote"],
                                     "git remote", env=git_env()).stdout.split()
            found["one repository"], found["the other"] = one, two
            found["one repository, again"] = entered()
            found["the same pin"] = entered(again)
            trees = os.path.join(kept, "golden-census-trees")
            # Asked only of what is there: a layout that moved is this row's
            # red, named in its detail, and not a raise out of the arm.
            found["folders"] = (
                sorted(os.listdir(kept)) if os.path.isdir(kept) else [],
                len(os.listdir(trees)) if os.path.isdir(trees) else 0)
            found["lines"] = (read(one[0]), read(two[0]))
        # The question `before_clone` carries is asked for a clone the call
        # makes and not for a tree it finds, and two inputs that pin one
        # repository at one commit enter one clone, which the place lists
        # once.
        with _tmpdir_as(scratch), _cache_in(os.path.join(box, "twin-cache")):
            noted: list[str] = []
            for taking in ("made", "found"):
                clone_input(os.path.join(box, "twin-clones"), origin, sha,
                            io.StringIO(),
                            before_clone=functools.partial(noted.append,
                                                           taking))
            found["before_clone, called for"] = noted
            twin = load_manifest(_scratch(
                os.path.join(box, "twin"), census_text=_QUIET_CENSUS,
                manifest_text=_TWIN_MANIFEST.format(
                    pin=f'git = "{origin}"\nsha = "{sha}"\n')))
            with place(twin, "golden-census-cache-home-", io.StringIO(),
                       rows=[(each, twin.surfaces["help"])
                             for each in twin.inputs]) as where:
                taken = [where.enter(each).roots.clone
                         for each in twin.inputs]
                found["twin inputs, one clone, listed"] = (
                    taken[0] is not None and taken[0] == taken[1],
                    len(where.clones))
        found["rule"] = [repository_folder(address)
                         for address, _folder in _REPOSITORY_FOLDERS]
        # The cache directory's question. A FILE where the cache directory
        # goes cannot be written in; a relative HOME is no home.
        with _tmpdir_as(scratch), \
                _cache_in(os.path.join(box, "blocked")) as blocked:
            os.makedirs(os.path.dirname(blocked), exist_ok=True)
            pathlib.Path(blocked).write_text("", encoding="utf-8")
            found["blocked"] = _quietly(
                main, ["census", "--manifest", manifest.path])
            found["no control"] = _quietly(main, ["census", "--manifest",
                                                  plain])
            found["bare"] = _quietly(main, ["census", "--manifest", bare])
            found["local"] = capturing(plain, "out-local", "--input",
                                       "local")
            found["out, local"] = os.path.isdir(
                os.path.join(box, "out-local"))
            found["every input"] = capturing(plain, "out-every")
            found["out, every input"] = os.path.lexists(
                os.path.join(box, "out-every"))
        with _tmpdir_as(scratch), \
                _cache_in(os.path.join(box, "unasked")) as unasked:
            asked = (_quietly(main, ["census", "--manifest", plain]),
                     capturing(plain, "out-unasked", "--input", "local"))
            found["unasked"] = (asked[0][0], asked[1][0],
                                os.path.lexists(unasked))
    kept_in = (f"; this input's clone was taken from a cache golden-census "
               f"kept from an earlier run: {clone}. Delete that directory "
               "and capture again.")
    hollowed = found["hollowed"]
    refused = found["blocked"]
    unpinned = found["bare"]
    no_control = found["no control"]
    local = found["local"]
    every = found["every input"]
    assert isinstance(hollowed, tuple) and isinstance(refused, tuple)
    assert isinstance(unpinned, tuple)
    assert isinstance(no_control, tuple) and isinstance(local, tuple)
    assert isinstance(every, tuple)
    reason = hollowed[1] or ""

    def refusal_of(ran: tuple[int, str]) -> str:
        """The first REFUSED line alone, its margin dropped: the line above
        it names a process group, which is a new number on every run."""
        return next((line.strip() for line in ran[1].splitlines()
                     if line.strip().startswith("REFUSED: ")),
                    "(no REFUSED line)")

    said = refusal_of(refused)
    said_every = refusal_of(every)
    cannot = ("golden-census could not write in its cache directory "
              f"{blocked!r}: ")
    controlled = ("REFUSED: census pin 'terminal width': the `vary` control "
                  "on '_subject/help', the first run under the pin: ")
    folders = found["folders"]
    assert isinstance(folders, tuple)
    asked_not = found["unasked"]
    check(label,
          found["first"] == (clone, None) and found["left"] == []
          and found["again"] == (clone, None)
          and hollowed[0] is None and reason.startswith("git config ")
          and reason.endswith(kept_in)
          and found["upper"] is True
          and one[0] is not None and two[0] is not None
          and one[1] is None and two[1] is None and one[0] != two[0]
          and found["remote"] == ["kept"]
          and found["named by four variables, taken"] is True
          and found["named by four variables, seen by"]
          == ["seen: prompt:0"] * 4
          and found["upper .git, named by four variables"] is True
          and found["before_clone, called for"] == ["made"]
          and found["twin inputs, one clone, listed"] == (True, 1)
          and found["one repository, again"] == one
          and found["the same pin"] == one
          and found["lines"] == ("one line of a throwaway repository\n",
                                 "a line of a second repository\n")
          and folders == (["golden-census-trees"], 2)
          and found["rule"] == [folder for _address, folder
                                in _REPOSITORY_FOLDERS]
          and refused[0] == 2 and refused[1].count(controlled + cannot) == 1
          and no_control[0] == 0 and "REFUSED" not in no_control[1]
          and local[0] == 0 and "REFUSED" not in local[1]
          and found["out, local"] is True
          and every[0] == 2 and said_every.startswith("REFUSED: " + cannot)
          and "\n  input local\n    help: exit 0\n  input _subject\n"
          in every[1]
          and "\n  ran: <PYTHON> stub.py --help\n" in every[1]
          and found["out, every input"] is False
          and unpinned[0] == 0 and "cache directory" not in unpinned[1]
          and "REFUSED" not in unpinned[1]
          and asked_not == (0, 0, False),
          # The pin is masked: a commit's hash is new on every run.
          ACTUAL + "; ".join(
              f"{case} -> "
              + _one_line(str(value)
                          .replace(repository_folder(
                              resolved_address(origin, None)), "<repo>")
                          .replace(repository_folder(
                              resolved_address(second, None)),
                              "<second repo>")
                          .replace(box, "<box>").replace(sha, "<sha>")
                          .replace(second_sha, "<second sha>"), 150)
              for case, value in found.items()
              if case not in ("blocked", "bare", "no control",
                              "local", "out, local", "every input",
                              "out, every input", "unasked"))
          + f"; the census with a vary control, blocked -> exit "
          f"{refused[0]}, "
          + _one_line(said.replace(box, "<box>"), 220)
          + f"; the census with no vary control, blocked -> exit "
          f"{no_control[0]}, refused={'REFUSED' in no_control[1]}; capture "
          f"--input local, blocked -> exit {local[0]}, refused="
          f"{'REFUSED' in local[1]}, `--out` made={found['out, local']}; "
          "capture of every input, blocked -> "
          f"exit {every[0]}, "
          + _one_line(said_every.replace(box, "<box>"), 200)
          + f", `--out` made={found['out, every input']}; the census "
          f"without a pin -> exit {unpinned[0]}, refused="
          f"{'REFUSED' in unpinned[1]}, says the cache directory="
          f"{'cache directory' in unpinned[1]}; under a cache that can be "
          f"written, census and capture --input local -> exit codes "
          f"{asked_not[:2] if isinstance(asked_not, tuple) else asked_not}"
          ", cache directory made="
          f"{asked_not[2] if isinstance(asked_not, tuple) else asked_not}",
          next="`run.place` hands `Platform.cache_dir` to every `Place`, "
               "whose `_ask_cache` calls `core.require_cache_dir` as "
               "`run.clone_input`'s `before_clone`, right before the first "
               "clone a run makes; `run.clone_input` keeps a clone at "
               "`<cache>/golden-census-trees/<repository>/<sha>` with "
               "`run.repository_folder`, and runs every git "
               "through `run._in_cache`; and `controls._vary_control` and "
               "`capture._record_everything` name the control and the run, "
               "or the subject that ran, in front of the place's refusal. "
               "The case that moved names which.")


# ------------------------------ a pinned input's four gits, planted (yyyyyy)

#: The pin of every state of arm `yyyyyy`, and what its planted git prints
#: for `rev-parse HEAD` when nothing is planted over that run.
_PLANTED_PIN = "abc1234"

#: A `git` that starts no other program: the interpreter of this run reads it
#: by its first line, so it runs where `PATH` holds no `git`, no `sh` and no
#: `mkdir`. It answers the runs of `run.clone_input` — a kept clone's
#: `config --get remote.origin.url` with the address the arm asks for — and
#: ONE of them —
#: `sub` — prints what the state plants and ends as the state says. The
#: question `run._in_cache` asks in front of each, which variables git names
#: as those of one repository, it answers with exit 0 and no name.
_PLANTED_GIT = """\
#!{python}
import os
import signal
import sys

words = sys.argv[1:]
while len(words) >= 2 and words[0] in ("-C", "-c", "--git-dir",
                                      "--work-tree"):
    words = words[2:]
if words[:2] == ["rev-parse", "--local-env-vars"]:
    sys.exit(0)
sub = words[0] if words else ""
if sub == {sub!r}:
    sys.stdout.write({printed!r})
    sys.stderr.write({said!r})
    sys.stdout.flush()
    sys.stderr.flush()
    {ends}
if sub == "clone":
    os.makedirs(os.path.join(words[-1], ".git"))
elif sub == "rev-parse":
    sys.stdout.write({pin!r} + "\\n")
elif sub == "config":
    sys.stdout.write("anywhere\\n")
sys.exit(0)
"""

_EXITS = "sys.exit({code})"
_SIGNALS_ITSELF = "os.kill(os.getpid(), signal.SIGTERM)"

#: What a state's detail opens with when the clone was TAKEN, in front of the
#: line `clone_input` wrote to the log.
_TAKEN = "the clone was taken, and the log says "

#: Standard error longer than the wide quote, on one line.
_PLANTED_LONG = "fatal: " + "x" * (2 * QUOTE)

#: Standard error that holds a space where the wide quote cuts it, with more
#: text after: the quote ends on its last character that shows.
_PLANTED_SPACED = "x" * (QUOTE - 1) + " more text after the cut"

_KEPT_SENTENCE = ("; this input's clone was taken from a cache golden-census "
                  "kept from an earlier run: <box>/{state}/golden-census-"
                  f"trees/anywhere/{_PLANTED_PIN}. Delete that directory and "
                  "capture again.")

#: Each state: its directory, what the detail calls it, the run planted over,
#: standard output, standard error, how that git ends, and what
#: `clone_input` must hand back for it, whole.
_PLANTED_STATES: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("control", "the control, a git that answers",
     "", "", "", "",
     f"{_TAKEN}'clone: anywhere @ {_PLANTED_PIN}, clean'"),
    ("clone", "a `git clone` that exits 128",
     "clone", "", "fatal: planted clone\n", _EXITS.format(code=128),
     "git clone exited 128: fatal: planted clone"),
    ("clonesignal", "a `git clone` that a signal ends",
     "clone", "", "fatal: planted clone signal\n", _SIGNALS_ITSELF,
     f"git clone was ended by signal {int(signal.SIGTERM)}: "
     "fatal: planted clone signal"),
    ("checkoutsignal", "a `git checkout` that a signal ends",
     "checkout", "", "fatal: planted checkout signal\n", _SIGNALS_ITSELF,
     f"git checkout {_PLANTED_PIN} was ended by signal "
     f"{int(signal.SIGTERM)}: fatal: planted checkout signal"),
    ("checkout", "a `git checkout` that exits 3 and prints no text",
     "checkout", "", " \n", _EXITS.format(code=3),
     f"git checkout {_PLANTED_PIN} exited 3, git printed no text on stderr"),
    ("blank", "a `git checkout` that prints its text after two blank lines",
     "checkout", "", "\n\n  fatal: after two blank lines  \n",
     _EXITS.format(code=128),
     f"git checkout {_PLANTED_PIN} exited 128: fatal: after two blank lines"),
    ("lines", "a `git checkout` that exits 1 and prints two lines",
     "checkout", "", "error: planted checkout\nhint: a second line\n",
     _EXITS.format(code=1),
     f"git checkout {_PLANTED_PIN} exited 1: error: planted checkout\n"
     "hint: a second line"),
    ("cut", "a `git checkout` that prints more than the wide quote holds",
     "checkout", "", _PLANTED_LONG + "\n", _EXITS.format(code=1),
     f"git checkout {_PLANTED_PIN} exited 1: " + _PLANTED_LONG[:QUOTE]
     + " …"),
    ("space", "a `git checkout` whose text the wide quote cuts after a space",
     "checkout", "", _PLANTED_SPACED + "\n", _EXITS.format(code=1),
     f"git checkout {_PLANTED_PIN} exited 1: " + _PLANTED_SPACED[:QUOTE - 1]
     + " …"),
    ("signal", "a `git status` that a signal ends",
     "status", "", "fatal: planted signal\n", _SIGNALS_ITSELF,
     f"git status --porcelain was ended by signal {int(signal.SIGTERM)}: "
     "fatal: planted signal"),
    ("listing", "a `git status` that exits 3 and lists a path",
     "status", "?? planted.txt\n", "fatal: planted status\n",
     _EXITS.format(code=3),
     "git status --porcelain exited 3: fatal: planted status"),
    ("revparse", "a `git rev-parse` that exits 4 and prints the pin",
     "rev-parse", _PLANTED_PIN + "\n", "fatal: planted rev-parse\n",
     _EXITS.format(code=4),
     "git rev-parse HEAD exited 4: fatal: planted rev-parse"),
    ("silent", "a `git rev-parse` that exits 4 and prints nothing",
     "rev-parse", "", "", _EXITS.format(code=4),
     "git rev-parse HEAD exited 4, git printed no text on stderr"),
)

#: The state whose base is cloned a SECOND time, where the clone the first
#: call made is a cache kept from an earlier run.
_KEPT_STATE = "revparse"


def _planted_clone(box: str, state: str) -> str:
    """What `clone_input` hands back under `<box>/<state>`, as ONE text: the
    reason, or `_TAKEN` and the line it wrote to the log. `<box>` stands for
    the scratch directory."""
    log = io.StringIO()
    tree, why = clone_input(os.path.join(box, state), "anywhere",
                            _PLANTED_PIN, log)
    if tree is None:
        return why.replace(box, "<box>")
    return f"{_TAKEN}{log.getvalue().strip()!r}"


def _planted_answer(planted: str, wanted: str) -> str:
    """Empty when the planted git at `planted` prints `wanted` for `rev-parse
    HEAD` run by its path and not found on `PATH`; else the arm's SKIP
    sentence, quoting what it printed or how that run failed."""
    try:
        proc = launch([planted, "rev-parse", "HEAD"],
                      "the planted git")
    except Refusal as refused:
        answer = _one_line(str(refused), 2 * DIFFERENCE)
    else:
        answer = proc.stdout.strip() if proc.returncode == 0 else (
            f"return code {proc.returncode}, "
            f"{_one_line(proc.stderr, DIFFERENCE, empty='no text on stderr')}")
    if answer == wanted:
        return ""
    return (f"the git this arm plants did not answer when run by its path: "
            f"{answer}. No state can be reached, and nothing is claimed.")


def _committed(root: str, message: str) -> tuple[int, str, str, str]:
    """`_repo_of` and then the sha it committed, read by `git rev-parse
    HEAD`: `(0, "", "", sha)`, or `_repo_of`'s `(exit, the command, stderr)`
    and no sha for the first command that failed, the rev-parse included."""
    code, head, stderr = _repo_of(root, message)
    if code != 0:
        return code, head, stderr, ""
    rev = launch(["git", "-C", root, "rev-parse", "HEAD"], "git rev-parse", env=git_env())
    if rev.returncode != 0:
        return rev.returncode, "git rev-parse HEAD", rev.stderr.strip(), ""
    return 0, "", "", rev.stdout.strip()


def _clone_git_exit_control(check: CheckRow, skip: SkipRow) -> None:
    """(yyyyyy) a pinned input's clone tests how each of the four gits it
    runs ended BEFORE it reads that git's standard output.

    `run.clone_input` runs `git clone`, `git checkout`, `git status
    --porcelain` and `git rev-parse HEAD`. One whose return code is
    not read is a clone taken over a git that did not answer: a `rev-parse`
    that fails prints nothing, an empty HEAD is a prefix of every pin, and
    the input's rows are recorded from whatever tree is there, at exit 0,
    under a log line that says `@ , clean`.

    Every git here is PLANTED, by a script the interpreter of this run
    reads, because no repository reaches most of these states — a git that a
    signal ends, one that fails and still prints on standard output — and
    because a planted git runs where
    `git` is not on PATH: the arm claims the same thing on every machine.
    Each state plants over ONE of the four runs and the three others answer;
    a clone kept from an earlier run is asked `git config --get
    remote.origin.url` in place of the `clone`, which the planted git
    answers with the address the arm asks for.
    A run that a signal ends has a return code below zero, which is not
    non-zero to a test of `> 0`: a `git clone` and a `git checkout` are each
    ended by one, as the `git status` is.
    Where the system cannot run the planted script at all — an interpreter
    path its first line cannot hold — the arm is a disclosed SKIP.

    The reasons are asserted WHOLE. A git that printed text on standard
    error has every line of it in the reason, after a colon, cut at `QUOTE`,
    right-stripped and ended with ` …` when something was cut; one that
    printed none, or only white space, has `census._git_said`'s words for
    that, after a comma. A second wording of
    how a git ended, or of a git that printed no text — `core.ended` and
    `census._git_said` own those — is a red row and not a sentence that
    drifts. The kept state is the
    `rev-parse` state's base a second time, where the clone the first call
    made is the cache.
    """
    label = ("yyyyyy  a pinned input's clone tests how each of the four gits "
             "it runs ended BEFORE it reads that git's standard output, and "
             "one that did not exit 0 is that input SKIPPED with how it "
             "ended and what it printed on stderr: a `git clone` that exits "
             "non-zero, with its exit code and, after a colon, git's own "
             "words, and a `git clone` that a signal ended, said with the "
             "signal's number and without the word `exited`, and a `git "
             "checkout` that a signal ended, likewise; "
             "a `git checkout` that prints no text on stderr, which "
             "is said in golden-census's words after a comma and never as a "
             "colon with nothing after it; a `git checkout` whose text follows "
             "blank lines, which is quoted from its first character that is "
             "not white space; a `git checkout` that prints two "
             "lines, both of them; a `git checkout` that prints more than "
             "the wide quote holds, cut there and ended with ` …`; a `git "
             "checkout` whose text the wide quote cuts after a space, which "
             "ends on ` …` and not on the space; a `git status` "
             "that a signal ended, which is said with the signal's number "
             "and without the word `exited`; a `git status` that exits "
             "non-zero AND lists a path, which is never \"not clean\" and "
             "whose listing is quoted nowhere; a `git rev-parse` that exits "
             "non-zero, which is never a clone taken — not at the HEAD it "
             "printed, and not at an empty one; and that failing `rev-parse` "
             "inside a clone kept from an "
             "earlier run, which names that directory after the fault. "
             "Every git is planted by the arm, so it runs where `git` is "
             "not on PATH. The control is a planted git that answers, whose "
             "clone is taken")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    got: dict[str, str] = {}
    wanted: dict[str, str] = {}
    with _box("golden-census-clone-git-") as box:
        for state, called, sub, printed, said, ends, want in _PLANTED_STATES:
            base = os.path.join(box, state)
            front = os.path.join(base, "bin")
            os.makedirs(front)
            planted = _planted_script(
                os.path.join(front, "git"),
                _PLANTED_GIT.format(python=sys.executable, sub=sub,
                                    printed=printed, said=said,
                                    ends=ends or "pass", pin=_PLANTED_PIN))
            if state == "control":
                # Asked of the script itself, by its path: a first line the
                # system cannot run sends `PATH` on to the next `git`, and
                # every state would then be a verdict about that one.
                why = _planted_answer(planted, _PLANTED_PIN)
                if why:
                    skip(label, why)
                    return
            with _env_as({"PATH": front + os.pathsep
                          + os.environ.get("PATH", "")}):
                got[called] = _planted_clone(box, state)
                wanted[called] = want
                if state == _KEPT_STATE:
                    kept = "that `git rev-parse`, inside a kept clone"
                    got[kept] = _planted_clone(box, state)
                    wanted[kept] = want + _KEPT_SENTENCE.format(state=state)
    check(label,
          got == wanted,
          ACTUAL + "; ".join(
              f"{called} -> "
              + ("as the label says" if said == wanted[called]
                 else _one_line(said, 2 * DIFFERENCE)
                 + (f" ({len(said)} characters)"
                    if len(said) > 2 * DIFFERENCE else ""))
              for called, said in got.items()),
          next="In `run.clone_input`, test each git's `returncode` before "
               "its standard output is read, word the four reasons through "
               "`census._git_failed` — `core.ended` for how the git ended, "
               "then git's standard error after a colon, every line of it, "
               "cut at `QUOTE` and ended with ` …` when something was cut, "
               "or `census._git_said`'s words after a comma when it printed "
               "no text that shows — and refuse an empty HEAD by name.")


# ------------------------- a row that writes into its pinned tree (kkkkkkk)

#: Arm `kkkkkkk`'s subject: it writes one line to the path it is given,
#: making the directory above it, and prints one line that names no path;
#: handed `raw` as well, it then prints a byte no UTF-8 decoder reads.
_WRITER_SUBJECT = '''\
import os
import sys

os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write("planted\\n")
print("wrote one file")
if sys.argv[2:] == ["raw"]:
    sys.stdout.flush()
    sys.stdout.buffer.write(b"\\xff\\n")
'''

#: Five inputs on one repository, in the order a capture enters them: a row
#: that writes where the repository's `.gitignore` ignores it, one that
#: writes under `<WORK>`, one that does the same on the second spelling, one
#: that writes a file into its pinned tree, and one that does the same and
#: then prints a byte no UTF-8 decoder reads. `dirty` stands after
#: `ignored`, so a capture of the two enters the clean clone first. One
#: address at one commit is ONE clone, so `dirty` and `sibling` name the
#: repository by a second spelling, `file://` in front: the clean clone and
#: the one a row writes into are two, and `sibling` and `dirty` share the
#: second.
_WRITER_MANIFEST = _subject("writer", '["<PYTHON>", "writer.py"]') + '''
[inputs.ignored]
args     = ["<CLONE>/ignored/planted.txt"]
surfaces = ["write"]
git      = "{origin}"
sha      = "{sha}"

[inputs.work]
args     = ["<WORK>/planted.txt"]
surfaces = ["write"]
git      = "{origin}"
sha      = "{sha}"

[inputs.sibling]
args     = ["<WORK>/planted.txt"]
surfaces = ["write"]
git      = "file://{origin}"
sha      = "{sha}"

[inputs.dirty]
args     = ["<CLONE>/planted.txt"]
surfaces = ["write"]
git      = "file://{origin}"
sha      = "{sha}"

[inputs.raw]
args     = ["<CLONE>/planted.txt", "raw"]
surfaces = ["write"]
git      = "{origin}"
sha      = "{sha}"

[surfaces.write]
args = []
'''

#: The fold of the clone every row of `_WRITER_MANIFEST` names in its argv.
_WRITER_CLONE_FOLD = '''
[[input]]
name        = "an input's clone directory"
disposition = "fold"
kind        = "path"
source      = "clone"
placeholder = "<CLONE>"
finding     = "a row's argv names its input's clone"
'''

#: A pin whose `vary` control runs the `dirty` row: the one row more in the
#: census of the control's case.
_WRITER_VARY_PIN = '''
[[input]]
name        = "a planted variable"
disposition = "pin"
variable    = "PLANTED"
value       = "1"
finding     = "planted: the control's row writes into its clone"
control     = { shape = "vary", surface = "dirty/write", value = "2" }
'''

#: The refusal the `dirty` row must meet, whole, with `<clone>` for the
#: `dirty` input's clone in the clone cache of its run.
_WRITTEN_SAID = ("dirty: the clone at <clone> was "
                 "clean when this run checked it out, and after this run's "
                 "rows `git status --porcelain` lists 1 line, "
                 "'?? planted.txt'")

#: The refusal two inputs that entered one clone meet, whole, in the order
#: a capture enters them: `sibling` writes under `<WORK>` and `dirty` writes
#: the file, and the run does not hold which of the two wrote it.
_SHARED_SAID = ("sibling and dirty: the clone at <clone> that their rows "
                "shared was clean when this run checked it out, and after "
                "this run's rows `git status --porcelain` lists 1 line, "
                "'?? planted.txt'")

#: The line a kept clone earns beside its input's `clone:` line when an
#: earlier row wrote into it where `.gitignore` ignores it.
_RESIDUE_LINE = ("  clone: git ignores 1 path in it that is not the pinned "
                 "content: 'ignored/'; delete the clone's folder to start "
                 "clean\n")

#: What `run._residue` is handed and what it says of five paths, the first
#: three of them spelled as git spells them, and of a listing that holds no
#: ignored path.
_RESIDUE_FIVE = "!! a/\n!! b\n!! c d\n!! e\n!! f"
_RESIDUE_SAID = ("  clone: git ignores 5 paths in it that are not the pinned "
                 "content: 'a/', 'b', 'c d' and 2 more; delete the clone's "
                 "folder to start clean\n")

#: Its `next:` sentence, whole.
_WRITTEN_NEXT = ("Make the row or the setup step that writes there write under "
                 "<WORK>, or where the pinned commit's own .gitignore "
                 "ignores it; then delete that directory "
                 "and run again.")

#: The first line of the block under that refusal opens with the subject's
#: command, and ends with the argument of the last row that ran: the file it
#: wrote.
_WRITTEN_RAN = "  ran: <PYTHON> writer.py "

#: How the `raw` row's own refusal opens: `core.launch`'s, over the byte.
_WRITTEN_RAW = "REFUSED: the subject ran and printed a byte"

#: How the `vary` control's refusal opens: the control, and which run.
_WRITTEN_VARY = ("REFUSED: census pin 'a planted variable': the `vary` "
                 "control on 'dirty/write', the first run under the pin: ")


def _written_capture(box: str, manifest: Manifest, root: str, out_dir: str,
                     inputs: tuple[str, ...], force: bool, config: str = ""
                     ) -> tuple[int | None, str, bool, str]:
    """One capture of `inputs` under the temp root `root`, its clone cache
    under `root` too, both made here: its exit code and "", or None and its
    refusal with the cache read as `<cache>`, `root` as `<t>` and `box` as
    `<box>`; whether the `dirty` clone holds the file its row writes; and
    the log the capture printed. With `config`, the home `_cache_in` plants
    holds it as `.gitconfig`: the global git configuration of the user the
    capture runs as."""
    os.makedirs(root)
    dirty = manifest.input_named("dirty")
    assert dirty is not None and dirty.git and dirty.sha
    with _tmpdir_as(root), _cache_in(root) as cache:
        if config:
            home = os.environ["HOME"]
            os.makedirs(home, exist_ok=True)
            pathlib.Path(home, ".gitconfig").write_text(config,
                                                        encoding="utf-8")
        clone = os.path.join(cache, "golden-census-trees",
                             repository_folder(dirty.git), dirty.sha)
        planted = os.path.join(clone, "planted.txt")
        log = io.StringIO()
        try:
            code = capture(manifest, out_dir, log, inputs, force)
        except Refusal as refused:
            said = (refusal_text(refused).replace(clone, "<clone>")
                    .replace(cache, "<cache>").replace(root, "<t>")
                    .replace(box, "<box>"))
            return None, said, os.path.isfile(planted), log.getvalue()
        return code, "", os.path.isfile(planted), log.getvalue()


@contextlib.contextmanager
def _asking_ignored(asked: list[tuple[str, bool]]) -> Iterator[None]:
    """For the length of the block, every `run._porcelain` is noted in
    `asked`, in the order it was called, as the folder name of the clone it
    asked and whether it asked for the paths git ignores, and runs as it
    would."""
    real = run_module._porcelain

    def spy(target: str, **options: bool) -> tuple[str | None, str]:
        asked.append((os.path.basename(target), bool(options.get("ignored"))))
        return real(target, **options)
    run_module._porcelain = spy
    try:
        yield
    finally:
        run_module._porcelain = real


def _written_clone_control(check: CheckRow, skip: SkipRow) -> None:
    """(kkkkkkk) a capture whose row writes a file into its input's pinned
    tree is refused after its rows, and its `--out` is as it was.

    `run.clone_input` finds a clone clean before its input's rows and
    nothing else looked again: the capture that wrote the file logged
    `clean` and exited 0, and every later capture skipped the input. This
    arm runs a real capture of a throwaway subject, under a temp root and
    a clone cache of its own in its box, over a repository of its own, five
    times, then the controls of a census once. First the `ignored` and
    `work` inputs into a fresh `--out`: one writes where the repository's
    `.gitignore` ignores it and one under `<WORK>`, and neither is refused
    — they are the arm's controls, and they leave a capture in that
    `--out`. Its log prints no residue line after the clone `ignored`
    makes, and after the clone `work` finds, which holds the file `ignored`
    wrote, the line that says git ignores 1 path in it that is not the
    pinned content, with `work`'s row running under it. `run._porcelain` is
    noted in that capture three times and in this order: the plain
    question for the clone `ignored` makes, ONE question with `ignored`
    for the clone `work` finds, which is the question `clone_input` asks
    there, and the plain question after the rows. `run._residue` is handed
    five paths and a listing of none that is ignored, for the cut and the
    count it words. Then `ignored` and `dirty`, in that order, so the clean
    clone is entered first and the one the row writes into second: refused,
    whole sentence and `next:`, the block under them opening `ran:` over
    the argv of the last row that ran, the subject's command and the file
    it wrote in the clone, so the refusal came after the row, and neither
    that `--out` nor its parent made. Then the same two under a third
    temp root, with `--force`, into the `--out` the first capture filled:
    refused alike, and that `--out` holds the first capture byte for byte.
    Then `raw`, whose row writes the same
    file and prints a byte no UTF-8 decoder reads: the refusal is the
    row's own, and no clone was checked after it. Then `sibling` and
    `dirty`, which pin one repository at one commit and so enter ONE clone,
    `sibling` first and `dirty` writing the file: refused naming both, in
    the order they entered, as sharing the clone. Then `ignored` and
    `dirty` twice more, under a home whose `.gitconfig` names a global
    ignore file that lists the file `dirty` writes, and under one whose
    `.gitconfig` sets `status.showUntrackedFiles = no`: refused alike, for
    whether a clone is clean is the repository's answer and not the
    caller's configuration's. Last, the controls of a
    census whose `vary` pin runs the `dirty` row: the refusal opens with
    the control and which of its runs it was. A SKIP where `git` is not on
    PATH: no input is cloned, so nothing is claimed.
    """
    label = ("kkkkkkk  a capture whose row writes a file into its input's "
             "pinned tree is refused after the row ran, in every clone the "
             "capture entered and not the first alone, naming every input "
             "that entered it in the order they entered, the clone and "
             "what `git status --porcelain` lists, saying to "
             "write under <WORK> or where the pinned commit's own "
             ".gitignore ignores it, under a block "
             "that opens `ran:` over the argv of the last row that ran; a "
             "fresh --out "
             "is not made and an --out holding an earlier capture holds it "
             "byte for byte; it is refused alike when the global git "
             "configuration of the user running it ignores that file, and "
             "when it sets `status.showUntrackedFiles = no`; a row that "
             "raised keeps its own refusal; under "
             "a `vary` control the refusal names the control and which of "
             "its runs it was — while a row that writes where the "
             "repository's .gitignore ignores it, and one that writes under "
             "<WORK>, are not refused, and the next input to enter a clone "
             "that holds such a file prints, beside its `clone:` line and "
             "with its rows running, a line saying how many paths git "
             "ignores in it that are not the pinned content, and the first "
             "three, from the one question it asks git before the rows, "
             "where a clone just made prints none and is asked the plain "
             "one")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no input of this arm can be "
                    "cloned and no row runs in a pinned tree; nothing was "
                    "made and nothing is claimed.")
        return
    with _box("golden-census-written-clone-") as box:
        origin = os.path.join(box, "origin")
        os.makedirs(origin)
        pathlib.Path(os.path.join(origin, "a.txt")).write_text(
            "one line of a throwaway repository\n", encoding="utf-8")
        pathlib.Path(os.path.join(origin, ".gitignore")).write_text(
            "ignored/\n", encoding="utf-8")
        code, head, stderr, sha = _committed(origin, "the origin")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        # `_committed`'s own control: a rev-parse that fails after a commit
        # that worked is its exit and its command, never a sha.
        # The plant fails the word HEAD, so `census.git_env`'s own question,
        # `rev-parse --local-env-vars`, is answered and the arm tests `_committed`.
        failing = os.path.join(box, "no-rev-parse")
        os.makedirs(failing)
        _planted_script(
            os.path.join(failing, "git"),
            '#!/bin/sh\nfor word in "$@"; do if [ "$word" = HEAD ]; '
            'then echo "fatal: planted" >&2; exit 128; fi; done\n'
            f'exec {json.dumps(shutil.which("git"))} "$@"\n')
        again = os.path.join(box, "origin-again")
        os.makedirs(again)
        pathlib.Path(again, "a.txt").write_text("x\n", encoding="utf-8")
        with _env_as({"PATH": failing + os.pathsep + os.environ.get("PATH", "")}):
            unread = _committed(again, "the origin")
        if unread[0] == 0 or unread[1] != "git rev-parse HEAD" or unread[3]:
            check(label, False, f"{ACTUAL}a `git rev-parse HEAD` planted to "
                                f"fail after the commit read as {unread!r}")
            return
        manifest_text = _WRITER_MANIFEST.format(origin=origin, sha=sha)
        census_text = (_STUB_ENVIRONMENT + _STUB_ROOT_FOLD + _STUB_WORK_FOLD
                       + _WRITER_CLONE_FOLD)
        manifest = load_manifest(_scratch(
            os.path.join(box, "subject"), manifest_text, census_text,
            {"writer.py": _WRITER_SUBJECT}))
        kept = os.path.join(box, "kept")
        asked: list[tuple[str, bool]] = []
        with _asking_ignored(asked):
            controls, said_controls, _, log_controls = _written_capture(
                box, manifest, os.path.join(box, "t1"), kept,
                ("ignored", "work"), False)
        before = _tree_bytes(kept)
        fresh = os.path.join(box, "fresh", "out")
        _, said_fresh, ran, _ = _written_capture(
            box, manifest, os.path.join(box, "t2"), fresh,
            ("ignored", "dirty"), False)
        _, said_kept, _, _ = _written_capture(
            box, manifest, os.path.join(box, "t3"), kept,
            ("ignored", "dirty"), True)
        _, said_raw, _, _ = _written_capture(
            box, manifest, os.path.join(box, "t4"), os.path.join(box, "raw"),
            ("raw",), False)
        _, said_both, _, _ = _written_capture(
            box, manifest, os.path.join(box, "t6"),
            os.path.join(box, "both", "out"), ("sibling", "dirty"), False)
        ignore = os.path.join(box, "global-ignore")
        pathlib.Path(ignore).write_text("planted.txt\n", encoding="utf-8")
        _, said_ignored, _, _ = _written_capture(
            box, manifest, os.path.join(box, "t7"),
            os.path.join(box, "global", "out"), ("ignored", "dirty"), False,
            f"[core]\n\texcludesFile = {ignore}\n")
        _, said_unshown, _, _ = _written_capture(
            box, manifest, os.path.join(box, "t8"),
            os.path.join(box, "unshown", "out"), ("ignored", "dirty"), False,
            "[status]\n\tshowUntrackedFiles = no\n")
        # The control's run: the same subject under a census whose `vary`
        # pin runs the `dirty` row, its first run writing into the clone.
        varied = load_manifest(_scratch(
            os.path.join(box, "varied"), manifest_text,
            census_text + _WRITER_VARY_PIN, {"writer.py": _WRITER_SUBJECT}))
        root = os.path.join(box, "t5")
        os.makedirs(root)
        with _tmpdir_as(root), _cache_in(root) as cache:
            roots = Roots(root=varied.subject.root, work=root, clone=None)
            try:
                _census_rows(varied, roots)
                said_vary = "no refusal"
            except Refusal as refused:
                said_vary = (refusal_text(refused).replace(
                    os.path.join(cache, "golden-census-trees",
                                 repository_folder(f"file://{origin}"), sha),
                    "<clone>").replace(cache, "<cache>")
                    .replace(root, "<t>").replace(box, "<box>"))
        fresh_made = os.path.lexists(os.path.dirname(fresh))
        held = before is not None and _tree_bytes(kept) == before

    def two(said: str) -> str:
        """A refusal's own two lines, without the block under them."""
        return "\n".join(said.splitlines()[:2])

    expected = f"REFUSED: {_WRITTEN_SAID}\n  next: {_WRITTEN_NEXT}"
    ran_line = (said_fresh.splitlines() + ["", "", ""])[2]
    opens_ran = (ran_line.startswith(_WRITTEN_RAN)
                 and ran_line.endswith("/planted.txt"))
    raised_first = (said_raw.startswith(_WRITTEN_RAW)
                    and "was clean when this run" not in said_raw)
    named = said_vary.startswith(_WRITTEN_VARY + _WRITTEN_SAID)
    seen = re.sub(r"@ [0-9a-f]+, clean", "@ <short>, clean",
                  log_controls.replace(origin, "<origin>"))
    clean_line = "  clone: <origin> @ <short>, clean\n"
    fresh_quiet = ("  input ignored\n" + clean_line
                   + "    write: exit 0\n  input work\n") in seen
    residue_told = ("  input work\n" + clean_line + _RESIDUE_LINE
                    + "    write: exit 0\n") in seen
    both = two(said_both) == f"REFUSED: {_SHARED_SAID}\n  next: {_WRITTEN_NEXT}"
    configured = [two(said_ignored) == expected, two(said_unshown) == expected]
    asked_once = asked == [(sha, False), (sha, True), (sha, False)]
    counted = (_residue(_RESIDUE_FIVE) == _RESIDUE_SAID
               and _residue("?? x\n") == "")
    check(label,
          controls == 0 and two(said_fresh) == expected
          and two(said_kept) == expected and opens_ran and ran
          and not fresh_made and held and raised_first and named
          and fresh_quiet and asked_once and residue_told and both and counted
          and all(configured),
          f"{ACTUAL}controls exit={controls}"
          f"{' ' + _one_line(said_controls) if said_controls else ''}; "
          f"the row ran={ran}; fresh --out made={fresh_made}; earlier "
          f"capture held={held}; the refusal into the earlier capture is "
          f"the same={two(said_kept) == two(said_fresh)}; the block opens "
          f"ran:={opens_ran}; a row that raised keeps its own "
          f"refusal={raised_first}; the control's refusal names it and the "
          f"run={named}; a fresh clone prints no residue line="
          f"{fresh_quiet} and asks git once={asked_once}; the next input to "
          f"enter it prints the line, its "
          f"row running={residue_told}; the refusal over two inputs names "
          f"both, in order={both}; the line counts and cuts as it says="
          f"{counted}; refused alike under a global ignore file that lists "
          f"the file={configured[0]}, under a global "
          f"status.showUntrackedFiles = no={configured[1]}; "
          f"{_one_line(said_fresh, 400, empty='no refusal')} | the "
          f"control: {_one_line(said_vary, 200)} | two inputs: "
          f"{_one_line(said_both, 300, empty='no refusal')}",
          next="`run.place` runs `git status --porcelain` through "
               "`run._porcelain` in every clone its rows ran in, after the "
               "rows and only when they ended without raising, and refuses "
               "naming each clone that lists a path, each once, with every "
               "input that entered it in the order they entered; "
               "`run.clone_input` asks `run._porcelain` once, with `ignored` "
               "in a clone it finds and without it in one it makes, "
               "and `run._residue` words the line that follows the "
               "`clone:` line; "
               "`capture._capture_once` marks its record as ran once the "
               "rows ended; "
               "`controls._vary_control` raises the place's refusal again "
               "in front of its label and the run; the refusal leaves "
               "`capture._staged` before `_swap_in`, so --out is as it was.")


# ------------------- a row that writes under its pinned clone's .git (ccccccccc)

#: Arm `ccccccccc`'s subject: handed a directory that holds a `.git`, it
#: writes a hook, a line into `.git/info/exclude` and a line into
#: `.git/config` there, none of which `git status --porcelain` lists; handed
#: any other directory it writes nothing. It prints which.
_HOOKED_SUBJECT = '''\
import os
import sys

git = os.path.join(sys.argv[1], ".git")
if os.path.isdir(git):
    hook = os.path.join(git, "hooks", "post-checkout")
    os.makedirs(os.path.dirname(hook), exist_ok=True)
    with open(hook, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\\n:\\n")
    os.chmod(hook, 0o755)
    with open(os.path.join(git, "info", "exclude"), "a",
              encoding="utf-8") as handle:
        handle.write("planted.txt\\n")
    with open(os.path.join(git, "config"), "a", encoding="utf-8") as handle:
        handle.write("[planted]\\n\\tkey = 1\\n")
print("wrote under .git" if os.path.isdir(git) else "wrote nothing")
'''

#: Two inputs on one repository: `dirty` is handed its clone, and `quiet`
#: the work directory, which holds no `.git`. The `file://` spelling keeps
#: the clone's folder the one `repository_folder` names from the address.
_HOOKED_MANIFEST = _subject("hooked", '["<PYTHON>", "hooked.py"]') + '''
[inputs.dirty]
args     = ["<CLONE>"]
surfaces = ["write"]
git      = "file://{origin}"
sha      = "{sha}"

[inputs.quiet]
args     = ["<WORK>"]
surfaces = ["write"]
git      = "file://{origin}"
sha      = "{sha}"

[surfaces.write]
args = []
'''

#: The refusal the `dirty` row must meet, whole, with `<clone>` for its
#: clone.
_HOOKED_SAID = ("dirty: the clone at <clone> was clean when this run "
                "checked it out, and after this run's rows its .git/config, "
                ".git/hooks/ and .git/info/ changed: a later capture of any "
                "manifest that pins this repository and commit would read "
                "what was written there")


def _git_metadata_control(check: CheckRow, skip: SkipRow) -> None:
    """(ccccccccc) no hook runs in a git golden-census starts in a clone, and
    a row that writes under its clone's `.git/` is refused.

    `_refuse_written` asked `git status --porcelain`, which never lists
    `.git/`, and `core.GIT_SETTINGS` set no `core.hooksPath`: a subject that
    wrote `<CLONE>/.git/hooks/post-checkout`, a line in `.git/info/exclude`
    and an edit to `.git/config` ended `capture complete`, and the next
    capture of any manifest that pinned that clone ran the hook during its
    `git checkout`.

    Two cases ask a hook to run. In the first a kept clone holds an
    executable `post-checkout` in its own `.git/hooks/` that writes a marker,
    and `_in_cache` runs a `checkout` there. In the second a fresh clone is
    made under a home whose `.gitconfig` sets `core.hooksPath` to a directory
    holding that hook. Neither marker may exist. Then two real captures,
    each under a temp root and a clone cache of its own: the `dirty` input,
    whose row writes the three things under `<CLONE>/.git/`, is refused with
    the sentence naming all three parts, its `next:` and no `--out` made;
    the `quiet` input, whose row writes nothing there, ends `capture
    complete`. A SKIP where `git` is not on PATH.
    """
    label = ("ccccccccc  a hook planted in a kept clone's .git/hooks/, and "
             "one a global core.hooksPath names, runs in no git "
             "golden-census starts there, and a capture whose row writes "
             "under its input's clone's .git/ (its config, a hook, an "
             "exclude line) is refused after the rows naming the input, the "
             "clone and the parts that changed, with the --out as it was, "
             "while a capture whose row writes nothing there is not")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no input of this arm can be "
                    "cloned; nothing was made and nothing is claimed.")
        return
    with _box("golden-census-git-metadata-") as box:
        origin = os.path.join(box, "origin")
        os.makedirs(origin)
        pathlib.Path(origin, "a.txt").write_text("one line\n",
                                                 encoding="utf-8")
        code, head, stderr, sha = _committed(origin, "the origin")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        hook = "#!/bin/sh\necho ran > {marker}\n"
        marker_kept = os.path.join(box, "marker-kept")
        tree, why = clone_input(os.path.join(box, "cache-kept"), origin, sha,
                                io.StringIO())
        ran_kept = "no clone"
        if tree is not None:
            _planted_script(os.path.join(tree, ".git", "hooks",
                                         "post-checkout"),
                            hook.format(marker=marker_kept))
            _in_cache(tree, "git checkout", "checkout", "--quiet",
                      "--no-guess", sha)
            ran_kept = str(os.path.exists(marker_kept))
        marker_global = os.path.join(box, "marker-global")
        hooks = os.path.join(box, "global-hooks")
        os.makedirs(hooks)
        _planted_script(os.path.join(hooks, "post-checkout"),
                        hook.format(marker=marker_global))
        home = os.path.join(box, "home")
        os.makedirs(home)
        pathlib.Path(home, ".gitconfig").write_text(
            f"[core]\n\thooksPath = {hooks}\n", encoding="utf-8")
        with _env_as({"HOME": home}):
            fresh, fresh_why = clone_input(os.path.join(box, "cache-global"),
                                           origin, sha, io.StringIO())
        manifest = load_manifest(_scratch(
            os.path.join(box, "subject"),
            _HOOKED_MANIFEST.format(origin=origin, sha=sha),
            _STUB_ENVIRONMENT + _STUB_ROOT_FOLD + _STUB_WORK_FOLD
            + _WRITER_CLONE_FOLD, {"hooked.py": _HOOKED_SUBJECT}))
        out = os.path.join(box, "refused", "out")
        _, said, _, _ = _written_capture(box, manifest, os.path.join(box, "t1"),
                                         out, ("dirty",), False)
        quiet_code, quiet_said, _, quiet_log = _written_capture(
            box, manifest, os.path.join(box, "t2"),
            os.path.join(box, "quiet", "out"), ("quiet",), False)
        made = os.path.lexists(os.path.dirname(out))
        ran_global = os.path.exists(marker_global)
    expected = f"REFUSED: {_HOOKED_SAID}\n  next: {_WRITTEN_NEXT}"
    two = "\n".join(said.splitlines()[:2])
    check(label,
          tree is not None and fresh is not None and ran_kept == "False"
          and not ran_global and two == expected and not made
          and quiet_code == 0 and not quiet_said,
          f"{ACTUAL}a hook in a kept clone's .git/hooks/ ran there="
          f"{ran_kept} ({_one_line(why, 100, empty='clone taken')}); a hook "
          f"a global core.hooksPath names ran={ran_global} "
          f"({_one_line(fresh_why, 100, empty='clone taken')}); the capture "
          f"whose row writes under .git/ -> "
          f"{_one_line(said, 500, empty='no refusal')}; its --out made="
          f"{made}; the capture whose row writes nothing there -> exit "
          f"{quiet_code} {_one_line(quiet_said, 300)}",
          next="`core.GIT_SETTINGS` sets `core.hooksPath` to the null device "
               "and `core.fsmonitor=false`, so no hook runs in a git "
               "`core.git_command` builds; `run.Place.enter` takes "
               "`run.git_metadata_digest` of each clone it enters and "
               "`run._refuse_written` takes it again, adding a line to its "
               "refusal for each part of `.git/config`, `.git/hooks/` and "
               "`.git/info/` that moved.")


# ------------------- what a `vary` control's runs printed of a clone (vvvvvvv)

#: Arm `vvvvvvv`'s subject: it writes one line to the path it is given,
#: making the directory above it, and prints the two variables the arm's
#: pins name.
_TELLER_SUBJECT = '''\
import os
import sys

os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write("planted\\n")
print(os.environ.get("PLANTED"), os.environ.get("BARE"))
'''

#: Two inputs: `kept` pins the arm's repository and writes where its
#: `.gitignore` ignores it, so the run after the one that made the clone
#: finds a path git ignores in it; `bare` pins no tree and writes under
#: `<WORK>`.
_TELLER_MANIFEST = _subject("teller", '["<PYTHON>", "teller.py"]') + '''
[inputs.kept]
args     = ["<CLONE>/ignored/planted.txt"]
surfaces = ["write"]
git      = "{origin}"
sha      = "{sha}"

[inputs.bare]
args     = ["<WORK>/planted.txt"]
surfaces = ["write"]

[surfaces.write]
args = []
'''

#: One `vary` pin per input of `_TELLER_MANIFEST`, after the clone
#: directory's path fold, and last a pin over the `kept` input of a
#: variable the subject never reads, whose row is UNPROVEN.
_TELLER_PINS = '''
[[input]]
name        = "the kept input's variable"
disposition = "pin"
variable    = "PLANTED"
value       = "1"
finding     = "planted: the row prints it, over a clone"
control     = { shape = "vary", surface = "kept/write", value = "2" }

[[input]]
name        = "the bare input's variable"
disposition = "pin"
variable    = "BARE"
value       = "1"
finding     = "planted: the row prints it, over no clone"
control     = { shape = "vary", surface = "bare/write", value = "2" }

[[input]]
name        = "the unproven input's variable"
disposition = "pin"
variable    = "UNSEEN"
value       = "1"
finding     = "planted: the subject never reads it, over a clone"
control     = { shape = "vary", surface = "kept/write", value = "2" }
'''

#: What the `kept` row tells under its detail, whole, the arm's repository
#: written `<origin>` and its short commit `<short>`: the first run made
#: the clone, and the two after it found the path the first one wrote.
_TELLER_TOLD = (
    "the first run under the pin: clone: <origin> @ <short>, clean",
    "the second run under the pin: clone: <origin> @ <short>, clean",
    "the second run under the pin: clone: git ignores 1 path in it that is "
    "not the pinned content: 'ignored/'; delete the clone's folder to "
    "start clean",
    "the run under PLANTED='2': clone: <origin> @ <short>, clean",
    "the run under PLANTED='2': clone: git ignores 1 path in it that is not "
    "the pinned content: 'ignored/'; delete the clone's folder to start "
    "clean")

#: What the UNPROVEN row tells, whole: its runs come after the `kept` row's,
#: so each finds the path those wrote.
_TELLER_UNPROVEN = tuple(
    f"{which}: clone: {said}"
    for which in ("the first run under the pin",
                  "the second run under the pin", "the run under UNSEEN='2'")
    for said in ("<origin> @ <short>, clean",
                 "git ignores 1 path in it that is not the pinned content: "
                 "'ignored/'; delete the clone's folder to start clean"))

#: The PASS detail of the clone directory's path fold: golden-census's own
#: sample line, folded over the stand-in directory the control made.
_TELLER_FOLD = ACTUAL + repr("scanned <CLONE>/App and "
                             "/nowhere/that/golden-census/made/App")


def _told_under(printed: str, label: str) -> tuple[str, ...]:
    """The lines a block in `printed` holds under the row whose line holds
    `label`, after its detail line, up to the next row, its `next:` line or
    the blank line that ends the rows; () when no row holds it. Each is
    the line with the detail's margin of 11 spaces taken off and nothing
    else, so a line printed at another margin does not read as one told."""
    lines = printed.splitlines()
    at = next((number for number, line in enumerate(lines)
               if line.startswith("  [") and label in line), None)
    if at is None:
        return ()
    told: list[str] = []
    for line in lines[at + 2:]:
        if not line.startswith(" " * 11) or line.startswith(" " * 11 + "next: "):
            break
        told.append(line[11:])
    return tuple(told)


def _vary_told_control(check: CheckRow, skip: SkipRow) -> None:
    """(vvvvvvv) a `vary` control's row tells what its runs printed of the
    clone they ran over.

    The place each of the control's three runs enters writes the lines
    `run.clone_input` writes to a log — the `clone:` line, and beside it in
    a kept clone the line that names what git ignores there — and the
    control picks them out of that place's log, so `census` prints them
    under the row, each opened with which run printed it. The arm runs the
    controls of one census as `census` runs them — `controls.manifest_controls`
    into a `core.Report` that prints every row, the call `census_check`
    makes, which no arm may call (arm `ii`) — under a temp root and a
    clone cache of its own in its box, over a repository of its own whose
    `.gitignore` ignores `ignored/`. The `kept` row writes there: its first
    run makes the clone and finds nothing ignored in it, and the two after
    it find the path the first one wrote. The last row varies a variable
    the subject never reads, over the same clone: it is UNPROVEN, a FAIL,
    and tells its runs' lines as a PASS does. The `bare` row's input pins
    no tree, so its row tells nothing. Every told line is asserted at the
    detail's margin (`_told_under`). The census holds the clone
    directory's path fold, and the work directory the controls are given
    is made with no clone directory: the control PASSES on the stand-in it
    makes there, and its detail is golden-census's own sample line folded.
    A SKIP where `git` is not on PATH: nothing is cloned, so nothing is
    claimed.
    """
    label = ("vvvvvvv  a `vary` control's row tells, under its detail and "
             "at its margin, the `clone:` line each of its three runs "
             "printed, opened with which run it was, and beside each run "
             "that found the kept clone holding a path git ignores the line "
             "that names it — the first run, which made the clone, names "
             "none; an UNPROVEN row, a FAIL, tells its runs' lines the same "
             "way; the row of a `vary` control whose input pins no tree "
             "tells nothing; and the clone directory's path fold PASSES on "
             "the stand-in directory its control makes under the work "
             "directory, its detail the folded sample line")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no input of this arm can be "
                    "cloned; nothing was made and nothing is claimed.")
        return
    with _box("golden-census-vary-told-") as box:
        origin = os.path.join(box, "origin")
        os.makedirs(origin)
        pathlib.Path(os.path.join(origin, "a.txt")).write_text(
            "one line of a throwaway repository\n", encoding="utf-8")
        pathlib.Path(os.path.join(origin, ".gitignore")).write_text(
            "ignored/\n", encoding="utf-8")
        code, head, stderr, sha = _committed(origin, "the origin")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        manifest = load_manifest(_scratch(
            os.path.join(box, "subject"),
            _TELLER_MANIFEST.format(origin=origin, sha=sha),
            _STUB_ENVIRONMENT + _WRITER_CLONE_FOLD + _TELLER_PINS,
            {"teller.py": _TELLER_SUBJECT}))
        root = os.path.join(box, "t")
        os.makedirs(root)
        out = io.StringIO()
        report = Report(out, "CENSUS CONTROLS")
        with _tmpdir_as(root), _cache_in(root):
            manifest_controls(report.check, report.skip, manifest,
                              io.StringIO())
        failed = report.finish()
        printed = re.sub(r"@ [0-9a-f]+, clean", "@ <short>, clean",
                         out.getvalue().replace(origin, "<origin>"))
    kept = _told_under(printed, "census pin \"the kept input's variable\"")
    bare = _told_under(printed, "census pin \"the bare input's variable\"")
    unproven = _told_under(printed,
                           "census pin \"the unproven input's variable\"")
    failing = "  [FAIL]  census pin \"the unproven input's variable\"" in printed
    fold_at = printed.find("  [PASS]  census fold \"an input's clone "
                           "directory\"")
    fold = (printed[fold_at:].splitlines() + ["", ""])[1].strip()
    check(label,
          failed == 1 and failing and kept == _TELLER_TOLD
          and unproven == _TELLER_UNPROVEN and bare == () and fold_at >= 0
          and fold == _TELLER_FOLD,
          f"{ACTUAL}census controls failed={failed}; the kept row tells "
          f"{len(kept)} line(s), as the label says={kept == _TELLER_TOLD}: "
          + _one_line(" | ".join(kept), 3 * DIFFERENCE, empty="nothing")
          + f"; the UNPROVEN row is a FAIL={failing} and tells "
          f"{len(unproven)} line(s), as the label says="
          f"{unproven == _TELLER_UNPROVEN}: "
          + _one_line(" | ".join(unproven), DIFFERENCE, empty="nothing")
          + f"; the bare row tells {len(bare)} line(s); the fold's PASS "
          + ("shows the folded sample" if fold == _TELLER_FOLD
             else _one_line(fold, DIFFERENCE, empty="is not printed")),
          next="In `controls._vary_control`, hand each run's place a log of "
               "its own and keep the lines that open with `run.CLONE_LINE`, "
               "each after which run printed it, as the row's `told`; "
               "`core.Report._write_row` prints them under the detail. The "
               "fold's PASS is `controls._path_fold_control`'s, on the "
               "stand-in it makes.")


# ------------------- the user's global git configuration, read by none (wwwwwww)

#: The global git configuration arm `wwwwwww` plants in its home: a global
#: ignore file, `{ignore}`, and line endings turned into `\r\n` on every
#: checkout, by `core.autocrlf` and, where that is off, by `core.eol` over the
#: repository's own `* text=auto`.
_GLOBAL_GITCONFIG = ("[core]\n\texcludesFile = {ignore}\n"
                     "\tautocrlf = true\n\teol = crlf\n")

#: Arm `wwwwwww`'s census: the environment, and a `git-checkout`
#: precondition that requires a clean tree.
_CLEAN_TREE_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the tree is a git checkout"
disposition = "precondition"
check       = "git-checkout"
clean       = true
finding     = "planted: a capture names the revision it was taken at"
'''


def _global_config_control(check: CheckRow, skip: SkipRow) -> None:
    """(wwwwwww) what a git golden-census starts in a tree answers is the
    repository's, whatever the global git configuration of the user running
    golden-census says.

    One repository of the arm's own, its committed file `alpha\\nbeta\\n`
    under a `.gitattributes` of `* text=auto`, and a file `stray.txt` in it
    that is not committed. Then a home of the arm's own whose `.gitconfig`
    names a global ignore file listing `stray.txt` and sets `core.autocrlf =
    true` and `core.eol = crlf`. The control is a plain `git clone` and a
    plain `git status --porcelain` under that home: the clone's file reads
    `\\r\\n` and the status lists nothing, so the home is read; where it is
    not, nothing is claimed and the arm is SKIPPED. Then, under that home:
    `run.clone_input`'s clone of the repository holds the committed bytes
    and is taken; a `git-checkout` precondition with `clean = true` over the
    repository is refused naming `?? stray.txt`; `mutants.clone_subject`'s
    clone holds the committed bytes; and, with `stray.txt` written into that
    clone too, `mutants.plant`'s `git status` after a mutant's commit lists
    it, and the mutant is refused naming it. A SKIP where `git` is not on
    PATH.
    """
    label = ("wwwwwww  under a global git configuration that ignores an "
             "untracked file and turns a checkout's line endings into "
             "\\r\\n, which a plain git obeys, a pinned input's clone holds "
             "the committed bytes with \\n and is taken, a `git-checkout` "
             "precondition with `clean = true` is refused naming the "
             "untracked file, and the clone `mutants` plants in holds the "
             "committed bytes with \\n, and a mutant planted in it with "
             "that untracked file there is refused naming the file")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no repository could be made; "
                    "nothing was made and nothing is claimed.")
        return
    committed = b"alpha\nbeta\n"
    with _box("golden-census-global-config-") as box:
        origin = os.path.join(box, "origin")
        manifest_path = _scratch(origin, census_text=_CLEAN_TREE_CENSUS,
                                 extra={".gitattributes": "* text=auto\n"})
        pathlib.Path(os.path.join(origin, "a.txt")).write_bytes(committed)
        code, head, stderr = _repo_of(origin, "the committed tree")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing is claimed.")
            return
        sha = launch(["git", "-C", origin, "rev-parse", "HEAD"],
                     "git rev-parse", env=git_env()).stdout.strip()
        pathlib.Path(os.path.join(origin, "stray.txt")).write_text(
            "not committed\n", encoding="utf-8")
        ignore = os.path.join(box, "global-ignore")
        pathlib.Path(ignore).write_text("stray.txt\n", encoding="utf-8")
        manifest = load_manifest(manifest_path)
        with _cache_in(box) as cache:
            home = os.environ["HOME"]
            os.makedirs(home, exist_ok=True)
            pathlib.Path(home, ".gitconfig").write_text(
                _GLOBAL_GITCONFIG.format(ignore=ignore), encoding="utf-8")
            plain = os.path.join(box, "plain")
            launch(["git", "clone", "--quiet", origin, plain], "git clone", env=git_env())
            plain_bytes = pathlib.Path(plain, "a.txt").read_bytes()
            plain_status = launch(["git", "-C", origin, "status",
                                   "--porcelain"], "git status", env=git_env()).stdout
            log = io.StringIO()
            tree, why = clone_input(cache, origin, sha, log)
            cloned = (pathlib.Path(tree, "a.txt").read_bytes()
                      if tree is not None else b"")
            try:
                preconditions(manifest.census,
                              Roots(root=origin, work=box, clone=None),
                              io.StringIO())
                refused = "no refusal"
            except Refusal as refusal:
                refused = str(refusal).replace(origin, "<origin>")
            into = os.path.join(box, "mutants")
            os.makedirs(into)
            clone = clone_subject(origin, into, "global")
            planted = pathlib.Path(clone, "a.txt").read_bytes()
            pathlib.Path(clone, "stray.txt").write_text(
                "not committed\n", encoding="utf-8")
            try:
                plant_mutant(clone, Mutant("stray", "a.txt", "beta", "gamma"))
                stray = "no refusal"
            except Refusal as refusal:
                stray = str(refusal)
    if plain_bytes != b"alpha\r\nbeta\r\n" or plain_status.strip():
        skip(label, "the control did not read the planted home: a plain "
                    f"`git clone` wrote {plain_bytes!r} and a plain `git "
                    f"status --porcelain` printed {plain_status.strip()!r}, "
                    "so this git does not take its global configuration from "
                    "HOME here; nothing is claimed.")
        return
    named = "printed '?? stray.txt'" in refused
    listed = "lists '?? stray.txt'" in stray
    check(label,
          tree is not None and cloned == committed and named
          and planted == committed and listed,
          f"{ACTUAL}the control: a plain clone wrote {plain_bytes!r}, a "
          f"plain status printed {plain_status.strip()!r}; the pinned "
          f"input's clone taken={tree is not None}"
          f"{'' if tree is not None else ' (' + _one_line(why, 200) + ')'}, "
          f"it holds {cloned!r}; the precondition -> "
          f"{_one_line(refused, 300)}; the mutants clone holds {planted!r}; "
          f"a mutant planted beside an untracked file -> "
          f"{_one_line(stray, 300)}",
          next="Every git golden-census starts in a tree is "
               "`core.git_command`'s argv, which puts `core.GIT_SETTINGS` in "
               "front of the subcommand: `run._in_cache`, "
               "`census._git_checkout` and `mutants._git`, whose clone, "
               "commit and status all take it. Read the detail for which "
               "answered from the global configuration.")


def _repo_global_ignore_control(check: CheckRow, skip: SkipRow) -> None:
    """(xxxxxxxx) the throwaway repository the self-test makes holds what was
    written in it, whatever the global git ignore file of the user running
    the self-test says.

    A home of the arm's own whose `.gitconfig` sets `core.excludesFile` to a
    file listing `a.txt`, and two directories holding an `a.txt`. The control
    is a plain `git init`, `git add -A` and `git ls-files` over the first:
    they list nothing, so the home is read; where they list the file, nothing
    is claimed and the arm is SKIPPED. Then `proof._repo_of` over the second
    commits, and `git ls-files` under `core.GIT_SETTINGS` lists `a.txt`. A
    `_repo_of` whose git obeys the home makes no commit: `git add -A` adds
    nothing and the commit exits 1. A SKIP where `git` is not on PATH.
    """
    label = ("xxxxxxxx  the throwaway repository `proof._repo_of` makes holds "
             "a file that the global git ignore file of the home it runs "
             "under names")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no repository could be made; "
                    "nothing was made and nothing is claimed.")
        return
    with _box("golden-census-repo-ignore-") as box:
        home = os.path.join(box, "home")
        ignore = os.path.join(box, "global-ignore")
        control = os.path.join(box, "control")
        made = os.path.join(box, "made")
        for directory in (home, control, made):
            os.makedirs(directory)
            if directory != home:
                pathlib.Path(directory, "a.txt").write_text(
                    "one line\n", encoding="utf-8")
        pathlib.Path(ignore).write_text("a.txt\n", encoding="utf-8")
        pathlib.Path(home, ".gitconfig").write_text(
            f"[core]\n\texcludesFile = {ignore}\n", encoding="utf-8")
        with _env_as({"HOME": home, "XDG_CONFIG_HOME": None,
                      "GIT_CONFIG_GLOBAL": None}):
            for argv in (["git", "init", "--quiet", control],
                         ["git", "-C", control, "add", "-A"]):
                launch(argv, "git " + argv[1])
            plain = launch(["git", "-C", control, "ls-files"],
                           "git ls-files", env=git_env()).stdout.split()
            code, head, stderr = _repo_of(made, "the committed file")
            listed = launch(git_command("-C", made, "ls-files"),
                            "git ls-files", env=git_env()).stdout.split()
    if plain:
        skip(label, "the control did not read the planted home: a plain "
                    f"`git add -A` took {plain!r} past a global ignore file "
                    "that names it, so this git does not take its global "
                    "configuration from HOME here; nothing is claimed.")
        return
    check(label, code == 0 and listed == ["a.txt"],
          f"{ACTUAL}`_repo_of` exited {code}"
          f"{'' if code == 0 else ' at `' + head + '`: ' + stderr[:DIFFERENCE]}"
          f"; `git ls-files` listed {listed!r}",
          next="`proof._repo_of` runs each of its three gits as "
               "`core.git_command` builds it, which puts "
               "`core.GIT_SETTINGS` (a null `core.excludesFile`) in front of "
               "the subcommand; a git of the self-test's own that does not "
               "takes the reader's global configuration.")


# ------------- an exported GIT_DIR and GIT_INDEX_FILE, reaching none (zzzzzzzz)


def _decoy_state(decoy: str) -> tuple[str, str, str]:
    """The decoy repository's HEAD, the SHA-256 of its `.git/index` and what
    `git status --porcelain` lists in it, each asked of a git started
    WITHOUT the two variables the arm exports, so the question is answered
    by the decoy and not by whatever they name."""
    plain = {name: value for name, value in os.environ.items()
             if name not in ("GIT_DIR", "GIT_INDEX_FILE")}
    head = launch(["git", "-C", decoy, "rev-parse", "HEAD"], "git rev-parse",
                  env=plain).stdout.strip()
    status = launch(["git", "-C", decoy, "status", "--porcelain"],
                    "git status", env=plain).stdout
    index = hashlib.sha256(
        pathlib.Path(decoy, ".git", "index").read_bytes()).hexdigest()
    return head, index, status


def _exported_git_dir_control(check: CheckRow, skip: SkipRow) -> None:
    """(zzzzzzzz) an exported `GIT_DIR` and `GIT_INDEX_FILE` reach no git
    golden-census starts.

    git exports both, absolute, to every hook, `!` alias and `rebase -x`
    command, so a golden-census started from one inherits a repository that
    is not the subject's. The arm makes a DECOY repository, one tracked file
    and one commit, records its HEAD, the digest of its index and what `git
    status --porcelain` lists, and exports `GIT_DIR` and `GIT_INDEX_FILE`
    naming it. Under that environment: the `git-checkout` precondition over
    a separate subject repository quotes the SUBJECT's commit; a mutant
    planted in a clone `mutants` makes of that subject (`clone_subject` and
    `plant`, which commit and ask for status) is planted, as it is without
    the variables; and `proof._repo_of` over a fresh directory gives that
    directory its own `.git`. Afterwards the decoy's HEAD, index digest and
    status are what they were.

    The control is the decoy's own state, read before and after: a git that
    obeys the variables commits into it, adds to its index or makes no
    `.git` in the fresh directory, and a row goes red. The arm runs in
    process under `proof._env_as`, which sets the variables in this
    process's environment, the one every git the package starts inherits
    unless it builds another. A SKIP where `git` is not on PATH.
    """
    label = ("zzzzzzzz  an exported GIT_DIR and GIT_INDEX_FILE reach no git "
             "golden-census starts: the decoy's refs and index are unchanged "
             "and the precondition names the subject's commit")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no repository could be made; "
                    "nothing was made and nothing is claimed.")
        return
    with _box("golden-census-git-env-") as box:
        decoy = os.path.join(box, "decoy")
        os.makedirs(decoy)
        pathlib.Path(decoy, "decoy.txt").write_text("decoy\n",
                                                    encoding="utf-8")
        subject = os.path.join(box, "subject")
        manifest_path = _scratch(subject, census_text=_CLEAN_TREE_CENSUS)
        pathlib.Path(subject, "a.txt").write_text("alpha\nbeta\n",
                                                  encoding="utf-8")
        fresh = os.path.join(box, "fresh")
        os.makedirs(fresh)
        pathlib.Path(fresh, "b.txt").write_text("fresh\n", encoding="utf-8")
        code, head, stderr, decoy_sha = _committed(decoy, "decoy commit")
        if code == 0:
            code, head, stderr, sha = _committed(subject, "subject commit")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        manifest = load_manifest(manifest_path)
        before = _decoy_state(decoy)
        exported = {"GIT_DIR": os.path.join(decoy, ".git"),
                    "GIT_INDEX_FILE": os.path.join(decoy, ".git", "index")}
        out = io.StringIO()
        refused = ""
        into = os.path.join(box, "mutants")
        os.makedirs(into)
        planted = ""
        with _env_as(exported):
            try:
                preconditions(manifest.census,
                              Roots(root=subject, work=box, clone=None), out)
            except Refusal as refusal:
                refused = str(refusal)
            try:
                clone = clone_subject(subject, into, "decoy")
                plant_mutant(clone, Mutant("decoy", "a.txt", "beta", "gamma"))
                planted = pathlib.Path(clone, "a.txt").read_text(
                    encoding="utf-8")
            except Refusal as refusal:
                planted = f"refused: {refusal}"
            made = _repo_of(fresh, "the fresh commit")
        has_git = os.path.isdir(os.path.join(fresh, ".git"))
        after = _decoy_state(decoy)
    line = out.getvalue().strip()
    named = sha[:7] in line and decoy_sha[:7] not in line and not refused
    check(label,
          named and planted == "alpha\ngamma\n" and made[0] == 0
          and has_git and after == before,
          f"{ACTUAL}the precondition printed {_one_line(line, 120)!r}"
          f"{' and refused: ' + _one_line(refused, 200) if refused else ''}"
          f" (subject {sha[:7]}, decoy {decoy_sha[:7]}); the mutant -> "
          f"{_one_line(planted, 200)!r}; `_repo_of` exited {made[0]} and "
          f"the fresh directory has a `.git`={has_git}; the decoy's HEAD "
          f"{before[0][:7]} -> {after[0][:7]}, index "
          f"{'unchanged' if after[1] == before[1] else 'CHANGED'}, status "
          f"{before[2]!r} -> {after[2]!r}",
          next="Every git golden-census starts runs under `census.git_env`'s "
               "environment, which drops the variables `git rev-parse "
               "--local-env-vars` names: `run._in_cache`, "
               "`census._git_checkout`, `mutants._git` and `proof._repo_of` "
               "pass it as `env=`.")


# ---------------------- the block of a child that ran and failed (ddddddd)

#: Arm `ddddddd`'s subject: it writes the file its surface `writes` and
#: prints one line, so a counter has a written file to be handed.
_ABOUT_SUBJECT = '''\
import sys

with open(sys.argv[1], "w", encoding="utf-8") as made:
    made.write("{}\\n")
print("written")
'''

#: A setup step or a counter of arm `ddddddd`: it prints what the state
#: plants and ends as the state says. `<here>` in what it says on standard
#: error is its own directory, the subject root, as the machine spells it.
_ABOUT_CHILD = """\
import os
import signal
import sys

sys.stdout.write({printed!r})
sys.stderr.write({said!r}.replace(
    "<here>", os.path.dirname(os.path.abspath(__file__))))
sys.stdout.flush()
sys.stderr.flush()
{ends}
"""

_ABOUT_MANIFEST = _subject("about", '["<PYTHON>", "subject.py"]') + '''
[inputs.one]
args     = []
surfaces = ["out"]

[surfaces.out]
args   = ["<WRITES>"]
writes = "<WORK>/out.json"
'''

_ABOUT_STEP = ('needs = ["prep"]\n\n[[setup]]\nname    = "prep"\n'
               'command = ["{program}", "<HERE>/child.py", "planted"]\n')

_ABOUT_COUNTER = 'counter = ["{program}", "<HERE>/child.py", "<WRITES>"]\n'

_ABOUT_CENSUS = _STUB_ENVIRONMENT + _STUB_WORK_FOLD + '''
[[input]]
name        = "the tree is a git checkout"
disposition = "precondition"
check       = "git-checkout"
clean       = true
finding     = "planted: a capture names the revision it was taken at"
'''

#: The row a state of a `command` precondition adds to the census: its name
#: and its `expect` are the state's, by `_ABOUT_EXPECTS`.
_ABOUT_COMMAND = '''
[[input]]
name        = "{name}"
disposition = "precondition"
check       = "command"
command     = ["{program}", "<ROOT>/child.py", "planted"]
expect      = "{expect}"
finding     = "planted: a capture depends on what this command made"
'''

#: What a state plants, for each row of `_ABOUT_COMMAND`: `command` the row
#: that expects `exit 0`, and `empty` the row that expects `empty stdout`;
#: each the row's name and its `expect`.
_ABOUT_EXPECTS = {
    "command": ("the planted command exits 0", "exit 0"),
    "empty": ("the planted command prints nothing", "empty stdout"),
}

#: A program no state's `PATH` holds.
_ABOUT_ABSENT = "no-such-program-ddddddd"

#: The lines of a block under its first: the environment a step or a
#: counter was given, and the line of a git, which is given none.
_ABOUT_GIVEN = ("\nthe environment it was built with (2 variable(s)):"
                "\n  GOLDEN_CENSUS_CHILD=1"
                "\n  PATH=<passed through, len(<box>/bin) characters>")
_ABOUT_OWN = ("\nthe environment: none — this command runs under "
              "golden-census's own environment rather than one a census "
              "built")

_ABOUT_STATUS = ("precondition 'the tree is a git checkout' (check "
                 "git-checkout, clean = true): `git status --porcelain` ")

#: The argv of the precondition's `git status`, as a `ran:` line names it.
_GIT_STATUS_RAN = " ".join(git_command("-C", "<box>", "status", "--porcelain",
                                       GIT_UNTRACKED))

#: What the sentence of a `command` precondition opens with: the row, and
#: the argv that ran, joined with spaces.
_ABOUT_ROW = ("precondition 'the planted command exits 0' (check command, "
              "expect exit 0): <PYTHON> <box>/child.py planted ")

#: The same, of the row that expects `empty stdout`.
_ABOUT_EMPTY = ("precondition 'the planted command prints nothing' (check "
                "command, expect empty stdout): <PYTHON> <box>/child.py "
                "planted ")

#: What the control's text is: the last line of a capture that refused
#: nothing.
_ABOUT_COMPLETE = "not refused, and the log ends: capture complete"

#: The state of a `command` precondition whose output is not UTF-8: its
#: sentence names the program folded, and its `next:` line is the row's,
#: `census.UNDECODED_NEXT`, never the subject's.
_ABOUT_UNDECODED = ("a `command` precondition whose standard output is not "
                    "UTF-8")

#: The state of a `git-checkout` precondition whose `git log` prints a
#: byte that is not UTF-8: its `next:` line is the precondition row's too,
#: `census.UNDECODED_NEXT`, for no reader wraps golden-census's own git.
_ABOUT_UNDECODED_GIT = ("a `git log` whose standard output is not UTF-8, "
                        "under `census`")

#: The state of a `command` precondition whose program is not there: its
#: `next:` line is `core.launch`'s own, which names PATH, and never
#: `census.UNDECODED_NEXT`.
_ABOUT_ABSENT_ROW = "a `command` precondition whose program is not there"

#: Every state of arm `ddddddd`: its name in the detail; the command that
#: runs it (`capture`, or `census`); what is planted (`step`, `counter`,
#: `command` or `empty` for a row of `_ABOUT_COMMAND`, or the subcommand of the
#: planted git) and the program a step, a counter or that row names; what
#: the planted child prints on standard output and on
#: standard error, and how it ends; and the text the refusal must be, its
#: `next:` line left out. Where the program is `_ABOUT_ABSENT` the text is
#: the block alone: the sentence over it is `core.launch`'s and carries the
#: system's own words.
_ABOUT_STATES = (
    ("the control, where the step, the counter and every git answer",
     "capture", "", "<PYTHON>", '{"n": 1}\n', "", _EXITS.format(code=0),
     _ABOUT_COMPLETE),
    ("a setup step that exits 3 and prints text naming its directory",
     "capture", "step", "<PYTHON>", "",
     "planted: the step failed in <here>\n", _EXITS.format(code=3),
     "[[setup]] 'prep' exited 3: planted: the step failed in <box>"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_GIVEN),
    ("a setup step that a signal ends",
     "capture", "step", "<PYTHON>", "", "planted: the step was ended\n",
     _SIGNALS_ITSELF,
     f"[[setup]] 'prep' was ended by signal {int(signal.SIGTERM)}: "
     "planted: the step was ended"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_GIVEN),
    ("a setup step that exits 3 and prints no text",
     "capture", "step", "<PYTHON>", "", " \n", _EXITS.format(code=3),
     "[[setup]] 'prep' exited 3, it printed no text on stderr"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_GIVEN),
    ("a setup step whose program is not there",
     "capture", "step", _ABOUT_ABSENT, "", "", "",
     f"about to run: {_ABOUT_ABSENT} <box>/child.py planted"
     + _ABOUT_GIVEN),
    ("a counter that a signal ends and that prints no text",
     "capture", "counter", "<PYTHON>", "", "", _SIGNALS_ITSELF,
     "[surfaces.out] counter was ended by signal "
     f"{int(signal.SIGTERM)}, it printed no text on stderr"
     "\nran: <PYTHON> <box>/child.py <work>/out.json" + _ABOUT_GIVEN),
    ("a counter that exits 0 and prints text that is not JSON",
     "capture", "counter", "<PYTHON>", "planted\n", "",
     _EXITS.format(code=0),
     "[surfaces.out] counter did not print a JSON object: Expecting "
     "value: line 1 column 1 (char 0)"
     "\nran: <PYTHON> <box>/child.py <work>/out.json" + _ABOUT_GIVEN),
    ("a counter that exits 0 and prints a JSON list",
     "capture", "counter", "<PYTHON>", "[1]\n", "", _EXITS.format(code=0),
     "[surfaces.out] counter printed list, not a JSON object"
     "\nran: <PYTHON> <box>/child.py <work>/out.json" + _ABOUT_GIVEN),
    ("a counter that exits 3 and prints text naming its directory",
     "capture", "counter", "<PYTHON>", "",
     "planted: the counter failed in <here>\n", _EXITS.format(code=3),
     "[surfaces.out] counter exited 3: planted: the counter failed in <box>"
     "\nran: <PYTHON> <box>/child.py <work>/out.json" + _ABOUT_GIVEN),
    ("a counter whose program is not there",
     "capture", "counter", _ABOUT_ABSENT, "", "", "",
     f"about to run: {_ABOUT_ABSENT} <box>/child.py <work>/out.json"
     + _ABOUT_GIVEN),
    ("a `git status` that lists a path, under `capture`",
     "capture", "status", "", "?? planted.txt\n", "",
     _EXITS.format(code=0),
     _ABOUT_STATUS + "in <box> printed '?? planted.txt'. planted: a capture "
     "names the revision it was taken at"
     "\nran: " + _GIT_STATUS_RAN
     + _ABOUT_OWN),
    ("a `git status` that exits 3, under `capture`",
     "capture", "status", "", "", "fatal: planted status\n",
     _EXITS.format(code=3),
     _ABOUT_STATUS + "exited 3 in <box>, so its standard output was not "
     "read — git said 'fatal: planted status'. planted: a capture names "
     "the revision it was taken at"
     "\nran: " + _GIT_STATUS_RAN
     + _ABOUT_OWN),
    ("a `git rev-parse` that exits 128, under `capture`",
     "capture", "rev-parse", "", "", "fatal: planted rev-parse\n",
     _EXITS.format(code=128),
     "precondition 'the tree is a git checkout' (check git-checkout): "
     "`git rev-parse --is-inside-work-tree` exited 128 in <box>, so its "
     "standard output was not read — git said 'fatal: planted "
     "rev-parse'. planted: a capture names the revision it was taken at"
     "\nran: " + " ".join(git_command("-C", "<box>", "rev-parse",
                                     "--is-inside-work-tree"))
     + _ABOUT_OWN),
    ("a `git status` that lists a path, under `census`",
     "census", "status", "", "?? planted.txt\n", "",
     _EXITS.format(code=0),
     _ABOUT_STATUS + "in <box> printed '?? planted.txt'. planted: a capture "
     "names the revision it was taken at"
     "\nran: " + _GIT_STATUS_RAN
     + _ABOUT_OWN),
    ("a `command` precondition that exits 3 and prints text naming its "
     "directory",
     "capture", "command", "<PYTHON>", "",
     "planted: the command failed in <here>\n", _EXITS.format(code=3),
     _ABOUT_ROW + "exited 3: planted: the command failed in <box>"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_OWN),
    (_ABOUT_ABSENT_ROW,
     "capture", "command", _ABOUT_ABSENT, "", "", "",
     f"about to run: {_ABOUT_ABSENT} <box>/child.py planted" + _ABOUT_OWN),
    ("a `command` precondition that a signal ends and that prints no text",
     "capture", "command", "<PYTHON>", "", "", _SIGNALS_ITSELF,
     _ABOUT_ROW + f"was ended by signal {int(signal.SIGTERM)}, it printed "
     "no text on stderr"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_OWN),
    ("a `command` precondition expecting empty stdout that exits 0 and "
     "prints nothing",
     "capture", "empty", "<PYTHON>", "", "", _EXITS.format(code=0),
     _ABOUT_COMPLETE),
    ("a `command` precondition expecting empty stdout that exits 0 and "
     "prints text",
     "capture", "empty", "<PYTHON>", "planted\n", "", _EXITS.format(code=0),
     _ABOUT_EMPTY + "printed 'planted'"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_OWN),
    ("a `command` precondition expecting empty stdout that exits 3 and "
     "prints nothing on stdout",
     "capture", "empty", "<PYTHON>", "", "planted: the command failed\n",
     _EXITS.format(code=3),
     _ABOUT_EMPTY + "exited 3: planted: the command failed"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_OWN),
    ("a `command` precondition expecting empty stdout that a signal ends "
     "and that prints no text",
     "capture", "empty", "<PYTHON>", "", "", _SIGNALS_ITSELF,
     _ABOUT_EMPTY + f"was ended by signal {int(signal.SIGTERM)}, it printed "
     "no text on stderr"
     "\nran: <PYTHON> <box>/child.py planted" + _ABOUT_OWN),
    (_ABOUT_UNDECODED,
     "census", "command", "<PYTHON>", "", "",
     "sys.stdout.buffer.write(b'planted \\xff\\n'); sys.exit(0)",
     "the precondition command '<PYTHON>' ran and printed a byte no UTF-8 "
     "decoder can read: 0xff at byte offset 8 of its standard output "
     "(invalid start byte).\nran: <PYTHON> <box>/child.py planted"
     + _ABOUT_OWN),
    (_ABOUT_UNDECODED_GIT,
     "census", "log", "", "", "",
     "sys.stdout.buffer.write(b'abc1234 planted \\xff\\n'); sys.exit(0)",
     "the precondition command 'git' ran and printed a byte no UTF-8 "
     "decoder can read: 0xff at byte offset 16 of its standard output "
     "(invalid start byte).\nran: "
     + " ".join(git_command("-C", "<box>", "log", "-1", "--oneline"))
     + _ABOUT_OWN),
)

#: The two states whose refusals carry one `next:` line: a `command`
#: precondition that exits 3, under `exit 0` and under `empty stdout`.
_ABOUT_SAME_NEXT = ("a `command` precondition that exits 3 and prints text "
                    "naming its directory",
                    "a `command` precondition expecting empty stdout that "
                    "exits 3 and prints nothing on stdout")


def _about_text(printed: str, base: str, block_alone: bool) -> str:
    """The refusal in `printed`, the text of a `core.refusal_text`, as the
    states of arm `ddddddd` spell it: without the word `REFUSED`, the
    `next:` line and the margin of the block; `base`, the state's own
    directory, written `<box>` however the path in front of its last two
    names is spelled or folded, the work directory of the run `<work>`,
    and the interpreter of this run, which a sentence that prints an argv
    spells whole, `<PYTHON>`. With `block_alone`, the lines under the first.

    The block folds a value before it cuts it, and `<base>/bin` folds to the
    work directory's token, so under a temp root of any width the `PATH`
    line is whole.
    """
    lines = [line for line in printed.splitlines()
             if not line.startswith("  next: ")]
    lines = [line[2:] if line.startswith("  ") else line for line in lines]
    text = "\n".join(lines).removeprefix("REFUSED: ")
    text = text.replace(sys.executable, "<PYTHON>")
    # `PATH` is passed through and prints by name and length; its length is
    # the machine's, so it is asserted as `len(<box>/bin)` or not at all.
    text = text.replace(
        f"<passed through, {len(os.path.join(base, 'bin'))} characters>",
        "<passed through, len(<box>/bin) characters>")
    text = text.replace(
        f"HOME=<passed through, {len(os.environ.get('HOME', ''))} characters>",
        "HOME=<passed through, len(HOME) characters>")
    ends = os.sep.join(base.split(os.sep)[-2:])
    text = re.sub(r"[^\s'=]*" + re.escape(ends), "<box>", text)
    text = re.sub(r"[^\s'=]*golden-census-[^/\s]+(?=/out\.json)", "<work>",
                  text)
    return text.partition("\n")[2] if block_alone else text


def _named_unfolded(printed: str, base: str) -> str:
    """The suffix a refusal's sentence in `printed` earns when it names the
    state's directory `base`, or the interpreter of this run, as the
    machine spells it, and "" when it does not: the block under it folds
    both, and so must the sentence, the stderr of a child it quotes
    included.

    `_about_text` writes `base` as `<box>` however it is spelled or folded,
    and the interpreter as `<PYTHON>`, so the text it returns cannot tell a
    sentence that folded them from one that printed them; this reads the
    raw first line.
    """
    first = printed.partition("\n")[0]
    if any(form in first for form in path_forms(base)):
        return " [the sentence names the subject root unfolded]"
    if sys.executable in first:
        return " [the sentence names the interpreter unfolded]"
    return ""


def _about_state(base: str, command: str, planted: str, program: str,
                 child: str, git: str) -> tuple[str, str]:
    """What one state of arm `ddddddd` refuses with, through
    `_about_text`, or what it printed last when it refused nothing; and the
    refusal's `next:` sentence, "" where it refused nothing.

    `base` is given the subject, the census, the manifest, the child a
    step, a counter or a `command` precondition of either `expect` runs,
    and `bin/git`, and
    `PATH` is `<base>/bin` alone while the command runs. `capture` is
    called as `cli` calls it; `census` is the real `main`.
    """
    # The counter's key first: `_ABOUT_STEP` opens a table of its own.
    parts = {"": (_ABOUT_COUNTER, _ABOUT_STEP), "step": (_ABOUT_STEP,),
             "counter": (_ABOUT_COUNTER,)}.get(planted, ())
    front = os.path.join(base, "bin")
    os.makedirs(front)
    path = _scratch(
        base, manifest_text=_ABOUT_MANIFEST + "".join(
            part.format(program=program) for part in parts),
        census_text=_ABOUT_CENSUS + (
            _ABOUT_COMMAND.format(program=program,
                                  name=_ABOUT_EXPECTS[planted][0],
                                  expect=_ABOUT_EXPECTS[planted][1])
            if planted in _ABOUT_EXPECTS else ""),
        extra={"subject.py": _ABOUT_SUBJECT, "child.py": child})
    _planted_script(os.path.join(front, "git"), git)
    log = io.StringIO()
    with _env_as({"PATH": front}):
        if command == "census":
            _code, printed = _quietly(main, ["census", "--manifest", path])
            at = printed.find("REFUSED: ")
            if at < 0:
                return ("not refused, and the log ends: "
                        + _one_line(printed, DIFFERENCE)[-DIFFERENCE:], "")
            return (_about_text(printed[at:], base, False)
                    + _named_unfolded(printed[at:], base),
                    next((line.removeprefix("  next: ")
                          for line in printed[at:].splitlines()
                          if line.startswith("  next: ")), ""))
        try:
            capture(load_manifest(path), os.path.join(base, "out"), log)
        except Refusal as refused:
            return (_about_text(refusal_text(refused), base,
                                program == _ABOUT_ABSENT)
                    + _named_unfolded(refusal_text(refused), base),
                    refused.next)
    return ("not refused, and the log ends: "
            + (log.getvalue().strip().splitlines() or [""])[-1].strip(), "")


def _about_moved(said: str, want: str) -> str:
    """The lines of `said` that are not the line `want` has at the same
    place, as one line of a detail, and how many lines `said` is short of
    `want` where it is."""
    got, wanted = said.splitlines(), want.splitlines()
    moved = [line.strip() for at, line in enumerate(got)
             if at >= len(wanted) or line != wanted[at]]
    if len(got) < len(wanted):
        moved.append(f"({len(got)} line(s), where {len(wanted)} are wanted)")
    return " | ".join(moved)[:3 * DIFFERENCE]


def _about_ran_control(check: CheckRow, skip: SkipRow) -> None:
    """(ddddddd) a refusal over a child that RAN carries the block of that
    child, and its sentence says how the child ended.

    A capture opens its widest `attaching` window over the SUBJECT's
    command, and a window per row over the row's. A refusal raised outside
    every narrower window leaves through one of those two and is given its
    block: the subject's argv, and `not built yet` for an environment that
    was built. So a setup step, a counter and a precondition each test
    how their child ended INSIDE a window of their own, which describes
    the child that ran, and a precondition's block is the same under
    `census`, which opens no window over any command.

    Every state is driven through the command a reader types: `capture`
    as `cli` calls it, and the real `main` for `census`. Each has a
    directory of its own holding a subject, a manifest, a census and a
    child the arm wrote, and `PATH` is that directory's `bin` alone, where
    the arm plants a `git` the interpreter of this run reads — so the arm
    claims the same thing where `git` is not on PATH. Where the system
    cannot run the planted script at all, the arm is a disclosed SKIP.

    The texts are asserted WHOLE, the `next:` line left out: the sentence,
    the first line of the block, and every line of the environment under
    it. The `next:` lines of one pair are asserted equal and not empty
    (`_ABOUT_SAME_NEXT`): a `command` precondition that exits 3 is told
    what to do in the same words under either `expect`. A sentence that
    names the state's directory as the machine spells it, where the block
    folds it, is a mismatch (`_named_unfolded`): a `git-checkout` sentence,
    and the stderr a step, a counter or a `command` precondition prints
    naming its own directory, which the sentence quotes; so is a sentence
    naming the interpreter unfolded. A `command` precondition whose output
    is not UTF-8 is refused in `core.launch`'s sentence, its program folded
    as `<PYTHON>`, and its `next:` line is asserted to be the precondition
    row's (`census.UNDECODED_NEXT`), never the subject's; so is that of a
    `git-checkout` row's `git log` whose output is not UTF-8, and a
    `command` row whose program is not there keeps `launch`'s. For a child that
    would not start the block alone is asserted: the sentence over it is
    `core.launch`'s and holds the system's own words.
    """
    label = ("ddddddd  a refusal over a child that RAN carries the block "
             "of THAT child — never the block of the subject's command, "
             "which the caller's window would give it — and its sentence "
             "says how the child ended: a `[[setup]]` step that exits "
             "non-zero and prints text naming its own directory, whose "
             "sentence is `exited`, its exit code and after a colon its "
             "words, that directory folded as the block folds it, over a "
             "block that "
             "opens `ran:` with the step's expanded argv and holds the "
             "environment the step was given; a step that a signal ended, "
             "which is said with the signal's number and without the word "
             "`exited`; a step that prints no text on stderr, which is "
             "said after a comma and never as a colon with nothing after "
             "it; a step whose program is not there, which was never "
             "started and whose block opens `about to run:`; a counter "
             "that exits non-zero and prints text naming its own directory, "
             "said as the step is; a counter "
             "that a signal ended, one that exits 0 and prints text that "
             "is not JSON, and one that prints a JSON list, each over "
             "`ran:` and the COUNTER's argv; a counter whose program is "
             "not there, over `about to run:`; under `capture` a "
             "`git-checkout` precondition whose `git status` lists a "
             "path, one whose `git status` exits non-zero and one whose "
             "`git rev-parse` exits non-zero, each over `ran:`, that "
             "git's argv and the line of a command that runs under "
             "golden-census's own environment; under `census` the refusal "
             "of that listing, over the block it carries under `capture`; "
             "a `command` precondition that exits non-zero and prints "
             "text naming its own directory, whose sentence is the argv "
             "that ran, `exited`, its exit code and after a colon its "
             "words, folded, over `ran:`, that argv "
             "with its placeholder expanded, and that line; a `command` "
             "precondition whose program is not there, over `about to "
             "run:` and the expanded argv; and a `command` precondition "
             "that a signal ended and that prints no text on stderr, "
             "which is said with the signal's number, without the word "
             "`exited` and after a comma, over `ran:`; and a `command` "
             "precondition that expects empty stdout is refused when it "
             "prints text, quoting it, and when it prints nothing and "
             "exits non-zero or a signal ends it, in the same words as "
             "one that expects exit 0, its `next:` line too, its `expect` "
             "named, each over `ran:` — and passes when it exits 0 and "
             "prints nothing; and under `census` a `command` precondition "
             "whose standard output is not UTF-8, whose sentence names its "
             "program folded, as `<PYTHON>`, over `ran:`, and whose `next:` "
             "is a precondition row's, never the subject's, as is that "
             "of a `git log` whose standard output is not UTF-8, while a "
             "`command` precondition whose program is not there keeps "
             "the `next:` that names PATH. "
             "Every git "
             "is planted by the arm, so it runs where `git` is not on "
             "PATH. The control is a capture whose step, counter and gits "
             "all answer, which completes")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    got: dict[str, str] = {}
    wanted: dict[str, str] = {}
    nexts: dict[str, str] = {}
    with _box("golden-census-about-ran-") as box:
        for number, (called, command, planted, program, printed, said,
                     ends, want) in enumerate(_ABOUT_STATES):
            base = os.path.join(box, f"state-{number}")
            os.makedirs(base)
            git = _PLANTED_GIT.format(
                python=sys.executable,
                sub=(planted if planted in ("status", "rev-parse", "log")
                     else ""),
                printed=printed, said=said, ends=ends or "pass", pin="true")
            if not number:
                # Asked of the script itself, by its path: see `yyyyyy`.
                why = _planted_answer(
                    _planted_script(os.path.join(base, "git"), git), "true")
                if why:
                    skip(label, why)
                    return
            got[called], nexts[called] = _about_state(
                base, command, planted, program,
                _ABOUT_CHILD.format(printed=printed, said=said,
                                    ends=ends or "pass"), git)
            wanted[called] = want
    told = [nexts.get(called, "") for called in _ABOUT_SAME_NEXT]
    same_next = told[0] == told[1] != ""
    undecoded = {called: nexts.get(called, "")
                 for called in (_ABOUT_UNDECODED, _ABOUT_UNDECODED_GIT)}
    absent_path = "on PATH" in nexts.get(_ABOUT_ABSENT_ROW, "")
    check(label,
          got == wanted and same_next and absent_path
          and set(undecoded.values()) == {UNDECODED_NEXT},
          ACTUAL + "; ".join(
              f"{called} -> "
              + ("as the label says" if said == wanted[called]
                 else _about_moved(said, wanted[called]))
              for called, said in got.items())
          + "; the `next:` of the row expecting empty stdout that exits 3 "
          f"is the one of the row expecting exit 0={same_next}"
          + "".join(f"; the `next:` of {called} -> "
                    + ("the precondition row's" if said == UNDECODED_NEXT
                       else repr(said))
                    for called, said in undecoded.items())
          + f"; the `next:` of {_ABOUT_ABSENT_ROW} names PATH="
          f"{absent_path}",
          next="In `run.run_setup`, `run.run_counter`, "
               "`census._git_checkout` and `census._command_check`, keep "
               "the `attaching` window open until the last test of what "
               "the child did, and hand its `Pending` to `launch`, which "
               "alone says the child ended. `census.about_to_run` words "
               "the first line of the block from that record, and "
               "`census._child_failed` the sentence of a step, a counter or a "
               "`command` precondition's command that did not exit 0.")


# ------------------------- the block of a subject that ran and failed (hhhhhhh)

#: Arm `hhhhhhh`'s subject: what it does is its first argument's.
_RAN_SUBJECT = '''\
import os
import sys

mode = sys.argv[1]
if mode == "text":
    print("planted: the subject printed this")
    sys.stderr.write("planted: the subject failed\\n")
    sys.exit(3)
if mode == "bytes-out":
    sys.stdout.buffer.write(b"planted \\xff\\n")
if mode == "bytes-err":
    sys.stderr.buffer.write(b"planted \\xff\\n")
if mode == "bytes-file":
    with open(sys.argv[2], "wb") as made:
        made.write(b"planted \\xff\\n")
if mode == "root":
    print(os.getcwd())
'''

_RAN_MANIFEST = _subject("ran", '["{program}", "subject.py"]') + '''\
{version}
[inputs.one]
args     = []
surfaces = ["out"]

[surfaces.out]
{surface}
'''

#: A matrix surface's three rows: the first prints a byte that is not UTF-8
#: on standard error, and the two after it print text.
_RAN_ROWS = ('[{"label": "a", "args": ["bytes-err"]}, '
             '{"label": "b", "args": ["text"]}, '
             '{"label": "c", "args": ["text"]}]\n')

#: A `regex` fold whose `volatile` group is inside the subject root, which
#: is `<box>/state-<N>`, and whose scope is the row that prints the root.
_RAN_FOLD = '''
[[input]]
name        = "the state number"
disposition = "fold"
kind        = "regex"
pattern     = 'state-(?P<volatile>[0-9]+)'
placeholder = "<STATE>"
scope       = ["one/out"]
finding     = "planted: a fold whose volatile group is inside the subject root"
control     = { sample = "state-1", moved = "state-2" }
'''

#: What the planted git does for `log`: a revision line whose subject holds
#: the byte 0xff, 16 bytes in, and exit 0.
_RAN_LOG = ("sys.stdout.buffer.write(b'abc1234 planted \\xff\\n'); "
            "sys.exit(0)")

#: The sentence `core.launch` says over a child whose output is not UTF-8,
#: launched inside a window: the block under it names the argv, so the
#: sentence does not; it names the stream the byte is in.
_RAN_BYTES = ("ran and printed a byte no UTF-8 decoder can read: 0xff at "
              "byte offset {offset} of its {stream} (invalid start byte).")

#: The same over standard output, the stream every state but the matrix
#: row's prints its byte on.
_RAN_OUT = _RAN_BYTES.replace("{stream}", "standard output")

_RAN_LOG_ARGV = " ".join(git_command("-C", "<box>", "log", "-1",
                                     "--oneline"))

#: Every state of arm `hhhhhhh`: its name in the detail; the command that
#: runs it (`capture`, `census` or `probe`); the program of `[subject]
#: command`; the surface's table, where `{mode}` is none; the `[subject]
#: version` line, or none; whether the census gains `_RAN_FOLD` (`fold`)
#: or `_ABOUT_CENSUS`'s precondition (`git`); and the text the refusal must
#: be, its `next:` line left out, or what the log says of the row. Where
#: the program is `_ABOUT_ABSENT` the text is the block alone.
_RAN_STATES = (
    ("the control, a subject that exits 3 and prints text",
     "capture", "<PYTHON>", 'args = ["text"]', "", "",
     "not refused, and the log says: out: exit 3"),
    ("a row whose standard output is not UTF-8",
     "capture", "<PYTHON>", 'args = ["bytes-out"]', "", "",
     "the subject " + _RAN_OUT.format(offset=8)
     + "\nran: <PYTHON> subject.py bytes-out" + _ABOUT_GIVEN),
    ("a row whose written file is not UTF-8",
     "capture", "<PYTHON>",
     'args = ["bytes-file", "<WRITES>"]\nwrites = "<WORK>/out.json"', "", "",
     "one/out writes <WORK>/out.json — not text: 0xff at byte offset 8 "
     "(invalid start byte). golden-census records text — a written file "
     "is read, normalized and compared line by line, and bytes it cannot "
     "decode have no golden and no diff."
     "\nran: <PYTHON> subject.py bytes-file <work>/out.json" + _ABOUT_GIVEN),
    ("a row whose text a `regex` fold refuses",
     "capture", "<PYTHON>", 'args = ["root"]', "", "fold",
     "census <box>/census.toml: row 'the state number' would rewrite the "
     "subject root's own path in the text of one/out: its pattern "
     "'state-(?P<volatile>[0-9]+)' replaces '{number}'. A regex fold sees "
     "the raw text, before the built-in path folds, so the root fold would "
     "no longer recognize what is left of the root, and the rows that "
     "print it would record a path nobody can read back."
     "\nran: <PYTHON> subject.py root" + _ABOUT_GIVEN),
    ("a `tallies` surface whose standard output is not UTF-8",
     "capture", "<PYTHON>",
     'kind    = "tallies"\nargs    = ["bytes-out", "<WRITES>"]\n'
     'writes  = "<WORK>/out.json"\nrule    = "="\nverdict = "^passed$"',
     "", "",
     "the subject " + _RAN_OUT.format(offset=8)
     + "\nran: <PYTHON> subject.py bytes-out <work>/out.json" + _ABOUT_GIVEN),
    ("a matrix row whose standard error is not UTF-8",
     "capture", "<PYTHON>",
     'kind        = "matrix"\ninclude     = "rows.json"\n'
     'record_argv = ["the rows of rows.json"]', "", "",
     "matrix row 'a' " + _RAN_BYTES.format(offset=8, stream="standard error")
     + "\nran: <PYTHON> subject.py bytes-err" + _ABOUT_GIVEN),
    ("a `version` run whose standard output is not UTF-8",
     "capture", "<PYTHON>", 'args = ["text"]', 'version = ["bytes-out"]', "",
     "the subject " + _RAN_OUT.format(offset=8)
     + "\nran: <PYTHON> subject.py bytes-out" + _ABOUT_GIVEN),
    ("a row whose program is not there",
     "capture", _ABOUT_ABSENT, 'args = ["text"]', "", "",
     f"about to run: {_ABOUT_ABSENT} subject.py text" + _ABOUT_GIVEN),
    ("a matrix row whose program is not there",
     "capture", _ABOUT_ABSENT,
     'kind        = "matrix"\ninclude     = "rows.json"\n'
     'record_argv = ["the rows of rows.json"]', "", "",
     f"about to run: {_ABOUT_ABSENT} subject.py bytes-err" + _ABOUT_GIVEN),
    ("a `git log` whose output is not UTF-8, under `capture`",
     "capture", "<PYTHON>", 'args = ["text"]', "", "git",
     "the precondition command 'git' " + _RAN_OUT.format(offset=16)
     + "\nran: " + _RAN_LOG_ARGV + _ABOUT_OWN),
    ("a `git log` whose output is not UTF-8, under `census`",
     "census", "<PYTHON>", 'args = ["text"]', "", "git",
     "the precondition command 'git' " + _RAN_OUT.format(offset=16)
     + "\nran: " + _RAN_LOG_ARGV + _ABOUT_OWN),
    ("a command `probe` runs whose output is not UTF-8",
     "probe", "<PYTHON>", 'args = ["text"]', "", "",
     "the probed command (run 1) " + _RAN_OUT.format(offset=8)
     + "\nran: <PYTHON> <box>/subject.py bytes-out <probe>/out-1"
     "\nthe environment it was built with (6 variable(s)):"
     "\n  COLUMNS=80\n  GOLDEN_CENSUS_CHILD=1"
     "\n  HOME=<passed through, len(HOME) characters>"
     "\n  PATH=<passed through, len(<box>/bin) characters>"
     "\n  SOURCE_DATE_EPOCH=0\n  TMPDIR=<TMPDIR>"),
)


def _ran_state(base: str, command: str, program: str, surface: str,
               version: str, census: str, git: str) -> str:
    """What one state of arm `hhhhhhh` refuses with, through
    `_about_text`, with the probe's work directory written `<probe>`; or,
    where it refused nothing, the log's line of the row.

    `base` is given the subject, the census, the manifest, the matrix's
    rows and `bin/git`, and `PATH` is `<base>/bin` alone while the command
    runs. `capture` is called as `cli` calls it; `census` and `probe` are
    the real `main`.
    """
    front = os.path.join(base, "bin")
    os.makedirs(front)
    path = _scratch(
        base,
        manifest_text=_RAN_MANIFEST.format(program=program, surface=surface,
                                           version=version),
        census_text=(_ABOUT_CENSUS if census == "git" else
                     _STUB_ENVIRONMENT + _STUB_WORK_FOLD
                     + (_RAN_FOLD if census == "fold" else "")),
        extra={"subject.py": _RAN_SUBJECT, "rows.json": _RAN_ROWS})
    _planted_script(os.path.join(front, "git"), git)
    log = io.StringIO()
    with _env_as({"PATH": front}):
        if command != "capture":
            argv = (["census", "--manifest", path] if command == "census"
                    else ["probe", sys.executable,
                          os.path.join(base, "subject.py"), "bytes-out",
                          "<WRITES>"])
            _code, printed = _quietly(main, argv)
            at = printed.find("REFUSED: ")
            if at < 0:
                return ("not refused, and the log ends: "
                        + _one_line(printed, DIFFERENCE)[-DIFFERENCE:])
            return re.sub(r"[^\s'=]*golden-census-probe-[^/\s]+", "<probe>",
                          _about_text(printed[at:], base, False))
        try:
            capture(load_manifest(path), os.path.join(base, "out"), log)
        except Refusal as refused:
            return _about_text(refusal_text(refused), base,
                               program == _ABOUT_ABSENT)
    lines = [line.strip() for line in log.getvalue().splitlines()]
    return "not refused, and the log says: " + next(
        (line for line in lines if line.startswith("out:")),
        lines[-1] if lines else "")


# ---------------------- a passed-through variable in a block (rrrrrrrrr)

#: The secret of arm `rrrrrrrrr`: a token a census passes through because
#: its subject needs it. Its characters are what a refusal must never print.
_PASSED_TOKEN = "sk-live-THISISASECRETVALUE1234567890"

#: What of the token's characters no line of the run may hold.
_PASSED_SECRET = "THISISASECRET"

_PASSED_CENSUS = '''\
[environment]
inherit     = false
passthrough = ["DEMO_API_TOKEN"]
''' + _STUB_WORK_FOLD + '''
[[input]]
name        = "the pinned width"
disposition = "pin"
variable    = "COLUMNS"
value       = "80"
finding     = "planted: the block prints a pin whole"
control     = { shape = "vary", surface = "one/out", value = "40" }
'''

#: The subject of arm `rrrrrrrrr`: it writes the file its surface `writes`
#: and prints the width it was given, so the pin's `vary` control moves it.
_PASSED_SUBJECT = '''\
import os
import sys

with open(sys.argv[1], "w", encoding="utf-8") as made:
    made.write(os.environ.get("COLUMNS", "") + "\\n")
print("written")
'''

_PASSED_MANIFEST = _ABOUT_MANIFEST + '''\
env    = { SURFACE_VARIABLE = "surface-value" }
''' + _ABOUT_COUNTER.format(program="<PYTHON>")


def _passed_through_control(check: CheckRow) -> None:
    """(rrrrrrrrr) a refusal's environment block says which variables the
    child got, and a passed-through variable is the user's: it prints by
    name and length, never its value.

    A census's `passthrough` list names a variable the subject needs, a
    token say, and `about_to_run` printed every variable of the built
    environment as `NAME=value`, into the text a reader quotes into a
    report. A variable the list names now prints as `NAME=<passed through,
    N characters>`, N the length of the value as the child got it; a pin
    and a surface's own `env` print whole. The plant is a census that
    passes `DEMO_API_TOKEN` through and pins `COLUMNS`, a surface with its
    own `env`, and a counter that exits 3, run with the token set in this
    process's environment.
    """
    label = ("rrrrrrrrr  a refusal's environment block prints a "
             "passed-through variable by name and length and never its "
             "value, while a pin and a surface's own env print whole")
    wanted = (f"DEMO_API_TOKEN=<passed through, {len(_PASSED_TOKEN)} "
              "characters>")
    with _box("golden-census-passed-through-") as box:
        path = _scratch(
            box, manifest_text=_PASSED_MANIFEST, census_text=_PASSED_CENSUS,
            extra={"subject.py": _PASSED_SUBJECT,
                   "child.py": _ABOUT_CHILD.format(
                       printed="", said="planted\n", ends="sys.exit(3)")})
        log = io.StringIO()
        with _env_as({"DEMO_API_TOKEN": _PASSED_TOKEN}):
            try:
                capture(load_manifest(path), os.path.join(box, "out"), log)
                printed = "(not refused)"
            except Refusal as refused:
                printed = refusal_text(refused)
    lines = [line.strip() for line in printed.splitlines()]
    named = wanted in lines
    whole = "COLUMNS=80" in lines and "SURFACE_VARIABLE=surface-value" in lines
    never = _PASSED_SECRET not in printed + log.getvalue()
    check(label, named and whole and never,
          f"{ACTUAL}the line {wanted!r} is there={named}; the pin "
          f"and the surface's variable print whole={whole}; "
          f"{_PASSED_SECRET} appears nowhere in the run={never}; the "
          f"refusal's block: {_one_line(printed, 3 * DIFFERENCE)!r}",
          next="`census.about_to_run` prints the built environment and is "
               "given the census, whose `passthrough` names the variables "
               "that are the user's; a pin or a surface's `env` is "
               "golden-census's to print.")


def _subject_ran_control(check: CheckRow, skip: SkipRow) -> None:
    """(hhhhhhh) a refusal raised after the SUBJECT ran carries a block
    that opens `ran:`.

    `core.launch` marks the record it is handed when the child ends, and
    `census.about_to_run` words the first line from that record: the
    subject's run, a matrix row, the `version` run, the `git log` of a
    `git-checkout` precondition and the command `probe` runs are each
    launched with the record of the window they are made in — a matrix
    row with a record and a window of its own, because its rows run at
    once. The matrix has three rows, the one that fails first: a record
    shared by the rows holds the argv of the row that was given it last.
    Where the rows run one after another — a machine with one processor
    — a shared record cannot be seen, and the arm then holds the rest.
    A refusal raised after one of them ended — `launch`'s own over a
    byte that is not UTF-8, `run.run_subject`'s over the written file, a
    fold's over what the subject printed — is given a block that opens
    `ran:`, and one that would not start a block that opens `about to
    run:` with the argv expanded. `launch`'s sentence over a byte that is
    not UTF-8 spells no argv where the block under it does: the block's is
    folded, and a second spelling in the sentence would be the unfolded one.

    Every state is driven through the command a reader types: `capture`
    as `cli` calls it, and the real `main` for `census` and `probe`. Each
    has a directory of its own, and `PATH` is that directory's `bin` alone,
    where the arm plants a `git` the interpreter of this run reads, as arm
    `ddddddd` does. Where the system cannot run the planted script at all,
    the arm is a disclosed SKIP. The texts are asserted WHOLE, the `next:`
    line left out; for a program that is not there, the block alone.

    `probe` makes the census's fixed-width directory before it runs
    anything. Where the temp root leaves no room for one, the `probe`
    state is not made: the label loses its clause, and the detail says
    which state was not made and why, in `core.fixed_dir_refusal`'s
    sentence, as `checks_process._probe_precondition` hands it. Where `HOME`
    lies under the temp root, the `probe` state is not made either: the
    block folds the temp root in its `HOME` line before `HOME`, so that line
    cannot read the `<HOME>` the state asserts.
    """
    no_probe = _probe_precondition()
    home = os.environ.get("HOME", "")
    unmade = (f"a probe cannot run here: {no_probe}" if no_probe
              else f"HOME ({home}) lies under the temp root ({temp_base()}), "
                   "so the block's HOME line reads <TMPROOT>/… and never the "
                   "<HOME> this state asserts."
              if home and under(home, temp_base(), strict=False) else "")
    label = ("hhhhhhh  a refusal raised after the SUBJECT ran carries a "
             "block that opens `ran:` — never `about to run:` — with the "
             "argv that ran and the environment it was given, and a "
             "sentence over a byte that is not UTF-8 names that argv "
             "nowhere but in the block: under "
             "`capture`, a row whose standard output is not UTF-8, a row "
             "whose written file is not UTF-8, a row whose text a `regex` "
             "fold refuses, a `tallies` surface whose standard output is "
             "not UTF-8, whose block holds its argv with `<WRITES>` "
             "expanded, a `version` run whose standard output is not "
             "UTF-8, and a matrix row whose "
             "standard error is not UTF-8, whose block holds THAT row's "
             "argv; a `git log` of a `git-checkout` precondition whose "
             "output is not UTF-8, under `capture` and under `census`, "
             "over that git's argv and the line of a command that runs "
             "under golden-census's own environment"
             + ("" if unmade else
                "; and a command `probe` runs whose output is not UTF-8")
             + ". A row and a matrix row whose "
             "program is not there were never started, and their blocks "
             "open `about to run:` with the argv expanded. The control is "
             "a subject that exits 3 and prints text, which is no refusal: "
             "the log says `out: exit 3`")
    got: dict[str, str] = {}
    wanted: dict[str, str] = {}
    not_made: list[str] = []
    with _box("golden-census-subject-ran-") as box:
        for number, (called, command, program, surface, version, census,
                     want) in enumerate(_RAN_STATES):
            base = os.path.join(box, f"state-{number}")
            os.makedirs(base)
            git = _PLANTED_GIT.format(
                python=sys.executable, sub="log" if census == "git" else "",
                printed="", said="", ends=_RAN_LOG, pin="true")
            if not number:
                # Asked of the script itself, by its path: see `yyyyyy`.
                why = _planted_answer(
                    _planted_script(os.path.join(base, "git"), git), "true")
                if why:
                    skip(label, why)
                    return
            if command == "probe" and unmade:
                not_made.append(
                    f"{called} -> SKIPPED, this state was not made: "
                    f"{unmade} Nothing was measured and nothing is claimed "
                    "of it")
                continue
            got[called] = _ran_state(base, command, program, surface,
                                     version, census, git)
            wanted[called] = want.replace("{number}", str(number))
    check(label,
          got == wanted,
          ACTUAL + "; ".join([
              f"{called} -> "
              + ("as the label says" if said == wanted[called]
                 else _about_moved(said, wanted[called]))
              for called, said in got.items()] + not_made),
          next="Hand the `Pending` of the window a run is made in to "
               "`launch`: `run.run_subject` takes it from `run.run_row`, "
               "`capture.record_tallies_surface` and the `version` run; "
               "`capture.record_matrix` launches each row in a window of "
               "its own over a `Pending` of that row; "
               "`census._git_checkout` runs `git log` in a window of its "
               "own; and `probe._one_run` hands the record it holds. "
               "`census.about_to_run` words the block's first line from "
               "that record.")


# --------------------------------------- the platform, planted both ways (eeeee)


def _platform_record_control(check: CheckRow) -> None:
    """(eeeee) `core.Platform` planted as each platform and asserted for
    both, whichever one this run is on.

    The record carries the two facts that differ with the platform — the
    roots user homes live under and the advice a temp root too wide for the
    census's pin earns — and each is asked of a PLANTED platform name, so the
    half about the platform this run is NOT on is exercised rather than
    assumed: `darwin` answers `/Users` and `TMPDIR=$(getconf
    DARWIN_USER_TEMP_DIR)`; `linux` answers `/home` and `/root` and
    `TMPDIR=/tmp`. A home under neither platform's roots adds its own root
    (`/export/home/bob` -> `/export/home`) and a home whose root is `/` adds
    none, `/` being a home root that matches every absolute path there is.
    The control is a platform name the record does not carry, which is a
    REFUSAL naming it rather than a guess; `detect()` is one of the two rows.
    `every_home_root()` is every row's roots at once — what a golden is
    judged against wherever it was captured, since a set recorded on one
    platform and compared on another is judged by one rule or by two. The
    `actual:` line carries every answer.
    """
    label = ("eeeee  `core.Platform` answers for a PLANTED platform as well "
             "as this one: the home roots and the width advice of `darwin` "
             "and `linux`, and a REFUSAL for a name the record lacks")
    # Written out rather than read from `core._PLATFORMS`: that mapping is the
    # OWNER of these two facts, and an arm that asks the owner what the
    # owner says asserts nothing.
    expected: dict[str, tuple[tuple[str, ...], str]] = {
        "darwin": (("/Users",), "TMPDIR=$(getconf DARWIN_USER_TEMP_DIR)"),
        "linux": (("/home", "/root"), "TMPDIR=/tmp"),
    }
    homes = {"darwin": "/Users/someone", "linux": "/home/someone"}
    carried = {
        name: (record.home_roots, record.short_root_advice)
        for name, record in ((each, Platform.for_platform(each, home=homes[each]))
                             for each in expected)}
    third = Platform.for_platform("linux", home="/export/home/bob").home_roots
    slash = Platform.for_platform("linux", home="/root").home_roots
    try:
        Platform.for_platform("plan9", home="/usr/glenda")
        refused = "no refusal"
    except Refusal as refusal:
        refused = refusal_text(refusal)
    everywhere = Platform.every_home_root(home="/Users/someone")
    elsewhere = Platform.every_home_root(home="/export/home/bob")
    here = Platform.detect()
    own = expected.get(here.name, ((), ""))[0]
    check(label,
          carried == expected
          and third == ("/home", "/root", "/export/home")
          and slash == ("/home", "/root")
          and everywhere == ("/Users", "/home", "/root")
          and elsewhere == ("/Users", "/home", "/root", "/export/home")
          and refused.startswith("REFUSED: ") and "'plan9'" in refused
          and here.name == sys.platform
          and here.home_roots[:len(own)] == own and bool(own),
          ACTUAL
          + "; ".join(f"{name} -> {carried[name]}" for name in sorted(carried))
          + f"; a home under neither -> {third}; a home whose root is / -> "
          f"{slash}; every_home_root() -> {everywhere}, and with a home under "
          f"neither -> {elsewhere}; a name the record does not carry -> "
          f"{_one_line(refused, 80)!r}; detect() -> {here.name!r} carrying "
          f"{here.home_roots}",
          next="Derive every field from `core._PLATFORMS` and add a row there "
               "for a platform golden-census is to run on. A field decided at "
               "the site that reads it is a fact about the machine that line "
               "was written on, and no self-check anywhere can go red on it.")


# -------------------- the record's reader, under a planted platform (fffff)


def _platform_readers_control(check: CheckRow, skip: SkipRow) -> None:
    """(fffff) the width refusal's advice, asked of a PLANTED platform rather
    than of this machine.

    The one rule that differs with the platform reads `core.Platform` and
    nothing else, and it is asserted for BOTH platforms on whichever one this
    run is on: under a planted `linux` a temp root too wide for the census's
    pin is refused with `next: … TMPDIR=/tmp`, and under a planted `darwin`
    the same refusal says `TMPDIR=$(getconf DARWIN_USER_TEMP_DIR)`. The
    refusal's own sentence names neither command, so the advice has one owner
    and the reader is given the one for the machine in front of them. The
    plant is a fresh copy of the module with the record it reads rebound, and
    the LAST platform planted is always the one this machine is NOT — so the
    live module, asked the same question afterwards, answers with this
    machine's advice and not the planted one, which is what says the plant
    did not leak into the arms after it. The `actual:` line carries each
    advice.
    """
    label = ("fffff  the width refusal's advice reads `core.Platform` and "
             "nothing else: asserted for BOTH platforms under a plant, and "
             "the live module still answers for this machine afterwards")
    core_copy = _fresh_module("core")
    if core_copy is None:
        # One absence policy (`core.Layout`'s): an install carrying no
        # importable source for a module cannot have a platform planted on it,
        # and a row whose plant cannot be built is a disclosed SKIP.
        skip(label, "this install carries no importable "
                    "`golden_census.core` to plant a platform on; the "
                    "record's reader runs unexercised against the platform "
                    "this machine is not.")
        return
    advice: dict[str, str] = {}
    neutral: dict[str, bool] = {}
    here = Platform.detect()
    # This machine's platform FIRST and the other one LAST, so the record left
    # planted on the copy is always the one the live module must not be
    # answering. Planted the other way round on a Linux machine, the last
    # plant and the live answer would agree and a leak would be invisible.
    other = next(name for name in ("darwin", "linux") if name != here.name)
    for name in (here.name, other):
        record = Platform.for_platform(name, home="/nowhere/someone")
        # A `_detected_platform` answering this one planted record; the
        # default argument binds the record of THIS pass of the loop.
        core_copy._detected_platform = lambda record=record: record
        refusal = core_copy.fixed_dir_refusal("/" + "b" * 59,
                                              FIXED_DIR_WIDTH)
        advice[name] = refusal_text(refusal).splitlines()[-1].strip()
        neutral[name] = record.short_root_advice not in str(refusal)
    # The LIVE module, asked the same question after the plant: it has to
    # answer this machine's advice and not the one left planted. Comparing
    # `detect().name` against `sys.platform` asserted nothing — `detect()`
    # makes that true by construction.
    live_advice = refusal_text(
        fixed_dir_refusal("/" + "b" * 59, FIXED_DIR_WIDTH)
    ).splitlines()[-1].strip()
    planted_last = Platform.for_platform(other,
                                         home="/nowhere/someone")
    no_leak = (here.short_root_advice in live_advice
               and planted_last.short_root_advice not in live_advice)
    check(label,
          advice["darwin"].endswith(
              "TMPDIR=$(getconf DARWIN_USER_TEMP_DIR), or point TMPDIR at any "
              f"directory of at most {widest_root(FIXED_DIR_WIDTH)} characters.")
          and "TMPDIR=/tmp, or point TMPDIR at any directory" in advice["linux"]
          and all(neutral.values())
          and no_leak,
          ACTUAL
          + "; ".join(f"{name} -> {_one_line(advice[name], 90)!r}, the "
                      f"sentence itself names no command: {neutral[name]}"
                      for name in sorted(advice))
          + f"; planted {here.name!r} then {other!r}, and the LIVE module "
          f"then answers {_one_line(live_advice, 90)!r} — this machine's "
          f"advice, not {other!r}'s: {no_leak}",
          next="Read the advice from `core.Platform`. A rule that decides it "
               "at the site that reads it is a rule no run on this machine "
               "can show to be wrong about the other platform.")


# ------------------------------------------- a path is a whole path (dddddd, eeeeee)
#
# Where a path's name ENDS decides what `core.fold` folds, and where a path
# can START decides what the contraband scan counts as a home path. Each is
# one lookaround in `core`, beside `fold`.

#: The subject arms `dddddd` and `eeeeee` capture. `mode.txt` beside it says
#: what it prints: `old` a sibling directory of its own root, `ends` its root
#: where the name ends four ways, `relative` a relative path holding `/home`,
#: and `print:TEXT` the text after the colon, for arm `llllllll`.
_PATH_EDGE_SUBJECT = '''\
import os

mode = open("mode.txt").read().strip()
here = os.getcwd()
if mode == "old":
    print(here + "-old/config.toml")
elif mode == "ends":
    print("at " + here + ".")
    print(here + "/x")
    print(here)
    print(here + ".bak")
elif mode == "under":
    print(here + "/home/x")
elif mode.startswith("print:"):
    print(mode.removeprefix("print:"))
else:
    print("compiled src/home/page.tsx")
'''


def _path_edge(box: str, mode: str,
               census_text: str = _JSON_CENSUS) -> tuple[int, str, str]:
    """Capture the path-edge subject in `box/mode`: `(exit, the recorded
    report.out, the log)`. A contraband hit is a printed refusal and exit 2,
    not a raised one, so the log is where it is read."""
    where = os.path.join(box, mode)
    manifest = load_manifest(_scratch(
        where, manifest_text=_TAIL_MANIFEST, census_text=census_text,
        extra={"stub.py": _PATH_EDGE_SUBJECT, "mode.txt": mode}))
    out = os.path.join(where, "out")
    log = io.StringIO()
    code = capture(manifest, out, log)
    path = os.path.join(out, "_subject", "report.out")
    recorded = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8", newline="") as handle:
            recorded = handle.read()
    return code, recorded, log.getvalue()


def _next_of(log: str) -> str:
    """The `next:` line of the refusal a capture log ends with, or "" when
    it holds none."""
    return next((line.strip().removeprefix("next: ")
                 for line in reversed(log.splitlines())
                 if line.strip().startswith("next: ")), "")


def _name_ends_control(check: CheckRow) -> None:
    """(dddddd) a directory folds only where its name ends.

    `core.fold` replaces a directory only where `core.NAME_ENDS` holds: at
    the end of the text, a `/`, or a character that cannot continue the
    name. `<root>-old` is another directory: a token there — `<REPO>-old` —
    would be a guess, and it is left alone for the contraband scan, whose
    subject-root pattern is unanchored and refuses it by name — in every
    spelling `core.path_forms` names, so a root given through a symlink is
    refused in the resolved spelling a command prints. A `.` ends a name:
    `<root>.bak` folds, and so does `probe`'s output path with `.json` added.

    The refusal's `next:` names what folds what it found: the sibling, which
    no `path` row can fold, is sent to a `regex` fold; the root itself,
    printed under a census with no `path` row for the root, is sent to the
    `path` row with `source = "root"`.

    What the row asserts: a subject printing its root + `-old/config.toml`
    is REFUSED by the contraband scan naming the subject root's absolute
    path, never recorded as `<REPO>-old`; its root before a sentence's `.`,
    before `/x`, at the end of a line and before `.bak` each fold to
    `<REPO>`; `probe`'s fold of its output path + `.json` is `<WRITES>.json`;
    for a root given through a symlink, a subject-root pattern matches the
    resolved root + `-old/x`; the sibling's refusal says in its `next:` that
    a `path` fold cannot name it, and the four ends under a census with no
    `path` row for the root are REFUSED with a `next:` naming the `path` row
    with `source = "root"`; a hit on the work directory under a census with
    no `path` row for it is sent to the row with `source = "work"`, and
    beside a home path the `regex` sentence follows it. The `actual:` line
    carries each.
    """
    label = "dddddd  a directory folds only where its name ends"
    with _box("golden-census-name-ends-") as box:
        old_code, old_recorded, old_log = _path_edge(box, "old")
        ends_code, ends_recorded, _ = _path_edge(box, "ends")
        bare_code, _, bare_log = _path_edge(
            os.path.join(box, "unfolded"), "ends",
            _STUB_ENVIRONMENT + _STUB_WORK_FOLD)
        # The work directory, under a census with a `path` row for the root
        # and none for it, alone and beside a home path.
        workless = load_manifest(_scratch(
            os.path.join(box, "workless"), manifest_text=_TAIL_MANIFEST,
            census_text=_STUB_ENVIRONMENT + _STUB_ROOT_FOLD,
            extra={"stub.py": _PATH_EDGE_SUBJECT, "mode.txt": "ends"})).census
        work_hit = ("_subject/report.out", 1, SOURCE_HITS["work"], box)
        home_hit = ("_subject/report.out", 2, "an absolute home path", "/Users/x")
        work_next = _contraband_next(workless, [work_hit])
        mixed_next = _contraband_next(workless, [work_hit, home_hit])
        target = os.path.join(box, "target")
        os.makedirs(target)
        link = os.path.join(box, "link")
        os.symlink(target, link)
        resolved = os.path.realpath(link) + "-old/x"
        root_patterns = [pattern for label_, pattern in contraband_patterns(
                             Roots(root=link, work=os.path.join(box, "work")))
                         if label_ == "the subject root's absolute path"]
        linked = any(pattern.search(resolved) for pattern in root_patterns)
        work = os.path.join(box, "work")
        written = os.path.join(work, "out-1")
        derived = Handed(root=box, work=work, fixed=None,
                         paths=(written,)).fold(f"wrote {written}.json",
                                                written)
    named = "the subject root's absolute path" in old_log
    sibling_next = _next_of(old_log)
    bare_next = _next_of(bare_log)
    sent = (sibling_next.startswith(
                "Stop the subject printing the path where you can; "
                "otherwise add the census `regex` fold")
            and "A `path` fold cannot name it" in sibling_next
            and bare_code == 2
            and bare_next.startswith('Add a census `path` row with '
                                     '`source = "root"`')
            and "cannot name it" not in bare_next
            and work_next.startswith('Add a census `path` row with '
                                     '`source = "work"`')
            and "regex" not in work_next
            and mixed_next.startswith(work_next.removesuffix(
                " Then capture again."))
            and "For any other line quoted above, stop the subject printing "
            "the path where you can; otherwise add the census `regex` fold"
            in mixed_next)
    check(label,
          old_code == 2 and named and "<REPO>-old" not in old_recorded
          and sent
          and ends_code == 0
          and ends_recorded == "at <REPO>.\n<REPO>/x\n<REPO>\n<REPO>.bak\n"
          and derived == "wrote <WRITES>.json"
          and linked,
          f"{ACTUAL}root-old -> exit {old_code}, the scan named the subject "
          f"root={named}, recorded {old_recorded!r}, next: "
          f"{_one_line(sibling_next, 90)}; the four ends with no root fold "
          f"-> exit {bare_code}, next: {_one_line(bare_next, 90)}; a work "
          f"directory hit with no work fold -> next: {_one_line(work_next, 90)}"
          f", and beside a home path -> {_one_line(mixed_next, 200)}; the four "
          "ends -> exit "
          f"{ends_code}, recorded {ends_recorded!r}; probe's fold -> "
          f"{derived!r}; the symlinked root's "
          f"{len(root_patterns)} subject-root pattern(s) match the resolved "
          f"sibling={linked}",
          next="`core.fold` replaces each form with `re.sub` and "
               "`core.NAME_ENDS` after it. If `<REPO>-old` was recorded, the "
               "lookahead has gone; if an end did not fold, it is too wide. "
               "If the resolved sibling is not matched, "
               "`capture.contraband_patterns` has stopped building its "
               "directories over `core.path_forms`.")


def _temp_root_control(check: CheckRow) -> None:
    """(llllllll) the bare temp root is contraband, with or without its
    closing `/`, and a longer name that begins with it is not.

    The pattern for the temp root asked for `/` and one more character, so a
    subject that printed the root itself, or `<root>/` at the end of a line,
    passed the scan and reached the golden. Asked of planted text through
    `scan_text` with the scan's own temp patterns, and through two real
    captures: a subject printing the bare root, and one printing the root and
    `pad`.

    What the row asserts: the root, the root and its closing `/`, a root
    closed by a full stop, a comma or a parenthesis, `TMPDIR=` and the root,
    and the root and `/x` are one hit each, while the root and `pad`, `-old`,
    `.bak` or `_x` — a name that begins with the root's letters — are none; a
    subject printing the bare root is REFUSED at exit 2 naming the hit as an
    unnormalized temp path, and one printing the root and `pad` captures at
    exit 0 with 0 hits. Unguarded the bare root reached the golden at exit 0.
    The `actual:` line carries each count.
    """
    label = ("llllllll  the temp root counts as an absolute path when it is "
             "printed bare")
    base = temp_base().rstrip("/")
    hits = (base + "/x", base, base + "/", f"root is {base}.", f"({base})",
            f"{base}, then", f"TMPDIR={base}")
    misses = (base + "pad", base + "-old", base + ".bak", base + "_x")
    temp = [(label_, pattern) for label_, pattern
            in contraband_patterns(_control_roots())
            if label_ == "an unnormalized temp path"]
    counted = {text: len(scan_text("planted", text, temp, frozenset()))
               for text in hits + misses}
    captured: dict[str, tuple[int, str]] = {}
    with _box("golden-census-temp-root-") as box:
        for name, printed in (("bare", base), ("padded", base + "pad")):
            where = os.path.join(box, name)
            manifest = load_manifest(_scratch(
                where, manifest_text=_TAIL_MANIFEST, census_text=_JSON_CENSUS,
                extra={"stub.py": _PATH_EDGE_SUBJECT,
                       "mode.txt": "print:" + printed}))
            log = io.StringIO()
            captured[name] = (capture(manifest, os.path.join(where, "out"),
                                      log), log.getvalue())
    bare_code, bare_log = captured["bare"]
    padded_code, padded_log = captured["padded"]
    check(label,
          bool(base) and all(counted[text] >= 1 for text in hits)
          and all(counted[text] == 0 for text in misses)
          and bare_code == 2 and "an unnormalized temp path" in bare_log
          and padded_code == 0 and "0 hit(s)" in padded_log,
          ACTUAL + ", ".join(f"{text!r} -> {count}"
                             for text, count in counted.items())
          + f"; the bare root captured -> exit {bare_code}, named="
          f"{'an unnormalized temp path' in bare_log}; the root and pad -> "
          f"exit {padded_code}, 0 hit(s)={'0 hit(s)' in padded_log}",
          next="`capture.contraband_patterns` builds the temp root's pattern "
               "from `core.path_forms`: the root and `/` and a character, or "
               "the root with an optional `/` and nothing that continues a "
               "name after it.")


def _path_start_control(check: CheckRow) -> None:
    """(eeeeee) a home root counts as an absolute path only where a path can
    start.

    `capture.home_root_pattern` puts `core.PATH_START` in front of the root:
    not after a character that can be inside a path name; an option word
    glued in front of the root, of any length, is consumed with it; and
    `scan_text` sets aside a match right after one of the fold tokens it is
    handed (`core.after_placeholder`) — the caller's vocabulary, never a
    token's shape. Asked of planted text through `scan_text` with the scan's
    own home patterns, and through two real captures: a subject printing a
    relative path, and one printing its root + `/home/x` under a census
    whose root placeholder is `<repo>`, which the capture must hand the
    scan from the census's own `path` rows.

    What the row asserts, with the `misses` and `hits` below spelling each
    text: a relative path, a path after `.`, an option word that ends in a
    letter or a digit before the root, and a path after a token of the fold's
    vocabulary are no hit, while a bare home path, one after `file://`, `=`,
    `-I`, `-L`, `-isystem`, `-Wl,-L`, `>`, `2>`, `(`, a tag outside the
    vocabulary, or an option glued to a token are one hit each; a subject
    printing a relative path captures at exit 0 with 0 hits; and one printing
    its root + `/home/x` under a `<repo>` root fold captures `<repo>/home/x`
    at exit 0 with 0 hits. The `actual:` line carries each count.
    """
    # Concatenated, as `contraband_control`'s tokens are, so this file
    # carries no absolute home path of its own.
    users = "/" + "Users"
    label = ("eeeeee  a home root counts as an absolute path only where a "
             "path can start")
    tokens = frozenset({"<REPO>", "<TMPROOT>", "<SUBJECT_ROOT>", "<repo>"})
    misses = ("src/home/page.tsx", "." + users + "/someone", "foo-I/home/x",
              "3-I/home/x", "<REPO>/home/someone", "<TMPROOT>/home/someone",
              "<SUBJECT_ROOT>/home/x", "<repo>/home/x")
    hits = ("/home/page", "file://" + users + "/someone", "x=/root/y",
            "-I/home/ci/include", "-L" + users + "/someone/lib",
            "cc -isystem/home/ci/include main.c",
            "<string>" + users + "/someone/x</string>",
            "cmd >/home/ci/log.txt", "2>/home/ci/err.log",
            "cc -Wl,-L/home/ci/lib main.o", "(-I/home/ci/include)",
            "<REPO>-I/home/x", "<BR>/home/ci/secret.txt", "<TD>" + users + "/someone/x</TD>",
            "<A>/home/ci/x")
    homes = [(label_, pattern) for label_, pattern
             in contraband_patterns(_control_roots())
             if label_ == "an absolute home path"]
    counted = {text: len(scan_text("planted", text, homes, tokens))
               for text in misses + hits}
    lower = _JSON_CENSUS.replace('placeholder = "<REPO>"',
                                 'placeholder = "<repo>"')
    with _box("golden-census-path-start-") as box:
        code, recorded, log = _path_edge(box, "relative")
        under_code, under_recorded, under_log = _path_edge(box, "under",
                                                           lower)
    scanned = "0 hit(s)" in log
    under_scanned = "0 hit(s)" in under_log
    check(label,
          all(counted[text] == 0 for text in misses)
          and all(counted[text] == 1 for text in hits)
          and code == 0 and scanned
          and recorded == "compiled src/home/page.tsx\n"
          and under_code == 0 and under_scanned
          and under_recorded == "<repo>/home/x\n",
          ACTUAL + ", ".join(f"{text!r} -> {count}"
                                 for text, count in counted.items())
          + f"; the relative path captured -> exit {code}, 0 hit(s)="
          f"{scanned}; the root + /home/x under <repo> -> exit {under_code},"
          f" 0 hit(s)={under_scanned}, recorded {under_recorded!r}",
          next="`capture.home_root_pattern` opens with `core.PATH_START` and "
               "consumes a glued option; `capture.scan_text` asks "
               "`core.after_placeholder` with the tokens the caller folded "
               "with (`census.path_pairs` for a capture). A relative path or "
               "a path under a vocabulary token counted as a hit means one "
               "of them has gone; a real home path missed — after a tag "
               "outside the vocabulary, or glued to an option — means the "
               "rule has narrowed.")
