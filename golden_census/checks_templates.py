"""The arms over `templates/` and `init`: whether there are templates and
that each of them works, the hole-parity rule going red four ways, the shipped
templates as they stand, and the round trip from an empty directory to a
refusal naming the first hole.
"""

from __future__ import annotations

import functools
import io
import os
import pathlib
import re
import shlex
import shutil
import stat
import tomllib
from collections.abc import Callable
from typing import Any, NamedTuple

from .census import (
    load_census,
)
from .cli import main
from .controls import CheckRow, SkipRow
from .core import (
    ACTUAL,
    DIFFERENCE,
    IMPORT_NAME,
    Made,
    holes_in,
    read_text,
    Refusal,
    spelled,
    under,
)
from .manifest import load_manifest
from .mutants import load_mutants
from .probe import probe
from .proof import (
    _STUB_CENSUS,
    _STUB_MANIFEST,
    _box,
    _heard,
    _one_line,
    _quietly,
    _scratch,
)
from .templates import (
    BROKEN_TEMPLATE_NEXT,
    NEUTRAL,
    TEMPLATES_ABSENT,
    TemplatesVerdict,
    File,
    Template,
    apply,
    init,
    load_template,
    refuse_unparity,
    shipped_templates,
    template_dir,
    template_directories,
    template_parity,
    templates_dir,
    templates_verdict,
)
from .checks_base import (
    PACKAGE,
    _capture_broke,
    _fresh_module,
    _NO_FILE_ROOM_ERROR,
    _printed_refusal,
    _READ_ONLY_DIRECTORY,
    _READ_ONLY_FILE,
    _modes_planted,
    _refused_by,
    _without_file_room,
    _writable_copy,
)

# ----------------------------------------------------------- the templates
#
# `bbbb` is the one that says whether there ARE templates. They are part of
# the install and optional to the app: `init` writes a project's files FROM a
# template and refuses without one, which `mmmmm` at the foot of this file is
# about, and every other command runs without them — so an absent or empty
# `templates/` is a disclosed SKIP here, and a template that is present and
# does not load is a red row. `ww` is the parity rule itself, on scratch
# templates that arm writes: three reds and a green, so the check is not
# simply always one or the other. `xx` is the SHIPPED neutral three, held to
# the same rule and to the one thing a template file must be before anything
# else — a document `tomllib` parses with its holes still in it.


def _plant_truncated(copy: str) -> str:
    """Plant, into a templates directory the arm already copied, a stray
    `.DS_Store` and one `template.toml` truncated; return that template's name.

    The stray file is the first NAME in sorted order, where the truncation must
    not land and neither the verdict nor `init` may take it for a template.
    The truncated file still opens and no longer parses: the shape a
    half-written copy or a truncated download arrives in. The copy and what a
    failure means stay each arm's.
    """
    pathlib.Path(os.path.join(copy, ".DS_Store")).write_bytes(b"Bud1\x00")
    cut = template_directories(copy)[0]
    pathlib.Path(os.path.join(copy, cut, "template.toml")).write_text(
        'name    = "' + cut + '"\n[[file]]\nsource = ', encoding="utf-8")
    return cut


def _copy_refused(error: OSError) -> TemplatesVerdict:
    """Arm bbbb's verdict on a copy of the templates that raised: present and
    ok, which the arm reads as red, quoting the error, which names the path
    in the operating system's words."""
    return TemplatesVerdict(True, True, (
        f"the copy could not be made ({type(error).__name__}: {error})"))


def _copy_truncated(source: str, copy: str) -> tuple[str, TemplatesVerdict]:
    """Arm bbbb's broken copy: `source` copied to `copy` by `_writable_copy`,
    `_plant_truncated` into it, and `templates_verdict` on it; where the copy
    or the plant raises, `_copy_refused`'s verdict. With the name of the
    template truncated, "" where none was."""
    cut = ""
    try:
        _writable_copy(source, copy)
        cut = _plant_truncated(copy)
        return cut, templates_verdict(copy)
    except OSError as exc:
        return cut, _copy_refused(exc)


def _templates_present_control(check: CheckRow, skip: SkipRow) -> None:
    """(bbbb) the templates beside the package are reported, never assumed:
    when there are some, every one works; when there are none, the row says so.

    A SKIP, never a pass and never a failure, when none is present — the same
    shape arms `xx` and `hhh` disclose, because there is nothing for any of
    them to describe. When some are present the row is a check, and its
    planted cases are the rule itself: a copy with one `template.toml`
    truncated is present and broken, naming that template; an empty directory
    and a path that does not exist are both NOT present. `mmmmm` is the arm
    that says `init` itself refuses in both cases.

    The truncation is planted a second time, on the copy of a templates
    directory an install keeps read-only: a copy of the templates under a
    package of the arm's own, every directory put at 0555 and every file at
    0444, as arm ttttttt plants the bundled fixture. The planted modes are
    asked once the copy is made, so a fix that makes the source writable
    rather than its copy is red, and again once a `finally` has put them
    back. Root writes in a 0555 directory: where a directory can be made
    inside the planted templates, the plant does not bite, and the read-only
    copy alone is not exercised. The row's detail says so, and the verdict
    reads that sentence in the detail; every other verdict of the row
    stands, so a broken template is red under root as anywhere else.

    The verdict comes from `templates.templates_verdict`, which is what `init`
    asks: one question, one owner, and a control that cannot drift from the
    command it is about.
    """
    label = ("bbbb  the templates beside the package are reported and never "
             "assumed: when there are some, every one WORKS — each "
             "template.toml loads and every hole its files spell is a hole it "
             "declares, files read and nothing run — and a copy with one "
             "template.toml truncated goes RED naming it, and so does a copy "
             "of a planted read-only templates directory — every directory "
             "at 0555 and every file at 0444, an install's modes — every "
             "planted path still at its read-only mode once the copy is "
             "made, asked of `os.stat` while the plant is in force, and back "
             "at its own mode afterwards, asked of `os.stat` once the plant "
             "is undone; where a directory can be made inside the planted "
             "templates directory at 0555, which is what running as root "
             "looks like, that read-only copy alone is NOT exercised, the "
             "detail says so, and every other verdict of the row stands; an "
             "empty or absent "
             "templates directory is NO templates, which is a disclosed SKIP "
             "of this row and a refusal at `init`, the one command that writes "
             "from them")
    live = templates_verdict(templates_dir())
    if not live.present:
        skip(label, f"{live.detail}: {TEMPLATES_ABSENT}. Nothing was read and "
                    "nothing is claimed.")
        return
    with _box("golden-census-essential-") as box:
        cut, broken = _copy_truncated(templates_dir(),
                                      os.path.join(box, "templates"))
        read_only = os.path.join(box, IMPORT_NAME, "templates")
        held: tuple[str, TemplatesVerdict] | None = None
        planted: dict[str, int] = {}
        before: dict[str, int] = {}
        on_return: dict[str, int] = {}
        try:
            shutil.copytree(templates_dir(), read_only)
        except OSError as exc:
            # The same answer as the first copy's: a red verdict naming the
            # path, and no plant on a copy that was not made.
            held = ("", _copy_refused(exc))
        else:
            for directory, _names, files in os.walk(read_only):
                planted[directory] = _READ_ONLY_DIRECTORY
                planted.update({os.path.join(directory, name): _READ_ONLY_FILE
                                for name in files})
            before = {path: stat.S_IMODE(os.stat(path).st_mode)
                      for path in planted}
            probe = os.path.join(read_only, "probe")
            with _modes_planted(planted, before, probe) as bites:
                if bites:
                    held = _copy_truncated(
                        read_only, os.path.join(box, "read-only-copy"))
                    on_return = {path: stat.S_IMODE(os.stat(path).st_mode)
                                 for path in planted}
        # Asked AFTER the block that puts the modes back, so a plant left
        # read-only is a red entry here and not a silent reset by the box's
        # removal.
        after = {path: stat.S_IMODE(os.stat(path).st_mode)
                 for path in planted}
        not_held = [f"{os.path.relpath(path, read_only)} {mode:o}"
                    for path, mode in on_return.items()
                    if mode != planted[path]]
        not_back = [f"{os.path.relpath(path, read_only)} {mode:o}"
                    for path, mode in after.items() if mode != before[path]]
        empty = os.path.join(box, "no-templates")
        os.makedirs(empty)
        emptied = templates_verdict(empty)
        gone = templates_verdict(os.path.join(box, "not-there"))
    if held is None:
        # Root writes in a 0555 directory, and so does a file system that
        # keeps no modes: no copy of the plant can be refused there. That
        # clause alone is not exercised, and the detail says so; every other
        # verdict of the row stands.
        held_ok = False
        held_said = ("-> not exercised: a directory could be made inside the "
                     "planted templates directory at 0555, which is what "
                     "running as root looks like, so no copy of it was made "
                     "and none can be refused")
        held_modes = ""
    else:
        held_cut, held_broken = held
        held_ok = (held_broken.present and not held_broken.ok
                   and held_cut in held_broken.detail and not not_held)
        held_said = (f"with {held_cut or '(none)'}/template.toml truncated -> "
                     f"present={held_broken.present}, {held_broken.detail}")
        held_modes = (f"not at their read-only mode once the copy was made "
                      f"{not_held}, ")
    detail = (f"{ACTUAL}{live.detail}; the copy with {cut or '(none)'}"
              f"/template.toml truncated -> present={broken.present}, "
              f"{broken.detail}; the copy of the read-only templates "
              f"{held_said}; planted paths {held_modes}not back at their own "
              f"mode afterwards {not_back}; an empty templates directory -> "
              f"present={emptied.present}, {emptied.detail}; a path that does "
              f"not exist -> present={gone.present}, {gone.detail}")
    # Under root the read-only clause holds by its disclosure alone, so the
    # verdict reads that sentence in the detail as it is printed.
    read_only_ok = not not_back and (
        held_ok if held is not None else "-> not exercised: " in detail)
    # The advice of a red read-only clause names what went wrong in it: a
    # copy that was made and not refused, and a mode not put back. Where no
    # copy was made — root, or a file system that keeps no modes — there is
    # no copy to advise about.
    advice = ([] if held is None or held_ok else [
        "Copy the templates with `checks_base._writable_copy`, and give the "
        "owner's write bit there to every directory and file of the copy and "
        "to nothing of the source."]) + ([
        "A mode not back at its own value is this arm's fault: "
        "`checks_base._modes_planted` puts it back in a `finally`."]
        if not_back else [])
    check(label,
          live.ok and broken.present and not broken.ok and cut in broken.detail
          and read_only_ok and not emptied.present and not gone.present,
          detail,
          # A plain copy that could not be made planted nothing: the error it
          # quotes is the templates', as the first copy's is.
          next=(BROKEN_TEMPLATE_NEXT if read_only_ok or not planted
                else " ".join(advice)))


