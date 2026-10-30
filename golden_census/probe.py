"""`golden-census probe` — the five clauses of `docs/contract.md`, executed.

The contract says what a command must do to plug in. This runs a candidate
twice and reports each clause one row, so the answer to "will this command
work as a subject" is a measurement rather than a reading of the page. It
needs no manifest and no census: a `probe` happens BEFORE either exists,
which is the whole point of it.

What it reuses is already golden-census's: `census.Census.builtin()` and
`census.build_env` for the environment, `core.make_fixed_dir` for the
pinned-width TMPDIR,
`core.launch` for the subprocess, `core.Report` for the block, and
`capture.contraband_patterns` for clause 4's scan — so `probe` and a capture
judge "an absolute path" by ONE list. Clause 4 reads that list over what the
command PRINTED and over what it WROTE, because a capture's own scan reads
every file a subject writes: a `probe` that read fewer texts than the capture
it comes before would pass a command the capture then refuses.
"""

from __future__ import annotations

import os
from typing import Any, NamedTuple

from .capture import contraband_patterns, scan_text
from .census import Census, build_env, describing, own_log
from .core import (
    ACTUAL,
    HITS_PER_STREAM,
    EXIT_MOVED,
    EXIT_OK,
    DIFFERENCE,
    Layout,
    Pending,
    Refusal,
    Report,
    Roots,
    first_difference,
    fold,
    launch,
    lines_of,
    path_forms,
    refuse_holes_in,
    roots_vocabulary,
    workspace,
)

#: The token a command spells where its output path goes.
WRITES = "<WRITES>"

#: The shortest environment value clause 5's canary will look for in a
#: command's output. Short values coincide with ordinary output — `xterm`,
#: `1`, `en_US`, a two-letter language code — and a canary that reported
#: every one of them would be a row nobody could read. Stated here, in the
#: clause-5 row, and in `docs/contract.md`, because a threshold that is only
#: in the code is a rule the reader cannot check the verdict against.
CANARY_MIN = 8

#: What both scanning clauses call the file the command wrote. Clause 4's
#: contraband scan and clause 5's canary read the same text, and a reader met
#: by two spellings of it would read two things.
FILE = "the written file"


class Run(NamedTuple):
    """One of the two runs, with the probe's own paths already folded."""

    exit: int
    out: str
    err: str
    #: The file's text, or None when the run did not write it.
    written: str | None
    #: Its size in bytes on disk, or None when it is not there.
    size: int | None
    #: True when `written` is the FILE's text. False when it is
    #: golden-census's note about a file it could not read as UTF-8 text —
    #: the note is not the file, so nothing that scans text may read it and
    #: call the file clean.
    readable: bool
    #: The file's bytes as they are on disk, unfolded, or None when the run
    #: wrote nothing golden-census could read at all. Clause 2 compares these
    #: when there is no text to compare, because a note about a file is not
    #: the file.
    raw: bytes | None


def banner(command: list[str], census: Census, roots: Roots,
           cwd: str) -> str:
    """The block's title: `PROBE` and the candidate's argv, with every
    absolute directory golden-census knows folded to its token.

    `cwd` is REQUIRED and is the directory `probe` resolved once at its top:
    a default that read the working directory here would be a second reader
    of the one fact this function is given.

    A tool does not print an absolute path it can fold — that rule is what
    the contraband scan enforces on a golden, and there is no reason the
    probe's own banner should be the exception. Two consequences: a probe
    report a reader pastes into a hand-back carries no home directory, and the
    README's `probe` cost row prices the same on every machine, which is the
    requirement `compare`'s COMPARE header meets as well.

    Through `census.own_log`, the same call every other command's header
    lines go through, and therefore through the CENSUS's `path` rows:
    `Census.builtin()` carries `fold` rows, so the banner needs no private
    vocabulary of its own — a default `probe` prints the built-in census's
    placeholders and a `--census` probe prints the ones that census's rows
    name.
    `<PYTHON>` is `own_log`'s too, folded there before the `path` rows for
    every line golden-census prints: a banner and a census `state` row name the
    interpreter for the same reason and there is one answer to it. A relative
    command has nothing to fold and is printed as typed.
    """
    return "PROBE  " + own_log(" ".join(command), census, cwd, roots.fixed)


