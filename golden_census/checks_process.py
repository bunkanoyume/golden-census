"""The arms over the run's process GROUP: the line every command that
launches anything opens with, the sweep that kills what a subject left
behind, and the marker every subject environment carries.
"""

from __future__ import annotations

import functools
import io
import os
import pathlib
import pty
import re
import select
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from .census import (
    CHILD_MARKER,
    CHILD_VALUE,
    Census,
    build_env,
)
from .cli import main
from .controls import CheckRow, SkipRow
from .core import (
    ACTUAL,
    DIFFERENCE,
    OTHER_STOP_NEXT,
    OTHER_STOP_SAID,
    TTY_STOP_SAID,
    anchored,
    fixed_dir_refusal,
    fixed_dir_room,
    group_line,
    IMPORT_NAME,
    launch,
    read_text,
    Refusal,
    Roots,
    start_anchor,
    temp_base,
)
from .docs import (
    _run as docs_run,
)
from .manifest import load_manifest
from .probe import WRITES
from .proof import (
    _STUB_CENSUS,
    _STUB_MANIFEST,
    _box,
    _heard,
    _one_line,
    _package_argv,
    _scratch,
)
from .checks_base import (
    PACKAGE,
    _printed_refusal,
    arm_modules_named,
    is_arm_module,
    _call_sites,
    _walk_package,
)

# --------------------------------------- one process group per run (www, xxx)
#
# golden-census keeps no clock, so the exit that ends a hung run is the
# caller's, and a caller that kills golden-census outright leaves everything it
# started running. One group per run is what makes that recoverable: an anchor
# holds the group open, every child joins it, the group is named on the first
# line, and it is swept on every exit golden-census sees.
#
# The two arms below are the two halves of that claim. `www` asks whether the
# sweep reaches a process golden-census never started and never waited for.
# `xxx` asks whether the line a reader would use is printed, is FIRST, names
# one group, and names a group the caller is not in.

#: The planted grandchild: it holds the write end of the arm's fifo — inherited
#: from the subject, never opened by name — and waits to be signaled. It is
#: `sys.executable` and two lines rather than `sh -c 'sleep 600 &'` because a
#: shell would be a program this arm depends on, and an arm's own fixture is
#: held to the same rule as everything else here.
_TREE_GRANDCHILD = "import signal\nsignal.pause()\n"

#: The planted subject: it BACKGROUNDS the grandchild, says so, and exits at
#: once. Both orderings matter. The grandchild is started before the byte is
#: written, so a byte on the fifo proves the grandchild exists; and the subject
#: EXITS, so the sweep has to reach a process whose parent is already gone,
#: which is the case a per-pid kill cannot cover.
#: The grandchild's own streams go to `DEVNULL`, which is not tidiness: a
#: grandchild that inherits the subject's stdout holds that pipe open after
#: the subject exits, and `launch` — which reads to EOF, as any caller
#: does — waits on it. That is the crash this whole mechanism is for, seen
#: one level down: the orphan holds the pipe, and the run looks like a hang.
#: Measured here before it was written down.
_TREE_SUBJECT = ("import os, subprocess, sys\n"
                 "fd = os.open(sys.argv[2], os.O_WRONLY)\n"
                 "subprocess.Popen([sys.executable, sys.argv[1]], "
                 "pass_fds=(fd,), stdin=subprocess.DEVNULL, "
                 "stdout=subprocess.DEVNULL, "
                 "stderr=subprocess.DEVNULL)\n"
                 "os.write(fd, b'g')\n")

#: Arm `xxx`'s planted subject: it writes its OWN process group and its
#: child's, so the arm reports which group the tree is actually in rather than
#: which group it was told to join.
_GROUP_SUBJECT = (
    "import os, subprocess, sys\n"
    "child = subprocess.run([sys.executable, '-c', "
    "'import os, sys; sys.stdout.write(str(os.getpgid(0)))'], "
    "capture_output=True, text=True)\n"
    "open(sys.argv[1], 'w').write(f'{os.getpgid(0)}\\n{child.stdout}\\n')\n")


