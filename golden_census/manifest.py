"""The manifest: one subject, its inputs, its surfaces, its permitted movements.

`docs/manifest-format.md` is authoritative for every key, the four surface
kinds, the placeholders and the list of errors golden-census refuses on.

Every row a capture needs is read from this file rather than out of the
subject: nothing in this package imports the subject.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, NamedTuple

from .census import (
    Census,
    check_controls,
    check_fold_overlap,
    check_scopes,
    load_census,
    surface_env,
)
from .core import (
    NOT_IN_A_COMPONENT,
    NO_ATTRIBUTION,
    SKIP_EXTENSION,
    STREAM_EXTENSIONS,
    SURFACES_FILE,
    TOKEN_RE,
    Layout,
    Placeholders,
    Refusal,
    Roots,
    folded_name,
    load_rows,
    load_toml,
    only_keys,
    resolved_below,
    roots_vocabulary,
    row_key,
    split_row_key,
    strings,
    table,
)

SURFACE_KINDS = ("run", "skip", "matrix", "tallies")

#: The document authoritative for this file's keys, written once: every
#: refusal that sends a reader to it reads it from here, so the name moves in
#: one edit. It is the FULL path, under the `docs` directory of whichever
#: layout this package is in, because a refusal is read from any directory
#: and a name a reader cannot open is not a `next:`.
_FORMAT_DOC = os.path.join(Layout.detect().data, "docs", "manifest-format.md")


def recorded_extension(writes: str | None) -> str | None:
    """The extension a written file is recorded under, or None for a surface
    that writes nothing.

    A `writes` carrying no extension of its own is recorded as `out`: a
    capture records every file under an extension and there is no fourth
    state. ONE owner, read by `Surface.extension` — what the recorder does —
    and by `_surface` — what the loader refuses — so the name the loader
    checks is the name the recorder writes.
    """
    if not writes:
        return None
    return os.path.splitext(writes)[1].lstrip(".") or "out"


class Subject(NamedTuple):
    name: str
    root: str                       # absolute; the cwd of every run
    command: tuple[str, ...]        # the argv prefix of every run
    version: tuple[str, ...]
    census: str                     # absolute path


class Input(NamedTuple):
    name: str
    args: tuple[str, ...]
    surfaces: tuple[str, ...]
    git: str | None = None
    sha: str | None = None
    expect_counts: dict[str, int] | None = None


class MatrixRow(NamedTuple):
    label: str
    args: tuple[str, ...]


#: The `verdict` of a surface that is not `tallies`: a pattern that matches
#: nothing, because only a tallies surface has a verdict line to find.
NO_VERDICT = re.compile(r"(?!)")


class Surface(NamedTuple):
    name: str
    kind: str = "run"
    args: tuple[str, ...] = ()
    writes: str | None = None
    counter: tuple[str, ...] = ()
    inputs: tuple[str, ...] | None = None      # None: no narrowing
    env: dict[str, str] | None = None
    needs: tuple[str, ...] = ()
    record_argv: tuple[str, ...] | None = None
    reason: str | None = None                  # kind = "skip"
    rows: tuple[MatrixRow, ...] = ()           # kind = "matrix"
    rule: str = "="                            # kind = "tallies"
    verdict: re.Pattern[str] = NO_VERDICT      # kind = "tallies"
    failing: re.Pattern[str] | None = None     # kind = "tallies"; optional

    def runs_for(self, input_name: str) -> bool:
        return self.inputs is None or input_name in self.inputs

    @property
    def extension(self) -> str | None:
        """The extension a written file is recorded under."""
        return recorded_extension(self.writes)


class Setup(NamedTuple):
    name: str
    command: tuple[str, ...]


class Movement(NamedTuple):
    path: str
    attribution: str


class Manifest(NamedTuple):
    path: str
    directory: str
    subject: Subject
    census: Census
    inputs: tuple[Input, ...]
    surfaces: dict[str, Surface]
    setups: tuple[Setup, ...]
    files: dict[str, tuple[str, ...]]
    movements: tuple[Movement, ...]
    #: The directory a path beside the manifest that EXECUTES resolves
    #: against: the `<HERE>` of `[subject] command`, of a `[[setup]]` argv and
    #: of a `counter` argv. It is `directory` for a run of the manifest where
    #: it sits, and `with_root` is the one thing that moves it. It is a field
    #: of its own rather than a second meaning for `directory`, which stays
    #: what it says — where this file is — so a refusal names the file the
    #: reader edits while an executed path names the tree the run is against.
    here: str

    def input_named(self, name: str) -> Input | None:
        return next((row for row in self.inputs if row.name == name), None)

    def setup_named(self, name: str) -> Setup | None:
        return next((row for row in self.setups if row.name == name), None)

    def surfaces_for(self, subject_input: Input) -> tuple[Surface, ...]:
        return tuple(self.surfaces[name] for name in subject_input.surfaces
                     if self.surfaces[name].runs_for(subject_input.name))

    def with_root(self, root: str) -> Manifest:
        """This manifest against a DIFFERENT copy of the subject.

        The subject root becomes `root`, and what a path beside the manifest
        means follows the copy when — and only when — the manifest sits INSIDE
        the original root, because then the copy carries the manifest's
        neighbors too. One thing moves: `<HERE>`, which only the three argvs
        that EXECUTE spell — `[subject] command`, a `[[setup]]` command and a
        `counter` — and the copy's version of what they execute is the whole
        point of running against a copy: an entry point taken from the tree
        golden-census was invoked in runs code the copy does not have, so a
        change planted in the copy is never reached and the silence reads as
        a clean result.

        Four things stay, because they are read and not run: the census, which
        pins the machine the run happens on and not the subject; an included
        row file, which is the argv the consumer froze; the `[files]`, which
        are lines and not a path; and everything in a manifest that sits
        OUTSIDE the original root, whose neighbors no copy of the subject
        carries.

        `mutants` is the one caller — a capture of a mutated clone is the same
        manifest read against another tree — and the override is a method
        rather than a `--root` flag on `capture` because a golden captured
        from an unnamed copy of the subject is not a golden anybody can
        re-derive.
        """
        moved = os.path.abspath(root)
        here = self.here
        inside = resolved_below(self.here, self.subject.root)
        if inside is not None:
            here = os.path.normpath(os.path.join(moved, inside))
        copy = self._replace(
            subject=self.subject._replace(root=moved), here=here)
        if here != self.here:
            for key, command in self.executed():
                for text in command:
                    _check_here(text, here, self.path, original=self.here,
                                key=key)
        return copy

    def with_command(self, command: tuple[str, ...]) -> Manifest:
        """This manifest with `compare --command`'s argv in place of
        `[subject] command`, checked as `[subject] command` is at load: every
        placeholder is one that key may spell, and a `<HERE>` path names
        something that is there. `<HERE>` is this manifest's directory, as it
        is in the key the argv replaces. The elements are otherwise taken as
        given. Nothing else of the manifest moves."""
        for text in command:
            command_context().check(text, _OVERRIDE_COMMAND)
            _check_here(text, self.here, self.path, key=_OVERRIDE_COMMAND)
        return self._replace(subject=self.subject._replace(command=command))

    def executed(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """`(the key, its argv)` for each argv this manifest EXECUTES — the
        three that may spell `<HERE>`, each named as a refusal names it."""
        return (((_SUBJECT_COMMAND, self.subject.command),)
                + tuple((f"[[setup]] {row.name} command", row.command)
                        for row in self.setups)
                + tuple((f"[surfaces.{name}] counter", surface.counter)
                        for name, surface in self.surfaces.items()
                        if surface.counter))

    def row_keys(self) -> tuple[str, ...]:
        """Every `<input>/<surface>` this manifest records, in capture order."""
        return tuple(row_key(i.name, s.name)
                     for i in self.inputs for s in self.surfaces_for(i))


# ------------------------------------------------------------------ loading


def _relative(directory: str, value: str) -> str:
    """A manifest path, resolved against the manifest's own directory."""
    return os.path.abspath(os.path.join(directory, value))