class Handed(NamedTuple):
    """Every string the PROBE itself handed the command: the cwd it ran the
    command in, the work directory, the fixed-width `TMPDIR`, and each run's
    output path.

    Built ONCE in `probe()` and passed to the two readers. Typed at each
    site instead, "the directories the probe knows" would be three hand-kept
    lists — the banner's, one run's fold pairs, and clause 5's exempt set —
    each adding its own `realpath` forms and each free to drift from the
    others. The banner's list is the census's business (`census.own_log`);
    these two are the probe's own, because `<WRITES>` and `<WORK>` are not
    directories a census `path` row can name and because folding a run's
    OUTPUT through the census would fold the cwd away and blind clause 4 to a
    command that prints it.
    """

    root: str                       # the cwd the command ran in
    work: str
    fixed: str | None
    paths: tuple[str, ...]          # each run's output path

    def fold(self, text: str, path: str) -> str:
        """One run's output with the probe's own directories folded out —
        the probe's VOCABULARY (`<WRITES>`, `<WORK>`, `<TMPDIR>`) over
        `core.fold`'s one algorithm: longest first, both `realpath` forms,
        so the output path inside the work directory is not half-replaced
        and a command that resolved its path is still folded."""
        return fold(text, self.pairs(path))

    def pairs(self, path: str) -> list[tuple[str, str]]:
        """The `(directory, token)` pairs `fold` folds one run's output
        with, `path` being that run's output path — the one list, so the
        tokens clause 4's scan is handed are the ones the fold wrote."""
        pairs = [(path, WRITES),
                 (self.work, roots_vocabulary(None).token("WORK"))]
        if self.fixed:
            pairs.append((self.fixed, "<TMPDIR>"))
        return pairs

    def tokens(self) -> frozenset[str]:
        """Every token `fold` can write into a run's output, for clause 4's
        contraband scan (`capture.scan_text`)."""
        return frozenset(token for path in self.paths
                         for _directory, token in self.pairs(path))

    def strings(self) -> tuple[str, ...]:
        """Clause 5's exempt set: each string in the form the probe passed AND
        in its `realpath` form, because macOS serves /tmp and /private/tmp as
        one directory and a command that resolved its path prints the form it
        was not handed."""
        handed = [self.root, self.work, self.fixed, *self.paths]
        forms = [form for one in handed if one for form in path_forms(one)]
        return tuple(dict.fromkeys(forms))


def _one_run(command: list[str], census: Census, roots: Roots, path: str,
             writes_env: str | None, number: int, handed: Handed,
             cwd: str) -> Run:
    """One run of the candidate, its own paths folded out of what it printed.

    `cwd` is REQUIRED, for the reason `banner`'s is: the directory the
    candidate runs in is one fact, resolved once in `probe`, and a default
    here would be a second reading of it.
    """
    # The window: a `--writes-env` naming a variable the census pins is
    # refused inside `build_env`, and a candidate that will not start inside
    # `launch`, and both are refusals raised after the probe has decided what
    # to run and before the run happens; a candidate whose output is not
    # UTF-8 is refused inside `launch` AFTER the run, and the record handed
    # to it makes that block open `ran:`.
    pending = Pending(command)
    with describing(pending, census, cwd, roots.fixed):
        if writes_env:
            argv = list(command)
            # Through `build_env`'s `extra`, not a dict update: the census owns
            # which variables may be set, and a --writes-env naming a pinned one
            # is refused there rather than silently unpinning the census.
            env = build_env(census, roots, {writes_env: path})
        else:
            argv = [token.replace(WRITES, path) for token in command]
            env = build_env(census, roots)
        pending.ran_as(argv, env)
        proc = launch(argv, f"the probed command (run {number})",
                      cwd=cwd, env=env, pending=pending)
    size = os.path.getsize(path) if os.path.isfile(path) else None
    written: str | None = None
    raw: bytes | None = None
    readable = True
    if size is not None:
        # The BYTES first, then the decode. A file the probe could not read is
        # NOT a file with nothing in it — the contraband scan holds the same
        # rule — and the note below is golden-census's sentence about the
        # file, never the file: `readable` is how clause 2 knows to compare
        # `raw` instead of it, and how clause 4 knows not to scan it and call
        # the file clean.
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError as unreadable:
            readable = False
            written = (f"<unreadable: {type(unreadable).__name__}: "
                       f"{unreadable}>")
        else:
            try:
                written = raw.decode("utf-8")
            except UnicodeDecodeError as undecodable:
                readable = False
                written = (f"<unreadable: {type(undecodable).__name__}: "
                           f"{undecodable}>")
    return Run(proc.returncode, handed.fold(proc.stdout, path),
               handed.fold(proc.stderr, path),
               None if written is None else handed.fold(written, path), size,
               readable, raw)