def _planted_tree(box: str, name: str) -> tuple[int, list[str]]:
    """`(the arm's read end of the fifo, the subject's argv)` for one planted
    tree under `box`.

    A named fifo and not an inherited pipe because `launch` hands a child
    nothing but its argv and its environment, and these arms measure the REAL
    launcher. The read end is opened first and non-blocking, so opening it
    waits for nobody; every question asked of it afterwards has a writer,
    because `launch` returns only once the subject has written its byte.
    """
    fifo = os.path.join(box, f"{name}.fifo")
    os.mkfifo(fifo)
    paths = []
    for part, source in (("subject", _TREE_SUBJECT),
                         ("grandchild", _TREE_GRANDCHILD)):
        path = os.path.join(box, f"{name}-{part}.py")
        pathlib.Path(path).write_text(source, encoding="utf-8")
        paths.append(path)
    return os.open(fifo, os.O_RDONLY | os.O_NONBLOCK), [
        sys.executable, paths[0], paths[1], fifo]


def _tree_up(fd: int) -> bool:
    """Whether the planted tree reached the fifo: one non-blocking read of the
    byte the subject wrote after starting the grandchild."""
    try:
        return os.read(fd, 1) == b"g"
    except BlockingIOError:                     # a writer, but no byte yet
        return False


def _tree_holds(fd: int) -> bool:
    """Whether the grandchild still holds its end of the fifo, asked once and
    without waiting.

    The fifo becomes readable only at EOF, and EOF arrives only when the last
    writer is gone; the readiness byte has already been taken, so there is
    nothing else the read end can report. Not a poll and not a clock: one
    question about a fact that has already settled.
    """
    return not select.select([fd], [], [], 0)[0]


#: How long arm `www` waits for the planted grandchild's end of the fifo to
#: close. The arm's own bound over its own two-line tree, never a subject's:
#: a swept grandchild is gone in milliseconds, and a sweep that does not reach
#: it would otherwise hang the self-test with no row at all.
_SWEEP_WAIT = 10


def _tree_gone(fd: int) -> bool:
    """Whether the grandchild's end of the fifo closes within `_SWEEP_WAIT`
    seconds: a red verdict for a sweep that does not reach the tree, where a
    wait with no bound hung the arm and printed nothing."""
    if not select.select([fd], [], [], _SWEEP_WAIT)[0]:
        return False
    return os.read(fd, 1) == b""


