"""The two documents, checked against the parser and against a measurement.

Two documents describe golden-census — `README.md` for humans,
`golden-census-skill/SKILL.md` for agents — and both promise the command line's real
surface. A command or a flag the parser dispatches on but neither document
names is drift a reader cannot detect, so parity is checked FROM THE PARSER
OUTWARD: the parser is the authority, both documents must carry what it
exposes, and a table row naming a flag the parser does not expose is the same
lie in the other direction.

What this module PRICES is a different question from what the README's cost
table says. The table is a reader's order-of-magnitude guide, taken by hand at
a release and checked by nothing; `PRICED` below is the list of invocations
the determinism arms run, and it is owned HERE, in code, because the property
they prove is golden-census's and not a document's: a command's output must
cost the same under a temp root of 15 characters and one of 49, and must carry
no absolute path of the machine that produced it. A document that was the
subject of that measurement made every figure in it a thing a change had to
preserve, which is backwards.

Two more document facts are held to one owner here: the exit-code sentence,
whose owner is `cli`'s module docstring and which both documents must carry
verbatim; and the shipped READMEs — every `templates/*/README.md` and
`examples/*/README.md` must be linked from the README, a directory without one
named rather than failed.

One shape this CLI needs and a one-command tool would not: the inventory is
per SUBCOMMAND, so parity is a table of subcommands and their flags rather
than one list.

ADMITTED BOUNDARY: the reverse direction (a document naming a flag the parser
lacks) is checked over the documents' markdown TABLES, not their prose and
code blocks. Both documents quote a consumer's manifest, and a consumer's
subject has flags of its own — `--json`, `--tests`, `--acceptance` — which are
not this parser's and must not be read as drift. The tables are where the
inventory lives; the examples are where somebody else's command line lives.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import io
import itertools
import os
import pathlib
import re
import shutil
import sys
from collections.abc import Callable, Collection, Mapping
from typing import Any, NamedTuple

from .cli import __doc__ as _CLI_DOC, build_parser, main
from .core import (
    ACTUAL,
    AGENT_SET,
    EXIT_REFUSED,
    DIFFERENCE,
    HUMAN_SET,
    PROG,
    IMPORT_NAME,
    SHIPPED,
    Layout,
    Placeholders,
    Refusal,
    read_text,
    refusal_text,
)
from .probe import WRITES
from .proof import _box

#: A long option as it is written in either document.
FLAG_TOKEN = re.compile(r"--[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

#: A backticked word in a table cell.
CELL_CODE = re.compile(r"`([^`]+)`")

#: argparse's own; not ours to document, and allowed wherever it is written.
ARGPARSE_OWN = "--help"


# ------------------------------------------------------------- the inventory


def command_surface() -> dict[str, tuple[str, ...]]:
    """`{subcommand: its long options}`, the bare command line under `""`.

    argparse offers no public enumeration, so this reads the action table the
    parser itself dispatches on — the same table a run is decided by, which is
    the whole point: a hand-kept list would drift with the documents rather
    than against them.
    """
    parser = build_parser()
    surface: dict[str, tuple[str, ...]] = {"": _long_options(parser)}
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if not isinstance(action, argparse._SubParsersAction) or not choices:
            continue
        for name, sub in choices.items():
            surface[name] = _long_options(sub)
    return surface


def _long_options(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    found = {option for action in parser._actions
             for option in action.option_strings
             if option.startswith("--") and option != ARGPARSE_OWN}
    return tuple(sorted(found))


def flags(surface: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Every long option the whole command line exposes, once."""
    return tuple(sorted({flag for row in surface.values() for flag in row}))