def _first_difference(one: str, other: str) -> str:
    """The line number and both texts of the first line that differs.

    The RULE — "two runs must be byte-identical; name what moved" — is
    `core.first_difference`, shared with `capture`'s `--twice` and `compare`'s
    `[DIFF]` detail; this is only the LAYOUT, which is eleven spaces and
    `core.DIFFERENCE` characters here and four spaces and `capture.DRIFT`
    there. The final-newline sentence comes from there too: a second copy of
    "the first difference between two texts" is what let the central guard go
    blind to a case this function already handled. `absent` is left None, so a
    run whose output is a prefix of the other's comes back as None and is
    reported as that.
    """
    moved = first_difference(one, other, DIFFERENCE)
    if moved is not None and moved.line is not None:
        return (f"line {moved.line}\n           first:  {moved.first!r}"
                f"\n           second: {moved.second!r}")
    if moved is not None:
        return f"no differing line ({moved.said()})"
    left, right = lines_of(one), lines_of(other)
    if len(left) != len(right):
        return (f"the runs wrote {len(left)} and {len(right)} lines; the "
                "shorter is a prefix of the longer")
    return ("no differing line and no final-newline difference; the two "
            "differ in bytes no line boundary holds")


def _clause_1(report: Report, runs: tuple[Run, Run]) -> None:
    sizes = [run.size for run in runs]
    report.check(
        "1  takes an output path and writes one file there",
        all(size is not None for size in sizes),
        f"{ACTUAL}run 1 wrote {_size(sizes[0])}, run 2 wrote {_size(sizes[1])}",
        next="Make the command create the file at the path it is given. It "
             "arrives as <WRITES> in the argv, or as the variable "
             "--writes-env names; the command never chooses the path.")


def _size(size: int | None) -> str:
    return "nothing" if size is None else f"{size} bytes"


def _byte_difference(one: bytes, other: bytes) -> str:
    """The first OFFSET at which two byte strings differ, and both bytes.

    The layout is `_first_difference`'s, eleven spaces and all, because a
    reader counting the lines of a detail should not have to learn two shapes
    for one answer. What differs is the unit: a file with no line boundaries
    has no line to name, and an offset is what is left.
    """
    # `strict=False`: two files of different lengths are exactly the case the
    # sentence below reports, and a raise here would be a traceback in place
    # of it.
    for offset, (left, right) in enumerate(zip(one, other, strict=False)):
        if left != right:
            return (f"byte {offset}\n           first:  {left:#04x}"
                    f"\n           second: {right:#04x}")
    return (f"byte {min(len(one), len(other))}: the runs wrote {len(one)} and "
            f"{len(other)} bytes; the shorter is a prefix of the longer")


def _file_difference(one: Run, other: Run) -> str | None:
    """Where the two runs' files differ, or None when they do not.

    TEXT against text is compared with the probe's OWN paths folded out of
    each first (`_one_run`, through `Handed.fold`): the two runs are handed
    two different output paths, and a command that writes down the path it was
    given must not read as a command whose output moved. What is left of the
    two texts is what the command chose, and `core.first_difference` names the
    line.

    A file golden-census could not read as UTF-8 text has no lines and nothing
    to fold, so its BYTES are compared as they are and the row names the first
    offset that differs. The note `_one_run` keeps for such a file says only
    which error reading it raised: two different files whose first bad byte
    sits at the same offset carry the SAME note, and two notes that match are
    not two files that match — a determinism clause comparing them reported a
    clean run of a command whose output moved.

    A function, and not four lines inside `_clause_2`, because the arm that
    proves this rebinds this ATTRIBUTE on a fresh copy of the module to the
    comparison of notes and watches two different binary files pass.
    """
    if one.readable and other.readable:
        if one.written == other.written:
            return None
        return (f"they differ at "
                f"{_first_difference(one.written or '', other.written or '')}")
    if one.raw == other.raw:
        return None
    return (f"they differ at "
            f"{_byte_difference(one.raw or b'', other.raw or b'')}")