def _kill_left(pgid: int) -> None:
    """SIGKILL what a sweep under test left in group `pgid`: the arm's own
    planted tree, which no exit of golden-census's will reach."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass                                    # nothing of the tree is left


def _sweep_control(check: CheckRow, skip: SkipRow) -> None:
    """(www) the sweep reaches a grandchild golden-census never started."""
    label = ("www  a subject that BACKGROUNDS a grandchild and exits leaves "
             "nothing of that tree behind once the run's group is swept: the "
             "fifo the grandchild holds reaches EOF as golden-census's own "
             "exit path runs, while the same tree under a copy of the "
             "mechanism with the sweep CUT OUT still holds that fifo open — "
             "which the arm then kills itself")
    with _box("golden-census-sweep-") as box:
        trees: list[tuple[int, list[str]]] = []
        try:
            for name in ("swept", "unswept"):
                trees.append(_planted_tree(box, name))
        except OSError as exc:
            for fd, _argv in trees:
                os.close(fd)
            skip(label, f"the planted tree could not be built "
                        f"({type(exc).__name__}: {exc}). Nothing was run and "
                        "nothing is claimed.")
            return
        green, red = _sweep_halves(*trees)
    check(label, green[0] and red[0], f"{ACTUAL}{green[1]}; {red[1]}")


def _sweep_halves(swept: tuple[int, list[str]],
                  unswept: tuple[int, list[str]]
                  ) -> tuple[tuple[bool, str], tuple[bool, str]]:
    """The two halves of arm `www`: the real mechanism, then a copy of it with
    the sweep removed.

    The red half is written out here rather than patched into `core`, because
    what it removes is one line of an exit path: a copy that starts the same
    anchor, joins it the same way and simply never sweeps is the whole
    counterfactual, and it is short enough to read beside what it contradicts.
    """
    fd, argv = swept
    with anchored(io.StringIO()) as group:
        launch(argv, "the planted subject")
        up = _tree_up(fd)
    gone = _tree_gone(fd)
    if not gone:
        _kill_left(group.pgid)
    os.close(fd)
    green = (up and gone,
             f"the swept half: the tree reached the fifo={up}, and after "
             f"golden-census's exit path the fifo reached EOF={gone}")

    fd, argv = unswept
    anchor = start_anchor()
    pgid = os.getpgid(anchor.pid)
    subprocess.run(argv, check=False, process_group=pgid,   # noqa: S603
                   stdin=subprocess.DEVNULL, capture_output=True)
    up = _tree_up(fd)
    held = _tree_holds(fd)
    os.killpg(pgid, signal.SIGTERM)             # the arm kills what it left
    anchor.wait()
    killed = _tree_gone(fd)
    os.close(fd)
    red = (up and held and killed,
           f"the unswept half: the tree reached the fifo={up}, the fifo was "
           f"STILL held open with the sweep cut out={held}, and reached EOF "
           f"only once the arm killed group {pgid} itself={killed}")
    return green, red


#: What arm `oooooooo` plants as `signal.py`: the marker file is the whole
#: report, because an anchor that imported this file would run it before
#: anything else.
_PLANTED_SIGNAL = "open({marker!r}, 'w').write('ran')\n"

#: What arm `oooooooo`'s child runs, from the planted directory: the group
#: started the way every run starts it, a wait long enough for a dead anchor
#: to have died, and one word on whether the anchor is still alive.
_ANCHOR_PROBE = ("import io, time\n"
                 "from golden_census.core import anchored\n"
                 "with anchored(io.StringIO()) as group:\n"
                 "    time.sleep(1)\n"
                 "    print(group.anchor.poll() is None)\n")


def _anchor_isolated_control(check: CheckRow) -> None:
    """(oooooooo) the anchor imports nothing from the directory the run was
    started in."""
    label = ("oooooooo  the process-group anchor imports nothing from the "
             "directory golden-census was started in: a planted signal.py "
             "there leaves no marker and the anchor is alive")
    with _box("golden-census-anchor-") as box:
        marker = os.path.join(box, "marker")
        planted = os.path.join(box, "start")
        os.mkdir(planted)
        pathlib.Path(planted, "signal.py").write_text(
            _PLANTED_SIGNAL.format(marker=marker), encoding="utf-8")
        # `-P` keeps the planted directory off THIS child's `sys.path`, so
        # the child's own `import signal` is the standard library's; the
        # package is reached through PYTHONPATH.
        ran = launch(_package_argv("-P", "-c", _ANCHOR_PROBE),
                     "the anchor probe", cwd=planted,
                     env=dict(os.environ, PYTHONPATH=os.path.dirname(PACKAGE)))
        heard = _heard(ran.stderr)
        ran_planted = os.path.exists(marker)
    alive = ran.stdout.strip() == "True"
    check(label,
          alive and not ran_planted and not heard.not_from(PACKAGE),
          f"{ACTUAL}the planted signal.py ran inside the anchor="
          f"{ran_planted}, the anchor was alive after a second={alive}; the "
          f"child imported the package from {heard.where}, and exited "
          f"{ran.returncode}{heard.not_from(PACKAGE)}")


# ---------------------------------- a subject that stops its group (ssssssss)
#
# A child that reads the terminal draws SIGTTIN, and the kernel stops every
# member of its group, the anchor with it. A stopped process does not act on
# SIGTERM, so the printed `kill -- -<PGID>` does nothing and the run hangs
# with no verdict. The arm plants the stop itself, SIGSTOP to the group, which
# is what the watcher sees whatever signal caused it; the pseudo-terminal case
# is the real trigger and is a disclosed SKIP where none can be made.

#: The planted subject: it stops its own whole group, as the kernel's SIGTTIN
#: does, and would sleep on if anything ever continued it.
_STOP_SUBJECT = ("import os, signal, time; "
                 "os.killpg(os.getpgrp(), signal.SIGSTOP); time.sleep(30)")

#: The subject of the pseudo-terminal case: it opens the controlling terminal
#: and reads it, from a group that is not the terminal's foreground group.
_TTY_SUBJECT = "open('/dev/tty').readline()"

#: How long arm `ssssssss` waits for one run of the package over the planted
#: subject. The arm's own bound, never a subject's: a run that refuses ends in
#: a second, and one that hangs would otherwise hang the self-test.
_STOP_WAIT = 10

def _stop_argv(subject: str) -> list[str]:
    return _package_argv("-m", IMPORT_NAME, "probe", "--", sys.executable,
                         "-c", subject, WRITES)


def _stop_env() -> dict[str, str]:
    """The run's environment: the arm's own temp root, which is the one
    `_probe_precondition` asked about, and the package's directory."""
    return dict(os.environ, TMPDIR=temp_base(),
                PYTHONPATH=os.path.dirname(PACKAGE))


def _end_group(pgid: int) -> None:
    """SIGTERM then SIGCONT to group `pgid`: what a hung run's reader does,
    and the order a stopped group needs."""
    for number in (signal.SIGTERM, signal.SIGCONT):
        try:
            os.killpg(pgid, number)
        except (ProcessLookupError, PermissionError):
            pass                                # nothing of it is left


