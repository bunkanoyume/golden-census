"""The seven groups over one subject — what `--selftest` runs.

What it holds: `selftest` itself, the seven group
functions — the controls, a capture, a comparison and its planted difference,
the mutants, the two documents against the parser, the first line every
command opens with, and every shipped template scaffolded — and the helpers
only they use.

ONE subject, and it is the one that TRAVELS: the stub lives inside the
package, so this command measures the same thing in a checkout and in a
wheel. `examples/python-function/` is a worked example for a reader to copy;
a user may delete it and no command, no check and no document here notices.

`--selfcheck` asks whether a guard can fire; this asks whether the program
still does what it says. That is why the split runs this way round: this
module imports `selfcheck` for the CONTROLS group, the arms import nothing
from here, and `proof.py` sits under both.
"""

from __future__ import annotations

import io
import os
import pathlib
import re
import shutil
import tempfile
from typing import Any

from . import __version__
from .capture import capture, read_capture
from .cli import main
from .compare import compare
from .core import (
    ACTUAL,
    AGENT_SET,
    EXIT_MOVED,
    EXIT_OK,
    EXIT_REFUSED,
    DIFFERENCE,
    HUMAN_SET,
    IMPORT_NAME,
    PROG,
    SKILL_DIR,
    Layout,
    Refusal,
    Report,
    not_removed,
    read_text,
    refusal_text,
    remove_tree,
    temp_base,
    with_next,
)
from .docs import (
    _run as docs_run,
    MEMBER_JOIN,
    PRICED,
    Members,
    command_surface,
    measure,
    exit_sentence,
    link_problems,
    live_parity,
    procedure_halves,
    procedure_problems,
    procedure_steps,
    set_sentence_problems,
    shipped_readmes,
    version_problems,
    version_set_problems,
    version_sites,
)
from .manifest import Manifest, load_manifest
from .mutants import load_mutants, run_mutants
from .proof import _NO_VERDICT, _box, _one_line
from .checks_base import prepare_fixture
from .checks_templates import template_verdict
from .checks_width import _wide_root_refusal
from .selfcheck import selfcheck
from .templates import (
    TEMPLATES_ABSENT,
    shipped_templates,
    templates_dir,
    templates_verdict,
)

# --------------------------------------------------------------- the selftest
#
# `--selfcheck` proves golden-census's guards can go red. `--selftest` proves the
# whole app works, on a SUBJECT: the stub under `fixture/`, its manifest, its
# census with a row of every shape, its committed golden and its two mutants.
# The two are different questions — can this check fire, and does this program
# still do what it says — and only the second needs a fixture.
#
# Nothing here writes into golden-census's own repository: the fixture is
# copied into a temporary directory and the copy's subject is put in a git
# repository of its own, so the census's `git-checkout` precondition holds
# without golden-census committing anything anywhere.


def _last_line(text: str) -> str:
    """A command log's last line for a row's detail, or the sentence saying
    there was no log.

    The guard has to make the expression TOTAL, and `if text` does not: a log
    of nothing but whitespace is truthy, and `text.strip().splitlines()[-1]` on
    it raises `IndexError`.
    """
    stripped = text.strip()
    return (_one_line(stripped.splitlines()[-1], DIFFERENCE) if stripped
            else "no log")


