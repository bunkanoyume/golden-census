"""The arms over what a run PRINTS and what it refuses: the report's one
layout and its tally, the interpreter floor's guard, the exit codes a
document quotes, and the private temp root the leak arms stand on.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import errno
import functools
import inspect
import io
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from typing import Any, NamedTuple

from . import __version__
from .capture import capture, read_capture
from .cli import _unanswered, main
from .compare import read_allow
from .controls import CheckRow, SkipRow
from .core import (
    ACTUAL,
    DIFFERENCE,
    IMPORT_NAME,
    Layout,
    PROG,
    RULE,
    SURFACES_FILE,
    anchored,
    launch,
    refusal_text,
    Refusal,
    Report,
    temp_base,
    UNREPORTABLE,
)
from .docs import (
    _run as docs_run,
    Members,
    command_surface,
    live_parity,
)
from .manifest import Manifest, load_manifest
from .mutants import load_mutants
from .probe import WRITES
from .templates import init
from .proof import (
    _NO_VERDICT,
    _STUB_CENSUS,
    _STUB_ENVIRONMENT,
    _STUB_MANIFEST,
    _STUB_MUTANTS,
    _STUB_WORK_FOLD,
    _box,
    _chmod_bites,
    _env_as,
    _heard,
    _package_argv,
    _scratch,
    _startup_noise,
    _startup_noise_reason,
    _made_under,
    _mode_as,
    _one_line,
    _plant_marker,
    _quietly,
    _CutOnLastLine,
    _subject,
)
from .checks_base import (
    arm_modules_named,
    is_arm_module,
    PACKAGE,
    _ast_owners,
    _capture_broke,
    _fresh_module,
    _NO_FILE_ROOM_ERROR,
    _owner_at,
    _printed_refusal,
    _refused_by,
    _rows_of,
    _walk_for_plant,
    _without_file_room,
)
from .checks_census import (
    _UNPROVEN_PIN,
)
from .checks_width import _same_pgid

def _closed_stdout_control(check: CheckRow, manifest: Manifest | None) -> None:
    """(q) a run whose standard output is closed is a refusal on stderr with
    exit 2, ahead of argparse — never the AttributeError traceback a first
    `out.write` would raise — and it makes nothing."""

    base_tmp = temp_base()
    err = io.StringIO()
    made = False
    # The box sits OUTSIDE the private root `_made_under` makes, so the
    # listing IS what the run left behind — nothing to subtract, and no
    # concurrent process to mistake for a leak.
    with _box("golden-census-noout-") as box:
        out_dir = os.path.join(box, "out")
        if manifest is not None:
            argv = ["capture", "--manifest", manifest.path, "--out", out_dir]
        else:
            argv = ["--selfcheck"]

        def body() -> int:
            # `sys.stdout` set to None, because None is exactly the state a
            # closed fd 1 produces, and `redirect_stdout` takes it.
            with contextlib.redirect_stdout(None), contextlib.redirect_stderr(err):
                return main(argv)

        code, leaked = _made_under(base_tmp, body)
        text = err.getvalue().strip()
        made = os.path.exists(out_dir)
    check("q  a run whose standard output is closed (`>&-`) is a refusal on "
          "stderr with exit 2 — never a traceback — and it makes nothing: "
          "no --out directory and no temp directory "
          "left behind",
          code == 2 and text.startswith("REFUSED:")
          and "standard output" in text and not made and not leaked,
          f"{ACTUAL}argv {argv[0]!r}, exit {code}, stderr {text[:60]!r}, --out "
          f"made={made}, {len(leaked)} left behind {leaked}")


class _PipeClosed:
    """A standard output whose reader has gone: it keeps what it was asked to
    write, then raises what a closed pipe raises."""

    def __init__(self) -> None:
        self.asked = ""

    def write(self, text: str) -> int:
        self.asked += text
        if not text:
            return 0          # an empty write moves no byte and fails on no pipe
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        pass


class _ClosedStderr(io.StringIO):
    """A standard error closed with standard output (`2>&1 | head`): every
    write raises what a closed pipe raises, and its descriptor is a pipe of
    the arm's own whose reader is gone."""

    def __init__(self, descriptor: int) -> None:
        super().__init__()
        self.descriptor = descriptor

    def write(self, text: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    def fileno(self) -> int:
        return self.descriptor


class _RefusedLastLine(_CutOnLastLine):
    """A standard output that refuses its last line as a full disk does,
    whose descriptor is a pipe of the arm's own whose reader is gone."""

    def __init__(self, error: OSError, descriptor: int) -> None:
        super().__init__(error)
        self.descriptor = descriptor

    def fileno(self) -> int:
        return self.descriptor


class _PipeOpen(io.StringIO):
    """The control's stream: `anchored` writes to it and nothing raises."""

    @property
    def asked(self) -> str:
        return self.getvalue()


def _anchor_left(stream: _PipeClosed | _PipeOpen) -> str:
    """Open `core.anchored` over `stream` and say whether the anchor it
    started is alive after the `with`: `gone`, `ALIVE` (then killed here, so
    no run leaks it) or `no group line`.

    The anchor's pid is the group id the line names — `process_group=0`
    makes the anchor its group's leader — so the line `anchored` tried to
    write is how the arm finds the process, with no seam of its own."""
    try:
        with anchored(stream):
            pass
    except BrokenPipeError:
        pass
    found = re.search(r"process group (\d+)", stream.asked)
    if found is None:
        return "no group line"
    pid = int(found.group(1))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        return "gone (the pid now names another user's process)"
    os.killpg(pid, signal.SIGTERM)
    return "ALIVE"


#: The child arm gggggg plants an exception that is not an `OSError`: the
#: runner `console.main` hands `cli.main` for `--selfcheck` leaves a partial
#: line in standard output's buffer, points fd 1 at a descriptor open for
#: reading only, and raises one; `main` lets it through as it was raised,
#: though the flush closing the body fails. Planted as `selfcheck.selfcheck`
#: before `console` is imported, so the child runs the command line's own
#: dispatch, and a `console.main` that hands no runner is a refusal here.
#: The partial line is read back: an exit handler, which runs before the
#: interpreter's last flush, points fd 1 at the child's own standard output
#: again where `main` pointed it at the null device for writing, so the line
#: still in the buffer reaches the arm, and a plant that wrote none shows
#: none. Where fd 1 is still the descriptor open for reading only, it is
#: left there, and that last flush fails as it would without the handler.
_NOT_A_WRITE = (
    "import atexit, fcntl, os, sys\n"
    "kept = os.dup(1)\n"
    "atexit.register(lambda: fcntl.fcntl(1, fcntl.F_GETFL) & os.O_ACCMODE\n"
    "                == os.O_RDONLY or os.dup2(kept, 1))\n"
    f"from {IMPORT_NAME} import selfcheck\n"
    "def planted(out, *_args):\n"
    "    out.write('partial')\n"
    "    os.dup2(os.open(os.devnull, os.O_RDONLY), 1)\n"
    "    raise RuntimeError('planted')\n"
    "selfcheck.selfcheck = planted\n"
    f"from {IMPORT_NAME} import console\n"
    "sys.exit(console.main(['--selfcheck']))\n")


def _unusable_midway_control(check: CheckRow, skip: SkipRow) -> None:
    """(gggggg) an unwritable `init` directory and a standard output closed
    under a run are each one refusal at exit 2, never a traceback; a capture
    whose last line meets a
    standard output that refuses it says the capture landed, at exit 2; an
    exception that is not an `OSError` leaves `main` as it was raised — and a run
    whose very first line meets the closed pipe leaves no anchor behind.

    The command halves run the real command line in a child, because
    what they assert is what the interpreter prints on its way out: a
    traceback, and the `Exception ignored` line its final flush of a closed
    stdout adds. The anchor half runs `core.anchored` in this process, since
    an anchor a child leaked has no parent left to ask about it.
    """
    label = ("gggggg  `init` into a directory it cannot write is ONE "
             "`REFUSED:` line at exit 2, never a traceback, and `init` whose "
             "output stops being read after its files are written leaves "
             "the project directory holding nothing; a standard output "
             "closed before the child's first write (`| head` that has "
             "already stopped reading) is ONE `REFUSED:` line on stderr at "
             "exit 2 with neither a `Traceback` nor an `Exception ignored`, "
             "and the same with stderr sent into that pipe too (`2>&1`) "
             "exits 2 and never 120, while the same command on an open pipe "
             "exits 0; `--help` into that closed pipe, with standard output "
             "unbuffered (`PYTHONUNBUFFERED=1`), is the same ONE "
             "`REFUSED:` line on stderr at exit 2 with neither a "
             "`Traceback` nor an `Exception ignored`, never 120, and says "
             "standard output closed while golden-census was still writing "
             "its help; a `capture --force` whose standard output is cut on "
             "its last line, after the swap, returns 0 with ONE stderr line "
             "saying --out holds the new capture, and with stderr closed too "
             "(`2>&1`) returns 0 with stderr's descriptor pointed at the null "
             "device; a `capture --force` whose standard output refuses its "
             "last line, after the swap (`File too large`), replaces --out, "
             "prints no `capture complete` and returns 2 with ONE stderr "
             "`REFUSED:` line that quotes the refusal and says --out holds "
             "the new capture, with standard output's descriptor pointed at "
             "the null device; an exception that is not an `OSError`, "
             "planted in a child whose `--selfcheck` runner leaves a partial line in a "
             "standard output open for reading only and raises it, leaves "
             "`main` as it was raised, at exit 1 and never as a `REFUSED:` "
             "line, and the partial line is read back from the child's "
             "standard output once its descriptor is given back; and "
             "`core.anchored` over a "
             "stream whose first write "
             "raises `BrokenPipeError` leaves no anchor alive, as a normal "
             "run leaves none")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(PACKAGE)
    said: dict[str, str] = {}
    held: dict[str, bool] = {}
    untested: list[str] = []
    # Both `init` halves need the templates; an install without them refuses
    # `init` before writing anything, which is not the case being asked.
    templates_here = Layout.detect().templates is not None
    if not templates_here:
        untested.append("both `init` halves (no templates beside the package)")
    with _box("golden-census-midway-") as box:
        # `init` into a directory `chmod 555` takes away.
        readonly = os.path.join(box, "readonly")
        os.makedirs(readonly)
        bites = _chmod_bites(readonly, os.listdir)
        if bites and templates_here:
            with _mode_as(readonly, 0o555):
                ran = launch(_package_argv("-m", IMPORT_NAME, "init",
                                           os.path.join(readonly, "p")),
                             "the unwritable-init arm's run", env=env,
                             cwd=box, stdin=subprocess.DEVNULL)
            heard = _heard(ran.stderr)
            refused = [line for line in ran.stdout.splitlines()
                       if line.startswith("REFUSED:")]
            said["init"] = (f"exit {ran.returncode}, "
                            + _one_line(ran.stdout, 150, needles=("REFUSED",),
                                        empty=_NO_VERDICT)
                            + f", stderr {_one_line(heard.own, 80, empty='empty')}"
                            + heard.not_from(PACKAGE))
            held["init"] = (ran.returncode == 2 and len(refused) == 1
                            and "cannot write" in refused[0]
                            and "Traceback" not in ran.stdout + heard.own
                            and not heard.not_from(PACKAGE))
        # `init` whose reader stops after the files are written: the undo
        # runs on every way out, so nothing of the project is left.
        if templates_here:
            project = os.path.join(box, "closed-init")
            try:
                init(project, None, False, _PipeClosed())
                raised = "returned"
            except BrokenPipeError:
                raised = "BrokenPipeError"
            except Refusal as refusal:
                raised = f"REFUSED {_one_line(str(refusal), 80)}"
            left = (sorted(os.listdir(project)) if os.path.isdir(project)
                    else None)
            said["init, reader gone"] = f"{raised}, the project holds {left}"
            held["init, reader gone"] = raised == "BrokenPipeError" and not left
        # A planted two-file capture, compared with itself: no subject runs.
        manifest = _scratch(box)
        golden = os.path.join(box, "golden")
        _plant_marker(golden)
        pathlib.Path(os.path.join(golden, "_subject", "help.out")).write_text(
            "stub\n", encoding="utf-8")
        compare = ["compare", "--manifest", manifest, "--golden", golden,
                   "--against", golden]
        argv = _package_argv("-m", IMPORT_NAME, *compare)
        opened = launch(argv, "the closed-pipe arm's control", env=env,
                        cwd=box, stdin=subprocess.DEVNULL)
        read_end, write_end = os.pipe()
        os.close(read_end)
        try:
            closed = launch(argv, "the closed-pipe arm's run", env=env,
                            cwd=box, stdin=subprocess.DEVNULL, stdout=write_end)
            # `2>&1` into the same closed pipe, through a shell that joins
            # the two before starting the command in its own place. Started
            # without `_package_argv`: its standard error IS the closed pipe,
            # so a directory line has nowhere to go and nothing here is
            # readable; the exit code is the whole claim.
            joined = launch(["sh", "-c", 'exec "$@" 2>&1', "sh", sys.executable,
                             "-m", IMPORT_NAME, *compare],
                            "the closed-pipe arm's joined run", env=env,
                            cwd=box, stdin=subprocess.DEVNULL, stdout=write_end)
            # argparse prints the help itself, inside `parse_args`. A buffered
            # standard output meets the error argparse swallowed again at the
            # flush; an unbuffered one does not. So this child runs unbuffered,
            # on every machine: it proves `main` does not rely on the flush.
            helped = launch(_package_argv("-m", IMPORT_NAME, "--help"),
                            "the closed-pipe arm's --help run",
                            env={**env, "PYTHONUNBUFFERED": "1"},
                            cwd=box, stdin=subprocess.DEVNULL, stdout=write_end)
        finally:
            os.close(write_end)
        other = launch(_package_argv("-P", "-c", _NOT_A_WRITE),
                       "the arm's planted-exception run", env=env, cwd=box,
                       stdin=subprocess.DEVNULL)
        said["closed pipe, 2>&1"] = f"exit {joined.returncode}"
        held["closed pipe, 2>&1"] = joined.returncode == 2
        # A reader that stops ONE line early — after the swap, before
        # `capture complete`: the work landed, so `capture` says so on stderr
        # and returns 0. In process and exact: the stream raises on that one
        # line, and it has no descriptor, so nothing of this process's own
        # standard output is redirected.
        landed = os.path.join(box, "landed")
        first_code = capture(load_manifest(manifest), landed, io.StringIO())
        before = os.stat(landed).st_ino if os.path.isdir(landed) else -1
        cut_out, cut_err = _CutOnLastLine(), io.StringIO()
        with contextlib.redirect_stderr(cut_err):
            try:
                cut_code = capture(load_manifest(manifest), landed, cut_out, (), True,
                                   landed_note=True)
                cut_said = f"exit {cut_code}"
            except BrokenPipeError as raised:
                cut_said = f"raised {type(raised).__name__}"
        replaced = (os.path.isdir(landed)
                    and os.stat(landed).st_ino != before)
        said["capture cut on its last line"] = (
            f"first capture exit {first_code}; the cut one {cut_said}, stderr "
            f"{_one_line(cut_err.getvalue(), DIFFERENCE, empty='empty')}, --out "
            f"replaced={replaced}, {len(cut_out.getvalue().splitlines())} "
            "line(s) written before the cut")
        stderr_lines = cut_err.getvalue().splitlines()
        held["capture cut on its last line"] = (
            first_code == 0 and cut_said == "exit 0" and replaced
            and len(stderr_lines) == 1
            and "standard output closed as the capture completed" in stderr_lines[0]
            and "--out" in stderr_lines[0])
        # The same cut with stderr closed too (`2>&1 | head`): the line cannot
        # land, so stderr's own descriptor is pointed at the null device. The
        # stand-in's descriptor is a pipe of this arm's whose reader is gone,
        # never this process's fd 2: after the call a write to it succeeds
        # only if it was redirected.
        read_end, write_end = os.pipe()
        os.close(read_end)
        closed_err = _ClosedStderr(write_end)
        with contextlib.redirect_stderr(closed_err):
            try:
                joined_code = capture(load_manifest(manifest), landed,
                                      _CutOnLastLine(), (), True, landed_note=True)
                joined_said = f"exit {joined_code}"
            except BrokenPipeError as raised:
                joined_said = f"raised {type(raised).__name__}"
        try:
            os.write(write_end, b"x")
            redirected = True
        except BrokenPipeError:
            redirected = False
        finally:
            os.close(write_end)
        said["capture cut on its last line, 2>&1"] = (
            f"{joined_said}, stderr's descriptor pointed at the null device={redirected}")
        held["capture cut on its last line, 2>&1"] = joined_said == "exit 0" and redirected
        # The same last line meeting a standard output that refuses the write
        # (a full disk): the work landed, and the refusal says so at exit 2.
        # The stand-in's descriptor is a pipe of this arm's whose reader is
        # gone: after the call a write to it succeeds only if it was pointed
        # at the null device, so `main`'s flush at the end has nothing left
        # to fail on.
        before = os.stat(landed).st_ino if os.path.isdir(landed) else -1
        read_end, write_end = os.pipe()
        os.close(read_end)
        full_out = _RefusedLastLine(OSError(errno.EFBIG, os.strerror(errno.EFBIG)),
                                    write_end)
        full_err = io.StringIO()
        with contextlib.redirect_stderr(full_err):
            try:
                full_code = capture(load_manifest(manifest), landed, full_out, (), True,
                                    landed_note=True)
                full_said = f"exit {full_code}"
            except OSError as raised:
                full_said = f"raised {type(raised).__name__}: {raised}"
        try:
            os.write(write_end, b"x")
            redirected = True
        except BrokenPipeError:
            redirected = False
        finally:
            os.close(write_end)
        replaced = os.path.isdir(landed) and os.stat(landed).st_ino != before
        full_lines = full_err.getvalue().splitlines()
        said["capture refused its last line"] = (
            f"{full_said}, stderr {_one_line(full_err.getvalue(), DIFFERENCE, empty='empty')}, "
            f"--out replaced={replaced}, capture complete printed="
            f"{'capture complete' in full_out.getvalue()}, standard output's "
            f"descriptor pointed at the null device={redirected}")
        held["capture refused its last line"] = (
            full_said == "exit 2" and replaced and redirected
            and sum(line.startswith("REFUSED:") for line in full_lines) == 1
            and f"standard output refused a write ({full_out.error}) as the "
                "capture completed, so its last line is missing or cut short; --out "
                "holds the new capture" in full_err.getvalue()
            and "capture complete" not in full_out.getvalue())
        opened_heard, closed_heard = _heard(opened.stderr), _heard(closed.stderr)
        helped_heard, other_heard = _heard(helped.stderr), _heard(other.stderr)
        said["open pipe"] = (f"exit {opened.returncode}, "
                             f"IDENTICAL={'IDENTICAL' in opened.stdout}"
                             + opened_heard.not_from(PACKAGE))
        said["closed pipe"] = (f"exit {closed.returncode}, stderr "
                               f"{_one_line(closed_heard.own, 170, empty='empty')}"
                               + closed_heard.not_from(PACKAGE))
        held["open pipe"] = (opened.returncode == 0 and "IDENTICAL" in opened.stdout
                             and not opened_heard.not_from(PACKAGE))
        held["closed pipe"] = (
            closed.returncode == 2
            and sum(line.startswith("REFUSED:")
                    for line in closed_heard.own.splitlines()) == 1
            and "Traceback" not in closed_heard.own
            and "Exception ignored" not in closed_heard.own
            and not closed_heard.not_from(PACKAGE))
        said["--help into a closed pipe"] = (
            f"unbuffered child, exit {helped.returncode}, stderr "
            f"{_one_line(helped_heard.own, 170, empty='empty')}"
            + helped_heard.not_from(PACKAGE))
        held["--help into a closed pipe"] = (
            helped.returncode == 2
            and sum(line.startswith("REFUSED:")
                    for line in helped_heard.own.splitlines()) == 1
            and f"standard output closed while {PROG} was still writing its help"
            in helped_heard.own
            and "Traceback" not in helped_heard.own
            and "Exception ignored" not in helped_heard.own
            and not helped_heard.not_from(PACKAGE))
        said["an exception that is not an OSError"] = (
            f"exit {other.returncode}, stderr's last line "
            f"{_one_line((other_heard.own.splitlines() or [''])[-1], 120, empty='empty')}"
            ", the partial line read back="
            f"{other.stdout.endswith(chr(10) + 'partial')}"
            + other_heard.not_from(PACKAGE))
        held["an exception that is not an OSError"] = (
            other.returncode == 1
            and other_heard.own.splitlines()[-1:] == ["RuntimeError: planted"]
            and "REFUSED" not in other_heard.own
            and other.stdout.endswith("\npartial")
            and not other_heard.not_from(PACKAGE))
    said["anchor, closed stream"] = _anchor_left(_PipeClosed())
    said["anchor, control"] = _anchor_left(_PipeOpen())
    held["anchor"] = (said["anchor, closed stream"].startswith("gone")
                      and said["anchor, control"].startswith("gone"))
    # The unwritable `init` is not a half here when `chmod 000` left the
    # directory writable (`bites` is False): it is SKIPPED below, by that
    # observation, and not counted in `held`. With no templates it is
    # already one of the two `init` halves taken off.
    expected = (11 - (0 if templates_here else 2)
                - (0 if bites or not templates_here else 1))
    check(label, all(held.values()) and len(held) == expected,
          ACTUAL + "; ".join(f"{why} -> {text}" for why, text in said.items())
          + ("; not exercised: " + "; ".join(untested) if untested else ""),
          next="`cli.main` hands every command `cli._Stdout`, which keeps "
               "the `OSError` a write or a flush of standard output raised "
               "(argparse swallows the one its `--help` write raises, so "
               "`main` asks `out` for it, not only the flush), "
               "and answers that error around its whole body — the flush "
               "after argparse exits and the flush closing the body included, "
               "which lets an exception already leaving the body leave as it "
               "was raised — with `cli._output_lost`, which says standard output closed "
               "for a `BrokenPipeError`, quotes any other `OSError` as a "
               "refused write, and says its help rather than its verdict "
               "while the help was written; `capture` answers its last line's "
               "`OSError` itself, at exit 0 for a closed pipe and at exit 2 "
               "for a refused write, both saying --out holds the new capture; "
               "`core.anchored` writes its group line inside the `try` that "
               "sweeps; `templates.apply` turns an `OSError` on the project "
               "directory into the refusal.")
    if not bites:
        skip(label, "`chmod 000` left the directory writable here, so the "
                    "unwritable `init` could not be planted; nothing is "
                    "claimed for it.")


def _unanswered_error_control(check: CheckRow) -> None:
    """(dddddddd) an `OSError` no site answers is ONE refusal at exit 2,
    never a traceback.

    Three children run the real command line over the stub: a `capture`
    with no limit, its control, which exits 0; the same capture under a
    file-size limit of 0 bytes, whose first record raises `File too large`;
    and the same again with `cli._unanswered` handing the error back, the
    arm's own red half. The sentence is `cli._unanswered`'s own, asked of
    the same error here, and it quotes the error as Python states it: the
    last line of the red half's traceback, which the arm reads in that
    child's output and never asks of `cli._unanswered`, which would agree
    with a sentence that quoted no error at all.
    """

    label = ("dddddddd  an `OSError` that no site of golden-census answers — "
             "a `capture` under a file-size limit of 0 bytes, whose first "
             "record raises `File too large` — is ONE `REFUSED:` sentence "
             "with its `next:` line, last on standard output under the "
             "process-group line, at exit 2, with stderr empty and no "
             "--out, where the same capture with no limit exits 0; and the "
             "same limited capture with that answer cut out of `cli.main` "
             "is a Python traceback at exit 1 whose last line, the error as "
             "Python states it, the sentence quotes between its dashes")
    error = _NO_FILE_ROOM_ERROR
    expected = refusal_text(_unanswered(error)) + "\n"
    env = dict(os.environ, PYTHONPATH=os.path.dirname(PACKAGE))
    ran: dict[str, subprocess.CompletedProcess[str]] = {}
    left: dict[str, bool] = {}
    with _box("golden-census-unanswered-") as box:
        manifest = _scratch(box)
        # The control runs with no limit; the other two in the
        # `_NO_FILE_ROOM` child, the second with the answer cut out.
        for name, cut_out in (("control", None), ("limited", "none"),
                              ("cut", "unanswered")):
            out_dir = os.path.join(box, f"out-{name}")
            argv = ["capture", "--manifest", manifest, "--out", out_dir]
            what = f"arm dddddddd's {name} run"
            ran[name] = (
                launch(_package_argv("-m", IMPORT_NAME, *argv), what,
                       env=env, cwd=box) if cut_out is None
                else _without_file_room(cut_out, argv, what, box))
            left[name] = os.path.lexists(out_dir)
    control, limited, cut = ran["control"], ran["limited"], ran["cut"]
    heard = {name: _heard(proc.stderr) for name, proc in ran.items()}
    elsewhere = "".join(one.not_from(PACKAGE) for one in heard.values())
    lines = limited.stdout.splitlines()
    stated = (heard["cut"].own.splitlines() or [""])[-1]
    quotes = bool(stated) and any(
        line.startswith("REFUSED:") and f"— {stated} —" in line
        for line in lines)
    held = (control.returncode == 0
            and "capture complete" in control.stdout
            and limited.returncode == 2
            and limited.stdout.endswith(expected)
            and quotes
            and sum(line.startswith("REFUSED:") for line in lines) == 1
            and bool(lines) and lines[0].startswith("process group ")
            and heard["limited"].own == ""
            and not left["limited"]
            and cut.returncode == 1
            and "Traceback (most recent call last)" in heard["cut"].own
            and heard["cut"].own.splitlines()[-1:] == [f"OSError: {error}"]
            and "REFUSED" not in cut.stdout
            and not elsewhere)
    check(label, held,
          f"{ACTUAL}control -> exit {control.returncode}, capture complete="
          f"{'capture complete' in control.stdout}; limited -> exit "
          f"{limited.returncode}, "
          f"{_one_line(limited.stdout, 260, needles=('REFUSED',), empty=_NO_VERDICT)}"
          f", the sentence cli._unanswered gives last={limited.stdout.endswith(expected)}"
          f", quotes the traceback's last line={quotes}"
          f", first line {_one_line(lines[0] if lines else '', 14, empty='none')!r}, "
          f"stderr {_one_line(heard['limited'].own, 80, empty='empty')}, --out there="
          f"{left['limited']}; the answer cut out -> exit "
          f"{cut.returncode}, stderr's last line "
          f"{_one_line(stated, 80, empty='empty')}{elsewhere}",
          next="`cli.main` answers every `OSError` that is not standard "
               "output's own, after `core.anchored`'s sweep, with "
               "`cli._unanswered`'s refusal on standard output at exit 2.")


def _report_parity_control(check: CheckRow) -> None:
    """(ll) the two behaviors a GREEN tree never reaches, so they get their
    positive control here or they get none.

    (a) An installed copy is a package with no README beside it. Two verdicts
    for that one absence — a `[FAIL]` for the README half and a `[SKIP]` for
    the skill half — would leave `--selftest` unable to pass anywhere but in
    this repository. Both halves are disclosed SKIPs, and this arm is what says
    so.

    (b) A raise inside a self-TEST group. `[FAIL]  !` decided only in the
    self-check's runner would let a group whose body raised abort the run and
    report nothing at all. `Report.guard` is the one decider, and a scratch
    group with a planted raise is what proves it.
    """
    with _box("golden-census-installed-") as box:
        package = os.path.join(box, IMPORT_NAME)
        os.makedirs(package)
        texts: list[tuple[Members | None, Members | None]] = []
        rows, skips = _rows_of(lambda check_row, skip_row: texts.append(live_parity(
            command_surface(), check_row, skip_row, package=package)))
    installed = (not rows and len(skips) == 2
                 and any("README.md" in reason for _label, reason in skips)
                 and texts == [(None, None)])

    scratch = Report(io.StringIO(), "A SCRATCH GROUP")

    def planted() -> None:
        scratch.check("(inner) an arm that ran before the fault", True,
                      ACTUAL + "fine")
        raise ImportError("a planted ImportError, on no list anywhere")

    scratch.guard(planted)                  # returns: no traceback escapes
    failures = scratch.finish()
    text = scratch.out.getvalue()
    grouped = (failures == 1 and "[FAIL]  !" in text
               and "ImportError: a planted ImportError" in text
               and "an arm that ran before the fault" in text
               and "1/2 passed" in text)

    check("ll  a package with no README beside it and none under it — a "
          "layout carrying no documents — files a disclosed [SKIP] for each "
          "document half and no [FAIL], "
          "the two halves agreeing on one absence; and a planted raise inside "
          "a self-TEST group is a "
          "[FAIL]  ! row through the one Report, not a traceback that takes "
          "the run with it",
          installed and grouped,
          f"{ACTUAL}the package-only layout gave {len(rows)} row(s) and "
          f"{len(skips)} disclosed SKIP(s); the scratch group reported "
          f"{failures} failure(s), [FAIL]  ! row={'[FAIL]  !' in text}, the "
          f"arm before the fault still printed="
          f"{'an arm that ran before the fault' in text}")


#: Names a pre-3.11 interpreter may go by, most explicit first. `python3` is
#: last and is not assumed to be old: on this machine it is 3.9 and on the
#: next it is 3.14, so it is PROVED old before it is used, the same way
#: `bin/golden-census` proves one new.
_OLD_NAMES = ("python3.10", "python3.9", "python3.8", "/usr/bin/python3",
              "python3")


def _pre_floor_python() -> str | None:
    """An interpreter on this machine BELOW the 3.11 floor, or None."""
    for name in _OLD_NAMES:
        if os.path.isabs(name):
            if not os.path.exists(name):
                continue
        elif shutil.which(name) is None:
            continue
        proc = launch([name, "-I", "-c", "import sys; raise SystemExit("
                              "0 if sys.version_info < (3, 11) else 1)"],
                      f"the floor arm's probe of `{name}`",
                      stdin=subprocess.DEVNULL)
        if proc.returncode == 0:
            return name
    return None


def _guard_cut(source: str) -> str | None:
    """`__main__.py` with its version-guard block CUT, or None.

    The counterfactual is DERIVED from the shipped file rather than typed
    beside it: a guard that moves, or is written differently, is still the
    block this removes, and a guard that is deleted outright makes this
    return None and the arm say so.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if "version_info" not in ast.dump(node.test) or node.end_lineno is None:
            continue
        return "".join(lines[:node.lineno - 1] + lines[node.end_lineno:])
    return None


def _startup_noise_control(check: CheckRow, skip: SkipRow) -> None:
    """(vvvvvvvv) the probe that the seven arms reading a child's output alone
    begin with sees the line a `.pth` in a user site prints, and nothing
    under a clean one.

    The planted file is read only when the interpreter reads a user site, so
    the child that names the site is asked first and the arm says what it
    found. The probe runs with `env` and not the cache: the cache holds the
    answer for THIS process's own HOME, which is no part of the question.
    The seven arms are not re-run here; the noisy `--selfcheck` run by hand
    is their measurement.
    """
    label = ("vvvvvvvv  the startup-noise probe finds the line a planted "
             "`.pth` in a scratch user site prints, quotes it, and finds "
             "nothing under a clean one; the seven arms that read a child's "
             "output alone SKIP by that observation and never go red for "
             "the interpreter's own line")
    planted = "startup noise from a .pth"
    removed = "PYTHONNOUSERSITE" in os.environ
    said: dict[str, tuple[str, str] | None] = {}
    with _box("golden-census-noise-") as box:
        for key in ("planted", "clean"):
            home = os.path.join(box, key)
            os.makedirs(home)
            env = {name: value for name, value in os.environ.items()
                   if name != "PYTHONNOUSERSITE"}
            env["HOME"] = home
            asked = subprocess.run(
                [sys.executable, "-P", "-c",
                 "import site; print(site.ENABLE_USER_SITE); "
                 "print(site.getusersitepackages())"],
                env=env, stdin=subprocess.DEVNULL, capture_output=True,
                text=True, encoding="utf-8", errors="surrogateescape",
                check=False)
            lines = asked.stdout.splitlines()
            if asked.returncode != 0 or len(lines) < 2 or lines[0] != "True":
                skip(label, "this interpreter does not read a user site "
                            f"under a scratch HOME (it answered {lines[:1]}, "
                            f"exit {asked.returncode}), so a planted `.pth` "
                            "is never run and the probe has nothing to see. "
                            "Nothing is claimed.")
                return
            if key == "planted":
                os.makedirs(lines[1])
                pathlib.Path(lines[1], "zz-noise.pth").write_text(
                    f'import sys; sys.stderr.write("{planted}\\n")\n',
                    encoding="utf-8")
            said[key] = _startup_noise(env)
    found = said["planted"]
    reason = _startup_noise_reason(found) if found is not None else ""
    check(label,
          found is not None and found[0] == "standard error"
          and found[1].strip() == planted and said["clean"] is None
          and planted in reason
          and "comes from Python's own site files" in reason,
          f"{ACTUAL}planted .pth -> {found!r}; clean HOME -> "
          f"{said['clean']!r}; reason quotes the line={planted in reason}; "
          f"PYTHONNOUSERSITE "
          f"{'removed from the child env' if removed else 'was not set'}")


def _floor_guard_control(check: CheckRow, skip: SkipRow) -> None:
    """(uu) `-m golden_census` under a pre-3.11 interpreter refuses; the same
    interpreter over the same file with the guard cut dies in the traceback
    the guard exists to replace."""
    label = ("uu  `python3 -m golden_census` under an interpreter BELOW the "
             "3.11 "
             "floor is one REFUSED sentence naming the floor and the "
             "interpreter found, with a `next:` line, at exit 2 — and the "
             "SAME interpreter over a copy of `__main__.py` with the guard "
             "block cut out dies in the traceback ending "
             "`ModuleNotFoundError: No module named 'tomllib'` at exit 1 "
             "that the guard exists to replace, which is how this row is "
             "known to be able to go red; and the refusal names NO "
             "interpreter path of its own — a path is a fact about one "
             "machine, and the only rooted path in it is the "
             "`sys.executable` it reports having FOUND")
    old = _pre_floor_python()
    source = None
    path = os.path.join(PACKAGE, "__main__.py")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    if old is None or source is None:
        skip(label, ("no interpreter below 3.11 was found on this machine "
                     f"(tried {', '.join(_OLD_NAMES)}), so the refusal has "
                     "nothing to refuse"
                     if old is None else
                     f"there is no __main__.py at {path} to read the guard "
                     "off — an installed copy reached by its console "
                     "script has no module entry point here")
                    + ". Nothing was run and nothing is claimed.")
        return
    cut = _guard_cut(source)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(PACKAGE)
    # `cwd` on both runs, because `-m` puts the CURRENT directory on the
    # path ahead of PYTHONPATH: run from a checkout without it, the
    # guard-cut copy below finds the real package and proves nothing.
    real = launch(_package_argv("-m", IMPORT_NAME, "--version", python=old),
                  "the floor arm's real run", env=env,
                  cwd=os.path.dirname(PACKAGE), stdin=subprocess.DEVNULL)
    real_heard = _heard(real.stderr)
    planted_code, planted_err = -1, "the guard block was not found to cut"
    if cut is not None:
        with _box("golden-census-floor-") as scratch:
            package = os.path.join(scratch, IMPORT_NAME)
            os.makedirs(package)
            for name, text in (("__init__.py", ""), ("__main__.py", cut),
                               # `console` stands in for the real one at its
                               # ONE relevant property: reaching it needs 3.11.
                               ("console.py", "import tomllib\n\n\n"
                                              "def main() -> int:\n"
                                              "    del tomllib\n"
                                              "    return 0\n")):
                pathlib.Path(os.path.join(package, name)).write_text(text, encoding="utf-8")
            planted_env = dict(os.environ)
            planted_env["PYTHONPATH"] = scratch
            plant = launch([old, "-m", IMPORT_NAME, "--version"],
                           "the floor arm's guard-cut copy", env=planted_env,
                           cwd=scratch, stdin=subprocess.DEVNULL)
            planted_code, planted_err = plant.returncode, plant.stderr
    # Every `/`-rooted token the refusal prints. The interpreter the guard
    # FOUND is reported on purpose — a reader has to know which one ran — and
    # any other rooted path is an EXAMPLE, which is a fact about the machine
    # the line was written on and wrong on every other one. The example this
    # refusal used to carry named Homebrew's path on Apple silicon, which
    # does not exist on Linux, in the one line that says what to DO.
    #
    # What that interpreter calls itself is asked of the interpreter, not
    # read off the refusal: a row that took the answer from the text it is
    # judging would pass whatever the text said.
    reports = launch([old, "-I", "-c",
                      "import sys; sys.stdout.write(sys.executable)"],
                     "the floor arm's interpreter question", env=env,
                     cwd=os.path.dirname(PACKAGE), stdin=subprocess.DEVNULL)
    found = reports.stdout.strip()
    # The found interpreter is REMOVED from the text before anything is
    # looked for, rather than compared against token by token: a path holding
    # a space — `/Applications/My Python.app/…` — fragments under `split()`
    # into pieces that equal nothing, and the row would go red about where
    # the machine keeps its interpreters.
    left = real.stdout.replace(found, "") if found else real.stdout
    stray = [token.strip("`'\"().,") for token in left.split()
             if token.strip("`'\"().,").startswith("/")]
    rooted = ([found] if found and found in real.stdout else []) + stray
    check(label,
          real.returncode == 2 and real.stdout.startswith("REFUSED: ")
          and "next: " in real.stdout and "Traceback" not in real_heard.own
          and not real_heard.not_from(PACKAGE)
          and planted_code == 1 and "tomllib" in planted_err
          and "Traceback" in planted_err
          and not stray,
          f"{ACTUAL}{old} -> exit {real.returncode}, "
          f"{_one_line(real.stdout, 170, empty=_NO_VERDICT)}, stderr "
          f"{_one_line(real_heard.own, 60, empty='empty')}"
          f"{real_heard.not_from(PACKAGE)}; rooted path(s) in "
          f"the refusal {rooted}, of which the interpreter that ran calls "
          f"itself {found!r} and {len(stray)} other(s) {stray}; the same "
          f"interpreter over the guard-cut copy -> exit {planted_code}, "
          f"stderr {_one_line(planted_err, 90, empty='empty')}",
          next="Run `/usr/bin/python3 -m golden_census --version` by hand: "
               "the guard at the top of golden_census/__main__.py has to "
               "precede the `from golden_census.console import main` line, and "
               "nothing above it "
               "may import anything newer than the floor.")


def _docs_exit_control(check: CheckRow) -> None:
    """(tt) `docs._run` catches argparse's `SystemExit` as well as a
    `Refusal`: caught nowhere, that exit walks out of the measurement of the
    priced commands (`docs.measure`) and ends the process."""
    argv = ["compare"]              # --manifest and --golden are required
    raised = ""
    code, text = -1, ""
    try:
        code, text = docs_run(main, argv)
    except BaseException as exc:    # noqa: BLE001 — the arm's whole subject
        if isinstance(exc, UNREPORTABLE):
            raise
        raised = f"{type(exc).__name__}: {exc}"
    check("tt  a priced invocation argparse REJECTS is a refusal naming the "
          "argv and exit 2, not a `SystemExit` out of `docs.measure` that "
          "ends `--selftest` with argparse's usage block as its only clue",
          code == 2 and not raised and text.startswith("REFUSED:")
          and " ".join(argv) in text and "next:" in text,
          f"{ACTUAL}exit {code}, raised {raised or 'nothing'}, verdict "
          f"{_one_line(text, 150)!r}")


def _private_root_control(check: CheckRow) -> None:
    """(fff) `_made_under` reports what the body left under the PRIVATE root
    and nothing that appeared under the shared one.

    Both directions, planted: a directory made under the shared temp root
    while the body runs must NOT be reported (that is the concurrent process a
    before/after listing of the shared root counts as this run's leak), and one
    made under the private root MUST be (or the arms would report clean
    whatever happened). The shared plant is removed by this arm; the private one
    goes with the root.
    """
    base = temp_base()
    shared = ""
    private = ""

    def body() -> str:
        nonlocal shared, private
        # Under the SHARED root, as a concurrent process would make it.
        shared = tempfile.mkdtemp(prefix="golden-census-concurrent-", dir=base)
        # Under the PRIVATE root, as the run under test would leak it. Through
        # `temp_base()`, which is what every scratch directory in the package
        # asks and what `_made_under` has pointed at the private root.
        private = tempfile.mkdtemp(prefix="golden-census-planted-leak-",
                                   dir=temp_base())
        return "ran"

    ran, reported = _made_under(base, body)
    still_there = os.path.isdir(shared)
    shutil.rmtree(shared, ignore_errors=True)
    check("fff  the private-root control that arms n, q, t and kk stand on: a "
          "directory planted under the PRIVATE temp root while the body runs "
          "is reported, and one planted under the SHARED root at the same "
          "moment is not — a concurrent process's directory under the shared "
          "root is not this run's leak; the "
          "private root and everything in it is removed afterwards",
          ran == "ran"
          and reported == [os.path.basename(private)]
          and still_there and not os.path.isdir(private),
          f"{ACTUAL}reported {reported}; planted under the private root "
          f"{os.path.basename(private)!r} (reported: "
          f"{os.path.basename(private) in reported}) and under the shared "
          f"root {os.path.basename(shared)!r} (reported: "
          f"{os.path.basename(shared) in reported}, still there at the end: "
          f"{still_there}); the private root is gone: "
          f"{not os.path.isdir(private)}")


#: The three tallies `core.Report.finish` can print, spelled out. A row that
#: says what the reader will see, byte for byte, so a suffix that grew a comma
#: or lost a word fails here rather than in a document nobody re-measured.
_TALLIES = (
    ("neither", "\n  2/2 passed\n"),
    ("a SKIP", "\n  1/1 passed, 1 arm(s) SKIPPED (disclosed, never a pass)\n"),
    ("a refusal", "\n  1/1 passed, REFUSED after row 1\n"),
    ("both", "\n  1/1 passed, REFUSED after row 1, 1 arm(s) SKIPPED "
             "(disclosed, never a pass)\n"),
)


def _tally_control(check: CheckRow) -> None:
    """(ggg) the one printer's three tally suffixes, on a scratch stream.

    `REFUSED after row N` has no other arm: a block whose body raises prints
    no row for the refusal, so a tally reading `N/N passed` alone looks like a
    clean run of everything (arm `s` proves the rows before it still print, and
    says nothing about the tally). The SKIPPED suffix has no other arm either.
    Both are asserted as BYTES, because both are what a reader counts lines
    of.
    """
    printed: dict[str, str] = {}

    def block(rows: int, skips: int, refuse: bool) -> str:
        stream = io.StringIO()
        report = Report(stream, "PLANTED")
        for number in range(rows):
            report.check(f"row {number}", True, ACTUAL + "planted")
        for number in range(skips):
            report.skip(f"skip {number}", "planted")
        if refuse:
            try:
                report.guard(_raises_planted)
            except Refusal:
                pass
        report.finish()
        return stream.getvalue()[-200:]

    printed["neither"] = block(2, 0, False)
    printed["a SKIP"] = block(1, 1, False)
    printed["a refusal"] = block(1, 0, True)
    printed["both"] = block(1, 1, True)
    wrong = [name for name, tail in _TALLIES
             if not printed[name].endswith(tail)]
    check("ggg  the one report printer's tally says what happened: `N/N "
          "passed` alone, with `, REFUSED after row N` when a body raised a "
          "Refusal and printed no row for it, with `, K arm(s) SKIPPED "
          "(disclosed, never a pass)` when arms were skipped, and with both "
          "in that order — each asserted as the exact bytes a reader counts "
          "lines of",
          not wrong,
          ACTUAL + "; ".join(f"{name} -> {printed[name].splitlines()[-1]!r}"
                                 for name, _tail in _TALLIES)
          + (f"; WRONG: {wrong}" if wrong else ""))


def _raises_planted() -> None:
    raise Refusal("a planted refusal, for the tally arm",
                  next="nothing — this is arm ggg's own plant.")


# ------------------------------------------------- the decoding of a child
#
# `launch` decodes a text run as UTF-8 and never by the locale's encoding.
# The locale is a fact about the SHELL a capture was started from, and a
# subject printing one non-ASCII byte would otherwise be recorded differently
# — or not at all, and a traceback — depending on it.

#: A subject that prints outside ASCII on both streams: a Latin accent, a dash,
#: a tick, and three characters well outside the Latin range.
_WIDE_SUBJECT = (
    "import sys\n"
    "print('na\\u00efve \\u2014 \\u2713 \\u65e5\\u672c\\u8a9e')\n"
    "sys.stderr.write('stderr too: \\u00e9\\n')\n"
)

#: What the child measures, in the locale it was started in: what `launch`
#: brings back, and — the positive control — what a `subprocess.run(text=True)`
#: naming no encoding does over the SAME subject in the SAME locale. The two
#: legs ride in one child because the locale is the thing being varied and two
#: children could not be shown to have had the same one.
#:
#: It drives `launch` and not a whole `capture`: a child running a command
#: would run its own self-check, reach this arm, and spawn children of its own
#: without end. `launch` is the decision this arm is about, and it is reached
#: by importing it.
#:
#: The SUBJECT is handed a pinned UTF-8 environment, the way `build_env` hands
#: a capture's subject an environment built from nothing: a subject that
#: inherited the child's C locale would print different BYTES in the two runs,
#: and the arm would be measuring the subject instead of the decoding. It
#: writes bytes to a file rather than printing, because a child in the C
#: locale cannot print what it is holding.
_DECODE_CHILD = (
    "import locale, os, subprocess, sys\n"
    "from golden_census.core import launch\n"
    "\n"
    "subject = [sys.executable, sys.argv[1]]\n"
    "pinned = {'PATH': os.environ.get('PATH', ''),\n"
    "          'LC_ALL': 'en_US.UTF-8', 'LANG': 'en_US.UTF-8'}\n"
    "through = launch(subject, 'the decoding arm\\'s subject', env=pinned,\n"
    "                 stdin=subprocess.DEVNULL)\n"
    "try:\n"
    "    subprocess.run(subject, check=False, text=True, env=pinned,\n"
    "                   capture_output=True, stdin=subprocess.DEVNULL)\n"
    "    by_locale = 'decoded'\n"
    "except UnicodeDecodeError:\n"
    "    by_locale = 'UnicodeDecodeError'\n"
    "with open(sys.argv[2], 'wb') as handle:\n"
    "    handle.write((locale.getpreferredencoding(False) + ' ' + by_locale\n"
    "                  + '\\n' + through.stdout + through.stderr).encode('utf-8'))\n"
)

#: The two environments the child is run under. The C leg turns OFF the two
#: escapes CPython offers from a non-UTF-8 locale — PEP 538's coercion of the
#: C locale and PEP 540's UTF-8 mode — because with either of them on this
#: machine's C locale decodes as UTF-8 anyway and the control could not fire.
#: A machine where it still cannot is a disclosed SKIP.
_C_LOCALE = {"LC_ALL": "C", "LANG": "C",
             "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"}
_UTF8_LOCALE = {"LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8"}


def _decoded_in(box: str, leaf: str, locale_env: dict[str, str]
                ) -> tuple[int, str, bytes, str]:
    """`(exit code, the locale's own encoding and verdict, the decoded text,
    what the child said of the package it imported)` for one run of the
    child in one locale; the last is `""` when it was this copy."""
    written = os.path.join(box, leaf)
    env = dict(os.environ)
    env.update(locale_env)
    env["PYTHONPATH"] = os.path.dirname(PACKAGE)
    proc = launch(_package_argv(os.path.join(box, "child.py"),
                                os.path.join(box, "subject.py"), written),
                  "the decoding arm's child", env=env, cwd=box,
                  stdin=subprocess.DEVNULL)
    heard = _heard(proc.stderr)
    if not os.path.isfile(written):
        return (proc.returncode, _one_line(heard.own, 90, empty="(nothing)"),
                b"", heard.not_from(PACKAGE))
    with open(written, "rb") as handle:
        first, _, rest = handle.read().partition(b"\n")
    return proc.returncode, first.decode("utf-8"), rest, heard.not_from(PACKAGE)


def _decoding_control(check: CheckRow, skip: SkipRow) -> None:
    """(iiii) a child's output is decoded as UTF-8, whatever the locale is."""
    label = ("iiii  a child's output is decoded as UTF-8 and never by the "
             "LOCALE's encoding: the same non-ASCII subject, run through "
             "`launch` under `LC_ALL=C` and under a UTF-8 locale, comes back "
             "byte-identical. The positive control is measured in the C "
             "locale itself and not assumed — the same child reports the "
             "encoding that locale would have decoded with, and what a "
             "`subprocess.run(text=True)` naming no encoding does over the "
             "same subject there")
    with _box("golden-census-decode-") as box:
        for leaf, text in (("subject.py", _WIDE_SUBJECT),
                           ("child.py", _DECODE_CHILD)):
            pathlib.Path(os.path.join(box, leaf)).write_text(text, encoding="utf-8")
        c_code, c_found, c_text, c_from = _decoded_in(box, "c.out", _C_LOCALE)
        utf8_code, utf8_found, utf8_text, utf8_from = _decoded_in(
            box, "utf8.out", _UTF8_LOCALE)
    if c_code == 0 and c_found.endswith(" decoded"):
        skip(label,
             f"a child of this machine started in the C locale reports "
             f"{c_found!r}: it decodes a non-ASCII byte without being told "
             "to, so the two runs below would agree whatever `launch` did "
             "and a green row would prove nothing. Nothing is claimed.")
        return
    same = c_text == utf8_text and c_text != b""
    wide = "na\u00efve \u2014 \u2713 \u65e5\u672c\u8a9e".encode() in c_text
    control = c_found.endswith(" UnicodeDecodeError")
    check(label, c_code == 0 and utf8_code == 0 and same and wide and control
          and not c_from and not utf8_from,
          f"{ACTUAL}LC_ALL=C -> exit {c_code}, {len(c_text)} byte(s); a UTF-8 "
          f"locale ({utf8_found.split(' ')[0]}) -> exit {utf8_code}, "
          f"{len(utf8_text)} byte(s); byte-identical={same}, the non-ASCII "
          f"text came through={wide}; the control — in the C locale itself, "
          f"{c_found!r}{c_from}{utf8_from}",
          next="Read `core.launch`: a text run names `encoding=\"utf-8\"`, and "
               "a run that leaves it to the locale records a golden about the "
               "shell the capture was started from.")


# ------------------------------------ the encoding of what is written
#
# The output-side twin of `iiii`: `cli.main` makes standard output and
# standard error UTF-8 before the first write to either, whatever
# `PYTHONIOENCODING` or the locale says, and `__main__` does the same for the
# refusal it prints before `cli` is imported. An encoding taken from the
# environment turns the first dash written into a traceback, or opens the
# stream with a byte-order mark.

_UTF8_SIG = {"PYTHONIOENCODING": "utf-8-sig"}
_UTF16 = {"PYTHONIOENCODING": "utf-16"}

#: The four environments that name another encoding for standard output: ASCII
#: named outright, `_C_LOCALE`, and two whose encoder opens with a byte-order
#: mark.
_NOT_UTF8 = (("PYTHONIOENCODING=ascii", {"PYTHONIOENCODING": "ascii"}),
             ("the C locale with UTF-8 mode off", _C_LOCALE),
             ("PYTHONIOENCODING=utf-8-sig", _UTF8_SIG),
             ("PYTHONIOENCODING=utf-16", _UTF16))

#: What each leg removes from the parent's environment first, so a self-check
#: run under one of these does not leak it into the UTF-8 leg.
_ENCODING_VARIABLES = ("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONCOERCECLOCALE",
                       "LC_ALL", "LC_CTYPE", "LANG")

#: A child that closes descriptor 1 and then becomes the command line after
#: it: what a shell's `>&-` does, with no shell.
_CLOSED = "import os, sys\nos.close(1)\nos.execv(sys.argv[1], sys.argv[1:])\n"

#: A child that names no encoding: what it writes is the environment's.
_UNNAMED = "import sys\nsys.stdout.write('x\\n')\n"

#: How the refusal for a closed standard output opens.
_UNUSABLE = b"REFUSED: standard output is unusable"


def _guard_forced(source: str) -> str | None:
    """`__main__.py` with its version test replaced by `True`, or None: the
    refusal an interpreter below the floor prints, reached by this one."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "version_info" in ast.dump(node.test):
            test = ast.get_source_segment(source, node.test)
            return None if test is None else source.replace(test, "True", 1)
    return None


def _stdout_in(argv: list[str], cwd: str, pythonpath: str,
               leg: dict[str, str]) -> tuple[int, bytes, bytes]:
    """`(exit code, standard output with the process id masked, standard
    error)` of one child of `argv` under the UTF-8 locale and `leg`, both
    streams as the BYTES the child wrote: nothing is stripped, so a
    byte-order mark is a difference."""
    env = {key: value for key, value in os.environ.items()
           if key not in _ENCODING_VARIABLES}
    env.update(_UTF8_LOCALE)
    env.update(leg)
    env["PYTHONPATH"] = pythonpath
    proc = launch(argv, "the output-encoding arm's child", env=env, cwd=cwd,
                  stdin=subprocess.DEVNULL, text=False)
    masked = _same_pgid(proc.stdout.decode("utf-8", "surrogateescape"))
    return (proc.returncode, masked.encode("utf-8", "surrogateescape"),
            proc.stderr)


def _last_said(said: bytes) -> str:
    """`, stderr empty`, or the last line a child wrote on standard error, in
    ASCII and with its NUL bytes taken out so that a traceback written as
    UTF-16 reads as one, for a row's detail: a traceback's last line is the
    exception."""
    if not said:
        return ", stderr empty"
    text = said.decode("utf-8", "replace").replace("\x00", "")
    lines = text.strip().splitlines() or [""]
    return f", stderr {len(said)} byte(s), ending {ascii(lines[-1])[:160]}"


def _stdout_encoding_control(check: CheckRow, skip: SkipRow) -> None:
    """(fffffff) golden-census writes UTF-8 on standard output and on
    standard error under five environments that name another encoding.

    Two command lines, each run as a child five times: under a UTF-8 locale
    and under the four legs of `_NOT_UTF8`. The first is `census --manifest`
    naming a file that is not there, whose name holds `café`, `日本語` and
    the byte 0xff: its refusal prints the process-group line's dash and the
    name as given, which no ASCII stream holds. The second is `--version`
    over a copy of `__main__.py` whose version test reads `True`, which
    prints the refusal an interpreter below the floor prints, before `cli`
    is imported. Each run must exit as the UTF-8 run exits, write nothing on
    standard error, and print the UTF-8 run's bytes once the process id is
    masked; the UTF-8 run of the first must hold the dash and the name's
    bytes, and that of the second `REFUSED:` and the dash.

    The fifth leg is the first command line with standard output CLOSED, by
    `_CLOSED`, under a UTF-8 locale and under `PYTHONIOENCODING=utf-16`: each
    exits 2 with nothing on standard output, the first writes the refusal
    for an unusable standard output on standard error, and the second writes
    the first's bytes.

    The control is `_UNNAMED`, a child that names no encoding, under a UTF-8
    locale and under `PYTHONIOENCODING=utf-8-sig`: the two must print
    DIFFERENT bytes, which proves that a leg's variable reaches the child
    and that a byte-order mark is a difference this arm sees.
    """
    label = ("fffffff  golden-census writes UTF-8 on standard output and on "
             "standard error under five environments that name another "
             "encoding: `census --manifest` naming a file that is not there, "
             "whose name holds `café`, `日本語` and the byte 0xff, run as a "
             "child under `PYTHONIOENCODING=ascii`, under the C locale with "
             "UTF-8 mode off, under `PYTHONIOENCODING=utf-8-sig` and under "
             "`PYTHONIOENCODING=utf-16`, exits as it does under a UTF-8 "
             "locale, with nothing on standard error, and prints the same "
             "bytes, the process-group line's dash and the name's bytes as "
             "given among them, once the process id is masked; the refusal "
             "`__main__` prints under an interpreter below the 3.11 floor, "
             "reached by a copy whose version test reads `True`, does the "
             "same; with standard output closed under "
             "`PYTHONIOENCODING=utf-16` the first exits 2 and writes on "
             "standard error, byte for byte, the refusal it writes under a "
             "UTF-8 locale; and a child that names no encoding prints other "
             "bytes under `PYTHONIOENCODING=utf-8-sig`, so a byte-order mark "
             "is a difference this arm sees")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    path = os.path.join(PACKAGE, "__main__.py")
    root = os.path.dirname(PACKAGE)
    source = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    forced = None if source is None else _guard_forced(source)
    entries: list[str] = []
    ok = forced is not None
    if forced is None:
        entries.append(f"no version test was found in {path} to force")
    with _box("golden-census-stdout-") as box:
        name = os.path.join(box, "café 日本語 \udcff.toml")
        census = [sys.executable, "-m", IMPORT_NAME, "census", "--manifest",
                  name]
        runs: list[tuple[str, list[str], str, str, tuple[bytes, ...], str]] = [
            ("census --manifest", census, box, root,
             ("—".encode(), os.fsencode(name)), "the dash and the name")]
        if forced is not None:
            copy = os.path.join(box, "floor")
            os.makedirs(os.path.join(copy, IMPORT_NAME))
            for leaf, text in (("__init__.py", ""), ("__main__.py", forced)):
                pathlib.Path(os.path.join(copy, IMPORT_NAME, leaf)).write_text(
                    text, encoding="utf-8")
            runs.append(("the floor's refusal", [sys.executable, "-m",
                                                 IMPORT_NAME, "--version"],
                         copy, copy, (b"REFUSED: ", "—".encode()),
                         "`REFUSED:` and the dash"))
        for what, argv, cwd, pythonpath, needles, words in runs:
            code, printed, said = _stdout_in(argv, cwd, pythonpath, {})
            held = all(needle in printed for needle in needles) and not said
            ok = ok and held
            entries.append(f"{what} under a UTF-8 locale -> exit {code}, "
                           f"{len(printed)} byte(s), {words} held={held}"
                           + _last_said(said))
            for leg, variables in _NOT_UTF8:
                leg_code, leg_printed, leg_said = _stdout_in(
                    argv, cwd, pythonpath, variables)
                same = leg_printed == printed
                ok = ok and leg_code == code and same and not leg_said
                entries.append(
                    f"{what} under {leg} -> exit {leg_code}, same bytes={same}"
                    + _last_said(leg_said))
        closed = [sys.executable, "-P", "-c", _CLOSED, *census]
        code, printed, said = _stdout_in(closed, box, root, {})
        held = code == 2 and not printed and said.startswith(_UNUSABLE)
        leg_code, leg_printed, leg_said = _stdout_in(closed, box, root, _UTF16)
        same = leg_said == said
        ok = ok and held and leg_code == 2 and not leg_printed and same
        entries.append(
            f"census --manifest with standard output closed under a UTF-8 "
            f"locale -> exit {code}, {len(printed)} byte(s) on standard "
            f"output, {len(said)} on standard error, the refusal held={held}; "
            f"under PYTHONIOENCODING=utf-16 -> exit {leg_code}, "
            f"{len(leg_printed)} byte(s) on standard output, same bytes on "
            f"standard error={same}")
        unnamed = [sys.executable, "-P", "-c", _UNNAMED]
        plain = _stdout_in(unnamed, box, root, {})[1]
        marked = _stdout_in(unnamed, box, root, _UTF8_SIG)[1]
        ok = ok and plain == b"x\n" and marked != plain
        entries.append(
            f"a child that names no encoding -> {len(plain)} byte(s) under a "
            f"UTF-8 locale, {len(marked)} under PYTHONIOENCODING=utf-8-sig, "
            f"other bytes={marked != plain}")
    check(label, ok, ACTUAL + "; ".join(entries),
          next="In `cli.main`, call `core.in_utf8` on standard output with "
               "`errors=\"surrogateescape\"` and on standard error, both "
               "before `usable` and before anything is written, and in "
               "`__main__` name `encoding=\"utf-8\"` on `sys.stdout` above "
               "the floor's refusal.")


# ------------------------------------- a byte no UTF-8 decoder reads (llll)
#
# Strict decoding is the right choice — a substitute character recorded in
# place of what the subject printed would be a golden of golden-census's
# repair rather than of the subject — and it has a consequence: the decoder
# raises, and an exception nobody catches reaches the reader as a traceback.
# Crashing is never the appropriate choice, so `launch` names the byte and
# the offset instead.

#: The planted subject: one byte that cannot begin a UTF-8 sequence, on
#: stdout, before anything else. Written through the buffer because a subject
#: that could print it as text would not be the case this arm is about.
_BAD_BYTE_SUBJECT = ("import sys\n"
                     "sys.stdout.buffer.write(b'\\xff\\n')\n")

#: The same byte on standard error, three bytes in, after a clean line on
#: standard output: the offset is standard error's, and the refusal must
#: say which stream it counts in.
_BAD_BYTE_STDERR = ("import sys\n"
                    "print('clean')\n"
                    "sys.stdout.flush()\n"
                    "sys.stderr.buffer.write(b'ok \\xff\\n')\n")


def _bad_byte_control(check: CheckRow, skip: SkipRow) -> None:
    """(llll) a subject printing a byte that is not UTF-8 is a refusal, not a
    traceback.

    The RED half is the decode the clause wraps: the same planted subject
    through a bare `subprocess.run(text=True, encoding="utf-8")`, which
    decodes as strictly as `core._decoded` does and raises the same
    exception. A refusal asserted without it would prove only that the arm's
    subject exists.

    The refusal names the stream the offset counts in, and its `next:`
    line names that stream too: a second subject prints a clean line on
    standard output and the byte three bytes into standard error, where
    "of its output" would send the reader to the wrong stream.
    """
    label = ("llll  a subject that prints a byte no UTF-8 decoder can read "
             "reaches the reader as a REFUSAL naming what was run and the "
             "byte offset — never as a traceback out of the decoder; the "
             "SAME planted subject through the bare `subprocess.run` the "
             "clause wraps raises the UnicodeDecodeError the refusal replaces; "
             "the refusal and its next: line name the stream, standard "
             "output there, and standard error for a subject that prints a "
             "clean line and then the byte three bytes into standard error")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    said = ""
    fault = ""
    control = "decoded"
    with _box("golden-census-badbyte-") as box:
        subject = os.path.join(box, "badbyte.py")
        pathlib.Path(subject).write_text(_BAD_BYTE_SUBJECT, encoding="utf-8")
        argv = [sys.executable, subject]
        try:
            launch(argv, "the planted subject", cwd=box,
                   stdin=subprocess.DEVNULL)
        except Refusal as refused:
            said = refusal_text(refused)
            fault = type(refused.__cause__).__name__
        except UnicodeDecodeError as escaped:
            fault = f"escaped as {type(escaped).__name__}"
        on_stderr = os.path.join(box, "stderr.py")
        pathlib.Path(on_stderr).write_text(_BAD_BYTE_STDERR, encoding="utf-8")
        err_said = ""
        try:
            launch([sys.executable, on_stderr], "the planted subject",
                   cwd=box, stdin=subprocess.DEVNULL)
        except Refusal as refused:
            err_said = refusal_text(refused)
        try:
            subprocess.run(argv, check=False, text=True, encoding="utf-8",
                           capture_output=True, stdin=subprocess.DEVNULL)
        except UnicodeDecodeError:
            control = "UnicodeDecodeError"
    named = ("0xff" in said and "byte offset 0" in said
             and "the planted subject" in said and subject in said)
    first, _sep, after = said.partition("\n")
    err_first, _sep, err_after = err_said.partition("\n")
    streams = ("byte offset 0 of its standard output" in first
               and "on its standard output" in after
               and "byte offset 3 of its standard error" in err_first
               and "on its standard error" in err_after)
    check(label,
          named and fault == "UnicodeDecodeError"
          and control == "UnicodeDecodeError" and streams,
          f"{ACTUAL}the refusal read {_one_line(said, 160)!r}, its cause was "
          f"{fault or '(nothing was raised)'}, and it names the byte, the "
          f"offset and the command={named}; the control — the bare "
          f"`subprocess.run` over the same subject — {control}; the byte on "
          f"standard error read "
          f"{err_first.partition(' The command was')[0]!r}, and both name "
          f"their stream in the sentence and the next: line={streams}",
          next="Read `core.launch`: a text run decodes strictly, and the "
               "UnicodeDecodeError that raises is a refusal naming the byte "
               "and the offset rather than a traceback.")


# --------------------------------- what a child is given to read (vvvvvv)
#
# A child that reads its standard input reads whatever golden-census itself
# was started with, unless something stands between the two — and then a
# census control's verdict follows the shell the command was typed in. What
# stands between them is `launch`'s default. The claim is about every call of
# `launch`, so it is asserted by a run that measures a bytes run and a text
# run, by a control showing that the run's plant can be read, and by a walk
# over every place the package reaches `launch` or starts a process itself.

#: What the arm puts on standard input, as bytes: the `drift` control
#: compares bytes and the control half compares these.
_PLANTED_INPUT = b"planted on standard input\n"

#: The planted command: its standard input copied to its output, then the
#: pinned variable when it is set and the clock when it is not.
_COPIES_STDIN = ("import os\n"
                 "import sys\n"
                 "import time\n"
                 "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
                 "stamp = (os.environ.get('SOURCE_DATE_EPOCH')\n"
                 "         or str(time.time_ns()))\n"
                 "sys.stdout.buffer.write(stamp.encode() + b'\\n')\n")

#: The planted census: the environment and two rows that run the command
#: above. The pin's `drift` control is a bytes run, the one call of `launch`
#: outside the self-check's own modules that is; the `state` row is a text
#: run, as every other is, and the census prints the first line of what its
#: command printed.
_COPIES_STDIN_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the clock"
disposition = "pin"
variable    = "SOURCE_DATE_EPOCH"
value       = "0"
finding     = "the planted command prints the clock unless the variable is set"
control     = { shape = "drift", command = ["<PYTHON>", "<HERE>/copies.py"], wait = 0.0 }

[[input]]
name        = "what a text run is given to read"
disposition = "state"
commands    = [["<PYTHON>", "<HERE>/copies.py"]]
finding     = "the planted command copies its standard input to its output"
'''

#: The planted command of the second half: it reads its standard input to
#: the end and reports, as one JSON object of integers, the bytes it got and
#: whether descriptor 0 is the null device. A pipe reads as end of file too,
#: so the second number is what tells the null device from a pipe. As `check`
#: it exits 0 only when it read nothing from the null device; as `write PATH`
#: it also writes the object to PATH, which gives the surface a file for its
#: counter; as anything else it only prints.
_REPORTS_STDIN = ("import json\n"
                  "import os\n"
                  "import sys\n"
                  "\n"
                  "data = sys.stdin.buffer.read()\n"
                  "null = os.path.samestat(os.fstat(0), os.stat(os.devnull))\n"
                  "seen = {'read': len(data), 'null_device': int(null)}\n"
                  "if sys.argv[1] == 'check':\n"
                  "    sys.exit(0 if not data and null else 1)\n"
                  "if sys.argv[1] == 'write':\n"
                  "    with open(sys.argv[2], 'w', encoding='utf-8') as out:\n"
                  "        out.write(json.dumps(seen) + '\\n')\n"
                  "print(json.dumps(seen))\n")

#: What `_REPORTS_STDIN` prints when it is given nothing to read: end of file
#: at once, on the null device.
_READS_NOTHING = {"read": 0, "null_device": 1}

#: The census of the second half: a precondition, a `state` command and the
#: work directory's fold, so that `census` and `capture` each start the
#: command through `launch` more than once. A precondition that fails is a
#: refusal at 2 before any row runs.
_REPORTS_STDIN_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "standard input is the null device"
disposition = "precondition"
check       = "command"
command     = ["<PYTHON>", "<HERE>/reports.py", "check"]
expect      = "exit 0"
finding     = "the planted command exits 0 only when it reads end of file from the null device"

[[input]]
name        = "what a state command is given to read"
disposition = "state"
commands    = [["<PYTHON>", "<HERE>/reports.py", "state"]]
finding     = "the planted command prints what it was given to read"
''' + _STUB_WORK_FOLD

#: The manifest of the second half: a setup step, a subject and a counter,
#: each started by golden-census with the planted command.
_REPORTS_STDIN_MANIFEST = _subject("reports", '["<PYTHON>", "reports.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["reading"]

[[setup]]
name    = "check"
command = ["<PYTHON>", "<HERE>/reports.py", "check"]

[surfaces.reading]
args    = ["write", "<WRITES>"]
writes  = "<WORK>/reading.json"
needs   = ["check"]
counter = ["<PYTHON>", "<HERE>/reports.py", "count"]
'''

#: What the planted copy of `census.py` carries: a call of `launch` that asks
#: for golden-census's own standard input, a `launch` named without being
#: called, a process started without `launch`, and a member of `subprocess`
#: fetched by `getattr` with a string built at run time. Written as source
#: rather than compiled, because the arm never RUNS it.
_PLANTED_INHERIT = ('def _planted() -> None:\n'
                    '    launch(["git", "--version"], "the planted '
                    'inheritance", stdin=None)\n'
                    '    start = launch\n'
                    '    subprocess.run(["git", "--version"], check=False)\n'
                    '    getattr(subprocess, "r" + "un")(["git", "--version"], '
                    'check=False)\n')

#: What the walk has to say of the plant, one sentence per line of its body.
_PLANTED_SAID = ("passes stdin=None",
                 "names `launch` without calling it",
                 "starts a process by `subprocess.run`, passing no `stdin=`",
                 "names a member of `subprocess` through `getattr`, "
                 "which this walk cannot read")

#: Every function that starts a process without `launch`, under the module
#: it is reached through. `os.exec*` and `os.spawn*` are families, matched
#: by how their names open.
_STARTERS = {"subprocess": ("run", "Popen", "call", "check_call",
                            "check_output", "getoutput", "getstatusoutput"),
             "os": ("system", "popen", "fork", "forkpty", "posix_spawn",
                    "posix_spawnp")}
_STARTER_FAMILIES = ("exec", "spawn")

#: The two places the package starts a process itself, as the walk reads
#: them: the module, the function, what it calls and what it passes. The
#: anchor's standard input is typed at its site; `launch` hands on its
#: caller's.
_DIRECT_STARTS = [
    ("core.py", "start_anchor", "subprocess.Popen", "stdin=subprocess.DEVNULL"),
    ("core.py", "launch", "subprocess.Popen", "stdin=stdin"),
]


#: The modules whose members the walk will not take from a string: the two
#: that start a process and the one that owns `launch`.
_GETATTR_OF = (*_STARTERS, "core")


def _starters_named() -> str:
    """How the row's sentence names `_STARTERS`, so the walk and the
    sentence cannot drift apart."""
    return ", ".join(
        [f"`{module}.{function}`" for module, functions in _STARTERS.items()
         for function in functions]
        + [f"`os.{family}*`" for family in _STARTER_FAMILIES])


def _starts_a_process(module: str, function: str) -> bool:
    return (function in _STARTERS.get(module, ())
            or (module == "os" and function.startswith(_STARTER_FAMILIES)))


class _Reach(NamedTuple):
    """One place a module reaches `launch` or a function of `_STARTERS`."""
    line: int
    owner: str
    #: `launch`, or `subprocess.run` and its like.
    what: str
    called: bool
    #: Of a call, what it passes: `stdin=<as written>`, `**<as written>`
    #: where it passes no `stdin=`, or the empty string for a call that
    #: passes neither. Of anything else, the sentence that says how the name
    #: is reached.
    said: str


def _reaches(source: str, name: str) -> list[_Reach]:
    """Every place `source` reaches `launch` or a function that starts a
    process: a call, a name that is not called — assigned, or handed to
    another function — and an import that gives one another name.

    A name inside an annotation is not a reach: `core.RunGroup` types its
    anchor as `subprocess.Popen[bytes]` and starts nothing by it. A member of
    one of `_GETATTR_OF` fetched with `getattr` is a reach at the `getattr`,
    whatever string names the member, because a string built at run time is
    not one this walk reads. A route through an alias of the module is not
    followed.
    """
    tree = ast.parse(source, filename=name)
    owners = _ast_owners(tree)
    calls = {id(node.func): node for node in ast.walk(tree)
             if isinstance(node, ast.Call)}
    typed = {id(inner) for node in ast.walk(tree)
             for note in (getattr(node, "annotation", None),
                          getattr(node, "returns", None))
             if isinstance(note, ast.AST) for inner in ast.walk(note)}
    found: list[_Reach] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            source_of = getattr(node, "module", None) or ""
            for alias in node.names:
                if isinstance(node, ast.Import):
                    what = alias.name if alias.name in _STARTERS else ""
                    renamed = bool(alias.asname) and alias.asname != alias.name
                elif alias.name == "launch":
                    what = "launch"
                    renamed = alias.asname not in (None, "launch")
                else:
                    what = (f"{source_of}.{alias.name}"
                            if _starts_a_process(source_of, alias.name)
                            else "")
                    renamed = True
                if what and renamed:
                    found.append(_Reach(
                        node.lineno, _owner_at(owners, node.lineno), what,
                        False, f"imports `{what}` as "
                               f"`{alias.asname or alias.name}`"))
            continue
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "getattr" and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in _GETATTR_OF):
            found.append(_Reach(
                node.lineno, _owner_at(owners, node.lineno), "getattr",
                False, f"names a member of `{node.args[0].id}` through "
                       "`getattr`, which this walk cannot read"))
            continue
        if isinstance(node, ast.Name) and node.id == "launch":
            what = "launch"
        elif isinstance(node, ast.Attribute) and node.attr == "launch":
            what = "launch"
        elif (isinstance(node, ast.Attribute)
              and isinstance(node.value, ast.Name)
              and _starts_a_process(node.value.id, node.attr)):
            what = f"{node.value.id}.{node.attr}"
        else:
            continue
        if id(node) in typed:
            continue
        call = calls.get(id(node))
        if call is None:
            found.append(_Reach(node.lineno, _owner_at(owners, node.lineno),
                                what, False,
                                f"names `{what}` without calling it"))
            continue
        # A call that passes `stdin=` by name is read by that alone: a `**`
        # mapping beside it cannot hold `stdin` too, which Python refuses.
        passed = ([f"stdin={ast.unparse(word.value)}"
                   for word in call.keywords if word.arg == "stdin"]
                  or [f"**{ast.unparse(word.value)}"
                      for word in call.keywords if word.arg is None])
        found.append(_Reach(call.lineno, _owner_at(owners, call.lineno),
                            what, True, ", ".join(passed)))
    return found


def _launch_calls(source: str, name: str) -> list[tuple[int, str, str]]:
    """`(line, owner, what it passes)` for every call of `launch` in
    `source`; what it passes is `stdin=<as written>`, `**<as written>` where
    it passes no `stdin=`, or the empty string for a call that passes
    neither.

    An `ast` walk and not a text search: three arms plant a call of `launch`
    inside a string, as source, and a search that counted strings would
    count their plants.
    """
    return [(reach.line, reach.owner, reach.said)
            for reach in _reaches(source, name)
            if reach.called and reach.what == "launch"]


def _stdin_sites(source: str, name: str) -> list[str]:
    """`file:line in owner() — what it does` for every place a module that
    is not one of the self-check's own decides what a child reads, or could:
    a call of `launch` that passes `stdin=` or a `**` mapping, a `launch` or
    a process-starting function that is named without being called or
    imported under another name, and a process started without `launch`
    anywhere but at `_DIRECT_STARTS`. An arm says what its child needs —
    this one hands its child a file — so the arms' modules are not walked."""
    if is_arm_module(name):
        return []
    sites = []
    for reach in _reaches(source, name):
        if not reach.called:
            said = reach.said
        elif reach.what == "launch":
            said = f"passes {reach.said}" if reach.said else ""
        elif (name, reach.owner, reach.what, reach.said) in _DIRECT_STARTS:
            said = ""
        else:
            said = (f"starts a process by `{reach.what}`, passing "
                    f"{reach.said or 'no `stdin=`'}")
        if said:
            sites.append(f"{name}:{reach.line} in {reach.owner}() — {said}")
    return sorted(sites)


def _recorded_reads(golden: str) -> tuple[str | None, object]:
    """What a capture of `_REPORTS_STDIN_MANIFEST` recorded: the text of the
    subject's `reading.out` and the counter's `_counts` object, each `None`
    where the capture left no such file or one that does not read."""
    inner = os.path.join(golden, "_subject")
    try:
        said = pathlib.Path(inner, "reading.out").read_text(encoding="utf-8")
        surfaces = json.loads(pathlib.Path(inner, SURFACES_FILE)
                              .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    return said, surfaces.get("_counts") if isinstance(surfaces, dict) else None


def _closed_stdin_control(check: CheckRow, skip: SkipRow) -> None:
    """(vvvvvv) a child started through `launch` reads nothing from
    golden-census's own standard input, unless its caller hands it one.

    The run is the real command line in a child, because the claim is about
    what a process inherits: `census --manifest M`, started with a planted
    file on standard input, over a census that runs one command twice. The
    command copies its standard input to its output. As the pin's `drift`
    control it is a bytes run: with the input inherited, one pinned run
    reads the file and the other reads end of file, so the two differ and
    the row is `[FAIL]`. As the `state` row's command it is a text run, as
    every call of `launch` outside the self-check's own modules is but the
    drift control's: the census prints the first line of what it printed, so
    with the input inherited the planted line is in the run's log. The file
    is read once, by whichever of the two is started first, so the arm
    asserts both.

    The control is the drift command itself, started with the same file
    through `launch(stdin=...)`: it prints the file's bytes. Without it a
    command that read nothing would pass the run for the wrong reason, and
    so would a `launch` that handed no caller's standard input on.

    The second command of `_REPORTS_STDIN` is what tells a pipe from the null
    device, which the first cannot: a pipe that nothing writes to reads as
    end of file too. It is started by `census` and by `capture`, over a
    manifest whose precondition, `[[setup]]` step, subject and counter each
    run it, so a `launch` that hands the parent's input, or a pipe, to some
    callers by the phrase it was given is seen. Its control is the same
    command handed the file.

    The walk is over every module outside the self-check's own. No call of
    `launch` passes `stdin=` or a `**` mapping, and `launch` is named
    nowhere except to call it, so the default is the one owner of what a
    child of `launch` reads and no call reaches `launch` by a name the walk
    does not follow. A process is started without `launch` at exactly the
    two places of `_DIRECT_STARTS`, each passing what is written there, and
    no function of `_STARTERS` is named except to call it or to annotate a
    type. The same walk over a copy of census.py with `_PLANTED_INHERIT` in
    it must name each of the four plants with the file, the line and the
    function.
    """
    label = ("vvvvvv  a child started through `launch` reads nothing from "
             "golden-census's own standard input: `census --manifest M`, "
             "started with a planted file on standard input over a census "
             "whose `drift` command copies its standard input to its "
             "output, exits 0 with that row [PASS] and its pinned runs "
             "identical, and the planted line nowhere in its log, where the "
             "census prints the first line its `state` command — a text "
             "run, as the drift control's is a bytes run — printed; the "
             "drift command itself, handed the same file through "
             "`launch(stdin=...)`, prints the file's bytes, so the plant can "
             "be read and a caller's own standard input is handed on; a "
             "second command that reports how many bytes it read and whether "
             "descriptor 0 is the null device, started with the same file "
             "by `census` (its precondition and its `state` command) and by "
             "`capture` (its precondition, a `[[setup]]` step, the subject "
             "and the counter), is given end of file on the null device by "
             "every one: both runs exit 0, the `state` command prints "
             "`{\"read\": 0, \"null_device\": 1}`, and the golden holds that "
             "line as the subject's output and that object as the counter's "
             "counts, where the same command handed the file reads its "
             "bytes off a descriptor that is not the null device; no "
             f"call of `launch` outside {arm_modules_named()} passes "
             "`stdin=` or a `**` mapping, and no module outside them names "
             "`launch` except to call it; outside them the package starts a "
             "process without `launch` at exactly two places — the "
             "process-group anchor, which passes `stdin=subprocess.DEVNULL`, "
             "and `launch`'s own `subprocess.run`, which passes the "
             f"caller's — where a start is a call of {_starters_named()}, "
             "and none of those is named except to call it or to annotate a "
             "type; and the same walk over a copy of census.py with a "
             "`stdin=None`, a `launch` named without a call, a "
             "`subprocess.run` and a `getattr(subprocess, \"r\" + \"un\")` "
             "planted in it names each with that file, its "
             "line and the function it sits in")
    walked = _walk_for_plant(_stdin_sites, label, skip, "census.py",
                             "inheritance")
    if walked is None:
        return
    sources, sites = walked
    outside = {name: source for name, source in sources.items()
               if not is_arm_module(name)}
    calls = sum(len(_launch_calls(source, name))
                for name, source in outside.items())
    starts = sorted((name, reach.line, reach)
                    for name, source in outside.items()
                    for reach in _reaches(source, name)
                    if reach.called and reach.what != "launch")
    only = (sorted((name, reach.owner, reach.what, reach.said)
                   for name, _, reach in starts) == sorted(_DIRECT_STARTS))
    started = [f"{name}:{line} in {reach.owner}() — `{reach.what}` passes "
               f"{reach.said or 'no `stdin=`'}"
               for name, line, reach in starts]
    passing = [site for site in sites if " — passes " in site]
    renamed = [site for site in sites
               if " — names " in site or " — imports " in site]
    planted_source = (sources["census.py"].rstrip("\n") + "\n\n\n"
                      + _PLANTED_INHERIT)
    first = (len(planted_source.rstrip("\n").splitlines())
             - len(_PLANTED_SAID) + 1)
    planted = [site for site in _stdin_sites(planted_source, "census.py")
               if site not in sites]
    wanted = [f"census.py:{first + index} in _planted() — {said}"
              for index, said in enumerate(_PLANTED_SAID)]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(PACKAGE)
    with _box("golden-census-stdin-") as box:
        manifest = _scratch(box, census_text=_COPIES_STDIN_CENSUS,
                            extra={"copies.py": _COPIES_STDIN})
        given = os.path.join(box, "given.txt")
        pathlib.Path(given).write_bytes(_PLANTED_INPUT)
        with open(given, "rb") as handle:
            ran = launch(_package_argv("-m", IMPORT_NAME, "census",
                                       "--manifest", manifest),
                         "the closed-input arm's run", env=env, cwd=box,
                         stdin=handle)
        with open(given, "rb") as handle:
            echoed = launch([sys.executable, os.path.join(box, "copies.py")],
                            "the closed-input arm's control", env=env,
                            cwd=box, stdin=handle, text=False)
        # The second half: the same file on standard input, over a command
        # that says what descriptor 0 is as well as what it read, started by
        # `census` and by `capture` — and by hand, as the control.
        reports = os.path.join(box, "reports")
        report_manifest = _scratch(
            reports, manifest_text=_REPORTS_STDIN_MANIFEST,
            census_text=_REPORTS_STDIN_CENSUS,
            extra={"reports.py": _REPORTS_STDIN})
        recorded = os.path.join(box, "reports-golden")
        with open(given, "rb") as handle:
            censused = launch(_package_argv("-m", IMPORT_NAME, "census",
                                            "--manifest", report_manifest),
                              "the closed-input arm's census run", env=env,
                              cwd=box, stdin=handle)
        with open(given, "rb") as handle:
            captured = launch(_package_argv("-m", IMPORT_NAME, "capture",
                                            "--manifest", report_manifest,
                                            "--out", recorded),
                              "the closed-input arm's capture run", env=env,
                              cwd=box, stdin=handle)
        with open(given, "rb") as handle:
            reported = launch([sys.executable,
                               os.path.join(reports, "reports.py"), "count"],
                              "the closed-input arm's second control",
                              env=env, cwd=box, stdin=handle)
        subject_said, counter_said = _recorded_reads(recorded)
    lines = ran.stdout.splitlines()
    at = next((index for index, line in enumerate(lines)
               if "two runs of" in line), None)
    row = lines[at].split("census pin")[0].strip() if at is not None else ""
    detail = (lines[at + 1].strip().removeprefix(ACTUAL)
              if at is not None and at + 1 < len(lines) else _NO_VERDICT)
    read_back = echoed.stdout.startswith(_PLANTED_INPUT)
    leaked = _PLANTED_INPUT.decode().strip() in ran.stdout
    nothing = json.dumps(_READS_NOTHING)
    control = json.dumps({"read": len(_PLANTED_INPUT), "null_device": 0})
    state_read = nothing in censused.stdout
    elsewhere = "".join(_heard(proc.stderr).not_from(PACKAGE)
                        for proc in (ran, censused, captured))
    check(label,
          ran.returncode == 0 and row == "[PASS]"
          and "identical=True" in detail and not leaked and read_back
          and censused.returncode == 0 and state_read
          and captured.returncode == 0 and subject_said == nothing + "\n"
          and counter_said == _READS_NOTHING
          and reported.stdout.strip() == control
          and not sites and only and sorted(planted) == sorted(wanted)
          and not elsewhere,
          f"{ACTUAL}the run exited {ran.returncode}, its drift row "
          f"{row or '(not printed)'} — {_one_line(detail, DIFFERENCE)}; the planted "
          f"line is in the run's log={leaked}; the control printed "
          f"{len(echoed.stdout)} byte(s), opening with the "
          f"{len(_PLANTED_INPUT)} planted={read_back}; over the second "
          f"command, `census` exited {censused.returncode} and its state "
          f"command printed {nothing}={state_read}, `capture` exited "
          f"{captured.returncode} and recorded {subject_said!r} for the "
          f"subject and {counter_said!r} for the counter, and the command "
          f"handed the file printed {reported.stdout.strip()!r}, wanting "
          f"{control!r}; outside the "
          f"self-check's own modules, {len(passing)} of {calls} call(s) of "
          f"`launch` pass `stdin=` or `**` {passing}; `launch` or a "
          f"function that starts a process is named without a call, or "
          f"imported under another name, at {renamed}; a process is started "
          f"without `launch` at {started}, which is the anchor and "
          f"`launch`'s own and no other={only}; "
          f"the planted sites came back as {planted} and had to be {wanted}"
          f"{elsewhere}",
          next="Read `core.launch`: `stdin` defaults to "
               "`subprocess.DEVNULL` and is handed to the child as the "
               "caller passed it, in a text run and in a bytes run. A call "
               "of `launch` outside the self-check's own modules passes no "
               "`stdin=` and calls `launch` by that name: the default is "
               "the one owner of what a child reads. A process the package "
               "starts without `launch` is the anchor's or `launch`'s own; "
               "any other goes through `launch`.")


# --------------------------------------- the run a pre-run refusal stopped
#
# Between "golden-census has decided what to run" and "the child has started"
# there is a window, and a refusal raised in it is the one a reader has to
# reconstruct by hand. It carries the argv and the environment instead.

#: A surface asking for `<WRITES>` without a `writes` key: the token is a name
#: of the manifest's vocabulary, so it loads, and it has no value in a run
#: that makes no file, so the expansion refuses — inside the window, after the
#: environment is built and before the child starts.
_NO_WRITES_MANIFEST = _STUB_MANIFEST.replace(
    'args = ["--help"]', 'args = ["--help", "<WRITES>"]')

#: The control: a manifest that never gets as far as a command. It is refused
#: by the loader, where there is no run to describe, and carries no block.
_NO_COMMAND_MANIFEST = _STUB_MANIFEST.replace(
    'command = ["<PYTHON>", "stub.py"]', 'command = []')

#: How the block opens, and the line that carries the environment. Named here
#: because the arm asserts the shape a READER sees and `census.about_to_run`
#: composes it; two spellings of one sentence would drift.
_ABOUT = "about to run"
_ENVIRONMENT = "the environment it was built with"


def _refusal_over(manifest_text: str) -> str:
    """The two-or-more lines one scratch manifest refuses with."""
    with _box("golden-census-pending-") as box:
        path = _scratch(box, manifest_text=manifest_text)
        return _printed_refusal(lambda: capture(
            load_manifest(path), os.path.join(box, "out"), io.StringIO()))


#: The leaf arm `kkkk` plants under the running user's home directory, to give
#: the block's `<HOME>` fold something of its own to fold. It need not exist:
#: a surface's `env` prints it as the reader wrote it, and no run looks the
#: entry up.
_HOME_PLANT_LEAF = "golden-census-kkkk-home-plant"


def _pending_control(check: CheckRow, skip: SkipRow) -> None:
    """(kkkk) a refusal raised before a run carries the run it stopped."""
    label = ("kkkk  a refusal raised AFTER golden-census has built a command "
             "and an environment and BEFORE the child starts carries both, "
             "under its `next:` line: the expanded argv and the built "
             "environment as NAME=value, folded, with the running user's home "
             "directory replaced by <HOME> — asserted over a value of "
             "a surface's `env` this arm PLANTS under that home, so the fold "
             "is judged on input the arm gave it and not on whatever the "
             "reader's environment happens to hold. The positive control is a "
             "refusal raised before a command exists — a manifest whose "
             "`[subject] command` is empty — which carries nothing new")
    home = os.path.expanduser("~")
    if not home or home == "/":
        # `census.about_to_run` folds nothing when the home is empty or `/`,
        # and it is right not to: `/` as a home matches every absolute path
        # there is. The half that asserts the fold FIRED cannot be built
        # here, and a row whose plant cannot be built is a disclosed SKIP.
        skip(label, f"the running user's home is {home!r}, which the block's "
                    "own rule folds nothing for, so there is no <HOME> to "
                    "plant a value under. Nothing is claimed about the fold "
                    "here.")
        return
    planted = os.path.join(home, _HOME_PLANT_LEAF)
    # PLANTED, not found: a variable of the surface's own `env`, which the
    # block prints whole through the fold. `PATH` is passed through and
    # prints by name and length, so it can carry no home path; the arm
    # reading one off the reader's environment would assert the output of a
    # fold it gave no input to — green on a machine whose value happens to
    # hold a home-rooted entry and red on one whose does not, which is a
    # verdict about the machine.
    pre_run = _refusal_over(
        _NO_WRITES_MANIFEST + f"env = {{ HOME_PLANT = '{planted}' }}\n")
    parse_time = _refusal_over(_NO_COMMAND_MANIFEST)
    carries = (_ABOUT in pre_run and _ENVIRONMENT in pre_run
               and "GOLDEN_CENSUS_CHILD=1" in pre_run
               and "stub.py" in pre_run)
    # The home directory is the one path `own_log` cannot fold, because no
    # census row names a reader's home; the block folds it itself, and this is
    # what says so. The planted leaf survives the fold and the whole home does
    # not, which is the fold doing its work rather than the value being absent.
    folded = "<HOME>" + os.sep + _HOME_PLANT_LEAF
    no_home = (planted not in pre_run and home not in pre_run
               and folded in pre_run)
    quiet = (parse_time.startswith("REFUSED: ")
             and _ABOUT not in parse_time and _ENVIRONMENT not in parse_time)
    check(label, carries and no_home and quiet,
          f"{ACTUAL}the pre-run refusal -> carries the argv and the "
          f"environment={carries}; the planted `env` value under the home "
          f"reaches it as {folded!r}: {folded in pre_run}, and neither the "
          f"planted path nor the home itself survives: "
          f"{planted not in pre_run and home not in pre_run}; the parse-time "
          "refusal -> "
          + ("no block" if quiet else "A BLOCK: " + _one_line(parse_time, DIFFERENCE)),
          next="Read `core.attaching` and `census.about_to_run`: the window "
               "is opened where a run starts being built, and the block is "
               "printed by `core.refusal_text`, which is the one printer of "
               "a refusal there is.")


# ------------------------------- which controls precede which command
#
# Two arms over one decision, divided the way the decision divides. `jjjjj`
# says WHICH block runs in front of each form, by recording the calls the real
# command line makes, and so what a red arm of golden-census's OWN does to a
# reader's capture — nothing. `lllll` says what a red control of the reader's
# OWN census does, command by command, with nothing rebound at all.
#
# `jjjjj` plants through `_fresh_module`: a second, independent copy of `cli`
# whose module-level `census_check` is rebound and whose `main` is handed a
# stand-in for the runner of `--selfcheck`. Its red half is `census_check`
# rebound to the package's own block, the one arrangement the split of the
# two blocks rules out, so it goes red on exactly the change it exists to
# hold.
#
# `--selftest` is absent from every table here and cannot be added: it IS the
# whole app, and an entry that ran it from inside an arm would not terminate.
# `docs.PRICED` leaves it out for the same reason.


def _recording(calls: list[str], name: str, code: int = 0) -> Any:
    """A stand-in for one entry point: it records that it ran and returns
    `code` without running a control.

    What these arms ask is WHICH block a form reaches, and a stand-in answers
    that in microseconds where the package's own block costs seconds. The real
    blocks are run by `--selfcheck` and by every arm around this one, so
    nothing here is the only place either is exercised.
    """
    def entry(out: Any, manifest: Any = None, *args: Any, **kwargs: Any) -> int:
        calls.append(name)
        return code
    return entry


def _ran_before(copy: Any, argv: list[str], package_code: int = 0,
                census_code: int = 0) -> tuple[list[str], int, str]:
    """`(the blocks that ran, the exit code, everything printed)` for one run
    of `copy.main(argv)` with both entry points recorded."""
    calls: list[str] = []
    copy.census_check = _recording(calls, "census", census_code)
    code, printed = _quietly(functools.partial(
        copy.main, selfcheck=_recording(calls, "package", package_code)), argv)
    return calls, code, printed


def _precedence_forms(manifest: str, golden: str, box: str
                      ) -> tuple[tuple[str, list[str], tuple[str, ...]], ...]:
    """Every form, its argv, and the blocks that must run in front of it.

    The COMMAND's own outcome is nobody's business here — `mutants` is pointed
    at `proof._STUB_MUTANTS`, whose one mutant passes `mutants.preflight` and
    whose subject is no git repository, so the run ends at the refusal of its
    first clone, which is the cheapest way to reach the dispatch — so every
    row asserts what ran BEFORE the command and nothing about what the command
    then did. The file is written into
    `box` by the caller.
    """
    writer = "import sys; open(sys.argv[1], 'w').write('probe ok\\n')"
    return (
        ("--version", ["--version"], ()),
        ("--selfcheck", ["--selfcheck"], ("package",)),
        ("--selfcheck --manifest", ["--selfcheck", "--manifest", manifest],
         ("package",)),
        ("census", ["census", "--manifest", manifest], ("census",)),
        ("capture", ["capture", "--manifest", manifest,
                     "--out", os.path.join(box, "one")], ("census",)),
        ("capture --twice", ["capture", "--manifest", manifest, "--out",
                             os.path.join(box, "two"), "--twice"], ("census",)),
        ("compare", ["compare", "--manifest", manifest, "--golden", golden],
         ("census",)),
        ("compare --against", ["compare", "--manifest", manifest,
                               "--golden", golden, "--against", golden], ()),
        ("mutants", ["mutants", "--manifest", manifest, "--mutants",
                     os.path.join(box, "mutants.toml")], ("census",)),
        ("probe", ["probe", "--", sys.executable, "-c", writer, WRITES], ()),
        ("init", ["init", os.path.join(box, "scaffold")], ()),
    )


def _precedes_control(check: CheckRow, skip: SkipRow) -> None:
    """(jjjjj) which block runs in front of which form, every form run.

    The package's own arms are regression tests of code that does not move
    between one command of a reader's and the next, so they run where a reader
    asks for them and in front of nothing. The census's controls are about the
    reader's own subject, so they run in front of every command that turns it
    into a golden or a verdict. A table of eleven forms is the only way to say
    that: a rule stated once and a single command run against it would leave
    the other ten to a reader's trust.
    """
    label = ("jjjjj  every form of the command line, run: golden-census's own "
             "arms precede `--selfcheck` alone, the census's controls precede "
             "`capture`, `capture --twice`, `compare` (which captures), "
             "`mutants` and `census`, and NOTHING precedes `--version`, "
             "`compare --against`, `probe` or `init` — asserted as the blocks "
             "each run reached and never as the command's own outcome; and "
             "the same walk over a copy whose `census_check` is the package's "
             "own block, which is what every command ran before the two were "
             "split, comes back with the package's arms in front of `capture`")
    copy = _fresh_module("cli")
    if copy is None:
        skip(label, "this install carries no importable `cli` source to build "
                    "a second copy from, so neither the table nor its planted "
                    "half can be run. Nothing is claimed.")
        return
    with _box("golden-census-precede-") as box:
        manifest = _scratch(box, extra={"mutants.toml": _STUB_MUTANTS})
        golden = os.path.join(box, "golden")
        _made, _code, made_text = _ran_before(
            copy, ["capture", "--manifest", manifest, "--out", golden])
        if not os.path.isdir(golden):
            _capture_broke(check, label,
                           "the stub subject would not capture, so the two "
                           "`compare` rows have no recorded directory to "
                           f"read: {_one_line(made_text, 600)}")
            return
        wrong: list[str] = []
        seen: list[str] = []
        for key, argv, wanted in _precedence_forms(manifest, golden, box):
            calls, _exit, _text = _ran_before(copy, argv)
            seen.append(f"{key} -> {calls or 'nothing'}")
            if tuple(calls) != wanted:
                wrong.append(f"{key}: {calls} wanted {list(wanted)}")
        # The red half, and it is the OLD arrangement restored rather than a
        # fault invented for the occasion: `census_check` bound to the block
        # that runs the package's own arms is what preceded every command
        # before the split, and this arm exists to say that is gone.
        restored: list[str] = []
        copy.census_check = _recording(restored, "package")
        _quietly(copy.main, ["capture", "--manifest", manifest,
                             "--out", os.path.join(box, "restored")])
    check(label, not wrong and restored == ["package"],
          ACTUAL + "; ".join(seen)
          + (f"; WRONG: {wrong}" if wrong else "")
          + "; the copy with the old automatic call restored -> "
          + f"{restored or 'nothing'} in front of `capture`",
          next="`cli.controls_before` is the whole of the decision and "
               "`cli.main` is the only place it is asked; `selfcheck` is "
               "golden-census's own arms and `census_check` is one census's "
               "controls, and neither is the other.")


def _dropped_flag_control(check: CheckRow, skip: SkipRow) -> None:
    """(hhhhhh) `--selftest` and `--selfcheck` beside a subcommand or beside
    each other, a `--manifest` no command reads, and `--version` beside
    anything, are refused rather than dropped.

    Dropped, `--selftest census --manifest M` exited 0 over a census block
    and no self-test: a verdict line for something that never ran. The
    refusals beside a subcommand, of `--manifest` and of `--version` run
    through the real `main` — each is refused before anything starts. The
    two whole-program flags beside each other do NOT: on code that drops one
    of them `main` starts the runner of the other from inside this arm
    (the comment above `_recording` says what that does), so both orders,
    with a `--manifest` and without one, run through a copy of `cli` whose
    `main` is handed recorders for both runners, and the row says which of
    them ran. The same copy is the control: `--selfcheck` alone is shown still to
    reach the self-check without this arm running the self-check from inside
    itself.

    The `next:` of the refusal of the two flags together names both of them,
    in each of the four command lines: a `next:` that names one sends the
    reader to a command that is refused the same way.
    """
    label = ("hhhhhh  `--selftest census --manifest M`, `--selfcheck compare "
             "--manifest M --golden G --against G`, `--selftest --selfcheck` "
             "in both orders, with a `--manifest M` and without one, a bare "
             "`--manifest M`, a `--manifest M` before `init --list` and before "
             "`census --manifest N`, and `--version init --list` are each ONE "
             "`REFUSED:` naming the flag — both flags, where two cannot be "
             "combined — with a `next:` that names both flags too, where two "
             "cannot be combined, at exit 2 and with no process-group "
             "line — refused before anything starts, never dropped at exit 0 "
             "or used in another flag's place — while `--selfcheck` alone "
             "still reaches the self-check and `--version` still exits 0")

    copy = _fresh_module("cli")
    if copy is None:
        skip(label, "this install carries no importable `cli` source to build "
                    "the copy the control runs `--selfcheck` through, so the "
                    "row cannot show the flag still works. Nothing is claimed.")
        return
    said: list[str] = []
    started: list[str] = []
    recorded = functools.partial(
        copy.main, selftest=_recording(started, "the self-test"),
        selfcheck=_recording(started, "the self-check"))
    both = ("--selftest", "--selfcheck")
    ok = True
    both_named: list[bool] = []
    with _box("golden-census-dropped-") as box:
        manifest = _scratch(box)
        golden = os.path.join(box, "golden")
        _plant_marker(golden)
        for flags, argv, through in (
                (("--selftest",), ["--selftest", "census", "--manifest", manifest],
                 main),
                (("--selfcheck",), ["--selfcheck", "compare", "--manifest", manifest,
                                    "--golden", golden, "--against", golden], main),
                (both, ["--selftest", "--selfcheck"], recorded),
                (both, ["--selfcheck", "--selftest"], recorded),
                (both, ["--selftest", "--selfcheck", "--manifest", manifest], recorded),
                (both, ["--manifest", manifest, "--selfcheck", "--selftest"], recorded),
                (("--manifest",), ["--manifest", manifest], main),
                (("--manifest",), ["--manifest", manifest, "init", "--list"], main),
                (("--manifest",), ["--manifest", manifest, "census", "--manifest",
                                   manifest], main),
                (("--version",), ["--version", "init", "--list"], main)):
            code, printed = _quietly(through, argv)
            lines = printed.splitlines()
            refused = [line for line in lines if line.startswith("REFUSED:")]
            named = bool(refused) and all(f"`{flag}`" in refused[0]
                                          for flag in flags)
            next_line = next((line.strip() for line in lines
                              if line.strip().startswith("next: ")), "")
            if len(flags) == 2:     # the `next:` is for the reader who gave both
                both_named.append(all(f"`{flag}`" in next_line
                                      for flag in flags))
            ok = (ok and code == 2 and len(refused) == 1 and named
                  and bool(next_line) and "process group" not in printed)
            said.append(f"{' '.join(argv[:2]).replace(box, '<box>')}"
                        f"{' …' if argv[2:] else ''} -> exit {code}, "
                        + _one_line(printed.replace(box, "<box>"), 110,
                                    empty=_NO_VERDICT))
        beside = list(started)
        calls, selfcheck_code, _printed = _ran_before(copy, ["--selfcheck"])
        version_code, version = _quietly(copy.main, ["--version"])
    control = calls == ["package"] and selfcheck_code == 0 and version_code == 0
    check(label, ok and not beside and control and len(both_named) == 4
          and all(both_named),
          ACTUAL + "; ".join(said)
          + "; the two flags beside each other started "
          f"{beside or 'nothing'}"
          f"; the `next:` of those {len(both_named)} refusals names both "
          f"flags={all(both_named)}"
          + f"; the control: `--selfcheck` alone reached {calls or 'nothing'} "
          f"at exit {selfcheck_code}, `--version` exit {version_code} "
          f"{version.strip()!r}",
          next="`cli.main` refuses a whole-program flag beside a subcommand "
               "or beside the other one, and a `--manifest` with no command, "
               "right after `--version` and before `anchored`; the refusal "
               "of the two flags together names both in its `next:`.")


#: What `main` hands a command line on to, by the name `cli` holds it under.
#: `_recorded` rebinds every one of them on a copy of `cli`, and hands that
#: copy's `main` a recorder for each of `_RUNNERS`, so a flag given
#: twice that is NOT refused starts nothing from inside the arm, and the row
#: says which of them the command line reached. `guard_capture` and
#: `load_mutants` are among them because `aaaaaaa` gives every flag a command
#: requires the manifest's path, which neither takes: recorded, the `--input`
#: and `--only` a command line repeats still reach a recorder. So is
#: `chosen_and_checked`, which is handed what `load_mutants` returned.
_HANDED_ON = ("census_check", "capture", "compare", "run_census",
              "run_mutants", "load_mutants", "chosen_and_checked",
              "guard_capture", "probe", "init")

#: The two runners `main` takes as arguments rather than holds as names,
#: by the keyword it takes each under: `console.main` hands both.
_RUNNERS = ("selftest", "selfcheck")


def _recorded(copy: Any, recorder: Callable[[str], Any]
              ) -> Callable[[list[str]], int]:
    """`copy.main`, with every name of `_HANDED_ON` rebound on `copy` to
    `recorder(name)` and handed `recorder(name)` for each of `_RUNNERS`."""
    for name in _HANDED_ON:
        setattr(copy, name, recorder(name))
    return functools.partial(copy.main,
                             **{name: recorder(name) for name in _RUNNERS})

#: A value that holds a quote of each kind, a space and a newline.
_AWKWARD = "it's \"3\"\n here"


def _arguments_of(parser: argparse.ArgumentParser, command: str = ""
                  ) -> list[tuple[str, argparse.ArgumentParser, argparse.Action]]:
    """`(subcommand, its parser, the argument's action)` for every flag and
    every positional of `parser` and of every subcommand's parser under it,
    read off the table the parser dispatches on as `docs.command_surface`
    reads it. A positional is an action with no `option_strings`. `--help` is
    left out: argparse answers it inside `parse_args`, the first time it is
    given."""
    found: list[tuple[str, argparse.ArgumentParser, argparse.Action]] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found += _arguments_of(sub, name)
        elif not isinstance(action, argparse._HelpAction):
            found.append((command, parser, action))
    return found


def _handed_on(main: Callable[[list[str]], int], argv: list[str]
               ) -> tuple[int | str | None, str]:
    """`_quietly`, for a command line argparse itself may turn down: its
    exit is the code, and what it wrote on standard error is kept off the
    self-check's own."""
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return _quietly(main, argv)
    except SystemExit as left:
        return left.code, "argparse exited before `main` read the flags"


def _given_again_control(check: CheckRow, skip: SkipRow) -> None:
    """(aaaaaaa) a flag given more than once is refused, naming the flag
    and every value it was given, unless the parser declares it `append`.

    Dropped, `compare --manifest A --manifest B --golden G` read `B` and
    printed `IDENTICAL` over it: a verdict about a manifest the reader may
    not have meant, and no word about `A`.

    No flag is named here. The walk is over the parser `cli.build_parser`
    returns, so a flag added to any parser is held by this row from the
    commit that adds it: given twice it is refused, or it is declared
    `append` and both values reach its command. Each flag is also given
    ONCE, which is the control: a rule that refused every flag would pass
    every other assertion of this row.

    A positional is no flag. Each one the parser holds is given as its
    command takes it — two values that are the same where it takes several,
    one where it takes one — and what was given reaches the command: a rule
    that counted a positional's values as a flag given again would refuse
    `probe -- x x`.

    Every run goes through a copy of `cli` whose entry points are recorders,
    for the reason `hhhhhh` gives: on code that drops a repeated flag the
    real `main` would run the command — `--selftest --selftest` a whole
    self-test — from inside this arm.
    """
    label = ("aaaaaaa  every flag of every parser but `--help`, given twice, "
             "is ONE `REFUSED:` naming the flag behind its subcommand, how "
             "many times it was given and every value in the order given — "
             "a flag that takes a value also given three times, one of them "
             "abbreviated, one as `--flag=value` and one with a value that "
             "holds a quote, a space and a newline, all on the one line — "
             "with ONE `next:` naming the flag, at exit 2, with no "
             "process-group line and nothing started; the flags the parser "
             "declares `append` are the ones that repeat, and each of them "
             "given twice reaches its command with both values in order; "
             "a positional is no flag, and one given the same value twice, "
             "or one value where it takes one, is not refused and reaches "
             "its command; and no flag given once is refused for how many "
             "times it was given — which flags and positionals there are is "
             "read from the parser, never from a list; and every runner "
             "`main` takes by keyword, read from its signature, is handed "
             "a recorder")
    copy = _fresh_module("cli")
    if copy is None:
        skip(label, "this install carries no importable `cli` source to build "
                    "the copy every command line here runs through, so no "
                    "flag can be given twice without starting its command. "
                    "Nothing is claimed.")
        return
    reached: list[tuple[str, tuple[Any, ...]]] = []

    def recorder(name: str) -> Any:
        def entry(*args: Any, **kwargs: Any) -> int:
            reached.append((name, args))
            return 0
        return entry

    recorded_main = _recorded(copy, recorder)
    # The runners `main` takes by keyword, read off its signature and not
    # off `_RUNNERS`: a runner `_recorded` hands no recorder is refused by
    # `_unhanded` when its flag is given once, and no `times` refusal is
    # missed for it, so the flag walk below cannot see that it was not handed.
    taken = sorted(name for name, parameter
                   in inspect.signature(copy.main).parameters.items()
                   if parameter.kind is inspect.Parameter.KEYWORD_ONLY)
    refused_flags: list[str] = []
    repeating: list[str] = []
    positionals: list[str] = []
    wrong: list[str] = []
    with _box("golden-census-again-") as box:
        manifest = _scratch(box)
        # `compare --golden` is read by `read_sides` above the recorders, and
        # refuses a file: it is given a directory that holds a capture, which
        # is what a repeated flag of `compare` needs to reach its command.
        golden = os.path.join(box, "golden")
        _plant_marker(golden)
        for command, parser, action in _arguments_of(copy.build_parser()):
            flag = next((name for name in action.option_strings
                         if name.startswith("--")),
                        str(action.metavar or action.dest))
            named = f"{command} {flag}".strip()
            head = [command] if command else []
            for other in parser._actions:
                if (other.required and other.option_strings
                        and other is not action):
                    head += [other.option_strings[-1],
                             golden if other.dest == "golden" else manifest]
            repeats = isinstance(action, argparse._AppendAction)
            # One run: the command line, the values a refusal names (None
            # where none is expected), what a recorder receives (None where
            # the run is a flag given once).
            runs: list[tuple[list[str], tuple[str, ...] | None, Any]]
            if not action.option_strings and action.nargs in ("*", "+"):
                runs = [(head + ["--", "x", "x"], None, ["x", "x"])]
            elif not action.option_strings:
                runs = [(head + ["d"], None, "d")]
            elif repeats:
                runs = [(head + [flag, "one", flag, "two"], None,
                         ("one", "two"))]
            elif action.nargs == 0:
                runs = [(head + [flag], None, None),
                        (head + [flag, flag], ("", ""), None)]
            else:
                runs = [(head + [flag, "one"], None, None),
                        (head + [flag, "one", flag, "two"], ("one", "two"),
                         None),
                        (head + [flag[:-1], "one", f"{flag}=one",
                                 flag, _AWKWARD], ("one", "one", _AWKWARD),
                         None)]
            for argv, given, handed in runs:
                del reached[:]
                code, printed = _handed_on(recorded_main, argv)
                lines = printed.splitlines()
                refused = [line for line in lines
                           if line.startswith("REFUSED:")]
                nexts = [line for line in lines
                         if line.strip().startswith("next: ")]
                if given is None:
                    # A positional's run gives no flag at all, so ANY
                    # refusal that counts times is wrong of it.
                    ok = (not any(" times" in line
                                  and (f"`{named}`" in line
                                       or not action.option_strings)
                                  for line in refused)
                          and (handed is None
                               or any(handed in args
                                      for _name, args in reached)))
                else:
                    values = (f" ({', '.join(map(repr, given))})"
                              if action.nargs != 0 else "")
                    ok = (code == 2 and len(refused) == 1
                          and f"`{named}`" in refused[0]
                          and f" {len(given)} times{values}" in refused[0]
                          and len(nexts) == 1 and f"`{named}`" in nexts[0]
                          and "process group" not in printed
                          and not reached)
                if not ok:
                    wrong.append(
                        f"{' '.join(argv).replace(box, '<box>')!r} -> exit "
                        f"{code}, "
                        + _one_line(printed.replace(box, "<box>"), 110,
                                    empty=_NO_VERDICT)
                        + f", reached {[name for name, _ in reached] or 'nothing'}")
            (positionals if not action.option_strings
             else repeating if repeats else refused_flags).append(f"`{named}`")
    check(label,
          not wrong and bool(refused_flags) and bool(repeating)
          and bool(positionals) and taken == sorted(_RUNNERS),
          f"{ACTUAL}{len(refused_flags)} flag(s) not declared `append` — "
          f"{', '.join(refused_flags) or 'none'} — {len(repeating)} declared "
          f"`append` — {', '.join(repeating) or 'none'} — and "
          f"{len(positionals)} positional(s) — "
          f"{', '.join(positionals) or 'none'}; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}; the runners `main` takes "
          f"by keyword {taken}, handed a recorder {sorted(_RUNNERS)}",
          next="`cli._Parser` keeps what every flag not declared `append` "
               "was given, and `cli.main` refuses a flag given more than "
               "once first of all, before `anchored`.")


def _help_lines_of(parser: argparse.ArgumentParser) -> list[str]:
    """The help line of every flag of `parser` that answers with the help,
    in the order the parser declares them: one line for a parser with one
    `-h, --help`, none for a parser with no such flag."""
    return [action.help or "" for action in parser._actions
            if isinstance(action, argparse._HelpAction)]


def _answered(main: Callable[[list[str]], int], argv: list[str],
              parser: argparse.ArgumentParser
              ) -> tuple[int | str | None, str, str, str]:
    """`(exit, standard output, standard error, the help of parser)` for one
    command line argparse may answer itself: it exits inside `parse_args`,
    so its exit is the code. The help is formatted under the same standard
    output the run printed to, because argparse decides there whether it
    colors what it prints."""
    out, err = io.StringIO(), io.StringIO()
    code: int | str | None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as left:
            code = left.code
        helped = parser.format_help()
    return code, out.getvalue(), err.getvalue(), helped


def _help_line_control(check: CheckRow, skip: SkipRow) -> None:
    """(bbbbbbb) `--help` runs nothing else on the command line, and the
    help of every parser carries the one help line that says so.

    `--selftest --selfcheck --help` prints the help and exits 0: argparse
    answers `--help` inside `parse_args`, the first time it reads the flag,
    and neither command runs. Under argparse's own help line a reader could
    take it that both ran. The help is what that reader has in front of
    them, so the help line is where it is said.

    No parser is named here and the sentence is not typed here. The walk is
    over the parser `cli.build_parser` returns, so a subcommand added to it
    is held by this row from the commit that adds it. The sentence is read
    off the program's own `-h, --help`, looked for in the help every parser
    prints, and held to be the help line of a plain
    `argparse.ArgumentParser` and more — which is what turns the row red
    over a parser left with argparse's own words. Every parser is held to
    declare ONE flag that answers with the help, under that line: a parser
    with a second such flag prints a second help line, which no search for
    the first one notices. The words after argparse's are not this row's to
    hold: it holds that what they say of the command line is so.

    A subcommand that requires a flag is also given every flag it requires,
    read from its parser, each with a value, ahead of `--help`. The parser
    answers `--help` before it checks for a required flag, so the help prints
    without them; they are given so that a `--help` that stopped answering
    would leave a command line that can start, and the recorders would see
    it start, where argparse would otherwise turn the line down itself for
    the missing flag and nothing would show that the help had stopped
    answering. What is printed
    is held to be the parser's own `format_help()`, to open with `usage: `
    and the parser's `prog`, and to name every flag the parser declares: a
    help emptied down to its help line is still what `format_help()`
    returns.

    Every run goes through a copy of `cli` whose entry points are recorders,
    for the reason `hhhhhh` gives: on code whose `--help` does not exit, the
    real `main` would run what stands beside it — `--selftest --selfcheck
    --help` a whole self-test — from inside this arm.

    Every run is made with `FORCE_COLOR=1` set and `NO_COLOR` and
    `PYTHON_COLORS` unset, the environment in which argparse 3.14 colors
    its help even into a file: the help is text a reader saves and
    compares, so not one escape byte is in it. Before 3.14 argparse has no
    color and that clause cannot go red.
    """
    label = ("bbbbbbb  `--help` and `-h`, on the program and on every "
             "subcommand the parser exposes, and behind every flag a "
             "subcommand requires, print that parser's own help, opening "
             "with its usage and naming every flag it declares, and nothing "
             "else — no process-group line and not one escape byte, with "
             "`FORCE_COLOR=1` set — on standard output, and "
             "nothing on standard error, at exit 0, with "
             "nothing started — beside `--selftest --selfcheck`, beside a "
             "flag given twice and beside a flag no parser knows as well — "
             "and the help line of the program's `-h, --help` is in every "
             "one of them, argparse's own words and more, the line of the "
             "ONE flag each parser declares that answers with the help — "
             "which parsers there are is read from the parser, never from "
             "a list")
    copy = _fresh_module("cli")
    if copy is None:
        skip(label, "this install carries no importable `cli` source to build "
                    "the copy every command line here runs through, so no "
                    "`--help` can be given beside a command without a way "
                    "for that command to start. Nothing is claimed.")
        return
    reached: list[str] = []

    def recorder(name: str) -> Any:
        def entry(*args: Any, **kwargs: Any) -> int:
            reached.append(name)
            return 0
        return entry

    recorded_main = _recorded(copy, recorder)
    parsers: dict[str, argparse.ArgumentParser] = {"": copy.build_parser()}
    for action in parsers[""]._actions:
        if isinstance(action, argparse._SubParsersAction):
            parsers.update(action.choices)
    own = "".join(_help_lines_of(argparse.ArgumentParser())[:1])
    sentence = "".join(_help_lines_of(parsers[""])[:1])
    others = [f"{f'`{command}`' if command else 'the program'} "
              f"{_help_lines_of(parser)}"
              for command, parser in parsers.items()
              if _help_lines_of(parser) != [sentence]]
    more = bool(own) and own in sentence and sentence != own
    # Each command line, and the command whose help it prints.
    runs = [([command, spelling] if command else [spelling], command)
            for command in parsers for spelling in ("--help", "-h")]
    runs += [(["--selftest", "--selfcheck", "--help"], ""),
             (["--selfcheck", "--selfcheck", "--help"], ""),
             (["--no-such-flag", "--help"], "")]
    for command, parser in parsers.items():
        needed = [part for action in parser._actions
                  if action.required and action.option_strings
                  for part in (action.option_strings[0], "x")]
        if command and needed:
            runs += [([command, *needed, spelling], command)
                     for spelling in ("--help", "-h")]
    wrong: list[str] = []
    for argv, command in runs:
        del reached[:]
        parser = parsers[command]
        with _env_as({"FORCE_COLOR": "1", "NO_COLOR": None,
                      "PYTHON_COLORS": None}):
            code, out, err, helped = _answered(recorded_main, argv, parser)
        flat = " ".join(out.split())
        if (code != 0 or out != helped or err or reached or "\x1b" in out
                or sentence not in flat
                or not flat.startswith(f"usage: {parser.prog} ")
                or any(option not in flat for action in parser._actions
                       for option in action.option_strings)):
            wrong.append(
                f"{' '.join(argv)!r} -> exit {code}, standard output "
                + _one_line(out.replace("\x1b", "\\x1b"), 70,
                            empty="(nothing printed)")
                + ", standard error "
                + _one_line(err, 70, empty="(nothing printed)")
                + f", started {reached or 'nothing'}"
                + (", an escape byte in standard output" if "\x1b" in out
                   else ""))
    check(label, not wrong and not others and more and len(parsers) > 1,
          f"{ACTUAL}{len(parsers)} parser(s) — the program and "
          f"{', '.join(f'`{command}`' for command in parsers if command) or 'no subcommand'}"
          f" — over {len(runs)} command line(s); the help line of the "
          f"program's `-h, --help` is {sentence!r} and argparse's own is "
          f"{own!r}; parsers that do not declare that one help line and "
          f"no other: {'; '.join(others) or 'none'}; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}",
          next="`cli._Parser.__init__` tells argparse `add_help=False` and "
               "adds `-h, --help` itself, once, with `cli.HELP_LINE`, to "
               "every parser, and `color=False` where argparse takes it, "
               "and argparse answers `--help` inside "
               "`parse_args` by printing the help and exiting 0.")


#: The flag that names the permitted-movement table, as the parser spells it.
_TABLE_FLAG = "--allow-diff"

#: A table saved as Latin-1: its `é` is the one byte 0xe9.
_TABLE_NOT_TEXT = "_subject/help.out :: café\n".encode("latin-1")

#: A table that is read.
_TABLE_READ = "_subject/help.out :: a movement the table permits\n"


def _listed(root: str) -> list[str]:
    """Every directory and file under `root`, sorted, each as its path from
    `root`."""
    return sorted(os.path.relpath(os.path.join(parent, name), root)
                  for parent, folders, files in os.walk(root)
                  for name in folders + files)


def _required_head(command: str, parser: argparse.ArgumentParser,
                   manifest: str, other: str) -> list[str]:
    """`command` and every flag its parser requires, each with a value:
    `manifest` for the flag that names the manifest, `other` for the rest."""
    line = [command]
    for action in parser._actions:
        if action.required and action.option_strings:
            line += [action.option_strings[-1],
                     manifest if action.dest == "manifest" else other]
    return line


def _allow_early_control(check: CheckRow, skip: SkipRow) -> None:
    """(ccccccc) a permitted-movement table the reader refuses is refused on
    the command line before anything is started.

    Read under the census's controls, a table that is not there costs three
    runs of the subject ahead of its refusal. `cli.main` reads it under the
    manifest's load and above the controls, and again where it dispatches
    the command, and hands what `compare.read_allow` returned the second
    time to the command.

    No command is named here: the walk is over the parser `cli.build_parser`
    returns, so a command that gains the flag is held from the commit that
    adds it. Nor are the refusals' words held here — `ppp` and `wwwwww` hold
    them: what is printed is compared with what the reader raises for the
    same path, which is spelled with a `.` component so that a path resolved
    before it was read is a different string.

    Every run goes through a copy of `cli` whose entry points are recorders,
    as `bbbbbbb`'s do: "nothing started" is that no recorder was reached,
    the census's controls among them. The reader is wrapped, not replaced,
    so the row counts the reads. Each run is made under a private temp root,
    and the box that holds the manifest is listed before and after.

    The control is a table that is read, and no table: a rule that refused
    every table, or read none, would pass every other assertion of this row.
    """
    label = (f"ccccccc  a `{_TABLE_FLAG}` table `compare.read_allow` "
             "refuses — a path that names no file, a directory, a file "
             "that is not UTF-8 text — given to every command whose parser "
             "declares the flag, alone and beside every other flag of that "
             "command that takes a value, prints the process-group line, "
             "then the refusal the reader raises for that path as it was "
             "typed, whole, with its `next:` line, and nothing else, at "
             "exit 2, with nothing started — no control of the census "
             "either — the table read ONCE, nothing made under the temp "
             "root and nothing written beside the manifest; beside a "
             "`--manifest` that names no file the refusal is the "
             "manifest's, and the table is not read; the control is a "
             "table that is read, and a command line with no table: the "
             "command is reached, behind the census's controls where they "
             "run, a table given, read twice, and is handed the rows the "
             "reader returned, never the path — which commands take the "
             "flag is read from the parser, never from a list")
    copy = _fresh_module("cli")
    if copy is None:
        skip(label, "this install carries no importable `cli` source to build "
                    "the copy every command line here runs through, so no "
                    "table can be given to a command without a way for that "
                    "command to start. Nothing is claimed.")
        return
    reached: list[tuple[str, tuple[Any, ...]]] = []

    def recorder(name: str) -> Any:
        def entry(*args: Any, **kwargs: Any) -> int:
            reached.append((name, args + tuple(kwargs.values())))
            return 0
        return entry

    recorded_main = _recorded(copy, recorder)
    reads: list[Any] = []
    reader = getattr(copy, "read_allow", None)

    def counted(path: Any) -> Any:
        if path is not None:
            reads.append(path)
        return reader(path) if reader is not None else []

    if reader is not None:
        copy.read_allow = counted
    base_tmp = temp_base()
    takers: list[str] = []
    lines_run = 0
    wrong: list[str] = []
    with _box("golden-census-allow-early-") as box:
        manifest = _scratch(box)
        golden = os.path.join(box, "golden")
        _plant_marker(golden)
        folder = os.path.join(box, ".", "a-directory")
        os.makedirs(folder)
        not_text = os.path.join(box, ".", "allow-latin-1.txt")
        pathlib.Path(not_text).write_bytes(_TABLE_NOT_TEXT)
        good = os.path.join(box, ".", "allow.txt")
        pathlib.Path(good).write_text(_TABLE_READ, encoding="utf-8")
        no_manifest = os.path.join(box, "no-such-manifest.toml")
        refused_tables = (os.path.join(box, ".", "no-such-allow.txt"),
                          folder, not_text)
        def guarded(body: Callable[[], str]) -> str:
            """`body`'s answer, or what it raised: a reader that raises
            where it should refuse is this row's red, and not an exception
            out of the arm."""
            try:
                return body()
            except Exception as raised:
                return f"RAISED {type(raised).__name__}: {raised}"

        # The control's table, asked of the reader itself: one it refuses
        # is this row's red, and not an exception out of the arm.
        rows: list[tuple[str, str]] = []
        unread = guarded(lambda: _refused_by(
            lambda: rows.extend(read_allow(good)), unrefused=""))

        def ran(argv: list[str]) -> tuple[Any, str, list[str], list[Any],
                                          list[str], list[str]]:
            """`(exit, printed, the recorders reached, the tables read,
            what was left under the temp root, what moved in the box)`."""
            del reached[:]
            del reads[:]
            before = _listed(box)
            try:
                (code, printed), left = _made_under(
                    base_tmp, lambda: _handed_on(recorded_main, argv))
            except Exception as raised:
                code, printed, left = (
                    f"RAISED {type(raised).__name__}: {raised}", "", [])
            after = _listed(box)
            moved = sorted(set(before) ^ set(after))
            return (code, printed, [name for name, _ in reached],
                    list(reads), left, moved)

        def said(argv: list[str], run: tuple[Any, ...],
                 wanted: str | None = None) -> str:
            """One command line that is not as the row says: what it
            printed, cut, and — where a refusal was `wanted` — whether what
            follows the process-group line is that refusal, whole."""
            code, printed, names, read, left, moved = run
            first, _, rest = printed.partition("\n")
            grouped = first.startswith("process group ")
            after = (rest if grouped else printed).replace(box, "<box>")
            whole = ""
            if wanted is not None and after != wanted.replace(
                    box, "<box>") + "\n":
                whole = (", which is NOT the refusal wanted, whole"
                         + (": it ends "
                            + repr(_one_line(after, len(after))[-60:])
                            if after else ""))
            elif wanted is not None:
                whole = ", which is the refusal wanted, whole"
            return (f"{' '.join(argv).replace(box, '<box>')!r} -> exit "
                    f"{code}, printed "
                    + ("the process-group line and then "
                       if grouped else "NO process-group line: ")
                    + _one_line(after, 110, empty="nothing") + whole
                    + f", started {names or 'nothing'}, read "
                    f"{[str(path).replace(box, '<box>') for path in read]}"
                    f", left {left or 'nothing'} under "
                    f"the temp root and moved {moved or 'nothing'} beside "
                    "the manifest")

        for command, parser, action in _arguments_of(copy.build_parser()):
            if _TABLE_FLAG not in action.option_strings:
                continue
            takers.append(f"`{command} {_TABLE_FLAG}`")
            head = _required_head(command, parser, manifest, golden)
            beside: list[list[str]] = [[]]
            beside += [[other.option_strings[-1], golden]
                       for other in parser._actions
                       if other.option_strings and not other.required
                       and other.nargs != 0 and other is not action
                       and not isinstance(other, argparse._HelpAction)]
            for extra in beside:
                for table in refused_tables:
                    argv = head + extra + [_TABLE_FLAG, table]
                    run = ran(argv)
                    lines_run += 1
                    code, printed, names, read, left, moved = run
                    first, _, rest = printed.partition("\n")
                    wanted = guarded(functools.partial(
                        _printed_refusal, functools.partial(read_allow, table)))
                    if (code != 2 or not first.startswith("process group ")
                            or rest != wanted + "\n" or names
                            or read != [table] or left or moved):
                        wrong.append(said(argv, run, wanted))
                # The control: a table that is read, and no table at all.
                for given, handed in (([_TABLE_FLAG, good], rows),
                                      ([], [])):
                    argv = head + extra + given
                    run = ran(argv)
                    lines_run += 1
                    code, printed, names, read, _left, _moved = run
                    last = reached[-1][1] if reached else ()
                    if (code != 0 or "REFUSED" in printed or not names
                            or "census_check" in names[1:]
                            or names[-1] == "census_check"
                            or handed not in last
                            or any(good in args for _, args in reached)
                            or read != given[1:] * 2):
                        path_handed = any(good in args for _, args in reached)
                        wrong.append(said(argv, run)
                                     + (", the table's path among what it "
                                        "was handed" if path_handed else "")
                                     + ", and handed its command "
                                     + _one_line(repr(last[3:4])
                                                 .replace(box, "<box>"), 110))
            # Beside a manifest that is not there, the manifest's refusal.
            argv = (_required_head(command, parser, no_manifest, golden)
                    + [_TABLE_FLAG, refused_tables[0]])
            run = ran(argv)
            lines_run += 1
            code, printed, names, read, left, moved = run
            wanted = _printed_refusal(
                functools.partial(load_manifest, no_manifest))
            if (code != 2 or printed.partition("\n")[2] != wanted + "\n"
                    or names or read or left or moved):
                wrong.append(said(argv, run, wanted))
    check(label,
          not wrong and bool(takers) and reader is not None and bool(rows),
          f"{ACTUAL}{len(takers)} command(s) take the flag — "
          f"{', '.join(takers) or 'none'} — over {lines_run} command "
          f"line(s); `cli` holds {'a' if reader is not None else 'NO'} "
          "`read_allow` to call; the reader "
          + (f"REFUSED the control's table: {_one_line(unread, 110)}"
             if unread else f"read the control's table as {rows}")
          + "; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}",
          next="`cli.main` calls `compare.read_allow` with the path as "
               "typed under the manifest's load and above `census_check`, "
               "and again where it dispatches the command, and hands what "
               "that second call returns to the command.")

#: The flags whose path `cli.main` reads through an owner above the census's
#: controls, beside `--allow-diff` (row `ccccccc`'s), each with the name
#: `cli` holds that owner under. Which commands declare each flag is read
#: from the parser; that a flag takes a PATH is not something argparse
#: records, so it is stated here.
_EARLY_OWNERS = {"--golden": "read_sides", "--against": "read_sides",
                 "--out": "guard_capture", "--mutants": "load_mutants"}

#: What each command's dispatch reaches below the controls, in order, by the
#: names `cli` holds them under: `mutants` is handed the read its file had
#: above; `capture` is handed what `guard_capture` returned above; `compare`
#: reads both sides again inside the command.
_EARLY_ENTRY = {"capture": ("capture",), "compare": ("compare",),
                "mutants": ("run_mutants",)}

#: What a command's dispatch reaches between its path's read and the
#: census's controls: `mutants` asks which mutants the file plants, and
#: refuses a name or a mutant it cannot, before the controls start the subject.
_EARLY_BETWEEN = {"mutants": ("chosen_and_checked",)}

def _early_paths_control(check: CheckRow, skip: SkipRow) -> None:
    """(ggggggg) every path a command is handed is refused, when its owner
    refuses it, before anything is started.

    Read under the census's controls, a `--golden` that is not there costs
    every run of the subject those controls make ahead of its refusal, and
    so does an `--out` that holds a stranger's file, an `--out` under a file,
    and a `--mutants` that names nothing. `cli.main` reads each under the
    manifest's load and above the controls, through the owner named in
    `_EARLY_OWNERS`: `--out`'s guard is handed to `capture`, and with it
    whether the capture replaces one, decided once from what stood at
    `--out` when the command started; `--golden` and `--against` are read
    again where the command reads them, and `--mutants` is read once.

    The refusals' words are not held here: what is printed is compared with
    what the owner of each refusal — `capture.read_capture`,
    `capture.guard_capture` as `cli` holds it, `mutants.load_mutants`,
    `manifest.load_manifest`, `compare.read_allow` — raises for the same
    path, given as `cli.main` gives it.

    Every command line of the first half goes through a copy of `cli` whose
    entry points are recorders, as `ccccccc`'s do: "nothing started" is that
    no recorder was reached, the census's controls among them. The owners
    are wrapped, not replaced, so the row sees each read and its order
    against the recorders. Each run is made under a private temp root, and
    the box that holds the manifest is listed before and after.

    Two refused paths on one command line: the refusal is that of the path
    whose flag the parser declares first, `--manifest` before them all and
    `--allow-diff` after `--against`. The control is every path good: the
    owner is read before anything is reached, the command is reached behind
    the census's controls where they run, and `capture` and `mutants` are
    handed what the read they dispatch on returned.
    """
    label = ("ggggggg  a path its owner refuses — `--golden` and `--against` "
             "a path that names nothing, a file, a directory holding no "
             "capture; `--out` a file, a path under a file, a directory "
             "holding a file golden-census did not write, a capture without "
             "`--force`; `--mutants` a path that names nothing, a directory, "
             "a file that is not TOML — given to every command whose parser "
             "declares the flag, every other path good, prints the "
             "process-group line, then the refusal that path's owner raises, "
             "whole, with its `next:` line, and nothing else, at exit 2, with "
             "nothing started — no control of the census either — nothing "
             "made under the temp root and nothing written beside the "
             "manifest; two refused paths on one command line print the "
             "refusal of the flag the parser declares first, `--manifest` "
             "first of all; the control is every path good: the owner is "
             "read before anything is reached, the command is reached behind "
             "the census's controls where they run, `capture` is handed what "
             "`guard_capture` returned and `mutants` what the dispatch's own "
             "read of its file returned — which commands take each flag is "
             "read from the parser")
    copy = _fresh_module("cli")
    if copy is None:
        skip(label, "this install carries no importable `cli` source to build "
                    "the copy every command line here runs through, so no "
                    "path can be given to a command without a way for that "
                    "command to start. Nothing is claimed.")
        return
    owners = {name: getattr(copy, name, None)
              for name in sorted(set(_EARLY_OWNERS.values()) | {"read_allow"})}
    #: Every recorder reached and every owner read, in the order they were.
    trace: list[str] = []
    reached: list[tuple[str, tuple[Any, ...]]] = []
    reads: list[str] = []
    returned: list[Any] = []

    def recorder(name: str) -> Any:
        def entry(*args: Any, **kwargs: Any) -> int:
            trace.append(name)
            reached.append((name, args + tuple(kwargs.values())))
            return 0
        return entry

    def counted(name: str, real: Any) -> Any:
        def read(*args: Any, **kwargs: Any) -> Any:
            # `read_allow` is asked of every command, and reads no file for
            # `None`: that call is no read of a path.
            if args[:1] == (None,):
                return real(*args, **kwargs)
            trace.append(name)
            reads.append(name)
            result = real(*args, **kwargs)
            returned.append(result)
            return result
        return read

    recorded_main = _recorded(copy, recorder)
    for name, real in owners.items():
        if real is not None:
            setattr(copy, name, counted(name, real))
    base_tmp = temp_base()
    wrong: list[str] = []
    takers: list[str] = []
    lines_run = 0
    with _box("golden-census-paths-early-") as box:
        manifest = _scratch(box, extra={"mutants.toml": _STUB_MUTANTS})
        golden = os.path.join(box, "golden")
        _plant_marker(golden)
        a_file = os.path.join(box, "a-file.txt")
        pathlib.Path(a_file).write_text("a file, not a directory\n",
                                        encoding="utf-8")
        empty = os.path.join(box, "an-empty-directory")
        os.makedirs(empty)
        stranger = os.path.join(box, "a-stranger")
        os.makedirs(stranger)
        pathlib.Path(os.path.join(stranger, "notes.txt")).write_text(
            "a file golden-census did not write\n", encoding="utf-8")
        nothing = os.path.join(box, "no-such-path")
        good = {"--manifest": manifest, "--golden": golden,
                "--against": golden, "--out": os.path.join(box, "new-out"),
                "--mutants": os.path.join(box, "mutants.toml")}
        refused = {"--golden": (nothing, a_file, empty),
                   "--against": (nothing, a_file, empty),
                   "--out": (a_file, os.path.join(a_file, "sub"), stranger,
                             golden),
                   "--mutants": (nothing, empty, a_file),
                   "--manifest": (nothing,),
                   "--allow-diff": (nothing,)}
        loaded = load_manifest(manifest)
        wanted_of = {
            "--golden": lambda path: read_capture(os.path.abspath(path),
                                                  "--golden"),
            "--against": lambda path: read_capture(os.path.abspath(path),
                                                   "--against"),
            # The owner `cli` holds, so a `cli` without one has no sentence
            # to want and every `--out` line is not as the row says.
            "--out": lambda path: (owners["guard_capture"](
                loaded, os.path.abspath(path), (), False)
                if owners["guard_capture"] is not None else None),
            "--mutants": load_mutants,
            "--manifest": load_manifest,
            "--allow-diff": read_allow}

        def line(command: str, parser: argparse.ArgumentParser,
                 given: dict[str, str]) -> list[str]:
            """`command`, every flag its parser requires, then `given`'s
            optional flags: each value from `given`, or good."""
            argv = [command]
            for action in parser._actions:
                if action.required and action.option_strings:
                    flag = action.option_strings[-1]
                    argv += [flag, given.get(flag, good.get(flag, "?"))]
            for flag, value in given.items():
                if flag not in argv:
                    argv += [flag, value]
            return argv

        def ran(argv: list[str]) -> tuple[Any, str, list[str], list[str],
                                          list[str], list[str]]:
            """`(exit, printed, the recorders reached, the owners read,
            what was left under the temp root, what moved in the box)`."""
            del trace[:]
            del reached[:]
            del reads[:]
            del returned[:]
            before = _listed(box)
            (code, printed), left = _made_under(
                base_tmp, lambda: _handed_on(recorded_main, argv))
            moved = sorted(set(before) ^ set(_listed(box)))
            return (code, printed, [name for name, _ in reached],
                    list(reads), left, moved)

        def refused_whole(argv: list[str], wanted: str, flag: str) -> None:
            """One command line that must print `wanted`, read by the owner
            of `flag` alone — `--manifest`'s is not counted — and start
            nothing."""
            code, printed, names, read, left, moved = ran(argv)
            first, _, rest = printed.partition("\n")
            owner = dict(_EARLY_OWNERS, **{"--allow-diff": "read_allow"}).get(flag)
            if (code != 2 or not first.startswith("process group ")
                    or rest != wanted + "\n" or names
                    or read != ([owner] if owner else []) or left or moved):
                wrong.append(
                    f"{' '.join(argv).replace(box, '<box>')!r} -> exit {code}, "
                    + _one_line(rest.replace(box, "<box>"), 110,
                                empty="nothing")
                    + (", which is the refusal wanted, whole"
                       if rest == wanted + "\n" else
                       ", which is NOT the refusal wanted, whole")
                    + f", started {names or 'nothing'}, read {read}, left "
                    f"{left or 'nothing'} under the temp root and moved "
                    f"{moved or 'nothing'} beside the manifest")

        parsers = {command: parser for command, parser, _action
                   in _arguments_of(copy.build_parser())}
        declared: dict[str, list[str]] = {}
        for command, parser, action in _arguments_of(copy.build_parser()):
            flag = action.option_strings[-1] if action.option_strings else ""
            if flag in refused and command:
                declared.setdefault(command, []).append(flag)
            if flag not in _EARLY_OWNERS:
                continue
            takers.append(f"`{command} {flag}`")
            for path in refused[flag]:
                lines_run += 1
                refused_whole(line(command, parser, {flag: path}),
                              _printed_refusal(
                                  functools.partial(wanted_of[flag], path)),
                              flag)
        # Two refused paths: each pair of flags next to each other in the
        # order the command's parser declares them.
        for command, flags in declared.items():
            if not any(flag in _EARLY_OWNERS for flag in flags):
                continue
            for earlier, later in zip(flags[:-1], flags[1:], strict=True):
                lines_run += 1
                refused_whole(
                    line(command, parsers[command],
                         {earlier: refused[earlier][0],
                          later: refused[later][0]}),
                    _printed_refusal(functools.partial(
                        wanted_of[earlier], refused[earlier][0])), earlier)
            # The control: every path good, and `--against` given and not.
            optional = [flag for flag in flags if flag in _EARLY_OWNERS
                        and not any(action.required and flag
                                    in action.option_strings
                                    for action in parsers[command]._actions)]
            forms: list[dict[str, str]] = [{}]
            forms += [{flag: good[flag]} for flag in optional]
            owner = next(_EARLY_OWNERS[flag] for flag in flags
                         if flag in _EARLY_OWNERS)
            for given in forms:
                argv = line(command, parsers[command], given)
                lines_run += 1
                code, printed, _names, _read, _left, _moved = ran(argv)
                last = reached[-1][1] if reached else ()
                runs = copy.controls_before(
                    copy.build_parser().parse_args(argv))[0]
                order = ([owner] + list(_EARLY_BETWEEN.get(command, ()))
                         + (["census_check"] if runs else [])
                         + list(_EARLY_ENTRY.get(command, (command,))))
                # `read_sides` returns nothing to hand on: `compare` reads
                # both sides again inside the command.
                handed = (returned[-1] is None
                          or any(item is returned[-1] for item in last)
                          if returned else False)
                if (code != 0 or "REFUSED" in printed or trace != order
                        or not handed):
                    wrong.append(
                        f"{' '.join(argv).replace(box, '<box>')!r} -> exit "
                        f"{code}, "
                        + _one_line(printed.replace(box, "<box>"), 110,
                                    needles=("REFUSED: ",), empty="nothing")
                        + f", reached and read {trace} where {order} was "
                        "wanted, and "
                        + ("handed its command what the owner returned"
                           if handed else
                           "NOT handed its command what the owner returned"))
    check(label, not wrong and len(takers) >= len(_EARLY_OWNERS),
          f"{ACTUAL}{len(takers)} flag(s) of a command take a path read "
          f"early — {', '.join(takers) or 'none'} — over {lines_run} command "
          f"line(s); `cli` holds "
          + ", ".join(f"{'`' + name + '`' if real is not None else 'NO `' + name + '`'}"
                      for name, real in owners.items())
          + f"; not as the row says: {'; '.join(wrong) or 'none of them'}",
          next="`cli.main` calls each owner in `_EARLY_OWNERS` under the "
               "manifest's load and above `census_check`, in the order the "
               "parser declares the flags; `capture` is handed what "
               "`guard_capture` returned, `mutants` is handed the read of its "
               "file, and `compare` reads its paths again where it uses "
               "them.")


def _launcher_run(launcher: str, cwd: str, env: dict[str, str]) -> str:
    """`exit N: <stdout, one line>` for one `sh <launcher> --version`."""
    ran = launch(["sh", launcher, "--version"], "the launcher arm's run",
                 env=env, cwd=cwd, stdin=subprocess.DEVNULL)
    return (f"exit {ran.returncode}: "
            + _one_line(ran.stdout + ran.stderr, 110, empty="(nothing printed)"))


def _launcher_control(check: CheckRow, skip: SkipRow) -> None:
    """(iiiiii) `bin/golden-census` runs its own package, whatever the
    working directory holds and whatever `CDPATH` says.

    Under `-m` the working directory goes on `sys.path` ahead of
    `PYTHONPATH`, so a `golden_census` there ran instead of the launcher's;
    and `CDPATH` sent the launcher's own `cd bin` to another directory. The
    arm sets `PATH` itself — the running interpreter's directory, then
    `/usr/bin:/bin` for `dirname` and `readlink` — so the run does not
    depend on the caller's shell, and it runs the same two cases through a
    copy of the launcher with `-P` and `unset CDPATH` stripped, beside a
    link to the real package, as the proof that each case can go red.
    """
    label = ("iiiiii  `bin/golden-census --version`, run with `sh` under a "
             "PATH the arm sets, prints this package's version from a "
             "directory holding an impostor `golden_census` package, and from "
             "the checkout with CDPATH naming a directory that holds a "
             "`bin/`; the same launcher with `-P` and `unset CDPATH` "
             "stripped prints the impostor's line and refuses under CDPATH — "
             "the control that both cases can go red")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    layout = Layout.detect()
    launcher = os.path.join(layout.root, "bin", PROG)
    if layout.shipped or not os.path.isfile(launcher):
        skip(label, "this is an installed copy, which carries no `bin/` beside "
                    "the package: the launcher is a checkout's, and an install "
                    "runs its console script instead. Nothing was run and "
                    "nothing is claimed.")
        return
    with open(launcher, encoding="utf-8") as handle:
        source = handle.read()
    env = {name: value for name, value in os.environ.items()
           if name not in ("PYTHONPATH", "GOLDEN_CENSUS_PYTHON", "CDPATH")}
    env["PATH"] = f"{os.path.dirname(sys.executable)}:/usr/bin:/bin"
    want = f"exit 0: {PROG} {__version__}"
    said: dict[str, str] = {}
    with _box("golden-census-launcher-") as box:
        impostor = os.path.join(box, "impostor", IMPORT_NAME)
        os.makedirs(impostor)
        for name, text in (("__init__.py", ""),
                           ("__main__.py", "print('IMPOSTOR')\n")):
            pathlib.Path(os.path.join(impostor, name)).write_text(text, encoding="utf-8")
        elsewhere = os.path.join(box, "cdpath")
        os.makedirs(os.path.join(elsewhere, "bin"))
        stripped = os.path.join(box, "stripped")
        os.makedirs(os.path.join(stripped, "bin"))
        os.symlink(layout.package, os.path.join(stripped, IMPORT_NAME))
        pathlib.Path(os.path.join(stripped, "bin", PROG)).write_text(
            source.replace("unset CDPATH\n", "").replace(" -P -m ", " -m "), encoding="utf-8")
        relative = os.path.join("bin", PROG)
        under_cdpath = dict(env, CDPATH=elsewhere)
        for key, home in (("", layout.root), ("stripped ", stripped)):
            said[f"{key}from the impostor's directory"] = _launcher_run(
                os.path.join(home, relative), os.path.dirname(impostor), env)
            said[f"{key}under CDPATH"] = _launcher_run(relative, home,
                                                       under_cdpath)
    real = [said["from the impostor's directory"], said["under CDPATH"]]
    red = (said["stripped from the impostor's directory"].startswith("exit 0: IMPOSTOR")
           and not said["stripped under CDPATH"].startswith("exit 0"))
    check(label, all(one == want for one in real) and red,
          ACTUAL + "; ".join(f"{why} -> {text.replace(box, '<box>')}"
                                 for why, text in said.items()),
          next="`bin/golden-census` has to `unset CDPATH` before its `cd` "
               "and `exec` the interpreter with `-P`; without `-P` the "
               "working directory's `golden_census` is imported first.")


#: The launcher's three refusals, held word for word. A change to the
#: launcher's words goes red in arm `yyyyyyyy` ON PURPOSE: no golden and no
#: document holds these sentences, so this is the one place a change shows,
#: and it is made here and in the launcher together.
_LAUNCHER_NO_PACKAGE = (
    "REFUSED: no golden_census package at {root}/golden_census — this "
    "launcher runs the package one directory up from itself, and there is "
    "none there.\n"
    "  next: Run bin/golden-census from a checkout of golden-census, or from "
    "an install that keeps bin/ beside the package.\n")
_LAUNCHER_BAD_OVERRIDE = (
    "REFUSED: GOLDEN_CENSUS_PYTHON={value} is not a Python 3.11+ "
    "interpreter, and golden-census needs one: it reads TOML with tomllib, "
    "which arrived in 3.11.\n"
    "  next: Point GOLDEN_CENSUS_PYTHON at a Python 3.11+ interpreter, or "
    "unset it.\n")
_LAUNCHER_NO_INTERPRETER = (
    "REFUSED: no Python 3.11+ interpreter found on PATH (tried python3.15 "
    "down to python3.11, then a bare python3), and golden-census needs one: "
    "it reads TOML with tomllib, which arrived in 3.11.\n"
    "  next: Install a Python 3.11+ interpreter (for example `brew install "
    "python3`), or point GOLDEN_CENSUS_PYTHON at one.\n")


def _launcher_refusals_control(check: CheckRow, skip: SkipRow) -> None:
    """(yyyyyyyy) `bin/golden-census` refuses in its own two lines at exit 2,
    before any Python runs, in each of its three cases.

    The cases: a copy of the launcher with no `golden_census` beside its
    `bin/`; `GOLDEN_CENSUS_PYTHON` naming a script that exits 1, so it fails
    the 3.11 probe; and a `PATH` holding only symlinks to `dirname` and
    `readlink`, so no `python3.x` is found. Each must print exactly the two
    lines held in the constants above, nothing on stderr, no `Traceback` and
    no shell `not found`. The control is the same launcher under the arm's
    own `PATH`, which prints the version.
    """
    label = ("yyyyyyyy  `bin/golden-census` refuses in its own two lines at "
             "exit 2, before any Python runs, in each of its three cases — "
             "no `golden_census` directory beside its `bin/`, "
             "`GOLDEN_CENSUS_PYTHON` naming an interpreter that fails the "
             "3.11 probe, and a `PATH` with no Python 3.11+ on it — each a "
             "`REFUSED:` line naming the cause and a `next:` line, and never "
             "a traceback or a shell error; the control is the same launcher "
             "under the arm's own `PATH`, which prints the version")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    layout = Layout.detect()
    launcher = os.path.join(layout.root, "bin", PROG)
    if layout.shipped or not os.path.isfile(launcher):
        skip(label, "this is an installed copy, which carries no `bin/` beside "
                    "the package: the launcher is a checkout's, and an install "
                    "runs its console script instead. Nothing was run and "
                    "nothing is claimed.")
        return
    with open(launcher, encoding="utf-8") as handle:
        source = handle.read()
    env = {name: value for name, value in os.environ.items()
           if name not in ("PYTHONPATH", "GOLDEN_CENSUS_PYTHON", "CDPATH")}
    env["PATH"] = f"{os.path.dirname(sys.executable)}:/usr/bin:/bin"
    shell = shutil.which("sh", path=env["PATH"]) or "sh"
    said: list[tuple[str, int, str, str]] = []
    wrong: list[str] = []

    def run(why: str, script: str, run_env: dict[str, str], want: str) -> None:
        ran = launch([shell, script, "--version"],
                     "the launcher refusals arm's run", env=run_env,
                     cwd=os.path.dirname(os.path.dirname(script)),
                     stdin=subprocess.DEVNULL)
        said.append((why, ran.returncode, ran.stdout, ran.stderr))
        if (ran.returncode != (0 if want.startswith(PROG) else 2)
                or ran.stdout != want or ran.stderr != ""
                or "Traceback" in ran.stdout + ran.stderr
                or "not found" in ran.stdout + ran.stderr):
            wrong.append(why)

    with _box("golden-census-launcher-refusals-") as box:
        alone = os.path.join(os.path.realpath(box), "alone")
        os.makedirs(os.path.join(alone, "bin"))
        lone = os.path.join(alone, "bin", PROG)
        pathlib.Path(lone).write_text(source, encoding="utf-8")
        os.chmod(lone, 0o755)
        run("no package", lone, env,
            _LAUNCHER_NO_PACKAGE.format(root=alone))
        fake = os.path.join(box, "bin", "not-python")
        os.makedirs(os.path.dirname(fake))
        pathlib.Path(fake).write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        os.chmod(fake, 0o755)
        run("bad override", launcher, dict(env, GOLDEN_CENSUS_PYTHON=fake),
            _LAUNCHER_BAD_OVERRIDE.format(value=fake))
        thin = os.path.join(box, "thin")
        os.makedirs(thin)
        for tool in ("dirname", "readlink"):
            found = shutil.which(tool, path=env["PATH"])
            if found:
                os.symlink(found, os.path.join(thin, tool))
        run("no interpreter", launcher, dict(env, PATH=thin),
            _LAUNCHER_NO_INTERPRETER)
        run("control", launcher, env, f"{PROG} {__version__}\n")
    check(label, not wrong and len(said) == 4,
          ACTUAL + "; ".join(
              f"{why} -> exit {code}, "
              + _one_line((out + err).replace(box, "<box>"), 110,
                          empty="(nothing printed)")
              for why, code, out, err in said)
          + (f"; not as the row says: {', '.join(wrong)}" if wrong else ""),
          next="`bin/golden-census` has to print its two `REFUSED:` and "
               "`next:` lines and exit 2 for each of its three refusals "
               "before it runs any Python; if its words changed on purpose, "
               "change the `_LAUNCHER_*` constants beside this arm to match.")



def _module_as_script_control(check: CheckRow) -> None:
    """(eeeeeeee) the two modules a reader runs by name with `-m` each say
    what they are, where without a `__main__` guard each ran its body,
    printed nothing and exited 0.

    `console` is the console script's target, so run as a script it runs
    `main` and answers as `python3 -m golden_census` does. `cli` cannot run
    `main` without the runners `console` hands it, so it refuses in one
    sentence naming the command that runs. The control is `python3 -m
    golden_census --version` itself, whose line `console` must print; each
    run is a child, with `PYTHONPATH` at the package's parent.
    """
    label = (f"eeeeeeee  `python3 -m {IMPORT_NAME}.console --version`, the "
             "module the console script calls run as a script, prints the "
             f"line `python3 -m {IMPORT_NAME} --version` prints, at exit 0; "
             f"`python3 -m {IMPORT_NAME}.cli --version` is ONE refusal at "
             f"exit 2 whose `next:` names `python3 -m {IMPORT_NAME}`; "
             "neither prints nothing at exit 0, which each did with no "
             "`__main__` guard")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(PACKAGE)
    said: dict[str, tuple[int, str]] = {}
    elsewhere = ""
    with _box("golden-census-as-script-") as box:
        for name in ("", ".console", ".cli"):
            ran = launch(_package_argv("-m", IMPORT_NAME + name, "--version"),
                         f"`-m {IMPORT_NAME}{name}`", cwd=box, env=env)
            heard = _heard(ran.stderr)
            elsewhere += heard.not_from(PACKAGE)
            said[IMPORT_NAME + name] = (ran.returncode,
                                        ran.stdout + heard.own)
    control = said[IMPORT_NAME]
    console = said[f"{IMPORT_NAME}.console"]
    cli = said[f"{IMPORT_NAME}.cli"]
    refused = cli[1].splitlines()
    named = (cli[0] == 2 and len(refused) == 2
             and refused[0].startswith("REFUSED: ")
             and refused[1] == (f"  next: Run `python3 -m {IMPORT_NAME}` "
                                "with the same arguments."))
    check(label,
          control == (0, f"{PROG} {__version__}\n") and console == control
          and named and not elsewhere,
          ACTUAL + "; ".join(
              f"-m {name} -> exit {code}, "
              + _one_line(text, 200, empty="(nothing printed)")
              for name, (code, text) in said.items()) + elsewhere,
          next="`console.py` ends with `if __name__ == \"__main__\": raise "
               "SystemExit(main())`, and `cli.py` with a guard that prints "
               "its one refusal through `core.refusal_text` and exits 2.")


#: What a broken `sitecustomize.py` prints at startup: a traceback block, the
#: shape of the stale `.pth` file or the broken site file an interpreter's
#: user site can hold. Arm `wwwwwwww` plants it on a child's import path.
_STARTUP_NOISE = ("Traceback (most recent call last):\n"
                  "  File \"<planted sitecustomize>\", line 1, in <module>\n"
                  "Error: planted startup noise\n")

#: A `console` that answers `--version` as the real one does and imports
#: nothing of the package: the copy a check that reads only the child's
#: output cannot tell from the real one.
_CARELESS_CONSOLE = ("def main(argv=None):\n"
                     f"    print({PROG + ' ' + __version__!r})\n"
                     "    return 0\n")


def _which_copy_control(check: CheckRow, skip: SkipRow) -> None:
    """(wwwwwwww) a child that runs the package says which copy it imported,
    and the interpreter's startup noise is read apart from the child's own
    text.

    Five runs of `-m golden_census --version`, each a child under
    `_package_argv`: this copy; a full second copy first on the import path;
    a careless second copy (`__init__.py`, `__main__.py` and a `console.py`
    that prints the version line) first on it; this copy under a
    `sitecustomize.py` that prints a traceback block and exits normally; and
    a run WITHOUT `_package_argv`, the run a user makes. The reader must name
    this copy's directory for the first and the fourth, the second copy's
    for the second, and no directory for the third; the fourth's noise must
    be the planted block and its own text empty, where the raw standard
    error holds the word `Traceback`; the fifth's standard error must be
    empty. The second and third print the same version line as the first, so
    a check that read only output would stay green under them.

    "Empty" and "the planted block" are relative to the interpreter the
    arm runs under: a bare `python3 -c pass` is run first, and whatever it
    prints on its own, a stale `.pth` file's traceback say, is the noise
    every run below is expected to carry and the planted block is expected to
    come on top of. A self-test run under a noisy interpreter therefore
    measures the same thing as one under a quiet one.
    """
    label = ("wwwwwwww  a child started with `_package_argv` prints the "
             "directory it imported the package from, and `_heard` names it: "
             "this copy's for a run of this copy; a second full copy's when "
             "that copy is first on the import path; NO directory when the "
             "second copy is a careless `console.py` that prints the same "
             "version line; and under a `sitecustomize.py` that prints a "
             "traceback block at startup it names this copy, holds the block "
             "as the interpreter's noise and the child's own text empty, "
             "where the raw standard error holds a `Traceback`; the same run "
             "without `_package_argv`, the run a user makes, prints on "
             "standard error only what the bare interpreter prints")
    if not os.path.isdir(PACKAGE):
        skip(label, f"{PACKAGE} is not a directory (the package is read from "
                    "an archive), so there is no copy of it to plant. "
                    "Nothing was run and nothing is claimed.")
        return
    version = f"{PROG} {__version__}\n"
    ran: dict[str, subprocess.CompletedProcess[str]] = {}
    with _box("golden-census-which-copy-") as box:
        second = os.path.join(box, "second")
        shutil.copytree(PACKAGE, os.path.join(second, IMPORT_NAME),
                        ignore=shutil.ignore_patterns("__pycache__",
                                                      "fixture", "_shipped"))
        careless = os.path.join(box, "careless", IMPORT_NAME)
        os.makedirs(careless)
        loud = os.path.join(box, "loud")
        os.makedirs(loud)
        for where, leaf, text in (
                (careless, "__init__.py", ""),
                (careless, "console.py", _CARELESS_CONSOLE),
                (careless, "__main__.py",
                 f"from {IMPORT_NAME}.console import main\n"
                 "raise SystemExit(main())\n"),
                (loud, "sitecustomize.py",
                 f"import sys\nsys.stderr.write({_STARTUP_NOISE!r})\n")):
            pathlib.Path(os.path.join(where, leaf)).write_text(
                text, encoding="utf-8")
        real = os.path.dirname(PACKAGE)
        ambient = launch([sys.executable, "-c", "pass"],
                         "arm wwwwwwww's bare interpreter", cwd=box,
                         env=dict(os.environ, PYTHONPATH=real),
                         stdin=subprocess.DEVNULL).stderr
        for name, first, argv in (
                ("this copy", "", _package_argv("-m", IMPORT_NAME, "--version")),
                ("a full second copy", second,
                 _package_argv("-m", IMPORT_NAME, "--version")),
                ("a careless second copy", os.path.dirname(careless),
                 _package_argv("-m", IMPORT_NAME, "--version")),
                ("a noisy interpreter", loud,
                 _package_argv("-m", IMPORT_NAME, "--version")),
                ("a user's run", "",
                 [sys.executable, "-m", IMPORT_NAME, "--version"])):
            env = dict(os.environ,
                       PYTHONPATH=os.pathsep.join([first, real] if first
                                                  else [real]))
            ran[name] = launch(argv, f"arm wwwwwwww's run of {name}", env=env,
                               cwd=box, stdin=subprocess.DEVNULL)
        second_package = os.path.join(second, IMPORT_NAME)
    heard = {name: _heard(proc.stderr) for name, proc in ran.items()}
    named = {name: (one.where, one.not_from(PACKAGE))
             for name, one in heard.items()}
    # The same version line from the first three, which is the point: output
    # alone cannot tell them apart.
    same = all(ran[name].returncode == 0 and ran[name].stdout == version
               for name in ("this copy", "a full second copy",
                            "a careless second copy"))
    here, full, careless_heard = (heard["this copy"],
                                  heard["a full second copy"],
                                  heard["a careless second copy"])
    noisy, plain = heard["a noisy interpreter"], ran["a user's run"]
    held = (same
            and here.where == PACKAGE and not here.not_from(PACKAGE)
            and here.noise == ambient and here.own == ""
            and full.where == second_package
            and second_package in full.not_from(PACKAGE)
            and careless_heard.where is None
            and "printed no package directory line"
            in careless_heard.not_from(PACKAGE)
            and noisy.where == PACKAGE and _STARTUP_NOISE in noisy.noise
            and noisy.noise.replace(_STARTUP_NOISE, "", 1) == ambient
            and noisy.own == ""
            and "Traceback" in ran["a noisy interpreter"].stderr
            and plain.returncode == 0 and plain.stdout == version
            and plain.stderr == ambient)
    check(label, held,
          f"{ACTUAL}"
          + "; ".join(f"{name} -> exit {proc.returncode}, directory "
                      f"{named[name][0]!r}, noise "
                      f"{_one_line(heard[name].noise, 60, empty='none')!r}, "
                      f"own text "
                      f"{_one_line(heard[name].own, 60, empty='none')!r}"
                      for name, proc in ran.items())
          + f"; the version line alone is the same for the first three={same}",
          next="`__init__` prints the line when the interpreter is started "
               "with `-X golden_census_say_where` and not otherwise; "
               "`proof._package_argv` starts a child with it and "
               "`proof._heard` splits what the child wrote on standard error "
               "at that line. A site that runs the package starts it with "
               "`_package_argv` and asks `_heard(...).not_from(PACKAGE)`.")


def _red_census_control_control(check: CheckRow, skip: SkipRow) -> None:
    """(lllll) a red control of the READER's own census, command by command,
    with nothing rebound.

    A pin whose `vary` control cannot move the surface it names is a census
    claiming something untrue about the reader's subject, and a golden made
    under it records the wrong thing. So `capture` and `mutants` stop;
    `compare --against` reads two recorded directories and starts no subject,
    so it runs; and `census`, whose whole job is that census, prints the red
    row and its state block under it.
    """
    label = ("lllll  a census pin whose control cannot move the surface it "
             "names, through the real command line: `capture` and `mutants` "
             "REFUSE with nothing started, `compare --against` runs to a "
             "verdict because it starts no subject, and `census` prints the "
             "failing row AND the block under it — the census it read and "
             "every row's disposition — and exits 1 without refusing; one "
             "manifest, four commands, nothing rebound")
    with _box("golden-census-red-census-") as box:
        healthy = _scratch(box)
        golden = os.path.join(box, "golden")
        made = _quietly(main, ["capture", "--manifest", healthy,
                               "--out", golden])
        if not os.path.isdir(golden):
            _capture_broke(check, label,
                           "the stub subject would not capture, so there is "
                           "no recorded directory for the `compare --against` "
                           f"row: {_one_line(made[1], 600)}")
            return
        red = _scratch(box, census_text=_STUB_CENSUS + _UNPROVEN_PIN,
                       extra={"manifest.toml": _STUB_MANIFEST.replace(
                           'census  = "census.toml"',
                           'census  = "red-census.toml"'),
                              "red-census.toml": _STUB_CENSUS + _UNPROVEN_PIN,
                              "mutants.toml": _STUB_MUTANTS})
        captured = _quietly(main, ["capture", "--manifest", red,
                                   "--out", os.path.join(box, "red-out")])
        # A mutants file that loads and whose mutant still applies, so what
        # stops `mutants` is the census's red control and not a refusal of
        # the file, which is read above it.
        mutated = _quietly(main, ["mutants", "--manifest", red, "--mutants",
                                  os.path.join(box, "mutants.toml")])
        against = _quietly(main, ["compare", "--manifest", red,
                                  "--golden", golden, "--against", golden])
        stated = _quietly(main, ["census", "--manifest", red])
    if "GOLDEN_CENSUS_UNREAD" not in captured[1]:
        skip(label, "the planted census control never ran: the block in front "
                    f"of `capture` stopped earlier ({_one_line(captured[1], 160)}"
                    "). Nothing is claimed.")
        return
    stops = (captured[0] == 2 and "capture complete" not in captured[1]
             and "UNPROVEN" in captured[1]
             and "MUTANTS" not in mutated[1]
             and "does not run `mutants`" in mutated[1])
    runs = (against[0] == 0 and "IDENTICAL" in against[1]
            and "UNPROVEN" not in against[1])
    # The census command's own block, asserted as the lines a reader of THIS
    # census sees: the file it read, and a row per disposition under it. The
    # preconditions and the state rows are the same block's other halves and
    # this stub census declares neither, so asking for them here would be an
    # assertion about the fixture rather than about the command.
    printed = [line for line in stated[1].splitlines()
               if line.startswith("census ")]
    states = (stated[0] == 1 and "UNPROVEN" in stated[1]
              and len(printed) == 1 and printed[0].endswith("red-census.toml")
              and "  pin           a variable no surface reads" in stated[1]
              and "REFUSED: " not in stated[1])
    check(label, stops and runs and states,
          f"{ACTUAL}`capture` -> exit {captured[0]}, "
          f"{_one_line(captured[1], 90, needles=('REFUSED: ',), empty='(no refusal)')}; "
          f"`mutants` -> exit {mutated[0]}, block reached="
          f"{'MUTANTS' in mutated[1]}; `compare --against` -> exit "
          f"{against[0]}, IDENTICAL={'IDENTICAL' in against[1]}, census rows="
          f"{'UNPROVEN' in against[1]}; `census` -> exit {stated[0]}, "
          f"UNPROVEN row={'UNPROVEN' in stated[1]}, the census block "
          f"{printed or '(absent)'} with a row per disposition under it, "
          f"refused={'REFUSED: ' in stated[1]}",
          next="`cli.controls_before` decides which commands the census's "
               "controls precede, and `cli.main` writes the refusal under "
               "them; `census` is the command that prints its state block "
               "whatever those controls said.")


#: The stub of arm `qqqqqqqq`: one surface, `say`, over a subject that prints
#: its first argument behind a word of its own. The manifest's command is
#: `stub.py`; `same.py` prints what it prints and `changed.py` another word.
_COMMAND_MANIFEST = _subject("stub") + '''
[inputs._subject]
args     = []
surfaces = ["say"]

[surfaces.say]
args = ["hello"]
'''

#: A census with one row, because a census with none is refused: the version
#: of the interpreter, which no surface of the stub reads.
_COMMAND_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the interpreter"
disposition = "state"
commands    = [["<PYTHON>", "--version"]]
finding     = "the stub runs under the interpreter that runs golden-census"
'''

_COMMAND_SCRIPTS = {
    "stub.py": "import sys\nprint('said', sys.argv[1])\n",
    "same.py": "import sys\nprint('said', sys.argv[1])\n",
    "changed.py": "import sys\nprint('said again', sys.argv[1])\n",
}


def _command_override_control(check: CheckRow, skip: SkipRow) -> None:
    """(qqqqqqqq) `compare --command ARG …` runs the fresh capture with
    another argv, and the golden stays the manifest's record.

    One stub subject, recorded under `stub.py`. Another script that prints
    the same is IDENTICAL at exit 0 with a `command:` line under `new:` that
    names the argv as resolved; one that prints a changed word moves exactly
    its row at exit 1, with the same line; a `compare` without the flag
    prints no such line. `--command` beside `--against`, an empty element
    and a `<HERE>` path that is not there are each ONE refusal at exit 2
    with no process-group line, because none of them can run.

    Every command line goes through the real `main`. The expected lines are
    spelled here as literals, with the box this row made, and are not
    computed by the code under test.
    """
    label = ("qqqqqqqq  `compare --command ARG ...` runs the fresh capture "
             "with that argv in place of the manifest's: a script that "
             "prints the same is IDENTICAL at exit 0 and one that prints a "
             "changed word moves its row at exit 1, each with a `command:` "
             "line directly under `new:` naming the argv as resolved, and a "
             "compare without the flag prints no `command:` line; the flag "
             "beside `--against`, an empty element and a `<HERE>` path that "
             "is not there are each ONE `REFUSED:` at exit 2, before the "
             "process-group line")
    wrong: list[str] = []
    said: list[str] = []
    with _box("golden-census-command-") as box:
        manifest = _scratch(box, _COMMAND_MANIFEST, _COMMAND_CENSUS,
                            _COMMAND_SCRIPTS)
        golden = os.path.join(box, "golden")
        base = ["compare", "--manifest", manifest, "--golden", golden]
        code, printed = _handed_on(main, ["capture", "--manifest", manifest,
                                          "--out", golden])
        recorded = code == 0
        if not recorded:
            wrong.append(f"`capture` -> exit {code}, "
                         + _one_line(printed, 110, empty=_NO_VERDICT))

        def ran(extra: list[str]) -> tuple[Any, list[str]]:
            code, printed = _handed_on(main, base + extra)
            said.append(f"{' '.join(extra) or '(no flag)'} -> exit {code}, "
                        + _one_line(printed.replace(box, "<box>"), 90,
                                    needles=("REFUSED:", "IDENTICAL",
                                             "[DIFF]", "command:", "argparse"),
                                    empty=_NO_VERDICT))
            return code, printed.splitlines()

        def after_new(lines: list[str]) -> str | None:
            """The line directly under `new:`'s, or None."""
            at = next((n for n, line in enumerate(lines)
                       if line.startswith("  new:")), None)
            if at is None or at + 1 >= len(lines):
                return None
            return lines[at + 1]

        python = ["--command", "<PYTHON>"]
        for file, code_wanted, verdict in (("same.py", 0, "  IDENTICAL"),
                                          ("changed.py", 1, "  1 differing row(s)")):
            code, lines = ran(python + ["--command", f"<HERE>/{file}"])
            if not (code == code_wanted and verdict in lines
                    and after_new(lines) == f"  command: <PYTHON> {box}/{file}"):
                wrong.append(f"--command {file}: not exit {code_wanted} with "
                             f"{verdict.strip()!r} and its `command:` line "
                             "under `new:`")
            if file == "changed.py" and not (
                    "  [DIFF]    _subject/say.out (changed)" in lines
                    and "      +said again hello" in lines):
                wrong.append("--command changed.py: its row is not the one "
                             "moved, with the changed line")
        code, lines = ran([])
        if not (code == 0 and "  IDENTICAL" in lines
                and not any(line.startswith("  command:") for line in lines)):
            wrong.append("a compare without the flag: not exit 0, IDENTICAL "
                         "and no `command:` line")
        for why, extra, words in (
                ("beside --against", ["--command", "x", "--against", golden],
                 ("`compare --command`", "`--against`")),
                ("an empty element", python + ["--command", ""],
                 ("`compare --command`", "empty or white-space")),
                ("a <HERE> path that is not there",
                 python + ["--command", "<HERE>/nope.py"],
                 ("compare --command", "does not exist"))):
            code, lines = ran(extra)
            refusals = [line for line in lines if line.startswith("REFUSED:")]
            # A path that cannot be checked until the manifest is read is
            # refused inside the group, so only the first two are held to
            # print no group line; none of the three starts the subject.
            grouped = any(line.startswith("process group") for line in lines)
            if not (code == 2 and len(refusals) == 1
                    and all(word in refusals[0] for word in words)
                    and any(line.strip().startswith("next: ")
                            for line in lines)
                    and "capture complete" not in "\n".join(lines)
                    and (grouped if "HERE" in why else not grouped)):
                wrong.append(f"{why}: not ONE refusal naming {words} at exit 2")
    check(label, recorded and not wrong,
          ACTUAL + "; ".join(said) + f"; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}",
          next="`cli.main` refuses `--command` beside `--against` and an "
               "empty element before `anchored`, applies it with "
               "`Manifest.with_command` after the load, and hands it to "
               "`compare.compare`, which prints the `command:` line.")


#: The sentence `compare` prints as its `next:` when every `[DIFF]` is a
#: surface the manifest names and the golden does not record (arm
#: `nnnnnnnn`), spelled here as a literal and not read from the code.
_NEW_ROWS_NEXT = ("Every [DIFF] row above is a surface the manifest names and "
                  "the golden does not record, because the golden was "
                  "captured from a manifest without those rows. To record "
                  "them, run capture --force and commit the golden with the "
                  "manifest row.")

_NEW_ROWS_ONE = _COMMAND_MANIFEST
_NEW_ROWS_TWO = _COMMAND_MANIFEST.replace(
    'surfaces = ["say"]', 'surfaces = ["say", "other"]') + '''
[surfaces.other]
args = ["there"]
'''


def _new_rows_next_control(check: CheckRow, skip: SkipRow) -> None:
    """(nnnnnnnn) `compare` says to record with `--force` when every
    `[DIFF]` is a surface the manifest names and the golden does not record,
    and prints the general `next:` in every other case.

    One stub subject with a golden captured from a manifest of one surface,
    then the manifest with a second surface added. The run exits 1 with
    exactly `surfaces.json (changed)` and the new surface's three files
    `(only-in-new)`, and its `next:` is the sentence about recording them.
    Two controls keep it from being printed for every red run: the same
    comparison with the first surface's output changed, and with a stray
    file in the golden's input directory, each print the general `next:`.

    Every command line goes through the real `main`. The expected sentence is
    a literal here, not read from the code under test.
    """
    label = ("nnnnnnnn  `compare` over a manifest that gained a surface since "
             "the golden was captured, where every `[DIFF]` is that "
             "surface's file or the `surfaces.json` that lists it, exits 1 "
             "and its `next:` says to record them with `capture --force`; "
             "the same comparison with another surface's output changed, "
             "and with a stray file in the golden, each print the general "
             "`next:` and not that sentence")
    wrong: list[str] = []
    said: list[str] = []
    with _box("golden-census-new-rows-") as box:
        manifest = _scratch(box, _NEW_ROWS_ONE, _COMMAND_CENSUS,
                            {"stub.py": _COMMAND_SCRIPTS["stub.py"]})
        golden = os.path.join(box, "golden")
        code, printed = _handed_on(main, ["capture", "--manifest", manifest,
                                          "--out", golden])
        recorded = code == 0
        if not recorded:
            wrong.append(f"`capture` -> exit {code}, "
                         + _one_line(printed, 110, empty=_NO_VERDICT))
        pathlib.Path(manifest).write_text(_NEW_ROWS_TWO, encoding="utf-8")

        def ran(what: str) -> tuple[Any, list[str], str]:
            code, printed = _handed_on(main, ["compare", "--manifest",
                                              manifest, "--golden", golden])
            lines = printed.splitlines()
            nexts = [line.strip() for line in lines
                     if line.strip().startswith("next:")]
            said.append(f"{what} -> exit {code}, next: "
                        + (_one_line(nexts[-1][len("next:"):].strip(), 60)
                           if nexts else "(none)"))
            return code, lines, (nexts[-1][len("next:"):].strip()
                                 if nexts else "")

        code, lines, line = ran("a second surface")
        rows = sorted(row.strip() for row in lines
                      if row.startswith("  [DIFF]"))
        wanted = sorted(f"[DIFF]    _subject/{name} ({kind})" for name, kind in
                        (("surfaces.json", "changed"),
                         ("other.out", "only-in-new"),
                         ("other.err", "only-in-new"),
                         ("other.exit", "only-in-new")))
        if code != 1 or rows != wanted:
            wrong.append(f"the case: exit {code} with rows {rows}, not exit 1 "
                         f"with {wanted}")
        if line != _NEW_ROWS_NEXT:
            wrong.append("the case: its `next:` is not the sentence about "
                         "recording the new surface")
        pathlib.Path(os.path.join(box, "stub.py")).write_text(
            _COMMAND_SCRIPTS["changed.py"], encoding="utf-8")
        code, lines, line = ran("the first surface changed")
        if code != 1 or not line or line == _NEW_ROWS_NEXT:
            wrong.append("control, a surface the golden holds moved: not "
                         "exit 1 with the general `next:`")
        pathlib.Path(os.path.join(box, "stub.py")).write_text(
            _COMMAND_SCRIPTS["stub.py"], encoding="utf-8")
        pathlib.Path(os.path.join(golden, "_subject", "stray.txt")).write_text(
            "stray\n", encoding="utf-8")
        code, lines, line = ran("a stray file in the golden")
        if code != 1 or not line or line == _NEW_ROWS_NEXT:
            wrong.append("control, a stray file in the golden: not exit 1 "
                         "with the general `next:`")
    check(label, recorded and not wrong,
          ACTUAL + "; ".join(said) + f"; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}",
          next="`compare.compare` chooses the sentence with "
               "`compare.only_new_surfaces`; it is the general line unless "
               "every blocking row is a surface the golden's `surfaces.json` "
               "does not list.")


#: The sentence `compare` prints as its `next:` when every `[DIFF]` is a
#: surface the golden records and the manifest no longer names (arm
#: `pppppppp`), spelled here as a literal and not read from the code.
_DROPPED_NEXT = ("Every [DIFF] row above is a surface the golden records and "
                 "the manifest no longer names. To stop recording them, run "
                 "capture --force and commit the golden with the manifest.")


def _dropped_next_control(check: CheckRow, skip: SkipRow) -> None:
    """(pppppppp) `compare` says to stop recording with `--force` when every
    `[DIFF]` is a surface the golden records and the manifest no longer
    names, and prints the general `next:` in every other case.

    One stub subject with a golden captured from a manifest of two surfaces,
    then the manifest with the second surface removed. The run exits 1 with
    exactly `surfaces.json (changed)` and the removed surface's three files
    `(only-in-golden)`, and its `next:` is the sentence about no longer
    recording them. Two controls keep it from being printed for every red
    run: the same comparison with the first surface's output changed, and
    with a stray file in the golden's input directory, each print the
    general `next:`.

    Every command line goes through the real `main`. The expected sentence is
    a literal here, not read from the code under test.
    """
    label = ("pppppppp  `compare` over a manifest that lost a surface since "
             "the golden was captured, where every `[DIFF]` is that "
             "surface's file or the `surfaces.json` that lists it, exits 1 "
             "and its `next:` says to stop recording them with `capture "
             "--force`; the same comparison with another surface's output "
             "changed, and with a stray file in the golden, each print the "
             "general `next:` and not that sentence")
    wrong: list[str] = []
    said: list[str] = []
    with _box("golden-census-dropped-") as box:
        manifest = _scratch(box, _NEW_ROWS_TWO, _COMMAND_CENSUS,
                            {"stub.py": _COMMAND_SCRIPTS["stub.py"]})
        golden = os.path.join(box, "golden")
        code, printed = _handed_on(main, ["capture", "--manifest", manifest,
                                          "--out", golden])
        recorded = code == 0
        if not recorded:
            wrong.append(f"`capture` -> exit {code}, "
                         + _one_line(printed, 110, empty=_NO_VERDICT))
        pathlib.Path(manifest).write_text(_NEW_ROWS_ONE, encoding="utf-8")

        def ran(what: str) -> tuple[Any, list[str], str]:
            code, printed = _handed_on(main, ["compare", "--manifest",
                                              manifest, "--golden", golden])
            lines = printed.splitlines()
            nexts = [line.strip() for line in lines
                     if line.strip().startswith("next:")]
            said.append(f"{what} -> exit {code}, next: "
                        + (_one_line(nexts[-1][len("next:"):].strip(), 60)
                           if nexts else "(none)"))
            return code, lines, (nexts[-1][len("next:"):].strip()
                                 if nexts else "")

        code, lines, line = ran("a surface removed")
        rows = sorted(row.strip() for row in lines
                      if row.startswith("  [DIFF]"))
        wanted = sorted(f"[DIFF]    _subject/{name} ({kind})" for name, kind in
                        (("surfaces.json", "changed"),
                         ("other.out", "only-in-golden"),
                         ("other.err", "only-in-golden"),
                         ("other.exit", "only-in-golden")))
        if code != 1 or rows != wanted:
            wrong.append(f"the case: exit {code} with rows {rows}, not exit 1 "
                         f"with {wanted}")
        if line != _DROPPED_NEXT:
            wrong.append("the case: its `next:` is not the sentence about "
                         "no longer recording the removed surface")
        pathlib.Path(os.path.join(box, "stub.py")).write_text(
            _COMMAND_SCRIPTS["changed.py"], encoding="utf-8")
        code, lines, line = ran("the first surface changed")
        if code != 1 or not line or line == _DROPPED_NEXT:
            wrong.append("control, a surface the manifest keeps moved: not "
                         "exit 1 with the general `next:`")
        pathlib.Path(os.path.join(box, "stub.py")).write_text(
            _COMMAND_SCRIPTS["stub.py"], encoding="utf-8")
        pathlib.Path(os.path.join(golden, "_subject", "stray.txt")).write_text(
            "stray\n", encoding="utf-8")
        code, lines, line = ran("a stray file in the golden")
        if code != 1 or not line or line == _DROPPED_NEXT:
            wrong.append("control, a stray file in the golden: not exit 1 "
                         "with the general `next:`")
    check(label, recorded and not wrong,
          ACTUAL + "; ".join(said) + f"; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}",
          next="`compare.compare` chooses the sentence with "
               "`compare.only_dropped_surfaces`; it is the general line "
               "unless every blocking row is a surface the golden's "
               "`surfaces.json` lists and the manifest no longer names.")


#: The line `compare --against` prints after `new:` (arm `rrrrrrrr`), spelled
#: here as a literal and not read from the code.
_AGAINST_LINE = ("  --against: no census control and no contraband scan ran "
                 "here; quote the ones from the capture that made that "
                 "directory.")


def _against_line_control(check: CheckRow, skip: SkipRow) -> None:
    """(rrrrrrrr) `compare --against` says, inside its COMPARE block, that
    no census control and no contraband scan ran in that command, and a
    plain `compare` does not.

    One stub subject, a golden and a second capture in another directory.
    `compare --against` that directory exits 0 and its block between the
    two rules is `golden:`, `new:` and exactly the sentence. The control is
    the plain `compare`: no line of its block opens `  --against:`, and the
    two blocks differ only in their `new:` line.

    Every command line goes through the real `main`. The expected sentence is
    a literal here, not read from the code under test.
    """
    label = ("rrrrrrrr  `compare --against` exits 0 and its COMPARE block "
             "holds the `new:` line followed by exactly the sentence that no "
             "census control and no contraband scan ran there, before the "
             "file-count line; the plain `compare` block has no line "
             "opening `  --against:` and differs from it only in its `new:` "
             "line")
    wrong: list[str] = []
    seen: list[str] = []

    def block(printed: str) -> list[str]:
        lines = printed.splitlines()
        if "COMPARE" not in lines:
            return []
        rest = lines[lines.index("COMPARE") + 1:]
        out: list[str] = []
        for line in rest:
            if line == RULE:
                if out:
                    break
                continue
            out.append(line)
        return out

    with _box("golden-census-against-line-") as box:
        manifest = _scratch(box, _NEW_ROWS_ONE, _COMMAND_CENSUS,
                            {"stub.py": _COMMAND_SCRIPTS["stub.py"]})
        golden = os.path.join(box, "golden")
        kept = os.path.join(box, "kept")
        recorded = True
        for out_dir in (golden, kept):
            code, printed = _handed_on(main, ["capture", "--manifest",
                                              manifest, "--out", out_dir])
            if code != 0:
                recorded = False
                wrong.append(f"`capture` -> exit {code}, "
                             + _one_line(printed, 110, empty=_NO_VERDICT))
        code, printed = _handed_on(main, ["compare", "--manifest", manifest,
                                          "--golden", golden,
                                          "--against", kept])
        against = block(printed)
        plain_code, plain_printed = _handed_on(
            main, ["compare", "--manifest", manifest, "--golden", golden])
        plain = block(plain_printed)
        seen.append("--against block: " + " | ".join(
            line.strip() for line in against))
        seen.append("plain block: " + " | ".join(
            line.strip() for line in plain))
        newer = [i for i, line in enumerate(against)
                 if line.startswith("  new:")]
        if code != 0:
            wrong.append(f"the case: `--against` exited {code}, not 0")
        if (not newer or against[newer[0] + 1:newer[0] + 2]
                != [_AGAINST_LINE] or against[newer[0] + 2:]):
            wrong.append("the case: the block is not `new:` followed by "
                         "exactly the sentence")
        if any(line.startswith("  --against:") for line in plain):
            wrong.append("control: the plain `compare` block has the line")
        if plain_code != 0:
            wrong.append(f"control: the plain `compare` exited {plain_code}")
        if (len(against) != len(plain) + 1
                or [line for line in against if line != _AGAINST_LINE
                    and not line.startswith("  new:")]
                != [line for line in plain if not line.startswith("  new:")]):
            wrong.append("control: the two blocks differ in more than their "
                         "`new:` line")
    check(label, recorded and not wrong,
          ACTUAL + "; ".join(seen) + f"; not as the row says: "
          f"{'; '.join(wrong) or 'none of them'}",
          next="`compare.compare` writes the sentence after the `new:` line "
               "when `against` is not None, and writes nothing there "
               "otherwise.")
