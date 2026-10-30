"""The arms over `probe`: the five clauses of `docs/contract.md`, each shown
green on a command that keeps it and red on one that does not.
"""

from __future__ import annotations

import io
import os
import pathlib
import re
import sys
from collections.abc import Callable

from .census import (
    CHILD_MARKER,
)
from .controls import CheckRow, SkipRow
from .core import (
    ACTUAL,
    Refusal,
)
from .checks_base import _fresh_module
from .probe import CANARY_MIN, FILE, PROBLEM, WRITES, Run, probe
from .proof import (
    _box,
    _env_as,
)

# ------------------------------------------------------- the `probe` controls
#
# One arm per clause of `docs/contract.md`, each on a scratch command written
# for it, plus the all-PASS arm that proves the five rows are not simply
# always red. The scripts are the plan's: one that does not write, one that
# writes the time, one that exits 0 without writing, one that prints its cwd,
# one that carries the value of a variable the built environment never passed.


#: The scratch commands the probe arms run, by arm letter. `<WRITES>` is
#: substituted by `probe` itself, exactly as it is for a real candidate.
_PROBE_SCRIPTS = {
    "mm": "import sys\nsys.exit(1)\n",
    "nn": ("import sys, time\n"
           "open(sys.argv[1], 'w').write(f'stamped {time.time_ns()}\\n')\n"),
    "oo": "import sys\nsys.exit(0)\n",
    "pp": ("import os, sys\n"
           "open(sys.argv[1], 'w').write('fine\\n')\n"
           "print('scanned', os.getcwd())\n"),
    "qq": ("import sys\n"
           "open(sys.argv[1], 'w').write('fine\\n')\n"
           "print('token', 'golden-census-probe-canary-4f19d2')\n"),
    "rr": ("import sys\n"
           "open(sys.argv[1], 'w').write('one stable line\\n')\n"),
    # Arm `ggggg`'s three. One program in three spellings: it writes a machine
    # fact into its FILE and prints nothing, it writes a clean line, and it
    # writes bytes that are not UTF-8 text at all.
    "ggggg-home": ("import os, sys\n"
                   "open(sys.argv[1], 'w').write(\n"
                   "    'scanned ' + os.path.expanduser('~') + '/x\\n')\n"),
    "ggggg-clean": ("import sys\n"
                    "open(sys.argv[1], 'w').write('scanned somewhere\\n')\n"),
    "ggggg-binary": ("import sys\n"
                     "open(sys.argv[1], 'wb').write(b'\\xff\\xfe\\x00 b\\n')\n"),
    # Arm `iiiii`'s two. The first writes a DIFFERENT non-UTF-8 file each run
    # whose first bad byte is at the same offset, so the note golden-census
    # keeps for an unreadable file is identical for both; the second writes
    # the same non-UTF-8 file twice. What differs is the last character of the
    # path the probe hands each run (`out-1`, `out-2`), written eight times
    # behind the two bytes that do not: the first difference is at byte
    # `_IIIII_MOVES_AT` in every run, by construction.
    "iiiii-moves": ("import sys\n"
                    "open(sys.argv[1], 'wb').write(\n"
                    "    b'\\xff\\xfe' + sys.argv[1][-1].encode() * 8)\n"),
    "iiiii-still": ("import sys\n"
                    "open(sys.argv[1], 'wb').write(b'\\xff\\xfe' + b'\\x01' * 8)\n"),
}

#: The offset at which `iiiii-moves`' two files first differ: behind the two
#: bytes every run writes.
_IIIII_MOVES_AT = 2

#: What arm `qq` plants in golden-census's OWN environment and nowhere else: a
#: variable no census names, whose value the scratch script carries verbatim.
#: The command "reads" it the way a real one does — by having found it some
#: other way — and clause 5 is what notices.
_PROBE_CANARY = ("GOLDEN_CENSUS_PROBE_CANARY", "golden-census-probe-canary-4f19d2")

#: What arm `pp`'s second half plants: a variable no census names whose value
#: is PART of the directory the probe hands the cwd-printing script. Clause 5
#: must stay green on it — the probe told the command that string — while
#: clause 4 stays red on the same output. The value is `_PLANTED_CWD_LEAF`,
#: the NAME of the directory the arms make and run in: a piece of the
#: reader's own cwd was a value that differed with where the reader stood,
#: and in a directory with no long enough piece there was none to take.
_PROBE_PATHPART = "GOLDEN_CENSUS_PROBE_PATHPART"