def _parity_case(box: str, name: str, declared: tuple[str, ...], text: str,
                 dest: str) -> list[str]:
    """One scratch template, and what `template_parity` says about it."""
    directory = os.path.join(box, name)
    os.makedirs(directory)
    rows = [f'name    = "{name}"',
            'summary = "a scratch template the parity arm writes for itself"',
            "", "[[file]]", 'source = "one.toml"', f'dest   = "{dest}"']
    for hole in declared:
        rows += ["", "[[hole]]", f'name        = "{hole}"',
                 'description = "declared by the scratch template"']
    for leaf, body in (("template.toml", "\n".join(rows) + "\n"),
                       ("one.toml", text)):
        pathlib.Path(os.path.join(directory, leaf)).write_text(body, encoding="utf-8")
    return template_parity(directory)


def _template_parity_control(check: CheckRow) -> None:
    """(ww) the template parity rule, going red three ways and green once.

    A template that fails parity is not shipped and is not written into
    anybody's project either, so this is the guard `init` stands on — and a
    guard nobody has watched go red is a zero result, not a clean one.
    """
    one = f'a = "{spelled("DECLARED")}"\n'
    with _box("golden-census-parity-") as box:
        clean = _parity_case(box, "clean", ("DECLARED",), one, "one.toml")
        spelled_case = _parity_case(box, "spelled", ("DECLARED",),
                                    one + f'b = "{spelled("STRANGER")}"\n',
                                    "one.toml")
        orphan = _parity_case(box, "orphan", ("DECLARED", "ORPHAN"), one,
                              "one.toml")
        in_dest = _parity_case(box, "indest", ("DECLARED",), one,
                               f"{spelled('WHERE')}/one.toml")
    reds = [
        ("spelled and not declared", spelled_case, "STRANGER", "declares it"),
        ("declared and spelled nowhere", orphan, "ORPHAN", "in no dest"),
        ("a dest hole not declared", in_dest, "WHERE", "the dest of"),
    ]
    ok = clean == [] and all(
        len(problems) == 1 and name in problems[0] and needle in problems[0]
        for _label, problems, name, needle in reds)
    check("ww  template hole parity goes red three ways on scratch templates "
          "this arm writes — a hole spelled and declared by no [[hole]] row, a "
          "[[hole]] row nothing spells, and a hole in a `dest` PATH rather "
          "than in a file's text — each naming that hole and nothing else; and "
          "green on a clean template, so the rule is not simply always red",
          ok,
          f"{ACTUAL}clean={clean}; "
          + "; ".join(f"{label} -> {problems}" for label, problems, _n, _x
                      in reds))


def _neutral_template_control(check: CheckRow, skip: SkipRow) -> None:
    """(xx) the SHIPPED neutral three, as they stand beside the package."""
    label = ("xx  the shipped neutral template is first in the list, writes "
             "the three files every project has, each of them parses under "
             "`tomllib` WITH ITS HOLES STILL IN IT — the holes live inside "
             "strings, so a scaffolded project is a readable TOML document "
             "before a single one is filled — each carries at least one hole, "
             "and the template holds to hole parity")
    try:
        shipped = shipped_templates()
        directory = os.path.join(templates_dir(), NEUTRAL)
        template = load_template(directory)
    except Refusal as refused:
        skip(label, f"{refused} Nothing was read and nothing is claimed.")
        return
    problems = template_parity(directory)
    parsed: dict[str, str] = {}
    holes: dict[str, tuple[str, ...]] = {}
    for row in template.files:
        path = os.path.join(directory, row.source)
        try:
            with open(path, "rb") as handle:
                tomllib.load(handle)
            parsed[row.source] = "parses"
        except (OSError, tomllib.TOMLDecodeError) as exc:
            parsed[row.source] = f"{type(exc).__name__}: {exc}"
        text = read_text(path)
        holes[row.source] = holes_in(text) if text is not None else ()
    check(label,
          shipped[0] == NEUTRAL and len(template.files) == 3
          and all(verdict == "parses" for verdict in parsed.values())
          and all(names for names in holes.values()) and not problems,
          f"{ACTUAL}{len(shipped)} template(s) shipped {shipped}, "
          + ", ".join(f"{name} {verdict} with {len(holes[name])} hole(s)"
                      for name, verdict in parsed.items())
          + f"; parity {problems or 'clean'}")


#: A template name one character longer than a printed line holds, which a
#: refusal quotes cut.
_LONG_NAME = "n" * (DIFFERENCE + 1)

#: A template name that holds a quote and a newline, which a refusal quotes
#: with `repr` so that it stays on the line it is written on.
_ODD_NAME = "it's\nodd"

#: The names `--list` is given a --template of, in arm `yy`: the neutral
#: template, a name no template has, the empty string, a name longer than a
#: printed line holds and the name above. None of them is looked up.
_COMBINED_NAMES = (NEUTRAL, "no-such-template", "", _LONG_NAME, _ODD_NAME)