#: How a refusal names the subject's own argv prefix — `_check_here`'s
#: default key, and the one whose relative element resolves under `root`.
_SUBJECT_COMMAND = "[subject] command"

#: How a refusal names `compare --command`'s argv, `_check_here`'s other key
#: that a reader types on a command line and not in a file.
_OVERRIDE_COMMAND = "compare --command"


def _check_here(text: str, directory: str, path: str,
                original: str | None = None,
                key: str = _SUBJECT_COMMAND) -> None:
    """An element spelling `<HERE>` names something that is there.

    `<HERE>` is the one placeholder of this key whose value exists before a run
    does — the directory the element's file sits in — so the path it builds is
    checkable before the run, and a runner that was moved or renamed costs one
    sentence rather than the interpreter's own error ten minutes into a
    capture. The rule is narrow on purpose: only an element that OPENS with the
    token and carries no other one, because an element mixing `<HERE>` with a
    token of the run is a path only the capture can value, and a flag that
    merely contains the token is not a path at all.

    `key` is the argv the element is part of, as the refusal names it:
    `[subject] command`, a `[[setup]]` command or a `counter`, the three that
    may spell the token. A relative element of the first resolves against the
    subject root, and one of the other two against `<WORK>`, where they run,
    so the `next:` line names the place that key's relative element goes.

    `original` is the directory the manifest itself sits in, given when
    `directory` is a COPY's — `Manifest.with_root`'s caller. It buys the
    refusal its second path: a neighbor the copy does not carry is a fact
    about the copy, and a reader told only that a file is missing would look
    for it where the manifest is, where it exists. Falling back to the
    original is the one thing this must not do: that is the run reading the
    tree it was invoked in, which is what running against a copy is for.

    The token is asked of the vocabulary that defines the name rather than
    typed here: a rule comparing against a token nobody defines is a rule that
    stops firing without saying so.
    """
    here = command_context().token("HERE")
    if not text.startswith(here) or len(TOKEN_RE.findall(text)) != 1:
        return
    resolved = os.path.abspath(text.replace(here, directory, 1))
    if os.path.exists(resolved):
        return
    if original is not None:
        raise Refusal(
            f"{path}: {key} names {resolved}, which the copy of "
            "the subject under test does not have (the manifest's own copy "
            f"of it is {os.path.abspath(text.replace(here, original, 1))}).",
            next="Commit that file to the subject's repository — a copy is made from the last "
            "commit, so an untracked or ignored file is not in it.")
    if key == _SUBJECT_COMMAND:
        relative = ("spell it relative to [subject] root instead, where it "
                    "resolves against the subject")
    elif key == _OVERRIDE_COMMAND:
        relative = "give the file's absolute path"
    else:
        relative = (f"drop the {here}/ for a path under <WORK>, where the "
                    "command runs")
    raise Refusal(
        f"{path}: {key} names {resolved}, which does not "
        f"exist. {here} is the directory this manifest sits in, so the "
        "path is known before anything runs.",
        next=f"Point that element at a file beside this manifest, or {relative}.")


#: The manifest's own top-level tables, beside `load_manifest`, which reads
#: each of them. `surface-sets` is here because the table exists; its KEYS are
#: set names the author chooses, so it earns no `only_keys` call of its own.
_MANIFEST_KEYS = ("subject", "surfaces", "inputs", "setup", "files",
                  "movements", "surface-sets")


def load_manifest(path: str) -> Manifest:
    """Read a manifest and every file it includes, and check both it and its
    census, before the first run.

    Every refusal here names the offending key: a wrong manifest costs one
    sentence and not ten minutes of capturing.
    """
    path = os.path.abspath(path)
    # `load_toml` refuses an unfilled hole on the text it read, before the
    # parse: a scaffolded manifest is valid TOML with its holes still in it,
    # so the parser would say nothing — and where a hole DOES break the
    # syntax, "fill SUBJECT_NAME" is the sentence the reader needs, not a
    # complaint about the line it happens to sit on.
    document, directory = load_toml(path, "manifest")
    only_keys(document, _MANIFEST_KEYS, f"{path}: the manifest", _FORMAT_DOC)

    subject = _subject(document, directory, path)
    census = load_census(subject.census)

    surfaces = _surfaces(document, directory, path)
    inputs = _inputs(document, path)
    setups = _setups(document, directory, path)
    files = _files(document, path)
    movements = _movements(document, path)

    surface_sets = table(document, "surface-sets", path)
    _refuse_set_named_as_surface(surface_sets, surfaces, path)
    inputs = tuple(_resolve_surfaces(row, surface_sets, surfaces, path)
                   for row in inputs)

    manifest = Manifest(path, directory, subject, census, inputs, surfaces,
                        setups, files, movements, here=directory)
    _check_cross_references(manifest)
    check_scopes(census, frozenset(manifest.row_keys()))
    check_controls(census, frozenset(
        key for key in manifest.row_keys()
        if manifest.surfaces[split_row_key(key)[1]].kind == "run"))
    check_fold_overlap(census, subject.root)
    return manifest


#: Every key `_subject` reads, beside it.
_SUBJECT_KEYS = ("name", "root", "command", "version", "census")


def _subject(document: dict[str, Any], directory: str, path: str) -> Subject:
    raw = document.get("subject")
    if not isinstance(raw, dict):
        raise Refusal(f"{path}: no [subject] table",
                      next="Add a [subject] table with `name`, `root`, `command` and `census`; "
                      f"{_FORMAT_DOC} has the shape.")
    only_keys(raw, _SUBJECT_KEYS, f"{path}: [subject]", _FORMAT_DOC)
    name = str(raw.get("name", "")).strip()
    if not name:
        raise Refusal(f"{path}: [subject] needs a `name`",
                      next="Add `name = \"...\"`, the subject's own word, printed in every "
                      "comparison.")
    root = raw.get("root")
    if not isinstance(root, str):
        raise Refusal(f"{path}: [subject] needs a `root`",
                      next="Add `root = \"...\"`, the subject's checkout directory, relative to "
                      "this manifest.")
    root_path = _relative(directory, root)
    if not os.path.isdir(root_path):
        raise Refusal(f"{path}: [subject] root {root_path} is not a directory",
                      next="Point [subject] root at the directory the subject's code sits in; it "
                      "is resolved relative to this manifest.")
    command = strings(raw.get("command", []), f"{path}: [subject] command")
    if not command:
        raise Refusal(f"{path}: [subject] needs a `command` (the argv prefix "
                      "of every run)",
                      next="Add `command = [...]`, the argv prefix of every run, with <PYTHON> "
                      "where the interpreter belongs.")
    version = strings(raw.get("version", []), f"{path}: [subject] version")
    # Two vocabularies, because `command` is the one key whose strings may name
    # the manifest's OWN directory: an entry point that sits beside the
    # manifest rather than under `root` has no other way to be spelled, and an
    # absolute path in a committed manifest is this machine baked into the
    # consumer's file. `version` keeps the narrow one — it is arguments to that
    # command, not a path — and each loop names the key it read, so a refusal
    # sends the reader to the line it came from.
    for text in command:
        command_context().check(text, f"{path}: [subject] command")
        _check_here(text, directory, path)
    for text in version:
        context().check(text, f"{path}: [subject] version")
    census = raw.get("census")
    if not isinstance(census, str) or not census:
        raise Refusal(f"{path}: [subject] needs a `census` — the manifest says "
                      "what to run, the census says what the environment "
                      "around every run is pinned to.",
                      next="Add `census = \"census.toml\"` naming the census file beside this "
                      "manifest.")
    return Subject(name, root_path, command, version,
                   _relative(directory, census))


