"""The template format: a directory of data `golden-census init` copies into a
project, holes and all.

`docs/adding-a-template.md` is authoritative for every key here. A template is
a directory under `templates/` beside the package holding a `template.toml`,
the files it writes, and the declaration of every hole those files spell.
golden-census's code does not change when a template is added: that is the
whole
point of the format, and it is why nothing in this module knows what any
template is for.

What this module reuses is already golden-census's: `core.load_toml` for the
file, `core.Refusal` for every sentence it will not guess past, and
`core.launch` for a `[[hole]]`'s optional probe.

Two rules that are decisions rather than transcriptions of the format:

* **A hole in a `dest` stays in the PATH.** `init` writes the file to the
  literal `<<HOLE:NAME>>` directory and prints the hole with the file beside
  it, saying the file must be MOVED once the hole is filled. The alternative —
  asking for the value before anything is written — would make `init`
  interactive, and a tool that asks questions cannot be run by an agent
  from a single line. Holes are filled in place, in the path as in the text.

* **`core` owns the `<<HOLE:` token; this module owns the SCAFFOLDING of it.**
  A hole is a fact about a consumer's file, so the regex, `holes_in`, `spelled`
  and `refuse_holes_in` sit in `core` beside `TOKEN_RE`, where every loader
  already looks — a second spelling of the token would be a second answer to
  "is this project finished plugging in". What is written here is what only a
  scaffolder needs: the `[[hole]]` row's own name shape, the parity rule, and
  the `[[hole]]` probe.
"""

from __future__ import annotations

import errno
import io
import os
import re
from typing import Any, NamedTuple

from .core import (
    EXIT_OK,
    DIFFERENCE,
    Layout,
    data_in,
    Made,
    NOT_IN_A_COMPONENT,
    Refusal,
    closed,
    ended,
    holes_in,
    launch,
    load_toml,
    read_text,
    spelled,
    strings,
    under,
    unpunctuated,
    with_next,
)

#: The template every `init` writes first: the three files every project has.
NEUTRAL = "_neutral"

#: What an install with no template in it MEANS, stated once: `init`'s
#: refusal, arm `bbbb`'s SKIP and `--selftest`'s TEMPLATES SKIP each build on
#: it with a closing sentence of their own. Templates are part of the install
#: and optional to the app, so their absence is a fact to disclose and never a
#: red row.
TEMPLATES_ABSENT = ("`init` has nothing to write from, and every other "
                    "command runs without templates")

#: What to do about a template that is present and does not load: `init`'s
#: refusal and arm `bbbb`'s red row both print it.
BROKEN_TEMPLATE_NEXT = ("Fix or delete the template named above, or "
                        "reinstall golden-census to put its own back.")

#: What a `[[hole]]`'s `name` may be: the same word, without the fence.
HOLE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

#: How much of a probe's output `init` prints under the hole's name.
#: golden-census never READS it — refuse-don't-guess applies to scaffolding too — so
#: this is a reading budget and nothing else.
PROBE_LINES = 12


class File(NamedTuple):
    """One `[[file]]` row: what to copy, and where it lands in the project."""

    source: str                     # relative to the template directory
    dest: str                       # relative to the project directory


class Hole(NamedTuple):
    """One `[[hole]]` row: a fact about the project only the project knows."""

    name: str
    description: str
    #: The optional command whose stdout `init` PRINTS under the hole's name.
    #: Never parsed: the reader picks the value, and golden-census does not.
    probe: tuple[str, ...] = ()


class Template(NamedTuple):
    name: str
    summary: str
    directory: str
    files: tuple[File, ...]
    holes: tuple[Hole, ...]


# ------------------------------------------------------------------ the token
#
# `HOLE_RE`, `holes_in`, `spelled` and `refuse_holes_in` are `core`'s: a hole is
# a fact about a consumer's file, `core.load_toml` refuses one on the text it
# already read, and no loader imports the scaffolder to read a consumer's file.
# What stays here is the SCAFFOLDER's half — the `[[hole]]` row's own name
# shape, the parity rule and the `[[hole]]` probe.


# ---------------------------------------------------------------- the loader


