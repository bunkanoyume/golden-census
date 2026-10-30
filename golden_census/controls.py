"""A census row's control, run: which control each row gets, and the six
controls, each with what it measures and the sentence it prints; and the
block that runs a census's controls in front of a command and turns them
into an exit code.

They are here, above `run`, and not in `census`, which says what a census
is: the `vary` control runs its row with `run.place` and `run.run_row`, and
`run` imports `census`.
"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import os
import shutil
import time
from collections.abc import Callable
from typing import Any, Protocol

from .census import (
    Census,
    RootRewrite,
    Row,
    _control_context,
    _json_parts,
    build_env,
    drift_output,
    fold_regex,
    normalize_paths,
    normalize_text,
)
from .core import (
    ACTUAL,
    EXIT_MOVED,
    EXIT_OK,
    EXIT_REFUSED,
    DISCLOSED,
    PATH_SOURCES,
    Platform,
    Refusal,
    Report,
    Roots,
    WouldNotStart,
    child_fault,
    closed,
    fixed_dir_refusal,
    fixed_dir_room,
    launch,
    make_fixed_dir,
    refusal_text,
    split_row_key,
    temp_base,
    under,
    unpunctuated,
    widest_root,
    with_next,
    workspace,
)
from .manifest import Manifest
from .run import CLONE_LINE, RowRun, place, run_row


def census_controls(census: Census, manifest: Manifest, roots: Roots,
                    check: CheckRow, skip: SkipRow) -> None:
    for row in census.pins:
        shape = (row.control or {}).get("shape")
        if shape == "vary":
            _vary_control(row, census, manifest, check, skip)
        elif shape == "drift":
            _drift_control(row, census, roots, check, skip)
        else:
            _fixed_width_control(row, census, check, skip)
    for row in census.folds:
        if row.kind == "path":
            _path_fold_control(row, census, roots, check, skip)
        elif row.kind == "regex":
            _regex_fold_control(row, census, manifest, roots, check, skip)
        else:
            _json_fold_control(row, census, manifest, roots, check, skip)


def _vary_control(row: Row, census: Census, manifest: Manifest,
                  check: CheckRow, skip: SkipRow) -> None:
    """The row the control names, run three times — twice under the pin and
    once under the control's value — each alone, in a new place holding
    only what preparation put there.

    Each run enters `run.place` for this row alone and runs it with
    `run.run_row`, and the place is removed before the next run has its
    own. The place is a new work directory and, where the census pins
    `<FIXED-WIDTH-DIR:N>`, a new fixed-width temp directory. Preparation is
    what a capture does to the place before its first row, done for this
    row alone: the census's preconditions are checked, the manifest's
    `[files]` are written, and the setup steps the row `needs` are run — and
    no other row's. Two trees are not part of the place and are the same in
    all three runs: the subject's own tree, and the pinned tree of the row's
    input, which is the clone golden-census keeps in the cache directory,
    checked out at the pinned commit and checked clean before each run, as
    it is before a capture, and after each run, as it is after a capture's
    rows: a run that leaves it not clean refuses the command, through
    `run.place`, and is no SKIP — the refusal is raised again here, in
    front of it this control's label and which of the three runs it
    was, because the control holds that fact and the place does not. A
    run that raised is a SKIP below and leaves the place raising, so no
    clone is checked after it. A capture's own log lines, the state
    block and the subject's `version`, are not preparation and are not
    run. What the place prints is dropped but for the lines `clone_input`
    writes — the `clone:` line, and the line beside it that names what git
    ignores in a kept clone — which the row tells under its detail, each
    opened with which of the three runs printed it, so a verdict over a
    clone that holds files that are not the pinned content is read beside
    them. A run that cloned nothing tells nothing.

    The two runs under the pin are expected IDENTICAL and the run under the
    value is expected to DIFFER from them, in the row's exit code or in what
    a capture records of its stdout, its stderr or the file it `writes`,
    after the census's folds, under the surface's own `env`. A run the
    control cannot compare is a disclosed SKIP naming which of the three
    runs it was and why, never a pass: a place that could not be made, or
    whose preparation was refused; an input whose pinned tree could not be
    cloned; a run that would not start; or a run refused before it could be
    compared, a fold's refusal of its text included. A pin whose three runs
    agree is UNPROVEN — a FAIL of the census, because the census claims the
    pin matters. Where the two runs under the pin agree before the census's
    folds as well, the row also says whether the run under the value differs
    from them before the folds. When the two runs under the pin differ, the
    row is a FAIL whose detail opens `the two runs under the pin differ`,
    and it is never UNPROVEN, whatever the run under the value did.
    """
    control = row.control or {}
    key = str(control.get("surface", ""))
    input_name, surface_name = split_row_key(key)
    subject_input = manifest.input_named(input_name)
    surface = manifest.surfaces.get(surface_name)
    if subject_input is None or surface is None or surface.kind != "run":
        raise Refusal(
            f"census {census.path}: the `vary` control of row {row.name!r} "
            f"was handed a manifest with no runnable row {key!r}",
            next="Report this as a golden-census defect, quoting the line "
            "above: `load_manifest` refuses a `vary` control that names no "
            "`run` row of the manifest, so nothing in your files can cause "
            "it.")
    label = _label(row, f"the `vary` control on {key!r}")
    value = str(control.get("value", ""))
    runs: list[RowRun] = []
    told: list[str] = []
    for which, change in (
            ("the first run under the pin", None),
            ("the second run under the pin", None),
            (f"the run under {row.variable}={value!r}",
             {row.variable or "": value})):
        ended = asking = False
        # The place's lines, for its `clone:` lines alone. A directory of
        # the place that stays is not among them: `core.left_behind` notes
        # it for the `workspace` `manifest_controls` holds open around every
        # control, which names it after the block.
        said = io.StringIO()
        try:
            with contextlib.ExitStack() as made:
                try:
                    # The prefix of a capture's place (`capture.py`), so
                    # `<WORK>` is as wide here as in the capture this
                    # control vouches for: a path under it that fits one
                    # fits the other.
                    where = made.enter_context(place(
                        manifest, "golden-census-", said,
                        rows=[(subject_input, surface)], change=change))
                except Refusal as refused:
                    skip(label, f"{which} was refused while its place was "
                         "being prepared, before the surface ran: "
                         f"{_quoted(refused)} {DISCLOSED}")
                    return
                except OSError as blocked:
                    skip(label, _work_fault(f"{which} could not be given a "
                                            "place to run in", blocked))
                    return
                # The place's first clone asks `core.require_cache_dir`, and
                # its refusal is the command's, never a SKIP: `asking` tells
                # it, below, from a refusal of the run.
                asking = True
                unavailable = where.enter(subject_input).unavailable
                asking = False
                if unavailable is not None:
                    reason = unpunctuated(unavailable) or "(no reason given)"
                    skip(label, f"{which} could not be given its input's "
                         f"pinned tree: {closed(reason)} {DISCLOSED}")
                    return
                # A refusal of the run leaves the place RAISING, so
                # `run.place` checks no clone after it and the run's own
                # refusal is the one caught below; `ended` tells it from the
                # place's own, raised on its way out after a run that ended.
                runs.append(run_row(where, subject_input, surface))
                ended = True
        except WouldNotStart as refused:
            # A surface that will not start here means the pin is NOT
            # exercised on this machine: a disclosed SKIP, never a pass.
            # `launch` raises the refusal and `core.child_fault` prints
            # the fault underneath it. One sentence for the three runs:
            # the control holds which run would not start, and nothing
            # about the others.
            fault = closed(with_next(unpunctuated(child_fault(refused)),
                                     refused))
            skip(label, f"{which} would not start: {fault} {DISCLOSED}")
            return
        except Refusal as refused:
            if ended or asking:
                # `run.place`'s refusal on its way out: the clone this run
                # left not clean; or the cache directory's, asked before
                # the clone. The control holds which run it was and says so
                # in front of the sentence; never a SKIP, because the
                # capture behind a SKIP would skip that input at exit 0.
                raise Refusal(f"{label}, {which}: {refused}",
                              next=refused.next) from refused
            # Every other refusal of a run — the run's own, or a fold's
            # of its text: it did not fail to start, so the sentence
            # above would be false of it, and it names the run, because
            # one refused under the varied value alone says nothing of
            # the pinned runs.
            skip(label, f"{which} was refused before this control could "
                 f"compare it: {_quoted(refused)} {DISCLOSED}")
            return
        told += [f"{which}: {line.removeprefix('  ')}"
                 for line in said.getvalue().splitlines()
                 if line.startswith(CLONE_LINE)]
    first, again, other = runs
    steady = (first.exit, first.recorded) == (again.exit, again.recorded)
    moves = (first.exit, first.recorded) != (other.exit, other.recorded)
    # The two facts in words: whether the two runs under the pin agree, and
    # whether the run under the varied value differs from the first of them.
    varied = f"the run with {row.variable}={value!r}"
    if steady:
        measured = (f"{ACTUAL}the two runs under the pin agree, and {varied} "
                    + ("differs from them" if moves
                       else "records the same as they do"))
    else:
        measured = (f"{ACTUAL}the two runs under the pin differ, and {varied} "
                    + ("differs from the first of them" if moves
                       else "records the same as the first of them"))
    if not steady:
        # Whatever the varied run did: a surface that moves under the pin
        # alone cannot show whether the pin matters.
        detail = (f"{measured}. Each run was made in a new place holding "
                  "only what preparation put there. Until the two runs under "
                  "the pin agree, this control cannot say whether the pin "
                  "matters.")
        next_ = ("Find what differs between two runs of this row and pin or "
                 "fold it in the census, or point this control at a surface "
                 "that is steady.")
    elif not moves:
        # What was compared, and nothing else: the written file only where
        # a run recorded one, and never the argv or the counter's counts,
        # which a capture records and this control does not compare.
        compared = ("its stdout, its stderr and the file it writes"
                    if any(run.recorded.written is not None for run in runs)
                    else "its stdout and its stderr")
        detail = (f"{measured}. UNPROVEN: the census says {row.variable} "
                  f"moves {key}, and run alone, in a new place prepared for "
                  "it, it does not change its exit code or what is recorded "
                  f"of {compared} when {row.variable} is varied")
        # Only when the two pinned runs agree unfolded: otherwise an
        # unfolded difference says nothing about the variable — two places
        # have two paths.
        if first.raw == again.raw:
            differs = ("differs from" if first.raw != other.raw
                       else "does not differ from")
            detail += (". Before the census's folds, the run under "
                       f"{row.variable}={value!r} {differs} the two under the "
                       "pin")
        detail += (". An UNPROVEN pin is a FAIL of the census, not of the "
                   "subject: nothing about the subject is claimed by this "
                   "row either way.")
        next_ = ("Demote the row to `state`, or point its control at a "
                 "surface the variable does move.")
    else:
        detail, next_ = measured, ""
    check(_label(row, f"{key} MOVES when {row.variable} is varied from "
                      f"{row.value!r} to {control.get('value')!r}, and is "
                      "identical twice under the pin"),
          steady and moves, detail, next=next_, told=tuple(told))


def _first_line(refused: Refusal) -> str:
    """A refusal's first line, quoted by `unpunctuated`."""
    said = (str(refused).strip().splitlines() or ["(no text)"])[0]
    return unpunctuated(said) or "(no text)"