#: What arm `pp`'s positive control rebinds on a fresh copy of `probe`:
#: clause 5's containment rule, narrowed to plain membership. An ATTRIBUTE of a
#: copy of the module, not a line of its source — the rule is one function, and
#: a copy of it that answers the narrow way is the whole control.
def _old_handed(value: str, given: tuple[str, ...]) -> bool:
    return value in given


#: What arm `ggggg`'s positive control rebinds on a fresh copy of `probe`:
#: clause 4's scan, narrowed to the two streams. Same shape as `_old_handed`
#: and for the same reason — the rule is one function, and a copy of it that
#: reads only what the command PRINTED is the whole control.
def _streams_only(run: Run) -> list[tuple[str, str]]:
    return [("stdout", run.out), ("stderr", run.err)]


#: What arm `iiiii`'s positive control rebinds on a fresh copy of `probe`:
#: clause 2's comparison, narrowed to the two texts — which for a file
#: golden-census could not read are two copies of its NOTE about the file and
#: not the file at all.
def _compare_notes(one: Run, other: Run) -> str | None:
    if one.written == other.written:
        return None
    return f"they differ at {one.written!r} / {other.written!r}"


#: What arm `hhhhh` rebinds on a fresh copy of THIS module: the `pp` arm that
#: told its caller to stop. Every label after `pp` then goes missing from the
#: block, which is what that answer cost.
def _pp_stops(check: CheckRow, skip: SkipRow, box: str) -> bool:
    skip("pp  the stopping shape", "planted")
    return False


#: A probe block for arm `hhhhh` to hand the arms in place of a real run. It
#: runs no subprocess, so the control costs nothing measurable, and its
#: verdicts are nobody's business: `hhhhh` reads WHICH LABELS the block
#: reported and never what they said.
_CANNED_BLOCK = """\
==============================================================================
PROBE  <PYTHON> <TMPROOT>/canned.py <WRITES>
==============================================================================
  [PASS]  1  takes an output path and writes one file there
           actual: run 1 wrote 5 bytes, run 2 wrote 5 bytes

  1/1 passed
"""


def _names_path(detail: str, path: str) -> bool:
    """True when a clause-4 detail names `path` — whole, or by its start.

    `probe` cuts each clause-4 problem at `PROBLEM` characters, so a cwd
    longer than the room the problem's own words leave can never appear
    whole. An arm asserting the WHOLE cwd therefore goes red from every long
    scratch directory — the 181-character session scratchpads an agent runs
    from — and takes `--selfcheck`, and with it every command, down from
    exactly the directories an agent works in. What the detail CAN carry is
    asserted instead: the token after `absolute path: ` is the
    start of `path`, whole when it fits and cut at exactly the rule's width
    when it does not. A short unrelated path cannot satisfy that.
    """
    if path in detail:
        return True
    for problem in detail.removeprefix(ACTUAL).split("; "):
        found = re.search(r"absolute path: (\S+)$", problem)
        if (found and len(problem) == PROBLEM
                and path.startswith(found.group(1))):
            return True
    return False


#: The leaf of the directory every probe arm runs its candidate in. Long
#: enough for clause 5's canary to look for, and its length is DERIVED from
#: `probe.CANARY_MIN` rather than typed: a canary that stopped looking at
#: values this short would leave the arms planting one it ignores.
_PLANTED_CWD_LEAF = "probe-arms-cwd".ljust(CANARY_MIN, "x")


def _planted_cwd(box: str) -> str:
    """The directory the probe arms run their candidates in, made under `box`.

    PLANTED, never the reader's. Built from `os.getcwd()`, these arms had a
    verdict that depended on where the reader was standing: a cwd with no
    path component of `CANARY_MIN` characters and a parent shorter than that
    — `/work`, `/usr`, `/`, a short home directory — left the canary with
    nothing of the cwd to look for, so `pp`'s old-rule control could not be
    built and the row went red about the machine rather than about `probe`,
    which behaved correctly in every one of those runs. `probe` takes the
    directory as a parameter for exactly this, the way
    `core.Platform.for_platform` and `core.Layout.for_package` take theirs.

    Resolved, because every path the block prints is resolved and the arms
    compare against what the block printed.
    """
    planted = os.path.join(box, _PLANTED_CWD_LEAF)
    os.makedirs(planted, exist_ok=True)
    return os.path.realpath(planted)