def _group_left(pgid: int) -> bool:
    """Whether group `pgid` still answers. On macOS a zombie answers
    `PermissionError`, so only `ProcessLookupError` is an empty group."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _reaped(child: subprocess.Popen[bytes]) -> bool:
    """Whether `child` ends within `_STOP_WAIT` seconds, reaped when it does.

    A thread and an event, so the arm's bound names no `timeout=` and no
    `TimeoutExpired`: arm `vvv` walks the package for both, because
    golden-census itself keeps no clock.
    """
    done = threading.Event()

    def reap() -> None:
        child.wait()
        done.set()
    threading.Thread(target=reap, daemon=True).start()
    return done.wait(_STOP_WAIT)


def _first_group(text: str) -> int | None:
    """The group the run's first line names, or None."""
    found = re.search(r"process group (\d+) ", text)
    return int(found.group(1)) if found else None


def _stop_ran(argv: list[str], box: str, name: str
              ) -> tuple[bool, int | None, str, int | None]:
    """`(hung, the exit code, what it printed, the run's group)` of one run of
    `argv` in a child, bounded by `_STOP_WAIT` seconds.

    A run still alive at the bound is a hang, and is ended here: SIGTERM then
    SIGCONT to the group its first line names, then SIGTERM to the run, then
    a reap. Its output is a file and not a pipe, so a subject that outlives
    the run cannot hold the arm's read.
    """
    path = os.path.join(box, f"{name}.out")
    with open(path, "wb") as sink:
        run = subprocess.Popen(argv, cwd=box, env=_stop_env(),   # noqa: S603
                               stdin=subprocess.DEVNULL, stdout=sink,
                               stderr=subprocess.STDOUT)
    hung = not _reaped(run)
    text = read_text(path) or ""
    pgid = _first_group(text)
    if hung:
        if pgid is not None:
            _end_group(pgid)
        run.terminate()
        if not _reaped(run):
            run.kill()
            run.wait()
        text = read_text(path) or ""
    return hung, None if hung else run.returncode, text, pgid


def _stop_run_half(box: str) -> tuple[bool, str]:
    """The first case: the run over a subject that stops its group exits 2
    inside the bound, names the stop, and leaves no process of the run."""
    hung, code, text, pgid = _stop_ran(_stop_argv(_STOP_SUBJECT), box, "stop")
    said = OTHER_STOP_SAID.format(
        what="the probed command (run 1)", number=int(signal.SIGSTOP),
        name=signal.SIGSTOP.name) in text
    nexted = OTHER_STOP_NEXT in text
    left = pgid is not None and _group_left(pgid)
    ok = (not hung and code == 2 and said and nexted and pgid is not None
          and not left)
    ended = (f"was still alive at the bound of {_STOP_WAIT} seconds (the arm "
             "ended it)" if hung else f"exited {code}")
    return ok, (f"the run over a subject that stops its group {ended}, its "
                f"output named the stop={said} and said what to do={nexted}, "
                f"and group {pgid} still answered={left}")


def _stopped_sweep_half() -> tuple[bool, str]:
    """The second case: the sweep Ctrl-C runs ends a group that is stopped.

    The sweep itself and not a SIGINT sent to a run, because a run over a
    stopped subject now refuses by itself and a signal would race that
    refusal; a SIGINT's whole effect is this call.
    """
    done = threading.Event()
    with anchored(io.StringIO()) as group:
        child = subprocess.Popen(                                  # noqa: S603
            [sys.executable, "-c", _STOP_SUBJECT], stdin=subprocess.DEVNULL,
            process_group=group.pgid)
        # typeshed declares `os.waitid` off macOS; CPython has it here.
        info = os.waitid(os.P_PID, child.pid,  # type: ignore[attr-defined]
                         os.WSTOPPED | os.WEXITED | os.WNOWAIT)
        stopped = info is not None and info.si_code == os.CLD_STOPPED

        def run_sweep() -> None:
            group.sweep()
            done.set()
        sweeper = threading.Thread(target=run_sweep, daemon=True)
        sweeper.start()
        ended = done.wait(_STOP_WAIT)
        if not ended:
            _end_group(group.pgid)              # the arm ends what it left
        sweeper.join(_STOP_WAIT)
        if not _reaped(child):
            child.kill()
            child.wait()
    left = _group_left(group.pgid)
    return (stopped and ended and not left,
            f"the subject stopped its group={stopped}, the sweep returned "
            f"inside the bound={ended}, and group {group.pgid} still "
            f"answered={left}")