def _quoted(refused: Refusal) -> str:
    """A refusal as a `vary` SKIP says it: its first line, then its `next:`
    as a second clause (`with_next`) where it has one, and the period that
    ends the SKIP's sentence about it."""
    return closed(with_next(_first_line(refused), refused))


def _work_fault(said: str, blocked: OSError) -> str:
    """The `vary` control's SKIP when a run's place could not be made: never
    a pass, because a run that had no place of its own is not the run a
    capture makes."""
    fault = f"{type(blocked).__name__}: {blocked.strerror or blocked}"
    return f"{said}: {closed(unpunctuated(fault))} {DISCLOSED}"


# ------------------------------------------------------------- the controls
#
# Every pin's and every fold's control, as rows a self-check prints. Each is a
# planted case that proves the disposition matters: the output moves without it
# and holds with it.

class CheckRow(Protocol):
    """One `[PASS]`/`[FAIL]` row of a report.

    A Protocol rather than a `Callable[[str, bool, str], None]`, for one
    reason: `next` and `told` are keyword-only, and `Callable` cannot spell a
    keyword argument at all. A control that wants to tell the reader what to
    do about a FAIL passes `next`; one whose detail already is the whole
    answer does not. `told` is `Report.check`'s: the lines a control's own
    runs printed that the reader reads beside its verdict.
    """

    def __call__(self, label: str, ok: bool, detail: str, *,
                 next: str = "", told: tuple[str, ...] = ()) -> None: ...