def _probe_once(box: str, letter: str) -> tuple[int, str]:
    """Write that arm's script into `box`, probe it in the PLANTED working
    directory, and hand back `(exit code, the whole block)`."""
    path = os.path.join(box, f"{letter}.py")
    pathlib.Path(path).write_text(_PROBE_SCRIPTS[letter], encoding="utf-8")
    log = io.StringIO()
    code = probe([sys.executable, path, WRITES], log, cwd=_planted_cwd(box))
    return code, log.getvalue()


def _rebound_probe(box: str, letter: str, rule: str,
                   stand_in: Callable[..., object]) -> tuple[int, str] | None:
    """`(exit code, the whole block)` for arm `letter`'s script, already in
    `box`, probed in the planted working directory by a fresh copy of `probe`
    whose `rule` is rebound to `stand_in` — or None when this install carries
    no importable source to make the copy from."""
    copy = _fresh_module("probe")
    if copy is None:
        return None
    setattr(copy, rule, stand_in)
    log = io.StringIO()
    code = copy.probe([sys.executable, os.path.join(box, f"{letter}.py"), WRITES],
                      log, cwd=_planted_cwd(box))
    return code, log.getvalue()


def _clause(text: str, number: int) -> str:
    """The verdict on one clause of a probe block: PASS, FAIL, or `absent`.

    Read off the printed block rather than out of a returned structure, on
    purpose: what the reader sees IS the verdict, and an arm that inspected a
    richer object could pass while the block said something else.
    """
    for line in text.splitlines():
        found = re.match(r"\s*\[(PASS|FAIL)\]\s+(\d)\s", line)
        if found and int(found.group(2)) == number:
            return found.group(1)
    return "absent"


def _detail(text: str, number: int) -> str:
    """The 11-space detail line under clause `number`."""
    lines = text.splitlines()
    for index, line in enumerate(lines[:-1]):
        found = re.match(r"\s*\[(?:PASS|FAIL)\]\s+(\d)\s", line)
        if found and int(found.group(1)) == number:
            return lines[index + 1].strip()
    return ""


def _probe_controls(check: CheckRow, skip: SkipRow) -> None:
    """(mm)-(rr) every clause of `probe` going red on a command that breaks
    it, and the all-PASS arm on one that does not."""
    try:
        with _box("golden-census-probe-arms-") as box:
            here = _planted_cwd(box)
            # The pathpart plant is the LEAF of the directory the arms run
            # in, which is one the arms make: a piece of the reader's own cwd
            # was a value that differed with where the reader stood, and in a
            # short directory there was no piece long enough to take.
            #
            # `PWD` and `OLDPWD` are planted with that directory too, for
            # two reasons that are not the same one.
            #
            # `PWD` IS the working directory under another name, and the
            # probe now hands the command the planted one, so the planted one
            # is what it must say.
            #
            # `OLDPWD` is the reader's PREVIOUS directory, which the product
            # deliberately keeps in clause 5's scan (`probe._handed`): nothing
            # gives it away, so a command printing its value has read it. But
            # a reader's shell puts a directory of the READER'S there, and
            # these arms write a home-shaped path into a file on purpose — so
            # the canary matches the reader's `$OLDPWD` by coincidence and the
            # verdict turns on where the reader had been standing. Measured:
            # with `OLDPWD` exported as the home directory and this one entry
            # left unplanted, arm `ggggg`'s streams-only control exits 1 where
            # it must exit 0. An arm's environment is the arm's to plant; the
            # product's rule is untouched.
            planted = {_PROBE_CANARY[0]: _PROBE_CANARY[1],
                       _PROBE_PATHPART: _PLANTED_CWD_LEAF,
                       "PWD": here, "OLDPWD": here}
            with _env_as(planted):
                _probe_arms(check, skip, box)
                _absent_arm_control(check, box)
    except Refusal as refused:
        # A temp root too wide for the `census.FIXED_DIR_WIDTH` pin refuses
        # every probe, including these. Disclosed as one SKIP rather than
        # seven FAIL rows about the machine.
        skip("mm-hhhhh  the five `probe` clauses, each red on a scratch "
             "command, the all-PASS arm, the written file's scan and the "
             "absent-arm control",
             f"a probe cannot run here: {refused}. Nothing was measured and "
             "nothing is claimed.")


