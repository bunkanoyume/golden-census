"""The census: everything around the subject that is not the subject's code.

Each row is one input to the subject's output — an environment variable, the
width of the temp root, the clock a renderer reads, the checkout's absolute
path — with its disposition (pin, fold, state, precondition) and, for pins and
folds, the control that proves the disposition matters.

`docs/census-format.md` is authoritative for every word here. The regex, the
JSON paths and fields, the scope, the serialization, the pinned variables and
the pinned width all come from census rows, so nothing in this module knows
what the subject is.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, NamedTuple

from .core import (
    REVISION_WIDTH,
    DIFFERENCE,
    GIT_UNTRACKED,
    NO_ENV_BUILT,
    PATH_SOURCES,
    printable_text,
    PROG,
    Layout,
    Pending,
    Placeholders,
    Refusal,
    Roots,
    WouldNotStart,
    QUOTE,
    QUOTE_SHORT,
    TOKEN_RE,
    _read_source,
    attaching,
    child_fault,
    ended,
    fold,
    git_command,
    launch,
    load_toml,
    only_keys,
    path_forms,
    roots_vocabulary,
    strings,
    table,
    temp_base,
    with_next,
)

DISPOSITIONS = ("pin", "fold", "state", "precondition")
FOLD_KINDS = ("path", "regex", "json-fields")
CONTROL_SHAPES = ("vary", "drift", "builtin")

#: Why a `regex` fold may not rewrite the subject root, said once for the two
#: refusals that find one doing it: `check_fold_overlap` when the manifest is
#: read, and `normalize_text` during a capture.
_ROOT_FOLD_WHY = ("A regex fold sees the raw text, before the built-in path "
                  "folds, so the root fold would no longer recognize what is "
                  "left of the root, and the rows that print it would record "
                  "a path nobody can read back.")

#: What to do about it, said once for the same two refusals; each ends it in
#: its own way.
_ROOT_FOLD_NEXT = ("Narrow the pattern so its `volatile` group takes all of "
                   "the subject root or none of it, or scope this fold to "
                   "rows that do not print the root")

#: The document authoritative for this file's keys, written once: every
#: refusal that sends a reader to it reads it from here, so the name moves in
#: one edit. It is the FULL path, under the `docs` directory of whichever
#: layout this package is in, because a refusal is read from any directory
#: and a name a reader cannot open is not a `next:`.
_FORMAT_DOC = os.path.join(Layout.detect().data, "docs", "census-format.md")

#: The one pin value golden-census resolves itself: a directory of exactly N
#: characters, made under the machine's temp root for the length of a capture.
FIXED_DIR_RE = re.compile(r"^<FIXED-WIDTH-DIR:(\d+)>$")

#: The width the built-in census pins the subject's TMPDIR to: the ONE place
#: the number 51 is written in this package, and the reason `fixed_dir_refusal`
#: derives both of the numbers it prints rather than being handed either. The
#: arithmetic the refusal states: a directory MADE under a root needs the root,
#: one separator and at least one character of name, so the widest root a
#: capture can run under is this less two — 49, which is exactly the width of
#: macOS's own per-user temp root. The command that prints that root is not
#: written here either: `core.Platform` owns the advice a reader is given, one
#: row per platform. Widen this and that sentence widens with it; there is
#: nothing else to change.
FIXED_DIR_WIDTH = 51

#: The recursion marker: the one variable no census names and every subject
#: environment carries. A subject whose own self-test would run the census
#: again refuses when it sees it; a subject that ignores it behaves as before.
#: Its name is built from `PROG` rather than typed, so the rename carries it.
CHILD_MARKER = PROG.upper().replace("-", "_") + "_CHILD"

#: Its value. One character, deliberately: `probe`'s clause-5 canary ignores
#: values shorter than `CANARY_MIN` because short ones coincide with ordinary
#: output, so a marker under that floor can never be read as contraband and
#: needs no entry in the exempt set. What a subject reads is the NAME.
CHILD_VALUE = "1"


class Row(NamedTuple):
    """One census row. Which fields carry meaning depends on `disposition`;
    `load_census` refuses a row whose disposition and fields disagree."""

    name: str
    disposition: str
    finding: str
    # pin
    variable: str | None = None
    value: str | None = None
    # fold
    kind: str | None = None
    source: str | None = None
    placeholder: str | None = None
    pattern: str | None = None
    regex: re.Pattern[str] | None = None
    #: None means the scope `"*"` — every row of the manifest.
    scope: tuple[str, ...] | None = None
    paths: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    indent: int = 2
    ensure_ascii: bool = False
    # state
    variables: tuple[str, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()
    # precondition
    check: str | None = None
    command: tuple[str, ...] = ()
    expect: str = "exit 0"
    clean: bool = False
    # pins and folds
    control: dict[str, Any] | None = None

    def in_scope(self, row_key: str) -> bool:
        return self.scope is None or row_key in self.scope


class Census(NamedTuple):
    path: str
    directory: str
    fixtures: str | None
    passthrough: tuple[str, ...]
    rows: tuple[Row, ...]
    #: Facts worth printing beside a capture that are not refusals — a path
    #: source no fold names, say.
    notes: tuple[str, ...] = ()

    def of(self, disposition: str) -> tuple[Row, ...]:
        return tuple(r for r in self.rows if r.disposition == disposition)

    @property
    def pins(self) -> tuple[Row, ...]:
        return self.of("pin")

    @property
    def folds(self) -> tuple[Row, ...]:
        return self.of("fold")

    def folds_of(self, kind: str) -> tuple[Row, ...]:
        return tuple(r for r in self.folds if r.kind == kind)

    @property
    def pinned_variables(self) -> tuple[str, ...]:
        return tuple(r.variable for r in self.pins if r.variable)

    @staticmethod
    def builtin() -> Census:
        """The environment golden-census pins when no consumer census says
        otherwise: `COLUMNS=80`, `SOURCE_DATE_EPOCH=0`, a TMPDIR of exactly
        `FIXED_DIR_WIDTH` characters, and `PATH`/`HOME` carried by name.

        The same three pins and the same passthrough as the bundled fixture's
        census, in CODE, so S1's `probe` — which needs a default environment
        and has no consumer file to read one from — feeds this to `build_env`
        rather than hand-typing the rule a second time in prose. `inherit` is
        false by construction: a `Census` carries no other environment, and
        `build_env` builds from nothing.
        """
        return Census(
            path="<builtin>", directory="", fixtures=None,
            passthrough=("PATH", "HOME"),
            rows=(
                Row("terminal width", "pin",
                    "argparse and most renderers wrap at $COLUMNS, so an "
                    "unpinned terminal width moves a surface by itself",
                    variable="COLUMNS", value="80",
                    control={"shape": "vary"}),
                Row("the clock renderers read", "pin",
                    "a renderer stamps the time into what it writes, so two "
                    "runs a second apart differ by bytes nobody changed",
                    variable="SOURCE_DATE_EPOCH", value="0",
                    control={"shape": "drift"}),
                Row("the subject's temp root, and its width", "pin",
                    "a subject that prints a temp path through a fixed-width "
                    "slice records half a path that no fold recognizes unless "
                    "the width is pinned",
                    variable="TMPDIR",
                    value=f"<FIXED-WIDTH-DIR:{FIXED_DIR_WIDTH}>",
                    control={"shape": "builtin", "name": "fixed-width-dir"}),
                # The three `path` folds golden-census's OWN log needs, as
                # rows: one fold serves a probe's banner, a capture's header
                # and a `census` header alike. Without them a command has no
                # vocabulary to fold its own log through and prints the
                # machine unfolded, or invents a private one. A `clone` row is
                # absent because nothing that runs under this census makes one
                # — a fold with no directory folds nothing.
                Row("the directory the command was run in", "fold",
                    "a tool that prints its own working directory prints "
                    "this machine, and a report pasted into a hand-back is "
                    "about the run rather than about where it was run",
                    kind="path", source="root", placeholder="<CWD>"),
                Row("the temp root golden-census makes its own directories "
                    "under", "fold",
                    "the width of this directory's path is a fact about the "
                    "machine, and a command's output must read the same "
                    "under any temp root",
                    kind="path", source="work", placeholder="<TMPROOT>"),
                Row("the fixed-width temp directory", "fold",
                    "the directory golden-census makes for the subject to run "
                    "under is this run's and nobody else's, so its name says "
                    "nothing a reader of the report can use",
                    kind="path", source="fixed-width-dir",
                    placeholder="<TMPDIR>"),
            ))

    @property
    def fixed_width(self) -> int | None:
        """The N of the `<FIXED-WIDTH-DIR:N>` pin, or None when no row asks
        for one. `compare --against` and the self-check make no such
        directory and run at any width."""
        return next((int(found.group(1)) for row in self.pins
                     if (found := FIXED_DIR_RE.match(row.value or ""))), None)


# ------------------------------------------------------------------ loading


#: The census's own top-level tables, and the keys of the two that are tables
#: of keys rather than of rows — each beside the code that reads it.
_CENSUS_KEYS = ("environment", "fixtures", "input")
_ENVIRONMENT_KEYS = ("inherit", "passthrough")
_FIXTURES_KEYS = ("dir",)


def load_census(path: str) -> Census:
    """Read a census file and check it, before anything is run.

    Every check here costs one sentence; the same wrong row found at capture
    time costs the capture.
    """
    path = os.path.abspath(path)
    # `load_toml` refuses an unfilled hole on the text it read, before the
    # parse: a hole is not a syntax error, and a reader whose census is a
    # scaffold with the holes still in it is better served by "fill
    # SUBJECT_NAME" than by a parser's complaint about the line it sits on.
    document, directory = load_toml(path, "census file",
                                    prefix=f"census {path}: ")
    only_keys(document, _CENSUS_KEYS, f"census {path}: the census",
              _FORMAT_DOC)
    environment = table(document, "environment", f"census {path}")
    only_keys(environment, _ENVIRONMENT_KEYS,
              f"census {path}: [environment]", _FORMAT_DOC)
    if environment.get("inherit", None) is not False:
        raise Refusal(
            f"census {path}: [environment] inherit must be present and false — "
            "it is the only value golden-census accepts. Every subject "
            "subprocess runs under an environment built from nothing: the "
            "pins, the passthrough list, the surface's own `env`, and "
            "golden-census's child marker.",
            next="Write `inherit = false` in the census's [environment] table; every other value "
            "is refused.")
    passthrough = strings(environment.get("passthrough", []),
                          f"census {path}: [environment] passthrough")

    fixtures = None
    fixtures_table = table(document, "fixtures", f"census {path}")
    only_keys(fixtures_table, _FIXTURES_KEYS, f"census {path}: [fixtures]",
              _FORMAT_DOC)
    if "dir" in fixtures_table:
        # `dir` has a vocabulary of its own, and this block is its one owner:
        # a path relative to this census's directory, or absolute, in which `<HERE>` — the
        # census's directory, the one name with a value when the census is
        # read — is the only placeholder. Any other token, one of the
        # census's vocabulary or none, is refused here in one sentence,
        # before the path is joined: a token left in the path names a
        # directory no `drift` control could ever find. What is left is
        # expanded through the census's vocabulary, which values `<HERE>`.
        spelled = str(fixtures_table["dir"])
        if any(token != "<HERE>" for token in TOKEN_RE.findall(spelled)):
            raise Refusal(
                f"census {path}: [fixtures] dir takes a path, relative to this "
                "census's directory or absolute, in which <HERE> is the one "
                f"placeholder it may spell; it was given {spelled!r}.",
                next="Spell `dir` relative to this census's directory, begin it "
                "with <HERE>, or give an absolute path.")
        fixtures = os.path.normpath(os.path.join(
            directory, _env_context(None, directory).expand(
                spelled, f"census {path}: [fixtures] dir")))
        if not os.path.isdir(fixtures):
            raise Refusal(
                f"census {path}: [fixtures] dir {fixtures_table['dir']!r} "
                f"names {fixtures}, which is not a directory",
                next="Point `dir` at the directory beside this census that holds "
                "the controls' files, spelled relative to the census, or delete "
                "the [fixtures] table if no control needs one.")

    raw_rows = document.get("input", [])
    if not isinstance(raw_rows, list) or not raw_rows:
        raise Refusal(f"census {path}: no [[input]] rows — a census with no "
                      "rows states that nothing outside the subject can move "
                      "a surface, which has never been true of anything.",
                      next="Write one [[input]] row per thing outside the subject that can move a "
                      f"surface; {_FORMAT_DOC} has the shapes.")
    rows = tuple(_row(raw, path) for raw in raw_rows)
    _refuse_pins_that_disagree(rows, path)
    json_rows = tuple(row for row in rows if row.kind == "json-fields")
    if json_rows:
        _one_serialization(json_rows, path)
    # A json-fields control's two files, READ here rather than when the
    # control runs: a file that is missing, will not open or is not UTF-8 is a
    # fact about the census, knowable before anything runs, and read later it
    # was a SKIP under `capture complete` — or, undecodable, a `[FAIL]  !`.
    for row in rows:
        if row.kind != "json-fields":
            continue
        control = row.control or {}
        if fixtures is None:
            raise Refusal(
                f"census {path}: row {row.name!r} is a json-fields fold, and "
                "this census has no [fixtures] dir to find its control's files "
                "in",
                next="Add a [fixtures] table with `dir = \"...\"`, the directory "
                f"beside this census that holds {control['sample']} and "
                f"{control['moved']}.")
        for key in ("sample", "moved"):
            joined = os.path.join(fixtures, str(control[key]))
            where = (f"census {path}: row {row.name!r}: its control's "
                     f"`{key}` file {joined}")
            _read_source(joined, where, where, False)

    notes = []
    named_sources = {r.source for r in rows if r.kind == "path"}
    missing = [s for s in PATH_SOURCES if s not in named_sources]
    if missing:
        notes.append(
            "no `path` fold names " + ", ".join(missing)
            + ". If a captured file prints one of those directories, the "
            "contraband scan refuses the capture.")
    return Census(path, directory, fixtures, passthrough, rows, tuple(notes))


def _refuse_pins_that_disagree(rows: tuple[Row, ...], path: str) -> None:
    """Two pin rows that cannot both hold are a refusal naming both.

    `build_env` sets every pin in turn, so a variable two rows pin keeps the
    later value and the earlier row pins nothing. `Census.fixed_width` is the
    first `<FIXED-WIDTH-DIR:N>` pin's N, and a capture makes ONE directory of
    that width, so a second pin of another width would run at a width its row
    does not state. The controls of both rows pass either way.
    """
    pinned: dict[str, Row] = {}
    fixed: Row | None = None
    width = 0
    for row in rows:
        if row.disposition != "pin" or not row.variable:
            continue
        if row.variable in pinned:
            first = pinned[row.variable]
            raise Refusal(
                f"census {path}: rows {first.name!r} and {row.name!r} both "
                f"pin {row.variable}, to {first.value!r} and to "
                f"{row.value!r}. A subject's environment holds one value of "
                "a variable, so the later row replaces the earlier and the "
                "earlier pins nothing.",
                next="Write each pinned variable in one row only: drop one of "
                "the two rows, or pin a different variable in one of them.")
        pinned[row.variable] = row
        wanted = FIXED_DIR_RE.match(row.value or "")
        if wanted is None:
            continue
        if fixed is None:
            fixed = row
            width = int(wanted.group(1))
        elif width != int(wanted.group(1)):
            raise Refusal(
                f"census {path}: rows {fixed.name!r} and {row.name!r} pin "
                f"{fixed.value} and {row.value}. A capture makes one "
                "fixed-width directory, of the first width, so the other row "
                "would run at a width its census does not state.",
                next="Use one width in every <FIXED-WIDTH-DIR:N> pin of this "
                "census.")


#: The three keys EVERY [[input]] row carries, whatever its disposition. Each
#: disposition's own keys are declared beside the function that reads them,
#: and that function makes the one `only_keys` call for its row — after the
#: dispatch below, which is where the disposition is known.
#:
#: `control` is NOT one of them. Only a pin and a fold read one, so it is
#: declared in those two key tuples and in no other: listed here it was
#: accepted on a `state` and a `precondition` row and dropped without a word,
#: which is the defect this whole rule exists to refuse.
_ROW_KEYS = ("name", "disposition", "finding")


def _row(raw: Any, where: str) -> Row:
    if not isinstance(raw, dict):
        raise Refusal(f"census {where}: every [[input]] must be a table",
                      next="Write the row as [[input]] with `name`, `disposition` and `finding` "
                      "keys.")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise Refusal(f"census {where}: an [[input]] row has no `name`",
                      next="Give the row a `name`: it is the word every control row and every "
                      "refusal about it uses.")
    place = f"census {where}: row {name!r}"
    disposition = str(raw.get("disposition", ""))
    if disposition not in DISPOSITIONS:
        raise Refusal(f"{place}: disposition {disposition!r} is not one of "
                      + ", ".join(DISPOSITIONS),
                      next="Set `disposition` to one of the four listed above.")
    finding = str(raw.get("finding", "")).strip()
    if not finding:
        raise Refusal(
            f"{place}: no `finding`. Every row states the sentence that says "
            "how this input was SEEN to move a surface; a row nobody measured "
            "is a guess with a placeholder's authority.",
            next="Write the `finding` as the sentence saying how this input was SEEN to move a "
            "surface.")
    # The SHAPE of a `control`, before the dispatch, because both readers of
    # the key want a table. Whether the row may carry the key at all is the
    # `only_keys` call inside each of the four, which is where the disposition
    # is known: a `state` row's `control` is refused there by name.
    control = raw.get("control")
    if control is not None and not isinstance(control, dict):
        raise Refusal(f"{place}: `control` must be a table",
                      next="Write `control = { shape = \"...\", ... }` as an inline table.")

    if disposition == "pin":
        return _pin_row(raw, name, finding, control, place)
    if disposition == "fold":
        return _fold_row(raw, name, finding, control, place)
    if disposition == "state":
        return _state_row(raw, name, finding, place)
    return _precondition_row(raw, name, finding, place)


#: Every key a pin row reads, and every key its `control` reads, by shape —
#: the sets differ with the shape, and the shape is checked just above the
#: call, so the table's rule is asked once with the right set.
_PIN_KEYS = ("control", "variable", "value")
_PIN_CONTROL_KEYS = {
    "vary": ("shape", "surface", "value"),
    "drift": ("shape", "command", "output", "wait"),
    "builtin": ("shape", "name"),
}


def drift_output(spelled: str) -> str | None:
    """A `drift` control's `output` as a path relative to the work directory
    its command runs in, or None when it names no file under it.

    `output` is written relative to `<WORK>`, or opens with `<WORK>/`. What
    is left, after `<WORK>` and every slash that follows it, holds no other
    placeholder, is not absolute, does not climb out with `..` and names
    more than `<WORK>` itself: a rule about the SPELLING, asked when the
    census is read, when no work directory exists yet. Where the path
    RESOLVES, links followed, is asked before each of the control's runs
    and after it, by `controls._drift_control`. ONE reader of the spelling,
    for the census's refusal and the control's path. An `output` that is not
    a string, and an empty one, are `_pin_row`'s refusals before this is
    asked: absent, `output` means the command's standard output.
    """
    rest = (spelled.removeprefix("<WORK>").lstrip("/")
            if spelled.startswith("<WORK>/") else spelled)
    below = os.path.normpath(rest) if rest else os.curdir
    if (TOKEN_RE.search(rest) or os.path.isabs(rest)
            or below in (os.curdir, os.pardir)
            or below.startswith(os.pardir + os.sep)):
        return None
    return below


def _pin_row(raw: dict[str, Any], name: str, finding: str,
             control: dict[str, Any] | None, place: str) -> Row:
    only_keys(raw, _ROW_KEYS + _PIN_KEYS, place, _FORMAT_DOC)
    variable = raw.get("variable")
    value = raw.get("value")
    if not isinstance(variable, str) or not variable:
        raise Refusal(f"{place}: a pin needs a `variable`",
                      next="Add `variable = \"NAME\"`, the environment variable this row pins.")
    if variable == CHILD_MARKER:
        raise Refusal(
            f"{place}: {variable} is set by golden-census in every subject "
            "environment, after the pins, and cannot be pinned by a census. "
            f"{_MARKER_IS_A_FACT}; a pin of it is a value no subject run "
            "receives.",
            next=f"Drop the census row that pins {variable}; nothing a "
                 "census can say about it is true.")
    if not isinstance(value, str):
        raise Refusal(f"{place}: a pin needs a `value` (a string)",
                      next="Add `value = \"...\"` as a string; a pin with no value pins nothing.")
    # Before anything is run, not when `build_env` reaches for the value: a
    # pin spelling `<TMP>` costs the whole capture it was read for.
    # `<FIXED-WIDTH-DIR:N>` is the one value golden-census resolves itself and
    # is not a placeholder of this vocabulary, so it is recognized first —
    # by the same regex `_pin_value` resolves it with, never a second one.
    if not FIXED_DIR_RE.match(value):
        _env_context().check(value, f"{place}: value")
    if control is None:
        raise Refusal(
            f"{place}: a pin needs a `control`. A pin nobody can show matters "
            "is a claim, not a measurement.",
            next="Add a `control` — `{ shape = \"vary\", surface = \"<input>/<surface>\", value = "
            "\"...\" }` shows the pin matters.")
    shape = control.get("shape")
    if shape not in CONTROL_SHAPES:
        raise Refusal(f"{place}: control shape {shape!r} is not one of "
                      + ", ".join(CONTROL_SHAPES),
                      next="Set `control.shape` to one of the three listed above.")
    only_keys(control, _PIN_CONTROL_KEYS[str(shape)], f"{place}: control",
              _FORMAT_DOC)
    if shape == "vary" and not isinstance(control.get("surface"), str):
        raise Refusal(f"{place}: a `vary` control needs a `surface` "
                      "(`<input>/<surface>`)",
                      next="Add `surface = \"<input>/<surface>\"` naming the manifest row the "
                      "varied value is measured on.")
    if shape == "vary" and not isinstance(control.get("value"), str):
        raise Refusal(f"{place}: a `vary` control needs the `value` it varies to",
                      next="Add `value = \"...\"`, the second value the control varies the pin to.")
    if shape == "drift" and not isinstance(control.get("command"), list):
        raise Refusal(f"{place}: a `drift` control needs a `command`",
                      next="Add `command = [...]`, the argv the control runs four times to show "
                      "the drift.")
    if shape == "drift":
        for element in control.get("command", []):
            _control_context().check(str(element),
                                     f"{place}: control command")
        # The command runs in the work directory, so a program named by a
        # relative path with a `/` is looked for there, where nothing of the
        # census's is, and no PATH is asked: refused here, by name, rather
        # than met as a program that would not start or is not on PATH.
        program = str((control.get("command") or [""])[0])
        if ("/" in program and not program.startswith("/")
                and not TOKEN_RE.match(program)):
            raise Refusal(
                f"{place}: the `drift` control's command names its program "
                f"{program!r} by a relative path, which is looked for in the "
                "work directory the command runs in, not beside this census "
                "or under the subject root.",
                next="Spell the program from this census's directory as "
                "`<HERE>/…` or from the subject root as `<ROOT>/…`, or name "
                "a program on PATH.")
        # One remedy for an `output` that names no file at all, whether it
        # is not a string or is an empty one.
        unnamed = ("Leave `output` out to compare what the command prints, "
                   "or write it relative to the work directory the command "
                   "runs in, or open it with `<WORK>/`.")
        if "output" in control and not isinstance(control["output"], str):
            raise Refusal(
                f"{place}: the `drift` control's `output` must be a string, "
                f"not the {type(control['output']).__name__} "
                f"{control['output']!r}",
                next=unnamed)
        if isinstance(control.get("output"), str):
            _control_context().check(str(control["output"]),
                                     f"{place}: control output")
            if not control["output"]:
                raise Refusal(
                    f"{place}: the `drift` control's `output` is empty",
                    next=unnamed)
            if drift_output(control["output"]) is None:
                raise Refusal(
                    f"{place}: the `drift` control's `output` "
                    f"{control['output']!r} is not a file under <WORK>",
                    next="Write `output` relative to the work directory the "
                    "command runs in, or open it with `<WORK>/`, and have the "
                    "command write that file there: the control removes it "
                    "before each of its four runs and reads what the run "
                    "wrote.")
    if shape == "builtin" and control.get("name") != "fixed-width-dir":
        raise Refusal(f"{place}: the only builtin control is "
                      f"`fixed-width-dir`, not {control.get('name')!r}",
                      next="Write `control = { shape = \"builtin\", name = \"fixed-width-dir\" }`, "
                      "the one builtin golden-census carries.")
    # The control measures `Census.fixed_width`, the census's own
    # `<FIXED-WIDTH-DIR:N>` pin, whichever row carries the control: on a pin
    # of another value it would pass and say nothing about that pin.
    if shape == "builtin" and not FIXED_DIR_RE.match(value):
        raise Refusal(
            f"{place}: the `fixed-width-dir` control measures a pin whose "
            f"value is `<FIXED-WIDTH-DIR:N>`, and this pin's value is "
            f"{value!r}. The control would measure the width of the census's "
            "fixed-width pin, a different row, and say nothing about this "
            "one.",
            next="Give the control only to the pin whose value is "
            "`<FIXED-WIDTH-DIR:N>`, and give this pin a `vary` or `drift` "
            "control.")
    return Row(name, "pin", finding, variable=variable, value=value,
               control=control)


#: Every key a fold row reads, and every key its `control` reads. The UNION of
#: the three fold kinds' keys, not one set per kind: the granularity is the
#: table, exactly as it is for a surface, and the per-kind refusals below
#: already say what each kind needs. A `path` fold's control is built in, so
#: the control set is the one the other two kinds declare.
_FOLD_KEYS = ("control", "kind", "placeholder", "scope", "source", "pattern",
              "paths", "fields")
#: The one key outside that union: a json-fields fold reads `serialization`,
#: and a `regex` or `path` fold carrying it is refused as carrying a key
#: golden-census does not read, since no per-kind refusal below would say so.
_JSON_FIELDS_KEYS = ("serialization",)
_FOLD_CONTROL_KEYS = ("sample", "moved")
#: Every key a json-fields fold's `serialization` table reads.
_SERIALIZATION_KEYS = ("indent", "ensure_ascii")


def _fold_row(raw: dict[str, Any], name: str, finding: str,
              control: dict[str, Any] | None, place: str) -> Row:
    # A `kind` that is none of the three keeps `serialization`, so its row is
    # refused for the kind, below, and not for a key that kind might read.
    only_keys(raw, _ROW_KEYS + _FOLD_KEYS
              + (() if raw.get("kind") in ("regex", "path")
                 else _JSON_FIELDS_KEYS), place, _FORMAT_DOC)
    if control is not None:
        only_keys(control, _FOLD_CONTROL_KEYS, f"{place}: control",
                  _FORMAT_DOC)
    kind = raw.get("kind")
    if kind not in FOLD_KINDS:
        raise Refusal(f"{place}: fold kind {kind!r} is not one of "
                      + ", ".join(FOLD_KINDS),
                      next="Set `kind` to one of the three listed above.")
    placeholder = raw.get("placeholder")
    if not isinstance(placeholder, str) or not placeholder:
        raise Refusal(f"{place}: a fold needs a `placeholder`",
                      next="Add `placeholder = \"<TOKEN>\"`, the token the folded text is replaced "
                      "by in every golden.")
    scope: tuple[str, ...] | None = None
    # The two spellings of "every row" mean the same thing: the string `"*"`,
    # and a list whose every element is `"*"`. The format offers a bare string
    # and a list, and a reader who took the list to be the form says the
    # default in the spelling their file already uses — refusing that would
    # teach a difference that carries no meaning.
    raw_scope = raw.get("scope", "*")
    every_row = raw_scope == "*" or (isinstance(raw_scope, list)
                                     and bool(raw_scope)
                                     and all(entry == "*"
                                             for entry in raw_scope))
    if not every_row:
        if isinstance(raw_scope, list) and "*" in raw_scope:
            raise Refusal(
                f"{place} scopes its fold to both \"*\" and named rows: "
                f"{raw_scope!r}. \"*\" is every row, so a list that also names "
                "rows says two things at once, and only one of them can be "
                "what the fold does.",
                next="Write `scope = \"*\"` for every row, or list only the "
                "`<input>/<surface>` keys this fold applies to.")
        scope = strings(raw_scope, f"{place}: scope")
        # A NARROWING scope only: `scope = "*"` is the default said out loud
        # and costs nothing. A narrowing one is read at a single site — the
        # regex loop in `normalize_text` — while `normalize_paths` takes no
        # row key, and `normalize_json` applies its `json-fields` folds to the
        # whole document before the row's regex folds see it: a scoped `path`
        # or `json-fields` fold would be a key the loader checked and the
        # comparator ignored. The REGEX half of a `.json` file honors a
        # narrowing scope, because it goes through `normalize_text`.
        if kind != "regex":
            raise Refusal(
                f"{place}: `scope` narrows a `regex` fold and nothing else, "
                f"and this row is a `{kind}` fold. A path fold folds the "
                "directories golden-census made wherever they appear, and a "
                "json-fields fold blanks its `fields` in every document under "
                "its `paths`; neither is given the row key a scope would be "
                "matched against, so a narrowing scope here would be checked "
                "when the census is read and ignored when the bytes are "
                "recorded.",
                next="Drop `scope` from this row, or write `scope = \"*\"`, which is "
                "this fold's own rule said out loud. To narrow what a path fold "
                "reaches, name a narrower directory; to narrow a json-fields "
                "fold, name narrower `paths`.")

    if kind == "path":
        source = raw.get("source")
        if source not in PATH_SOURCES:
            raise Refusal(f"{place}: source {source!r} is not one of "
                          + ", ".join(PATH_SOURCES),
                          next="Set `source` to one of the four listed above, the directory this "
                          "fold folds away.")
        # A path fold's control is golden-census's own — an absolute directory
        # it made is folded, and an absolute path it did not make is not.
        # The census format's example rows carry no `control` key for exactly
        # this reason; `census_controls` supplies one.
        return Row(name, "fold", finding, kind="path", source=str(source),
                   placeholder=placeholder, scope=scope, control=control)

    if control is None or not isinstance(control.get("sample"), str) \
            or not isinstance(control.get("moved"), str):
        raise Refusal(
            f"{place}: a {kind} fold needs a `control` with `sample` and "
            "`moved`. A fold that cannot be shown to fire could be blinding "
            "the comparator.",
            next="Add `control = { sample = \"...\", moved = \"...\" }`: two texts differing only "
            "in what the fold folds.")

    if kind == "regex":
        pattern = raw.get("pattern")
        if not isinstance(pattern, str):
            raise Refusal(f"{place}: a regex fold needs a `pattern`",
                          next="Add `pattern = \"...\"` with a (?P<volatile>...) group around the "
                          "part that moves.")
        try:
            regex = re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            raise Refusal(f"{place}: pattern does not compile: {exc}",
                          next="Fix that regular expression; it is compiled when the "
                          "census is read, before anything runs.") from exc
        if "volatile" not in regex.groupindex:
            raise Refusal(
                f"{place}: the pattern has no group named `volatile`. Only "
                "that group is replaced, so the rest of the line stays a byte "
                "comparison — a pattern without one would fold the line.",
                next="Wrap the moving part of the pattern in (?P<volatile>...); everything outside "
                "it stays a byte comparison.")
        return Row(name, "fold", finding, kind="regex", pattern=pattern,
                   regex=regex, placeholder=placeholder, scope=scope,
                   control=control)

    paths = strings(raw.get("paths", []), f"{place}: paths")
    fields = strings(raw.get("fields", []), f"{place}: fields")
    if not paths or not fields:
        raise Refusal(f"{place}: a json-fields fold needs `paths` and `fields`",
                      next="Add `paths = [...]` (the surfaces) and `fields = [...]` (the JSON keys "
                      "blanked in them).")
    serialization = raw.get("serialization", {})
    if not isinstance(serialization, dict):
        raise Refusal(f"{place}: `serialization` must be a table",
                      next="Write `serialization = { indent = N, ensure_ascii = false }` as an "
                      "inline table.")
    only_keys(serialization, _SERIALIZATION_KEYS, f"{place}: serialization",
              _FORMAT_DOC)
    indent = serialization.get("indent", 2)
    ensure_ascii = serialization.get("ensure_ascii", False)
    # A TOML `true` is a Python `bool`, which is an `int`: tested first, so
    # `indent = true` is refused rather than read as an indent of 1.
    if isinstance(indent, bool) or not isinstance(indent, int) \
            or not isinstance(ensure_ascii, bool):
        raise Refusal(f"{place}: serialization needs an integer `indent` and a "
                      "boolean `ensure_ascii`",
                      next="Write `indent` as an integer and `ensure_ascii` as a boolean, matching "
                      "the subject's own json.dumps call.")
    return Row(name, "fold", finding, kind="json-fields", paths=paths,
               fields=fields, placeholder=placeholder, scope=scope,
               indent=indent, ensure_ascii=ensure_ascii, control=control)


#: Every key a state row reads, beside it.
_STATE_KEYS = ("variables", "commands")


def _state_row(raw: dict[str, Any], name: str, finding: str, place: str) -> Row:
    only_keys(raw, _ROW_KEYS + _STATE_KEYS, place, _FORMAT_DOC)
    variables = strings(raw.get("variables", []), f"{place}: variables")
    raw_commands = raw.get("commands", [])
    if not isinstance(raw_commands, list):
        raise Refusal(f"{place}: `commands` must be a list of argv lists",
                      next="Write `commands = [[\"prog\", \"--flag\"], ...]`: a list whose every "
                      "entry is itself a list of strings.")
    commands = tuple(strings(c, f"{place}: a command") for c in raw_commands)
    for command in commands:
        if not command:
            raise Refusal(f"{place}: a command in `commands` is an empty list",
                          next="Give every entry of `commands` at least its "
                               "program: `[\"prog\", \"--flag\"]`.")
        for text in command:
            _env_context().check(text, f"{place}: a command")
    return Row(name, "state", finding, variables=variables, commands=commands)


#: Every key a precondition row reads, beside it.
_PRECONDITION_KEYS = ("check", "expect", "command", "clean")


def _precondition_row(raw: dict[str, Any], name: str, finding: str,
                      place: str) -> Row:
    only_keys(raw, _ROW_KEYS + _PRECONDITION_KEYS, place, _FORMAT_DOC)
    check = raw.get("check")
    if check not in ("git-checkout", "command"):
        raise Refusal(f"{place}: check {check!r} is not `git-checkout` or "
                      "`command`",
                      next="Set `check` to `git-checkout` or `command`.")
    command: tuple[str, ...] = ()
    expect = str(raw.get("expect", "exit 0"))
    if check == "command":
        command = strings(raw.get("command", []), f"{place}: command")
        if not command:
            raise Refusal(f"{place}: a `command` check needs a `command`",
                          next="Add `command = [...]`, the argv this precondition runs.")
        if expect not in ("exit 0", "empty stdout"):
            raise Refusal(f"{place}: expect {expect!r} is not `exit 0` or "
                          "`empty stdout`",
                          next="Set `expect` to `exit 0` or `empty stdout`.")
        for text in command:
            _env_context().check(text, f"{place}: command")
    return Row(name, "precondition", finding, check=str(check), command=command,
               expect=expect, clean=bool(raw.get("clean", False)))


def check_scopes(census: Census, known_rows: frozenset[str]) -> None:
    """Every `scope` names rows the manifest defines.

    Called by `load_manifest`, because a scope is a statement about the
    manifest's rows and the census alone cannot check it.

    Only `regex` folds are walked, and there is nothing else to walk: a
    narrowing `scope` on any other kind is refused when the census is read,
    so by the time a manifest is loaded no other fold can carry one.
    """
    for row in census.folds_of("regex"):
        for key in row.scope or ():
            if key not in known_rows:
                raise Refusal(
                    f"census {census.path}: row {row.name!r} scopes its fold to "
                    f"{key!r}, which is no row of this manifest. A fold scoped "
                    "to a row nobody records is a fold nobody runs.",
                    next="Spell the scope as one of the manifest's own `<input>/<surface>` keys. "
                    "To apply the fold to every row, write `scope = \"*\"` in the "
                    "census instead of listing rows.")


def check_controls(census: Census, runnable: frozenset[str]) -> None:
    """Every `vary` control names a row the manifest records whose surface
    runs.

    Called by `load_manifest` beside `check_scopes`, for the same reason: the
    control is a statement about the manifest's rows, and the census alone
    cannot check it. `runnable` is the manifest's `<input>/<surface>` keys
    whose surface is `kind = "run"` — the only rows a `vary` control can run
    twice and compare. After this, `_vary_control`'s lookup cannot fail.
    """
    for row in census.pins:
        control = row.control or {}
        key = control.get("surface")
        if control.get("shape") == "vary" and key not in runnable:
            raise Refusal(
                f"census {census.path}: row {row.name!r}: its `vary` control "
                f"names {key!r}, which is no `run` row this manifest records",
                next="Spell the control's `surface` as one of the manifest's "
                "own `<input>/<surface>` keys whose surface runs — no `kind`, "
                "or `kind = \"run\"`.")


def check_fold_overlap(census: Census, root: str) -> None:
    """No fold that applies to EVERY row has a `volatile` group that SPLITS
    the subject root's own absolute path — replaces part of it and leaves a
    fragment. `_root_overlap` is the test; a group that takes the whole root
    leaves no fragment and loads.

    A `regex` fold sees the raw text, before the built-in `path` folds, and
    that order is a contract rather than an accident: a consumer's fold names
    the subject's own temporary directories, which are made UNDER a directory
    a `path` fold folds, and running the path folds first would leave the
    regex matching from the character after a placeholder. So a pattern broad
    enough to match inside the subject root replaces part of that root before
    the root fold ever sees it, the root fold then fails to recognize what is
    left, and the row that reddens is golden-census's own path fold control —
    blaming golden-census for a row the consumer wrote.

    Four limits, each deliberate:

    1. **Only `*`-scoped folds are walked.** A fold with a narrowing `scope`
       runs on the rows it names, and whether those rows print the root is a
       fact of their text, which the manifest does not hold. `normalize_text`
       asks the same question of every fold in scope during the capture, so a
       scoped fold that splits the root in a row it is scoped to is refused
       there, naming the row.
    2. **Only the subject root is tested.** It is the only one of the four
       `path` sources that EXISTS when a manifest is read — the work
       directory, a clone and the fixed-width directory are made per run — so
       the smallest rule and the only available one are the same rule. Testing
       the temp base instead, which is knowable, would make the same manifest
       load on one machine and refuse on another, which is not deterministic.
       What the bare root cannot show — a pattern that needs the text around
       the root to match — `normalize_text` sees at capture time, where the
       row and its text are known.
    3. **It runs once, at load, against the subject root.**
       `Manifest.with_root` hands the same manifest back against a different
       COPY of the subject, which is what `mutants` runs against every clone,
       and nothing calls this again for that root. Every capture of a clone
       still passes through `normalize_text` with the clone as the root, so a
       fold that splits the clone's path in a row's text is refused there.
    4. **The `volatile` GROUP decides, not the match.** `fold_regex` replaces
       that group and leaves every other byte of the match alone, so this
       test asks the group the same question and quotes the group's own text.
       A match the group took no part in — one branch of an alternation
       matching where the group is in the other — moves nothing, and is no
       overlap; the search goes on past it, because a later match may
       participate.
    """
    for row in census.folds_of("regex"):
        if row.scope is not None:
            continue
        hit = _root_overlap(row, root, (root,))
        if hit is not None:
            raise Refusal(
                f"census {census.path}: row {row.name!r} folds EVERY row "
                "(scope = \"*\"), and its pattern matches inside the subject "
                "root's own absolute path — it would replace "
                f"{hit.group('volatile')!r} in it. {_ROOT_FOLD_WHY}",
                next=f"{_ROOT_FOLD_NEXT} — `scope = "
                "[\"<input>/<surface>\", …]`.")


# ----------------------------------------------------------- the environment


def build_env(census: Census, roots: Roots,
              extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment every subject subprocess runs under, built FROM NOTHING.

    The pinned variables at their pinned values, the passthrough list, the
    surface's own `env`, and golden-census's child marker, and nothing
    golden-census's own environment happens to hold. A variable the census
    does not name cannot reach the subject, so it cannot move a surface:
    enforcement by construction, not detection.

    The ONE variable no census names and every subject gets is `CHILD_MARKER`.
    It is set after the pins and the passthrough and cannot be overridden,
    because what it says is true of the run rather than of the subject: this
    process was started by golden-census. A subject whose own self-test would
    run the census again reads it and refuses; a subject that ignores it
    behaves exactly as it did before. `docs/contract.md` names it under what
    golden-census gives back, as a clause a subject MAY honor.
    """
    env: dict[str, str] = {}
    for row in census.pins:
        if not row.variable:
            continue
        value = _pin_value(row, roots, census.directory or None)
        if value is None:            # a directory this run never made
            continue
        env[row.variable] = value
    for name in census.passthrough:
        if name not in env and name in os.environ:   # a pin outranks a passthrough
            env[name] = os.environ[name]
    env[CHILD_MARKER] = CHILD_VALUE
    return surface_env(census, env, extra or {})