def _init_control(check: CheckRow, skip: SkipRow) -> None:
    """(yy) every refusal `init` owes, and the one property its clean block
    states, in one row.

    `init` writes into somebody's project, which is the one place in this
    package where a wrong guess is not a bad golden but a lost file. So the
    six verdicts here are all about NOT writing: over a file that is there,
    from a template that is not, outside the directory it was given, and for
    the flag that prints instead of writing — given a directory, and given a
    --template.

    `--list` given a --template is asked five times, because the name is
    never looked up: the neutral template, a name no template has, the
    empty string, a name longer than a printed line holds and a name that
    holds a quote and a newline are each refused in the same words, the
    fourth with its name cut at `DIFFERENCE` characters and ` …` after it,
    the fifth written with `repr` and so printed in as many lines as the
    first, and none of the five prints the list. Given a directory as well,
    the refusal is the directory's. The five are asked again through the
    command line, `cli.main` itself, with the two flags in either order,
    because the flags reach `init` only through the parser and `cli.main`: a
    check of `init` alone cannot see a flag dropped on the way, nor the exit
    code the reader gets. Each must exit 2, print no list, and print a
    refusal that carries the same words.

    The same two flags, asked of a copy of `init` whose templates directory
    is not there, are refused for the missing templates: the templates are
    a precondition of the command and are checked before either form reads
    its arguments, so the refusal names the directory and the pair's words
    are not in it.

    The seventh verdict is about what the clean `init` PRINTS: its block
    carries all four of its parts. That the block names no absolute path —
    the `wrote` lines name a dest relative to the project — is asserted
    nowhere: the two-root arm `eee` prices `capture` alone, and no arm prices
    `init` under two temp roots.
    """
    label = ("yy  `init` refuses six ways and writes nothing in any of them: "
             "a `dest` that already exists, naming the file; an unknown "
             "--template, listing the shipped ones; a directory with no "
             "template.toml in it; a `dest` that lands OUTSIDE the project "
             "directory; `--list` given a directory, which prints a refusal "
             "naming the directory and no list, with a --template beside the "
             "directory or without one; and `--list` given a --template — "
             "the neutral one, an unknown one, the empty string, a name "
             "longer than a printed line, quoted cut, and a name holding a "
             "quote and a newline, quoted on as many lines as the others — "
             "which prints no list, names both flags and the name given, says they "
             "cannot be combined and that `init --list` takes no --template, "
             "and carries a `next:` that says to run `init --list` alone or "
             "`init <dir> --template NAME` without --list; through the "
             "command line, with the two flags in either order, each of the "
             "five exits 2 and prints that refusal and no list; and with the "
             "templates directory gone, the same two flags are refused for "
             "the missing directory, which the refusal names, and not for "
             "the pair. The first, "
             "clean `init` in the same scratch box writes the neutral three, "
             "so the row is not simply always red, and that block carries "
             "all four of its parts")
    try:
        shipped = shipped_templates()
    except Refusal as refused:
        skip(label, f"{refused} There is no template to write, so none of the "
                    "six refusals can be exercised. Nothing is claimed.")
        return
    with _box("golden-census-init-") as box:
        project = os.path.join(box, "project")
        printed = io.StringIO()
        first = init(project, None, False, printed)
        block = printed.getvalue()
        wrote = sorted(os.listdir(project))
        empty = os.path.join(box, "not-a-template")
        os.makedirs(empty)
        source = os.path.join(box, "escape-source.toml")
        pathlib.Path(source).write_text("a = 1\n", encoding="utf-8")
        escaping = Template("escaping", "a scratch template written by arm yy",
                            box, (File("escape-source.toml",
                                       "../escaped.toml"),), ())
        elsewhere = os.path.join(box, "elsewhere")
        verdicts = {
            "an existing dest":
                _refused_by(lambda: init(project, None, False, io.StringIO())),
            "an unknown --template":
                _refused_by(lambda: init(elsewhere, "no-such-template", False,
                                         io.StringIO())),
            "no template.toml": _refused_by(lambda: load_template(empty)),
            "a dest outside the project":
                _refused_by(lambda: apply(escaping, elsewhere, io.StringIO())),
            "--list with a directory":
                _refused_by(lambda: init(project, None, True, io.StringIO())),
            "--list with a directory and a --template":
                _refused_by(lambda: init(elsewhere, NEUTRAL, True,
                                         io.StringIO())),
        }
        combined: dict[str, tuple[str, str]] = {}
        for name in _COMBINED_NAMES:
            listed = io.StringIO()
            combined[name] = (
                _printed_refusal(
                    functools.partial(init, None, name, True, listed)),
                listed.getvalue())
        through = {
            shlex.join(argv): (name, *_quietly(main, argv))
            for name in _COMBINED_NAMES
            for argv in (["init", "--list", "--template", name],
                         ["init", "--template", name, "--list"])}
        absent = os.path.join(box, "templates-moved-away")
        moved_copy, moved_code, moved_text = _init_without_templates(
            absent, ["init", "--list", "--template", "x"])
        left = os.path.isfile(os.path.join(box, "escaped.toml"))
        made = os.path.isdir(elsewhere)
    if moved_copy is None:
        skip(label, "this install carries no importable `templates` or `cli` "
                    "source to build a second copy from, so the refusal with "
                    "the templates gone cannot be asked for. Nothing is "
                    "claimed.")
        return
    needles = {
        "an existing dest": ("manifest.toml", "overwrites nothing"),
        "an unknown --template": ("no-such-template", NEUTRAL),
        "no template.toml": ("template.toml", "is not a template"),
        "a dest outside the project": ("../escaped.toml",
                                       "outside the project directory"),
        "--list with a directory": ("--list", "takes no directory"),
        "--list with a directory and a --template": ("--list",
                                                     "takes no directory"),
    }
    # What each refusal of `--list` with a --template has to carry, called or
    # printed by the command line, and what of it each one lacks. The name is
    # looked for as the sentence quotes it: whole, or cut at `DIFFERENCE`
    # characters with ` …` after its closing quote.
    def shown(name: str) -> str:
        return repr(name[:DIFFERENCE]) + (" …" if len(name) > DIFFERENCE
                                          else "")

    def lacks(name: str, text: str) -> list[str]:
        return [needle for needle in (
                    "REFUSED: ", "`--list` and `--template`",
                    "cannot be combined", "takes no --template",
                    f"({shown(name)} was given)", "\n  next: ",
                    "`init --list` alone", "without --list")
                if needle not in text]
    lacking = {name: lacks(name, printed_as)
               for name, (printed_as, _) in combined.items()}
    lacking_through = {argv: lacks(name, printed)
                       for argv, (name, _, printed) in through.items()}
    # The name that holds a newline is printed in the lines the others are:
    # a refusal that quotes it as typed breaks over two.
    odd_lines = {name: len(printed_as.splitlines())
                 for name, (printed_as, _) in combined.items()
                 if name in (NEUTRAL, _ODD_NAME)}
    one_line = odd_lines[_ODD_NAME] == odd_lines[NEUTRAL]
    templates_first = (moved_code == 2 and absent in moved_text
                       and "cannot be combined" not in moved_text
                       and "TEMPLATES" not in moved_text)
    # The four parts, asserted present: a `wrote` line that printed nothing
    # would satisfy every claim about what the block does NOT carry.
    shape = (block.startswith("\nINIT  ")
             and block.count("\n  wrote ") == len(wrote)
             and "hole(s) to fill" in block
             and "Fill every hole above" in block)
    ok = (first == 0 and wrote == ["census.toml", "manifest.toml",
                                   "mutants.toml"]
          and not left and not made
          and all(all(needle in verdicts[key] for needle in wanted)
                  for key, wanted in needles.items())
          and not any(lacking.values())
          and not any(listed for _, listed in combined.values())
          and all(code == 2 and "TEMPLATES" not in printed
                  for _, code, printed in through.values())
          and not any(lacking_through.values())
          and one_line and templates_first
          and shape)
    check(label, ok,
          f"{ACTUAL}{len(shipped)} template(s) shipped; the first init exited "
          f"{first} and wrote {wrote}; "
          + "; ".join(f"{key} -> {_one_line(text, 110)!r}"
                      for key, text in verdicts.items())
          + "".join(f"; --list with --template {name!r} -> "
                    f"{_one_line(printed_as, 60)!r}, which lacks "
                    f"{lacking[name] or 'nothing'} and printed "
                    f"{len(listed.splitlines())} line(s)"
                    for name, (printed_as, listed) in combined.items())
          + "".join(f"; `{_spelled(argv)}` -> exit {code}, printed "
                    f"{len(printed.splitlines())} line(s), which lack "
                    f"{lacking_through[argv] or 'nothing'}"
                    f"{' and hold the list' if 'TEMPLATES' in printed else ''}"
                    for argv, (_, code, printed) in through.items())
          + f"; the name with a quote and a newline is printed in "
            f"{odd_lines[_ODD_NAME]} line(s) against the neutral name's "
            f"{odd_lines[NEUTRAL]}; with the templates directory moved away, "
            f"`init --list --template x` -> exit {moved_code}, names that "
            f"directory={absent in moved_text}, is the pair's refusal="
            f"{'cannot be combined' in moved_text}"
          + f"; a file left outside the project={left}, a directory made by a "
          f"refused init={made}"
          f"; the clean block is {len(block.splitlines())} line(s), all four "
          f"parts present={shape}")


def _spelled(text: str) -> str:
    """`text` with every character that does not print written as `repr`
    writes it, so a name that holds a newline stays on the detail's one line."""
    return "".join(char if char.isprintable() else repr(char)[1:-1]
                   for char in text)


#: A mutants file the hole arm can load twice: once as it stands, and once
#: with its `golden` replaced by a hole. Nothing is planted from it — the arm
#: is about the LOAD, which is where a hole is caught.
_LOADABLE_MUTANTS = '''\
[checks.comparator]
builtin = "compare"
golden  = "golden"

[[mutant]]
name    = "the row count every surface carries"
file    = "stub.py"
find    = "ROWS = 3"
replace = "ROWS = 4"
expect  = ["comparator"]
'''


def _names_the_way(text: str) -> bool:
    """True when the no-output-path refusal's text carries the way forward, in
    the order a reader needs it: the token first, with the word that it has
    to be quoted, because a forgotten `<WRITES>` is the commoner cause, then
    the flag. The pipe form for a command that only prints follows them.
    """
    return ("Put <WRITES> where" in text
            and "quote it" in text
            and "--writes-env" in text
            and (text.index("Put <WRITES> where")
                 < text.index("name the variable with --writes-env")))