#: Every arm `_probe_arms` owes a row, in the order it owes them. Read by arm
#: `hhhhh` and by nothing else — a list, because the claim is about which rows
#: a reader gets and a walk over the source would be a claim about lines.
_PROBE_ARM_LETTERS = ("mm", "nn", "oo", "pp", "qq", "rr", "ggggg", "iiiii")


def _reported(stopping: bool, box: str) -> list[str]:
    """Which arms report a row when no positive control can be built, over a
    fresh copy of this module with every probe canned.

    `_fresh_module("probe")` is planted to None, which is the absence two arms
    build their controls from; `_probe_once` is planted to a canned block, so
    no subprocess runs and this control costs nothing measurable. `stopping`
    restores the shape where `pp` told its caller to stop.
    """
    copy = _fresh_module("checks_probe")
    if copy is None:
        return []
    copy._fresh_module = lambda name: None
    copy._probe_once = lambda where, letter: (1, _CANNED_BLOCK)
    if stopping:
        copy._pp_arm = _pp_stops
    seen: list[str] = []
    copy._probe_arms(lambda label, ok, detail, **rest: seen.append(label),
                     lambda label, reason: seen.append(label), box)
    return [one.split(" ", 1)[0] for one in seen]


def _absent_arm_control(check: CheckRow, box: str) -> None:
    """(hhhhh) an arm whose positive control cannot be built REPORTS — a
    disclosed SKIP — and the arms after it still run."""
    label = ("hhhhh  a probe arm whose positive control cannot be built is a "
             "disclosed SKIP and never an absent row: with "
             "`_fresh_module` planted to return None — the absence `pp` and "
             f"`ggggg` build their controls from — all {len(_PROBE_ARM_LETTERS)} "
             "arms still report, each as a PASS or a SKIP of its own; a copy "
             "whose `pp` answers that its caller should STOP reports only the "
             "arms up to `pp`, which is how this row is known to be able to "
             "go red and is what an absent row costs a reader: it is "
             "indistinguishable from an arm nobody wrote")
    went_on = _reported(False, box)
    stopped = _reported(True, box)
    after_pp = _PROBE_ARM_LETTERS[_PROBE_ARM_LETTERS.index("pp") + 1:]
    check(label,
          went_on == list(_PROBE_ARM_LETTERS)
          and stopped == list(_PROBE_ARM_LETTERS[:_PROBE_ARM_LETTERS.index("pp") + 1])
          and not any(one in stopped for one in after_pp),
          f"{ACTUAL}with the absence planted, the block reported {went_on}; "
          f"with `pp` rebound to the stopping shape it reported {stopped}, "
          f"missing {[one for one in after_pp if one not in stopped]}; owed "
          f"{list(_PROBE_ARM_LETTERS)}")


def _probe_arms(check: CheckRow, skip: SkipRow, box: str) -> None:
    mm_code, mm = _probe_once(box, "mm")
    check("mm  probe clause 1 goes red on a command that writes nothing: the "
          "row says the file was not written and clause 3 still PASSES, "
          "because a command that fails and says so is keeping clause 3",
          _clause(mm, 1) == "FAIL" and _clause(mm, 3) == "PASS"
          and mm_code == 1,
          f"{ACTUAL}exit {mm_code}, clause 1 {_clause(mm, 1)}, clause 3 "
          f"{_clause(mm, 3)}, detail {_detail(mm, 1)[:90]!r}")

    nn_code, nn = _probe_once(box, "nn")
    check("nn  probe clause 2 goes red on a command that writes the time, and "
          "the row NAMES the first differing line rather than saying only "
          "that the two runs differ",
          _clause(nn, 2) == "FAIL" and nn_code == 1
          and "they differ at line 1" in _detail(nn, 2),
          f"{ACTUAL}exit {nn_code}, clause 2 {_clause(nn, 2)}, detail "
          f"{_detail(nn, 2)[:110]!r}")

    oo_code, oo = _probe_once(box, "oo")
    check("oo  probe clause 3 goes red on a command that exits 0 and writes "
          "nothing — the tool that prints SUCCEEDED when its filter matched "
          "nothing, which is the clause's whole reason for existing",
          _clause(oo, 3) == "FAIL" and oo_code == 1
          and "exited 0 and wrote no file" in _detail(oo, 3),
          f"{ACTUAL}exit {oo_code}, clause 3 {_clause(oo, 3)}, detail "
          f"{_detail(oo, 3)[:110]!r}")

    if not _pp_arm(check, skip, box):
        return

    qq_code, qq = _probe_once(box, "qq")
    check("qq  probe clause 5 goes red on a command whose output carries the "
          f"value of ${_PROBE_CANARY[0]} — a variable this process holds and "
          "the built environment did not pass — and the row NAMES that "
          "variable; clause 4 stays green, because the value is not a path",
          _clause(qq, 5) == "FAIL" and qq_code == 1
          and _PROBE_CANARY[0] in _detail(qq, 5)
          and _clause(qq, 4) == "PASS",
          f"{ACTUAL}exit {qq_code}, clause 5 {_clause(qq, 5)}, clause 4 "
          f"{_clause(qq, 4)}, detail {_detail(qq, 5)[-110:]!r}")

    _rr_arm(check, box)
    _ggggg_arm(check, skip, box)
    _iiiii_arm(check, skip, box)