def _one_component(name: str, what: str, place: str) -> None:
    """A surface or input name is ONE path component, or a refusal naming it.

    A capture writes `<out>/<input>/<surface>.<ext>`, so both names become a
    directory or a file name under the capture directory: one carrying a
    separator, or naming this directory or its parent, is joined by
    `os.path.join` and lands somewhere else — and an absolute one discards the
    capture directory altogether. Refused at LOAD, because every one of these
    names is known before the first row runs and a refusal after two rows are
    on disk is a refusal too late.

    The ways a name is not a component are asked of `os` — `curdir`, `pardir`,
    `sep` and `altsep` — and not of a list this project keeps: a rule spelled
    out by hand is a rule that is wrong on the platform nobody tried it on.
    `NOT_IN_A_COMPONENT` is the one `os` has no name for.
    """
    if not (not name or name in (os.curdir, os.pardir) or os.sep in name
            or NOT_IN_A_COMPONENT in name
            or (os.altsep and os.altsep in name)):
        return
    raise Refusal(
        f"{place} — {what} is one path component, and this one is not. A "
        "capture writes <out>/<input>/<surface>.out, so a name carrying a "
        "separator, or naming this directory or its parent, writes outside "
        "the capture directory.",
        next="Rename it to one path component — letters, digits, dashes and dots are all "
        "fine.")


def _components(name: str) -> list[str]:
    """A relative path as golden-census reads it: its components, split on
    `os.sep` with `os.altsep` read as `os.sep`. ONE owner, asked by
    `_stays_under` — does every component name something? — and by
    `_refuse_file_above_file` — is one key a directory above another?"""
    spelled = name.replace(os.altsep, os.sep) if os.altsep else name
    return spelled.split(os.sep)


def _stays_under(name: str, what: str, where_token: str, place: str, *,
                 prefix: str = "") -> None:
    """A value golden-census resolves against a directory stays under it, or a
    refusal naming it.

    The rule is about the COMPONENTS: the value is relative, and every
    component of it NAMES something a file system can hold — which is where
    `NOT_IN_A_COMPONENT` comes in, a character no name holds. One that is
    empty, `.` or `..` navigates instead of naming, so the value resolves to a
    directory or to a place above the one it was joined onto, and the file
    golden-census goes on to open is not a file. The noun and the directory
    are arguments because two keys of two different files obey the one rule: a
    `files` key, written under the work directory, and a mutant's `file`,
    opened for writing inside the clone of the subject. One condition, one
    sentence, two callers.

    Components and never a substring, so a fixture called `..hidden.txt` is a
    fixture and not an escape.

    `prefix` is what the caller already read off the front of the value — the
    `<WORK>/` a `writes` begins with — so the refusal quotes the value as the
    manifest spells it and its `next:` spells a value that loads.
    """
    if not os.path.isabs(name) and all(
            part and part not in (os.curdir, os.pardir)
            and NOT_IN_A_COMPONENT not in part
            for part in _components(name)):
        return
    after = f"{prefix} followed by " if prefix else ""
    slashes = (f"no \"/\" after {prefix} and none at the end" if prefix
               else "no leading or trailing \"/\"")
    raise Refusal(
        f"{place} — {what} must be {after}a relative path under "
        f"{where_token} that names a file; {prefix + name!r} is not one.",
        next=f"Spell it as a path under {where_token} — \"{prefix}fixtures/a.txt\" or "
        f"\"{prefix}a.txt\" — with {slashes}, and no \".\" or \"..\" component.")


def _code_points(key: str) -> str:
    """` (U+0063 U+0061 …)`: every code point of `key`. What a refusal naming
    two keys that are `_alike` puts after each, so the reader sees which is
    which."""
    return " (" + " ".join(f"U+{ord(char):04X}" for char in key) + ")"


def _alike(one: str, other: str) -> bool:
    """`one` and `other` are one string once canonically decomposed: they
    differ only in how a character is encoded, and print alike."""
    return (unicodedata.normalize("NFD", one)
            == unicodedata.normalize("NFD", other))


def _refuse_alike_names(kind: str, first: str, name: str, path: str,
                        why: str) -> None:
    """Refuse two `[<kind>.<name>]` keys that are `folded_name`-equal, naming
    both; each is followed by its code points when the two print alike.

    ONE sentence for the surfaces and the inputs: the names, the fold and the
    `next:` line are the same, and `why` is what the second name would
    overwrite.
    """
    spelled = ((_code_points(first), _code_points(name))
               if _alike(first, name) else ("", ""))
    raise Refusal(
        f"{path}: [{kind}.{first}]{spelled[0]} and "
        f"[{kind}.{name}]{spelled[1]} are the same name once case and "
        f"Unicode normalization are folded. {why}",
        next=f"Rename {first!r}{spelled[0]} or {name!r}{spelled[1]} so "
        "the two are different names once case and Unicode "
        "normalization are folded.")


def _surfaces(document: dict[str, Any], directory: str,
              path: str) -> dict[str, Surface]:
    raw_surfaces = table(document, "surfaces", path)
    surfaces: dict[str, Surface] = {}
    #: The name each folded spelling was FIRST written as, so a collision names
    #: both keys rather than one and a fold of it.
    folded: dict[str, str] = {}
    for name in raw_surfaces:
        # The name is quoted here and nowhere else in this function: a name
        # that is not one component is one TOML makes the author quote, so the
        # bracket the refusal prints is the line they wrote.
        _one_component(name, "a surface name", f'{path}: [surfaces."{name}"]')
        if folded_name(name) in folded:
            _refuse_alike_names(
                "surfaces", folded[folded_name(name)], name, path,
                "A capture writes every surface of an input into one "
                "directory as <surface>.out/.err/.exit, and a golden set has "
                "to survive a checkout on a filesystem that folds case or "
                "Unicode normalization whoever recorded it: there the second "
                "set of files is written over the first, so one of the two "
                "surfaces has no golden and nothing says which.")
        folded[folded_name(name)] = name
        raw = table(raw_surfaces, name, path, label=f"surfaces.{name}")
        surfaces[name] = _surface(name, raw, directory, path)
    if not surfaces:
        raise Refusal(f"{path}: no [surfaces.<name>] tables — a manifest with "
                      "no surfaces records nothing.",
                      next="Add one [surfaces.<name>] table per surface: an argv, and what it "
                      "records.")
    return surfaces