#: What the child marker states, in both refusals of a census or a manifest
#: that sets it: a census pin (`_pin_row`) and a surface's `env`
#: (`surface_env`).
_MARKER_IS_A_FACT = ("It states that this process was started by "
                     "golden-census, which is a fact about the run")


def surface_env(census: Census, env: Mapping[str, str],
                extra: Mapping[str, str], place: str = "env") -> dict[str, str]:
    """`env` with a surface's own `env` (`extra`, already expanded) on top:
    the ONE owner of "a surface's `env` on top of an environment", and of
    the two things it may not do.

    `build_env` ends here with the environment it built, and a caller that
    was HANDED one — a capture's row, the `vary` control's varied run —
    comes here with that, so a value the caller set survives the surface's
    own. Neither refusal lets a surface undo the environment: the child
    marker is a fact about the run, and a pinned variable is the census's.

    `place` opens both refusals. The manifest's load passes the file and the
    `[surfaces.<name>]` table, as its own refusals open; a caller that runs
    a row passes nothing, and the refusal opens `env`.
    """
    built = dict(env)
    for name, value in extra.items():
        if name == CHILD_MARKER:
            raise Refusal(
                f"{place}: {name} is set by golden-census in every subject "
                "environment and cannot be overridden by a surface's `env`. "
                f"{_MARKER_IS_A_FACT}; a surface that unset it would "
                "be telling a subject it is not being captured while it is.",
                next="Drop the surface's `env` override of "
                     f"{name}; nothing a surface can say about it is true.")
        if name in census.pinned_variables:
            raise Refusal(
                f"{place}: {name} is pinned by the census (row "
                f"{_pin_named(census, name)!r}) and cannot be overridden by a "
                "surface's `env`. Change the pin or drop the override; a "
                "surface that quietly unpins a variable records a golden about "
                "the override, not about the subject.",
                next="Change the census pin, or drop the surface's `env` override; one of the two "
                "owns the variable.")
        built[name] = value
    return built