def _stop_tty_half(box: str) -> tuple[bool | None, str]:
    """The third case, the real trigger: the run, on a pseudo-terminal as its
    controlling terminal, over a subject that reads `/dev/tty`. `None` is the
    SKIP, with the error that made it."""
    try:
        pid, fd = pty.fork()
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if pid == 0:                                # the session leader
        argv = _stop_argv(_TTY_SUBJECT)
        os.chdir(box)
        os.execve(argv[0], argv, _stop_env())
    seen = b""
    deadline = time.monotonic() + _STOP_WAIT
    hung = False
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            hung = True
            break
        if not select.select([fd], [], [], left)[0]:
            continue
        try:
            data = os.read(fd, 4096)
        except OSError:                         # EIO: the last holder closed
            break
        if not data:
            break
        seen += data
    text = seen.decode("utf-8", "replace")
    if hung:
        pgid = _first_group(text)
        if pgid is not None:
            _end_group(pgid)
        os.kill(pid, signal.SIGTERM)
    os.close(fd)
    _pid, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    said = TTY_STOP_SAID.format(what="the probed command (run 1)") in text
    ended = ("was still alive at the bound (the arm ended it)" if hung
             else f"exited {code}")
    return (not hung and code == 2 and said,
            f"the run over a subject that reads the terminal {ended} and "
            f"its output named the read={said}")


def _stop_control(check: CheckRow, skip: SkipRow) -> None:
    """(ssssssss) a subject that stops its group is refused, not waited for."""
    label = ("ssssssss  a subject that stops its group, as a read from the "
             "terminal does, is refused naming the stop and the group is "
             "ended: the run does not hang, and Ctrl-C ends a stopped group")
    no_probe = _probe_precondition()
    if no_probe:
        skip(label, f"a probe cannot run here: {no_probe} The planted run "
                    "needs one, so nothing was run and nothing is claimed.")
        return
    with _box("golden-census-stop-") as box:
        first = _stop_run_half(box)
        second = _stopped_sweep_half()
        third = _stop_tty_half(box)
    # One verdict row under the name: the terminal case joins it where a
    # pseudo-terminal could be made, and is the name's one SKIP row where
    # none could (a verdict and a SKIP under one name is the allowed shape;
    # two verdicts is the `[FAIL]  !` row arm nnnnn plants).
    if third[0] is None:
        check(label, first[0] and second[0],
              f"{ACTUAL}{first[1]}; {second[1]}")
        skip("ssssssss  a subject that reads the terminal is refused "
             "naming the read",
             f"a pseudo-terminal could not be made here ({third[1]}). The "
             "terminal half was not exercised here, and nothing is claimed "
             "about a real read of /dev/tty.")
    else:
        check(label, first[0] and second[0] and third[0],
              f"{ACTUAL}{first[1]}; {second[1]}; {third[1]}")


def _anchored_calls(source: str, name: str) -> list[str]:
    """`file:line in owner()` for every CALL to `anchored(...)` in `source`."""
    return _call_sites(source, name, ("anchored",))


#: What arm `xxx` plants: a second place that opens a group of its own. Two
#: groups in one run is two lines and two kill commands for one tree, and
#: whichever the reader takes names only half of what it has to reach.
_PLANTED_ANCHOR = ("def _planted(out: Any) -> None:\n"
                   "    with anchored(out):\n"
                   "        pass\n")

#: A command that keeps every clause, for the half of arm `xxx` that runs a
#: REAL command line rather than the mechanism underneath one.
_GROUP_PROBE_SCRIPT = ("import sys\n"
                       "open(sys.argv[1], 'w').write('one stable line\\n')\n")

#: Arm `xxx`'s label in three pieces, because one of the three claims has a
#: precondition the other two do not: a REAL command line needs a temp root a
#: probe can run under, and the mechanism underneath one needs no directory at
#: all. Concatenated where the probe runs, so the row a reader diffs is one
#: sentence; the middle piece alone is the disclosed SKIP's where it does not.
_XXX_HEAD = ("xxx  every command that launches anything opens with the line "
             "naming the run's process group and the command that kills it, "
             "decided in ONE place — `cli.main`, above the self-check — and "
             "the group named is NOT the caller's: ")