def _clause_2(report: Report, runs: tuple[Run, Run]) -> None:
    if any(run.written is None for run in runs):
        report.check(
            "2  is deterministic: two runs write byte-identical files",
            False,
            ACTUAL + "not judged — one of the two runs wrote no file, so there "
            "is nothing to compare. Clause 1 above says which.",
            next="Fix clause 1 first; determinism is a statement about two "
                 "files, and this run has fewer than two.")
        return
    moved = _file_difference(runs[0], runs[1])
    report.check(
        "2  is deterministic: two runs write byte-identical files",
        moved is None,
        ACTUAL + "identical" if moved is None else f"{ACTUAL}{moved}",
        next="Find what the differing line or byte reads — the clock, a "
             "random source, the network, or an unordered collection whose "
             "order reaches the output — and make it fixed. The probe already "
             "pins SOURCE_DATE_EPOCH, COLUMNS and TMPDIR for you.")


def _clause_3(report: Report, runs: tuple[Run, Run]) -> None:
    lied = [n for n, run in enumerate(runs, 1)
            if run.exit == 0 and run.size is None]
    report.check(
        "3  exits 0 on success and non-zero otherwise",
        not lied,
        f"{ACTUAL}exit codes {[run.exit for run in runs]}"
        + ("" if not lied
           else f"; run(s) {lied} exited 0 and wrote no file"),
        next="Add the command's own check that the file exists, and exit "
             "non-zero when it does not. A tool that prints SUCCEEDED when "
             "its filter matched nothing is the standing example.")


#: How much of ONE clause-4 problem this row's detail carries. A display
#: width, and this row's own: `core`'s two quoting widths are for a failed
#: child's stderr (`core.QUOTE`) and for a line that is evidence
#: (`core.QUOTE_SHORT`), and a clause-4 problem is neither — it is a sentence
#: this module composed. It coincides with `core.QUOTE_SHORT` today, and
#: spelling it that way would read as a quoting rule this row does not
#: follow.
PROBLEM = 200


def _scanned(run: Run) -> list[tuple[str, str]]:
    """The texts clause 4's contraband scan reads from ONE run: what the
    command printed, and what it wrote.

    The written file is on this list because it is the text a golden commits.
    A home path in it is a golden about this machine as surely as one in
    stdout, and a command handed its output path through a shell redirection
    puts its WHOLE output here, where a scan of the streams alone sees
    nothing. Clause 5's canary already reads all three texts of a run; two
    scans of one run that disagree about which texts they cover leave a hole
    exactly the width of the file.

    A file golden-census could not read as UTF-8 text is not on the list —
    `Run.readable` says so — and `_clause_4` discloses that rather than
    counting an unscanned file as clean.

    A function, and not a tuple built inside `_clause_4`, because the arm that
    proves this half can go red rebinds this ATTRIBUTE on a fresh copy of the
    module to the streams-only list and watches a planted file pass.
    """
    texts = [("stdout", run.out), ("stderr", run.err)]
    if run.written is not None and run.readable:
        texts.append((FILE, run.written))
    return texts