def _pin_named(census: Census, variable: str) -> str:
    return next((row.name for row in census.pins if row.variable == variable),
                variable)


def _pin_value(row: Row, roots: Roots, here: str | None = None) -> str | None:
    found = FIXED_DIR_RE.match(row.value or "")
    if found:
        return roots.fixed
    return _env_context(roots, here).expand(row.value or "",
                                            f"census row {row.name!r}")


def _env_context(roots: Roots | None = None,
                 here: str | None = None) -> Placeholders:
    """The census's ONE placeholder vocabulary: the names a census string may
    spell, and their values in a run.

    `load_census` builds it with no roots — the NAMES are all a load-time check
    needs — so a pin value or a command row spelling a token golden-census does
    not define is refused with the rest of the census's errors, before anything
    runs, and never when `build_env` reaches for the value ten minutes into a
    capture. `<FIXTURE>` is added by the controls
    (`Placeholders.also`), which are the only census strings allowed to name
    one.

    `<HERE>` is the directory of the file that spells it — this census's own —
    and it is a name of this vocabulary and of the mutants file's, and of no
    other. The manifest's neighbors already resolve through
    `manifest._relative`, so a manifest that spelled it earns the ordinary
    unknown-token refusal naming the whole list. A run whose census has no
    directory (`Census.builtin()`, which is code and not a file) passes None,
    so a `<HERE>` there refuses "has no value in this run" rather than
    expanding to nothing. The four names every run has are
    `core.roots_vocabulary`'s; this vocabulary adds the one that is its own.
    """
    return roots_vocabulary(roots).also({"HERE": here})