def templates_dir() -> str:
    """`templates/` wherever this install put it, asked of `core.Layout`
    (two layouts, one decider): beside the package in a checkout, under the
    package in a wheel. An install carrying neither answers with the
    CHECKOUT's directory — a path and not a None — so `shipped_templates`
    can name the directory it looked in."""
    layout = Layout.detect()
    return layout.templates or data_in(layout.package, "templates")


def shipped_templates() -> tuple[str, ...]:
    """Every template directory this install carries, `_neutral` first.

    `_neutral` first because it is applied first and because a reader of
    `--list` should meet the three files every project has before the runners
    that sit on top of them. An install with no `templates/` beside it is a
    REFUSAL naming the directory it looked in, never an empty list: an empty
    list reads as "golden-census ships no templates", which is a statement
    about the product rather than about this install.
    """
    directory = templates_dir()
    names: tuple[str, ...] = ()
    if os.path.isdir(directory):
        names = tuple(sorted(
            name for name in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, name, "template.toml"))))
    if not names:
        raise no_templates_refusal(directory)
    return tuple(sorted(names, key=lambda name: (name != NEUTRAL, name)))


def no_templates_refusal(directory: str) -> Refusal:
    """The one refusal for an install with no template in `directory`.

    Returned, not raised, so each caller raises it where the absence is
    found. The sentence names the directory looked in, says what the absence
    costs, and gives the two ways forward a reader of an INSTALL has: neither
    `core.Layout` nor `docs/` is something that reader can open.
    """
    return Refusal(
        f"there is no template at {directory}: {TEMPLATES_ABSENT}.",
        next="Reinstall golden-census to put its templates back, or write the "
             "manifest, the census and the mutants file yourself.")


def template_dir(name: str) -> str:
    """The directory a template name refers to, or a refusal listing the
    shipped ones."""
    shipped = shipped_templates()
    if name not in shipped:
        raise Refusal(
            f"no template named {name!r} is installed. The shipped templates "
            "are " + ", ".join(shipped) + ".",
            next="Spell --template with one of the names listed above, or "
                 "drop the flag to write the neutral three alone.")
    return os.path.join(templates_dir(), name)


def load_template(directory: str) -> Template:
    """Read a `template.toml` and check every row of it, before anything is
    written.

    Every refusal names the offending key: a wrong template costs one sentence
    and not half a scaffolded project.
    """
    directory = os.path.abspath(directory)
    path = os.path.join(directory, "template.toml")
    if not os.path.isfile(path):
        raise Refusal(
            f"{os.path.basename(directory)} is not a template: there is no "
            f"template.toml in {directory}. A template is a directory of data, "
            "and template.toml is the file that says what it carries.",
            next="Add a template.toml with `name`, `summary`, its [[file]] "
                 "rows and its [[hole]] rows; docs/adding-a-template.md has "
                 "the shape.")
    # `holes=False`: a template is the ONE file whose holes are the point.
    # Every other reader of a consumer's file refuses on one.
    document, _directory = load_toml(path, "template file", holes=False)

    name = str(document.get("name", "")).strip()
    if not name:
        raise Refusal(f"{path}: no `name`",
                      next="Add `name = \"...\"`, which is the directory's own "
                           "name and the word --template is spelled with.")
    if name != os.path.basename(directory):
        raise Refusal(
            f"{path}: `name` is {name!r} but the directory is "
            f"{os.path.basename(directory)!r}. The two are one name: "
            "`--template` spells the directory, and a template that answered "
            "to two words could not be reported by either.",
            next="Rename the directory, or change `name`, so the two agree.")
    summary = str(document.get("summary", "")).strip()
    if not summary or "\n" in summary:
        raise Refusal(f"{path}: `summary` must be one non-empty line — it is "
                      "what `init --list` prints beside the name",
                      next="Add `summary = \"...\"` as one line saying what "
                           "this template is for.")
    return Template(name, summary, directory,
                    _files(document, path), _holes(document, path))


