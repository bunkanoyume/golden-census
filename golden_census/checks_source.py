"""The arms that walk golden-census's OWN source.

Five properties no single call site can carry — the self-check has one
decider, the package keeps no clock, every refusal carries a `next:` and the
words `REFUSED: ` and `next: ` have one producer each, the pinned TMPDIR
width is written once, and no module imports its way back to itself. Each is
a fact about every module, so each is asserted by a walk over every module,
with a planted copy that must come back naming what it planted.
"""

from __future__ import annotations

import ast
import pathlib

from .census import (
    FIXED_DIR_WIDTH,
)
from .controls import CheckRow, SkipRow
from .core import (
    ACTUAL,
    IMPORT_NAME,
    Refusal,
    refusal_text,
)
from .proof import _box
from .checks_base import (
    PACKAGE,
    arm_modules_named,
    is_arm_module,
    _ast_owners,
    _call_sites,
    _named,
    _owner_at,
    _walk_for_plant,
    _walk_package,
)

#: The two functions that put a block of controls in front of something:
#: golden-census's own arms, and the controls of one census. A call to either
#: is a decision that controls run HERE, and the arm below holds every one of
#: them to the same single owner. Named as a pair rather than one at a time,
#: because an entry point the walk does not know about is a second decider
#: nobody is looking for.
_CONTROL_ENTRIES = ("selfcheck", "census_check")


def _control_calls(source: str, name: str) -> list[str]:
    """`file:line in owner()` for every CALL to one of `_CONTROL_ENTRIES` in
    `source`: `checks_base._call_sites`, a call and not a mention."""
    return _call_sites(source, name, _CONTROL_ENTRIES)


def _one_decider_control(check: CheckRow, skip: SkipRow) -> None:
    """(ii) "which controls precede which command" is decided in ONE place —
    `cli.main`, before the dispatch — and nowhere else.

    Decided per command instead, four deciders are three orderings and two exit
    policies for one sentence. A second decider planted in any module is what
    this arm exists to see, so the same walk is run over a copy of `capture.py`
    with one planted call of EACH entry point: both must come back naming that
    file and those lines. Both, because a walk that knew only one of the two
    would read a second decider for the other as a clean package.
    """
    label = ("ii  which controls precede which command is decided in ONE "
             "place — `cli.main`, after the command's own file is read, when "
             "it has one, and before the dispatch — and no other function of "
             "the package calls either entry point ("
             + ", ".join(f"`{one}`" for one in _CONTROL_ENTRIES) + "); the "
             "same walk over a copy of capture.py with ONE call of each "
             "planted in it names that file, those lines and the function "
             "that would be the second decider")
    # The two files this arm is ABOUT, excluded by name and disclosed in the
    # row. `selfcheck.py` defines `selfcheck` and no arm calls either entry
    # point as a command's precondition; `controls.py` defines
    # `census_check`, is walked, and calls neither; `selftest.py` calls one
    # once, for the CONTROLS group — the self-TEST's own first group, and not
    # a command's precondition, which is what this arm counts. Both are named
    # in the detail, so a THIRD file quietly dropped from the walk would be
    # the false clean this arm exists to refuse rather than a silent pass.
    excluded = ("selfcheck.py", "selftest.py")
    walked = _walk_for_plant(
        lambda text, name: ([] if name in excluded
                            else _control_calls(text, name)),
        label, skip, "capture.py", "call")
    if walked is None:
        return
    sources = {name: text for name, text in walked[0].items()
               if name not in excluded}
    sites = walked[1]

    planted_source = sources["capture.py"].rstrip("\n")
    wanted: list[str] = []
    for number, entry in enumerate(_CONTROL_ENTRIES):
        planted_source += (f"\n\n\ndef _planted{number}(out: Any, "
                           "manifest: Any) -> int:\n"
                           f"    return {'controls.' if number else ''}{entry}(out, manifest)\n")
        line = len(planted_source.rstrip("\n").splitlines())
        wanted.append(f"capture.py:{line} in _planted{number}()")
    planted = _control_calls(planted_source, "capture.py")
    ok = (bool(sites)
          and all(site.startswith("cli.py:") and site.endswith(" in main()")
                  for site in sites)
          and planted == sorted(wanted))
    # A green row states WHAT held, a red row states WHERE it broke. The line
    # numbers are left out of the green detail on purpose: they move with every
    # edit to cli.py or capture.py, and a control whose passing text changes
    # under an unrelated commit is a control nobody can diff.
    check(label, ok,
          f"{ACTUAL}{len(sites)} call site(s) outside selfcheck.py and "
          f"selftest.py, every one "
          f"in cli.py's main(), across {len(sources)} module(s); a planted "
          f"second decider for each of {len(_CONTROL_ENTRIES)} entry point(s) "
          "was found, named by its file, its line and its function"
          if ok else
          f"{ACTUAL}{len(sites)} call site(s) outside selfcheck.py and "
          f"selftest.py {sites}, "
          f"across {len(sources)} module(s); the planted second deciders came "
          f"back as {planted} and had to be {sorted(wanted)}")