def _control_context(roots: Roots | None = None,
                     fixtures: str | None = None,
                     here: str | None = None) -> Placeholders:
    """The census's vocabulary plus `<FIXTURE>`, built FROM it: a `drift`
    control's command is the one census string the format lets name the
    fixtures directory."""
    return _env_context(roots, here).also({"FIXTURE": fixtures})


# ------------------------------------------------------------- normalization


def path_pairs(census: Census, roots: Roots) -> list[tuple[str, str]]:
    """The `(directory, token)` pairs the census's `path` rows fold under
    `roots`: each row whose directory this run has, with its placeholder.

    The one builder of them: `normalize_paths` folds with these, and the
    contraband scan is handed their tokens, so the tokens the scan sets a
    path aside after are exactly the ones the fold wrote into this text.
    """
    pairs: list[tuple[str, str]] = []
    for row in census.folds_of("path"):
        value = roots.by_source(row.source or "")
        if value and row.placeholder:
            pairs.append((value, row.placeholder))
    return pairs


def normalize_paths(text: str, census: Census, roots: Roots) -> str:
    """Fold the absolute paths of directories golden-census made, and of the
    subject root, into the placeholders the census's `path` rows name.

    The census's `path` rows are the VOCABULARY (`path_pairs`); the
    algorithm — longest first, both `realpath` forms — is `core.fold`'s.
    """
    return fold(text, path_pairs(census, roots))