def _files(document: dict[str, Any], path: str) -> tuple[File, ...]:
    raw_rows = document.get("file", [])
    if not isinstance(raw_rows, list) or not raw_rows:
        raise Refusal(f"{path}: no [[file]] rows — a template that writes no "
                      "file scaffolds nothing.",
                      next="Add one [[file]] row per file this template "
                           "writes, with `source` and `dest`.")
    rows: list[File] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise Refusal(f"{path}: every [[file]] must be a table",
                          next="Write each file as a [[file]] table with "
                               "`source` and `dest`.")
        for key in ("source", "dest"):
            value = raw.get(key)
            if not isinstance(value, str) or not value:
                raise Refusal(f"{path}: every [[file]] needs a `{key}` (a "
                              "non-empty string)",
                              next=f"Add `{key} = \"...\"` to that [[file]] "
                                   "row.")
        source, dest = str(raw["source"]), str(raw["dest"])
        for key, value, row, act in (("source", source, dest, "read"),
                                     ("dest", dest, source, "write")):
            if NOT_IN_A_COMPONENT in value:
                raise Refusal(
                    f"{path}: the [[file]] row for {row!r} has a `{key}` "
                    f"holding a NUL character ({value!r}), which no file name "
                    f"can hold, so `init` could not {act} it.",
                    next="Remove the NUL character — `\\u0000` in TOML — "
                         f"from that `{key}`.")
        if not _source_inside(source, os.path.dirname(path)):
            raise Refusal(
                f"template {os.path.basename(os.path.dirname(path))!r}: the "
                f"[[file]] source {source!r} lands outside the template "
                "directory. `init` copies from the template directory and "
                "nowhere else.",
                next="Fix that template's `source` so it names a file inside "
                     "the template directory.")
        if dest in seen:
            raise Refusal(f"{path}: two [[file]] rows both write {dest!r}; "
                          "`init` overwrites nothing, itself included.",
                          next="Give the two rows different `dest` paths.")
        seen.add(dest)
        rows.append(File(source, dest))
    return tuple(rows)


def _holes(document: dict[str, Any], path: str) -> tuple[Hole, ...]:
    raw_rows = document.get("hole", [])
    if not isinstance(raw_rows, list):
        raise Refusal(f"{path}: [[hole]] must be a list of tables",
                      next="Write each hole as a [[hole]] table with `name` "
                           "and `description`.")
    rows: list[Hole] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise Refusal(f"{path}: every [[hole]] must be a table",
                          next="Write each hole as a [[hole]] table with "
                               "`name` and `description`.")
        name = str(raw.get("name", "")).strip()
        if not HOLE_NAME_RE.match(name):
            raise Refusal(
                f"{path}: a [[hole]] `name` is {name!r}, which is not a hole "
                "name: a letter followed by letters, digits or underscores, "
                f"as it is spelled in a file ({spelled('NAME')}).",
                next="Spell that `name` as the word inside the "
                     f"{spelled('NAME')} fence, with no punctuation.")
        if name in seen:
            raise Refusal(f"{path}: two [[hole]] rows are both named {name!r}; "
                          "a hole is one fact with one description.",
                          next="Delete one of the two rows.")
        seen.add(name)
        description = str(raw.get("description", "")).strip()
        if not description:
            raise Refusal(
                f"{path}: [[hole]] {name!r} has no `description`. The "
                "description is the whole of what the reader has to go on "
                "when `init` prints the hole.",
                next="Add `description = \"...\"` saying what value belongs "
                     "in that hole.")
        probe: tuple[str, ...] = ()
        if "probe" in raw:
            probe = strings(raw["probe"], f"{path}: [[hole]] {name} probe")
            if not probe:
                raise Refusal(f"{path}: [[hole]] {name!r} has an empty `probe`",
                              next="Write `probe = [...]` with the argv whose "
                                   "output shows the candidates, or drop the "
                                   "key.")
        rows.append(Hole(name, description, probe))
    return tuple(rows)


# ------------------------------------------------------- where holes are spelled


class Spelling(NamedTuple):
    """What one `[[file]]` row spells: the holes in its `dest` path and the
    holes in its source's text, each in first-appearance order."""

    row: File
    in_dest: tuple[str, ...]
    in_text: tuple[str, ...]       # empty when the source is not readable
    readable: bool