# ------------------------------------------------------------- no clock (vvv)
#
# golden-census cannot know how long a subject should run — a subject that
# drives a telescope runs for hours — so it keeps no clock and the CALLER owns
# the deadline. That is a property of the whole package rather than of any one
# call, so it is asserted by a walk over every module rather than at a site.


def _clock_sites(source: str, name: str) -> list[str]:
    """`file:line in owner() — what it keeps` for every clock in `source`: a
    call passing `timeout=`, or a mention of the `TimeoutExpired` name.

    An `ast` walk and not a text search, for the reason this arm exists at
    all: the sentence that STATES the rule spells the word, and a search that
    counted prose would report the rule as a breach of itself.
    """
    tree = ast.parse(source, filename=name)
    owners = _ast_owners(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        # The line is read INSIDE each branch: `ast.walk` yields the bare
        # `AST` type, and only the branch that identified the node knows it
        # carries a line number.
        kept, line = "", 0
        if isinstance(node, ast.Call) and any(word.arg == "timeout"
                                              for word in node.keywords):
            kept, line = "passes timeout=", node.lineno
        elif isinstance(node, ast.Name) and node.id == "TimeoutExpired":
            kept, line = "names TimeoutExpired", node.lineno
        elif isinstance(node, ast.Attribute) and node.attr == "TimeoutExpired":
            kept, line = "names TimeoutExpired", node.lineno
        if kept:
            found.append(f"{name}:{line} in {_owner_at(owners, line)}() "
                         f"— {kept}")
    return sorted(found)


#: What the planted copy of `capture.py` carries: one call that passes a
#: deadline. Written as source rather than compiled, because the arm never
#: RUNS it — the claim is about what the walk sees, and a planted clock that
#: had to run would be a clock this package keeps.
_PLANTED_CLOCK = ('def _planted() -> None:\n'
                  '    launch(["git", "--version"], "the planted clock", '
                  'timeout=1)\n')


def _no_clock_control(check: CheckRow, skip: SkipRow) -> None:
    """(vvv) golden-census keeps no clock, in any module.

    Three clocks lived here — a mutants check's, a `git clone`'s and
    `launch`'s own parameter — and each one was golden-census deciding how
    long somebody else's program may take. The caller's deadline is the only
    one that can know, and the process group printed at the top of the log is
    how the caller finds what its deadline left behind.
    """
    label = ("vvv  golden-census keeps NO clock: no call in the package "
             "passes a `timeout=` and nothing in it names `TimeoutExpired`, "
             "because it cannot know how long a subject may take and the "
             "CALLER owns the deadline; the same walk over a copy of "
             "capture.py with ONE `timeout=` planted in it names that file, "
             "that line and the function it sits in")
    sources, sites, why = _walk_package(_clock_sites)
    if why:
        skip(label, why)
        return
    if "capture.py" not in sources:
        skip(label, "capture.py was not found beside this module, so the "
                    "planted-clock control cannot be built. Nothing is "
                    "claimed.")
        return
    planted_source = (sources["capture.py"].rstrip("\n") + "\n\n\n"
                      + _PLANTED_CLOCK)
    planted_line = len(planted_source.rstrip("\n").splitlines())
    planted = _clock_sites(planted_source, "capture.py")
    wanted = f"capture.py:{planted_line} in _planted() — passes timeout="
    ok = not sites and planted == [wanted]
    check(label, ok,
          f"{ACTUAL}0 clock(s) across {len(sources)} module(s); the planted "
          "clock was found, named by its file, its line and its function"
          if ok else
          f"{ACTUAL}{len(sites)} clock(s) across {len(sources)} module(s) "
          f"{sites}; the planted clock came back as {planted} and had to be "
          f"[{wanted!r}]")


# ------------------------------------------------ the `next:` coverage arm
#
# The claim is "every refusal says what to do next". These two walks are what
# make it a measurement: one over every call site of a refusal class, one over
# every place the word `REFUSED:` is produced at all.


def _no_next_sites(sources: dict[str, str]
                   ) -> tuple[frozenset[str], list[str]]:
    """The refusal classes `sources` define, and every call of one that
    passes no `next` (by keyword, or as the second positional argument,
    which is where `Refusal` takes it) and every `raise` of one that is not
    called, as `file:line`. A zero result here is the claim, so the arm
    plants each shape.

    The classes are `Refusal` and every class `sources` define under it, by
    name: a `ClassDef` whose base is `Refusal` or a class already found. That
    walk is repeated until it finds no new name, so a class defined in a
    module read before its base's module is found too.
    """
    trees = {name: ast.parse(text) for name, text in sources.items()}
    defined = [node for tree in trees.values() for node in ast.walk(tree)
               if isinstance(node, ast.ClassDef)]
    classes = {Refusal.__name__}
    grown = True
    while grown:
        more = {node.name for node in defined
                if any(_named(base) in classes for base in node.bases)}
        grown = not more <= classes
        classes |= more
    found = [f"{name}:{node.lineno}"
             for name, tree in trees.items() for node in ast.walk(tree)
             if (isinstance(node, ast.Call) and _named(node.func) in classes
                 and len(node.args) < 2
                 and not any(word.arg == "next" for word in node.keywords))
             or (isinstance(node, ast.Raise) and node.exc is not None
                 and not isinstance(node.exc, ast.Call)
                 and _named(node.exc) in classes)]
    return frozenset(classes), sorted(found)


def _literals(tree: ast.Module) -> list[tuple[int, str]]:
    """`(line, text)` for every non-docstring string literal in `tree` — an
    f-string's literal parts among them.

    Comments are not AST nodes, so prose about a word is free; docstrings
    are, so they are collected and skipped by identity. The one rule both
    producer walks below read.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef
                          | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", [])
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            docstrings.add(id(body[0].value))
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def _produced(source: str, name: str, word: str) -> list[str]:
    """Every non-docstring string literal in `source` that PRODUCES `word`, as
    `file:line`."""
    return sorted(f"{name}:{line}" for line, text in _literals(ast.parse(source))
                  if word in text)


#: What a `[SKIP]` line's literal carries, whatever its indent: the bracket
#: and the two spaces after it. Spelled here by hand and not asked of
#: `core.skip_line`, so a change to the owner's opening is a change this walk
#: can see.
_SKIP_WORD = "[SKIP]  "


def _skip_sites(source: str, name: str) -> list[tuple[str, str, str]]:
    """`(file:line, the function it sits in, the literal)` for every site that
    PRODUCES `[SKIP]  `.

    Two are expected: `core.skip_line`, the one opening of every per-row SKIP
    line, and `compare`'s summary of the rows skipped on both sides — a line
    about many rows, recognized by its own text, whose four spaces after the
    bracket no row shares. A literal that CONTAINS the word is counted, not
    only one that begins with the opening: a producer with four leading
    spaces is a second shape too.
    """
    tree = ast.parse(source)
    owners = _ast_owners(tree)
    return sorted((f"{name}:{line}", _owner_at(owners, line), text)
                  for line, text in _literals(tree) if _SKIP_WORD in text)


def _verdict_sites(source: str, name: str) -> list[str]:
    """Every site that PRODUCES the word `REFUSED: `.

    There must be exactly one, in `core.refusal_text`: a second would print
    the verdict without the `next:` line under it, and nobody reading the
    output could tell.
    """
    return _produced(source, name, "REFUSED: ")


def _next_sites(source: str, name: str) -> list[str]:
    """Every site that PRODUCES the word `next: `.

    The companion walk, and the one the `REFUSED: ` walk cannot make: the
    `next:` LINE is also laid out by two exit-1 verdicts that are neither a
    `Refusal` nor a `Report` row, which that walk cannot see. The layout is
    `core.next_line`'s alone.
    """
    return _produced(source, name, "next: ")


def _parsed(source: str, name: str) -> list[str]:
    """No sites: `source` parsed under its own file name, inside
    `_walk_package`'s guard, so a module that does not parse is named in the
    one sentence every walking arm SKIPs with, before an arm's own walks ask
    it again."""
    ast.parse(source, filename=name)
    return []


#: What arm `cccccccc` plants beside a scratch copy of the package's
#: modules, one at a time under one name: (the shape, the bytes of the file,
#: or None for a directory, and the exception the walk must name).
_UNWALKABLE: tuple[tuple[str, bytes | None, str], ...] = (
    ("a `.py` that is a directory", None, "IsADirectoryError"),
    ("a `.py` that is not UTF-8", b"VALUE = '\xff'\n", "UnicodeDecodeError"),
    ("a `.py` that does not parse", b"def (:\n", "SyntaxError"))


def _walk_fault_control(check: CheckRow, skip: SkipRow) -> None:
    """(cccccccc) the walk every source-reading arm opens with returns its
    sentence, naming the file, where a module cannot be walked.

    `checks_base._walk_package` is the one place those arms read the
    package, and its `except` is the one place a module that cannot be
    read, decoded or parsed becomes a disclosed SKIP rather than a raise or
    a clean walk. No module of a sound package reaches it, so it is planted:
    a scratch copy of the package's modules is walked as it is, then with a
    `.py` that is a directory — unreadable as a file to every user, root
    included — then with one that is not UTF-8, then with one that does not
    parse, each walk handed `_parsed`, the sites function the parsing arms
    hand it.
    """
    label = ("cccccccc  `checks_base._walk_package`, the walk every arm that "
             "reads the package's own source opens with, returns every "
             "module of a scratch copy of the package, and over the same "
             "copy with one planted `.py` that is a directory, one that is "
             "not UTF-8 and one that does not parse returns no module and "
             "the sentence the walking arms SKIP with, naming that file and "
             "what was raised, never a raise")
    with _box("golden-census-walk-fault-") as box:
        copy = pathlib.Path(box, IMPORT_NAME)
        copy.mkdir()
        for module in sorted(pathlib.Path(PACKAGE).glob("*.py")):
            (copy / module.name).write_bytes(module.read_bytes())
        sources, _sites, why = _walk_package(_parsed, str(copy))
        if why:
            skip(label, why)
            return
        copied = len(list(copy.glob("*.py")))
        planted = copy / "zz_planted.py"
        said: dict[str, str] = {}
        held: list[bool] = []
        for shape, made, raised in _UNWALKABLE:
            if made is None:
                planted.mkdir()
            else:
                planted.write_bytes(made)
            walked, _found, fault = _walk_package(_parsed, str(copy))
            if made is None:
                planted.rmdir()
            else:
                planted.unlink()
            said[shape] = fault.replace(box, "<box>") or (
                f"walked {len(walked)} module(s), no sentence")
            held.append(not walked and fault.startswith(
                "the package's own source could not be walked at "
                f"{planted.name} ({raised}: "))
    check(label, len(sources) == copied > 0 and all(held),
          f"{ACTUAL}the scratch copy -> {len(sources)} of {copied} "
          "module(s); " + "; ".join(f"{shape} -> {text}"
                                    for shape, text in said.items()),
          next="`checks_base._walk_package` reads every `.py` of the package "
               "inside one `try` and answers an `OSError`, a `SyntaxError` "
               "or a `ValueError` (a decoding error among them) with one "
               "sentence that names the file it stopped at; a module none "
               "of those reach is a walk an arm would read as clean.")


def _next_coverage_control(check: CheckRow, skip: SkipRow) -> None:
    """(ss) every call of `Refusal` or of a class the package defines under
    it carries a `next=`, `REFUSED: ` is produced at exactly one site, and
    `[SKIP]  ` at exactly two."""
    label = ("ss  every call of `Refusal`, or of any class the package's "
             "source defines under it (a `class` whose base is `Refusal` or "
             "such a class, found by walking that source), passes a "
             "`next=`, the word "
             "`REFUSED: ` is PRODUCED at exactly one site "
             "(`core.refusal_text`) and so is the word `next: ` "
             "(`core.next_line`) — so no verdict can reach a reader without "
             "the sentence that says what to do, and no producer of that "
             "sentence lays it out its own way; the same three walks over "
             "scratch copies with one planted `Refusal(` without a `next=`, "
             "one passing another keyword and no `next=`, "
             "one planted subclass of a planted subclass raised without one, "
             "one planted `core.Refusal(` called through its module, one "
             "planted class defined inside a function and raised without one "
             "and one planted `raise` of a class that is not called, all "
             "named, and one planted `Refusal(` that passes its `next` as "
             "the second positional argument, which is not, "
             "one planted `out.write(\"  next: …\")` and one planted "
             "`out.write(\"REFUSED: …\")` name that file and that line; and "
             "`[SKIP]  ` is PRODUCED at exactly two sites — `core.skip_line`, "
             "the opening of every per-row SKIP line, and `compare`'s summary "
             "of the rows skipped on both sides, recognized by its own text — "
             "the same walk over copies with a planted second producer, one "
             "with two leading spaces and one with four, naming that file and "
             "that line")
    # The walk only parses: this arm's three walks run over `sources` below.
    sources, _sites, why = _walk_package(_parsed)
    if why:
        skip(label, why)
        return
    if "capture.py" not in sources or "core.py" not in sources:
        skip(label, "capture.py or core.py was not found beside this module, "
                    "so neither planted control can be built. Nothing is "
                    "claimed.")
        return

    classes, bare = _no_next_sites(sources)
    # The self-check's own modules and `__main__.py` are excluded from
    # the SECOND walk, each disclosed in the row. An arm file quotes the
    # words in the assertions it makes ABOUT them and prints neither, and
    # a control that reads its own expected output is not a second
    # printer. `__main__.py` produces both and cannot do otherwise: its
    # floor guard runs before the import of `core`, because the import of
    # `core` is what a pre-3.11 interpreter dies in. So it is held to the
    # layout instead of to the ownership — `_floor_layout` below asserts
    # its block reads exactly as `core.refusal_text` lays one out, which
    # is what the ownership rule was protecting.
    verdicts = [site for name, text in sources.items()
                if _is_printer(name)
                for site in _verdict_sites(text, name)]
    nexts = [site for name, text in sources.items()
             if _is_printer(name)
             for site in _next_sites(text, name)]
    skips = [site for name, text in sources.items()
             if _is_printer(name)
             for site in _skip_sites(text, name)]

    planted_next = (sources["capture.py"].rstrip("\n")
                    + '\n\n\ndef _planted_bare() -> None:\n'
                      '    raise Refusal("a planted refusal with no next")\n')
    bare_line = len(planted_next.rstrip("\n").splitlines())
    _classes, bare_found = _no_next_sites({**sources,
                                           "capture.py": planted_next})

    # A call that passes a keyword of its own and no `next=`: a walk that
    # took any keyword for a `next=` would pass it.
    planted_keyword = (sources["capture.py"].rstrip("\n")
                       + '\n\n\ndef _planted_keyword() -> None:\n'
                         '    raise Refusal("a planted refusal with no next", '
                         'fold="another keyword")\n')
    keyword_line = len(planted_keyword.rstrip("\n").splitlines())
    _classes, keyword_found = _no_next_sites({**sources,
                                              "capture.py": planted_keyword})

    # The subclass is written above its base, as a class in a module read
    # before its base's module is, and the base names `Refusal` through its
    # module: the walk must find both all the same.
    planted_class = (sources["capture.py"].rstrip("\n")
                     + '\n\n\nclass _PlantedRefusal(_PlantedBase):\n'
                       '    """A planted subclass of a planted subclass."""\n'
                       '\n\nclass _PlantedBase(core.Refusal):\n'
                       '    """A planted subclass of `Refusal`."""\n'
                       '\n\ndef _planted_subclass() -> None:\n'
                       '    raise _PlantedRefusal("a planted refusal with no '
                       'next")\n')
    class_line = len(planted_class.rstrip("\n").splitlines())
    _classes, class_found = _no_next_sites({**sources,
                                            "capture.py": planted_class})

    # The shapes a walk narrowed to bare names, to classes at the top of a
    # module, or to calls would not see, and the one legal way to pass a
    # `next` that a walk reading only keywords would flag.
    shapes = {
        "qualified": ('def _planted_qualified() -> None:\n'
                      '    raise core.Refusal("a planted refusal with no '
                      'next")\n'),
        "local class": ('def _planted_local() -> None:\n'
                        '    class _PlantedLocal(Refusal):\n'
                        '        """A planted class inside a function."""\n'
                        '\n'
                        '    raise _PlantedLocal("a planted refusal with no '
                        'next")\n'),
        "uncalled": ('def _planted_uncalled() -> None:\n'
                     '    raise WouldNotStart\n'),
    }
    shape_lines: dict[str, str] = {}
    shape_found: dict[str, list[str]] = {}
    for shape, text in shapes.items():
        planted_shape = sources["capture.py"].rstrip("\n") + "\n\n\n" + text
        planted_at = len(planted_shape.rstrip("\n").splitlines())
        shape_lines[shape] = f"capture.py:{planted_at}"
        shape_found[shape] = _no_next_sites(
            {**sources, "capture.py": planted_shape})[1]
    planted_positional = (sources["capture.py"].rstrip("\n")
                          + '\n\n\ndef _planted_positional() -> None:\n'
                            '    raise Refusal("a planted refusal", "its next, '
                            'passed by position")\n')
    _classes, positional_found = _no_next_sites({**sources,
                                                 "capture.py":
                                                 planted_positional})

    planted_verdict = (sources["capture.py"].rstrip("\n")
                       + '\n\n\ndef _planted_verdict(out: Any) -> None:\n'
                         '    out.write("REFUSED: a second printer\\n")\n')
    verdict_line = len(planted_verdict.rstrip("\n").splitlines())
    verdict_found = _verdict_sites(planted_verdict, "capture.py")

    planted_layout = (sources["capture.py"].rstrip("\n")
                      + '\n\n\ndef _planted_next(out: Any) -> None:\n'
                        '    out.write("  next: a second layout\\n")\n')
    layout_line = len(planted_layout.rstrip("\n").splitlines())
    layout_found = _next_sites(planted_layout, "capture.py")

    skip_found: dict[str, list[str]] = {}
    skip_wanted: dict[str, str] = {}
    for spaces, indent in (("two", "  "), ("four", "    ")):
        planted_skip = (sources["capture.py"].rstrip("\n")
                        + '\n\n\ndef _planted_skip(out: Any) -> None:\n'
                          f'    out.write("{indent}[SKIP]  a second producer\\n")\n')
        planted_at = len(planted_skip.rstrip("\n").splitlines())
        skip_wanted[spaces] = f"capture.py:{planted_at}"
        skip_found[spaces] = [site for site, _owner, _text
                              in _skip_sites(planted_skip, "capture.py")]
    # The two sites expected, by where they are and what they say: the owner
    # by its function, the summary by its own text.
    two_skips = (len(skips) == 2
                 and skips[0][0].startswith("compare.py:")
                 and skips[0][2].startswith("  [SKIP]    ")
                 and skips[1][0].startswith("core.py:")
                 and skips[1][1] == "skip_line"
                 and skips[1][2] == "  [SKIP]  ")

    one_owner = len(verdicts) == 1 and verdicts[0].startswith("core.py:")
    one_layout = len(nexts) == 1 and nexts[0].startswith("core.py:")
    floor_ok, floor_detail = _floor_layout(sources.get("__main__.py"))
    ok = (not bare and one_owner and one_layout and floor_ok
          and bare_found == [f"capture.py:{bare_line}"]
          and keyword_found == [f"capture.py:{keyword_line}"]
          and class_found == [f"capture.py:{class_line}"]
          and all(shape_found[shape] == [where]
                  for shape, where in shape_lines.items())
          and positional_found == []
          and verdict_found == [f"capture.py:{verdict_line}"]
          and layout_found == [f"capture.py:{layout_line}"]
          and two_skips
          and all(skip_found[key] == [where]
                  for key, where in skip_wanted.items()))
    check(label, ok,
          f"{ACTUAL}{len(sources)} module(s) walked, {len(bare)} call(s) of "
          f"{sorted(classes)} without a next= {bare[:4]}, `REFUSED: ` "
          f"produced at {verdicts}, "
          f"`next: ` produced at {nexts} ({arm_modules_named()} and "
          f"{_FLOOR_PRINTER} excluded from both — the "
          "self-check's own modules quote the words in the assertions they "
          "make about them and print none of them, the last produces them "
          "before `core` can be imported and is held to the LAYOUT instead: "
          f"{floor_detail}; disclosed, never a pass); the planted bare "
          f"refusal came back {bare_found}, the planted refusal passing "
          f"another keyword {keyword_found}, the planted subclass of a "
          f"subclass raised bare {class_found}, the planted refusal called "
          f"through its module, the planted class defined inside a function "
          f"and the planted `raise` of a class that is not called "
          f"{shape_found}, the planted `next` passed by position "
          f"{positional_found}, the planted second printer "
          f"{verdict_found} and the planted second next: layout "
          f"{layout_found}; `[SKIP]  ` produced at "
          f"{[f'{site} in {owner}()' for site, owner, _text in skips]}, the "
          f"planted second producer with two leading spaces {skip_found['two']} "
          f"and with four {skip_found['four']}")


#: The one module named by hand: `__main__.py` PRODUCES both words and cannot
#: do otherwise — its floor guard runs before the import of `core`, because
#: the import of `core` is what a pre-3.11 interpreter dies in — so it is held
#: to the LAYOUT instead, by `_floor_layout`. The self-check's own modules are
#: excluded by `checks_base.is_arm_module`: each quotes the words in the
#: assertions it makes ABOUT them and prints neither.
_FLOOR_PRINTER = "__main__.py"


def _is_printer(name: str) -> bool:
    """Whether the `REFUSED: `/`next: ` ownership walks read this module."""
    return not (name == _FLOOR_PRINTER or is_arm_module(name))


def _floor_layout(source: str | None) -> tuple[bool, str]:
    """Whether `__main__.py`'s floor refusal is laid out the way
    `core.refusal_text` lays one out, and the sentence saying so.

    The one module that produces `REFUSED: ` and `next: ` without asking
    `core` for them — it cannot ask, because importing `core` is what a
    pre-3.11 interpreter dies in. What the ownership rule was protecting is
    the LAYOUT, so the layout is what is checked here, against a refusal
    formatted live rather than against a typed copy of it: a change to
    `refusal_text`'s shape moves this assertion with it.
    """
    if source is None:
        return False, "__main__.py was not found beside this module"
    reference = refusal_text(Refusal("s", next="n")).split("\n")
    head, under = reference[0][:len("REFUSED: ")], "\n" + reference[1][:-1]
    try:
        literals = [node.value for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.Constant)
                    and isinstance(node.value, str)]
    except (SyntaxError, ValueError) as exc:
        return False, f"__main__.py would not parse ({type(exc).__name__})"
    opens = [one for one in literals if one.startswith(head)]
    follows = [one for one in literals if under in one]
    return bool(opens) and bool(follows), (
        f"__main__.py opens {len(opens)} literal(s) with {head!r} and lays "
        f"{len(follows)} out under it as {under!r}, which is "
        "`core.refusal_text`'s own layout, read off a live refusal")


# --------------------------------------------- the width's one owner (zzz)
#
# The pinned TMPDIR width is one number that three sentences depend on: the
# pin the built-in census writes, the docstring that describes it, and the
# refusal a too-wide temp root earns, which states the width AND the widest
# root that fits under it. Written at each site, they are three chances to
# disagree; `census.FIXED_DIR_WIDTH` owns it and the refusal derives both of
# its numbers, so there is one number and one place to change it.


def _width_literals(source: str, name: str) -> list[str]:
    """`file:line in owner() — how` for every place `source` spells the pinned
    width, as an integer or inside a string.

    Both forms, because either can be how a second spelling arrives: the
    census row writes the width INSIDE the `<FIXED-WIDTH-DIR:N>` pin value,
    where an integer-only walk would never see it. A string that merely
    contains the digits is enough to name — this walk reports, it does not
    judge, and a site it names is one a reader decides about. It spells no
    example of its own: a docstring here that quoted a pin value would be the
    second spelling, found by the walk it belongs to.
    """
    width = str(FIXED_DIR_WIDTH)
    tree = ast.parse(source, filename=name)
    owners = _ast_owners(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        how = ""
        if isinstance(node.value, int) and not isinstance(node.value, bool) \
                and node.value == FIXED_DIR_WIDTH:
            how = "as an integer"
        elif isinstance(node.value, str) and width in node.value:
            how = "inside a string"
        if how:
            found.append(f"{name}:{node.lineno} in "
                         f"{_owner_at(owners, node.lineno)}() — {how}")
    return sorted(found)


#: What arm `zzz` plants: a second place that writes the width down. A copy of
#: the census row as it was before the constant owned the number — the exact
#: shape the arm exists to catch coming back.
_PLANTED_WIDTH = ('def _planted() -> str:\n'
                  '    return "<FIXED-WIDTH-DIR:{}>"\n')


def _width_owner_control(check: CheckRow, skip: SkipRow) -> None:
    """(zzz) the pinned width is spelled once, at the constant that owns it."""
    label = (f"zzz  the pinned TMPDIR width {FIXED_DIR_WIDTH} is written in "
             "exactly ONE place in the package — `census.FIXED_DIR_WIDTH`, "
             "which the pin, the docstring and the refusal's two numbers are "
             "all derived from — and a walk over every module finds it there "
             "and nowhere else, as an integer or inside a string; the same "
             "walk over a copy of census.py with ONE more spelling planted in "
             "it names that file, that line and the function it sits in")
    walked = _walk_for_plant(_width_literals, label, skip, "census.py",
                             "width")
    if walked is None:
        return
    sources, sites = walked
    planted_source = (sources["census.py"].rstrip("\n") + "\n\n\n"
                      + _PLANTED_WIDTH.format(FIXED_DIR_WIDTH))
    planted_line = len(planted_source.rstrip("\n").splitlines())
    planted = _width_literals(planted_source, "census.py")
    wanted = f"census.py:{planted_line} in _planted() — inside a string"
    owner = [site for site in sites if site.startswith("census.py:")
             and "(module level)" in site and "as an integer" in site]
    # `sorted` orders by the line number as TEXT, so the plant is not
    # necessarily last: the whole planted list is compared instead, which also
    # says that planting one spelling added exactly one row.
    ok = (sites == owner and len(owner) == 1
          and planted == sorted([*owner, wanted]))
    check(label, ok,
          f"{ACTUAL}1 spelling across {len(sources)} module(s), at "
          f"{owner[0].split(' in ')[0] if owner else 'nowhere'} — the "
          "constant itself; the planted second spelling was found, named by "
          "its file, its line and its function"
          if ok else
          f"{ACTUAL}{len(sites)} spelling(s) across {len(sources)} module(s) "
          f"{sites}; the planted second spelling came back as {planted} and "
          f"had to end in [{wanted!r}]")


# ------------------------------------------------ no import cycle (bbbbbbbb)
#
# The arms import `cli` to exercise it, and `--selfcheck` and `--selftest`
# run the arms, so the one way a cycle comes back is `cli` importing a module
# that imports it. The walk is over every import of every module, so it names
# that cycle and any other.


def _import_graph(sources: dict[str, str]) -> dict[str, list[str]]:
    """`{module: the package modules it imports}` for every module in
    `sources`, by an `ast` walk of every import statement — at the top of the
    file and inside a function alike, relative or spelled with the package's
    own name."""
    names = {name[:-3] for name in sources}
    graph: dict[str, list[str]] = {}
    for file, text in sources.items():
        found: set[str] = set()
        for node in ast.walk(ast.parse(text, filename=file)):
            if isinstance(node, ast.ImportFrom):
                parts = (node.module or "").split(".")
                if node.level == 1 or (node.level == 0
                                       and parts[0] == IMPORT_NAME):
                    inner = parts[1:] if node.level == 0 else parts
                    found |= ({inner[0]} if inner and inner[0]
                              else {alias.name for alias in node.names})
            elif isinstance(node, ast.Import):
                found |= {alias.name.split(".")[1] for alias in node.names
                          if alias.name.startswith(IMPORT_NAME + ".")}
        graph[file[:-3]] = sorted(found & names - {file[:-3]})
    return graph


def _first_cycle(graph: dict[str, list[str]]) -> list[str]:
    """The first import cycle of `graph`, walked in name order, as the
    modules from one back to itself; empty when there is none."""
    state: dict[str, bool] = {}     # True while on the path, False when done

    def visit(node: str, path: list[str]) -> list[str]:
        state[node] = True
        path.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) is True:
                return path[path.index(nxt):] + [nxt]
            if nxt not in state:
                found = visit(nxt, path)
                if found:
                    return found
        path.pop()
        state[node] = False
        return []

    for start in sorted(graph):
        if start not in state:
            found = visit(start, [])
            if found:
                return found
    return []


#: The line the planted copy of cli.py carries: the import that closes the
#: cycle this arm exists to see.
_PLANTED_IMPORT = "from .selfcheck import selfcheck\n"


def _no_cycle_control(check: CheckRow, skip: SkipRow) -> None:
    """(bbbbbbbb) no module of the package reaches itself through its
    imports.

    The modules that exercise `cli` import it, and `cli` imports none of
    them: the runners of `--selfcheck` and `--selftest` are handed to
    `cli.main` by `console.main`. A cycle whose imports back are written
    inside functions loads without a word, so nothing but this walk objects
    to one. The same walk over a copy of cli.py with one import of
    `selfcheck` planted in it must come back with a cycle through both.
    """
    label = ("bbbbbbbb  no module of the package reaches itself through its "
             "imports — every import statement, at the top of a file and "
             "inside a function alike, read by an `ast` walk of every "
             "module, so `cli` imports no module that imports it; the same "
             "walk over a copy of cli.py with "
             f"`{_PLANTED_IMPORT.strip()}` planted in it names the cycle "
             "that one line makes, through `cli` and `selfcheck`")
    walked = _walk_for_plant(_parsed, label, skip, "cli.py", "import")
    if walked is None:
        return
    sources = walked[0]
    cycle = _first_cycle(_import_graph(sources))
    planted = _first_cycle(_import_graph(
        {**sources, "cli.py": sources["cli.py"] + "\n" + _PLANTED_IMPORT}))
    caught = "cli" in planted and "selfcheck" in planted
    check(label, not cycle and caught,
          f"{ACTUAL}no cycle across {len(sources)} module(s); the copy of "
          "cli.py with the planted import came back naming a cycle through "
          "`cli` and `selfcheck`"
          if not cycle and caught else
          (f"{ACTUAL}across {len(sources)} module(s), the cycle "
           f"{' -> '.join(cycle)}" if cycle else
           f"{ACTUAL}no cycle across {len(sources)} module(s), but the copy "
           "of cli.py with the planted import came back with "
           f"{' -> '.join(planted) or 'no cycle'}, not one through `cli` "
           "and `selfcheck`"),
          next=("Break the cycle the detail names: a module that has to call "
                "one that imports it takes the function as an argument from "
                "a module above both, as `cli.main` takes the runners of "
                "`--selfcheck` and `--selftest` from `console.main`."
                if cycle else
                "The walk did not see the import planted in cli.py: the "
                "control, `_import_graph` and `_first_cycle` read every "
                "import statement, so one of them has stopped reading."))