def _hole_refusal_control(check: CheckRow, skip: SkipRow) -> None:
    """(zz) an unfilled hole is refused by every file golden-census reads and by
    the command `probe` is handed — and the same four, filled, are not.

    Both halves, because a gate that refused everything would look exactly
    like this one from the red side. The negative half for `probe` is that a
    hole-free command reaches the NEXT rule (the one about `<WRITES>`) rather
    than that it runs: whether a candidate runs is arms mm-rr's question, and
    it needs a temp root this machine may not have.
    """
    label = ("zz  an unfilled hole is REFUSED by `load_manifest`, "
             "`load_census`, `load_mutants` and `probe`, each naming the hole "
             "and the file it is in — the command, for `probe` — before the "
             "file is parsed and before anything is run; and the same four "
             "with their holes filled are not refused for a hole: the three "
             "load, and the hole-free command reaches the next rule — whose "
             "refusal names the way forward in the order a reader needs it, "
             "<WRITES> first because a forgotten token is the commoner "
             "cause, then --writes-env")
    holed: dict[str, str] = {}
    clean: dict[str, str] = {}
    with _box("golden-census-holes-") as box:
        filled_dir = os.path.join(box, "filled")
        holed_dir = os.path.join(box, "holed")
        _scratch(filled_dir, extra={"mutants.toml": _LOADABLE_MUTANTS})
        _scratch(
            holed_dir,
            manifest_text=_STUB_MANIFEST.replace(
                'name    = "stub"', f'name    = "{spelled("SUBJECT_NAME")}"'),
            census_text=_STUB_CENSUS.replace(
                'value       = "80"', f'value       = "{spelled("WIDTH")}"'),
            extra={"mutants.toml": _LOADABLE_MUTANTS.replace(
                'golden  = "golden"', f'golden  = "{spelled("GOLDEN")}"')})
        readers: tuple[tuple[str, str, Callable[[str], Any], str], ...] = (
            ("a manifest", "manifest.toml", load_manifest, "SUBJECT_NAME"),
            ("a census", "census.toml", load_census, "WIDTH"),
            ("a mutants file", "mutants.toml", load_mutants, "GOLDEN"))
        for what, leaf, reader, _hole in readers:
            for verdicts, where in ((holed, holed_dir), (clean, filled_dir)):
                verdicts[what] = _refused_by(
                    functools.partial(reader, os.path.join(where, leaf)))
        holed["a probed command"] = _refused_by(
            lambda: probe(["mytool", "--out", spelled("OUTPUT")], io.StringIO()))
        clean["a probed command"] = _refused_by(
            lambda: probe(["mytool", "--out", "somewhere"], io.StringIO()))
        # The same refusal AS PRINTED, because what this half asserts is the
        # WAY FORWARD and the way forward is the `next:` line, which
        # `str(Refusal)` does not carry and `core.refusal_text` is the one
        # producer of.
        forward = _printed_refusal(
            lambda: probe(["mytool", "--out", "somewhere"], io.StringIO()))

    named = all(spelled(hole) in holed[what] and leaf in holed[what]
                for what, leaf, _reader, hole in readers)
    probed = (spelled("OUTPUT") in holed["a probed command"]
              and "the probed command" in holed["a probed command"])
    # The next rule's refusal, and the WAY FORWARD it names: `<WRITES>` or
    # `--writes-env` first, because a forgotten token is the commoner cause,
    # and then the pipe, because a command that only prints has no token to
    # forget and is the reader this sentence was added for.
    # The positive control for that reading: the same predicate over the
    # MESSAGE alone — all `str(Refusal)` carries — must answer False. A
    # way-forward check that passed on a text with no way forward in it would
    # pass on anything.
    blind = _names_the_way(clean["a probed command"])
    quiet = (all(clean[what] == "NOT REFUSED"
                 for what, _leaf, _reader, _hole in readers)
             and "HOLE" not in forward
             and "names no output path" in forward
             and _names_the_way(forward) and not blind)
    check(label, named and probed and quiet,
          ACTUAL + "with holes — "
          + "; ".join(f"{what} -> {_one_line(text, 105)!r}"
                      for what, text in holed.items())
          + "; filled — "
          + "; ".join(f"{what} -> {_one_line(text, 70)!r}"
                      for what, text in clean.items())
          + f"; the way forward, as PRINTED -> {_names_the_way(forward)} "
          + f"({_one_line(forward, 150)!r}); the same predicate over the "
          + f"message alone -> {blind}")


def _round_trip_control(check: CheckRow, skip: SkipRow) -> None:
    """(aaa) `init` into a scratch directory, then golden-census pointed at what
    it just wrote: the whole loop an adopter's first minute is.

    The verdict is the WHOLE of what the command printed, not a returned
    object: a scaffolded project's first run must be one sentence naming the
    first hole, with no self-check block in front of it, because the manifest
    is read before the controls are run. What IS in front of it is the one
    line every run that launches anything opens with, and this arm is where
    that ordering is asserted for a refusal: the group is named before the
    thing that refuses, or a run that crashed before refusing would leave
    orphans nobody could find.
    """
    label = ("aaa  the round trip: `init` into a scratch directory, then "
             "`--selfcheck --manifest` on the manifest it just wrote, is exit "
             "2 and ONE refusal naming the manifest's first hole — nothing in "
             "front of it but the line naming the run's process group, "
             "because the file is read before the controls run; and `init`'s "
             "last line names the three files a command REFUSES while a hole "
             "is left in one, and with `--template python-function` names "
             "runner.py as a file no command looks into for one, whose hole "
             "is not refused, and with `--template swift-package` names its "
             "runner's dest, hole and all — a clause the neutral `init` does "
             "not print")
    try:
        shipped_templates()
    except Refusal as refused:
        skip(label, f"{refused} There is nothing to scaffold, so the round "
                    "trip cannot be made. Nothing is claimed.")
        return
    with _box("golden-census-roundtrip-") as box:
        project = os.path.join(box, "project")
        said_neutral = io.StringIO()
        wrote = init(project, None, False, said_neutral)
        said_runner = io.StringIO()
        wrote_runner = init(os.path.join(box, "runner"), "python-function",
                            False, said_runner)
        said_swift = io.StringIO()
        wrote_swift = init(os.path.join(box, "swift"), "swift-package",
                           False, said_swift)
        manifest_path = os.path.join(project, "manifest.toml")
        first = (holes_in(read_text(manifest_path) or "") or ("",))[0]
        code, said = _quietly(main, ["--selfcheck", "--manifest",
                                     manifest_path])
        printed = said.strip().splitlines()
    opener = printed[0] if printed else ""
    text = "\n".join(printed[1:]).strip()
    last = (said_neutral.getvalue().splitlines() or [""])[-1]
    last_runner = (said_runner.getvalue().splitlines() or [""])[-1]
    last_swift = (said_swift.getvalue().splitlines() or [""])[-1]
    three = ("Fill every hole above. Commands that read manifest.toml, "
             "census.toml or mutants.toml refuse one that still spells")
    unread = ("; none checks runner.py, so a hole left there is not "
              "refused")
    swift = (f"; none checks {spelled('TEST_TARGET_DIR')}"
             "/GoldenCensusRunner.swift, so a hole left there is not refused")
    closing = (three in last and "none checks" not in last
               and three in last_runner and unread in last_runner
               and three in last_swift and swift in last_swift)
    check(label,
          wrote == 0 and code == 2 and opener.startswith("process group ")
          and "kill -- -" in opener and text.startswith("REFUSED:")
          and bool(first) and spelled(first) in text and "next:" in text
          and "[PASS]" not in text and wrote_runner == 0 and wrote_swift == 0
          and closing,
          f"{ACTUAL}init exited {wrote}, the first hole of the manifest is "
          f"{spelled(first)}, `--selfcheck --manifest` exited {code} and opened "
          f"with {_one_line(opener, 110)!r}, then printed "
          f"{_one_line(text, 160)!r}; `init`'s last line names the three "
          f"files and, with python-function (exit {wrote_runner}) and "
          f"swift-package (exit {wrote_swift}), the runner as a file no "
          f"command looks into={closing}"
          + ("" if closing
             else f" ({last!r} | {last_runner!r} | {last_swift!r})"))


# ------------------------------------------------------------ the templates
#
# The TEMPLATES group's checker and the two arms that stand on it. The checker
# is one function over a TEMPLATE DIRECTORY rather than over `templates_dir()`,
# so arm `iii` can point it at scratch copies it has broken on purpose — a
# checker nobody has watched go red is a zero result — while the group points
# it at the shipped directory.


class _TemplateVerdict(NamedTuple):
    ok: bool
    detail: str
    block: str          # what `apply` printed — the same block `init` prints
    project: str        # the scratch project the files were written into


_PRINTED_HOLE_RE = re.compile(r"^    ([A-Za-z][A-Za-z0-9_]*) — ", re.MULTILINE)