def _capture_group(manifest: Manifest, box: str,
                   out: Any) -> tuple[int, str]:
    """`capture --twice` of the bundled stub. Returns (failures, the capture
    directory)."""
    group = Report(out, "CAPTURE")
    into = os.path.join(box, "capture")

    def body() -> None:
        # A `Refusal` is caught and reported AS THE ROW rather than let out into
        # the group's `guard`: a subject that will not run is the very thing
        # this row measures, and a group that aborted on it would report
        # nothing at all.
        log = io.StringIO()
        code = -1
        blocked: Refusal | None = None
        try:
            code = capture(manifest, into, log, (), False, True)
        except Refusal as refusal:
            blocked = refusal
        text = log.getvalue()
        ok = (code == 0 and "byte-identical" in text and "0 hit(s)" in text
              and "capture complete" in text)
        group.check(
            "`capture --twice` records every row of the bundled manifest into "
            "a temporary directory and the two captures are byte-identical: a "
            "subject whose surfaces move between two runs of one tree has a "
            "census row nobody has written yet", ok,
            f"{ACTUAL}exit {code}, "
            + (with_next(f"REFUSED {_one_line(str(blocked), 160)!r}", blocked)
               if blocked is not None
               # The agreement line, which is what this row is about;
               # `capture complete` comes after it on a success.
               else _one_line(text, DIFFERENCE, needles=("byte-identical",),
                              empty=_last_line(text))))

    group.guard(body)
    return group.finish(), into


#: What a comparison's log lines have to carry for a row's detail to be
#: EVIDENCE: the file counts, the verdict, and — when the verdict is a red
#: one — the `[DIFF]` rows and the count of them. Filtering for the first two
#: alone, a red row says `5 golden files, 5 new files` and names nothing that
#: moved. One tuple, so every row quotes the same four things.
_COMPARE_NEEDLES = ("golden files", "IDENTICAL", "[DIFF]", "differing row(s)")


def _compare_group(manifest: Manifest, fixture: str, capture_dir: str,
                   box: str, out: Any) -> int:
    """The stub's committed golden against the capture just taken, and the
    comparator's own planted difference."""
    group = Report(out, "COMPARE")
    golden = os.path.join(fixture, "subject", "golden")

    def body() -> None:
        log = io.StringIO()
        code = compare(manifest, golden, capture_dir, None, log)
        text = log.getvalue()
        group.check("the committed golden and a fresh capture of the bundled "
                    "stub are IDENTICAL", code == 0 and "IDENTICAL" in text,
                    f"{ACTUAL}exit {code}, "
                    + _one_line(text, 300, needles=_COMPARE_NEEDLES,
                                empty=_NO_VERDICT))

        planted = os.path.join(box, "planted")
        shutil.copytree(capture_dir, planted)
        target = os.path.join(planted, "_subject", "report.out")
        before = read_capture(planted, "the planted capture").get(
            "_subject/report.out", "")
        after = before.replace("stub report", "stub reporX", 1)
        pathlib.Path(target).write_text(after, encoding="utf-8", newline="\n")
        log = io.StringIO()
        code = compare(manifest, golden, planted, None, log)
        text = log.getvalue()
        group.check(
            "a copy of that capture with ONE byte changed is reported as "
            "exactly one differing row, naming it — a comparator nobody has "
            "seen go red has compared nothing",
            code == 1 and before != after
            and "[DIFF]    _subject/report.out (changed)" in text
            and "1 differing row(s)" in text,
            f"{ACTUAL}exit {code}, one byte planted={before != after}, "
            + _one_line(text, 300, needles=_COMPARE_NEEDLES,
                        empty=_NO_VERDICT))

    group.guard(body)
    return group.finish()


def _mutants_group(manifest: Manifest, fixture: str, out: Any) -> int:
    group = Report(out, "MUTANTS")

    def body() -> None:
        log = io.StringIO()
        mutants = load_mutants(os.path.join(fixture, "mutants.toml"))
        code = run_mutants(manifest, mutants, log, ())
        text = log.getvalue()
        group.check(
            "both bundled mutants are caught, each by a DIFFERENT check: "
            "the row count every surface carries by the comparator, the "
            "constant no surface carries by the consumer's own command check "
            "— and the null mutant, the unmutated copy, is SILENT on both",
            code == 0 and "2/2 mutants caught" in text
            and "null mutant: comparator SILENT, probe SILENT" in text
            and re.search(
                r"the row count every surface carries\s+FIRED\s+SILENT",
                text) is not None
            and re.search(r"a constant no recorded surface carries\s+SILENT\s+"
                          r"FIRED", text) is not None,
            f"{ACTUAL}exit {code}, "
            + _one_line(text, 300,
                        needles=("null mutant:", "FIRED", "mutants caught"),
                        empty=_NO_VERDICT))

    group.guard(body)
    return group.finish()