def _refuse_recorded_collision(name: str, writes: str, place: str) -> None:
    """Refuse a `writes` whose recorded file is one a capture already writes.

    A capture writes `<surface>.out`, `<surface>.err` and `<surface>.exit` for
    every surface, `<surface>.<SKIP_EXTENSION>` for one it skipped, and one
    `surfaces.json` per input, then records the written file under the
    extension `writes` carries. Recorded under one of those names it lands on
    top of what was written moments earlier, or claims a meaning that is not
    its own: the stream or the index is gone, the surface it belonged to has
    no golden, and nothing in the capture says so. Refused at LOAD, where it
    costs one sentence instead of a whole capture.

    Compared case-folded, the way `_surfaces` compares surface names and the
    file system compares names on the platforms golden-census runs on: on a
    case-insensitive one `<surface>.OUT` IS `<surface>.out`.
    """
    extension = recorded_extension(writes)
    folded = folded_name(extension or "")
    reserved = ", ".join(f".{one}" for one in
                         (*STREAM_EXTENSIONS, SKIP_EXTENSION))
    # One sentence for every name in the namespace, written once: the reader's
    # move is the same whichever of them they landed on.
    give_it_one = (f"Give `writes` an extension of its own — {reserved} are the capture's "
                   "— or drop the key if the surface writes no file.")
    if folded in STREAM_EXTENSIONS:
        raise Refusal(
            f"{place}: `writes = \"{writes}\"` is recorded as "
            f"{name}.{extension}, which, whatever its case, is the file this "
            f"surface's {folded} stream is written to, so the written file "
            "would replace that stream's golden.",
            next=give_it_one)
    if folded == SKIP_EXTENSION:
        # Two harms, and the message names the one a reader can see in a
        # report. `compare` reads a both-sides skip by this suffix, so a
        # surface that really ran is reported as one that ran on neither
        # side. The file it wrote is then also read as the sentence saying
        # why nothing ran.
        raise Refusal(
            f"{place}: `writes = \"{writes}\"` is recorded as "
            f"{name}.{extension}, which, whatever its case, is the file a "
            "skipped surface records its reason in, so a surface that ran "
            "would be reported as one that ran on neither side.",
            next=give_it_one)
    if folded_name(f"{name}.{extension}") == SURFACES_FILE:
        raise Refusal(
            f"{place}: `writes = \"{writes}\"` is recorded as "
            f"{name}.{extension}, which, whatever its case, is {SURFACES_FILE}: "
            "the index a capture writes for every input — the file that says "
            "a directory holds a capture at all. Recorded over it, this "
            "surface's file replaces the record of every surface of its input.",
            next=f"Rename the surface, or give `writes` an extension that does not make "
            f"{SURFACES_FILE}.")


#: Every key `_surface` and `_matrix_rows` read, beside them. The UNION of the
#: four kinds' keys, not one set per kind: the granularity is the table, so a
#: `run` surface carrying `verdict` still loads and the per-kind refusals that
#: exist keep saying what each kind needs, each in its own words.
_SURFACE_KEYS = ("kind", "skip", "record_argv", "args", "writes", "counter",
                 "inputs", "env", "needs", "include", "rule", "verdict",
                 "failing")

#: Every key a row of a matrix surface's include file carries.
_INCLUDE_ROW_KEYS = ("label", "args")

#: The keys ONE kind reads, each with that kind, why the key would do nothing
#: on any other, and when the reader's surface really is that kind. `_surface`
#: refuses each on every other kind in one sentence shape, because a key a
#: reader can write and golden-census will not read is the worst shape there
#: is.
_ONE_KIND_KEYS: dict[str, tuple[str, str, str]] = {
    "record_argv": (
        "matrix",
        "Every other kind records the argv it really ran, so the key would "
        "sit in the manifest doing nothing — and `shares_invocation_with`, "
        "which a reader takes as evidence that two rows priced one "
        "invocation, would still be derived from the real argvs and not "
        "from this.",
        "if its rows really are many small runs recorded as one file."),
    "failing": (
        "tallies",
        "No other kind reduces a run to groups, so the key would sit in the "
        "manifest doing nothing — and a reader would take the failing rows' "
        "evidence to be recorded when no line of it is.",
        "if the run prints fenced groups, each with its verdict line."),
}


def _tallies_pattern(raw: dict[str, Any], key: str,
                     place: str) -> re.Pattern[str] | None:
    """A tallies surface's `verdict` or `failing`, compiled when the manifest
    is read — or None when the key is absent, or the refusal naming the table
    and the key. A value that is not a string is refused rather than spelled
    into a pattern: `['x']` would compile as a character class."""
    if key not in raw:
        return None
    pattern = raw[key]
    if not isinstance(pattern, str):
        raise Refusal(f"{place}: `{key}` must be a string",
                      next=f"Write `{key} = '...'`: one regular expression, as "
                      "a string.")
    try:
        return re.compile(pattern)
    except (re.error, OverflowError) as exc:
        # OverflowError is what `re` raises for a repeat count past its limit
        # (`a{4294967296}`), and it is the same fault as a `re.error`.
        raise Refusal(f"{place}: `{key}` does not compile: {exc}",
                      next=f"Fix the `{key}` regular expression in that table; "
                      "it is compiled when the manifest is read, before "
                      "anything runs.") from exc