@functools.cache
def _on_path(name: str, _path: str) -> str | None:
    """`shutil.which(name)`, memoized on the PATH it searched.

    `own_log` folds every line a command prints, so an unmemoized lookup walks
    PATH once per line. The PATH is a key and not a comment: a memo that
    answered for an environment it never searched would fold — or fail to fold
    — by what some earlier environment happened to hold.
    """
    return shutil.which(name)


def interpreter_spellings() -> list[tuple[str, str]]:
    """Every path this machine names the RUNNING interpreter by, as `<PYTHON>`
    fold pairs.

    `core.fold` already folds each pair in its `realpath` form as well, so two
    spellings are covered by `sys.executable` alone. The third is the short
    name on PATH: `sys.executable` is the path the interpreter was started
    from, and a subject or a census row that spells `python3.14` runs the one
    PATH resolves — a different string, the same file, and unfolded it is this
    machine's Cellar in a pasted log.

    The same-file test is the whole guard. A basename that PATH resolves to a
    DIFFERENT interpreter — `/usr/bin/python3` where golden-census runs under
    Homebrew's — must not fold to `<PYTHON>`, because that token means the
    interpreter this command is running under and a log that used it for
    another one would be wrong rather than merely unfolded.

    Any other link to the same file — a symlink a reader made, a shim — is
    printed as typed, and one whose path begins with a folded spelling and
    goes on past a `.` (`…/python3.12` beside `…/python3`) as `<PYTHON>.12`.
    `docs/contract.md` discloses that, because a gap nobody wrote down is a
    gap a reader meets as a surprise.
    """
    spellings = [sys.executable]
    short = _on_path(os.path.basename(sys.executable),
                     os.environ.get("PATH", ""))
    if (short and short not in path_forms(sys.executable)
            and os.path.realpath(short) == os.path.realpath(sys.executable)):
        spellings.append(short)
    token = roots_vocabulary(None).token("PYTHON")
    return [(one, token) for one in spellings]


def own_log(text: str, census: Census, root: str,
            fixed: str | None = None) -> str:
    """A line GOLDEN-CENSUS ITSELF prints, folded through this census's own
    `path` rows.

    Every line a command prints about the machine goes through here, so a
    pasted log carries `<REPO>`/`<TMPROOT>` and never a home directory — and
    a command's header lines read the same under a temp root of 15
    characters and under one of 49. Left
    to each command, it is one header folded, one folded through a private
    vocabulary, one printing relative paths and three never asked — and half
    the priced rows tracking the width of this machine's temp root.

    The roots are DISPLAY roots and not the run's: the source for `<TMPROOT>`
    is the temp ROOT itself rather than the work directory under it, because
    what a header names — an `--out` directory, a `--against` directory a
    reader passed, a scratch box — sits under the root and not under the work
    directory. `root` is the subject root, which is the one directory a
    command's header names that the reader chose. The temp root is taken
    as `os.path.normpath` spells it, because that is how every path made
    under it is printed: a TMPDIR spelled with `/./`, `/../` or a doubled
    slash after its first name folds as its plain spelling does; a TMPDIR
    that opens with exactly two slashes keeps them, as `os.path.normpath`
    does.

    The interpreter is folded here too, and FIRST: `<PYTHON>` is a name of
    this vocabulary that expands to `sys.executable`, so every line naming it
    — a `state` row's command, a `command` precondition's, a `probe`
    candidate's argv — carries an absolute path no `path` row can fold,
    because the interpreter is a file and not a directory golden-census made.
    Two passes of `core.fold`, on purpose: the interpreter is not a census
    row, and it is folded before the rows.
    """
    text = fold(text, interpreter_spellings())
    try:
        work = os.path.normpath(temp_base()).rstrip("/")
    except OSError:
        # No temp root to name — `tempfile.gettempdir` found no directory it
        # could write in — so no directory under one to fold either: "" is
        # the work fold `path_pairs` leaves out, as it does a root of "/".
        work = ""
    return normalize_paths(text, census, Roots(
        root=root, work=work, clone=None, fixed=fixed))


def folded_for_reader(text: str, census: Census, root: str,
                      fixed: str | None = None) -> str:
    """`own_log`, then the reader's home directory folded to `<HOME>`.

    The home is the one fold beyond `own_log`'s rows, and it is made LAST:
    no census row names a reader's home, and nothing else golden-census
    prints carries an environment. A refusal and the `census state` block are
    pasted into hand-backs like any other evidence, and `$HOME` and `$PATH`
    would put the machine in every one of them. Nothing is folded when the
    home is empty or `/`, which would match every absolute path there is.
    """
    text = own_log(text, census, root, fixed)
    home = os.path.expanduser("~")
    return fold(text, [(home, "<HOME>")]) if home and home != "/" else text