def _version_sync_row(group: Report, human: Members | None,
                      agent: Members | None) -> None:
    """The version is a SYNC key with one owner: every document site that
    spells it spells `golden_census.__version__`.

    Checked by hand — a `git grep` at a gate — the sync fails silently:
    `__version__` bumped with the prose sites left behind leaves `--selftest`
    green at exit 0, printing the NEW number as its own last line, and only a
    consumer copy run by hand goes red. This row is what holds the sites
    together.

    Three places spell it: the human set, the agent set (the skill's version
    lock) and the worked example's README. Each is disclosed by name when it
    is not in the layout — a package run with no documents beside or under it —
    and a set or the example that IS there and spells no version at all is a
    red row, never a pass.
    """
    label = ("every site in the human set, the agent set and the worked "
             "example's README that spells golden-census's version spells "
             f"`{IMPORT_NAME}.__version__` — its one owner — and each of "
             "those documents spells it at least once: the version is a sync "
             "key, and a document left behind by a bump is drift no command "
             "goes red on. The control is each site of those documents moved in "
             "turn, alone, in memory, each named by its file and line")
    layout = Layout.detect()
    example = (None if layout.example is None
               else os.path.join(layout.example, "README.md"))
    halves: list[tuple[str, str]] = []
    problems: list[str] = []
    absent: list[str] = []
    for name, paths, members in (("the human set", HUMAN_SET, human),
                                 ("the agent set", AGENT_SET, agent)):
        if members is None:
            absent.extend(paths)
        else:
            halves += members
            problems += version_set_problems(members, name, __version__)
    name = "examples/python-function/README.md"
    text = read_text(example) if example else None
    if text is None:
        absent.append(name)
    else:
        halves.append((name, text))
        problems += version_problems(text, name, __version__)
    if not halves:
        group.skip(label, layout.absent(", ".join(absent))
                          + " Nothing was read and nothing is claimed.")
        return
    sites = [site for name, text in halves
             for site in version_sites(text, name)]
    planted, missed = _version_control(halves)
    caught = bool(planted) and not missed
    group.check(
        label, not problems and caught,
        f"{ACTUAL}{IMPORT_NAME}.__version__ = {__version__!r}; {len(sites)} site(s) "
        + ", ".join(f"{where} -> {found}" for where, found in sites)
        + (f"; not beside the package: {', '.join(absent)}" if absent else "")
        + ("; every site in step" if not problems
           else " | " + " | ".join(problems))
        + f"; the control, each of {len(planted)} site(s) moved alone in a "
          f"copy held in memory, is named={caught}"
        + (f" (not named: {', '.join(missed)})" if missed else ""),
        next=f"Move every site named above to the value {IMPORT_NAME}"
             "/__init__.py "
             "holds, in the SAME commit as the bump — the number is a sync "
             "key, so a site left behind is the whole defect.")


def _version_control(halves: list[tuple[str, str]]
                     ) -> tuple[list[str], list[str]]:
    """`(every site planted, those the check did not name exactly)`: each
    `(name, text)` of `halves` with each of its version sites in turn moved
    to a version that is not `__version__`, alone, in memory, put to
    `version_problems` — the row's positive control, which the live
    documents cannot be while they are in step. Every site and not the
    first: a check that read only some of a document's sites passes a
    control that moves only those."""
    planted: list[str] = []
    missed: list[str] = []
    for name, text in halves:
        for where, spelled in version_sites(text, name):
            number = int(where.rsplit(":", 1)[1])
            lines = text.splitlines()
            lines[number - 1] = lines[number - 1].replace(
                spelled, __version__ + "9", 1)
            named = [problem.split(" spells ")[0] for problem
                     in version_problems("\n".join(lines), name, __version__)]
            planted.append(where)
            if named != [where]:
                missed.append(where)
    return planted, missed