def _surface(name: str, raw: dict[str, Any], directory: str,
             path: str) -> Surface:
    place = f"{path}: [surfaces.{name}]"
    only_keys(raw, _SURFACE_KEYS, place, _FORMAT_DOC)
    # BEFORE the `skip` early return and before every other key, because the
    # question it answers is about the surface's KIND and not about anything
    # a later branch reads: a `skip` surface that quietly swallowed the key
    # would be the same defect wearing a different word.
    kind = "skip" if "skip" in raw else str(raw.get("kind", "run"))
    for key, (owner, why, when) in _ONE_KIND_KEYS.items():
        if key in raw and kind != owner:
            raise Refusal(
                f"{place}: `{key}` is read only for a `{owner}` surface, and "
                f"this one is `{kind}`. {why}",
                next=f"Drop `{key}` from this surface, or set "
                f"`kind = \"{owner}\"` {when}")
    # `capture._record_surface` runs a counter for a `run` surface alone, and
    # only on the file it wrote: on any other kind a counter never runs.
    # Asked before the `skip` return, for the reason the loop above is.
    if raw.get("counter") and kind in SURFACE_KINDS and kind != "run":
        raise Refusal(
            f"{place}: `counter` is handed the file a `run` surface writes, "
            f"and this surface is a `{kind}`, which runs no counter, so its "
            "counter would never run.",
            next="Move the `counter` to a `run` surface with `writes`, or "
            "remove it.")
    if "skip" in raw:
        reason = raw["skip"]
        if not isinstance(reason, str) or not reason.strip():
            raise Refusal(f"{place}: `skip` must be the reason recorded as the "
                          "golden",
                          next="Write `skip = \"the reason\"`: the sentence recorded as that "
                          "surface's golden.")
        return Surface(name, kind="skip", reason=reason)
    if kind not in SURFACE_KINDS:
        raise Refusal(f"{place}: kind {kind!r} is not one of "
                      + ", ".join(SURFACE_KINDS),
                      next="Set `kind` to one of the kinds listed above.")

    args = strings(raw.get("args", []), f"{place}: args")
    for text in args:
        context().check(text, f"{place}: args")
    writes = raw.get("writes")
    if writes is not None:
        if not isinstance(writes, str):
            raise Refusal(f"{place}: `writes` must be a string",
                          next="Write `writes = \"<WORK>/name.json\"` as a string.")
        writes_context().check(writes, f"{place}: writes")
        work = writes_context().token("WORK")
        if not writes.startswith(f"{work}/"):
            raise Refusal(
                f"{place}: `writes` must begin with <WORK>/, and {writes!r} "
                "does not — golden-census "
                "captures only what it can fold, and a file written anywhere "
                "else carries a path no golden may hold.",
                next="Rewrite `writes` to start with <WORK>/, and hand the subject the same path "
                "with <WRITES>.")
        # The rest stays under <WORK>: golden-census removes the file at this
        # path before each run (`run._clear_written`), and a `..` or an
        # empty component would aim that removal outside its own directory.
        _stays_under(writes[len(work) + 1:], "`writes`", work, place,
                     prefix=f"{work}/")
        _refuse_recorded_collision(name, writes, place)
    counter = strings(raw.get("counter", []), f"{place}: counter")
    # The run's vocabulary, `run.resolve_command`'s, so a token the counter's
    # run would refuse is refused here, before the subject runs.
    for text in counter:
        command_context().check(text, f"{place}: counter")
        _check_here(text, directory, path, key=f"[surfaces.{name}] counter")
    # The same reason for a `run` surface that writes nothing: its counter
    # would never run, and an `expect_counts` beside it never be checked.
    if counter and writes is None:
        raise Refusal(
            f"{place}: `counter` is handed the file the surface writes, and "
            "this surface has no `writes`, so its counter would never run.",
            next="Give the surface a `writes` file under <WORK>/ and hand the "
            "subject that path with <WRITES>, or remove the `counter`.")
    inputs = strings(raw["inputs"], f"{place}: inputs") if "inputs" in raw else None
    env = raw.get("env")
    if env is not None:
        if not isinstance(env, dict) or not all(isinstance(v, str)
                                                for v in env.values()):
            raise Refusal(f"{place}: `env` must be a table of strings",
                          next="Write `env = { NAME = \"value\" }` with string values only.")
        for text in env.values():
            context().check(text, f"{place}: env")
    needs = strings(raw.get("needs", []), f"{place}: needs")
    record_argv = (strings(raw["record_argv"], f"{place}: record_argv")
                   if "record_argv" in raw else None)

    rows: tuple[MatrixRow, ...] = ()
    if kind == "matrix":
        # `capture.record_matrix` runs `command + input.args + row.args`: of
        # the surface's own `args` it reads nothing.
        if "args" in raw:
            raise Refusal(
                f"{place}: `args` is not read for a `matrix` surface. Each "
                "row runs the command with the input's `args` and the row's "
                "own `args`, so the key would sit in the manifest doing "
                "nothing.",
                next="Move the arguments to the `args` of the rows in the "
                "include file, or to the input's `args`, and drop the key "
                "from this surface.")
        rows = _matrix_rows(raw, directory, place)
    rule, verdict = "=", NO_VERDICT
    failing: re.Pattern[str] | None = None
    if kind == "tallies":
        rule = str(raw.get("rule", "="))
        if len(rule) != 1:
            raise Refusal(f"{place}: `rule` is the single character a banner is "
                          "fenced with",
                          next="Write `rule = \"=\"`: the one character the subject fences its "
                          "banners with.")
        compiled = _tallies_pattern(raw, "verdict", place)
        if compiled is None or not compiled.pattern:
            raise Refusal(f"{place}: a tallies surface needs a `verdict` "
                          "regular expression",
                          next="Add `verdict = \"...\"`, the regular expression matching the line "
                          "that states the surface's verdict.")
        verdict = compiled
        # Present means present: compiled and used as written, like `verdict`.
        failing = _tallies_pattern(raw, "failing", place)
    return Surface(name, kind=kind, args=args, writes=writes, counter=counter,
                   inputs=inputs, env=env, needs=needs,
                   record_argv=record_argv, rows=rows, rule=rule,
                   verdict=verdict, failing=failing)


def _matrix_rows(raw: dict[str, Any], directory: str,
                 place: str) -> tuple[MatrixRow, ...]:
    include = raw.get("include")
    if not isinstance(include, str):
        raise Refusal(f"{place}: a matrix surface needs an `include` naming "
                      "the generated row file",
                      next="Add `include = \"rows.toml\"` naming the generated row file committed "
                      "beside this manifest.")
    include_path = _relative(directory, include)
    if not os.path.isfile(include_path):
        raise Refusal(f"{place}: include {include_path} does not exist. The "
                      "row file is generated by a script the consumer owns and "
                      "committed beside the manifest; a capture never imports "
                      "the subject to learn its rows.",
                      next="Generate that row file with the consumer's own script and commit it "
                      "beside the manifest.")
    # The fifth loader, through the same seam the other four use: ONE read,
    # the hole check on the text it read, and every row's `args` checked
    # against the manifest's OWN vocabulary before anything runs. An include
    # row spelling `<TMP>` must refuse HERE and not mid-capture from inside
    # the thread pool, and one spelling `<<HOLE:ARG>>` must be refused as an
    # unfilled hole rather than as an unknown placeholder — a sentence about
    # the wrong rule sends the reader to the wrong file.
    raw_rows = load_rows(include_path, f"{place}: include {include_path}")
    if not raw_rows:
        raise Refusal(f"{place}: include {include_path} holds no rows",
                      next="Regenerate that row file; a matrix surface with no rows records "
                      "nothing.")
    rows = []
    for row in raw_rows:
        if not isinstance(row, dict) or "label" not in row:
            raise Refusal(f"{place}: include {include_path} has a row that is "
                          "not {label, args}",
                          next="Give every row of the include file a `label` and an `args` list.")
        only_keys(row, _INCLUDE_ROW_KEYS,
                  f"{place}: include {include_path}, row {row['label']!r}",
                  _FORMAT_DOC)
        args = strings(row.get("args", []), f"{place}: include row args")
        for text in args:
            context().check(text, f"{place}: include row args")
        rows.append(MatrixRow(str(row["label"]), args))
    return tuple(rows)


#: Every key `_inputs` reads, beside it.
_INPUT_KEYS = ("args", "git", "sha", "expect_counts", "surfaces")

#: What a `sha` is made of: a commit's id, or a prefix of one, as
#: `git rev-parse HEAD` prints it, in lowercase.
_HEXADECIMAL = re.compile(r"[0-9a-f]+")

#: A `scheme://` address whose userinfo holds a `:`, a password.
_PASSWORD_ADDRESS = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/@]*:[^/@]*@")