def template_verdict(templates_directory: str, name: str, box: str
                     ) -> _TemplateVerdict:
    """One shipped template, held to everything `init` will do with it.

    Four claims, in the order a reader meets them: the template holds to hole
    parity; the neutral three and then the template apply into a FRESH
    scratch project and every `dest` is written (a hole in a `dest` stays in
    the PATH, as the literal `<<HOLE:…>>` directory); the holes the
    block prints are exactly the declared holes of `_neutral` and the
    template, in order; and every hole each written file spells is among
    them. The detail quotes the per-file `holes_in` sets, so a reader of the
    row sees which file spells which hole rather than a count.
    """
    directory = os.path.join(templates_directory, name)
    try:
        problems = template_parity(directory)
    except Refusal as refused:
        # A template that will not LOAD is this template's red row, never a
        # refusal of the whole run: arm iii hands this function copies it
        # has broken on purpose.
        return _TemplateVerdict(False, f"{name}: does not load — {refused}",
                                "", "")
    if problems:
        return _TemplateVerdict(False, f"{name}: parity FAILS — "
                                + "; ".join(problems), "", "")
    chosen = [os.path.join(templates_directory, NEUTRAL)]
    if name != NEUTRAL:
        chosen.append(directory)
    templates = [refuse_unparity(one) for one in chosen]
    project = os.path.join(box, f"project-{name}")
    printed = io.StringIO()
    for template in templates:
        apply(template, project, printed)
    block = printed.getvalue()
    dests = [row.dest for template in templates for row in template.files]
    missing = [dest for dest in dests
               if not os.path.isfile(os.path.join(project, dest))]
    declared = [hole.name for template in templates for hole in template.holes]
    printed_holes = _PRINTED_HOLE_RE.findall(block)
    spelled: dict[str, tuple[str, ...]] = {}
    for dest in dests:
        text = read_text(os.path.join(project, dest))
        spelled[dest] = holes_in(text) if text is not None else ("<unreadable>",)
    strangers = sorted({hole for names in spelled.values() for hole in names}
                       - set(declared))
    ok = not missing and printed_holes == declared and not strangers
    detail = (f"{name}: parity clean; wrote {len(dests)} file(s) {dests}"
              + (f", MISSING {missing}" if missing else "")
              + f"; printed {len(printed_holes)} hole(s)"
              + ("" if printed_holes == declared
                 else f" {printed_holes} != declared {declared}")
              + "; spelled per file "
              + ", ".join(f"{dest}={list(names)}" for dest, names in spelled.items())
              + (f"; UNDECLARED {strangers}" if strangers else ""))
    return _TemplateVerdict(ok, detail, block, project)


def _shipped_templates_control(check: CheckRow, skip: SkipRow) -> None:
    """(hhh) the templates shipped beyond `_neutral`, as they stand."""
    label = ("hhh  the shipped templates beyond `_neutral` — python-function, "
             "swift-package, swift-xcodebuild — are listed in that order after "
             "it, each template.toml parses under `tomllib`, each holds to hole "
             "parity, and each Swift runner's spelled set equals its "
             "template's declared set less the `dest` hole — so the runner "
             "spells every hole the reader is told about and no other")
    try:
        shipped = shipped_templates()
    except Refusal as refused:
        skip(label, f"{refused} Nothing was read and nothing is claimed.")
        return
    beyond = shipped[1:]
    parsed: dict[str, str] = {}
    parity: dict[str, list[str]] = {}
    runners: dict[str, str] = {}
    for name in beyond:
        directory = os.path.join(templates_dir(), name)
        try:
            with open(os.path.join(directory, "template.toml"), "rb") as handle:
                tomllib.load(handle)
            parsed[name] = "parses"
        except (OSError, tomllib.TOMLDecodeError) as exc:
            parsed[name] = f"{type(exc).__name__}: {exc}"
        parity[name] = template_parity(directory)
        if parity[name]:
            continue
        template = load_template(directory)
        declared = {hole.name for hole in template.holes}
        for row in template.files:
            if not row.source.endswith(".swift"):
                continue
            text = read_text(os.path.join(directory, row.source)) or ""
            in_dest = set(holes_in(row.dest))
            spelled = set(holes_in(text))
            runners[f"{name}/{row.source}"] = (
                "equal" if spelled == declared - in_dest
                else f"spelled {sorted(spelled)} != declared-less-dest "
                     f"{sorted(declared - in_dest)}")
    wanted = ("python-function", "swift-package", "swift-xcodebuild")
    ok = (shipped[0] == NEUTRAL
          and all(name in beyond for name in wanted)
          and beyond == tuple(sorted(beyond))
          and all(verdict == "parses" for verdict in parsed.values())
          and not any(parity.values())
          and len(runners) == 2
          and all(verdict == "equal" for verdict in runners.values()))
    check(label, ok,
          f"{ACTUAL}shipped {shipped}; "
          + ", ".join(f"{name} {verdict}, parity "
                      f"{parity[name] or 'clean'}" for name, verdict in parsed.items())
          + "; Swift runners " + (", ".join(f"{key} {verdict}"
                                            for key, verdict in runners.items())
                                  or "(none found)"),
          next="Hold every shipped template to parity and make each Swift "
               "runner spell exactly its template's declared holes; "
               "docs/adding-a-template.md has the rule.")


def _drop_hole(text: str, name: str) -> str:
    """`text` with the `[[hole]]` table named `name` removed — arm iii's plant."""
    return re.sub(r'\[\[hole\]\]\nname\s*=\s*"' + re.escape(name)
                  + r'"\n(?:.+\n)*?\n', "", text)


def _template_checker_control(check: CheckRow, skip: SkipRow) -> None:
    """(iii) the TEMPLATES group's checker goes red on scratch copies this arm
    breaks, naming what broke — and green on the shipped directory.

    A shipped file the copy cannot read — an install at mode 0000 — is this
    row red with arm bbbb's verdict on the same copy, naming the path, and
    never a raise."""
    label = ("iii  the TEMPLATES group's checker goes red on scratch copies "
             "this arm writes — a swift-xcodebuild copy with the LOAD_INPUT "
             "[[hole]] row dropped FAILS naming that hole, and a "
             "python-function copy whose [[file]] source names a file that is "
             "not there FAILS naming it — and is green on the two shipped "
             "directories, so the checker is not simply always red")
    try:
        shipped = shipped_templates()
    except Refusal as refused:
        skip(label, f"{refused} There is no template to copy, so nothing is "
                    "claimed.")
        return
    if "swift-xcodebuild" not in shipped or "python-function" not in shipped:
        skip(label, f"the shipped templates are {shipped}; the two this arm "
                    "plants on are not both there. Nothing is claimed.")
        return
    with _box("golden-census-templates-") as box:
        copy = os.path.join(box, "templates")
        try:
            _writable_copy(templates_dir(), copy)
        except OSError as exc:
            # A shipped file this user cannot read: arm bbbb's verdict on the
            # same copy, naming the path in the operating system's words.
            check(label, False, f"{ACTUAL}{_copy_refused(exc).detail}",
                  next=BROKEN_TEMPLATE_NEXT)
            return
        xcode_toml = os.path.join(copy, "swift-xcodebuild", "template.toml")
        before = read_text(xcode_toml) or ""
        pathlib.Path(xcode_toml).write_text(_drop_hole(before, "LOAD_INPUT"), encoding="utf-8")
        python_toml = os.path.join(copy, "python-function", "template.toml")
        renamed = (read_text(python_toml) or "").replace(
            'source = "runner.py"', 'source = "runner-gone.py"', 1)
        pathlib.Path(python_toml).write_text(renamed, encoding="utf-8")
        planted = ("LOAD_INPUT" in before
                   and "LOAD_INPUT" not in (read_text(xcode_toml) or ""))
        dropped = template_verdict(copy, "swift-xcodebuild", box)
        gone = template_verdict(copy, "python-function", box)
        green = [template_verdict(templates_dir(), name, box)
                 for name in ("swift-xcodebuild", "python-function")]
    ok = (planted and not dropped.ok and "LOAD_INPUT" in dropped.detail
          and "declares it" in dropped.detail
          and not gone.ok and "runner-gone.py" in gone.detail
          and all(verdict.ok for verdict in green))
    check(label, ok,
          f"{ACTUAL}the [[hole]] row dropped from the copy={planted}; the "
          f"dropped-hole copy -> {_one_line(dropped.detail, 160)!r}; "
          f"the missing-source copy -> {_one_line(gone.detail, 160)!r}; the "
          f"shipped two -> {[verdict.ok for verdict in green]}",
          next="Make `template_verdict` report the parity problem it was "
               "handed by name; arm ww is the parity rule's own control.")