def _pp_arm(check: CheckRow, skip: SkipRow, box: str) -> bool:
    """(pp) clause 4 red on a command that prints its working directory, and
    clause 5 green on the same one.

    The return value is whether the arms AFTER this one should still run, and
    it is always True: an arm whose positive control cannot be built is a
    disclosed SKIP, and what the arms after it can measure is none of its
    business. It is a value rather than nothing at all because arm `hhhhh`
    rebinds this function to one that answers False and watches every label
    after `pp` vanish from the block — a row that goes missing is the zero
    result this project exists to refuse, and it looks identical to a run of
    arms that were never written.
    """
    here = _planted_cwd(box)
    pp_code, pp = _probe_once(box, "pp")
    pp_detail = _detail(pp, 4)
    # The second half's plant is live for every arm (`_probe_controls` sets
    # it): a variable no census names whose value is part of the very
    # directory this script prints. Under the containment rule clause 5
    # ignores it; under plain membership it is reported, and the copy below is
    # what says so rather than a comment claiming it.
    part = os.environ[_PROBE_PATHPART]
    # The positive control: a fresh copy of `probe` whose clause-5 rule is
    # rebound to plain membership. `_clause_5` looks `_handed` up on the
    # module, so rebinding the module's attribute is the whole of it.
    copy = _rebound_probe(box, "pp", "_handed", _old_handed)
    old_code, old = copy or (-1, "")
    pp_label = ("pp  probe clause 4 goes red on a command that prints its "
                "working directory, and the row names the absolute path it "
                "found — whole, or by its start where the row's width cuts "
                "it, so a long cwd is not a red arm — the probe's OWN "
                "directories are folded first, so "
                "every path a clause-4 row quotes is one the command found "
                "for itself; clause 5 stays GREEN on the same command, for "
                f"the whole cwd AND for ${_PROBE_PATHPART}, planted with "
                "the NAME of that directory, because a value CONTAINED IN a "
                "string the probe handed the command is not evidence either; "
                "a copy of the module with clause 5's rule rebound to the old "
                "equality reports that same variable, which is how this row "
                "is known to be able to go red. The working directory is one "
                "this arm MADE, under its own box and long enough for the "
                "canary to look for: read off the reader's instead, all three "
                "claims held or failed by where the reader was standing")
    if copy is None:
        # One absence policy (`core.Layout`'s): an install with no
        # importable `golden_census.probe` cannot have the narrow-rule control
        # built for it — and a row whose control cannot be built is a disclosed
        # SKIP, never a pass and never a raise that takes every later arm with
        # it.
        skip(pp_label,
             "golden_census.probe could not be loaded a second time, so the "
             "old-rule control this row is measured against cannot be built. "
             "Nothing is claimed.")
        return True
    check(pp_label,
          _clause(pp, 4) == "FAIL" and pp_code == 1
          and "stdout:1" in pp_detail and _names_path(pp_detail, here)
          and not _names_path(pp_detail, os.path.join(box, "elsewhere"))
          and _clause(pp, 5) == "PASS"
          and _PROBE_PATHPART not in _detail(pp, 5)
          and len(part) >= CANARY_MIN and part in here
          and old_code == 1 and _clause(old, 5) == "FAIL"
          and _PROBE_PATHPART in _detail(old, 5),
          f"{ACTUAL}exit {pp_code}, clause 4 {_clause(pp, 4)}, clause 5 "
          f"{_clause(pp, 5)}, detail {pp_detail[:110]!r} (names the planted "
          f"cwd {_names_path(pp_detail, here)}, an unrelated path "
          f"{_names_path(pp_detail, os.path.join(box, 'elsewhere'))}); the "
          f"working directory is planted, {len(here)} characters under this "
          f"arm's own box; planted "
          f"${_PROBE_PATHPART}={part!r} ({len(part)} chars, in the planted "
          f"cwd: {part in here}); the old-rule copy (clause 5's `_handed` "
          f"rebound on a fresh module) exit {old_code}, clause 5 "
          f"{_clause(old, 5)}, names it "
          f"{_PROBE_PATHPART in _detail(old, 5)}")
    return True