def spelled_holes(template: Template) -> tuple[Spelling, ...]:
    """Every hole each file of `template` spells — the ONE walk.

    Two readers want this fact and want it labeled differently: the parity
    check names a site by its source, `init`'s output by its dest. The walk
    itself is written once, so the check and the printout cannot disagree
    about where a hole is; the callers only choose the label.
    """
    sites: list[Spelling] = []
    for row in template.files:
        text = read_text(os.path.join(template.directory, row.source))
        sites.append(Spelling(row, holes_in(row.dest),
                              holes_in(text) if text is not None else (),
                              text is not None))
    return tuple(sites)


# ---------------------------------------------------------------- the parity


def template_parity(directory: str) -> list[str]:
    """Everything wrong with one template's holes, as sentences; empty means
    parity.

    Three directions, and all three are needed. A hole SPELLED and not
    declared is a value `init` will never mention, so the reader meets it when
    the loader refuses. A hole DECLARED and spelled nowhere is a question
    asked about nothing. And a `dest` hole is the easiest of the three to
    forget, because it is in a path rather than in a file's text — so it is
    counted with the others rather than beside them.
    """
    template = load_template(directory)
    problems: list[str] = []
    declared = {hole.name for hole in template.holes}
    where: dict[str, list[str]] = {}
    for site in spelled_holes(template):
        for name in site.in_dest:
            where.setdefault(name, []).append(f"the dest of {site.row.source}")
        if not site.readable:
            problems.append(
                f"{template.name}: [[file]] source {site.row.source!r} is not "
                "a readable file of the template directory")
            continue
        for name in site.in_text:
            where.setdefault(name, []).append(site.row.source)
    for name in sorted(set(where) - declared):
        problems.append(
            f"{template.name}: {spelled(name)} is spelled in "
            + ", ".join(where[name]) + " and no [[hole]] row declares it")
    for name in sorted(declared - set(where)):
        problems.append(
            f"{template.name}: [[hole]] {name!r} is declared and spelled in no "
            "file and in no dest — a question asked about nothing")
    return problems


class TemplatesVerdict(NamedTuple):
    """`templates_verdict`'s answer: whether there are templates at all,
    whether every one of them works, the sentence that says so, and the
    `next:` of the refusal of the first template that did not load, "" where
    every one loaded."""

    present: bool
    ok: bool
    detail: str
    next: str = ""


def template_directories(directory: str) -> list[str]:
    """The names of the subdirectories of `directory`, sorted: what this
    package counts as its templates. A FILE beside them — a `.DS_Store` a
    file browser left, a README — is no template and is not listed."""
    return sorted(name for name in os.listdir(directory)
                  if os.path.isdir(os.path.join(directory, name)))


def templates_verdict(directory: str) -> TemplatesVerdict:
    """Whether there are templates under `directory`, whether every one of
    them WORKS, and the sentence that says so: each `template.toml` loads, and
    each template's spelled holes and declared holes account for each other.

    PRESENT means at least one template directory. No `directory`, and a
    `directory` holding no subdirectory, are one answer — not present —
    because `init` has nothing to write from either way and no reader acts on
    the two differently; a subdirectory that does not load is a template that
    is present and broken, which is `ok=False`.

    A directory PARAMETER, so `init`'s own check and the arm's planted control
    are the same question asked twice, and neither can answer it differently.
    Files are read and nothing is run — writing a template out and putting it
    to work is `--selftest`'s TEMPLATES group.

    Never about bytes. A user who edits a shipped template and keeps it usable
    passes here: the question is whether `init` can write from it, not whether
    it is the copy that was installed.
    """
    if not os.path.isdir(directory):
        return TemplatesVerdict(
            False, False, f"there is no templates directory at {directory}")
    names = template_directories(directory)
    if not names:
        return TemplatesVerdict(
            False, False, f"{directory} holds no template directory")
    verdicts: list[str] = []
    advice = ""
    for name in names:
        one = os.path.join(directory, name)
        try:
            template = load_template(one)
            problems = template_parity(one)
        except Refusal as refused:
            # The word the loader would print is not spelled here: this is a
            # verdict ABOUT a template, and `core.refusal_text` is the one
            # producer of `REFUSED: ` there is (arm ss walks for it).
            verdicts.append(f"{name} does not load: {refused}")
            advice = advice or refused.next
            continue
        verdicts.append(f"{name} loads, {len(template.holes)} hole(s), parity "
                        + ("clean" if not problems
                           else "RED: " + "; ".join(problems)))
    ok = all(" loads, " in verdict and "parity clean" in verdict
             for verdict in verdicts)
    return TemplatesVerdict(
        True, ok, f"{len(names)} template(s): " + "; ".join(verdicts), advice)