def _init_leaves_nothing_control(check: CheckRow, skip: SkipRow) -> None:
    """(ccccc) `init` is ALL OR NOTHING across both of its passes.

    It writes the neutral three and then a template's own files, so a refusal
    in the second pass used to leave the first pass's three on disk — where
    the next `init` refused them as already existing. That is the one `init`
    failure mode a reader meets twice, and it made the sentence the refusal
    prints wrong: what to do about it was not what the sentence said.

    Three plants, because "leaves nothing" has three halves. A collision in a
    directory that already carries something: the three files go, the planted
    file stays, and the next `init` succeeds. A collision behind a
    subdirectory the second pass created: that directory goes too, and the
    directory the READER made does not. And a project directory `init` itself
    had to create: it goes, so a failed scaffold leaves no empty folder named
    after somebody's project. The first plant's page is read too: a `wrote`
    line printed before the refusal names a file the undo removed.
    """
    label = ("ccccc  `init` writes the neutral three and then a template's "
             "own files, and a refusal in the SECOND pass leaves the project "
             "exactly as `init` found it: the first pass's files are removed, "
             "a directory `init` created on the way is removed, a file and a "
             "directory that were already there are untouched, and the next "
             "`init` into the same directory SUCCEEDS; and the refused "
             "`init` printed no `INIT` and no `wrote` line before its refusal, "
             "none for a file it removed")
    try:
        shipped = shipped_templates()
    except Refusal as refused:
        skip(label, f"{refused} There is no template for a second pass to "
                    "fail in. Nothing is claimed.")
        return
    if "python-function" not in shipped or "swift-xcodebuild" not in shipped:
        skip(label, "this copy ships neither `python-function` nor "
                    "`swift-xcodebuild`, and the two plants below are their "
                    f"second-pass collisions; it ships {sorted(shipped)}. "
                    "Nothing is claimed.")
        return

    with _box("golden-census-init-undo-") as box:
        # (1) a collision with a file the reader already had.
        flat = os.path.join(box, "flat")
        os.mkdir(flat)
        pathlib.Path(os.path.join(flat, "runner.py")).write_text(
            "the reader's own\n", encoding="utf-8")
        page = io.StringIO()
        first = _refused_by(lambda: init(flat, "python-function", False,
                                         page))
        printed = page.getvalue()
        left = sorted(os.listdir(flat))
        kept = read_text(os.path.join(flat, "runner.py"))
        # Caught, not allowed to travel: if the undo has gone, this second
        # `init` is exactly the refusal the reader used to meet, and an arm
        # that let it out would stop the self-check instead of reporting it.
        try:
            again: int | str = init(flat, None, False, io.StringIO())
        except Refusal as refused:
            again = _one_line(str(refused), 70)
        after = sorted(os.listdir(flat))

        # (2) a collision behind a subdirectory the second pass makes, in a
        #     directory whose own subdirectory the reader made.
        nested = os.path.join(box, "nested")
        os.makedirs(os.path.join(nested, "golden-census"))
        pathlib.Path(os.path.join(nested, "golden-census", "wrapper.py")).write_text(
            "the reader's own\n", encoding="utf-8")
        second = _refused_by(lambda: init(nested, "swift-xcodebuild", False,
                                          io.StringIO()))
        walked = sorted(
            os.path.relpath(os.path.join(where, name), nested)
            for where, dirs, files in os.walk(nested)
            for name in list(dirs) + list(files))

        # (3) a project directory `init` itself had to create. No shipped
        #     template collides inside a directory that did not exist a
        #     moment ago, so the second pass is a template built here whose
        #     one `dest` is a file the first pass just wrote.
        fresh = os.path.join(box, "made", "by", "init")
        collide = Template(name="collide", summary="a planted second pass",
                           directory=template_dir(NEUTRAL),
                           files=(File(source="manifest.toml",
                                       dest="manifest.toml"),),
                           holes=())
        made = Made()
        try:
            apply(refuse_unparity(template_dir(NEUTRAL)), fresh,
                  io.StringIO(), made)
            apply(collide, fresh, io.StringIO(), made)
            third = "NOT REFUSED"
        except Refusal as refused:
            made.undo()
            third = str(refused)
        remains = os.path.exists(fresh) or os.path.exists(
            os.path.join(box, "made"))

    check(label,
          first.startswith("runner.py already exists")
          and left == ["runner.py"] and kept == "the reader's own\n"
          and printed == ""
          and again == 0
          and after == ["census.toml", "manifest.toml", "mutants.toml",
                        "runner.py"]
          and second.startswith("golden-census/wrapper.py already exists")
          and walked == ["golden-census",
                         os.path.join("golden-census", "wrapper.py")]
          and third.startswith("manifest.toml already exists")
          and not remains,
          f"{ACTUAL}the flat plant -> {_one_line(first, 70)!r} after "
          f"{printed.count(chr(10))} printed line(s) "
          f"({printed.count('  wrote ')} `wrote`), left "
          f"{left}, the planted file reads {kept!r}, the next init exited "
          f"{again} leaving {after}; the nested plant -> "
          f"{_one_line(second, 70)!r}, left {walked}; the created-directory "
          f"plant -> {_one_line(third, 70)!r}, anything left under it="
          f"{remains}",
          next="`init` collects what it made in a `templates.Made` and calls "
               "`undo()` under a Refusal. If files are left behind, that "
               "ledger is not being passed through both `apply` calls; if a "
               "file the reader had is GONE, the ledger is recording paths it "
               "did not create, which is worse.")


# ------------------------------------- `init` writes inside, and nowhere else
#
#: A `dest` no file system here holds: one name past `NAME_MAX` (255 on
#: macOS and Linux), so the write fails with `ENAMETOOLONG` whatever the
#: project directory's own length. Arm `qqqqqqq`'s control of the refusal
#: that names the length.
_TOO_LONG = "n" * 256 + ".toml"

# `qqqqqqq` holds `init` to its promise where the SPELLING of a path cannot
# see: a link. `core.under` is the rule `init` asks, so the rule's own table is
# the arm's first half; the five cases after it are the three places a link
# meets `apply` and the file in the way whose `FileExistsError` is not one of
# them; and the last, a write that fails once its file exists, is the undo's.

#: The two shapes `core.under` is asked only where the file system says the
#: other spelling of the arm's directory is the same directory.
_OTHER_CASE = "a link inside spelled in another case"
_ITSELF_OTHER_CASE = "the directory itself spelled in another case"

#: `core.under` over six shapes of path, as `(strict=False, strict=True)`.
_UNDER_TABLE = {
    "the directory itself": (True, False),
    "a link inside to inside": (True, True),
    "a link inside that leads out": (False, False),
    "the tree through a linked directory": (True, True),
    _OTHER_CASE: (True, True),
    _ITSELF_OTHER_CASE: (True, False),
}


def _under_table(box: str) -> dict[str, tuple[bool, bool] | None]:
    """`core.under`'s answers over `_UNDER_TABLE`'s six shapes, in a tree
    built under `box` — the fourth shape through a link of the arm's own, so
    it does not depend on whether the temp root is spelled through one.

    The fifth is a link inside to `root/sub` whose target spells `box`'s own
    name in the other case. Whether that names the same directory is the file
    system's to say, so it is asked first, by `os.path.samefile`: where the
    two spellings are two directories (a file system that does not fold case)
    the link dangles, the shape is not asked of `core.under`, and its answer
    is None — disclosed in the row, never a pass and never a failure. The
    sixth is `root` itself reached through that other spelling, asked under
    the same answer of the file system.
    """
    root = os.path.join(box, "root")
    elsewhere = os.path.join(box, "elsewhere")
    os.makedirs(os.path.join(root, "sub"))
    os.makedirs(elsewhere)
    os.symlink(os.path.join(root, "sub"), os.path.join(root, "in-link"))
    os.symlink(elsewhere, os.path.join(root, "out-link"))
    os.symlink(root, os.path.join(box, "alias"))
    other = os.path.join(os.path.dirname(box),
                         os.path.basename(box).swapcase())
    os.symlink(os.path.join(other, "root", "sub"),
               os.path.join(root, "case-link"))
    try:
        folds = os.path.samefile(other, box)
    except OSError:
        folds = False
    shapes = {
        "the directory itself": root,
        "a link inside to inside": os.path.join(root, "in-link"),
        "a link inside that leads out": os.path.join(root, "out-link"),
        "the tree through a linked directory": os.path.join(box, "alias",
                                                            "sub"),
        _OTHER_CASE: os.path.join(root, "case-link"),
        _ITSELF_OTHER_CASE: os.path.join(other, "root"),
    }
    return {name: (under(path, root, strict=False),
                   under(path, root, strict=True))
            if folds or name not in (_OTHER_CASE, _ITSELF_OTHER_CASE)
            else None
            for name, path in shapes.items()}