SkipRow = Callable[[str, str], None]


def _label(row: Row, text: str) -> str:
    return f"census {row.disposition} {row.name!r}: {text}"


def _drift_control(row: Row, census: Census, roots: Roots, check: CheckRow,
                   skip: SkipRow) -> None:
    """An input that moves with TIME, not with a value golden-census can choose:
    the command run twice `wait` seconds apart WITHOUT the pin must differ, and
    twice WITH it must be identical.

    What is compared is the command's standard output, or the file its
    `output` names: a path under the work directory the command runs in,
    `census.drift_output`'s. Before each of the four runs that file is asked
    where it resolves, links followed, and removed, so each run is judged
    on the file IT wrote; after each run it is asked again, before it is
    read. A file that resolves outside the work directory — through a link
    a run made, or a work directory a run replaced with one — before a run
    or after it, refuses the command, naming the run: the control neither
    removes nor reads a file outside the directory golden-census made.
    """
    control = row.control or {}
    context = _control_context(roots, census.fixtures,
                               census.directory or None)
    place = f"census row {row.name!r}"
    written = [str(a) for a in control.get("command", [])]
    argv = [context.expand(a, place) for a in written]
    #: The command AS THE CENSUS SPELLS IT, for the row's label. The expanded
    #: form is this machine's — `<PYTHON>` becomes an absolute interpreter
    #: path — and a printed row that carried it would move between machines
    #: and put a home directory in a pasted verdict.
    spelling = written[0] if written else "(no command)"
    pinned_env = build_env(census, roots)
    bare_env = dict(pinned_env)
    bare_env.pop(row.variable or "", None)
    # Looked up on the PATH of each environment the command RUNS under —
    # the census's, and the same without this row's variable, `os.defpath`
    # where one passes none, as `subprocess` does — and never on
    # golden-census's own, which the command never sees. A program named
    # by a path — absolute, or opening with a token, since the census
    # loader refuses a relative one — is asked of that path and of no
    # PATH, and the SKIP says so.
    if not argv or any(
            shutil.which(argv[0], path=env.get("PATH", os.defpath)) is None
            for env in (pinned_env, bare_env)):
        missing = (f"nothing to run at {spelling!r}"
                   if argv and os.path.dirname(argv[0])
                   else f"no {spelling!r} on PATH")
        skip(_label(row, "the drift control"),
             f"{missing}: two runs a "
             "second apart cannot be taken on this machine, so the pin's "
             "effect is NOT exercised here. " + DISCLOSED)
        return
    output = control.get("output")
    below = drift_output(str(output)) if output else None
    output_path = os.path.join(roots.work, below) if below else None
    wait = float(control.get("wait", 1.2))

    def outside(when: str) -> None:
        # Asked of `output_path` before a run and again after it: a run may
        # make the link, and the file the next read would follow it to is
        # one golden-census did not make.
        if (os.path.islink(roots.work)
                or not under(str(output_path), roots.work, strict=True)):
            raise Refusal(
                f"{place}: the `drift` control's `output` {str(output)!r} "
                f"resolves outside the work directory, through a link, {when}",
                next="Have the command write its file under the work "
                "directory, with no link on the way out of it, or leave "
                "`output` out and let the control compare what the "
                "command prints.")

    def render(run: int, env: dict[str, str]) -> tuple[int, bytes]:
        # Each run is judged on the file IT wrote: what an earlier run left
        # at `output` goes first, so a run that writes nothing reads as
        # nothing and never as the run before it. Only under the work
        # directory, the one place golden-census removes anything from: a
        # path that resolves anywhere else, before the run or after it, is
        # refused, never read; a path it cannot remove — a directory, say —
        # is read as before.
        if output_path is not None:
            outside(f"before the control's run {run} of 4, so it is neither "
                    "removed nor read")
            with contextlib.suppress(OSError):
                os.remove(output_path)
        # `text=False`: this control compares BYTES, because what a renderer
        # writes is not necessarily text and a decode would be golden-census
        # deciding what "identical" means.
        proc = launch(argv, "the drift control's command", cwd=roots.work,
                      env=env, text=False)
        if output_path is None:
            return proc.returncode, proc.stdout
        outside(f"after the control's run {run} of 4, so it is not read")
        if proc.returncode != 0 or not os.path.isfile(output_path):
            return proc.returncode, b""
        with open(output_path, "rb") as handle:
            return proc.returncode, handle.read()

    pin_first, bare_first = render(1, pinned_env), render(2, bare_env)
    time.sleep(wait)               # longer than the second a clock stamps
    pin_second, bare_second = render(3, pinned_env), render(4, bare_env)
    codes = [r[0] for r in (pin_first, bare_first, pin_second, bare_second)]
    check(_label(row, f"two runs of {spelling} {wait}s apart are "
                      f"byte-identical WITH {row.variable} pinned, and differ "
                      "without it"),
          set(codes) == {0} and pin_first[1] == pin_second[1]
          and bare_first[1] != bare_second[1],
          # The unpinned runs' sizes stay OUT of the detail: what the pin
          # holds still is the clock, and a stamp of a different length —
          # a second that rolled a digit — moves a byte count that nothing
          # about the code decides. The pinned pair's sizes are the same
          # bytes on every run and are evidence; `differ=` is the verdict.
          f"{ACTUAL}exits {codes}, pinned {len(pin_first[1])}B/"
          f"{len(pin_second[1])}B identical={pin_first[1] == pin_second[1]}, "
          f"unpinned differ={bare_first[1] != bare_second[1]}",
          next="Point `control.command` at a command that really does stamp the "
               "time, or widen `wait` past the resolution of the stamp; a "
               "command whose unpinned runs agree does not show the pin "
               "matters, and one whose pinned runs differ reads something "
               "else this census has not named.")