def refuse_usable_templates() -> None:
    """Refuse before `init` writes anything when there is no template, or
    when one that is present is broken.

    `init` is the one command that reads the templates, so it is the one
    command that asks. A reader meets the fault where the fault matters — at
    the command that would have written from it — rather than in front of a
    `capture` that never opens the directory, and the sentence names the
    template and what is wrong with it.
    """
    directory = templates_dir()
    verdict = templates_verdict(directory)
    if verdict.ok:
        return
    if not verdict.present:
        raise no_templates_refusal(directory)
    raise Refusal(
        f"`init` writes a project's files FROM a template and this install's "
        "templates are not usable: "
        f"{closed(unpunctuated(verdict.detail))}",
        next=verdict.next or BROKEN_TEMPLATE_NEXT)


def refuse_unparity(directory: str) -> Template:
    """The template at `directory`, or a refusal quoting every parity problem.

    `init` calls this rather than `load_template`, because a template that
    fails parity is not shipped and must not be written into somebody's
    project either.
    """
    problems = template_parity(directory)
    if problems:
        raise Refusal(
            "that template does not hold to hole parity: " + "; ".join(problems)
            + ".",
            next="Declare every hole its files spell, and delete the [[hole]] "
                 "rows nothing spells; --selfcheck holds every shipped "
                 "template to the same rule.")
    return load_template(directory)


# ----------------------------------------------------------------- applying


def _inside(path: str, directory: str) -> bool:
    """True when `path` lands strictly inside `directory`.

    Lexical, not `realpath`: the project directory need not exist yet, and the
    question is about the path the template asked for.
    """
    directory = os.path.abspath(directory).rstrip(os.sep)
    return os.path.abspath(path).startswith(directory + os.sep)


def _source_inside(source: str, directory: str) -> bool:
    """True when a `[[file]]` `source` names a file inside the template
    `directory`: relative, no empty, `.` or `..` component, and resolving
    strictly below the directory by `core.under`, which follows every link on
    the way, the file's own included. `dest` is held to the spelling by
    `_inside` and to the links by `_leads_out` because the project directory
    may not exist yet; the template directory does, so the one question
    `under` asks covers both."""
    return (not os.path.isabs(source)
            and all(part not in ("", os.curdir, os.pardir)
                    for part in source.split("/"))
            and under(os.path.join(directory, source), directory, strict=True))


def _leads_out(project: str, dest: str) -> str | None:
    """The highest level on the way to `dest` that resolves outside the
    project, found from the nearest level that EXISTS — or None when that
    level resolves inside, or when the project directory is not there yet
    and every level of it will be made.

    `_inside` reads the spelling and cannot see a link: a project
    subdirectory that is a link to somewhere else passes it, and the file
    lands where the link leads. So the nearest level that exists is asked of
    the filesystem through `core.under`; every level below it is made by
    `Made.makedirs` as a directory, and stays where it is made. When it
    resolves outside, the levels above it are asked up to the one whose own
    directory resolves inside: that level is the link that leads out, the
    one the reader replaces. `lexists`, so a dangling link is a level that
    exists and is asked too.
    """
    walk = os.path.dirname(dest)
    while not os.path.lexists(walk):
        if walk == project:
            return None
        walk = os.path.dirname(walk)
    if under(walk, project, strict=False):
        return None
    while not under(os.path.dirname(walk), project, strict=False):
        walk = os.path.dirname(walk)
    return walk


def _already_exists(row_dest: str) -> Refusal:
    """The refusal for a `dest` the project directory already carries — a
    file, a directory, or a link, dangling or not. ONE sentence for the two
    places that find one: the test before anything is made, and the write
    itself, which opens with `"xb"` and so refuses a link that appeared after
    the test."""
    return Refusal(
        f"{row_dest} already exists in the project directory; `init` "
        "overwrites nothing.",
        next=f"Move or delete {row_dest}, or run `init` into a "
             "directory that does not carry one yet.")