def _inputs(document: dict[str, Any], path: str) -> tuple[Input, ...]:
    raw_inputs = document.get("inputs", {})
    if not isinstance(raw_inputs, dict) or not raw_inputs:
        raise Refusal(f"{path}: no [inputs.<name>] tables",
                      next="Add one [inputs.<name>] table per input the surfaces are run over.")
    rows = []
    #: The name each folded spelling was FIRST written as, as `_surfaces` keeps.
    folded: dict[str, str] = {}
    for name, raw in raw_inputs.items():
        _one_component(name, "an input name", f'{path}: [inputs."{name}"]')
        if folded_name(name) in folded:
            _refuse_alike_names(
                "inputs", folded[folded_name(name)], name, path,
                "A capture writes every input into one directory, "
                "<out>/<input>/, and a golden set has to survive a checkout "
                "on a filesystem that folds case or Unicode normalization "
                "whoever recorded it: there the second input's record "
                "replaces the first's, and a change to the first input "
                "compares IDENTICAL.")
        folded[folded_name(name)] = name
        place = f"{path}: [inputs.{name}]"
        if not isinstance(raw, dict):
            raise Refusal(f"{place}: must be a table",
                          next="Write that input as an [inputs.<name>] table.")
        only_keys(raw, _INPUT_KEYS, place, _FORMAT_DOC)
        args = strings(raw.get("args", []), f"{place}: args")
        for text in args:
            context().check(text, f"{place}: args")
        # The VALUES, not their presence: `git = ""` with a `sha` passed a
        # test written as `(git is None) != (sha is None)`, then became None
        # three lines below — where `str(git) if git else None` reads the
        # value — and the input was captured against the local tree instead of
        # the pinned clone, silently and with the manifest still claiming a
        # pin. One reading of what is set, used by the check and by the row.
        git = str(raw.get("git") or "")
        sha = str(raw.get("sha") or "")
        if bool(git) != bool(sha):
            raise Refusal(f"{place}: `git` and `sha` must both be present "
                          "and non-empty, or both absent. A clone with no "
                          "commit is not a pinned input.",
                          next="Give the input both `git` and `sha`, or neither; an empty string "
                          "is neither.")
        # `run.repository_folder` keeps `.` and `..` whole, and a clone kept
        # in a folder of either name lands beside or above the layout.
        # `run` imports this module, so the two values are spelled here.
        # `git` and `sha` are both set or both empty by now.
        if git in (".", ".."):
            raise Refusal(f"{place}: `git` is {git!r}, and `.` and `..` "
                          "cannot name the folder a clone is kept in.",
                          next="Give `git` as the repository's address, a URL "
                          "or a path.")
        if git.startswith("-"):
            raise Refusal(f"{place}: `git` is {git!r}, which opens with `-` "
                          "and git would read as an option.",
                          next="Give `git` as the repository's address, a URL "
                          "or a path; spell a path that begins with `-` as "
                          "`./-…`.")
        if _PASSWORD_ADDRESS.match(git):
            raise Refusal(f"{place}: `git` carries a password in its address.",
                          next="Keep the credential in a git credential "
                          "helper and pin the address without it: the "
                          "manifest is committed, and the capture log, which "
                          "a hand-back quotes, prints the address.")
        if sha and _HEXADECIMAL.fullmatch(sha) is None:
            raise Refusal(f"{place}: `sha` is {sha!r}, which is not made of "
                          "lowercase hexadecimal digits — a pin is a commit's id, and "
                          "its clone is kept in a folder of that name",
                          next="Give `sha` as the commit's lowercase hexadecimal id, or "
                          "a prefix of it.")
        counts = raw.get("expect_counts")
        if counts is not None and not isinstance(counts, dict):
            raise Refusal(f"{place}: `expect_counts` must be a table",
                          next="Write `expect_counts = { key = N }` as a table.")
        if counts is not None and not counts:
            raise Refusal(f"{place} sets `expect_counts` to an empty table, "
                          "which checks nothing.",
                          next="Give `expect_counts` the counts the counter "
                          "must print, or remove it.")
        surfaces = raw.get("surfaces", [])
        named = ((surfaces,) if isinstance(surfaces, str)
                 else strings(surfaces, f"{place}: surfaces"))
        rows.append(Input(name, args, named, git or None, sha or None,
                          dict(counts) if counts else None))
    return tuple(rows)


def _refuse_set_named_as_surface(surface_sets: dict[str, Any],
                                 surfaces: dict[str, Surface],
                                 path: str) -> None:
    """A `[surface-sets]` entry that has the name of a `[surfaces.<name>]`
    table is a refusal naming both.

    `_resolve_surfaces` decides an entry of an input's `surfaces` list by
    asking the sets first, so with one name for both the surface is never run
    or recorded, and nothing says so. Asked of the names themselves, whether
    or not an input lists the name: the author who writes one name for both
    has already made the list ambiguous.
    """
    for name in surface_sets:
        if name in surfaces:
            raise Refusal(
                f"{path}: [surface-sets] {name} and [surfaces.{name}] are one "
                "name. An entry of an input's `surfaces` list is read as the "
                "set when it names one, so the surface of that name would "
                "never be run or recorded, and nothing would say so.",
                next="Rename the set or the surface, so that no [surface-sets] "
                "entry has the name of a [surfaces.<name>] table.")


def _resolve_surfaces(row: Input, surface_sets: dict[str, Any],
                      surfaces: dict[str, Surface], path: str) -> Input:
    """An input's `surfaces` list, with every surface-set name expanded IN
    PLACE.

    An entry is a surface or a set, decided entry by entry, so `["tree",
    "acceptance"]` is the set plus one and an input that wants a set with a
    sixth surface stops respelling the other five. The whole list is one
    entry long in the common case and this reads it the same way, which is
    why there is no separate "a bare set name" branch to keep in step.

    Deduplicated by first occurrence, because a list naming a set and one of
    its members means those surfaces and not one of them twice: the result is
    what `row_keys` calls this input's rows, and a key that appears twice is a
    surface recorded over itself.

    An input's `expect_counts` is checked only against the numbers a
    surface's `counter` prints, so an input that sets it and names no surface
    with a counter is refused here, over the expanded list: a set may hold
    the surface that counts. So is an input naming two such surfaces:
    `surfaces.json` holds one `_counts` per input.
    """
    expanded: list[str] = []
    for entry in row.surfaces:
        if entry in surface_sets:
            expanded += strings(surface_sets[entry],
                                f"{path}: [surface-sets] {entry}")
        else:
            expanded.append(entry)
    names = tuple(dict.fromkeys(expanded))
    if not names:
        raise Refusal(f"{path}: [inputs.{row.name}] names no surfaces",
                      next="Add `surfaces = [...]` naming the [surfaces.<name>] tables this input "
                      "is recorded over.")
    for name in names:
        if name not in surfaces:
            raise Refusal(
                f"{path}: [inputs.{row.name}] names {name!r}, which is "
                "neither a [surfaces.<name>] table nor a [surface-sets] "
                "entry. An entry of that list is one or the other.",
                next="Add the [surfaces.<name>] table, or add the [surface-sets] entry of that "
                "name, or drop the name from the input's `surfaces` list.")
    counted = [name for name in names if surfaces[name].counter]
    if len(counted) > 1:
        raise Refusal(
            f"{path}: [inputs.{row.name}] names {len(counted)} surfaces with "
            f"a `counter`, {', '.join(f'`{name}`' for name in counted[:-1])} "
            f"and `{counted[-1]}`, and `surfaces.json` records one "
            "`_counts` per input, so the last one's numbers would replace "
            "the others' in the golden and a change in theirs would compare "
            "IDENTICAL.",
            next="Keep one counted surface per input: remove the `counter` "
            "from all but one of those surfaces, or record them under inputs "
            "of their own.")
    if row.expect_counts is not None and not any(
            surfaces[name].counter for name in names):
        raise Refusal(
            f"{path}: [inputs.{row.name}] sets `expect_counts`, and none of "
            "the surfaces it names has a `counter`, so the counts would never "
            "be checked.",
            next="Give one of those surfaces a `counter`, or remove "
            "`expect_counts` from the input.")
    return row._replace(surfaces=names)