def _procedure_row(group: Report, human: Members,
                   agent: Members | None) -> None:
    """The adopter's procedure, stated once and told twice.

    Both halves or neither: a count and a set of names compared against
    nothing is not a check, so an install carrying no skill files a disclosed
    SKIP rather than a row about the README alone. Each set tells it in ONE
    member, and a second member carrying it is a problem.
    """
    label = ("the adopter's procedure is ONE procedure: the human set and the "
             "agent set state the same number of steps, numbered the same, "
             "each named by the same leading bold phrase — the human reading "
             "and the agent reading are the same walk, and a step in one and "
             "not the other is a step somebody skips")
    if agent is None:
        group.skip(label, Layout.detect().absent(f"{SKILL_DIR}/SKILL.md")
                          + " There is one procedure to read and nothing to "
                          "read it against; nothing is claimed.")
        return
    halves, problems = procedure_halves([("the human set", human),
                                         ("the agent set", agent)])
    problems = procedure_problems(halves) + problems
    counts = [(name, len(procedure_steps(text))) for name, text in halves]
    group.check(
        label, not problems,
        ACTUAL + ", ".join(f"{name} {count} step(s)"
                               for name, count in counts)
        + ("; the same steps, the same names" if not problems
           else " | " + " | ".join(problems)),
        next="Both documents' `Plugging a project in, in order` sections are "
             "one procedure written twice: the step's NAME is the bold phrase "
             "it opens with, and the two have to be the same word for word. "
             "The prose under it is each audience's own.")


def _docs_group(out: Any) -> int:
    """The two documents against the parser, and the version they and the
    worked example's README share with `golden_census.__version__`."""
    group = Report(out, "DOCS PARITY")
    surface = command_surface()
    human, agent = live_parity(surface, group.check, group.skip)
    _version_sync_row(group, human, agent)
    if human is not None:
        # The two one-owner facts, live. The README's absence is already a
        # disclosed SKIP above, so these run only when there is a document to
        # read; the skill's absence is disclosed the same way, and the
        # exit-sentence row says which halves it read.
        sentence = exit_sentence()
        halves = [("the human set", human)]
        if agent is not None:
            halves.append(("the agent set", agent))
        owned = [problem for name, members in halves
                 for problem in set_sentence_problems(members, name, sentence)]
        group.check(
            "the exit-code sentence of `cli`'s docstring — its one owner — "
            "stands verbatim in "
            + " and in ".join(name for name, _members in halves),
            not owned,
            f"{ACTUAL}owner {sentence!r}; "
            + ("carried by both" if not owned and len(halves) == 2
               else "carried" if not owned else " | ".join(owned)))
        _procedure_row(group, human, agent)
        layout = Layout.detect()
        present, missing = shipped_readmes(layout.data)
        if present:
            links = link_problems(
                MEMBER_JOIN.join(text for _path, text in human),
                "the human set", present)
            group.check(
                "every `templates/*/README.md` and `examples/*/README.md` "
                "beside the package is a link target in the human set, and "
                "the directories with no README are named here rather than "
                "failed",
                not links,
                f"{ACTUAL}{len(present)} README(s) — {', '.join(present)}; "
                f"without a README: {', '.join(missing) or 'none'}; "
                + ("every one linked" if not links else " | ".join(links)))
        else:
            group.skip("every shipped template and example README is linked "
                       "from the README",
                       layout.absent("templates/*/README.md and "
                                     "examples/*/README.md")
                       + " Nothing was checked and nothing is claimed.")
    return group.finish()