def _in_the_way(project: str, row_dest: str) -> str | None:
    """What stands where a directory has to be on the way to a `[[file]]`
    row's directory, said without an absolute path: `<path> is a file` (or
    `a link`), the path relative to the project — or None when nothing
    does."""
    walk = os.path.abspath(os.sep)
    rest = os.path.dirname(os.path.normpath(row_dest))
    for part in (project.split(os.sep) + (rest.split(os.sep) if rest else [])):
        walk = os.path.join(walk, part) if part else walk
        if os.path.lexists(walk) and not os.path.isdir(walk):
            kind = "a link" if os.path.islink(walk) else "a file"
            relative = os.path.relpath(walk, project)
            if relative == ".":
                return f"the project directory itself is {kind}"
            if relative.split(os.sep)[0] == os.pardir:
                up = relative.split(os.sep).count(os.pardir)
                return (f"{os.path.basename(walk)}, {up} level"
                        f"{'' if up == 1 else 's'} above the project directory, "
                        f"is {kind}")
            return f"{relative} inside the project directory is {kind}"
    return None


def apply(template: Template, project_dir: str, out: Any,
          made: Made | None = None) -> None:
    """Copy every `[[file]]` row into the project, holes in place, and print
    what was written and what is left to fill.

    Nothing printed here is an absolute path. A scaffolded project's first
    report is pasted into a hand-back like any other, and a tool that
    prints a home directory into one is asking the reader to redact it.

    `made` is the ledger of absolute paths this call brought into being —
    files first, then the directories that had to be created for them. It is
    the CALLER's, because `init` writes two templates and a failure in the
    second has to undo the first as well; a ledger scoped to one `apply`
    could not.
    """
    project = os.path.abspath(project_dir)
    ledger = Made() if made is None else made
    written: list[str] = []
    for row in template.files:
        source = os.path.join(template.directory, row.source)
        if not os.path.isfile(source):
            raise Refusal(
                f"template {template.name!r}: [[file]] source {row.source!r} "
                "is not a file of the template directory.",
                next="Add that file to the template directory, or drop its "
                     "[[file]] row.")
        dest = os.path.abspath(os.path.join(project, row.dest))
        if not _inside(dest, project):
            raise Refusal(
                f"template {template.name!r}: the [[file]] dest {row.dest!r} "
                "lands outside the project directory. `init` writes inside the "
                "directory it was given and nowhere else.",
                next="Fix that template's `dest` so it names a path inside the "
                     "project directory.")
        outward = _leads_out(project, dest)
        if outward is not None:
            spelled_as = os.path.relpath(outward, project)
            resolved = os.path.relpath(os.path.realpath(outward),
                                       os.path.realpath(project))
            raise Refusal(
                f"`init` cannot write {row.dest} into the project directory: "
                f"{spelled_as} inside it resolves to {resolved}, outside the "
                "project directory, and `init` writes inside the directory it "
                "was given and nowhere else, so it wrote none of the "
                "project's files.",
                next=f"Replace {spelled_as} with a directory of the project's "
                     "own, or run `init` into another directory.")
        if os.path.lexists(dest):
            raise _already_exists(row.dest)
        # Bytes, not text: a template file is copied unchanged, so the line
        # endings a project gets are the ones the template was committed with
        # and not the ones this machine would have translated them into.
        with open(source, "rb") as handle:
            data = handle.read()
        # The PROJECT's half, and only it: a directory or a file `init` cannot
        # make there is a refusal about the directory it was given — naming
        # the file relative to it, never an absolute path — and the caller's
        # ledger undoes what earlier rows wrote. A template source that
        # cannot be read, above, is not the project directory's fault.
        try:
            ledger.makedirs(os.path.dirname(dest) or project)
            # `"xb"` creates and never opens what is there, so a link that
            # appeared at `dest` after the test above is refused rather than
            # written through. Its clause is the inner one: a
            # `FileExistsError` out of `makedirs` is a file where a directory
            # has to be, which the clause below names.
            try:
                target = open(dest, "xb")
            except FileExistsError as taken:
                raise _already_exists(row.dest) from taken
            ledger.files.append(dest)
            with target:
                target.write(data)
        except OSError as unwritable:
            in_the_way = _in_the_way(project, row.dest)
            if in_the_way is not None:
                raise Refusal(
                    f"`init` cannot write into the project directory: {in_the_way}, "
                    "not a directory, so it wrote none of the project's files.",
                    next="Point `init` at a directory, or move that file out of the way."
                ) from unwritable
            if unwritable.errno == errno.ENAMETOOLONG:
                raise Refusal(
                    f"`init` cannot write {row.dest} into the project "
                    "directory: the path is too long for the file system "
                    f"({len(dest)} characters), so it wrote none of the "
                    "project's files.",
                    next="Point `init` at a directory with a shorter path."
                ) from unwritable
            raise Refusal(
                f"`init` cannot write {row.dest} into the project directory "
                f"({type(unwritable).__name__}: {unwritable.strerror}), so it "
                "wrote none of the project's files.",
                next="Point `init` at a directory you can write, or make it writable."
            ) from unwritable
        written.append(row.dest)

    out.write(f"\nINIT  {template.name}  ({len(written)} file(s)) — "
              f"{template.summary}\n")
    for dest in written:
        out.write(f"  wrote {dest}\n")
    _print_holes(template, out)