#: Every key `_setups` reads, beside it.
_SETUP_KEYS = ("name", "command")


def _setups(document: dict[str, Any], directory: str,
            path: str) -> tuple[Setup, ...]:
    """The manifest's `[[setup]]` tables, in the order the file gives them.

    Two tables with one `name` are refused, naming both by their number in
    the file and both commands, as two `[[movements]]` rows with one `path`
    are: `Manifest.setup_named` takes the first table of a name, so a
    `needs` would only ever run the first, and the second would never run.
    """
    raw_setups = document.get("setup", [])
    if not isinstance(raw_setups, list):
        raise Refusal(f"{path}: [[setup]] must be a list of tables",
                      next="Write each setup as a [[setup]] table with `name` and `command`.")
    setups = []
    #: The table number and command each `name` was FIRST given, so a
    #: second table with the same name names both tables.
    named: dict[str, tuple[int, tuple[str, ...]]] = {}
    for number, raw in enumerate(raw_setups, start=1):
        if not isinstance(raw, dict) or "name" not in raw:
            raise Refusal(f"{path}: every [[setup]] needs a `name`",
                          next="Give every [[setup]] a `name`; it is the word `needs` refers to it "
                          "by.")
        only_keys(raw, _SETUP_KEYS, f"{path}: [[setup]] {raw['name']}",
                  _FORMAT_DOC)
        command = strings(raw.get("command", []),
                           f"{path}: [[setup]] {raw['name']} command")
        if not command:
            raise Refusal(f"{path}: [[setup]] {raw['name']} needs a `command`",
                          next="Add `command = [...]` to that setup.")
        for text in command:
            command_context().check(
                text, f"{path}: [[setup]] {raw['name']} command")
            _check_here(text, directory, path,
                        key=f"[[setup]] {raw['name']} command")
        name = str(raw["name"])
        if name in named:
            first, spelled = named[name]
            raise Refusal(
                f"{path}: [[setup]] tables {first} and {number} are both "
                f"named {name!r}, with the commands "
                f"{json.dumps(list(spelled), ensure_ascii=False)} and "
                f"{json.dumps(list(command), ensure_ascii=False)}. A name is "
                "one step: a `needs` naming it would only ever run the "
                "first, and the second would never run.",
                next="Keep one of the two tables, or give the second a name "
                "of its own and name it in the `needs` of the surfaces that "
                "want it.")
        named[name] = (number, command)
        setups.append(Setup(name, command))
    return tuple(setups)


#: Every key `_files` reads, beside it.
_FILES_KEYS = ("lines",)


def files_key(name: str) -> str:
    """A `files` key as every refusal spells it: JSON's string, whose escapes
    a TOML basic string reads the same, so a key holding a newline or a NUL
    stays on the line of the refusal that names it. The one spelling of a
    key, for the loader and for `run.write_files`."""
    return json.dumps(name, ensure_ascii=False)


def files_table(name: str) -> str:
    """The table header of a `files` key, `[files."<key>"]`, as a refusal
    names it."""
    return f"[files.{files_key(name)}]"


def _files(document: dict[str, Any], path: str) -> dict[str, tuple[str, ...]]:
    files = {}
    for name, raw in table(document, "files", path).items():
        _stays_under(name, "a `files` key", context().token("WORK"),
                     f"{path}: {files_table(name)}")
        if not isinstance(raw, dict) or "lines" not in raw:
            raise Refusal(f"{path}: {files_table(name)} needs `lines`",
                          next="Add `lines = [...]`, the lines golden-census writes into that file "
                          "before the runs.")
        only_keys(raw, _FILES_KEYS, f"{path}: {files_table(name)}",
                  _FORMAT_DOC)
        files[name] = strings(raw["lines"],
                              f"{path}: {files_table(name)} lines")
    _refuse_file_above_file(tuple(files), path)
    return files


def _refuse_file_above_file(names: tuple[str, ...], path: str) -> None:
    """Refuse `files` keys of which one is a directory above another, naming
    every such pair.

    `run.write_files` writes every key as a FILE under the work directory and
    makes the directories above it first, so `a` beside `a/b.txt` asks for
    `a` to be a file and a directory at once, and whichever of the two is
    written second fails in `os`, far from the manifest. Refused at LOAD,
    because every key is known before anything runs, and with EVERY pair
    named, so that one edit of the manifest can clear them all.

    Whole components are compared, never characters, so `ab` and `a.txt` sit
    beside `a/b.txt` untouched. They are compared case-folded and
    canonically decomposed (`core.folded_name`). A pair whose spellings
    match only once case and Unicode normalization are folded is named "on a
    filesystem that folds case or Unicode normalization", because that is
    where such a pair collides, and it is refused on every machine because a
    manifest is checked out on both kinds; where the two differ only in how
    a character is encoded, and so print alike, each key is followed by its
    code points (`_code_points`). The pairs are named in the
    manifest's order of the directory key, then of the key below it, the
    pairs that match as spelled before the others. Two keys that are ONE
    name once folded are not a pair here: neither is a directory above the
    other. Called after every key has passed `_stays_under`, so every
    component names something.
    """
    parts = {name: _components(name) for name in names}
    folded = {name: [folded_name(part) for part in parts[name]]
              for name in names}
    as_spelled: list[str] = []
    case_folded: list[str] = []
    for upper in names:
        depth = len(parts[upper])
        for lower in names:
            if (len(parts[lower]) <= depth
                    or folded[lower][:depth] != folded[upper]):
                continue
            if parts[lower][:depth] == parts[upper]:
                as_spelled.append(f"{files_table(upper)} is a directory "
                                  f"above {files_table(lower)}")
                continue
            marks = ((_code_points(upper), _code_points(lower))
                     if _alike("/".join(parts[upper]),
                               "/".join(parts[lower][:depth]))
                     else ("", ""))
            case_folded.append(
                f"{files_table(upper)}{marks[0]} is a directory above "
                f"{files_table(lower)}{marks[1]} on a filesystem that folds "
                "case or Unicode normalization")
    if as_spelled or case_folded:
        raise Refusal(
            f"{path}: {'; '.join(as_spelled + case_folded)}. A manifest's "
            "`files` keys name files `capture` writes under <WORK>, so a key "
            "that is a directory above another would have to be a file and a "
            "directory at once; the manifest is refused for every command, "
            "because no capture could run it.",
            next="Rename one key of each pair named above, so that no `files` key is a "
            "directory above another.")


#: Every key `_movements` reads, beside it.
_MOVEMENT_KEYS = ("path", "attribution")