def _clause_4(report: Report, runs: tuple[Run, Run], roots: Roots,
              tokens: frozenset[str]) -> None:
    """Two questions, one clause: did the STREAMS move between the runs, and
    does anything the run produced — either stream or the file — carry a
    machine fact? The contract states both under clause 4, so they are
    reported as one row and the detail says which half broke. `tokens` are
    the ones `Handed.fold` folded the runs with (`Handed.tokens`)."""
    problems: list[str] = []
    for label, one, other in (("stdout", runs[0].out, runs[1].out),
                              ("stderr", runs[0].err, runs[1].err)):
        if one != other:
            problems.append(f"{label} moved between the runs at "
                            f"{_first_difference(one, other)}")
    patterns = contraband_patterns(roots)
    unscanned: list[str] = []
    for number, run in enumerate(runs, 1):
        for stream, text in _scanned(run):
            name = f"run {number} {stream}"
            for where, line, what, token in scan_text(name, text, patterns,
                                                     tokens)[:HITS_PER_STREAM]:
                problems.append(f"{where}:{line} {what}: {token}")
        if run.written is not None and not run.readable:
            unscanned.append(f"run {number}'s file is not UTF-8 text and was "
                             f"NOT scanned ({run.written})")
    report.check(
        "4  prints nothing that moves: stdout and stderr identical across "
        "the runs, and no machine fact in either stream or in the written "
        "file",
        not problems,
        (ACTUAL + "identical and clean" if not problems
         else ACTUAL + "; ".join(p[:PROBLEM] for p in problems))
        + ("" if not unscanned
           else "; " + "; ".join(unscanned) + " — disclosed, not a pass"),
        next="Quiet the command, or make the wrapper swallow what moves. A "
             "machine fact in the WRITTEN FILE is the subject's to stop "
             "writing — or, when the command is piped into <WRITES>, is what "
             "the command printed — and the fix is the program's: a census "
             "`regex` fold is not one here, because `probe` applies no census "
             "row. The probe folds its OWN paths (<WRITES>, <WORK>, "
             "<TMPDIR>) before looking, so every path named above is one the "
             "command found for itself.")


def _handed(value: str, given: tuple[str, ...]) -> bool:
    """True when `value` is CONTAINED IN a string the probe handed the command.

    Such a value is not evidence, and the reason is the same for all of them:
    the probe told the command that string, so a piece of it in the output says
    nothing about where the command got it. Equality is not enough, and that is
    the whole of this rule. An agent's scratch cwd is the standing example:
    a path like `<temp root>/<session id>/scratchpad/…` carries
    `$SESSION_ID` as one path COMPONENT and `$AGENT_TMPDIR` as a
    PREFIX, so under equality clause 5 names variables the command never
    read, on every probe an agent runs from such a directory. `OLDPWD` and
    every other variable stay in the scan, because
    nothing gives those away. The line below is what arm `pp`'s positive
    control swaps for `value in given`, plain membership, to watch the row go
    red.
    """
    return any(value in one for one in given)


def _clause_5(report: Report, runs: tuple[Run, Run], env: dict[str, str],
              writes_env: str | None, given: tuple[str, ...]) -> None:
    """The names actually passed, and the canary.

    A FAIL here is a command that read a variable the built environment never
    gave it: it found the value some other way — an inherited process, a
    dotfile, a hard-coded path — and a golden recorded under it is a golden
    about this machine. `given` is what the probe handed the command; see
    `_handed` for why a value inside any of it is never evidence.
    """
    passed = sorted(env)
    leaks: list[str] = []
    for name, value in sorted(os.environ.items()):
        if name in env or len(value) < CANARY_MIN or _handed(value, given):
            continue
        for number, run in enumerate(runs, 1):
            for label, text in (("stdout", run.out), ("stderr", run.err),
                                (FILE, run.written or "")):
                if value in text:
                    leaks.append(f"run {number} {label} carries the value of "
                                 f"${name}, which the built environment did "
                                 "not pass")
    report.check(
        "5  runs under the census's environment: reads no variable the built "
        "environment did not pass",
        not leaks,
        f"{ACTUAL}{len(passed)} variable(s) passed — {', '.join(passed)}"
        + (f"; --writes-env {writes_env} among them" if writes_env else "")
        + (f"; no variable value of {CANARY_MIN} or more characters appears "
           "in the output (shorter values coincide with ordinary text, and a "
           "value inside a path the probe handed the command is skipped): "
           "clean" if not leaks
           else "; " + "; ".join(dict.fromkeys(leaks))),
        next="Add a census row for the variable named above — a `pin` with "
             "its value, or a `passthrough` entry with the reason — or stop "
             "the command reading it. A variable nobody wrote down is one "
             "the next machine will not have.")