def _print_holes(template: Template, out: Any) -> None:
    spelled_in: dict[str, list[str]] = {}
    moved: dict[str, list[str]] = {}
    for site in spelled_holes(template):
        for name in site.in_dest:
            moved.setdefault(name, []).append(site.row.dest)
        for name in site.in_text:
            spelled_in.setdefault(name, []).append(site.row.dest)
    if not template.holes:
        out.write("  no holes: this template's files are complete as they "
                  "stand.\n")
        return
    # A hole is a project fact golden-census cannot know, so it is written
    # IN PLACE in the file that needs it and filled by the reader:
    # golden-census never guesses one.
    out.write(f"  {len(template.holes)} hole(s) to fill; each is written as "
              f"{spelled('NAME')} in the file named under it:\n")
    for hole in template.holes:
        out.write(f"    {hole.name} — {hole.description}\n")
        if spelled_in.get(hole.name):
            out.write("      in " + ", ".join(spelled_in[hole.name]) + "\n")
        for dest in moved.get(hole.name, []):
            out.write(f"      in the PATH of {dest} — that file was written to "
                      f"the literal {spelled(hole.name)} directory, so MOVE it "
                      "once you have filled the hole\n")
        _print_probe(hole, out)


def _print_probe(hole: Hole, out: Any) -> None:
    """A `[[hole]]`'s probe output, indented under the hole's name.

    A probe that will not run is a NOTE, never a refusal: it is a convenience
    for the reader, golden-census never reads a byte of what it prints, and a
    scaffold that refused because `xcodebuild` is not installed would be
    refusing about the machine rather than about the project.
    """
    if not hole.probe:
        return
    out.write(f"      probe: {' '.join(hole.probe)}\n")
    try:
        # No deadline of its own: golden-census keeps no clock anywhere, and a
        # probe is a command the TEMPLATE named, so how long it may run is the
        # caller's question, not this scaffolder's.
        proc = launch(list(hole.probe), f"the probe of [[hole]] {hole.name!r}")
    except Refusal as refused:
        out.write(f"        (not run: {with_next(str(refused), refused)})\n")
        return
    except Exception as exc:                       # noqa: BLE001 — see above
        out.write(f"        (not run: {type(exc).__name__}: {exc})\n")
        return
    text = (proc.stdout.strip() or proc.stderr.strip()
            or f"(no output, {ended(proc.returncode)})")
    lines = text.splitlines()
    for line in lines[:PROBE_LINES]:
        out.write(f"        {line[:DIFFERENCE]}\n")
    if len(lines) > PROBE_LINES:
        out.write(f"        … {len(lines) - PROBE_LINES} more line(s); "
                  "golden-census reads none of them\n")


# ------------------------------------------------------------- the command


def _either(names: list[str]) -> str:
    """`a`, `a or b`, `a, b or c`: file names as one phrase of a sentence."""
    return (names[0] if len(names) == 1
            else ", ".join(names[:-1]) + " or " + names[-1])