def _fixed_width_control(row: Row, census: Census, check: CheckRow,
                         skip: SkipRow) -> None:
    """The width rule is ARITHMETIC — a root of at most N-2 characters leaves
    a name of N less the root and one separator, a wider one leaves none —
    so it is exercised on CONSTRUCTED widths that need no directory at all.
    Whether the file system takes a name that long is its own limit, which
    `core.make_fixed_dir` meets and this rule does not state. A control that
    could only test the refusal by building a wide directory passes on a short
    temp root and RAISES on every other machine.

    N is the census's `<FIXED-WIDTH-DIR:N>`, so the expected table is computed
    from it rather than written out; what keeps the control honest is that N is
    a census row a reader can see move, and the boundary is asserted separately
    from the table.
    """
    width = census.fixed_width
    if width is None:
        skip(_label(row, "the fixed-width-dir control"),
             "the pin's value is not <FIXED-WIDTH-DIR:N>; nothing to measure.")
        return
    widest = widest_root(width)
    verdicts: list[tuple[int, str]] = []
    for constructed_width in (15, 30, 48, 49, 50, 60):
        constructed = "/" + "b" * (constructed_width - 1)   # never touched on disk
        _norm, room = fixed_dir_room(constructed, width)
        verdicts.append((constructed_width, f"leaf {room}" if room >= 1
                         else "refused"))
    boundary = all((verdict == "refused") == (w > widest)
                   for w, verdict in verdicts)
    # The refusal AS PRINTED, because the advice is its `next:` line: the
    # record owns that sentence, and an assertion on a literal here would pin
    # one platform's wording into a control that runs on both.
    printed = refusal_text(fixed_dir_refusal("/" + "b" * 59, width))
    names_advice = Platform.detect().short_root_advice in printed

    base = temp_base()
    normalized_base, real_room = fixed_dir_room(base, width)
    made_width: int | None = None
    if real_room >= 1:
        made = make_fixed_dir(base, width)
        made_width = len(made)
        os.rmdir(made)
        real = (f"a real directory at the live temp root "
                f"({len(normalized_base)} chars) came out {made_width}")
    else:
        real = (f"the live temp root is {len(normalized_base)} characters — "
                "SKIPPED, see below")
        skip(_label(row, "the real-directory arm"),
             f"this machine's temp root {normalized_base!r} is "
             f"{len(normalized_base)} characters, wider than the {widest} a "
             "capture needs, so the real-directory check did not run; the "
             "checks above still ran, and `capture` would refuse here with "
             "the same message.")
    # The row, on constructed widths that need no directory: a root of at
    # most `widest` characters leaves a name of `width` less the root and one
    # separator, a `width`-character path when the file system takes a name
    # that long, and a wider one is REFUSED, naming the advice this platform's
    # readers are given; plus one real directory when this machine's own root
    # fits. The `actual:` line carries each figure.
    check(_label(row, f"the TMPDIR width rule at {width} (widest root {widest})"),
          boundary and names_advice and made_width in (None, width),
          f"{ACTUAL}pinned at {width} (widest root {widest}), {verdicts}, "
          f"refusal names the platform's advice={names_advice}, {real}",
          next="Report this as a golden-census defect, quoting the row above: "
               "the width rule is golden-census's own arithmetic and nothing "
               "in your files can move it. Capture nothing until it is fixed "
               "— a subject that slices a temp path at a fixed width would "
               "record half a path no fold recognizes.")