def describing(pending: Pending, census: Census, root: str,
               fixed: str | None = None) -> AbstractContextManager[None]:
    """`core.attaching` with `about_to_run` over these four as the
    description: the window a launch of a child is opened in when its four
    values are known at entry, so a refusal inside it carries what the run
    was about to be."""
    return attaching(functools.partial(about_to_run, pending, census, root, fixed))


def about_to_run(pending: Pending, census: Census, root: str,
                 fixed: str | None = None) -> str:
    """What a run WAS about to be, for the refusal that stopped it: the
    expanded argv and the built environment, folded.

    The first line is worded HERE and nowhere else, from the three states
    `core.Pending` holds. `ran: ` where the child was started and ended: a
    command that ran is not about to run, and the refusal is over how it
    ended or what it printed. `about to run: ` where the argv is expanded
    and no child ended: a program that would not start, or a refusal
    between the expansion and the launch. `about to run, with its
    placeholders still unexpanded: ` where the argv is the manifest's
    spelling.

    Folded through `own_log`, because this is a line golden-census prints
    about the machine like any other — the interpreter reads `<PYTHON>`, and
    a directory reads the token of the census's `path` row that names it,
    the subject root `<REPO>` and the temp root `<TMPROOT>` in the bundled
    census; a census with no row for the root leaves it under the temp
    root's token — so a refusal pasted into a hand-back carries no home
    directory and reads the same on any machine.

    Both halves say so when they do not exist: a half left out is a half a
    reader takes for empty, and "the environment was empty" and "there was no
    environment yet" are different faults.

    Each value is folded FIRST and cut AFTER, to one line's width, so the cut
    is of what the reader sees and a directory wider than the cut folds whole.
    A `PATH` of three thousand characters would bury the variable the reader
    is looking for, and the cut is disclosed where it happens, with the
    length of the folded value, rather than left for them to wonder about.

    A variable the census's `passthrough` list names is the user's, a token
    say, and the block exists to say which variables the child got: it
    prints as `NAME=<passed through, N characters>`, N the length of the
    value as passed, before any fold or cut, and never the value. A pin and
    a surface's own `env` print whole, and so does a variable both pinned
    and listed, whose value is the pin's, because `build_env` lets a pin
    outrank a passthrough.

    The fold is `folded_for_reader`'s, which adds the reader's home directory
    to `own_log`'s rows.
    """
    if pending.ran:
        opening = "ran: "
    elif pending.expanded:
        opening = "about to run: "
    else:
        opening = "about to run, with its placeholders still unexpanded: "

    def shown(text: str) -> str:
        return folded_for_reader(text, census, root, fixed)

    lines = [shown(opening + " ".join(pending.argv))]
    if pending.env is None:
        lines.append(shown("the environment: " + pending.without_env))
    else:
        lines.append("the environment it was built with "
                     f"({len(pending.env)} variable(s)):")
        pinned = {row.variable for row in census.pins}
        lines += [f"  {name}=<passed through, {len(value)} characters>"
                  if name in census.passthrough and name not in pinned
                  else f"  {name}={_cut(shown(value))}"
                  for name, value in sorted(pending.env.items())]
    return "\n".join(lines)


def _cut(value: str) -> str:
    """One environment value, at one line's width, saying so when it is cut."""
    if len(value) <= DIFFERENCE:
        return value
    return value[:DIFFERENCE] + f"… ({len(value)} characters)"


def fold_regex(row: Row, text: str) -> str:
    """Replace ONLY the `volatile` group of every match with the placeholder.

    The token, never the line: everything outside the group — a count, a file
    name, a suffix that states a fact rather than a freshness — stays a byte
    comparison.
    """
    regex, placeholder = row.regex, row.placeholder or ""
    if regex is None:
        return text

    def replace(match: re.Match[str]) -> str:
        start, end = match.span("volatile")
        if start < 0:
            return match.group(0)
        base = match.start()
        whole = match.group(0)
        return whole[:start - base] + placeholder + whole[end - base:]

    return regex.sub(replace, text)


def _root_overlap(row: Row, text: str, forms: tuple[str, ...]
                  ) -> re.Match[str] | None:
    """The first match of `row`'s pattern in `text` whose `volatile` group
    would SPLIT an occurrence of the subject root — replace part of it and
    leave a fragment — or None.

    An occurrence is any spelling in `forms` found by a plain left-to-right
    walk, whatever follows it: every occurrence the root fold replaces and
    more, because `core.fold` goes through `re.sub` with `core.NAME_ENDS` and
    leaves `<root>-old` and `<root>2` alone. A group that splits one of those
    is refused here, as a rewrite of the subject root, before the contraband
    scan could refuse the unfolded sibling — both refuse, and this refusal
    runs first, at the row's fold, naming the row. The GROUP decides, as it
    does in `fold_regex`: a match the group takes no part in moves nothing.
    A group whose span CONTAINS a whole occurrence is no split either: it
    leaves nothing of the root behind for the root fold to miss, and records
    its placeholder the same on every machine. It is the one test of both
    refusals: `check_fold_overlap` asks it of the bare root, `normalize_text`
    of a row's text.
    """
    if row.regex is None:
        return None
    spans: list[tuple[int, int]] = []
    for form in forms:
        at = text.find(form)
        while at >= 0:
            spans.append((at, at + len(form)))
            at = text.find(form, at + len(form))
    if not spans:
        return None
    for match in row.regex.finditer(text):
        start, end = match.span("volatile")
        if start >= 0 and any(start < last and first < end
                              and not (start <= first and last <= end)
                              for first, last in spans):
            return match
    return None


class RootRewrite(Refusal):
    """`normalize_text`'s refusal of a fold that would split the subject
    root, carrying the fold's name and the text it would replace — so the
    one caller whose text is golden-census's own, the path fold control, can
    report it as its own red row rather than as a refusal naming a row no
    manifest has."""

    def __init__(self, message: str, next: str, fold: str,
                 replaced: str) -> None:
        super().__init__(message, next=next)
        self.fold = fold
        self.replaced = replaced


def normalize_text(text: str, census: Census, roots: Roots,
                   row_key: str = "*") -> str:
    """What a recorder writes for one text surface — the single entry point,
    so a control exercises the real decision and not a copy of it.

    It also REFUSES a `regex` fold whose `volatile` group would split the
    subject root in this text, naming the row, the fold, the pattern and the
    text; a census control reaches that refusal the same way a row does, and
    the path fold control, whose text is golden-census's own sample, catches
    it as a `RootRewrite` and reports its own red row. The occurrences are
    found again before each fold, on the text as that fold receives it,
    because an earlier fold may have moved them.
    """
    forms = path_forms(roots.root)
    for row in census.folds_of("regex"):
        if not row.in_scope(row_key):
            continue
        hit = _root_overlap(row, text, forms)
        if hit is not None:
            raise RootRewrite(
                f"census {census.path}: row {row.name!r} would rewrite the "
                "subject root's own path in the text of "
                f"{row_key}: its pattern {row.pattern!r} replaces "
                f"{hit.group('volatile')!r}. {_ROOT_FOLD_WHY}",
                next=f"{_ROOT_FOLD_NEXT}.", fold=row.name,
                replaced=hit.group("volatile"))
        text = fold_regex(row, text)
    return normalize_paths(text, census, roots)


def _walk_to(document: Any, dotted: str) -> Any:
    node = document
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _one_serialization(rows: tuple[Row, ...], path: str) -> tuple[int, bool]:
    """The `(indent, ensure_ascii)` every `json-fields` row of `rows` asks
    for, or the refusal naming the first two rows that ask for different
    ones: every such row applies to every written `.json` document, so the
    census can re-serialize one only one way.

    The one owner of that sentence, for `load_census`, which asks before
    anything runs, and for `_json_parts`, which asks of every document.
    """
    indent, ensure_ascii = rows[0].indent, rows[0].ensure_ascii
    for row in rows[1:]:
        if (row.indent, row.ensure_ascii) != (indent, ensure_ascii):
            raise Refusal(
                f"census {path}: rows {rows[0].name!r} and {row.name!r} "
                "ask for different `serialization`; one document cannot be "
                "re-serialized two ways.",
                next="Give both rows the same `serialization`: every `json-fields` row applies "
                "to every written `.json` document, and `scope` cannot narrow one.")
    return indent, ensure_ascii


def _json_parts(raw: str, census: Census) -> tuple[str, str]:
    """`(text, tail)` of a written `.json` file: `tail` is its trailing run of
    `"\\r"` and `"\\n"`, recorded exactly as the subject wrote it, and `text`
    is the document body — re-serialized with the census's `json-fields`
    rows applied when there are any, the body as written when there are none.

    The round trip is asserted, not assumed: re-serializing the UNTOUCHED
    document with exactly the census's `serialization` must reproduce the
    subject's BODY. If the subject ever changes how it writes JSON this
    refuses instead of quietly re-formatting the golden and hiding the change.
    The trailing line endings are set aside for that comparison because they
    are not the document: they are recorded as written, so a subject that
    gains, loses or changes its final newline moves its golden by that byte.

    The paths and the fields are census rows, and a path is resolved from the
    document root: nothing here knows what the subject writes.
    """
    text = raw.rstrip("\r\n")
    tail = raw[len(text):]
    rows = census.folds_of("json-fields")
    if not rows:
        return text, tail
    indent, ensure_ascii = _one_serialization(rows, census.path)
    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise Refusal(f"the subject's JSON does not parse: {exc}",
                      next="Run the subject's own command and look at what it wrote; a "
                      "json-fields fold needs a document that parses.") from exc
    rebuilt = json.dumps(document, indent=indent, ensure_ascii=ensure_ascii)
    if rebuilt != text:
        raise Refusal(
            "the subject's JSON writer no longer matches the census's round "
            f"trip (json.dumps(indent={indent}, ensure_ascii={ensure_ascii})); "
            "the golden would silently re-format it — fix the census, do not "
            "capture.",
            next="Read the subject's own json.dumps call and set the census's `serialization` to "
            "its `indent` and `ensure_ascii`; do not capture until they agree.")
    for row in rows:
        _fold_json_fields(document, row)
    return json.dumps(document, indent=indent, ensure_ascii=ensure_ascii), tail