def _rr_arm(check: CheckRow, box: str) -> None:
    rr_code, rr = _probe_once(box, "rr")
    rr_detail = _detail(rr, 5)
    names = re.findall(r"\b[A-Z][A-Z_]+\b", rr_detail.split("—", 1)[-1]
                       .split(";", 1)[0])
    # The banner's SHAPE. That the whole block carries no machine path is
    # asserted nowhere: the two-root arm `eee` prices `capture` alone, and no
    # arm prices `probe` under two temp roots. What this arm can say is that
    # the banner folds through the census's rows, so the scratch script
    # under the temp root reads as `<TMPROOT>/…/rr.py`.
    rr_line = next((line for line in rr.splitlines()
                    if line.startswith("PROBE  ")), "")
    check("rr  a command that keeps all five clauses comes out 5/5 PASS, and "
          "clause 5's row lists the SIX variables the built-in default "
          "actually passed, TMPDIR and the recursion marker among them: a "
          "probe that forgot to make the fixed-width directory before "
          "building the environment prints five; and the block's banner "
          "carries the argv "
          "FOLDED through the census's own `path` rows — `PROBE  <PYTHON> "
          "<TMPROOT>/…/rr.py <WRITES>`, the script being given to the probe "
          "by its absolute path under the temp root",
          rr_code == 0 and all(_clause(rr, n) == "PASS" for n in range(1, 6))
          and len(names) == 6 and "TMPDIR" in names
          and CHILD_MARKER in names
          and rr_line.startswith("PROBE  <PYTHON> <TMPROOT>/")
          and rr_line.endswith("rr.py <WRITES>"),
          f"{ACTUAL}exit {rr_code}, clauses "
          f"{[_clause(rr, n) for n in range(1, 6)]}, {len(names)} variable(s) "
          f"{names}; banner {rr_line!r}")


def _ggggg_arm(check: CheckRow, skip: SkipRow, box: str) -> None:
    """(ggggg) clause 4 reads what the command WROTE, not only what it
    printed.

    Four halves. A program that prints nothing and writes a home-shaped path
    into its file goes red and the row names the file, the line and the token;
    the same program writing a clean line is green, which is what says the
    wider scan refuses nothing an ordinary subject writes; a copy of the
    module whose scan is rebound to the streams alone passes the planted file,
    which is how this row is known to be able to go red; and a program whose
    file is not UTF-8 text is not scanned, with the row saying so, because a
    limit nothing exercises is a limit nobody has seen hold.
    """
    home = os.path.expanduser("~")
    red_code, red = _probe_once(box, "ggggg-home")
    red_detail = _detail(red, 4)
    green_code, green = _probe_once(box, "ggggg-clean")
    binary_code, binary = _probe_once(box, "ggggg-binary")
    binary_detail = _detail(binary, 4)
    # The positive control: a fresh copy of `probe` whose clause-4 scan is
    # rebound to the two streams. `_clause_4` looks `_scanned` up on the
    # module, so rebinding the module's attribute is the whole of it — and
    # what it restores is the behavior a piped print-only command met, where a
    # machine fact in the file passed all five clauses.
    copy = _rebound_probe(box, "ggggg-home", "_scanned", _streams_only)
    old_code, old = copy or (-1, "")
    label = ("ggggg  probe clause 4 scans what the command WROTE as well as "
             "what it printed: a command that prints nothing and writes a "
             f"home-shaped path into its file goes red naming `{FILE}`, the "
             "line and the token; the same command writing a clean line is "
             "green, so the wider scan refuses nothing an ordinary subject "
             "writes; a command whose file is not UTF-8 text is NOT scanned "
             "and the row discloses that rather than calling it clean; and a "
             "copy of the module with clause 4's `_scanned` rebound to the "
             "two streams passes the planted file, which is how this row is "
             "known to be able to go red")
    named = (f"run 1 {FILE}:1" in red_detail
             and "an absolute home path" in red_detail
             and _names_path(red_detail, home))
    disclosed = ("not UTF-8 text and was NOT scanned" in binary_detail
                 and "disclosed, not a pass" in binary_detail)
    measured = (f"{ACTUAL}exit {red_code}, clause 4 {_clause(red, 4)}, detail "
                f"{red_detail[:130]!r} (names the file, the line and the home "
                f"path: {named}); the clean file — exit {green_code}, clauses "
                f"{[_clause(green, n) for n in range(1, 6)]}, detail "
                f"{_detail(green, 4)!r}; the binary file — clause 4 "
                f"{_clause(binary, 4)}, exit {binary_code}, detail "
                f"{binary_detail[:150]!r} (disclosed: {disclosed}); the "
                f"streams-only copy exit {old_code}, clause 4 "
                f"{_clause(old, 4)}")
    if copy is None:
        # One absence policy (`core.Layout`'s): an install with no importable
        # `golden_census.probe` cannot have the streams-only control built for
        # it, and a row whose control cannot be built is a disclosed SKIP,
        # never a pass.
        skip(label,
             "golden_census.probe could not be loaded a second time, so the "
             "streams-only control this row is measured against cannot be "
             f"built. Nothing is claimed. What DID run: {measured}")
        return
    check(label,
          _clause(red, 4) == "FAIL" and red_code == 1 and named
          and green_code == 0
          and all(_clause(green, n) == "PASS" for n in range(1, 6))
          and _clause(binary, 4) == "PASS" and disclosed
          and old_code == 0 and _clause(old, 4) == "PASS",
          measured)