def _some_key_in_scope(row: Row, manifest: Manifest) -> str:
    if row.scope:
        return row.scope[0]
    keys = manifest.row_keys()
    return keys[0] if keys else "control/sample"


def _key_outside_scope(row: Row, manifest: Manifest) -> str | None:
    return None if row.scope is None else next(
        (key for key in manifest.row_keys() if key not in row.scope), None)


def _one_byte_outside(row: Row, sample: str) -> str | None:
    """`sample` with one character changed OUTSIDE the volatile group.

    Preference order: a character outside the match altogether, then one after
    the volatile group, then one before it. None when the whole sample IS the
    volatile token and there is nothing to move.
    """
    regex = row.regex
    if regex is None:
        return None
    match = regex.search(sample)
    if match is None:
        return None
    v_start, v_end = match.span("volatile")
    candidates = (list(range(match.end(), len(sample)))
                  + list(range(0, match.start()))
                  + list(range(v_end, match.end()))
                  + list(range(match.start(), v_start)))
    for index in candidates:
        char = sample[index]
        if char.isalnum():
            other = "9" if char.isalpha() else "z"
            return sample[:index] + other + sample[index + 1:]
    return None


def _regex_fold_control(row: Row, census: Census, manifest: Manifest,
                        roots: Roots, check: CheckRow, skip: SkipRow) -> None:
    """One row per regex fold.

    the row's OWN pattern replaces something in the sample and in the moved
    text, alone — a second fold that folds the same token does not count for
    it; sample vs moved NORMALIZED are identical (the fold fired); the same pair
    UNNORMALIZED differ (the honesty arm — the fold was needed, and the
    comparison is not simply blind); one byte changed outside the volatile
    group is still REPORTED (the fold replaces the token, never the line); and
    for a scoped fold the same moved token on a surface OUTSIDE the scope is
    REPORTED.
    """
    control = row.control or {}
    sample, moved = str(control["sample"]), str(control["moved"])
    key = _some_key_in_scope(row, manifest)
    folded_same = (normalize_text(sample, census, roots, key)
                   == normalize_text(moved, census, roots, key))
    honest = sample != moved
    unmoved = [text for text in (sample, moved) if fold_regex(row, text) == text]
    changed = _one_byte_outside(row, sample)
    if changed is None:
        reported = True
        byte_note = "no character outside the volatile group to move"
        skip(_label(row, "the one-byte arm"),
             "the whole sample is the volatile token, so there is no character "
             "outside the group to change. The other arms ran. Nothing is "
             "claimed for this one.")
    else:
        reported = (normalize_text(changed, census, roots, key)
                    != normalize_text(sample, census, roots, key))
        byte_note = f"one byte outside the group reported={reported}"
    outside_key = _key_outside_scope(row, manifest)
    if outside_key is None:
        narrow = True
        scope_note = ("scope is * — no surface outside it"
                      if row.scope is None else
                      "every row of this manifest is in the fold's scope")
    else:
        narrow = (normalize_text(sample, census, roots, outside_key)
                  != normalize_text(moved, census, roots, outside_key))
        scope_note = f"the moved token on {outside_key} reported={narrow}"
    check(_label(row, f"the fold fires on {key} and folds the TOKEN, not the "
                      "line: sample and moved normalize IDENTICAL, the same "
                      "pair unnormalized DIFFERS, a byte outside the volatile "
                      "group is still REPORTED"
                      + ("" if outside_key is None
                         else f", and the moved token on {outside_key} — "
                              "outside the scope — is REPORTED")),
          folded_same and honest and reported and narrow and not unmoved,
          f"{ACTUAL}normalized identical={folded_same}, unnormalized "
          f"differs={honest}, {byte_note}, {scope_note}"
          + (f", this row's own pattern {row.pattern!r} replaced nothing in "
             f"{' or '.join(map(repr, unmoved))}: whatever else the census "
             "folds, this row folds nothing" if unmoved else ""),
          next="Read the detail: a fold that did not fire needs a `pattern` "
               "that matches this row's `control.sample`, and one that folded "
               "a byte outside the volatile group needs a narrower "
               "(?P<volatile>...). Until it is one or the other, this fold is "
               "either doing nothing or blinding the comparator.")