def _movements(document: dict[str, Any], path: str) -> tuple[Movement, ...]:
    """The manifest's `[[movements]]` rows, in the order the file gives them.

    Two rows whose `path` is the same string are refused, naming both rows
    by their number in the file and both attributions: only the first
    row's attribution would ever be printed for that path. Two rows whose
    `path` strings differ are not compared here, where no path has moved
    yet: `compare.split_diffs` refuses a moved path both of them match."""
    raw_movements = document.get("movements", [])
    if not isinstance(raw_movements, list):
        raise Refusal(f"{path}: [[movements]] must be a list of tables",
                      next="Write each movement as a [[movements]] table with `path` and its "
                      "attribution.")
    movements: list[Movement] = []
    #: The row number and attribution each `path` string was FIRST given, so
    #: a second row with the same string names both rows.
    named: dict[str, tuple[int, str]] = {}
    for number, raw in enumerate(raw_movements, start=1):
        if not isinstance(raw, dict) or "path" not in raw:
            raise Refusal(f"{path}: every [[movements]] needs a `path`",
                          next="Give every [[movements]] row a `path`: the exact surface path it "
                          "permits.")
        only_keys(raw, _MOVEMENT_KEYS,
                  f"{path}: [[movements]] {raw['path']!r}", _FORMAT_DOC)
        # An ABSENT key reads `(no attribution)` below; a present one that
        # says nothing is a row permitted for no stated reason.
        if "attribution" in raw and not str(raw["attribution"]).strip():
            raise Refusal(
                f"{path}: [[movements]] {raw['path']!r} has an empty or "
                "blank `attribution`, which would permit that row while saying "
                "nothing about why it moved.",
                next="Write the change that moved it, or drop the key to record "
                "`(no attribution)`.")
        movement = Movement(str(raw["path"]),
                            str(raw.get("attribution", NO_ATTRIBUTION)))
        if movement.path in named:
            first, attributed = named[movement.path]
            raise Refusal(
                f"{path}: [[movements]] rows {first} and {number} both name "
                f"{movement.path!r}, attributed {attributed!r} and "
                f"{movement.attribution!r}. A path is one row: only the "
                "first row's attribution would ever be printed, and the "
                "second would permit nothing the first does not.",
                next="Keep one of the two rows, with an attribution that "
                "gives every reason the path moved.")
        named[movement.path] = (number, movement.attribution)
        movements.append(movement)
    return tuple(movements)


def _check_cross_references(manifest: Manifest) -> None:
    """The errors the manifest format lists by name, each refused with its key."""
    path = manifest.path
    pinned = manifest.census.pinned_variables
    for subject_input in manifest.inputs:
        for name in subject_input.surfaces:
            surface = manifest.surfaces[name]
            if not surface.runs_for(subject_input.name):
                raise Refusal(
                    f"{path}: [inputs.{subject_input.name}] names the surface "
                    f"{name!r}, whose own `inputs` narrows it away from that "
                    "input. A surface cannot be both asked for and excluded.",
                    next="Drop the surface from that input's `surfaces` list, or widen the "
                    "surface's own `inputs` to include the input.")
    for name, surface in manifest.surfaces.items():
        place = f"{path}: [surfaces.{name}]"
        for need in surface.needs:
            if manifest.setup_named(need) is None:
                raise Refusal(f"{place}: `needs` names {need!r}, which no "
                              "[[setup]] defines.",
                              next="Add the [[setup]] table with that name, or drop the `needs` "
                              "entry.")
        for variable in (surface.env or {}):
            if variable in pinned:
                raise Refusal(
                    f"{place}: `env` sets {variable!r}, which the census pins. "
                    "A surface that quietly unpins a variable records a golden "
                    "about the override, not about the subject.",
                    next="Change the census pin, or drop the surface's `env` override; one of the "
                    "two owns the variable.")
        # The child marker, refused here in `surface_env`'s own words, so a
        # surface that sets it costs nothing that ran: a refusal at its row
        # would come after the rows before it, and would leave a `vary`
        # control on it a SKIP.
        surface_env(manifest.census, {}, surface.env or {}, place)
        for target in surface.inputs or ():
            if manifest.input_named(target) is None:
                raise Refusal(f"{place}: `inputs` narrows to {target!r}, which "
                              "no [inputs.<name>] table defines.",
                              next="Spell the narrowing with one of the [inputs.<name>] table "
                              "names, or drop it.")


# ------------------------------------------------------------ the expansion


def context(roots: Roots | None = None,
            writes: str | None = None) -> Placeholders:
    """The manifest's ONE placeholder vocabulary: the names a manifest string
    may spell, and their values in a run.

    `load_manifest` builds it with no roots — the NAMES are all a load-time
    check needs, and the values are filled in by the capture that has them. One
    value rather than a `MANIFEST_TOKENS` tuple beside a run-time table, so the
    two cannot come to hold different names.

    `<input>` and `<surface>` are absent by design outside `writes` (see
    `writes_context`), and `<HERE>` is absent outside the argvs that execute
    (see `command_context`): the format defines each where it defines it and
    nowhere else, so a row that spells one in `args` earns the same refusal as an
    invented token.

    `WRITES` is valued from a `writes` the caller has already expanded, and it
    is valued the same way in a surface's `env` as in its `args`: `env = {
    GOLDEN_CENSUS_OUT = "<WRITES>" }` and `args = ["<WRITES>"]` name one path. The
    caller that has it is `run.row_start`, which computes it before
    the `env` block for exactly that reason; a surface with no `writes` at all
    leaves the value None, and the token is refused there. The four names
    every run has are `core.roots_vocabulary`'s, with `<WRITES>` in the slot
    this vocabulary lists it in.
    """
    return roots_vocabulary(roots, writes=writes)


def command_context(roots: Roots | None = None, here: str | None = None, *,
                    writes: str | None = None) -> Placeholders:
    """The manifest's vocabulary plus `<HERE>`, built FROM it: the three argvs
    that EXECUTE — `[subject] command`, a `[[setup]]` command and a `counter`
    (`Manifest.executed`) — are the keys whose strings may name the
    manifest's own directory.

    `<HERE>` means what it means in a census and in a mutants file — the
    directory of the file that spells it — and here that is the manifest's.
    It is scoped to those three rather than added to `context()` because
    each of them runs somewhere other than the manifest's directory —
    `command` from `<ROOT>`, a setup step and a counter in `<WORK>` — so a
    relative element in one resolves there, and a program committed beside
    the manifest has no other spelling than an absolute path. `args` are
    arguments to the subject, never a program golden-census runs.

    `load_manifest` builds it with no directory, for the same reason
    `context` builds with no roots: the NAMES are all a load-time check
    needs, and the value is filled in by the capture that has it. `writes`
    is the counter's, which expands `<WRITES>` too.
    """
    return context(roots, writes).also({"HERE": here})


def writes_context(roots: Roots | None = None, input_name: str | None = None,
                   surface_name: str | None = None) -> Placeholders:
    """The manifest's vocabulary plus the two names `writes` adds, built FROM
    it."""
    return context(roots).also({"input": input_name, "surface": surface_name})


def expand_writes(surface: Surface, roots: Roots,
                  input_name: str) -> str | None:
    if not surface.writes:
        return None
    return writes_context(roots, input_name, surface.name).expand(
        surface.writes, where=f"[surfaces.{surface.name}] writes")