def probe(command: list[str], out: Any, census: Census | None = None,
          writes_env: str | None = None, *, cwd: str | None = None) -> int:
    """Run `command` twice under the contract and report its five clauses.

    0 every clause passed, 1 a clause FAILED, 2 REFUSED. The environment is
    `build_env(census or Census.builtin(), roots)` — ONE dictionary, built by
    the one decider a capture uses, so "the environment `probe` runs under"
    and "the environment a capture runs under" cannot become two rules.

    The fixed-width directory is made BEFORE the environment: `build_env`
    drops a pin whose value resolves to nothing, so a `probe` that built the
    environment first would silently hand the command four variables and a
    clause-5 row that reads honestly and is wrong.

    The working directory is resolved ONCE, here, and handed to everything
    that needs it: the banner's fold, each run's window, each `launch`, and
    the workspace the run's roots are built under. Read at five sites
    instead, it is five readings of one fact, and an arm that wants to plant
    it has nowhere to plant it. `cwd=None` is the current directory, which
    the command line is the only caller of and which is what `probe` has
    always run in; a caller that names one gets its resolved form, because
    every path in the block is compared against the resolved one.
    """
    here = os.path.realpath(cwd) if cwd is not None else os.getcwd()
    if not command:
        raise Refusal(
            "probe was given no command to run.",
            next="Write the candidate after `--`, with <WRITES> where its "
                 "output path goes: `golden-census probe -- mytool --json "
                 "<WRITES>`.")
    # Ahead of the <WRITES> check: a candidate pasted out of a scaffolded
    # runner may have neither, and "fill the hole" is the sentence that gets
    # the reader to a command worth probing.
    refuse_holes_in(" ".join(command), "the probed command")
    if writes_env is None and not any(WRITES in token for token in command):
        # The pipe form is for a command that only prints, and it is not a
        # special case of the manifest: a `run` row records stdout, stderr
        # and the exit code, and `writes` is optional, so the manifest needs
        # the shell wrapper nowhere. It is in the `next:` for every reader of
        # this refusal because the refusal cannot tell a forgotten token from
        # a command with no output path to name.
        raise Refusal(
            f"the probed command names no output path: no argument contains "
            f"{WRITES} and no --writes-env was given. Clause 1 of the "
            "contract is that golden-census chooses the path and the command "
            "writes there, so a command with nowhere to write cannot be "
            "probed at all.",
            next="Put <WRITES> where the command's output path goes (quote "
                 "it, because a shell reads the angle brackets as a "
                 "redirection), or name the variable with --writes-env. A "
                 "command that only prints is probed through a shell that "
                 "writes the file for it: `sh -c 'mytool --json > \"$1\"' _ "
                 "'<WRITES>'`.")

    used = census or Census.builtin()
    # `core.workspace`: the fixed-width directory FIRST — `build_env` drops a
    # pin whose value resolves to nothing, so a probe that built the
    # environment first would silently hand the command four variables and a
    # clause-5 row that reads honestly and is wrong — then the work directory,
    # then both removed in `finally`. A refusal on the way (a command that
    # would not launch, a census pin a --writes-env collides with) must leave
    # no temp directory behind, which is what controls (n) and (t) are about.
    # The outer window, for the refusal `workspace` raises before a run has
    # anything: a temp root too wide for the census's pin. The candidate's argv
    # exists — the reader typed it — and it is printed as typed, with both
    # halves of what does not exist yet said rather than left out.
    typed = Pending(command)
    with describing(typed, used, here, None), \
            workspace(used, "golden-census-probe-", here, out=out) as roots:
        paths = (os.path.join(roots.work, "out-1"),
                 os.path.join(roots.work, "out-2"))
        handed = Handed(root=roots.root, work=roots.work, fixed=roots.fixed,
                        paths=paths)
        runs = (_one_run(command, used, roots, paths[0], writes_env, 1,
                         handed, here),
                _one_run(command, used, roots, paths[1], writes_env, 2,
                         handed, here))
        env = (build_env(used, roots, {writes_env: WRITES}) if writes_env
               else build_env(used, roots))

        report = Report(out, banner(command, used, roots, here))
        _clause_1(report, runs)
        _clause_2(report, runs)
        _clause_3(report, runs)
        _clause_4(report, runs, roots, handed.tokens())
        _clause_5(report, runs, env, writes_env, handed.strings())
        failed = report.finish()
        # The contract by its full path under this layout's `docs`, as a
        # refusal names a format document: a reader opens it from anywhere.
        contract = os.path.join(Layout.detect().data, "docs", "contract.md")
        out.write(f"\n  Clause numbers are those of {contract}.\n")
        return EXIT_MOVED if failed else EXIT_OK