def subcommands(surface: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(sorted(name for name in surface if name))


# ------------------------------------------------------------- the documents


def tables(text: str) -> list[tuple[str, list[str]]]:
    """Markdown tables as `(header row, body rows)`; a table is a run of
    lines beginning with `|`."""
    runs = [list(run) for is_row, run in itertools.groupby(
                text.splitlines(), key=lambda line: line.lstrip().startswith("|"))
            if is_row]
    return [(rows[0], rows[1:]) for rows in runs if len(rows) >= 2]


def _is_separator(row: str) -> bool:
    return re.fullmatch(r"[|\s:\-]+", row) is not None


def parity_problems(surface: dict[str, tuple[str, ...]], text: str,
                    label: str) -> list[str]:
    """Everything wrong with one document, as sentences; empty means parity.

    Two directions: `inventory_problems` and `table_problems`.
    """
    return (inventory_problems(surface, text, label)
            + table_problems(surface, text, label))


def inventory_problems(surface: dict[str, tuple[str, ...]], text: str,
                       label: str) -> list[str]:
    """The forward direction: every subcommand and every long option the
    parser exposes appears in `text`, word-bounded, so `--manifest` cannot be
    satisfied by `--manifests`."""
    problems: list[str] = []
    missing = [name for name in subcommands(surface)
               if not re.search(r"(?<![a-z-])" + re.escape(name)
                                + r"(?![a-z0-9-])", text)]
    if missing:
        problems.append(f"{label} names no subcommand " + ", ".join(missing))
    absent = [flag for flag in flags(surface)
              if not re.search(re.escape(flag) + r"(?![a-z0-9-])", text)]
    if absent:
        problems.append(f"{label} is missing: " + ", ".join(absent))
    return problems


def table_problems(surface: dict[str, tuple[str, ...]], text: str,
                   label: str) -> list[str]:
    """The reverse direction: no markdown table names a flag the parser does
    not expose, which is the same lie the other way round."""
    known = set(flags(surface))
    problems: list[str] = []
    for _header, body in tables(text):
        for row in body:
            if _is_separator(row):
                continue
            for token in FLAG_TOKEN.findall(row):
                if token not in known and token != ARGPARSE_OWN:
                    problems.append(
                        f"{label} table row names {token!r}, which the parser "
                        f"does not expose: {row.strip()[:60]!r}")
    return problems


def pair_problems(surface: dict[str, tuple[str, ...]], text: str,
                  label: str) -> list[str]:
    """Every (subcommand, long option) pair the parser exposes has its own row
    in a flag table of `text`: a table whose header's first cell is `Flag`, a
    row whose first cell names the option and whose second cell names the
    subcommand in backticks, or `whole program` for the bare command line
    (`--selfcheck` standing for it where the option is `--manifest`).

    And the other way round: every place a row's second cell names, a
    backticked subcommand or `whole program`, is a pair the parser exposes,
    and a cell that names no place at all is a problem. A row for a pair the
    parser does not have is a false row the reader would trust.

    `inventory_problems` asks whether a flag's NAME appears anywhere; a table
    row deleted while the prose still names the flag passes it, and this does
    not.
    """
    rows: dict[str, list[str]] = {}
    for header, body in tables(text):
        if _cells(header)[:1] != ["Flag"]:
            continue
        for row in body:
            cells = _cells(row)
            named = FLAG_TOKEN.findall(cells[0]) if cells else []
            if named and not _is_separator(row):
                rows.setdefault(named[0], []).append(
                    cells[1] if len(cells) > 1 else "")
    problems: list[str] = []
    for name, options in sorted(surface.items()):
        for option in options:
            where = "whole program" if name == "" else f"`{name}`"
            alternate = ("`--selfcheck`"
                         if name == "" and option == "--manifest" else None)
            if not any(where in cell or (alternate and alternate in cell)
                       for cell in rows.get(option, [])):
                problems.append(
                    f"{label} has no flag-table row for {option} under "
                    f"{name or 'the bare command line'}")
    known = subcommands(surface)
    for option, cells in sorted(rows.items()):
        for cell in cells:
            places = [f"`{name}`" for name in CELL_CODE.findall(cell)
                      if name in known]
            if "whole program" in cell or (
                    option == "--manifest" and "`--selfcheck`" in cell):
                places.append("whole program")
            if not places:
                problems.append(
                    f"{label} has a flag-table row for {option} whose "
                    f"second cell names no subcommand and not the whole "
                    f"program: {cell}")
            for place in places:
                name = "" if place == "whole program" else place.strip("`")
                if option not in surface.get(name, ()):
                    problems.append(
                        f"{label} has a flag-table row for {option} under "
                        f"{place}, a pair the parser does not have: {cell}")
    return problems


def _cells(row: str) -> list[str]:
    """The cells of a markdown table row, stripped."""
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


#: A document set as read: `(path from the root, text)` per member.
Members = list[tuple[str, str]]

#: A reference file the skill names: `references/<name>.md`.
REFERENCE_NAME = re.compile(r"references/([A-Za-z0-9_-]+\.md)")

#: Between the members of a set when they are read as one text, so a table
#: ending one member cannot run into a table beginning the next.
MEMBER_JOIN = "\n\n"


def reference_problems(text: str, label: str,
                       carried: Collection[str]) -> list[str]:
    """Every `references/<name>.md` that `text` (the skill file, whose path
    from the root is `label`) names is a path in `carried`."""
    base = os.path.dirname(label)
    return [f"{label} names references/{name}, which the agent set does not "
            "carry"
            for name in dict.fromkeys(REFERENCE_NAME.findall(text))
            if f"{base}/references/{name}" not in carried]


def set_problems(surface: dict[str, tuple[str, ...]],
                 members: Members, name: str,
                 entry: str | None = None) -> list[str]:
    """Everything wrong with one document SET, as sentences; empty means
    parity. `members` is `(path from the root, text)` per member and `name`
    is what a sentence calls the set.

    The members are read as one text for the inventory and the tables: a flag
    may be named in any of them, and its row may stand in any of them. `entry`
    is the path of the file read first and whole: it alone keeps every
    subcommand and flag, so the invocations block it carries cannot lose one
    to a reference, and every reference it names must be a member.
    """
    text = MEMBER_JOIN.join(body for _path, body in members)
    problems = (parity_problems(surface, text, name)
                + pair_problems(surface, text, name))
    for path, body in members:
        if path != entry:
            continue
        if len(members) > 1:
            problems += inventory_problems(surface, body, path)
        problems += reference_problems(body, path,
                                       [member for member, _ in members])
    return problems


# ------------------------------------------------------- the priced commands


class Invocation(NamedTuple):
    """One golden-census command line to price, placeholders intact.

    `key` is the name a row prints it under; `argv` is what the parser is
    handed once `cost_placeholders` has expanded it.
    """

    key: str
    argv: tuple[str, ...]


#: Every command the determinism arms price, owned HERE and read from no
#: document. One per subcommand and per whole-program flag that LAUNCHES
#: something, because the claim — a command's output is the same under any
#: temp root, and names no directory of the machine — is a claim about all of
#: them and a subset would leave the rest unmeasured.
#:
#: `--selftest` is absent and cannot be added: it IS the whole app, and an
#: entry that ran it from inside a measurement would not terminate.
#: `--selfcheck` is absent from the two-root arms for a different reason,
#: stated at `selfcheck._UNPRICED_UNDER_TWO_ROOTS`: its own rows quote the
#: scratch directories they plant, by design.
PRICED: tuple[Invocation, ...] = (
    Invocation("`--version`", ("--version",)),
    Invocation("`--selfcheck`", ("--selfcheck", "--manifest", "<MANIFEST>")),
    Invocation("`census`", ("census", "--manifest", "<MANIFEST>")),
    Invocation("`capture`", ("capture", "--manifest", "<MANIFEST>",
                             "--out", "<OUT>")),
    Invocation("`capture --twice`", ("capture", "--manifest", "<MANIFEST>",
                                     "--out", "<OUT>", "--twice")),
    Invocation("`compare --against`", ("compare", "--manifest", "<MANIFEST>",
                                       "--golden", "<GOLDEN>",
                                       "--against", "<AGAINST>")),
    Invocation("`compare`", ("compare", "--manifest", "<MANIFEST>",
                             "--golden", "<GOLDEN>")),
    Invocation("`mutants`", ("mutants", "--manifest", "<MANIFEST>",
                             "--mutants", "<MUTANTS>")),
    Invocation("`probe`", ("probe", "--", "<PYTHON>", "<STUB>", "--json",
                           WRITES)),
    Invocation("`init`", ("init", "<OUT>")),
    Invocation("`init --template python-function`",
               ("init", "<OUT>", "--template", "python-function")),
    Invocation("`init --list`", ("init", "--list")),
)


# ---------------------------------------------------------- the measurement


def cost_placeholders(fixture: str, reference: str) -> Placeholders:
    """The vocabulary an `Invocation` may spell, built from one prepared copy
    of the bundled fixture.

    `<PYTHON>`, `<STUB>` and `<WRITES>` are the `probe` entry's: a probe
    prices a COMMAND, and the only command this repository may point one at is
    the fixture's own stub. `<WRITES>` maps to itself — `probe` substitutes
    it, so the argv has to be able to carry it through unchanged rather than
    have it refused as a token nobody defines — and it is `probe.WRITES`, the
    token's owner, not a second spelling of it.
    """
    return Placeholders({
        "MANIFEST": os.path.join(fixture, "manifest.toml"),
        "GOLDEN": os.path.join(fixture, "subject", "golden"),
        "MUTANTS": os.path.join(fixture, "mutants.toml"),
        "AGAINST": reference,
        "PYTHON": sys.executable,
        "STUB": os.path.join(fixture, "subject", "stub.py"),
        "WRITES": WRITES,
        "OUT": None,
    })


def measure_one(one: Invocation, table: Placeholders, out_dir: str,
                selfcheck: Callable[..., int] | None = None
                ) -> tuple[int, int, int, str]:
    """`(exit, lines, characters, the block itself)` for ONE invocation.

    The block comes back so a caller can look at the TEXT and not only the
    count: arm `eee` asserts that the priced output carries the census's fold
    tokens and neither the scratch temp root nor this machine's, which is a
    question about bytes that a triple of numbers cannot answer. Characters
    and not an estimate of tokens: no arithmetic over a model's tokenizer
    survives a change of model, and what these arms compare is one run against
    another run of the same command.
    """
    where = f"the priced invocation {one.key}"
    argv = [table.also({"OUT": out_dir}).expand(token, where)
            for token in one.argv]
    code, text = _run(functools.partial(
        main, selfcheck=_no_runner if selfcheck is None else selfcheck), argv)
    return code, len(text.splitlines()), len(text), text


def _no_runner(*_args: Any) -> int:
    """What a priced `--selfcheck` runs when `measure` was handed no runner:
    a raise, never `cli.main`'s refusal, so the caller's row fails as a fault
    of the code instead of measuring a refusal as the command's output."""
    raise RuntimeError("`docs.measure` priced `--selfcheck` and was handed "
                       "no runner for it")


def measure(priced: tuple[Invocation, ...], fixture: str, box: str,
            blocks: dict[str, str] | None = None,
            keys: set[str] | None = None,
            selfcheck: Callable[..., int] | None = None
            ) -> dict[str, tuple[int, int, int]]:
    """`{key: (exit, lines, characters)}` from running every invocation
    against a prepared copy of the bundled fixture.

    Each command is run through the real command line with the self-check
    suppressed: what is measured is the COMMAND's own output, and a
    measurement that repeated the controls in front of every one would say
    more about the controls than about the command.

    The placeholders are one `Placeholders` value, so an argv spelling
    `<OUTT>` is REFUSED naming the token and the whole list. A private
    `dict.get` beside a `str.replace` would resolve what it recognized and hand
    everything else to argparse unexpanded — an expander that never refuses.

    `blocks`, when given, is filled with each command's whole TEXT, and `keys`
    narrows the run to the ones named. Both are for the two-root arm: whether
    a command prices the same under a 15-character temp root and a
    49-character one is a question about the BYTES, and a triple of numbers
    cannot answer it.

    `selfcheck` is what a priced `--selfcheck` runs, handed to `cli.main` as
    `console.main` hands it: the FIRST LINE group of `--selftest` hands
    `selfcheck.selfcheck`, and a caller that prices no `--selfcheck` hands
    none; one that prices it handed none raises (`_no_runner`).
    """
    reference = os.path.join(box, "reference-capture")
    manifest_path = os.path.join(fixture, "manifest.toml")
    table = cost_placeholders(fixture, reference)
    # The SELECTED entries, not every priced one: the reference capture exists
    # to give `<AGAINST>` a directory to read, and asked of the whole list it
    # ran a full capture of the fixture for a measurement that never spells the
    # token — the most expensive thing this function does, done for nothing.
    selected = [one for one in priced if keys is None or one.key in keys]
    if any("<AGAINST>" in one.argv for one in selected):
        _run(main, ["capture", "--manifest", manifest_path, "--out", reference])
    measured: dict[str, tuple[int, int, int]] = {}
    for number, one in enumerate(priced):
        if keys is not None and one.key not in keys:
            continue
        out_dir = os.path.join(box, f"out-{number}")
        code, lines, characters, text = measure_one(one, table, out_dir,
                                                    selfcheck)
        measured[one.key] = (code, lines, characters)
        if blocks is not None:
            blocks[one.key] = text
        shutil.rmtree(out_dir, ignore_errors=True)
    return measured


def _run(main: Any, argv: list[str]) -> tuple[int, str]:
    """One golden-census command, in process, with its whole verdict
    captured.

    Through `sys.stdout` rather than an `out` parameter because that is what
    the command line writes to, and what is measured has to be what a reader
    sees.

    BOTH exits a bad argv can take are caught: a `Refusal`, and the
    `SystemExit` argparse raises on an argv the parser rejects (a missing
    required flag, a subcommand that is not one). Uncaught, that second one
    ends the whole run from inside a measurement with argparse's usage block
    as the only clue; caught, it is a refusal naming the argv, like every
    other precondition this package cannot meet. `stderr` is a buffer for the
    duration so that usage block does not land in the middle of the rows.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = main(argv, run_selfcheck=False)
        except Refusal as refused:
            buffer.write(refusal_text(refused) + "\n")
            code = EXIT_REFUSED
        except SystemExit as exited:
            buffer.write(refusal_text(Refusal(
                f"`{' '.join(argv)}` is not a command line this parser accepts: "
                f"argparse rejected it and exited {exited.code}.",
                next="Fix that entry in `docs.PRICED` so its argv is one `--help` "
                     "shows — a flag it spells that the parser does not expose is "
                     "caught by the parity arms, but a REQUIRED flag it omits is "
                     "not.")
                ) + "\n")
            code = EXIT_REFUSED
    return code, buffer.getvalue()


# ------------------------------------------------ one owner per document fact
#
# Three facts a document would otherwise state on its own — the exit-code
# sentence, which READMEs ship, golden-census's version — have ONE owner here,
# and the documents are checked against it rather than trusted to agree.

#: golden-census's version wherever a document spells it: `golden-census
#: x.y.z` in the README and in the worked example's, `golden-census version
#: x.y.z` in the skill's
#: version lock. Built from `PROG` rather than the literal word, so the rename
#: carries the pattern with the program.
#:
#: The capture takes a PEP 440 pre-release suffix — `a`, `b` or `rc` and a
#: number — because `\b` cannot hold between the last digit of `1.0.0` and the
#: `b` after it: a token that stopped at three numbers would match nothing in
#: a document spelling a beta, and a pattern that matches nothing reads as a
#: document with no version site.
VERSION_TOKEN = re.compile(rf"\b{re.escape(PROG)}\s+(?:version\s+)?"
                           r"(\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)\b")

#: The line of `cli`'s docstring that owns the exit-code sentence.
EXIT_SENTENCE_PREFIX = "Exit codes:"

#: A markdown link target: `](path)`.
LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def exit_sentence() -> str:
    """The exit-code sentence, from its one owner: the line of `cli`'s module
    docstring beginning `Exit codes:`, stripped; `""` when no line does.

    Three documents carry the sentence — `cli.py`, the manual, the skill —
    and three statements of one fact drift apart one word at a time, so one of
    them owns it. `cli.py`'s is the owner because it sits beside `cli.main`,
    which decides the exit codes; `--help` prints the parser's description,
    not this docstring.
    """
    return next((line.strip() for line in (_CLI_DOC or "").splitlines()
                 if line.strip().startswith(EXIT_SENTENCE_PREFIX)), "")


def owned_sentence_problems(text: str, label: str, sentence: str) -> list[str]:
    """Empty when `text` carries `sentence` verbatim, whitespace aside — a
    document wraps its lines and that is not drift. A miss names `label:LINE`
    (the first line spelling the sentence's opening words, else `absent`) and
    quotes what stands there."""
    if not sentence:
        return [f"{label}: the owner states no sentence to check against"]
    if _normalized(sentence) in _normalized(text):
        return []
    # The line to name is the one that comes CLOSEST to the sentence — the
    # document's own statement of the fact, wherever it drifted — scored by
    # the sentence's opening words first and then by the words it shares; a
    # document sharing none has no statement to point at.
    head = (sentence.split(":", 1)[0] if ":" in sentence
            else sentence.split()[0]).lower()
    words = {word.strip(".,:").lower() for word in sentence.split()
             if len(word.strip(".,:")) >= 4}
    best, where = 0, 0
    for number, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        shared = (sum(1 for word in words if word in lowered)
                  + (len(words) if head in lowered else 0))
        if shared > best:
            best, where = shared, number
    if best:
        line = text.splitlines()[where - 1]
        return [f"{label}:{where} does not carry the owner's sentence "
                f"{sentence!r} — what stands there: "
                f"{line.strip()[:DIFFERENCE]!r}"]
    return [f"{label}: absent — no line shares a word with {sentence!r}"]


def set_sentence_problems(members: Members, name: str,
                          sentence: str) -> list[str]:
    """Empty when ONE member of the set carries `sentence` (see
    `owned_sentence_problems`). When none does, the member that comes
    closest is named, as it is for a single document; a set none of whose
    members shares a word with it is named as a whole."""
    results = [owned_sentence_problems(body, path, sentence)
               for path, body in members]
    if not sentence:
        return results[0] if results else [f"{name}: no member to read"]
    if any(not problems for problems in results):
        return []
    near = [problem for problems in results for problem in problems
            if "does not carry" in problem]
    return near[:1] or [f"{name}: absent — no member of it shares a word "
                        f"with {sentence!r}"]


#: The heading both documents give the adopter's procedure. The section is
#: found BY it: each document carries other numbered lists — the skill's
#: report-hygiene list among them — and a walk over every `N.` in a document
#: would compare a procedure against a checklist.
PROCEDURE_HEADING = "Plugging a project in, in order"

#: A numbered item of a markdown list, and the bold phrase that opens it.
STEP_LINE = re.compile(r"^(\d+)\.\s+(.*)$")
STEP_LEAD = re.compile(r"^\*\*(.+?)\*\*")


def procedure_steps(text: str) -> list[tuple[str, str]]:
    """`(number, the leading bold phrase)` for every numbered item under
    `PROCEDURE_HEADING`, in the order they are written.

    The phrase and not the item's whole text: the two documents say the same
    steps to two audiences and their bodies differ by design, while the phrase
    that NAMES a step is the thing an agent and a human have to be told
    identically. An item opening with no bold phrase comes back with an empty
    one, which `procedure_problems` names rather than skipping — a step whose
    name is missing is exactly what this check is for.
    """
    lines = text.splitlines()
    heading = next((number for number, line in enumerate(lines)
                    if line.lstrip("#").strip() == PROCEDURE_HEADING
                    and line.startswith("#")), None)
    if heading is None:
        return []
    steps: list[tuple[str, str]] = []
    for line in lines[heading + 1:]:
        if line.startswith("#"):
            break
        found = STEP_LINE.match(line)
        if found:
            lead = STEP_LEAD.match(found.group(2))
            steps.append((found.group(1), lead.group(1) if lead else ""))
    return steps


def procedure_problems(halves: list[tuple[str, str]]) -> list[str]:
    """Everything the two procedures disagree about, as sentences.

    The count, the numbering and the name of each step. A document that
    carries no procedure at all is named rather than passed: two documents
    with no steps between them agree perfectly and say nothing.
    """
    problems: list[str] = []
    read = [(label, procedure_steps(text)) for label, text in halves]
    for label, steps in read:
        if not steps:
            problems.append(f"{label} carries no numbered step under "
                            f"{PROCEDURE_HEADING!r}")
        for number, phrase in steps:
            if not phrase:
                problems.append(f"{label} step {number} opens with no bold "
                                "phrase naming it")
    if len(read) < 2 or any(not steps for _label, steps in read):
        return problems
    (first_label, first), (second_label, second) = read[0], read[1]
    if len(first) != len(second):
        problems.append(
            f"{first_label} states {len(first)} steps and {second_label} "
            f"{len(second)} — the two documents are one procedure")
    for left, right in zip(first, second, strict=False):
        if left[0] != right[0]:
            problems.append(f"{first_label} numbers a step {left[0]} where "
                            f"{second_label} numbers it {right[0]}")
        elif left[1] != right[1]:
            problems.append(
                f"step {left[0]} is {left[1]!r} in {first_label} and "
                f"{right[1]!r} in {second_label}")
    return problems


def procedure_halves(sets: list[tuple[str, Members]]
                     ) -> tuple[list[tuple[str, str]], list[str]]:
    """`(one (label, text) per set for `procedure_problems`, the problems of
    the sets themselves)`, from `(name, members)` per set.

    A set tells the procedure ONCE: the member carrying `PROCEDURE_HEADING` is
    the set's half, and a second member carrying it is a problem naming both.
    A set whose members carry it nowhere is its own half, so the comparison
    names it as having no step.
    """
    halves: list[tuple[str, str]] = []
    problems: list[str] = []
    for name, members in sets:
        carriers = [(path, body) for path, body in members
                    if _carries_heading(body)]
        if len(carriers) > 1:
            problems.append(
                " and ".join(path for path, _ in carriers)
                + f" both carry {PROCEDURE_HEADING!r}: the procedure has one "
                f"home in {name}")
        halves.append(carriers[0] if carriers else (
            name, MEMBER_JOIN.join(body for _path, body in members)))
    return halves, problems


def _carries_heading(text: str) -> bool:
    return any(line.startswith("#")
               and line.lstrip("#").strip() == PROCEDURE_HEADING
               for line in text.splitlines())


def version_sites(text: str, label: str) -> list[tuple[str, str]]:
    """Every `label:LINE` of `text` that spells golden-census's version, with
    the version it spells there.

    By REGEX over the document, never by a kept list of line numbers: such a
    list is one more site to hold in step and the one that would be
    forgotten, and it goes stale the first time a paragraph above it grows a
    line.
    """
    return [(f"{label}:{number}", found.group(1))
            for number, line in enumerate(text.splitlines(), 1)
            for found in VERSION_TOKEN.finditer(line)]


def version_problems(text: str, label: str, version: str) -> list[str]:
    """Empty when every site in `text` spells `version` AND there is at least
    one site.

    The version is a SYNC key with one owner, `golden_census.__version__`:
    the digits exist to keep the app, the README, the skill and the worked
    example in step, so what is checkable about it is the sync and nothing
    else. What a digit CLAIMS is a judgment, and nothing here makes one.

    A document with NO site is a problem rather than a pass, for two reasons
    at once: a document that names the version nowhere cannot be in step with
    anything, and a pattern that matched nothing has not been shown able to
    match — a zero result is not a clean result.
    """
    return version_set_problems([(label, text)], label, version)


def version_set_problems(members: Members, name: str,
                         version: str) -> list[str]:
    """`version_problems` for a SET: every site of every member spells
    `version`, and the set as a whole spells it at least once — a reference
    file with no version in it is not drift, a set with none is."""
    sites = [site for path, body in members
             for site in version_sites(body, path)]
    problems = [f"{where} spells {PROG} {found}, and {IMPORT_NAME}.__version__ is "
                f"{version}" for where, found in sites if found != version]
    if not sites:
        problems.append(
            f"{name} spells no {PROG} version at all: the pattern "
            f"{VERSION_TOKEN.pattern!r} matched nothing in it, so either the "
            "document lost its version site or this check has lost its "
            "ability to see one")
    return problems


def shipped_readmes(root: str) -> tuple[list[str], list[str]]:
    """`(the README.md files under templates/*/ and examples/*/, relative to
    `root`; the directories there that carry none)`, both sorted.

    A directory with no README is NAMED, never a problem: `templates/_neutral`
    is the three files every project gets and has no pattern document of its
    own, and a check that failed on it would be a check nobody could keep
    green.
    """
    present: list[str] = []
    missing: list[str] = []
    for kind in ("templates", "examples"):
        base = os.path.join(root, kind)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not os.path.isdir(os.path.join(base, name)):
                continue
            relative = f"{kind}/{name}/README.md"
            if os.path.isfile(os.path.join(root, relative)):
                present.append(relative)
            else:
                missing.append(f"{kind}/{name}")
    return present, missing


def link_problems(text: str, label: str, readmes: list[str]) -> list[str]:
    """Empty when every path in `readmes` is a markdown link TARGET in `text`
    — `](templates/x/README.md)`, a link a reader can follow, never a
    mention in prose."""
    targets = set(LINK_TARGET.findall(text))
    return [f"{label} links no {path}" for path in readmes
            if path not in targets]


def packaging_problems(document: Mapping[str, Any]) -> list[str]:
    """Everything wrong with `pyproject.toml`'s two packaging tables, as
    sentences; empty means the artifacts carry what the documents promise.

    Two facts the TOML states that the package cannot import, so nothing but
    this reads them. The sdist: every `include` pattern is ANCHORED
    with a leading `/`, because hatchling matches an unanchored name at any
    depth, so an unanchored package or docs name ships every directory of
    that name wherever it sits. The wheel: every `force-include`
    target lands under `<core.IMPORT_NAME>/<core.SHIPPED>/`, the directory
    `core.data_in` reads in a wheel —
    the two spell one name, and a drift between them is an installed `init`
    refusing "no templates are installed" while the checkout stays green.
    """
    problems: list[str] = []
    targets = (document.get("tool", {}).get("hatch", {}).get("build", {})
               .get("targets", {}))
    sdist = targets.get("sdist", {})
    include = [str(pattern) for pattern in sdist.get("include", [])]
    if not include:
        problems.append("[tool.hatch.build.targets.sdist] names no include "
                        "pattern")
    unanchored = [pattern for pattern in include if not pattern.startswith("/")]
    if unanchored:
        problems.append(
            "the sdist include pattern(s) " + ", ".join(map(repr, unanchored))
            + " are not anchored: hatchling matches an unanchored name at "
            "any depth, so every directory of that name would ship")
    force = targets.get("wheel", {}).get("force-include", {})
    if not force:
        problems.append("[tool.hatch.build.targets.wheel] names no "
                        "force-include row")
    for source, target in force.items():
        if not str(target).startswith(f"{IMPORT_NAME}/{SHIPPED}/"):
            problems.append(
                f"the wheel's force-include row {source!r} -> {target!r} "
                f"does not land under {IMPORT_NAME}/{SHIPPED}/, which is "
                "where "
                "`core.data_in` looks in an install")
    return problems


# ---------------------------------------------------- the fabricated controls
#
# A checker nobody has seen go red is a checker that passes every document.
# These are pure: a synthetic document and, for the cost arm, a synthetic
# measurement — so they cost the self-check nothing and need no fixture.


def synthetic(surface: dict[str, tuple[str, ...]],
              rows: list[str] | None = None) -> str:
    """The smallest document that satisfies the checker. Fabricated drift
    starts from here.

    The table is here because one direction of parity is only checkable
    against one: a document naming a flag the parser does not expose is
    caught in its markdown TABLES, so a control for that direction needs a
    table to put the impostor in.
    """
    text = ["# synthetic", "", " ".join(subcommands(surface)), "",
            " ".join(flags(surface)), ""]
    text += ["| Command | What it does | Exit |", "|---|---|---|"]
    text += rows if rows is not None else ["| `--version` | the version | 0 |"]
    text += [""]
    return "\n".join(text) + "\n"


def synthetic_flag_table(surface: dict[str, tuple[str, ...]],
                         omit: Collection[str] = ()) -> list[str]:
    """A flag table with one row per long option but those in `omit`, each
    row's Where cell naming every subcommand that takes the option, as the
    documents' own tables do."""
    where: dict[str, list[str]] = {}
    for name, options in sorted(surface.items()):
        for option in options:
            where.setdefault(option, []).append(
                f"`{name}`" if name else "whole program")
    return ["| Flag | Where | What it does |", "|---|---|---|"] + [
        f"| `{option}` | {' '.join(cells)} | what it does |"
        for option, cells in sorted(where.items()) if option not in omit]


def synthetic_entry(surface: dict[str, tuple[str, ...]],
                    omit: Collection[str] = (),
                    unnamed: Collection[str] = (), tail: str = "") -> str:
    """A document whose PROSE names every subcommand and every long option
    but those in `unnamed`, and whose flag table lacks those in `omit` —
    prose naming a flag its table does not carry is the drift the pair check
    exists for."""
    named = [option for option in flags(surface) if option not in unnamed]
    return "\n".join(["# one", "", " ".join(subcommands(surface)), "",
                      " ".join(named), "",
                      *synthetic_flag_table(surface, omit), "", tail, ""])


#: The steps arm `cccc` fabricates a procedure out of. Four, because the
#: checks it exercises — the count, the numbering, the name — need more than
#: one step and no more than a handful, and because a plant made from the
#: REAL documents would go red the day somebody edits them for a good reason.
_FIXTURE_STEPS: tuple[tuple[str, str], ...] = (
    ("0", "Once per session:"),
    ("1", "Choose the function."),
    ("2", "`probe` — before the first `capture`."),
    ("3", "`init`."),
)


def synthetic_procedure(steps: list[tuple[str, str]]
                        | tuple[tuple[str, str], ...]) -> str:
    """A document carrying `steps` under the procedure's own heading, and one
    numbered list elsewhere that the reader must NOT pick up."""
    text = [f"## {PROCEDURE_HEADING}", ""]
    for number, phrase in steps:
        opening = f"**{phrase}** " if phrase else ""
        text += [f"{number}. {opening}what the step says.", ""]
    text += ["## Report hygiene", "", "1. a list that is not the procedure.",
             ""]
    return "\n".join(text)


def usage_subcommands(usage: str | None = None) -> tuple[str, ...]:
    """The subcommands `cli`'s module docstring's usage block names.

    Arm `bb`'s expectation, read off the one statement of the command
    inventory the same-commit rule already makes a stage edit: the usage block
    is what `--help`'s reader is told the commands are. A literal set typed
    here instead costs a one-word edit in this file per subcommand added — and
    the edit that is forgotten leaves the arm agreeing with itself.

    A usage line is `<prog> <word> …` with the word not a flag; `--selfcheck`,
    `--selftest` and `--version` are whole-program flags and not subcommands,
    which is exactly the distinction the leading `--` makes.
    """
    if usage is None:
        usage = _CLI_DOC
    words = [line.split() for line in (usage or "").splitlines()]
    return tuple(dict.fromkeys(w[1] for w in words if len(w) >= 2
                               and w[0] == PROG and not w[1].startswith("-")))


def set_control(check: Any) -> None:
    """(ff) the document-set checks go red on a fabricated set and pass the
    same set whole: the pair check in both directions, the first file read
    alone, the references it names, and the procedure's one home."""
    surface = command_surface()
    entry, reference = "fixture/one.md", "fixture/references/two.md"
    other = "# two\n"
    cite = "see references/two.md"
    well = set_problems(surface, [(entry, synthetic_entry(surface, tail=cite)),
                                  (reference, other)], "fixture-set", entry)
    pair = set_problems(
        surface, [(entry, synthetic_entry(surface, omit=("--census",),
                                          tail=cite)),
                  (reference, other)], "fixture-set", entry)
    whole_entry = synthetic_entry(surface, tail=cite)
    false_row = set_problems(
        surface, [(entry, whole_entry.replace(
            "|---|---|---|\n", "|---|---|---|\n| `--twice` | `compare` | x |\n",
            1)), (reference, other)], "fixture-set", entry)
    selfcheck_only = set_problems(
        surface, [(entry, whole_entry.replace(
            "| `--version` | whole program |",
            "| `--version` | `--selfcheck` |", 1)), (reference, other)],
        "fixture-set", entry)
    alone = set_problems(
        surface, [(entry, synthetic_entry(surface, omit=("--allow-diff",),
                                          unnamed=("--allow-diff",),
                                          tail=cite)),
                  (reference, "\n".join(synthetic_flag_table(surface)))],
        "fixture-set", entry)
    unmade = set_problems(
        surface, [(entry, synthetic_entry(
            surface, tail=cite + " and references/gone.md")),
                  (reference, other)], "fixture-set", entry)
    heading = synthetic_procedure(_FIXTURE_STEPS)
    homes = procedure_halves([("fixture-set", [(entry, heading),
                                               (reference, other)])])
    twice = procedure_halves([("fixture-set", [(entry, heading),
                                               (reference, heading)])])
    check("ff  a document SET is read as one text with a row of its own for "
          "every flag of every subcommand: a two-file set whose prose names "
          "every flag passes; the same set with the flag table's row for "
          "`--census` removed, the prose untouched, FAILS naming exactly "
          "`--census` under `probe`; a row for a pair the parser does not "
          "have (`--twice` under `compare`) FAILS naming it; a bare flag "
          "(`--version`) whose row names `--selfcheck` alone, which stands "
          "for the bare command line only for `--manifest`, FAILS; a set "
          "whose first file lacks a flag its "
          "second carries FAILS naming that file and flag; a first file "
          "naming a reference the set does not carry FAILS naming it; and "
          "the procedure heading in a second file FAILS naming both files",
          well == []
          and pair == ["fixture-set has no flag-table row for --census under "
                       "probe"]
          and false_row == ["fixture-set has a flag-table row for --twice "
                            "under `compare`, a pair the parser does not "
                            "have: `compare`"]
          and selfcheck_only == [
              "fixture-set has no flag-table row for --version under the "
              "bare command line",
              "fixture-set has a flag-table row for --version whose second "
              "cell names no subcommand and not the whole program: "
              "`--selfcheck`"]
          and alone == [f"{entry} is missing: --allow-diff"]
          and unmade == [f"{entry} names references/gone.md, which the agent "
                         "set does not carry"]
          and homes == ([(entry, heading)], [])
          and twice[1] == [f"{entry} and {reference} both carry "
                           f"{PROCEDURE_HEADING!r}: the procedure has one "
                           "home in fixture-set"],
          f"{ACTUAL}whole {well}; row removed {pair}; false row {false_row}; "
          f"`--selfcheck` alone {selfcheck_only}; first file short "
          f"{alone}; unmade reference {unmade}; the heading in one file "
          f"{homes[1]}; in two {twice[1]}")


def docs_controls(check: Any) -> None:
    """The parity checker's own arms: it goes red on fabricated drift, and it
    passes a document that carries everything."""
    surface = command_surface()
    every = flags(surface)
    stated = usage_subcommands()
    # The positive control for the derivation: the same reader over a usage
    # block with one line struck out must come back short by exactly that
    # word, so a reader that found nothing — or everything — could not make
    # this row green.
    dropped = subcommands(surface)[0] if subcommands(surface) else ""
    struck = usage_subcommands("\n".join(
        line for line in (_CLI_DOC or "").splitlines()
        if line.split()[1:2] != [dropped]))
    check("bb  the parser exposes its surface for inspection: every "
          "subcommand, every long option of each, and argparse's own --help "
          "kept out — and the set it exposes is the set `cli`'s own module "
          "docstring names in its usage block, which is what a reader of "
          "`cli.py` is told the commands are and what the same-commit rule "
          "already edits when one is added; the same reader over that block "
          "with one usage line struck out comes back short by exactly that "
          "word, which is how the derivation is known to be able to go red",
          bool(stated) and set(subcommands(surface)) == set(stated)
          and {"--twice", "--against", "--only", "--selftest", "--allow-diff",
               "--census", "--writes-env"} <= set(every)
          and ARGPARSE_OWN not in every
          and all(flag.startswith("--") for flag in every)
          and set(stated) - set(struck) == {dropped},
          f"{ACTUAL}{len(subcommands(surface))} subcommands "
          f"{sorted(subcommands(surface))}, the usage block names "
          f"{sorted(stated)}, {len(every)} long options, e.g. {every[:4]}; "
          f"the same block with the {dropped!r} line struck out names "
          f"{sorted(struck)}")

    clean = parity_problems(surface, synthetic(surface), "fixture")
    check("cc  a fabricated document that names every subcommand, every flag "
          "and one well-formed table passes with ZERO problems — the "
          "checker is not simply always red",
          clean == [], f"{ACTUAL}{clean}")

    lost = "--allow-diff"
    thinned = synthetic({name: tuple(f for f in row if f != lost)
                         for name, row in surface.items()})
    problems = parity_problems(surface, thinned, "fixture")
    check("dd  a copy of a document with ONE flag deleted FAILS naming "
          f"exactly that flag ({lost})",
          len(problems) == 1 and lost in problems[0]
          and "missing" in problems[0]
          and not any(f in problems[0] for f in every if f != lost),
          f"{ACTUAL}{problems}")

    invented = synthetic(surface,
                         rows=["| `--frobnicate` a sweep | a sweep | 0 |"])
    problems = parity_problems(surface, invented, "fixture")
    check("ee  a copy of a document naming an INVENTED flag in a table FAILS "
          "naming the impostor",
          len(problems) == 1 and "'--frobnicate'" in problems[0]
          and "does not expose" in problems[0],
          f"{ACTUAL}{problems}")

    set_control(check)

    whole = synthetic_procedure(_FIXTURE_STEPS)
    agree = procedure_problems([("fixture-readme", whole),
                                ("fixture-skill", whole)])
    cut = synthetic_procedure([step for step in _FIXTURE_STEPS
                               if step[0] != "2"])
    short = procedure_problems([("fixture-readme", whole),
                                ("fixture-skill", cut)])
    reworded = procedure_problems(
        [("fixture-readme", whole),
         ("fixture-skill", synthetic_procedure(
             [(number, "Pick the function." if number == "1" else phrase)
              for number, phrase in _FIXTURE_STEPS]))])
    nameless = procedure_problems(
        [("fixture-readme", whole),
         ("fixture-skill", synthetic_procedure(
             [(number, "" if number == "3" else phrase)
              for number, phrase in _FIXTURE_STEPS]))])
    check("cccc  the adopter's procedure is ONE procedure told twice: the two "
          "documents state the same number of steps, numbered the same, and "
          "name each step with the same leading bold phrase — a step a human "
          "is told to take and an agent is not is a step somebody skips. Two "
          "fabricated documents carrying the same four steps pass; the same "
          "pair with ONE step removed FAILS naming the count, one with a step "
          "RENAMED FAILS naming that step and both phrases, and one whose "
          "step opens with no bold phrase at all FAILS naming it",
          agree == []
          and any("states 4 steps" in one and "3" in one for one in short)
          and any("'Choose the function.'" in one
                  and "'Pick the function.'" in one for one in reworded)
          and any("opens with no bold phrase" in one for one in nameless),
          f"{ACTUAL}the same twice {agree}; one step removed {short}; one "
          f"renamed {reworded}; one unnamed {nameless}")

    # The two one-owner facts, each checker shown red on a planted document
    # before its live row is believed.
    sentence = exit_sentence()
    owner_line = next((line.strip() for line in (_CLI_DOC or "").splitlines()
                       if line.strip().startswith(EXIT_SENTENCE_PREFIX)), "")
    wrapped = "x\n" + sentence.replace("IDENTICAL, ", "IDENTICAL,\n  ") + "\n"
    kept = owned_sentence_problems(wrapped, "fixture-skill", sentence)
    reworded = owned_sentence_problems(
        "x\n" + sentence.replace("1 a FAIL", "1 a failure") + "\n",
        "fixture-skill", sentence)
    check("mmm  the exit-code sentence has one owner, `cli`'s docstring, and "
          "both documents are read against it: `exit_sentence()` is that "
          "docstring's `Exit codes:` line; a fabricated document carrying it "
          "across a line wrap passes; one with `1 a FAIL` reworded to `1 a "
          "failure` FAILS naming the line and quoting what stands there",
          bool(sentence) and sentence == owner_line
          and kept == [] and len(reworded) == 1
          and "fixture-skill:2" in reworded[0] and "1 a failure" in reworded[0],
          f"{ACTUAL}owner {sentence!r}; wrapped {kept}; reworded {reworded}")

    with _box("golden-census-links-") as box:
        for name in ("templates/_neutral", "templates/a", "templates/b",
                     "examples/c"):
            os.makedirs(os.path.join(box, name))
        for name in ("templates/a", "templates/b", "examples/c"):
            pathlib.Path(os.path.join(box, name, "README.md")).write_text(
                "# a pattern document\n", encoding="utf-8")
        present, missing = shipped_readmes(box)
    linked = "".join(f"- [`{path}`]({path})\n" for path in present)
    full = link_problems(linked, "fixture-readme", present)
    unlinked = link_problems(linked.replace("](templates/b/README.md)",
                                            "](templates/b/)"),
                             "fixture-readme", present)
    check("nnn  every `templates/*/README.md` and `examples/*/README.md` must "
          "be a link target in the README, and a directory with no README is "
          "NAMED rather than failed: a scratch box with templates/{_neutral,"
          "a,b}/ and examples/c/ lists three READMEs and names `_neutral` as "
          "README-less; a README linking all three passes; the same README "
          "with `templates/b/README.md`'s link removed FAILS naming exactly "
          "that path",
          present == ["templates/a/README.md", "templates/b/README.md",
                      "examples/c/README.md"]
          and missing == ["templates/_neutral"]
          and full == [] and unlinked == ["fixture-readme links no "
                                          "templates/b/README.md"],
          f"{ACTUAL}present {present}, without a README {missing}; all "
          f"linked {full}; b's link removed {unlinked}")


# ------------------------------------------------------------- the live check


def live_parity(surface: dict[str, tuple[str, ...]], check: Any, skip: Any,
                package: str | None = None
                ) -> tuple[Members | None, Members | None]:
    """Both live document sets against the parser. Returns their members, as
    `(path from the root, text)`, so the caller can go on to the other rows
    without reading them twice; a set that was not read comes back None.

    `package` is the directory the documents are found from; it exists so a
    control can point this at a package-only scratch layout and see what a
    copy with no documents sees. Both sets travel in a wheel, under
    `core.SHIPPED` in the checkout's own shape, so an installed copy reads
    them from there through `core.Layout`. A layout that carries neither —
    a package run with nothing beside or under it — reaches this with both
    absent, and each set is ONE disclosed SKIP in `core.Layout`'s one
    sentence, never a pass and never a FAIL about a document nobody shipped.
    Two verdicts for one absence — a [FAIL] for one set and a [SKIP] for the
    other — would leave `--selftest` unable to pass anywhere but in this
    repository. In a checkout, a member the set NAMES — one whose path
    carries no `*` — that is missing is the FAIL, naming it.
    """
    layout = Layout.detect() if package is None else Layout.for_package(package)
    human_label = (
        f"the human set ({', '.join(HUMAN_SET)}), found from the package, "
        "names every subcommand and every long option the parser "
        "exposes, gives every flag of every subcommand its own row in a "
        "flag table, and no table row names a flag it does not")
    agent_label = (
        f"the agent set ({', '.join(AGENT_SET)}), found from the package, "
        "carries the same inventory, the file read first carries every "
        "subcommand and flag itself, and every reference it names exists")
    # Per set: its name in a sentence, its paths, where they were found, its
    # row label, and the file read first and whole, if it has one.
    sets = (
        ("the human set", HUMAN_SET, layout.human, human_label, None),
        ("the agent set", AGENT_SET, layout.agent, agent_label, AGENT_SET[0]),
    )
    read: list[Members | None] = []
    for name, paths, found, label, entry in sets:
        have = {os.path.relpath(path, layout.data) for path in found}
        gone = [path for path in paths if "*" not in path and path not in have]
        members: Members | None = None
        if layout.checkout and gone:
            # A checkout missing a member is a defect, not a layout: parity is
            # a development check, and the install's absence sentence would be
            # false here.
            check(label, False,
                  ACTUAL + " ".join(layout.missing(path) for path in gone),
                  next=f"Restore {', '.join(gone)} beside pyproject.toml — "
                       "`core.HUMAN_SET` and `core.AGENT_SET` name what each "
                       "set must carry, and `core.SKILL_DIR` the skill "
                       "directory.")
        elif found:
            texts = [(os.path.relpath(path, layout.data), read_text(path))
                     for path in found]
            unreadable = [path for path, text in texts if text is None]
            if unreadable:
                check(label, False,
                      ACTUAL + ", ".join(unreadable) + " cannot be read as "
                      "UTF-8 text", next="Restore it as UTF-8 text.")
            else:
                members = [(path, text) for path, text in texts
                           if text is not None]
                problems = set_problems(surface, members, name, entry)
                check(label, not problems,
                      ACTUAL + ("no drift" if not problems
                                else " | ".join(problems)))
        else:
            skip(label,
                 layout.absent(", ".join(paths)) + f" {name.capitalize()} did "
                 "not run and is not claimed passed.")
        read.append(members)
    return read[0], read[1]