_XXX_PROBE = "a real `probe` command opens with that line, "
_XXX_TAIL = ("a planted subject and that subject's own child both report the "
             "anchor's group, and this process's group is not it; the same "
             "walk over a copy of cli.py with a SECOND anchor site names that "
             "file, that line and its function")


def _probe_precondition() -> str:
    """Why a real `probe` cannot run under this temp root, or `""` when it can.

    A probe makes the census's fixed-width directory before it runs anything,
    so a root with no room for one refuses every probe — including the one
    this arm runs to see a real command's first line. Asked of
    `core.fixed_dir_room`, where the width rule is decided, and answered in
    `core.fixed_dir_refusal`'s own sentence: the rule is not re-spelled here,
    and nothing is made to find out.
    """
    width = Census.builtin().fixed_width
    if width is None:
        return ""
    _base, room = fixed_dir_room(temp_base(), width)
    if room >= 1:
        return ""
    return str(fixed_dir_refusal(temp_base(), width))


def _group_line_control(check: CheckRow, skip: SkipRow) -> None:
    """(xxx) the line every run opens with, and whose group it names.

    Three things in one row, because they are one claim: the line is printed,
    it is FIRST, and the group it names is the run's own rather than the
    caller's. The last is the measured correction the whole design turns on —
    an agent's shell is already a process-group leader, so a run that printed
    its own group as it found it would hand the reader a command that kills
    the shell.

    What this arm cannot say is that the group holds NOTHING ELSE: enumerating
    a process group needs `ps`, which golden-census does not depend on. It
    says that the anchor, a planted subject and that subject's own child are
    all in the group and that this process is not, and the exhaustive
    membership is a `ps` measurement made by hand beside the stage's record.

    The real-`probe` claim is the one with a precondition, and under a temp
    root too wide for the census's fixed-width rule it is a disclosed SKIP of
    its own rather than a red row about the machine — the shape `mm-rr` and
    `eee` file for the same width. The other two claims still run: they make
    no directory.
    """
    no_probe = _probe_precondition()
    label = _XXX_HEAD + ("" if no_probe else _XXX_PROBE) + _XXX_TAIL
    sources, found, why = _walk_package(_anchored_calls)
    if why:
        skip(label, why)
        return
    # The self-check's own modules are excluded and disclosed in the row: the
    # two arms of this section drive the mechanism directly, which is a CALL
    # and not a decision about a command. Recognized by their name rather than
    # listed, so a new arm file cannot be silently left out of the walk and
    # read as a second decider.
    sites = [site for site in found
             if not is_arm_module(site.split(":")[0])]
    if "cli.py" not in sources:
        skip(label, "cli.py was not found beside this module, so the "
                    "planted-anchor control cannot be built. Nothing is "
                    "claimed.")
        return
    planted_source = (sources["cli.py"].rstrip("\n") + "\n\n\n"
                      + _PLANTED_ANCHOR)
    planted_line = len(planted_source.rstrip("\n").splitlines()) - 1
    planted = _anchored_calls(planted_source, "cli.py")
    wanted = f"cli.py:{planted_line} in _planted()"
    with _box("golden-census-group-") as box:
        try:
            _group_files(box)
        except OSError as exc:
            skip(label, f"the planted subject could not be written "
                        f"({type(exc).__name__}: {exc}). The walk found "
                        f"{sites}, and nothing is claimed about the group.")
            return
        live, said = _group_halves(box, main, not no_probe)
    ok = (len(sites) == 1 and sites[0].startswith("cli.py:")
          and sites[0].endswith(" in main()")
          and planted[-1:] == [wanted] and live[0]
          and (said is None or said[0]))
    probed = "" if said is None else f"{said[1]}; "
    # The line numbers stay out of the green detail, as arm `ii`'s do: they
    # move with every edit to cli.py, and a control whose passing text changes
    # under an unrelated commit is a control nobody can diff.
    check(label, ok,
          f"{ACTUAL}{len(sites)} anchor site(s) outside {arm_modules_named()}, in "
          f"cli.py's main(), across {len(sources)} module(s); {live[1]}; "
          f"{probed}the planted second anchor was found, named by its "
          "file, its line and its function"
          if ok else
          f"{ACTUAL}anchor site(s) {sites} across {len(sources)} module(s); "
          f"{live[1]}; {probed}the planted second anchor came back as "
          f"{planted} and had to end in [{wanted!r}]")
    if no_probe:
        skip("xxx  " + _XXX_PROBE.rstrip(", "),
             f"a probe cannot run here: {no_probe} The two claims above it "
             "were measured and this one was not: no real command line was "
             "run and nothing is claimed about its first line.")