def _first_line_group(fixture: str, box: str, out: Any) -> int:
    """(FIRST LINE) every command that LAUNCHES anything opens with the run's
    process-group line, and the one that launches nothing does not.

    Arm `xxx` says this of one real `probe` and proves the decision has a
    single owner in `cli.main`; this says it of every command there is. The
    two together are the claim: one decider, and a run of each to see it.

    A GROUP and not a self-check arm, and the reason is the reader's time:
    the self-check runs in front of every command a person types, and running
    twelve commands there would cost each of them three seconds to re-prove
    something about golden-census rather than about their subject. Here it is
    paid once, by the command that exists to measure golden-census.

    `--version` is the exception the rule needs. It launches nothing, opens no
    group, and a run of it that printed a kill command would be naming a group
    with no members — so it is asserted to be WITHOUT the line, never skipped.
    """
    group = Report(out, "FIRST LINE")

    def body() -> None:
        blocks: dict[str, str] = {}
        measure(PRICED, fixture, box, blocks, selfcheck=selfcheck)
        opens: list[str] = []
        for one in PRICED:
            first = (blocks.get(one.key, "").splitlines() or [""])[0]
            wants = "--version" not in one.key
            has = first.startswith("process group ") and "kill -- -" in first
            if has != wants:
                opens.append(f"{one.key}: {first[:60]!r}")
        group.check(
            "every golden-census command that launches anything opens with "
            "the line naming the run's process group and the command that "
            "kills it — each of them run here, not one of them and a rule — "
            "and `--version`, which launches nothing, opens without it",
            len(blocks) == len(PRICED) and not opens,
            f"{ACTUAL}{len(blocks)} of {len(PRICED)} command(s) run; "
            + ("every one that launches anything opened with `process group "
               "N — … kill -- -N` and --version did not"
               if not opens else f"wrong at {opens}"),
            next="`cli.main` opens the group once, above the dispatch, for "
                 "every form but `--version` and `--help`; arm xxx is the "
                 "walk that says it is decided in one place.")

    group.guard(body)
    return group.finish()


def _templates_group(out: Any) -> int:
    """Every shipped template, scaffolded: the checker and the real command.

    One row per template, `_neutral` included: `template_verdict` on the
    shipped directory, AND `init <scratch> --template NAME` through the real
    command line in process (the self-check off — `cli.main`'s one knob,
    the one `docs.measure` uses; the self-check that precedes this group
    already ran) exiting 0 with the same block. One more row: the two Swift
    runners are one file, byte for byte.

    With no template present the group is one disclosed SKIP and the run
    goes on: templates are optional to the app, and `--selftest` is a command
    that runs without them. The question is `templates_verdict`'s, the one
    arm `bbbb` and `init` ask.
    """
    group = Report(out, "TEMPLATES")

    def body() -> None:
        present = templates_verdict(templates_dir())
        if not present.present:
            group.skip("every shipped template, scaffolded",
                       f"{present.detail}: {TEMPLATES_ABSENT}; nothing was "
                       "scaffolded and nothing is claimed.")
            return
        shipped = shipped_templates()
        with _box("golden-census-templates-") as box:
            for name in shipped:
                verdict = template_verdict(templates_dir(), name, box)
                scratch = os.path.join(box, f"init-{name}")
                code, text = docs_run(main, ["init", scratch, "--template",
                                             name])
                # Past the run's process-group line, which every command that
                # launches anything opens with and `init`'s own block cannot
                # carry: the claim here is that the COMMAND prints what the
                # scaffolder prints, and the group is the run's, not the
                # template's. The FIRST LINE group is where the line itself is
                # asserted, for every priced command at once.
                body_text = text.split("\n", 1)[1] if text.startswith(
                    "process group ") else text
                same = (body_text.startswith(verdict.block)
                        and verdict.block != "")
                group.check(
                    f"`init --template {name}` into a scratch directory: the "
                    "template holds to parity, every dest is written (a hole "
                    "dest as the literal <<HOLE:…>> directory), the printed "
                    "holes are the declared holes, and the real command "
                    "exits 0 with the same block",
                    verdict.ok and code == 0 and same,
                    f"{ACTUAL}init exit {code}, same block={same}; "
                    + verdict.detail,
                    next="Read the row's detail: the first clause named "
                         "there is the one to fix; docs/adding-a-template.md "
                         "is the format.")
        runners = [os.path.join(templates_dir(), name, "GoldenCensusRunner.swift")
                   for name in ("swift-package", "swift-xcodebuild")]
        raws: list[bytes | None] = []
        for path in runners:
            try:
                with open(path, "rb") as handle:
                    raws.append(handle.read())
            except OSError:
                raws.append(None)
        group.check(
            "the swift-package and swift-xcodebuild runners are one file, "
            "byte for byte — the second template adds the wrapper and nothing "
            "to the runner",
            raws[0] is not None and raws[0] == raws[1],
            f"{ACTUAL}{[len(raw) if raw is not None else None for raw in raws]}"
            " byte(s) each"
            + ("" if raws[0] == raws[1] else "; they DIFFER"),
            next="Copy templates/swift-package/GoldenCensusRunner.swift over "
                 "templates/swift-xcodebuild/GoldenCensusRunner.swift; every "
                 "difference between the two templates belongs in wrapper.py "
                 "or a README.")

    group.guard(body)
    return group.finish()