def _closing(templates: list[Template]) -> str:
    """`init`'s last line: the files golden-census REFUSES while one still
    spells a hole, and — only when it applies — the files it never looks
    into for one.

    A hole is refused in a file golden-census READS AS ITS OWN, which is the
    neutral three: the manifest and the census every command that runs a
    subject reads, and the mutants file `mutants` reads. A template's own
    files — a runner, a wrapper — are the subject's, run and never searched
    for a hole, so one left there is not refused: the run it breaks is
    recorded like any other, at exit 0. The clause that says so names them,
    and only those whose TEXT spells a hole, so it is printed only when it
    applies: `init` with no template, or with one whose files carry no hole
    in their text, says nothing about a file it did not write.
    """
    read = [row.dest for row in templates[0].files]
    unread = [site.row.dest for template in templates[1:]
              for site in spelled_holes(template) if site.in_text]
    line = (f"\n  Fill every hole above. Commands that read {_either(read)} "
            f"refuse one that still spells {spelled('NAME')}")
    if unread:
        line += (f"; none checks {_either(unread)}, so a hole left there is "
                 "not refused and a capture records the run it breaks")
    return line + ".\n"


def _shown_name(name: str) -> str:
    """A name or a directory the reader typed, as a refusal quotes it: written
    with `repr`, so one that holds a newline stays on one line, cut at
    `DIFFERENCE` characters, with ` …` after the closing quote when
    something was cut."""
    return repr(name[:DIFFERENCE]) + (" …" if len(name) > DIFFERENCE else "")


def init(directory: str | None, template_name: str | None, listing: bool,
         out: Any) -> int:
    """`golden-census init` — the whole command. 0 written, 2 REFUSED.

    The neutral three are written first and always: a template adds a runner
    and, where the tool needs one, a wrapper, and neither is a project's
    manifest, census or mutants file.

    The templates are checked first, before either form writes or prints a
    line: they are a precondition of this command and of no other, and an
    install that lost them or carries a truncated one refuses here.
    """
    refuse_usable_templates()
    if listing:
        if directory is not None:
            raise Refusal(
                f"`init --list` prints the shipped templates and writes "
                f"nothing, so it takes no directory ({_shown_name(directory)} was "
                "given).",
                next="Run `init --list` with no directory, or drop --list to "
                     "write into that directory.")
        if template_name is not None:
            raise Refusal(
                "`--list` and `--template` cannot be combined: `init --list` "
                "prints the shipped templates and writes nothing, so it "
                f"takes no --template ({_shown_name(template_name)} was "
                "given).",
                next="Run `init --list` alone to see the shipped templates, "
                     "or `init <dir> --template NAME` without --list to "
                     "write one of them.")
        out.write("\nTEMPLATES\n")
        for name in shipped_templates():
            out.write(f"  {name} — "
                      f"{load_template(os.path.join(templates_dir(), name)).summary}\n")
        return EXIT_OK
    if directory is None:
        raise Refusal(
            "`init` needs the directory to write the project's files into.",
            next="Run `init <dir>`, or `init --list` to see the shipped "
                 "templates.")
    chosen = [template_dir(NEUTRAL)]
    if template_name is not None and template_name != NEUTRAL:
        chosen.append(template_dir(template_name))
    templates = [refuse_unparity(one) for one in chosen]
    # ALL OR NOTHING across both passes. A refusal in the second — a dest the
    # directory already carries is the common one — leaves the project exactly
    # as `init` found it, so the thing to do about the refusal is the thing
    # the sentence says and not "and now delete the three files it left".
    made = Made()
    # The page is held until both passes have written: a refusal in the
    # second undoes the first pass's files, and a `wrote` line printed for
    # one of them would name a file the directory no longer holds.
    page = io.StringIO()
    try:
        for template in templates:
            apply(template, directory, page, made)
        out.write(page.getvalue())
        out.write(_closing(templates))
    except BaseException:
        # Every way out, not only a refusal: a reader such as `head` closing
        # standard output mid-listing raises `BrokenPipeError` after the
        # files are written, and all-or-nothing has to hold there too — up
        # to the last line this command prints.
        made.undo()
        raise
    return EXIT_OK