def normalize_json(raw: str, census: Census, roots: Roots,
                   row_key: str = "*") -> str:
    """What a recorder writes for a written `.json` file, through the ONE door
    every recorded text goes through.

    In order: the `json-fields` folds and their round-trip assertion FIRST
    (`_json_parts`) — they need the document to parse — then `normalize_text`
    under the row's key: every `regex` fold whose scope takes the row, the
    capture-time root-overlap refusal, then the `path` folds. The trailing
    line endings are appended AS WRITTEN: none added, none removed.
    """
    text, tail = _json_parts(raw, census)
    return normalize_text(text, census, roots, row_key) + tail


def _fold_json_fields(document: Any, row: Row) -> None:
    """Blank every named field under every named path. A path that is absent
    is skipped; a field that is absent is skipped."""
    for dotted in row.paths:
        node = _walk_to(document, dotted)
        if not isinstance(node, dict):
            continue
        for field in row.fields:
            if field in node:
                node[field] = row.placeholder


# -------------------------------------------------------------- preconditions


def preconditions(census: Census, roots: Roots, out: Any) -> None:
    """Every `precondition` row, before the first run. A failure is a REFUSAL
    naming the check — not a FAIL: a FAIL is a statement about the subject, a
    REFUSAL is a statement about the run.

    Each command a row runs, the `git log -1 --oneline` that quotes the
    revision among them, is made AND tested inside a window of its own,
    so the block of a refusal is of the command that failed, under
    `core.NO_ENV_BUILT`, whichever command of golden-census's asked: a
    `capture`, whose own window is over the subject's command, or `census`,
    which opens none.
    """
    rows = census.of("precondition")
    if not rows:
        return
    out.write("  census preconditions\n")
    for row in rows:
        if row.check == "git-checkout":
            _git_checkout(row, census, roots, out)
        else:
            _command_check(row, census, roots, out)


#: What a precondition whose command's output is not UTF-8 is told to do,
#: a `command` row's command or a `git-checkout` row's git alike.
#: `core.launch`'s own `next:` asks the reader to wrap the command, and a
#: `git-checkout` row's git is golden-census's own, which no reader wraps.
UNDECODED_NEXT = ("Make that command print UTF-8, or change or drop the "
                  "census's precondition row that runs it.")


def _run(argv: list[str], cwd: str, pending: Pending | None = None,
         env: Mapping[str, str] | None = None
         ) -> subprocess.CompletedProcess[str]:
    """`launch` for a command a precondition row runs. Its refusal over
    output that is not UTF-8 — the one refusal `launch` raises other than
    `WouldNotStart`, which passes as it is — is told what to do of the
    row: `UNDECODED_NEXT`."""
    try:
        return launch(argv, f"the precondition command {argv[0]!r}",
                      cwd=cwd, env=env, pending=pending)
    except WouldNotStart:
        raise
    except Refusal as refused:
        raise Refusal(str(refused), next=UNDECODED_NEXT) from refused


def _stderr_text(stderr: str) -> str:
    """What a child printed on standard error, as text to quote: `stderr`
    with the white space at both ends dropped, or the empty string when no
    character of what is left shows, by `str.isprintable` — a zero-width
    space, an escape or a NUL alone prints as a colon with nothing after
    it. The ONE test of which form `_git_said`, `_child_failed` and
    `census._git_failed` write. The text it returns is written through
    `core.printable_text`, so a line holding an escape sequence is quoted
    with `!r` and never reaches a terminal raw."""
    said = stderr.strip()
    return (printable_text(said)
            if any(char.isprintable() for char in said) else "")


def _git_said(proc: subprocess.CompletedProcess[str]) -> str:
    """The clause that says what a git that did not exit 0 printed on
    standard error, in one of two forms.

    `git said '<first line>'` when `_stderr_text(proc.stderr)` is not empty:
    the first line of what is left, cut at `QUOTE` and written as `repr`
    writes it. It quotes git's OWN words rather than translating them: a git
    that does not exit 0 says why — a repository owned by another user, a
    broken index, a flag this version does not have — and golden-census
    cannot know which. The first line is the sentence; what follows is
    usually a hint addressed to the terminal.

    `git printed no text on stderr` when it is empty: git wrote nothing
    there, white space only, which `str.strip` drops, or characters none of
    which shows. The words are golden-census's and are never written inside
    the quotes that mark git's.
    """
    said = _stderr_text(proc.stderr).splitlines()
    if not said:
        return "git printed no text on stderr"
    return f"git said {said[0][:QUOTE]!r}"


def _git_failed(run: str, proc: subprocess.CompletedProcess[str]) -> str:
    """The reason for one git run that did not exit 0, in one of two forms:
    `clone_input`'s and `_porcelain`'s, and `mutants`' clone, commit and
    `rev-parse` steps.

    `<run> <how it ended>: <standard error>` when git printed text there:
    `_stderr_text` of its standard error, EVERY line of it, because
    the line that names the path or the fault is often not the first, cut at
    `QUOTE` and then right-stripped, with ` …` after it when something was
    cut, so that the sentence that follows never starts a line of its own.

    `<run> <how it ended>, git printed no text on stderr` when it printed
    none, so that no reason ends on a colon with nothing after it.

    ONE shape for every such run, and neither clause is worded here: how the
    git ended is `core.ended`'s, so a git that a signal ended is never said
    to have exited, and the words for a git that printed no text are
    `_git_said`'s, which returns them in exactly that case. Nothing
    of that git's standard output is in the reason.
    """
    how = f"{run} {ended(proc.returncode)}"
    said = _stderr_text(proc.stderr)
    if said:
        cut = said[:QUOTE].rstrip() + (" …" if len(said) > QUOTE else "")
        return f"{how}: {cut}"
    return f"{how}, {_git_said(proc)}"


def git_env(what: str = "git") -> dict[str, str]:
    """The environment of every git golden-census starts: its own, less git's
    location variables, with `GIT_TERMINAL_PROMPT` set to `0`. The ONE owner
    of that environment, beside `core.git_command`'s argv, so a git of the
    package never answers for a repository the process that started
    golden-census names.

    git exports `GIT_DIR` and `GIT_INDEX_FILE`, absolute, to every hook, `!`
    alias and `rebase -x` command, so a golden-census started from one
    would commit a mutant, make a throwaway repository or answer the
    `git-checkout` precondition in THAT repository. Every git runs without
    the variables `git rev-parse --local-env-vars` names, asked each time,
    except the ones whose name begins `GIT_CONFIG`: those carry
    configuration, not a location (`GIT_CONFIG_PARAMETERS`,
    `GIT_CONFIG_COUNT` and the `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` pairs
    git reads with it), and a proxy's authentication, a credential helper
    or a `safe.directory` handed to git that way reaches the git
    golden-census starts as it reaches the user's own. Where the question
    does not exit 0, the refusal says how it ended; `what` is the phrase
    its launch refusal opens with. Every git runs with `GIT_TERMINAL_PROMPT`
    set to `0`, which turns off git's own prompt on the terminal for a
    username or a password.
    """
    asked = "git rev-parse --local-env-vars"
    named = launch(["git", "rev-parse", "--local-env-vars"], what)
    if named.returncode != 0:
        raise Refusal(_git_failed(asked, named),
                      next="Put a `git` on PATH that answers that question.")
    local = {name for name in named.stdout.split()
             if not name.startswith("GIT_CONFIG")}
    return {**{name: value for name, value in os.environ.items()
               if name not in local},
            "GIT_TERMINAL_PROMPT": "0"}


def _child_failed(what: str, proc: subprocess.CompletedProcess[str],
                  census: Census, root: str, fixed: str | None) -> str:
    """The sentence of a refusal over a setup step, a counter or the command
    of a `command` precondition that did not exit 0, in one of two forms.

    `<what> <how it ended>: <standard error>` when the child printed text
    there: `_stderr_text` of its standard error, folded by
    `folded_for_reader` over `census`, `root` and `fixed` — the fold and
    the four values the caller's `describing` window folds the block under
    the sentence with — FIRST and cut at `QUOTE` AFTER, as `about_to_run`
    folds and cuts a value. A child's
    error names the interpreter that ran it and the paths it was handed as
    often as not, and the `ran:` line under the sentence prints those as
    `<PYTHON>` and their tokens.

    `<what> <how it ended>, it printed no text on stderr` when it printed
    none, so that no sentence ends on a colon with nothing after it.

    How the child ended is `core.ended`'s clause, so a child that a signal
    ended is never said to have exited. The shape is `census._git_failed`'s,
    and that function is not the owner of this sentence because its second
    form names git: `git printed no text on stderr` are `_git_said`'s words
    for a git, and a setup step, a counter or a precondition's command is
    the consumer's own program.
    """
    how = f"{what} {ended(proc.returncode)}"
    said = _stderr_text(proc.stderr)
    if said:
        return f"{how}: {folded_for_reader(said, census, root, fixed)[:QUOTE]}"
    return f"{how}, it printed no text on stderr"