def _first_unfolded_leaf(document: Any, row: Row,
                         trail: tuple[str | int, ...] = ()
                         ) -> tuple[tuple[str | int, ...], Any] | None:
    """The trail — dict keys and list indexes, in order — to a scalar the
    fold does NOT touch, and its value, for the one-byte arm.

    A trail and not a dotted string: a string has to be parsed again to set
    the leaf, and `items[0]` or a key holding a `.` does not parse back.
    "Inside a folded path" is asked only of a trail with no index in it,
    joined as a `json-fields` path is written — a path names dict keys only
    (`_walk_to`), so a trail through a list is never inside one.

    `document` is `Any` because it is a parsed JSON document: a dict, a
    list, or a scalar at a leaf.
    """
    if isinstance(document, dict):
        keys_only = all(isinstance(step, str) for step in trail)
        for key, value in document.items():
            here = (*trail, key)
            if (keys_only and ".".join(str(step) for step in trail) in row.paths
                    and key in row.fields):
                continue
            if isinstance(value, str | int) and not isinstance(value, bool):
                return here, value
            found = _first_unfolded_leaf(value, row, here)
            if found is not None:
                return found
    elif isinstance(document, list):
        for index, item in enumerate(document):
            found = _first_unfolded_leaf(item, row, (*trail, index))
            if found is not None:
                return found
    return None