def _group_files(box: str) -> None:
    """Arm `xxx`'s planted subject and probed script, written into `box`: the
    one step of the arm a machine can fail at without golden-census being
    wrong."""
    for name, text in (("group-subject.py", _GROUP_SUBJECT),
                       ("probed.py", _GROUP_PROBE_SCRIPT)):
        pathlib.Path(os.path.join(box, name)).write_text(text,
                                                          encoding="utf-8")


def _group_halves(box: str, main: Any, probe_half: bool
                  ) -> tuple[tuple[bool, str], tuple[bool, str] | None]:
    """Arm `xxx`'s two measurements: whose group a planted tree is in, and —
    where a probe can run at all — what a real command's first line says."""
    report = os.path.join(box, "groups.txt")
    subject = os.path.join(box, "group-subject.py")
    sink = io.StringIO()
    with anchored(sink) as group:
        launch([sys.executable, subject, report], "the planted subject")
        reported = [int(part) for part in (read_text(report) or "").split()]
    line = (sink.getvalue().splitlines() or [""])[0]
    mine = os.getpgrp()
    live = (len(reported) == 2 and set(reported) == {group.pgid}
            and mine != group.pgid
            and line == group_line(group.pgid).rstrip("\n"),
            f"the planted subject and its child reported group(s) "
            f"{sorted(set(reported))}, the anchor's is {group.pgid}, this "
            f"process's is {mine} and is NOT it={mine != group.pgid}; the "
            f"line read {_one_line(line, 110)!r}")

    if not probe_half:
        return live, None

    script = os.path.join(box, "probed.py")
    code, text = docs_run(main, ["probe", "--", sys.executable, script, WRITES])
    first = (text.splitlines() or [""])[0]
    said = (code == 0 and first.startswith("process group ")
            and "kill -- -" in first,
            f"a real `probe` exited {code} and its FIRST line was "
            f"{_one_line(first, 110)!r}")
    return live, said


# ------------------------------------------------- the recursion marker (yyy)
#
# Every subject environment carries one variable no census names. It says the
# thing the subject cannot find out for itself and most needs to know: this
# process was started by golden-census. A subject whose own self-test would
# run the census again reads it and refuses, and one that ignores it behaves
# exactly as it did before — which is why it is documented as a clause a
# subject MAY honor and never enforced.

#: The planted subject: it writes its whole environment where the arm can read
#: it. The whole environment, not just the marker, because the claim is about
#: what `build_env` BUILDS — a marker present beside variables nobody pinned
#: would be a different finding, and this way the arm can see it.
_MARKER_SUBJECT = ("import os, sys\n"
                   "open(sys.argv[1], 'w').write("
                   "''.join(f'{k}={v}\\n' for k, v in sorted(os.environ.items())))\n")


#: A census row that pins the recursion marker to `{value}`, for arm `yyy`:
#: the stub census plus this row is a census that loads in every other
#: respect.
_MARKER_PIN = f'''
[[input]]
name        = "the child marker"
disposition = "pin"
variable    = "{CHILD_MARKER}"
value       = "{{value}}"
finding     = "a planted pin of the recursion marker"
control     = {{{{ shape = "vary", surface = "_subject/help", value = "varied" }}}}
'''