def _git_checkout(row: Row, census: Census, roots: Roots, out: Any) -> None:
    """The `git-checkout` precondition over `roots.root`: three runs of git,
    and the return code of each is tested BEFORE its standard output is read.

    `git rev-parse --is-inside-work-tree` must exit 0 and print `true`. With
    `clean = true`, `git status --porcelain` must exit 0 and print nothing;
    it is asked with `core.GIT_UNTRACKED`, so a configuration that sets
    `status.showUntrackedFiles = no` hides no untracked file from it, and
    each of the three runs is `core.git_command`'s argv, so no global
    ignore file of the user running golden-census hides one either.
    Each of those failing is a REFUSAL. This function raises no refusal over
    a `git log -1 --oneline` that does not exit 0, because the precondition
    — a work tree, clean when asked — has passed by then: the `[OK]` line
    carries the revision when that git exits 0, and `core.ended` and
    `_git_said` when it does not. What either line quotes is folded by ONE
    call of `own_log`, because either can name a path: git names the object
    file of a linked worktree or of a separate git directory by its absolute
    path, and a commit's subject holds whatever its author typed. The
    revision is folded FIRST and cut at `REVISION_WIDTH` characters AFTER, so the cut is
    of what the reader sees and a line that names a path reads the same
    under a temp root of any width; git's first line is cut at `QUOTE` by
    `_git_said` before it is folded. Each refusal's sentence is folded the
    same way, so it names the subject root as the `about_to_run` block under
    it does.

    The three gits run under `git_env`'s environment, asked once before the
    first, and the refusal of that question is raised before any window
    opens, so it carries no block.

    How a git ended is `core.ended`'s clause, so no sentence here says
    "exited" of a git a signal ended. A byte that is not UTF-8, on standard
    error or on standard output, is `launch`'s refusal and not this
    function's, for any of the three runs, told what to do of the row by
    `_run`.

    Each of the three runs is made AND tested inside a window of its own,
    which stays open until the last test of that run: the block of a
    refusal is `about_to_run`'s, of the git it is about, under
    `core.NO_ENV_BUILT`. The one refusal that can follow `git log` is
    `launch`'s, over a byte that is not UTF-8.
    """
    def said(text: str) -> str:
        return own_log(text, census, roots.root, roots.fixed)

    env = git_env("the precondition command 'git'")
    argv = git_command("-C", roots.root, "rev-parse",
                       "--is-inside-work-tree")
    pending = Pending(argv, without_env=NO_ENV_BUILT)
    pending.ran_as(argv)
    with describing(pending, census, roots.root, roots.fixed):
        inside = _run(argv, roots.root, pending, env)
        # Two different facts, two different sentences. A return code that
        # is not 0 is git declining to answer — whatever its stdout holds
        # then says nothing about work trees — so the refusal hands back
        # `core.ended` and `_git_said`. The sentence below is for the case
        # where git DID answer, and answered no.
        if inside.returncode != 0:
            raise Refusal(
                said(f"precondition {row.name!r} (check git-checkout): `git "
                     f"rev-parse --is-inside-work-tree` "
                     f"{ended(inside.returncode)} in {roots.root}, so its "
                     f"standard output was not read — {_git_said(inside)}. "
                     f"{row.finding}"),
                next="Run `git rev-parse --is-inside-work-tree` in the [subject] root yourself "
                "and fix what git reports, or drop the git-checkout precondition row.")
        if inside.stdout.strip() != "true":
            raise Refusal(
                said(f"precondition {row.name!r} (check git-checkout): the "
                     f"subject root {roots.root} is not inside a git work "
                     f"tree — `git rev-parse --is-inside-work-tree` said "
                     f"{inside.stdout.strip()!r}. {row.finding}"),
                next="Point [subject] root at a git work tree, or drop the git-checkout "
                "precondition row that requires one.")
    if row.clean:
        argv = git_command("-C", roots.root, "status", "--porcelain",
                           GIT_UNTRACKED)
        pending = Pending(argv, without_env=NO_ENV_BUILT)
        pending.ran_as(argv)
        with describing(pending, census, roots.root, roots.fixed):
            status = _run(argv, roots.root, pending, env)
            if status.returncode != 0:
                raise Refusal(
                    said(f"precondition {row.name!r} (check git-checkout, "
                         f"clean = true): `git status --porcelain` "
                         f"{ended(status.returncode)} in {roots.root}, so its "
                         f"standard output was not read — "
                         f"{_git_said(status)}. {row.finding}"),
                    next="Run `git status --porcelain` in the [subject] root yourself and fix "
                    "what git reports, or set `clean = false` on that row if the tree need not "
                    "be clean.")
            if status.stdout.strip():
                raise Refusal(
                    said(f"precondition {row.name!r} (check git-checkout, "
                         f"clean = true): `git status --porcelain` in "
                         f"{roots.root} printed "
                         f"{status.stdout.strip()[:QUOTE_SHORT]!r}. "
                         f"{row.finding}"),
                    next="Commit or stash what `git status` listed above, or set `clean = "
                    "false` on that row if a dirty tree is acceptable.")
    argv = git_command("-C", roots.root, "log", "-1", "--oneline")
    pending = Pending(argv, without_env=NO_ENV_BUILT)
    pending.ran_as(argv)
    with describing(pending, census, roots.root, roots.fixed):
        head = _run(argv, roots.root, pending, env)
        if head.returncode != 0:
            quoted = said("no revision quoted — `git log -1 --oneline` "
                          f"{ended(head.returncode)}, {_git_said(head)}")
        else:
            quoted = said(head.stdout.strip())[:REVISION_WIDTH]
    out.write(f"    [OK] {row.name}: {quoted}\n")


def _command_check(row: Row, census: Census, roots: Roots, out: Any) -> None:
    """The `command` precondition: the row's command, run from `roots.root`
    under golden-census's own environment, must do what `expect` says:
    exit 0, for `exit 0`; exit 0 and print nothing but white space on
    standard output, for `empty stdout`. A command that did not exit 0 — an
    exit code that is not 0, or a signal that ended it — is refused under
    either, in `_child_failed`'s sentence, before what it printed is read.

    The run is made AND tested inside one window, which stays open until
    the last test: the block of a refusal is `about_to_run`'s, of the
    row's command, under `core.NO_ENV_BUILT`. The sentence of a command
    that did not exit 0 is `_child_failed`'s, as a setup step's and a
    counter's are. A command whose output is not UTF-8 is `launch`'s
    refusal, its program folded here as the block's is, and told what to
    do of a precondition row by `_run` (`UNDECODED_NEXT`).
    """
    pending = Pending(row.command, without_env=NO_ENV_BUILT)
    with describing(pending, census, roots.root, roots.fixed):
        table = _env_context(roots, census.directory or None)
        argv = [table.expand(a, f"census row {row.name!r}")
                for a in row.command]
        pending.ran_as(argv)
        try:
            proc = _run(argv, roots.root, pending)
        except WouldNotStart as refused:
            # The sentence names the program twice, in `launch`'s words and
            # in the operating system's, each the EXPANDED argv[0]: folded
            # here as `spelled` below is and the block under it is.
            raise WouldNotStart(own_log(str(refused), census, roots.root,
                                        roots.fixed),
                                next=refused.next) from refused
        except Refusal as refused:
            # `launch`'s own over output that is not UTF-8, the one other
            # refusal it raises: its sentence names the program by the
            # EXPANDED argv[0], folded here as the one above is; its
            # `next:` is `_run`'s, the census's row's, not the subject's.
            raise Refusal(own_log(str(refused), census, roots.root,
                                  roots.fixed),
                          next=refused.next) from refused
        spelled = own_log(" ".join(argv), census, roots.root, roots.fixed)
        if proc.returncode != 0:
            # Under either expectation: a command that did not exit 0 did not
            # answer the row's question, whatever it printed, so `empty
            # stdout` is tested only of a command that exited 0.
            # QUOTE, not QUOTE_SHORT: `core` states the rule — the wide quote
            # for an error's stderr, the short one for a line that is
            # evidence — and this is an error's stderr, which
            # `_child_failed` cuts. The `empty stdout` clause below quotes
            # what the command PRINTED, which is evidence, and stays at the
            # short width.
            raise Refusal(
                _child_failed(f"precondition {row.name!r} (check command, "
                              f"expect {row.expect}): {spelled}", proc,
                              census, roots.root, roots.fixed),
                next="Run that command by hand from the subject root and fix what it "
                "reports; the row's `finding` says why the capture depends on it.")
        if row.expect == "empty stdout" and proc.stdout.strip():
            raise Refusal(
                f"precondition {row.name!r} (check command, expect empty stdout): "
                f"{spelled} printed {proc.stdout.strip()[:QUOTE_SHORT]!r}",
                next="Run that command by hand from the subject root; the row expects it "
                "to print nothing.")
    out.write(own_log(f"    [OK] {row.name}: {' '.join(argv)} — "
                      f"{row.expect}\n", census, roots.root, roots.fixed))


# --------------------------------------------------------------- state rows


def state(census: Census, roots: Roots, env: dict[str, str], out: Any) -> None:
    """Print the `census state` block: each command's first line and each
    variable AS THE SUBJECT WILL SEE IT — after the environment rule, so an
    unlisted variable reads `<unset>` — with each value folded as
    `about_to_run` folds one, through `folded_for_reader`. Not a golden: a
    version string that moves between machines would make every golden a
    statement about the machine."""
    rows = census.of("state")
    if not rows:
        return
    out.write("  census state\n")
    for row in rows:
        for name in row.variables:
            value = folded_for_reader(env.get(name, "<unset>"), census,
                                      roots.root, roots.fixed)
            out.write(f"    {name} = {value!r}\n")
        table = _env_context(roots, census.directory or None)
        for command in row.commands:
            pending = Pending(command)
            pending.env = env
            # Both the expansion and the launch, and the refusal caught around
            # BOTH: a state row is a DIAGNOSTIC — the whole point of the block
            # is to print what this machine has, and a machine that lacks one
            # of the commands, or a token that names a directory this run never
            # made, is exactly what the reader is looking at. One refused
            # command costs its own line and the rest of the block still
            # prints. The line carries the exception a launch's refusal holds
            # (`core.child_fault`, in parentheses) and the sentence an
            # expansion's refusal is, so the shape is the same either way; an
            # expansion that refused has no expanded argv, so the row names the
            # command as the census spells it.
            argv = list(command)
            blocked: Refusal | None = None
            try:
                with describing(pending, census, roots.root, roots.fixed):
                    argv = [table.expand(a, f"census row {row.name!r}")
                            for a in command]
                proc = launch(argv, f"the state command {argv[0]!r}",
                              cwd=roots.root, env=env)
                line = (proc.stdout.strip() or proc.stderr.strip()
                        or f"(no output, {ended(proc.returncode)})")
            except Refusal as refused:
                blocked = refused
                line = f"({child_fault(refused)})"
            # Folded FIRST and cut AFTER, as `about_to_run` does for a value,
            # so a directory wider than the cut folds whole; the refusal's
            # advice goes after the cut: it is the part of the line the reader
            # acts on.
            shown = folded_for_reader(line, census, roots.root,
                                      roots.fixed).splitlines()[0][:DIFFERENCE]
            if blocked is not None:
                shown = with_next(shown, blocked)
            out.write(folded_for_reader(f"    {' '.join(argv)} -> {shown}\n",
                                        census, roots.root, roots.fixed))