def _iiiii_arm(check: CheckRow, skip: SkipRow, box: str) -> None:
    """(iiiii) clause 2 compares the BYTES two runs wrote when there is no
    text to compare.

    The moving script writes the last character of the path it is handed,
    eight times, behind the same two leading bad bytes each run, so the two
    files differ at byte `_IIIII_MOVES_AT` and golden-census's note about
    each — which error decoding it raised, and at which position — is the same
    string. A clause 2 that compared the notes called that a deterministic
    command.
    """
    moves_code, moves = _probe_once(box, "iiiii-moves")
    moves_detail = _detail(moves, 2)
    still_code, still = _probe_once(box, "iiiii-still")
    # The positive control: a fresh copy of `probe` whose clause-2 comparison
    # is rebound to the two notes. `_clause_2` looks `_file_difference` up on
    # the module, so rebinding the module's attribute is the whole of it.
    copy = _rebound_probe(box, "iiiii-moves", "_file_difference", _compare_notes)
    old_code, old = copy or (-1, "")
    label = ("iiiii  probe clause 2 compares the BYTES two runs wrote when "
             "neither file is UTF-8 text: two different binary files whose "
             "first bad byte sits at the same offset go RED and the row names "
             "the offset — the first byte behind the two both begin with — and "
             "both bytes, where golden-census's NOTE about "
             "each file — the error and the position — is one string for "
             "both; the same binary file written twice stays green; and a "
             "copy of the module with clause 2's `_file_difference` rebound "
             "to the comparison of notes passes the two different files, "
             "which is how this row is known to be able to go red")
    offset = re.search(r"they differ at byte (\d+)", moves_detail)
    named = offset is not None and int(offset.group(1)) == _IIIII_MOVES_AT
    measured = (f"{ACTUAL}two different binary files — exit {moves_code}, "
                f"clause 2 {_clause(moves, 2)}, detail {moves_detail[:120]!r} "
                f"(names byte {_IIIII_MOVES_AT}: {named}); the same file twice — exit "
                f"{still_code}, clauses "
                f"{[_clause(still, n) for n in range(1, 6)]}, detail "
                f"{_detail(still, 2)!r}; the notes-only copy exit {old_code}, "
                f"clause 2 {_clause(old, 2)}")
    if copy is None:
        skip(label,
             "golden_census.probe could not be loaded a second time, so the "
             "notes-only control this row is measured against cannot be "
             f"built. Nothing is claimed. What DID run: {measured}")
        return
    check(label,
          _clause(moves, 2) == "FAIL" and moves_code == 1 and named
          and still_code == 0
          and all(_clause(still, n) == "PASS" for n in range(1, 6))
          and old_code == 0 and _clause(old, 2) == "PASS",
          measured)