def _init_stays_inside_control(check: CheckRow, skip: SkipRow) -> None:
    """(qqqqqqq) `init` writes inside the directory it was given and nowhere
    else, links included.

    `templates._inside` reads the spelling of a `dest`, which is right — the
    project directory need not exist yet — and cannot see a link. Two
    places a link meets `apply`, each with a directory of the arm's own as
    the place the link leads, made empty and listed after: the `dest` itself a
    dangling link, which `os.path.exists` reads as absent; a project
    subdirectory that is a link, two levels above the `dest`, which the
    spelling passes — and again where a directory below the link exists, so
    `_leads_out` has to climb back to the link to name it. And a FILE where
    a directory has to be, the case whose `FileExistsError` must NOT be read
    as the first one's.

    And a write that fails after `open` made its file, planted plainly:
    `init` in a child whose files may hold no byte, so its first write
    raises `File too large` as a full disk would. The refusal says it wrote
    none of the project's files, so the project directory it made must be
    gone after it, which holds only when the file joins the ledger before
    the write. The same child with `Made.undo` cut out is the case's
    control: it leaves the file the open made.
    """
    label = ("qqqqqqq  `core.under` answers six shapes of path — the "
             "directory itself, under its own spelling and under another "
             "where the file system says the two spellings are one directory, "
             "is inside only when not strict; a link inside that leads out is "
             "outside; a link to inside, a link to inside spelled in another "
             "case where the file system says so, and the tree reached "
             "through a linked directory are inside — and `init` writes "
             "nowhere outside the directory it was given: a `dest` that is a "
             "dangling link out is REFUSED as already existing; a project "
             "subdirectory that is a link out is REFUSED naming it and where "
             "it resolves, and named so too when the level nearest the "
             "`dest` that exists is a directory below it, reached through "
             "it; a file where a directory has to be is still REFUSED as a "
             "file in the way; the directories the links lead to are "
             "empty after all three; and a write that fails once its file "
             "exists — `init` in a child whose files may hold no byte, as on "
             "a full disk — is REFUSED quoting the error and leaves no "
             "project directory, where the same child with the undo cut out "
             "leaves the file the open made; a `dest` whose path the file "
             "system cannot hold is REFUSED naming the path's length")
    try:
        shipped_templates()
    except Refusal as refused:
        skip(label, f"{refused} There is no template to write from, so none "
                    "of the `init` cases can be exercised. Nothing is "
                    "claimed.")
        return

    def one_file(dest: str) -> Template:
        return Template(name="planted", summary="a planted template",
                        directory=template_dir(NEUTRAL),
                        files=(File(source="manifest.toml", dest=dest),),
                        holes=())

    with _box("golden-census-init-inside-") as box:
        os.mkdir(os.path.join(box, "table"))
        table = _under_table(os.path.join(box, "table"))
        dangles = not os.path.exists(
            os.path.join(box, "table", "root", "case-link"))
        projects = {name: os.path.join(box, name)
                    for name in ("dangling", "linked", "climbed",
                                 "blocked", "long")}
        # `climbed`'s link leads to `away-climbed`, which holds `deep`: the
        # level nearest the `dest` that exists is `sub/deep`, below the link,
        # and `_leads_out` climbs from it to `sub`, the link the reader
        # replaces. `deep` is where a write through the link would land.
        away = {name: os.path.join(box, f"away-{name}")
                for name in ("dangling", "linked")}
        away["climbed"] = os.path.join(box, "away-climbed", "deep")
        for directory in list(projects.values()) + list(away.values()):
            os.makedirs(directory)
        os.symlink(os.path.join(away["dangling"], "manifest.toml"),
                   os.path.join(projects["dangling"], "manifest.toml"))
        os.symlink(away["linked"], os.path.join(projects["linked"], "sub"))
        os.symlink(os.path.dirname(away["climbed"]),
                   os.path.join(projects["climbed"], "sub"))
        pathlib.Path(os.path.join(projects["blocked"], "sub")).write_text(
            "the reader's own\n", encoding="utf-8")
        said = {
            "dangling": _refused_by(lambda: init(
                projects["dangling"], None, False, io.StringIO())),
            "linked": _refused_by(lambda: apply(
                one_file("sub/inner/manifest.toml"), projects["linked"],
                io.StringIO(), Made())),
            "climbed": _refused_by(lambda: apply(
                one_file("sub/deep/inner/manifest.toml"),
                projects["climbed"], io.StringIO(), Made())),
            "blocked": _refused_by(lambda: apply(
                one_file("sub/manifest.toml"), projects["blocked"],
                io.StringIO(), Made())),
            "too long": _refused_by(lambda: apply(
                one_file(_TOO_LONG), projects["long"], io.StringIO(),
                Made())),
        }
        left = {name: sorted(os.listdir(where)) for name, where in away.items()}
        full = {cut: os.path.join(box, f"full-{cut}")
                for cut in ("none", "undo")}
        ran = _without_file_room("none", ["init", full["none"]],
                                 "arm qqqqqqq's full-disk run", box)
        undone = _without_file_room("undo", ["init", full["undo"]],
                                    "arm qqqqqqq's undo-cut run", box)
        elsewhere = "".join(_heard(proc.stderr).not_from(PACKAGE)
                            for proc in (ran, undone))
        kept = {cut: sorted(os.listdir(project))
                if os.path.isdir(project) else "gone"
                for cut, project in full.items()}
        sentences = [line.removeprefix("REFUSED: ")
                     for line in ran.stdout.splitlines()
                     if line.startswith("REFUSED: ")]
        said["full disk"] = (
            sentences[0] if ran.returncode == 2 and len(sentences) == 1
            else f"exit {ran.returncode}, {len(sentences)} REFUSED line(s)")
    resolves = os.path.join(os.pardir, "away-linked")
    holds = {
        "the table": table.keys() == _UNDER_TABLE.keys() and all(
            answer == _UNDER_TABLE[name]
            or (answer is None
                and name in (_OTHER_CASE, _ITSELF_OTHER_CASE) and dangles)
            for name, answer in table.items()),
        "dangling": said["dangling"].startswith(
            "manifest.toml already exists in the project directory"),
        "linked": said["linked"].startswith(
            "`init` cannot write sub/inner/manifest.toml into the project "
            f"directory: sub inside it resolves to {resolves}, outside the "
            "project directory"),
        "climbed": said["climbed"].startswith(
            "`init` cannot write sub/deep/inner/manifest.toml into the "
            "project directory: sub inside it resolves to "
            f"{os.path.join(os.pardir, 'away-climbed')}, outside the project "
            "directory"),
        "blocked": said["blocked"].startswith(
            "`init` cannot write into the project directory: sub inside the "
            "project directory is a file"),
        "nothing outside": not any(left.values()),
        "too long": said["too long"].startswith(
            f"`init` cannot write {_TOO_LONG} into the project directory: "
            "the path is too long for the file system ("),
        "full disk": said["full disk"].startswith(
            "`init` cannot write manifest.toml into the project directory "
            f"(OSError: {_NO_FILE_ROOM_ERROR.strerror}), so it wrote none of "
            "the project's files") and kept["none"] == "gone",
        "undo cut": kept["undo"] == ["manifest.toml"],
        "the package the children ran": not elsewhere,
    }
    check(label, all(holds.values()),
          f"{ACTUAL}core.under (not strict, strict): "
          + "; ".join(f"{name} {answer}" if answer is not None
                      else f"{name} not asked: this file system holds the "
                           "two spellings as two directories"
                      for name, answer in table.items())
          + "; " + "; ".join(f"{name} -> {_one_line(text, 150)!r}"
                             for name, text in said.items())
          + f"; left where the links lead: {left}; the project after the "
          f"full disk: {kept['none']}, with the undo cut out: {kept['undo']}"
          f"{elsewhere}; "
          f"failed: {[name for name, held in holds.items() if not held]}",
          next="`core.under` is the rule, and it asks the file system where "
               "the two real paths' spellings differ. `templates.apply` tests "
               "a `dest` with `os.path.lexists`, asks `_leads_out` before it "
               "makes a directory, and records the file in the ledger before "
               "it writes. A case that wrote where a link leads, or left a "
               "file behind, has lost one of them.")


# ------------------------------------------- the templates are `init`'s own
#
# `bbbb` above says an install's templates are sound, as a control a reader can
# ask for. `mmmmm` says what the COMMAND that reads them does when they are
# not: `init` refuses naming the template, and a `capture` on the same machine
# runs, because a capture opens no template directory and a golden a reader
# needs is not owed to one.


def _init_without_templates(templates: str, argv: list[str], *,
                            checked: bool = True) -> tuple[Any | None, int, str]:
    """`(the cli copy, the exit code, everything printed)` for one run of the
    real command line whose templates directory is `templates` — with
    `checked` False, in a copy whose `init` no longer asks
    `refuse_usable_templates`.

    A second, independent copy of `templates` with its `templates_dir` rebound,
    and a second copy of `cli` whose `init` is that copy's: the rebinding is an
    ATTRIBUTE of a copy, so nothing about the install this arm runs in moves,
    and the run goes through `cli.main` rather than past it.
    """
    templates_copy = _fresh_module("templates")
    cli_copy = _fresh_module("cli")
    if templates_copy is None or cli_copy is None:
        return None, 0, ""
    templates_copy.templates_dir = lambda: templates
    if not checked:
        templates_copy.refuse_usable_templates = lambda: None
    cli_copy.init = templates_copy.init
    code, printed = _quietly(cli_copy.main, argv)
    return cli_copy, code, printed


#: The words only `templates.refuse_usable_templates` prints about a broken
#: template: without the check, `init` still refuses the same template, in
#: the loader's sentence.
_TEMPLATES_UNUSABLE = "this install's templates are not usable"