def _set_leaf(document: Any, trail: tuple[str | int, ...], value: Any) -> None:
    """Set the leaf at `trail` to `value`, stepping through dict keys and
    list indexes alike. `document` and `value` are `Any`: a parsed JSON
    document and a scalar of it."""
    node = document
    for step in trail[:-1]:
        node = node[step]
    node[trail[-1]] = value


def _trail_text(trail: tuple[str | int, ...]) -> str:
    """A trail as a reader types it, the one place a trail is printed: keys
    joined by `.`, an index as `[N]` with no dot before it — `items[0].n`,
    `[0].n` — so a trail with no index reads as the `json-fields` path that
    would name it. A key is printed as it is: one that holds a `.` reads like
    two keys, and an empty key prints as nothing (`a..n`, `.n`)."""
    text = ""
    for position, step in enumerate(trail):
        if isinstance(step, int):
            text += f"[{step}]"
        else:
            text += f".{step}" if position else step
    return text


def _json_fold_control(row: Row, census: Census, manifest: Manifest,
                       roots: Roots, check: CheckRow, skip: SkipRow) -> None:
    control = row.control or {}
    if not census.fixtures:
        raise Refusal(
            f"census {census.path}: the json-fields control of row "
            f"{row.name!r} was handed a census with no [fixtures] dir",
            next="Report this as a golden-census defect, quoting the line "
            "above: `load_census` refuses a json-fields row in a census with "
            "no [fixtures] dir, so nothing in your files can cause it.")
    # `load_census` read both files already, and refuses either one that
    # will not read.
    texts = []
    for name in ("sample", "moved"):
        with open(os.path.join(census.fixtures, str(control[name])),
                  encoding="utf-8") as handle:
            texts.append(handle.read())
    sample, moved = texts

    def measured(raw: str) -> str:
        # The folded BODY and no tail, on every side: the claim is about the
        # json-fields fold and the path folds, and the tail — recorded as
        # written — would decide the comparison on its own wherever two texts
        # end differently, as the re-serialized `changed` below and a sample
        # ending in a newline do. No regex fold either: one folding the planted
        # change would turn this row red for a reason that is not the row's.
        return normalize_paths(_json_parts(raw, census)[0], census, roots)

    try:
        folded_same = measured(sample) == measured(moved)
    except Refusal as refused:
        check(_label(row, "the json-fields control"), False,
              f"{ACTUAL}REFUSED normalizing the fixtures: "
              f"{with_next(str(refused), refused)}")
        return
    honest = sample != moved
    document = json.loads(sample)
    leaf = _first_unfolded_leaf(document, row)
    if leaf is None:
        reported = True
        note = "no scalar outside the folded fields to move"
        skip(_label(row, "the one-field arm"),
             "the sample document has no scalar outside the folded fields. The "
             "other arms ran. Nothing is claimed for this one.")
    else:
        trail, value = leaf
        _set_leaf(document, trail,
                  value + 1 if isinstance(value, int) else str(value) + "-x")
        changed = json.dumps(document, indent=row.indent,
                             ensure_ascii=row.ensure_ascii)
        reported = measured(changed) != measured(sample)
        note = f"a change at {_trail_text(trail)} reported={reported}"
    check(_label(row, "the JSON fold blanks the named fields and NOTHING else: "
                      "sample and moved normalize IDENTICAL, unnormalized they "
                      "DIFFER, and a change outside the folded fields is "
                      "REPORTED"),
          folded_same and honest and reported,
          f"{ACTUAL}normalized identical={folded_same}, unnormalized "
          f"differs={honest}, {note}",
          next="Read the detail: name in `fields` every key that really moves "
               "under each of this row's `paths`, and no key that does not. A "
               "field list that is short leaves the comparator firing on the "
               "machine; one that is long blanks evidence.")