def _marker_env_control(check: CheckRow, skip: SkipRow) -> None:
    """(yyy) the recursion marker reaches every subject, and neither a
    surface nor a census can set it.

    Three verdicts in one row because they are one rule: the marker is in the
    built environment, a copy of `build_env` without the line does not put it
    there, and a surface's `env` naming it is refused the way a pinned
    variable's override is refused. The middle one is the control: a marker
    asserted present by reading the same dictionary that set it would prove
    nothing, so the red half runs the SAME planted subject under an
    environment built without it.

    The files are read too: a census row that pins the marker, and a
    surface's `env` that names it, are each refused when the manifest is
    loaded, in a sentence that opens with its own place — the census and
    the row, the manifest and the surface — as every refusal of a loader
    opens. The pin is planted twice, at a value of its own and at the
    marker's own value, which a subject would see either way, and its
    `next:` says to drop the census row. The stub files without either
    load, which is their control.
    """
    label = ("yyy  every subject environment carries the recursion marker "
             f"{CHILD_MARKER}={CHILD_VALUE}, set after the pins and the "
             "passthrough: a planted subject that writes out its whole "
             "environment shows it, the same subject handed `build_env`'s "
             "environment with the marker filtered out does not, and a "
             "surface's "
             "`env` naming the marker is refused in one sentence, as an "
             "override of a pinned variable is; when the files are read, a "
             "census row that pins the marker, to the marker's own value as "
             "to any other, is refused in one sentence that opens with the "
             "census and the row and says a census cannot pin it, with a "
             "`next:` that says to drop that census row, and a surface's "
             "`env` naming it in one that opens with the manifest and the "
             "surface, while the same files without either load")
    census = Census.builtin()
    try:
        with _box("golden-census-marker-") as box:
            # No fixed-width directory, and the arm runs at any temp root
            # because of it: `_pin_value` leaves the TMPDIR pin out when the
            # run made no such directory, and the marker is set after the
            # pins and the passthrough either way. A width this arm did not
            # need would have made it a disclosed SKIP on the machine an
            # adopter actually has.
            roots = Roots(root=box, work=box, clone=None, fixed=None)
            green = _marker_run(box, "green", build_env(census, roots))
            without = {name: value
                       for name, value in build_env(census, roots).items()
                       if name != CHILD_MARKER}
            red = _marker_run(box, "red", without)
    except Refusal as refused:
        skip(label, f"the planted subject could not be run: {refused} Nothing "
                    "was measured and nothing is claimed.")
        return
    refusal = ""
    try:
        build_env(census, Roots(root="", work="", clone=None),
                  {CHILD_MARKER: "0"})
    except Refusal as refused:
        refusal = str(refused)
    marked = f"{CHILD_MARKER}={CHILD_VALUE}"
    with _box("golden-census-marker-load-") as box:
        loads = {
            name: _printed_refusal(functools.partial(load_manifest, _scratch(
                os.path.join(box, name), manifest_text=manifest_text,
                census_text=census_text)),
                unrefused="LOADED").replace(box, "<box>")
            for name, manifest_text, census_text in (
                ("pin", _STUB_MANIFEST,
                 _STUB_CENSUS + _MARKER_PIN.format(value="pinned")),
                ("pin-own", _STUB_MANIFEST,
                 _STUB_CENSUS + _MARKER_PIN.format(value=CHILD_VALUE)),
                ("env", _STUB_MANIFEST + f'env = {{ {CHILD_MARKER} = "0" }}\n',
                 _STUB_CENSUS),
                ("clean", _STUB_MANIFEST, _STUB_CENSUS))}
    is_set = f"{CHILD_MARKER} is set by golden-census in every subject environment"
    check(label,
          marked in green and marked not in red
          and CHILD_MARKER in refusal and "cannot be overridden" in refusal
          and all(loads[pin].startswith(
                      f"REFUSED: census <box>/{pin}/census.toml: row 'the "
                      f"child marker': {is_set}")
                  and "cannot be pinned by a census" in loads[pin]
                  and loads[pin].endswith(
                      f"\n  next: Drop the census row that pins "
                      f"{CHILD_MARKER}; nothing a census can say about it "
                      "is true.")
                  for pin in ("pin", "pin-own"))
          and loads["env"].startswith(
              f"REFUSED: <box>/env/manifest.toml: [surfaces.help]: {is_set}")
          and "cannot be overridden by a surface's `env`" in loads["env"]
          and loads["clean"] == "LOADED",
          f"{ACTUAL}the planted subject read {marked!r} from its own "
          f"environment={marked in green}, the same subject under a "
          f"`build_env` without the line read it={marked in red}, and a "
          f"surface's `env` naming it was refused with "
          f"{_one_line(refusal, DIFFERENCE)!r}; when the files are read, a "
          f"census pin of it -> {_one_line(loads['pin'], 170)!r}, a "
          f"census pin of it at its own value -> "
          f"{_one_line(loads['pin-own'], 170)!r}, its `next:` -> "
          f"{loads['pin'].partition(chr(10))[2].strip()!r}, a "
          f"surface's `env` naming it -> {_one_line(loads['env'], 170)!r}, "
          f"the same files without either -> {loads['clean']}")


def _marker_run(box: str, name: str, env: dict[str, str]) -> str:
    """The planted subject's own view of one environment, as text."""
    script = os.path.join(box, f"marker-{name}.py")
    pathlib.Path(script).write_text(_MARKER_SUBJECT, encoding="utf-8")
    report = os.path.join(box, f"marker-{name}.env")
    launch([sys.executable, script, report], "the planted subject", env=env)
    return read_text(report) or ""