def _init_checks_templates_control(check: CheckRow, skip: SkipRow) -> None:
    """(mmmmm) `init` is the command that reads the templates, so `init` is the
    command that refuses when they are not there.

    Three runs of one command line and one run of another. An empty templates
    directory and a truncated `template.toml` each stop `init` with a sentence
    naming what is wrong; a `capture` over a healthy manifest on the same copy
    runs to completion, because it opens no template directory.
    """
    label = ("mmmmm  `init` reads the templates and refuses when they are not "
             "usable: an empty templates directory and a copy with one "
             "template.toml truncated each stop `init` before it writes a "
             "file, each naming the fault, the truncated one with its "
             "template's own `next:`, while a `capture` over a healthy "
             "manifest on the same copy runs to completion; and the same copy "
             "with the check taken out of `init` gets as far as printing the "
             "TEMPLATES header of `init --list` before the loader stops it, "
             "which is the half-printed listing the check exists to prevent")
    with _box("golden-census-init-templates-") as box:
        empty = os.path.join(box, "no-templates")
        os.makedirs(empty)
        broken = os.path.join(box, "broken")
        try:
            _writable_copy(templates_dir(), broken)
        except OSError as exc:
            skip(label, f"the templates could not be copied ({type(exc).__name__}"
                        f": {exc}), so the truncated half cannot be built. "
                        "Nothing is claimed.")
            return
        # Outside the `try`: the copy exists, so a write that fails here is
        # the arm choosing the wrong entry, which is a red row and not a
        # machine that could not copy.
        cut = _plant_truncated(broken)
        advice = templates_verdict(broken).next
        gone_dir = os.path.join(box, "from-empty")
        copy, gone_code, gone_text = _init_without_templates(
            empty, ["init", gone_dir])
        if copy is None:
            skip(label, "this install carries no importable `templates` or "
                        "`cli` source to build a second copy from. Nothing is "
                        "claimed.")
            return
        broken_dir = os.path.join(box, "from-broken")
        _copy, broken_code, broken_text = _init_without_templates(
            broken, ["init", broken_dir])
        manifest = _scratch(box)
        _copy, capture_code, capture_text = _init_without_templates(
            empty, ["capture", "--manifest", manifest,
                    "--out", os.path.join(box, "out")])
        # `--list` is where the two arrangements are told apart, because it is
        # the form that PRINTS before it reads: with the check, the refusal is
        # the first thing on the page; without it, the header is printed and
        # the loader stops the listing halfway through.
        _copy, listed_code, listed_text = _init_without_templates(
            broken, ["init", "--list"])
        # The red half: the check taken out of `init`, and nothing else moved.
        _copy, removed_code, removed_text = _init_without_templates(
            broken, ["init", "--list"], checked=False)
        wrote_anything = os.path.isdir(gone_dir) or os.path.isdir(broken_dir)
    refuses = (gone_code == 2 and "REFUSED: " in gone_text
               and empty in gone_text
               and broken_code == 2 and "REFUSED: " in broken_text
               and _TEMPLATES_UNUSABLE in broken_text
               and cut in broken_text and not wrote_anything
               and bool(advice) and advice in broken_text)
    captures = capture_code == 0 and "capture complete" in capture_text
    if not captures and "REFUSED: " in capture_text and cut not in capture_text:
        _capture_broke(check, label,
                       "the stub subject would not capture, so what a lost "
                       "templates directory does to a capture cannot be "
                       f"measured: {_one_line(capture_text, 600)}")
        return
    listed = listed_code == 2 and "TEMPLATES" not in listed_text
    removed = removed_code == 2 and "TEMPLATES" in removed_text
    check(label, refuses and captures and listed and removed,
          f"{ACTUAL}`init` with an empty templates directory -> exit "
          f"{gone_code}, "
          + _one_line(gone_text, 110, needles=("REFUSED: ",),
                      empty="(no refusal)") + "; "
          f"with {cut or '(none)'}/template.toml truncated -> exit "
          f"{broken_code}, in the check's own sentence="
          f"{_TEMPLATES_UNUSABLE in broken_text}, names that template="
          f"{cut in broken_text}, carries "
          f"its `next:`={bool(advice) and advice in broken_text}; neither "
          f"wrote a directory={not wrote_anything}; `capture` on the same "
          f"copy -> exit {capture_code}, capture complete="
          f"{'capture complete' in capture_text}; `init --list` -> exit "
          f"{listed_code}, TEMPLATES header printed="
          f"{'TEMPLATES' in listed_text}; the check taken out of `init`, "
          f"`init --list` -> exit {removed_code}, TEMPLATES header printed="
          f"{'TEMPLATES' in removed_text}",
          next="`templates.refuse_usable_templates` is the check and `init` is "
               "its one caller; `templates.templates_verdict` is the question "
               "it and arm bbbb both ask.")


# ------------------------------------------- a template's `source` stays home
#
# `qqqqqqq` holds a `dest` inside the project. `qqqqqqqqq` holds a `source`
# inside the template directory, the other half of the same rule: `init`
# copies from one directory into another and a row may name neither's
# outside.

#: The line arm qqqqqqqqq adds to the file OUTSIDE the template directory, so
#: that a project file holding it is a file copied from outside.
_OUTSIDE_MARKER = "# copied from outside the template directory\n"


def _loaded_or_refused(directory: str) -> tuple[Template | None, Refusal | None]:
    """`load_template(directory)` as (the template, None) or (None, the
    refusal)."""
    try:
        return load_template(directory), None
    except Refusal as refused:
        return None, refused


def _source_outside_control(check: CheckRow, skip: SkipRow) -> None:
    """(qqqqqqqqq) a `[[file]]` `source` that leaves the template directory,
    spelled or by a link, is refused at load.

    Two scratch copies of the neutral template, each beside an `outside.txt`
    holding that template's own manifest text and one marker line, so that a
    hole-parity check passes the copy. In one the first row's `source` is
    `../outside.txt`; in the other it names a link inside the template that
    leads to that file. `load_template` of each must refuse; where it does
    not, the loaded template is applied into a project, and the detail says
    whether the marker arrived there. Every shipped template must still load.
    """
    label = ("qqqqqqqqq  a template whose [[file]] source names a path outside "
             "the template directory, or a link leading out, is refused at "
             "load naming the row, and every shipped template still loads")
    try:
        shipped = shipped_templates()
        neutral = template_dir(NEUTRAL)
    except Refusal as refused:
        skip(label, f"{refused} There is no template to copy, so no plant "
                    "can be made. Nothing is claimed.")
        return
    sources = {"spelled": "../outside.txt", "link": "linked.txt"}
    with _box("golden-census-source-outside-") as box:
        loaded: dict[str, Template | None] = {}
        said: dict[str, tuple[str, str] | None] = {}
        planted: dict[str, bool] = {}
        for shape, source in sources.items():
            home = os.path.join(box, shape)
            os.makedirs(home)
            copy = os.path.join(home, NEUTRAL)
            _writable_copy(neutral, copy)
            text = read_text(os.path.join(copy, "manifest.toml")) or ""
            pathlib.Path(os.path.join(home, "outside.txt")).write_text(
                text + _OUTSIDE_MARKER, encoding="utf-8")
            if shape == "link":
                os.symlink(os.path.join(os.pardir, "outside.txt"),
                           os.path.join(copy, source))
            toml = os.path.join(copy, "template.toml")
            before = read_text(toml) or ""
            after = before.replace('source = "manifest.toml"',
                                   f'source = "{source}"', 1)
            planted[shape] = after != before and bool(text)
            pathlib.Path(toml).write_text(after, encoding="utf-8")
            loaded[shape], why = _loaded_or_refused(copy)
            said[shape] = None if why is None else (str(why), why.next)
        leaked: dict[str, bool] = {}
        for shape, template in loaded.items():
            project = os.path.join(box, f"project-{shape}")
            if template is None:
                leaked[shape] = False
                continue
            apply(template, project, io.StringIO(), Made())
            leaked[shape] = _OUTSIDE_MARKER in (
                read_text(os.path.join(project, "manifest.toml")) or "")
        broken = {name: str(why) for name in template_directories(templates_dir())
                  for _, why in [_loaded_or_refused(
                      os.path.join(templates_dir(), name))] if why is not None}
    row = {shape: f"the [[file]] source {source!r} lands outside the template "
                  "directory. `init` copies from the template directory and "
                  "nowhere else."
           for shape, source in sources.items()}
    advice = ("Fix that template's `source` so it names a file inside the "
              "template directory.")
    holds = {
        shape: planted[shape] and said[shape]
        == (f"template {NEUTRAL!r}: {row[shape]}", advice)
        for shape in sources}
    check(label, all(holds.values()) and not broken and bool(shipped),
          ACTUAL + "; ".join(
              f"{shape} source {sources[shape]!r}: planted {planted[shape]}, "
              + ("LOADED, and an `init` from it wrote the outside file's "
                 f"marker into the project: {leaked[shape]}"
                 if (one := said[shape]) is None
                 else f"refused {_one_line(one[0], 150)!r}, "
                      f"next {_one_line(one[1], 150)!r}")
              for shape in sources)
          + f"; shipped templates that do not load: {broken or 'none'}",
          next="`templates._files` holds a `source` to the same rule `apply` "
               "holds a `dest` to: relative, no empty, `.` or `..` component, "
               "and resolving strictly inside the template directory by "
               "`core.under`, so a link leading out is outside.")