def _path_fold_control(row: Row, census: Census, roots: Roots, check: CheckRow,
                       skip: SkipRow) -> None:
    """A path fold's own control: the directory golden-census made is folded to
    the placeholder, and an absolute path it did NOT make survives — a fold
    that swallowed every path would leave a golden nobody could read.

    The directory is the one `roots` holds for the row's source. Where it
    holds none — the work directory this control is given is made by
    `manifest_controls` with no clone and no fixed-width directory — a
    stand-in directory named for the source is made under that work
    directory and folded instead, and goes when the work directory goes.
    The fold is arithmetic on a path golden-census made, and which path it
    is does not matter; what the command's own runs print is the capture's
    to fold, not this control's. `skip` is the list's call shape; this
    control never skips.
    """
    value = roots.by_source(row.source or "")
    if not value:
        value = os.path.join(roots.work, f"stand-in-{row.source}")
        os.makedirs(value, exist_ok=True)
        field = dict(zip(PATH_SOURCES, Roots._fields,
                         strict=True))[row.source or ""]
        roots = roots._replace(**{field: value})
    stranger = "/nowhere/that/golden-census/made"
    sample = f"scanned {value}/App and {stranger}/App\n"
    label = _label(row, f"the {row.source} directory folds to "
                        f"{row.placeholder} and a path golden-census did not "
                        "make survives")
    try:
        folded = normalize_text(sample, census, roots, "control/path")
    except RootRewrite as refused:
        # The text is golden-census's own sample, so the fault is reported
        # as this control's red row, naming the reader's fold — never as a
        # refusal naming `control/path`, a row the reader did not write.
        check(label, False,
              f"{ACTUAL}your fold {refused.fold!r} rewrites the subject root "
              f"in golden-census's sample text: it replaces "
              f"{refused.replaced!r}",
              next=refused.next)
        return
    check(label,
          (row.placeholder or "") in folded and value not in folded
          and stranger in folded,
          f"{ACTUAL}{folded.strip()!r}",
          next="Check your census's regex folds first: one whose pattern "
               "matches this directory's path, or the other path on the "
               "detail line above, can make this row red — scope it to the "
               "rows that need it. If none does, report this as a "
               "golden-census defect, quoting the row above: which "
               "directories golden-census made is its own to know, and no key "
               "of your census decides it.")


# ------------------------------------------------------------- the block
#
# Two entry points onto one list of controls, and the difference between them
# is WHO ASKED. `census_check` is the controls of the reader's own census,
# which run in front of the commands that turn their subject into a golden or
# a verdict; `selfcheck.selfcheck` is golden-census's own arms, which a
# reader asks for by name. `block` is everything the two share.

#: A self-check's control set. Named because `selfcheck` accepts one: control
#: (s) hands it a set that raises, which is the only way to exercise its catch
#: from inside a control without swapping a global.
Controls = Callable[[CheckRow, SkipRow], None]


def manifest_controls(check: CheckRow, skip: SkipRow,
                      manifest: Manifest, out: Any) -> None:
    """The census's own rows: every pin's and every fold's control, under a
    work directory `core.workspace` makes and removes, naming on `out` what
    of it stayed."""
    with workspace(None, "golden-census-census-",
                   manifest.subject.root, out=out) as roots:
        census_controls(manifest.census, manifest, roots, check, skip)


def block(out: Any, banner: str, quiet: bool, controls: Controls) -> int:
    """Run a set of controls, print it as one block, and return a process exit
    code.

    0 every control passed; 1 a control failed or raised; 2 golden-census
    REFUSED — a precondition it cannot meet. The distinction is the point: a
    failed control is a statement about the code, a refusal is a statement
    about the run, and only the second earns the word REFUSED.

    Never raises anything a caller has to handle: an exception out of a control
    becomes a FAIL row, a `Refusal` becomes the exit-2 line under the rows, and
    the rows collected before either still print.

    ONE body under both blocks, because they differ in WHICH controls run and
    in nothing else: a second copy would be a second way to print a red row and
    a second way to turn one into an exit code.
    """
    report = Report(out, banner, quiet)
    refusal: Refusal | None = None
    try:
        report.guard(lambda: controls(report.check, report.skip))
    except Refusal as refused:
        refusal = refused

    failed = report.finish()
    if refusal is not None:
        out.write("\n" + refusal_text(refusal, "  ") + "\n  The controls after "
                  "that one did not run; the rows above are every control "
                  "that did.\n")
        return EXIT_REFUSED
    return EXIT_MOVED if failed else EXIT_OK


def census_check(out: Any, manifest: Manifest, quiet: bool = True) -> int:
    """The controls of ONE census — every pin's and every fold's own row — and
    none of golden-census's own arms.

    What runs in FRONT of a command the reader typed. These rows are about the
    reader's own subject and the environment around it: whether each pin still
    moves the surface it names, whether each fold still folds what it claims.
    A census whose pin no longer matters makes a golden that records the wrong
    thing, so the rows are worth their second to every command that turns a
    subject into a golden or a verdict, and a red one stops it.

    The list comes from `manifest_controls`, which `selfcheck._run_controls`
    also calls: ONE owner, so a census row cannot be exercised by one entry
    point and missed by the other.

    A work directory of the controls' that stayed is named after the block,
    beside its tally: the line is held until the block is printed.
    """
    left = io.StringIO()
    code = block(out, "CENSUS CONTROLS", quiet,
                 functools.partial(manifest_controls, manifest=manifest,
                                   out=left))
    out.write(left.getvalue())
    return code