def selftest(out: Any) -> int:
    """Check golden-census on its own bundled fixture and print the version.

    Seven groups, each a banner fenced by `=` rules with a `N/M passed`
    tally: the controls, a capture, a comparison and its planted control, the
    mutants, the two documents against the parser, the first line every
    command opens with, and every shipped template scaffolded. Returns 0 when
    every arm passed, 1
    when one did not, 2 when golden-census REFUSED — a precondition of the run
    it cannot meet. The temp root's width is the first of those and is asked
    BEFORE the first group, because it is true of the machine rather than of
    any arm; arm `rrr` is its control.

    ONE subject: the stub under `fixture/`, prepared here as a working copy in
    a repository of its own. It carries the surface kinds and the exotic
    census rows a self-test needs, and it travels inside the package, so this
    command measures the same thing in a checkout and in a wheel.
    `examples/python-function/` is a worked example for a reader to copy, not
    a subject of this command: a user may delete it and nothing here notices.
    """
    too_wide = _wide_root_refusal()
    if too_wide is not None:
        # Before the box, before the CONTROLS group, and with no leading
        # blank line: nothing has been printed for one to separate from.
        out.write(refusal_text(too_wide) + "\n")
        return EXIT_REFUSED
    box = tempfile.mkdtemp(prefix="golden-census-selftest-", dir=temp_base())
    try:
        prepared = prepare_fixture(box)
        if prepared.path is None:
            # The ONE place the `--selftest:` name goes in front of a
            # fixture's absence: this command cannot run without one, where a
            # self-test that needs one files a disclosed SKIP and the
            # self-tests after it still run.
            raise Refusal("--selftest: " + prepared.why, next=prepared.next)
        fixture = prepared.path
        manifest = load_manifest(os.path.join(fixture, "manifest.toml"))
        code = selfcheck(out, manifest)
        if code == EXIT_REFUSED:
            return EXIT_REFUSED
        failures = 1 if code else 0
        capture_failures, capture_dir = _capture_group(manifest, box, out)
        failures += capture_failures
        failures += _compare_group(manifest, fixture, capture_dir, box, out)
        failures += _mutants_group(manifest, fixture, out)
        failures += _docs_group(out)
        failures += _first_line_group(fixture, box, out)
        failures += _templates_group(out)
    except Refusal as refused:
        out.write("\n" + refusal_text(refused) + "\n")
        return EXIT_REFUSED
    finally:
        # Under the last block, refusal or tally: a scratch directory left
        # in the temp root is a fact of this run, said where it is read.
        if not remove_tree(box):
            out.write(not_removed(box))
    out.write(f"\n{PROG} {__version__}\n")
    return EXIT_MOVED if failures else EXIT_OK
