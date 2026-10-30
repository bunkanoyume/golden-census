"""The arms over a census and a manifest as FILES: what the loaders refuse,
what a placeholder resolves to, what `<HERE>` means, what an absent program
does to a state row and a precondition, and the census's own controls run
against a consumer's census.
"""

from __future__ import annotations

import contextlib
import errno
import functools
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
from collections.abc import Callable

from .capture import (
    capture,
    read_capture,
)
from .census import (
    FIXED_DIR_RE,
    FIXED_DIR_WIDTH,
    Census,
    Row,
    _env_context,
    build_env,
    git_env,
    load_census,
    own_log,
    preconditions,
    state,
)
from .core import (
    ACTUAL,
    DIFFERENCE,
    DISCLOSED,
    IMPORT_NAME,
    Layout,
    QUOTE,
    Refusal,
    fixed_dir_room,
    git_command,
    launch,
    path_forms,
    refusal_text,
    Report,
    Roots,
    temp_base,
    UNREPORTABLE,
    unpunctuated,
)
from .cli import run_census
from .controls import (
    CheckRow,
    SkipRow,
    _path_fold_control,
    _regex_fold_control,
    census_controls,
)
from .docs import (
    Invocation,
    measure,
)
from .manifest import SURFACE_KINDS, Manifest, load_manifest
from .mutants import Mutant, load_mutants, preflight
from .probe import banner
from .run import (
    clone_input,
    place,
    run_row,
    write_files,
)
from .proof import (
    _NO_VERDICT,
    _STUB_CENSUS,
    _STUB_ENVIRONMENT,
    _STUB_MANIFEST,
    _STUB_WORK_CENSUS,
    _STUB_ROOT_FOLD,
    _STUB_SUBJECT,
    _STUB_WORK_FOLD,
    _box,
    _cache_in,
    _chmod_bites,
    _repo_of,
    _startup_noise,
    _startup_noise_reason,
    _root_fold,
    _env_as,
    _fixed_fold,
    _fixed_pin,
    _heard,
    _made_under,
    _mode_as,
    _one_line,
    _opens,
    _package_argv,
    _planted_script,
    _scratch,
    _subject,
    _tmpdir_as,
)
from .checks_base import (
    PACKAGE,
    _census_rows,
    _control_roots,
    _fresh_module,
    _printed_refusal,
    _refused_by,
    _rows_of,
)
from .checks_capture import (
    _EXITS,
    _PLANTED_CLONE_STEP,
    _PLANTED_SAID,
    _SIGNALS_ITSELF,
    _clone_that_fails,
)
from .checks_mutants import (
    _mutant_box,
    _mutants_run,
)

def _environment_control(check: CheckRow, manifest: Manifest | None) -> None:
    """(o) `build_env` builds a subject's environment FROM NOTHING.

    Every pin row's variable is set to its value; a variable golden-census's own
    environment holds and the census does not name does NOT reach the subject;
    a passthrough variable does. The last two carry the weight: an environment
    built by pinning names on TOP of a copy of `os.environ` keeps nothing out.
    """
    rows = (Row("a pinned width", "pin", "a control's own row",
                variable="GOLDEN_CENSUS_CONTROL_PIN", value="80",
                control={"shape": "vary"}),)
    census = Census("<control>", "", None, ("GOLDEN_CENSUS_CONTROL_PASS",), rows)
    with _env_as({"GOLDEN_CENSUS_CONTROL_PASS": "carried by name",
                  "GOLDEN_CENSUS_CONTROL_CANARY": "must not reach the subject"}):
        env = build_env(census, _control_roots())
    pinned = env.get("GOLDEN_CENSUS_CONTROL_PIN") == "80"
    passed = env.get("GOLDEN_CENSUS_CONTROL_PASS") == "carried by name"
    kept_out = "GOLDEN_CENSUS_CONTROL_CANARY" not in env
    real = "no --manifest was given, so no real census pin was checked"
    real_ok = True
    if manifest is not None:
        real_env = build_env(manifest.census, _control_roots())
        # `FIXED_DIR_RE`, not `startswith("<FIXED-WIDTH-DIR")`: the two
        # disagreed on `<FIXED-WIDTH-DIR:abc>`, which is not a width and is
        # now refused by `load_census` as the invented placeholder it is.
        wanted = [row.variable for row in manifest.census.pins
                  if row.variable and not FIXED_DIR_RE.match(row.value or "")]
        missing = [name for name in wanted if name not in real_env]
        real_ok = not missing
        real = (f"{len(wanted)} census pin(s) reach the built environment, "
                f"missing {missing}")
    check("o  the environment every subject subprocess runs under is built "
          "FROM NOTHING: every census pin is set, a passthrough variable is "
          "carried by name, and a variable golden-census's own environment holds "
          "that no row names does NOT reach the subject",
          pinned and passed and kept_out and real_ok,
          f"{ACTUAL}pin set={pinned}, passthrough carried={passed}, canary "
          f"kept out={kept_out}, {real}")


#: The manifest errors the format lists by name, each as one scratch manifest
#: and the key its refusal must name.
_LOADER_CASES: tuple[tuple[str, str, str, str], ...] = (
    ("surfaces", "a surface no [surfaces.<name>] defines",
     _STUB_MANIFEST.replace('surfaces = ["help"]', 'surfaces = ["nope"]'),
     _STUB_CENSUS),
    ("needs", "a `needs` naming no [[setup]]",
     _STUB_MANIFEST + '\nneeds = ["nothing"]\n', _STUB_CENSUS),
    ("env", "an `env` key the census has pinned",
     _STUB_MANIFEST + '\nenv = { COLUMNS = "10" }\n', _STUB_CENSUS),
    ("args", "a placeholder golden-census does not define",
     _STUB_MANIFEST.replace('args = ["--help"]', 'args = ["--help", "<TMP>"]'),
     _STUB_CENSUS),
    ("include", "an include file that does not exist",
     _STUB_MANIFEST.replace('args = ["--help"]', 'kind = "matrix"')
     + '\ninclude = "absent.json"\n', _STUB_CENSUS),
    ("writes", "a `writes` without a <WORK> prefix",
     _STUB_MANIFEST + '\nwrites = "/tmp/x.json"\n', _STUB_CENSUS),
    ("census", "a census file that is missing",
     _STUB_MANIFEST.replace('census  = "census.toml"',
                            'census  = "absent.toml"'), _STUB_CENSUS),
    ("inputs", "a surface that narrows itself away from an input that names it",
     _STUB_MANIFEST + '\ninputs = ["somebody-else"]\n', _STUB_CENSUS),
    ("setup", "two [[setup]] tables with one `name`",
     _STUB_MANIFEST + "".join(
         f'\n[[setup]]\nname    = "step"\ncommand = ["<PYTHON>", "{one}"]\n'
         for one in ("first.py", "second.py")), _STUB_CENSUS),
)


def _loader_control(check: CheckRow) -> None:
    """(v) the manifest loader refuses each error the format lists by name,
    and the refusal says which key to fix."""
    verdicts: list[str] = []
    for key, _what, manifest_text, census_text in _LOADER_CASES:
        with _box("golden-census-loader-") as box:
            path = _scratch(box, manifest_text, census_text)
            try:
                load_manifest(path)
                verdicts.append(f"{key}=LOADED (no refusal)")
            except Refusal as refused:
                # The scratch box is named `golden-census-loader-…`, so the
                # key is looked for with the box's path taken out: a
                # refusal that quotes the path must still SAY `census`.
                text = str(refused)
                for spelling in (box, os.path.realpath(box)):
                    text = text.replace(spelling, "<box>")
                verdicts.append(f"{key}={'names it' if key in text else text[:60]}")
            except Exception as exc:            # noqa: BLE001 — reported, not raised
                if isinstance(exc, UNREPORTABLE):
                    raise
                verdicts.append(f"{key}=RAISED {type(exc).__name__}: {exc}")
    ok = all(v.endswith("names it") for v in verdicts)
    check("v  the manifest loader refuses every error the format lists — "
          + ", ".join(what for _key, what, _m, _c in _LOADER_CASES)
          + " — and every refusal names the offending key",
          ok, f"{ACTUAL}{verdicts}")


def _unopenable_control(check: CheckRow, skip: SkipRow) -> None:
    """(vvvv) a consumer file that would not open says so."""
    label = ("vvvv  a consumer file this run cannot OPEN is refused as one, "
             "with a `next:` about reaching the file — never as `does not "
             "parse`, which sends a reader to look for a syntax error in bytes "
             "golden-census never saw; a file that opens and does not parse "
             "keeps the parser's sentence and its `next:`")
    verdicts: dict[str, str] = {}
    with _box("golden-census-unopenable-") as box:
        path = _scratch(box)
        if not _chmod_bites(path, _opens):
            skip(label, "`chmod 000` left the manifest readable — this run "
                        "is likely root — so the branch this arm is about "
                        "cannot be reached here. Nothing is claimed.")
            return
        with _mode_as(path, 0o000, 0o600):
            verdicts["unreadable"] = _refusal_gist(path, box)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\nthis line is not TOML =\n")
        verdicts["unparsable"] = _refusal_gist(path, box)
    unreadable = verdicts["unreadable"]
    unparsable = verdicts["unparsable"]
    check(label,
          "cannot be read: PermissionError" in unreadable
          and "may read it" in unreadable
          and "does not parse: TOMLDecodeError" in unparsable
          and "Fix the TOML error" in unparsable,
          f"{ACTUAL}chmod 000 -> {unreadable}; a TOML syntax error -> "
          f"{unparsable}")


#: The ways an input can spell a pinned clone: both set, each half empty,
#: and neither (only the last is an input that is not pinned); then a
#: `sha` that is a prefix of a commit's id, which loads, and the two `git`
#: values a file system reads as a direction, a `sha` that is a path, a `sha`
#: that is a path whose every character is a hexadecimal digit, a `.` or a
#: `/`, and a `sha` in capitals, which do not.
_A_SHA = "0" * 40
_A_URL = "https://example.invalid/r"
_A_PATH = "../elsewhere"
_A_PATH_OF_HEX = "../e"
_A_CAPITALS = "ABCDEF"
_PIN_PLANTS = {
    "both set": f'git = "{_A_URL}"\nsha = "{_A_SHA}"',
    "an empty git": f'git = ""\nsha = "{_A_SHA}"',
    "an empty sha": f'git = "{_A_URL}"\nsha = ""',
    "neither": "",
    "a prefix": f'git = "{_A_URL}"\nsha = "{_A_SHA[:7]}"',
    "a git of .": f'git = "."\nsha = "{_A_SHA}"',
    "a git of ..": f'git = ".."\nsha = "{_A_SHA}"',
    "a sha that is a path": f'git = "{_A_URL}"\nsha = "{_A_PATH}"',
    "a sha that is a path of hexadecimal characters":
        f'git = "{_A_URL}"\nsha = "{_A_PATH_OF_HEX}"',
    "a sha in capitals": f'git = "{_A_URL}"\nsha = "{_A_CAPITALS}"',
}


def _empty_pin_control(check: CheckRow) -> None:
    """(xxxx) an empty `git` or `sha` is a missing one, and a `git` of `.` or
    `..`, or a `sha` that is not a lowercase hexadecimal id, is refused: neither
    can name a folder under the cache."""
    label = ("xxxx  `git` and `sha` come together by their VALUES, so an "
             "empty one is a missing one: `git = \"\"` beside a `sha` is "
             "refused at load, where a test on their PRESENCE let it through "
             "and the input was then captured against the local tree with the "
             "manifest still claiming a pin. Both set loads as a pinned input, "
             "neither as an unpinned one; a `git` of `.` or `..` and a `sha` "
             "that is not made of lowercase hexadecimal digits are refused at load, "
             "a `sha` of `../e`, a path made of nothing else than `.`, `/` "
             "and a hexadecimal digit, among them, "
             "each naming the input and the value as given, with a `next:` "
             "that says what to give, while a prefix of a commit's id loads")
    verdicts: dict[str, str] = {}
    nexts: dict[str, str] = {}
    for why, rows in _PIN_PLANTS.items():
        text = _STUB_MANIFEST.replace("args     = []",
                                      "args     = []\n" + rows)
        with _box("golden-census-pin-") as box:
            try:
                pinned = load_manifest(_scratch(box, manifest_text=text)).inputs[0]
                verdicts[why] = (f"loaded, git={pinned.git!r} sha="
                                 f"{(pinned.sha or '')[:4] or None!r}")
            except Refusal as refused:
                # The refusal cut at its first clause, with the scratch
                # manifest's own path taken out: this row is read on any
                # machine and the directory it would name is this one's.
                verdicts[why] = ("REFUSED: "
                                 + str(refused).replace(box + "/", ""))
                nexts[why] = refused.next
    empties = [verdicts["an empty git"], verdicts["an empty sha"]]
    place = "manifest.toml: [inputs._subject]: "
    check(label,
          all(text.startswith("REFUSED: ")
              and "must both be present and non-empty" in text
              for text in empties)
          and verdicts["both set"].startswith("loaded, git='https")
          and verdicts["neither"] == "loaded, git=None sha=None"
          and verdicts["a prefix"] == "loaded, git='https://example.invalid/r' sha='0000'"
          and all(verdicts[why].startswith(f"REFUSED: {place}`git` is {value!r},")
                  and "a URL or a path" in nexts[why]
                  for why, value in (("a git of .", "."), ("a git of ..", "..")))
          and all(verdicts[why].startswith(f"REFUSED: {place}`sha` is {value!r}, ")
                  and "lowercase hexadecimal id, or a prefix" in nexts[why]
                  for why, value in (("a sha that is a path", _A_PATH),
                                     ("a sha that is a path of hexadecimal "
                                      "characters", _A_PATH_OF_HEX),
                                     ("a sha in capitals", _A_CAPITALS))),
          ACTUAL + "; ".join(f"{why} -> {verdicts[why]}"
                                 for why in _PIN_PLANTS))


#: What arm `ddddddddd` plants as a `git` that opens with `-`: a flag git
#: takes whole, a short one, and an option that carries a program; then the
#: spelling that names a path, which loads.
_DASH_PLANTS = ("--bare", "-q", "--upload-pack=touch x", "./-lib")


def _dash_address_control(check: CheckRow, skip: SkipRow) -> None:
    """(ddddddddd) a `git` value that opens with `-` is refused at load, and
    the `git clone` golden-census runs passes `--` before the address.

    `run.clone_input` once ran `git clone --quiet <url> <target>` and
    `manifest._inputs` refused only `""`, `.` and `..`: a `git` of `--bare`
    was read by git as an option, and the SKIP named the cache folder as the
    repository. Each value of `_DASH_PLANTS` is loaded from a scratch
    manifest: the first three are refused naming the input and the value as
    given, with the `next:` sentence, and `./-lib` loads. Then one
    `clone_input` of a local repository runs with a `git` in front of PATH
    that appends its argv to a file and runs the real one; the argv of the
    `clone` it was handed has `--` after `--quiet` and before the address.
    A SKIP where `git` is not on PATH.
    """
    label = ("ddddddddd  a git value that opens with - is refused at load "
             "naming the input and the value, --bare, -q and an "
             "--upload-pack= among them, while ./-lib loads; and the git "
             "clone golden-census runs passes -- before the address, read "
             "from the argv a git planted on PATH wrote down")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no repository can be made and "
                    "no clone run; nothing was made and nothing is claimed.")
        return
    verdicts: dict[str, str] = {}
    nexts: dict[str, str] = {}
    for value in _DASH_PLANTS:
        text = _STUB_MANIFEST.replace(
            "args     = []",
            f'args     = []\ngit = {json.dumps(value)}\nsha = "{_A_SHA}"')
        with _box("golden-census-dash-") as box:
            try:
                load_manifest(_scratch(box, manifest_text=text))
                verdicts[value] = "loaded"
            except Refusal as refused:
                verdicts[value] = ("REFUSED: "
                                   + str(refused).replace(box + "/", ""))
                nexts[value] = refused.next
    with _box("golden-census-dash-clone-") as box:
        origin = os.path.join(box, "origin")
        os.makedirs(origin)
        pathlib.Path(origin, "a.txt").write_text("one line\n",
                                                 encoding="utf-8")
        code, head, stderr = _repo_of(origin, "the origin")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        sha = launch(["git", "-C", origin, "rev-parse", "HEAD"],
                     "git rev-parse", env=git_env()).stdout.strip()
        front = os.path.join(box, "bin")
        os.makedirs(front)
        notes = os.path.join(box, "argv")
        _planted_script(
            os.path.join(front, "git"),
            f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {shlex.quote(notes)}\n"
            f"echo --- >> {shlex.quote(notes)}\n"
            f"exec {shlex.quote(shutil.which('git') or 'git')} \"$@\"\n")
        with _env_as({"PATH": front + os.pathsep
                      + os.environ.get("PATH", "")}):
            tree, why = clone_input(os.path.join(box, "cache"), origin, sha,
                                    io.StringIO())
        try:
            blocks = [block.splitlines() for block in
                      pathlib.Path(notes).read_text(encoding="utf-8")
                      .split("---\n")]
        except OSError:
            blocks = []
    argv = next((block[block.index("clone"):] for block in blocks
                 if "clone" in block), [])
    place = "manifest.toml: [inputs._subject]: "
    dashed = _DASH_PLANTS[:3]
    check(label,
          all(verdicts[value].startswith(
              f"REFUSED: {place}`git` is {value!r}, which opens with `-` "
              "and git would read as an option.") for value in dashed)
          and all("a URL or a path; spell a path that begins with `-` as "
                  "`./-…`" in nexts[value] for value in dashed)
          and verdicts["./-lib"] == "loaded"
          and tree is not None and argv[:3] == ["clone", "--quiet", "--"]
          and len(argv) == 5 and argv[3].endswith(os.sep + "origin"),
          ACTUAL + "; ".join(f"{value} -> {_one_line(verdicts[value], 200)}"
                             for value in _DASH_PLANTS)
          + f"; the clone: {tree!r} {_one_line(why, 100)!r}, argv "
          + _one_line(" ".join(argv).replace(box, "<box>"), 200,
                      empty="not written down"),
          next="`manifest._inputs` refuses a `git` that opens with `-` after "
               "its `.` and `..` refusal, and `run.clone_input` runs `git "
               "clone --quiet -- <address> <target>`.")


#: The password `fffffffff` plants and must never find in a sentence.
_A_PASSWORD = "s3cr3t-token"


def _password_address_control(check: CheckRow) -> None:
    """(fffffffff) an address that carries a password is refused at load.

    `git = "http://user:TOKEN@host/repo.git"` once cloned at exit 0, the
    `clone:` line printed the token and the cache folder's name held it.
    The address with a password is refused naming the input and never the
    password, the refusal and its `next:` alike; a userinfo with no password,
    an scp-like address and an `ssh://` address load. A user name with no
    password stays in the address, the folder name and the `clone:` line:
    it is no secret, and the manifest that spells it is committed.
    """
    label = ("fffffffff  an address that carries a password is refused at "
             "load naming the input and never the password, while a "
             "userinfo with no password, an scp-like address and an ssh:// "
             "address load")
    loads = ("https://alice@host/r", "git@host:o/r.git", "ssh://git@host/r")
    refused_value = f"http://alice:{_A_PASSWORD}@host/r.git"
    verdicts: dict[str, str] = {}
    nexts: dict[str, str] = {}
    for value in (refused_value, *loads):
        text = _STUB_MANIFEST.replace(
            "args     = []",
            f'args     = []\ngit = {json.dumps(value)}\nsha = "{_A_SHA}"')
        with _box("golden-census-password-") as box:
            try:
                load_manifest(_scratch(box, manifest_text=text))
                verdicts[value] = "loaded"
            except Refusal as refused:
                verdicts[value] = ("REFUSED: "
                                   + str(refused).replace(box + "/", ""))
                nexts[value] = refused.next
    said = verdicts[refused_value]
    check(label,
          said == "REFUSED: manifest.toml: [inputs._subject]: `git` carries "
                  "a password in its address."
          and _A_PASSWORD not in said
          and _A_PASSWORD not in nexts.get(refused_value, _A_PASSWORD)
          and nexts.get(refused_value, "").startswith(
              "Keep the credential in a git credential helper")
          and all(verdicts[value] == "loaded" for value in loads),
          ACTUAL + "; ".join(f"{value} -> {_one_line(verdicts[value], 160)}"
                             for value in (refused_value, *loads)),
          next="`manifest._inputs` refuses a `git` that matches "
               "`_PASSWORD_ADDRESS` without quoting it.")


def _refusal_gist(path: str, box: str) -> str:
    """What `load_manifest` said about one file, as one line without the
    arm's own scratch directory in it."""
    return _one_line(_printed_refusal(functools.partial(load_manifest, path),
                                      unrefused="LOADED (no refusal)")
                     .replace(box, "<box>"), DIFFERENCE * 2)


_UNPROVEN_PIN = '''
[[input]]
name        = "a variable no surface reads"
disposition = "pin"
variable    = "GOLDEN_CENSUS_UNREAD"
value       = "1"
finding     = "planted: this row claims a pin that moves nothing, so its own control must go red"
control     = { shape = "vary", surface = "_subject/help", value = "2" }
'''


def _vary_red_control(check: CheckRow, skip: SkipRow) -> None:
    """(w) the census `vary` control itself can go red.

    A pin of a variable the subject reads comes out PASS; a pin of a variable
    no surface reads comes out UNPROVEN — a FAIL. A control that could not go
    red would let any census claim anything.
    """
    with _box("golden-census-vary-") as box:
        try:
            manifest = load_manifest(_scratch(
                box, census_text=_STUB_CENSUS + _UNPROVEN_PIN))
        except Refusal as refused:
            skip("w  the census vary control's own red",
                 f"the scratch manifest would not load: {refused}. Nothing is "
                 "claimed.")
            return
        roots = Roots(root=manifest.subject.root, work=box, clone=None)
        rows, skips = _census_rows(manifest, roots)
    reads = [r for r in rows if "COLUMNS" in r[0]]
    unread = [r for r in rows if "GOLDEN_CENSUS_UNREAD" in r[0]]
    ok = (len(reads) == 1 and reads[0][1]
          and len(unread) == 1 and not unread[0][1]
          and "UNPROVEN" in unread[0][2])
    check("w  the census `vary` control can go red: a COLUMNS pin against a "
          "stub subject that wraps its --help PASSES, and a pin of a variable "
          "no surface reads comes out UNPROVEN — a FAIL of the census, not of "
          "the subject",
          ok,
          f"{ACTUAL}{[(r[0][:44], r[1]) for r in rows]}, "
          f"{len(skips)} skip(s)")


# ------------------------------------------- one vocabulary per loader (jj, kk)
#
# `core.Placeholders` is built once per loader, so the load-time half — every
# token is one golden-census knows — cannot drift away from the run-time half.
# The two arms below are the two files where the cost of losing that is
# highest: a census pin and a mutants check command that LOAD and refuse later,
# at a price the loader exists to avoid.

#: (jj) a census pin whose value spells a placeholder golden-census does not
#: define. Unchecked at load, this file LOADS and refuses inside `build_env`,
#: with a capture already under way.
_TMP_PIN_CENSUS = _STUB_CENSUS + '''
[[input]]
name        = "a pin whose value spells an invented placeholder"
disposition = "pin"
variable    = "GOLDEN_CENSUS_PLANTED"
value       = "<TMP>/planted"
finding     = "planted: <TMP> is no placeholder of golden-census, and the load has to say so"
control     = { shape = "vary", surface = "_subject/help", value = "2" }
'''

#: (kk) a mutants `command` check spelling a placeholder golden-census does not
#: define. Unchecked at load, this file LOADS, the subject is cloned and the
#: null mutant run before the refusal arrives.
_WORK_CHECK_MUTANTS = '''\
[checks.probe]
command = ["<PYTHON>", "probe.py", "<WORK>"]
fires   = { pattern = "MOVED" }

[[mutant]]
name    = "a mutant no clone is ever made for"
file    = "tool.py"
find    = "rows: 3"
replace = "rows: 4"
expect  = ["probe"]
'''


def _loader_placeholder_control(check: CheckRow) -> None:
    """(jj) the census loader refuses an unknown placeholder in a pin value,
    naming the token and the file; and `docs.measure` refuses one in a README
    cost pin rather than handing it to argparse unexpanded.

    Two halves of one fact — a placeholder vocabulary that is checked where it
    is read — so they ride in one row.
    """
    pin_verdict = "LOADED (no refusal)"
    with _box("golden-census-pinvocab-") as box:
        _scratch(box, census_text=_TMP_PIN_CENSUS)
        census_path = os.path.join(box, "census.toml")
        try:
            load_census(census_path)
        except Refusal as refused:
            text = str(refused)
            pin_verdict = ("names the token and the file"
                           if "<TMP>" in text and census_path in text
                           else f"REFUSED without naming both: {text[:90]}")

    cost_verdict = "EXPANDED nothing and refused nothing"
    with _box("golden-census-pinvocab-") as box:
        planted = (Invocation("`planted`", ("--version", "<OUTT>")),)
        before = sorted(os.listdir(box))
        try:
            measure(planted, os.path.join(box, "fixture"), box)
        except Refusal as refused:
            text = str(refused)
            cost_verdict = ("names the token"
                            if "<OUTT>" in text and "<OUT>" in text
                            else f"REFUSED without naming it: {text[:90]}")
        ran = sorted(os.listdir(box)) != before

    check("jj  a placeholder vocabulary is checked where the file is READ: a "
          "census pin spelling <TMP> is refused by `load_census` naming the "
          "token and the census file, before anything runs; and a priced "
          "invocation spelling <OUTT> is refused by `docs.measure` naming the "
          "token and the whole list, with no command run",
          pin_verdict == "names the token and the file"
          and cost_verdict == "names the token" and not ran,
          f"{ACTUAL}the census pin -> {pin_verdict}; the priced argv -> "
          f"{cost_verdict}, a command ran={ran}")


def _mutants_placeholder_control(check: CheckRow) -> None:
    """(kk) the mutants loader refuses an unknown placeholder in a `command`
    check, before a clone exists to run it against.

    The cost of the other order is what this arm holds: a check command
    spelling `<WORK>` that loads, a subject cloned, a null mutant run against
    it, and only then the expansion's refusal.
    """
    base_tmp = temp_base()
    # The box sits OUTSIDE the private root `_made_under` makes, so the
    # listing IS what the load made — where a before/after subtraction over the
    # shared root counts any directory another process made during the body.
    with _box("golden-census-checkvocab-") as box:
        path = os.path.join(box, "mutants.toml")
        pathlib.Path(path).write_text(_WORK_CHECK_MUTANTS, encoding="utf-8")

        def body() -> str:
            try:
                load_mutants(path)
            except Refusal as refused:
                text = str(refused)
                return ("names the token and the check"
                        if "<WORK>" in text and "[checks.probe]" in text
                        else f"REFUSED without naming both: {text[:90]}")
            return "LOADED (no refusal) — a clone would follow"

        verdict, made = _made_under(base_tmp, body)
    check("kk  a mutants `command` check spelling <WORK> is refused by "
          "`load_mutants` naming the token and the check — before a clone is "
          "made, so a bad token costs no clone, no null mutant and no "
          "capture; and the load itself makes nothing",
          verdict == "names the token and the check" and not made,
          f"{ACTUAL}the check command -> {verdict}, "
          f"{len(made)} directory(ies) made by the load {made}")


# ------------------------------------------------------------------ <HERE>
#
# The token means "the directory of the file that spells it", and it is a name
# of the census's vocabulary and of the mutants file's, and of no other. Three
# verdicts in one row: it resolves in a census, it resolves in a mutants file's
# `golden` — proved end to end, by a null mutant that is SILENT against a
# golden only that resolution can reach — and a manifest that spells it is
# refused like any other invented token, which is the positive control.

#: A census whose `state` command names a script by `<HERE>`. The script exists
#: BESIDE THE CENSUS and nowhere else, and the run's cwd is a different, empty
#: directory — so the marker in the state line cannot have come from anywhere
#: but the token resolving to the census's own directory.
_HERE_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the tool versions this capture was taken under"
disposition = "state"
commands    = [["<PYTHON>", "<HERE>/version.py"]]
finding     = "a toolchain upgrade moves a rendered surface and is attributed as such"
'''

_HERE_VERSION_SCRIPT = 'print("HERE-MARKER 1.0")\n'

#: A mutants file whose golden sits BESIDE IT rather than inside the subject —
#: the shape a consumer whose goldens are not in the subject's repository
#: needs, and the reason `<HERE>` was added to this vocabulary.
_HERE_MUTANTS = '''\
[checks.comparator]
builtin = "compare"
golden  = "<HERE>/golden"

[[mutant]]
name    = "the row count"
file    = "tool.py"
find    = 'print("rows: 3")'
replace = 'print("rows: 4")'
expect  = ["comparator"]
'''


def _here_census_half(box: str) -> str:
    """The state line a census spelling `<HERE>/version.py` prints."""
    beside = os.path.join(box, "beside")
    root = os.path.join(box, "elsewhere")
    for one in (beside, root):
        os.makedirs(one)
    for leaf, body in (("version.py", _HERE_VERSION_SCRIPT),
                       ("census.toml", _HERE_CENSUS)):
        pathlib.Path(os.path.join(beside, leaf)).write_text(body, encoding="utf-8")
    census = load_census(os.path.join(beside, "census.toml"))
    roots = Roots(root=root, work=box, clone=None, fixed=None)
    log = io.StringIO()
    state(census, roots, build_env(census, roots), log)
    # The VERDICT, not the line: the line carries a temp path, and an
    # assertion made against a truncation of it would read differently under
    # a 15-character temp root and a 49-character one.
    return (f"the marker the script beside the census prints reached the "
            f"state block={'HERE-MARKER 1.0' in log.getvalue()}")


#: The label of the SKIP row that discloses a `<HERE>` mutants half not run.
_HERE_HALF_LABEL = "bbb  the mutants `golden` half"


def _here_golden_half(box: str, skip: SkipRow) -> tuple[str, str]:
    """`(what the <HERE> golden did, what the bare golden did)`, or `("", "")`
    and one disclosed SKIP of `skip` when this machine's `git` cannot make the
    repository the half plants its mutants in: one that exits non-zero on the
    way. The reason names the command and its exit code. Neither is a verdict
    on `<HERE>`.

    The whole `mutants` run, not a resolved path: a null mutant that is SILENT
    means a capture of the unmutated clone was IDENTICAL to a golden the
    golden-census could only have found beside the mutants file, and the
    mutant
    FIRING against the same golden means it was really compared. The bare form
    beside it is what says the token did the work — the clone carries no
    `golden` directory, so it refuses naming what it was resolved against.
    """
    path, why = _mutant_box(box)
    if path is None:
        skip(_HERE_HALF_LABEL,
             f"{why.rstrip(': ')}; the half needs `git clone --local` to make "
             "the repo-shaped copy a mutant is planted in, and that git did "
             "not make the repository. The census half and the manifest "
             "control still ran; nothing is claimed for this one.")
        return "", ""
    manifest = load_manifest(path)
    log = io.StringIO()
    code = capture(manifest, os.path.join(box, "golden"), log)
    if code != 0:
        return (f"the golden capture exited {code}: "
                f"{_one_line(log.getvalue(), DIFFERENCE)}"), ""
    for leaf, text in (("here.toml", _HERE_MUTANTS),
                       ("bare.toml", _HERE_MUTANTS.replace(
                           'golden  = "<HERE>/golden"', 'golden  = "golden"'))):
        pathlib.Path(os.path.join(box, leaf)).write_text(text, encoding="utf-8")
    here_code, here_text = _mutants_run(manifest, box, "here.toml")
    bare_code, bare_text = _mutants_run(manifest, box, "bare.toml")
    # The verdicts, computed from the WHOLE log. A truncation of the log would
    # cut at a different word under a 15-character temp root and a
    # 49-character one, and an assertion made against it would move with the
    # machine — which is the defect this whole tool exists to catch.
    return (f"exit {here_code}, null mutant SILENT="
            f"{'null mutant: comparator SILENT' in here_text}, mutant caught="
            f"{'1/1 mutants caught' in here_text}",
            f"exit {bare_code}, refused about the golden="
            f"{'no golden directory' in bare_text}, the form named="
            f"{'relative to the mutated copy' in bare_text}")


def _here_control(check: CheckRow, skip: SkipRow) -> None:
    """(bbb) `<HERE>` in the two files that define it, and nowhere else.

    The mutants half needs a repository, so a machine whose `git` cannot make
    one is a disclosed SKIP of that half and never a red row.
    """
    label = ("bbb  `<HERE>` is the directory of the file that spells it, in a "
             "census and in a mutants file: a `state` command spelling "
             "`<HERE>/version.py` runs the script that sits beside the CENSUS "
             "while the run's cwd is a different directory, and a mutants file "
             "whose `golden` is `<HERE>/golden` compares against the golden "
             "beside ITSELF — its null mutant SILENT and its mutant FIRED — "
             "where the same file written with the bare form refuses, naming "
             "what it resolved against. The positive control is a manifest "
             "spelling `<HERE>` in a surface's `args`, refused as a token "
             "golden-census defines elsewhere and not THERE — `is not a "
             "placeholder golden-census defines here` — with the whole list "
             "in the sentence")
    with _box("golden-census-here-") as box:
        state_line = _here_census_half(box)

        control = os.path.join(box, "control")
        # In `args`, where the token is not a name of the vocabulary: in
        # `[subject] command` it now IS one, which is arm `dddd`'s subject.
        holed = _scratch(control, manifest_text=_STUB_MANIFEST.replace(
            'args = ["--help"]', 'args = ["--help", "<HERE>/stub.py"]'))
        refused = _refused_by(functools.partial(load_manifest, holed))

        here_run, bare_run = "", ""
        if shutil.which("git") is None:
            skip(_HERE_HALF_LABEL,
                 "`git` is not on PATH, and the half needs `git clone --local` "
                 "to make the repo-shaped copy a mutant is planted in. The "
                 "census half and the manifest control still ran; nothing is "
                 "claimed for this one.")
        else:
            mutants_box = os.path.join(box, "mutants")
            os.makedirs(mutants_box)
            here_run, bare_run = _here_golden_half(mutants_box, skip)
    census_ok = state_line.endswith("=True")
    golden_ok = (not here_run
                 or (here_run == "exit 0, null mutant SILENT=True, mutant "
                                 "caught=True"
                     and bare_run == "exit 2, refused about the golden=True, "
                                     "the form named=True"))
    manifest_ok = ("<HERE> is not a placeholder golden-census defines "
                   "here. The whole list is <ROOT>," in refused)
    check(label, census_ok and golden_ok and manifest_ok,
          f"{ACTUAL}the census half — {state_line}; the <HERE> golden -> "
          f"{here_run or '(not exercised; see the SKIP)'}; the bare golden -> "
          f"{bare_run or '(not exercised)'}; a manifest spelling it -> "
          + _one_line(refused, DIFFERENCE))


# ------------------------------------------- git declining to answer at all
#
# `git rev-parse --is-inside-work-tree` says `true`, says `false`, or does not
# answer: a repository owned by another user, a broken index, a git too old
# for the flag. The third is not the second, and a refusal that read an empty
# stdout as "not a work tree" would send the reader to the manifest over a
# fault in the machine.

_GIT_CENSUS = _STUB_CENSUS + '''
[[input]]
name        = "the subject's tree is a git checkout"
disposition = "precondition"
check       = "git-checkout"
clean       = false
finding     = "planted: a golden captured from an unidentified tree names no sha"
'''


def _git_precondition(census: Census, root: str) -> str:
    """The verdict a `git-checkout` precondition reaches over `root`: the
    `[OK]` line it wrote, or the two lines it refused with."""
    log = io.StringIO()
    try:
        preconditions(census, Roots(root=root, work=root, clone=None), log)
    except Refusal as refused:
        return refusal_text(refused)
    return log.getvalue().strip()


def _git_answer_control(check: CheckRow, skip: SkipRow) -> None:
    """(hhhh) git's own words when git declines to answer."""
    label = ("hhhh  a `git-checkout` precondition over a directory that is no "
             "repository refuses with GIT's own words — its exit code and the "
             "first line of its stderr — and not with a sentence about work "
             "trees that git never said. The other side of the row is the "
             "control: the same precondition over a real repository writes "
             "its `[OK]` line, so the refusal is not something this check "
             "does to every directory")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so neither half can be run. "
                    "Nothing is claimed.")
        return
    with _box("golden-census-gitanswer-") as box:
        bare = os.path.join(box, "not-a-repository")
        repo = os.path.join(box, "a-repository")
        for one in (bare, repo):
            os.makedirs(one)
        census_path = os.path.join(box, "census.toml")
        pathlib.Path(census_path).write_text(_GIT_CENSUS, encoding="utf-8")
        census = load_census(census_path)
        pathlib.Path(os.path.join(repo, "a-file")).write_text("one line\n", encoding="utf-8")
        made, what, why = _repo_of(repo, "the control's own commit",
                                   lambda argv: f"the git arm's {argv[1]!r}")
        if made != 0:
            skip(label, f"the scratch repository could not be made: {what} "
                        f"exited {made}: {_one_line(why, DIFFERENCE)}. "
                        "Nothing is claimed.")
            return
        # `bare` is only a directory this arm made; it is a repository only if
        # the machine's temp root is itself inside a work tree, which the
        # verdict below would show as an [OK] line and fail the row honestly.
        declined = _git_precondition(census, bare)
        answered = _git_precondition(census, repo)
    quotes_git = ("so its standard output was not read" in declined
                  and "exited 128" in declined
                  and "not a git repository" in declined
                  and declined.startswith("REFUSED: "))
    # The verdicts, not the refusal: it carries the scratch directory's path,
    # and a detail line quoting it would print a directory of this machine.
    ok_line = "[OK] the subject's tree is a git checkout" in answered
    check(label, quotes_git and ok_line,
          ACTUAL + "a directory that is no repository -> "
          + ("refused quoting git's exit code and git's own first line"
             if quotes_git else _one_line(declined, DIFFERENCE))
          + f"; a real repository -> its [OK] line={ok_line}")


# ------------------------------------------ git not exiting 0, every run
#
# `_git_checkout` runs git three times and tests each return code before it
# reads a byte of standard output. Two of the states below are repositories
# anyone can make. The planted ones are states no repository can be put into
# from outside — a git that exits non-zero AND prints on standard output, a
# git that prints no text at all, a git a signal ended, a first line longer
# than `QUOTE` — so a `git` in front of the real one answers one subcommand
# and hands every other to the real git.

_GIT_CLEAN_CENSUS = _GIT_CENSUS.replace("clean       = false",
                                        "clean       = true")

_NOT_READ = ", so its standard output was not read — "

_GIT_OK = "    [OK] the subject's tree is a git checkout: "

_STATUS = "clean = true): `git status --porcelain` "

#: The last statement of a `git` in front: it exits 3, or it ends itself
#: with a signal, which `subprocess` hands back as a negative return code.
_EXITS_3 = _EXITS.format(code=3)

#: A first line seven characters longer than the quote is wide.
_LONG_LINE = "fatal: " + "x" * QUOTE


def _quoted_width(verdict: str) -> str:
    """What the red detail of the long first line opens with: how many
    characters of that line the verdict quotes, which a verdict cut to a
    row's width cannot show."""
    runs = re.findall("fatal: x+", verdict)
    return (f"{len(runs[0]) if runs else 0} of the first line's "
            f"{len(_LONG_LINE)} character(s) quoted, `QUOTE` is {QUOTE} — ")


#: One row per state the git in front plants: the state's name, the
#: subcommand answered, what it prints on standard output, what it prints on
#: standard error, how it ends, the needles the verdict must carry, and the
#: needles it must not.
_GIT_IN_FRONT: tuple[tuple[str, str, str, str, str, tuple[str, ...],
                           tuple[str, ...]], ...] = (
    ("a `git status` that exits 3 and lists a path", "status",
     "?? planted.txt\n", "fatal: planted status\nhint: a second line\n",
     _EXITS_3,
     ("REFUSED: precondition ", _STATUS + "exited 3 in ",
      _NOT_READ + "git said 'fatal: planted status'. planted: "),
     ("planted.txt", "a second line", "[OK]")),
    ("a `git status` that exits 3 and prints nothing", "status", "", "",
     _EXITS_3,
     ("REFUSED: precondition ", _STATUS + "exited 3 in ",
      _NOT_READ + "git printed no text on stderr. planted: "),
     ("git said", "[OK]")),
    ("a `git log` that exits 3 and prints a revision", "log",
     "abc1234 a planted revision\n", "fatal: planted log\n", _EXITS_3,
     (_GIT_OK + "no revision quoted — `git log -1 --oneline` exited 3, "
      "git said 'fatal: planted log'",),
     ("abc1234", "REFUSED")),
    ("a `git rev-parse` that exits 3 and prints `true`", "rev-parse",
     "true\n", " \n", _EXITS_3,
     ("REFUSED: precondition ",
      "git-checkout): `git rev-parse --is-inside-work-tree` exited 3 in ",
      _NOT_READ + "git printed no text on stderr. planted: "),
     ("git said", "[OK]")),
    ("a `git status` that a signal ends", "status", "", "", _SIGNALS_ITSELF,
     ("REFUSED: precondition ",
      _STATUS + f"was ended by signal {int(signal.SIGTERM)} in ",
      _NOT_READ + "git printed no text on stderr. planted: "),
     ("exited", "[OK]")),
    ("a `git rev-parse` that a signal ends and prints `true`", "rev-parse",
     "true\n", "", _SIGNALS_ITSELF,
     ("REFUSED: precondition ",
      "git-checkout): `git rev-parse --is-inside-work-tree` was ended by "
      f"signal {int(signal.SIGTERM)} in ",
      _NOT_READ + "git printed no text on stderr. planted: "),
     ("exited", "[OK]")),
    ("a `git log` that a signal ends and prints a revision", "log",
     "abc1234 a planted revision\n", "fatal: planted log signal\n",
     _SIGNALS_ITSELF,
     (_GIT_OK + "no revision quoted — `git log -1 --oneline` was ended by "
      f"signal {int(signal.SIGTERM)}, git said 'fatal: planted log signal'",),
     ("abc1234", "exited", "REFUSED")),
    ("a first line longer than `QUOTE`", "status", "", _LONG_LINE + "\n",
     _EXITS_3,
     ("REFUSED: precondition ", _STATUS + "exited 3 in ",
      _NOT_READ + "git said '" + _LONG_LINE[:QUOTE] + "'. planted: "),
     (_LONG_LINE[:QUOTE + 1], "[OK]")),
)


#: A `git` in front of the real one that starts no program but the real
#: git: the interpreter of this run reads it by its first line, as it reads
#: arm `yyyyyy`'s planted git. It answers the run whose subcommand is `sub`
#: — the first word after the `-c` and `-C` pairs of `core.git_command`'s
#: argv — and replaces itself with the real git for every other run.
_IN_FRONT_GIT = """\
#!{python}
import os
import signal
import sys

# `rev-parse --local-env-vars` is `census.git_env`'s question, asked before
# every git the precondition runs, and it is answered by the real git.
words = sys.argv[1:]
while len(words) >= 2 and words[0] in ("-C", "-c"):
    words = words[2:]
if words[:1] == [{sub!r}] and words != ["rev-parse", "--local-env-vars"]:
    sys.stdout.write({printed!r})
    sys.stderr.write({said!r})
    sys.stdout.flush()
    sys.stderr.flush()
    {ends}
os.execv({git!r}, [{git!r}] + sys.argv[1:])
"""


def _git_in_front(directory: str, sub: str, printed: str, said: str,
                  ends: str) -> None:
    """Write `directory/git` from `_IN_FRONT_GIT`: a script that answers the
    subcommand `sub` by printing `printed` on standard output and `said` on
    standard error and ending as `ends` says, and hands every other
    invocation to the real git unchanged."""
    _planted_script(os.path.join(directory, "git"), _IN_FRONT_GIT.format(
        python=sys.executable, sub=sub, printed=printed, said=said, ends=ends,
        git=shutil.which("git")))


def _git_exit_control(check: CheckRow, skip: SkipRow) -> None:
    """(xxxxxx) a `git-checkout` precondition tests how every git it runs
    ended before it reads that git's standard output.

    Sixteen verdicts. Eight are over repositories this arm makes: one
    commit and an index overwritten with the word `garbage`, which `git
    status` exits 128 over — under `clean = true`, under `clean = false`,
    and under the `census` command run as a child, which is the one verdict
    that sees an exit code of golden-census's own; no commit and no file,
    which `git log` exits 128 over; a linked worktree of a repository whose
    HEAD commit object is cut to 0 bytes, which `git log` exits 128 over
    naming that object file by its absolute path in the MAIN repository,
    outside the subject root; one commit whose subject is the word `at` and
    the scratch directory's path, which `git log` prints; one commit and an
    untracked file, in a repository whose configuration sets
    `status.showUntrackedFiles = no`, under which a plain `git status
    --porcelain` lists nothing; and the control, one commit and a clean
    tree.
    Eight are over the control with a `git` in front of the real one
    (`_GIT_IN_FRONT`), because no repository makes git exit non-zero AND
    print on standard output, print no text at all, end by a signal, or
    print a first line longer than `QUOTE`: those are the states that tell a
    test of the return code made FIRST from one made after standard output
    was read, `_git_said`'s second form from its first, `core.ended`'s
    second form from its first — for each of the three gits, since a return
    code tested with `> 0` lets a signal through where `!= 0` does not — and
    a quote cut at `QUOTE` from one cut anywhere else.

    Git's own words are asserted only where this arm planted them. Over the
    real repositories the verdict is held to git's exit code and to the
    opening of `_git_said`'s first form, so a git that words its error
    differently does not turn the row red. The linked worktree's verdict
    and the path-bearing subject's also hold the path as the fold leaves it
    — the census's `<WORK>` token, then the path under the temp root, whole
    — and neither spelling of the scratch directory: each `[OK]` line is a
    line golden-census prints about the machine, folded by
    `census.own_log`, so a git that names no path in its first line turns
    the row red rather than passing it unexamined.
    """
    label = ("xxxxxx  a `git-checkout` precondition tests how every git it "
             "runs ended BEFORE it reads that git's standard output: with "
             "`clean = true` over a repository whose index git cannot read "
             "it refuses with git's exit code and git's own first line — "
             "never an `[OK]` over a `git status` whose standard output was "
             "not read — the `census` command run over that repository as a "
             "child exits 2, and with `clean = false` the same repository "
             "prints its revision, because no `git status` is run. Over a "
             "repository with no commit the `[OK]` line says no revision is "
             "quoted, with `git log`'s exit code and git's own first line; "
             "over a linked worktree whose HEAD commit object is empty that "
             "line names the object's file in the main repository, outside "
             "the subject root, and over a repository whose commit subject "
             "is `at` and the scratch directory's path the `[OK]` line that "
             "quotes the revision names that directory: each path is "
             "written as the token of the census's `path` row and the whole "
             "path under it, and neither line holds the scratch directory "
             "as this machine spells it. With `clean = true` over a "
             "repository whose configuration sets "
             "`status.showUntrackedFiles = no` and that holds an untracked "
             "file, it refuses naming that file. "
             "A `git` planted in front of the real one reaches what no "
             "repository can: a `git status` and a `git log` that exit "
             "non-zero AND print on standard output, whose output is quoted "
             "nowhere; a `git status` and a `git rev-parse` that exit "
             "non-zero and print no text on stderr, which is said in "
             "golden-census's words outside any quotes; a `git rev-parse` "
             "that prints `true`, a `git status`, and a `git log` that "
             "prints a revision, each of which a signal ended, which is said "
             "with the signal's number and without the word `exited`, and "
             "neither `true` nor the revision is read; and a first line "
             "longer than "
             "`QUOTE`, which is quoted at `QUOTE` characters. The control "
             "is a clean repository with one commit, which prints its "
             "revision")
    noise = _startup_noise()
    if noise is not None:
        skip(label, _startup_noise_reason(noise))
        return
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no half can be run. "
                    "Nothing is claimed.")
        return
    verdicts: dict[str, tuple[bool, str]] = {}
    with _box("golden-census-gitexit-") as box:
        census_path = os.path.join(box, "census.toml")
        pathlib.Path(census_path).write_text(_GIT_CLEAN_CENSUS,
                                             encoding="utf-8")
        clean = load_census(census_path)
        pathlib.Path(census_path).write_text(_GIT_CENSUS, encoding="utf-8")
        unclean = load_census(census_path)
        pathlib.Path(census_path).write_text(_GIT_CENSUS + _STUB_WORK_FOLD,
                                             encoding="utf-8")
        folded = load_census(census_path)
        control = os.path.join(box, "one-commit")
        unread = os.path.join(box, "unreadable-index")
        empty = os.path.join(box, "no-commit")
        main = os.path.join(box, "main-repository")
        linked = os.path.join(box, "linked-worktree")
        pathed = os.path.join(box, "path-in-subject")
        hidden = os.path.join(box, "hidden-untracked")
        for one in (control, empty, main, pathed, hidden):
            os.makedirs(one)
        # The child's manifest, census and subject are in the commit, so the
        # tree it is run over holds nothing `git status` would list.
        manifest = _scratch(unread, census_text=_GIT_CLEAN_CENSUS)

        def phrase(argv: list[str]) -> str:
            return f"the git exit arm's {argv[1]!r}"

        for one in (control, unread, main, pathed, hidden):
            pathlib.Path(os.path.join(one, "a-file")).write_text(
                "one line\n", encoding="utf-8")
            made, what, why = _repo_of(
                one, f"at {box}" if one == pathed
                else "the control's own commit", phrase)
            if made != 0:
                skip(label, f"the scratch repository could not be made: "
                            f"{what} did not exit 0 (return code {made}): "
                            f"{_one_line(why, DIFFERENCE)}. Nothing is "
                            "claimed.")
                return
        for made_by in (["git", "-C", hidden, "config",
                         "status.showUntrackedFiles", "no"],
                        ["git", "init", "--quiet", empty],
                        ["git", "-C", main, "worktree", "add", "--quiet",
                         linked],
                        ["git", "-C", linked, "rev-parse", "HEAD"]):
            started = launch(git_command(*made_by[1:]), phrase(made_by),
                             stdin=subprocess.DEVNULL, env=git_env())
            if started.returncode != 0:
                skip(label, "the scratch repository could not be made: "
                            f"{' '.join(made_by[:4])} did not exit 0 "
                            f"(return code {started.returncode}): "
                            f"{_one_line(started.stderr, DIFFERENCE)}. "
                            "Nothing is claimed.")
                return
        # The HEAD commit's object, which the linked worktree shares with the
        # main repository, cut to 0 bytes: git reads the object store there.
        sha = started.stdout.strip()
        cut = os.path.join(main, ".git", "objects", sha[:2], sha[2:])
        os.chmod(cut, 0o644)
        pathlib.Path(cut).write_bytes(b"")
        pathlib.Path(os.path.join(unread, ".git", "index")).write_text(
            "garbage\n", encoding="utf-8")
        pathlib.Path(os.path.join(hidden, "untracked.txt")).write_text(
            "not in the commit\n", encoding="utf-8")

        def held(key: str, census: Census, root: str,
                 carries: tuple[str, ...], lacks: tuple[str, ...],
                 told: Callable[[str], str] | None = None) -> None:
            verdict = _git_precondition(census, root)
            verdicts[key] = (
                all(needle in verdict for needle in carries)
                and not any(needle in verdict for needle in lacks),
                (told(verdict) if told is not None else "")
                + _one_line(verdict.replace(os.path.realpath(box), "<box>")
                            .replace(box, "<box>"), 2 * DIFFERENCE,
                            needles=("REFUSED: ", "[OK]")))

        refused_128 = ("REFUSED: precondition ",
                       _STATUS + "exited 128 in " + unread + _NOT_READ
                       + "git said ")
        held("an index git cannot read", clean, unread, refused_128,
             ("[OK]",))
        held("the same index with `clean = false`", unclean, unread,
             (_GIT_OK, " the control's own commit"),
             ("no revision quoted", "exited", "REFUSED"))
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.dirname(PACKAGE)
        child = launch(_package_argv("-m", IMPORT_NAME, "census",
                                     "--manifest", manifest),
                       "the git exit arm's child", env=env, cwd=box,
                       stdin=subprocess.DEVNULL)
        heard = _heard(child.stderr)
        verdicts["the `census` command over that index, as a child"] = (
            child.returncode == 2
            and all(needle in child.stdout for needle in refused_128)
            and _GIT_OK not in child.stdout
            and "Traceback" not in child.stdout + heard.own
            and not heard.not_from(PACKAGE),
            f"exit {child.returncode}, "
            + _one_line(child.stdout.replace(box, "<box>"), 2 * DIFFERENCE,
                        needles=("REFUSED: ", "[OK]"), empty=_NO_VERDICT)
            + heard.not_from(PACKAGE))
        held("a repository with no commit", clean, empty,
             (_GIT_OK + "no revision quoted — `git log -1 --oneline` exited "
              "128, git said ",),
             ("REFUSED",))
        under_token = "<WORK>/" + os.path.basename(box)
        held("a linked worktree whose HEAD commit object is empty", folded,
             linked,
             (_GIT_OK + "no revision quoted — `git log -1 --oneline` exited "
              "128, git said '",
              f"{under_token}/main-repository/.git/objects/{sha[:2]}/"
              f"{sha[2:]}"),
             (*path_forms(box), "REFUSED"))
        held("a commit subject that holds a path", folded, pathed,
             (_GIT_OK, f" at {under_token}"),
             (*path_forms(box), "no revision quoted", "exited",
              "REFUSED"))
        held("an untracked file `status.showUntrackedFiles = no` hides",
             clean, hidden,
             ("REFUSED: precondition ", _STATUS + "in " + hidden
              + " printed '?? untracked.txt'. planted: "),
             ("[OK]",))
        held("the control", clean, control,
             (_GIT_OK, " the control's own commit"),
             ("no revision quoted", "exited", "REFUSED"))
        front = os.path.join(box, "in-front")
        os.makedirs(front)
        for key, sub, printed, said, ends, carries, lacks in _GIT_IN_FRONT:
            _git_in_front(front, sub, printed, said, ends)
            with _env_as({"PATH": front + os.pathsep
                          + os.environ.get("PATH", "")}):
                held(key, clean, control, carries, lacks,
                     _quoted_width if said.startswith(_LONG_LINE) else None)
    check(label, all(ok for ok, _ in verdicts.values()),
          ACTUAL + "; ".join(
              f"{key} -> " + ("as the label says" if ok else said)
              for key, (ok, said) in verdicts.items()),
          next="In `census._git_checkout`, test each git's `returncode` "
               "before its standard output is read, take the clause about "
               "how it ended from `core.ended` and the clause about "
               "standard error from `census._git_said`, and write both "
               "`[OK]` lines through one call of `census.own_log`.")


# ------------------------------------------ two surface keys, one file name

#: Two surfaces whose names differ only by case. On the case-insensitive
#: filesystem a golden set has to survive a checkout on, their recorded files
#: are one set of files and the second surface's bytes land on the first's.
_CASE_MANIFEST = _STUB_MANIFEST.replace(
    'surfaces = ["help"]', 'surfaces = ["help", "HELP"]') + '''
[surfaces.HELP]
args = ["--help", "--flag", "x"]
'''

#: The control: two names that differ by more than case, which is the ordinary
#: manifest this refusal must not touch.
_DISTINCT_MANIFEST = _CASE_MANIFEST.replace("HELP", "helpx")


def _case_folded_control(check: CheckRow) -> None:
    """(jjjj) two surface keys that are one name once case is folded."""
    label = ("jjjj  two `[surfaces.<name>]` keys that are the same name once "
             "case is folded are refused at LOAD, naming BOTH keys: a capture "
             "writes every surface of an input into one directory, and a "
             "golden set has to survive a checkout on a case-insensitive "
             "filesystem whoever recorded it — there the second set of files "
             "lands on the first, leaving one surface with no golden and "
             "nothing to say which. The control is two keys differing by more "
             "than case, which loads")
    verdicts: dict[str, str] = {}
    for name, text in (("the folded pair", _CASE_MANIFEST),
                       ("the distinct pair", _DISTINCT_MANIFEST)):
        with _box("golden-census-case-") as box:
            path = _scratch(box, manifest_text=text)
            try:
                verdicts[name] = ", ".join(load_manifest(path).row_keys())
            except Refusal as refused:
                verdicts[name] = refusal_text(refused)
    refused_text = verdicts["the folded pair"]
    names_both = ("[surfaces.help]" in refused_text
                  and "[surfaces.HELP]" in refused_text
                  and refused_text.startswith("REFUSED: "))
    loads = verdicts["the distinct pair"] == "_subject/help, _subject/helpx"
    check(label, names_both and loads,
          ACTUAL + "`help` beside `HELP` -> "
          + ("refused at load naming both keys" if names_both
             else _one_line(refused_text, DIFFERENCE))
          + f"; `help` beside `helpx` -> {verdicts['the distinct pair']}")


#: Two surface names arm `aaaaaaaa` plants beside the stub's, by their code
#: points: `é` as one character, and as `e` followed by a combining accent;
#: the compatibility ideograph U+F900, whose canonical decomposition is
#: U+8C48, beside U+8C48; two names that differ by case alone; then the
#: control pairs, which differ by more than that: `é` beside a bare `e`, and
#: a circled digit beside the digit, which only a compatibility
#: normalization would make one.
_NORMAL_PAIRS = {"one name": ("café", "café"),
                 "an ideograph": ("豈", "豈"),
                 "a case": ("Café", "café"),
                 "an accent": ("café", "cafe"),
                 "a compatibility form": ("row①", "row1")}


def _normal_plant(first: str, second: str) -> str:
    """The stub manifest with two more surfaces, named `first` and
    `second`, on its one input."""
    return _STUB_MANIFEST.replace(
        'surfaces = ["help"]',
        f'surfaces = ["help", "{first}", "{second}"]') + "".join(
        f'\n[surfaces."{name}"]\nargs = ["--help", "{index}"]\n'
        for index, name in enumerate((first, second)))


def _points(name: str) -> str:
    """` (U+0063 U+0061 …)`, every code point of `name`: what the arm
    expects after a key that prints like the other key of its pair."""
    return " (" + " ".join(f"U+{ord(char):04X}" for char in name) + ")"


def _normalized_name_control(check: CheckRow) -> None:
    """(aaaaaaaa) two names that differ only in how a character is encoded
    are one name, as the file systems golden-census runs on read them, and
    the refusal tells them apart by their code points.

    Loaded in this process: two `[surfaces.<name>]` keys, `café` with `é` as
    one character and as `e` followed by a combining accent, are refused at
    load naming both keys, each followed by its code points, the sentence
    saying they are one name once case and Unicode normalization are folded
    and the `next:` line asking to rename one so the two are different
    names once both are folded; so are U+F900 beside U+8C48, its canonical
    decomposition, which has no accent. Two keys that differ by case alone
    are named without code points. Two `[files]` keys, the first of the
    `café` spellings and the second spelling with `/x.txt` after it, are
    refused as a directory above a file on a filesystem that folds case or
    Unicode normalization, each key followed by its code points, with the
    `next:` line of that refusal. The controls load: `café` beside `cafe`,
    and `row①` beside `row1`, which only a compatibility normalization — one
    no file system golden-census runs on applies to names — would make one.
    """
    label = ("aaaaaaaa  two names that differ only in how a character is "
             "encoded — `é` as one character and as `e` and a combining "
             "accent, and U+F900 beside U+8C48 — are one name: two "
             "`[surfaces.<name>]` keys so spelled are refused at LOAD naming "
             "both keys, each with its code points, as the same name once "
             "case and Unicode normalization are folded, with a `next:` line "
             "asking for two names that are different once both are folded; "
             "a `[files]` key so spelled above another is refused as a "
             "directory above it on a filesystem that folds case or Unicode "
             "normalization, each key with its code points, with its `next:` "
             "line; two keys that differ by case alone are named without code "
             "points; the controls, `café` beside `cafe` and `row①` beside "
             "`row1`, load")
    verdicts: dict[str, str] = {}
    for name, (first, second) in _NORMAL_PAIRS.items():
        with _box("golden-census-normal-") as box:
            path = _scratch(box, manifest_text=_normal_plant(first, second))
            verdicts[name] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")
    first, second = _NORMAL_PAIRS["one name"]
    with _box("golden-census-normal-") as box:
        path = _scratch(box, manifest_text=_STUB_MANIFEST
                        + _files_plant(first, f"{second}/x.txt"))
        files = _printed_refusal(functools.partial(load_manifest, path),
                                 unrefused="LOADED")

    def named(pair: str) -> bool:
        """The pair `pair` was refused naming both keys, each with its code
        points, and the `next:` line whole."""
        one, other = _NORMAL_PAIRS[pair]
        said = verdicts[pair]
        return (said.startswith("REFUSED: ")
                and f"[surfaces.{one}]{_points(one)} and "
                f"[surfaces.{other}]{_points(other)} are the same name once "
                "case and Unicode normalization are folded. " in said
                and said.endswith(
                    f"\n  next: Rename {one!r}{_points(one)} or "
                    f"{other!r}{_points(other)} so the two are different "
                    "names once case and Unicode normalization are folded."))

    one, other = _NORMAL_PAIRS["a case"]
    cased = (verdicts["a case"].startswith("REFUSED: ")
             and f"[surfaces.{one}] and [surfaces.{other}] are the same name "
             "once case and Unicode normalization are folded. "
             in verdicts["a case"]
             and verdicts["a case"].endswith(
                 f"\n  next: Rename {one!r} or {other!r} so the two are "
                 "different names once case and Unicode normalization are "
                 "folded."))
    above = (files.startswith("REFUSED: ")
             and f'[files."{first}"]{_points(first)} is a directory above '
             f'[files."{second}/x.txt"]{_points(f"{second}/x.txt")} on a '
             "filesystem that folds case or Unicode normalization. " in files
             and files.endswith(
                 "\n  next: Rename one key of each pair named above, so that "
                 "no `files` key is a directory above another."))
    loads = (verdicts["an accent"] == "LOADED"
             and verdicts["a compatibility form"] == "LOADED")
    check(label,
          named("one name") and named("an ideograph") and cased and above
          and loads,
          ACTUAL + "; ".join(
              f"{name} -> " + ascii(_one_line(
                  text.partition(".toml: ")[2] or text, 700))
              for name, text in [*verdicts.items(), ("the files keys",
                                                      files)]))


# ------------------------------- a written file over a file the capture owns
#
# The same class as the case-folded pair above, one layer down: there the two
# names collide with each other, here one name collides with a file
# golden-census writes itself. Five plants, four more spelling a reserved
# name in another case — on a case-insensitive file system `.OUT` IS `.out` —
# and the last is the ordinary `.json` written file the rule must leave alone.

#: A `writes` recorded under each of the names a capture owns, and the one it
#: does not. The surface is named `surfaces` in every plant, so the `.json`
#: row IS the index collision and the others are not confounded by the name.
_WRITES_PLANTS = {
    "a stream extension": ("surfaces", "<WORK>/written.out"),
    "no extension at all": ("surfaces", "<WORK>/written"),
    "a skipped surface's file": ("surfaces", "<WORK>/written.skip"),
    "the input's index": ("surfaces", "<WORK>/written.json"),
    "a stream extension in upper case": ("surfaces", "<WORK>/written.OUT"),
    "a stream extension in mixed case": ("surfaces", "<WORK>/written.Exit"),
    "a skipped surface's file in upper case": ("surfaces",
                                               "<WORK>/written.SKIP"),
    "the input's index in upper case": ("surfaces", "<WORK>/written.JSON"),
    "an extension of its own": ("report", "<WORK>/written.json"),
}


def _writes_manifest(surface: str, writes: str) -> str:
    return _STUB_MANIFEST.replace(
        'surfaces = ["help"]', f'surfaces = ["help", "{surface}"]') + f'''
[surfaces.{surface}]
args   = ["--json", "<WRITES>"]
writes = "{writes}"
'''


def _reserved_writes_control(check: CheckRow) -> None:
    """(pppp) a `writes` recorded as a file the capture writes itself.

    The reserved names this arm looks for in the refusal are spelled by hand
    rather than from `core.STREAM_EXTENSIONS`, `SKIP_EXTENSION` and
    `SURFACES_FILE`: the refusal is built from those constants, and an arm
    that only asks the owner cannot notice the owner moved.
    """
    label = ("pppp  a `writes` recorded as one of the five names a capture "
             "writes itself — `<surface>.out`, `<surface>.err`, "
             "`<surface>.exit`, the `<surface>.skip` a skipped row records "
             "its reason in, or the input's `surfaces.json` — is refused at "
             "LOAD naming the surface, the path and the reserved names, a "
             "`writes` with no extension included, since that one is recorded "
             "as `.out` — whatever the case, so `.OUT`, `.Exit`, `.SKIP` and "
             "a `surfaces` surface writing `.JSON` are refused too; a "
             "`writes` with an extension of its own loads")
    verdicts: dict[str, str] = {}
    for why, (surface, writes) in _WRITES_PLANTS.items():
        with _box("golden-census-writes-") as box:
            path = _scratch(box, manifest_text=_writes_manifest(surface, writes))
            try:
                loaded = load_manifest(path).surfaces[surface]
                verdicts[why] = f"loaded, recorded as {surface}.{loaded.extension}"
            except Refusal as refused:
                verdicts[why] = refusal_text(refused)
    reserved = [verdicts[why] for why in ("a stream extension",
                                          "no extension at all",
                                          "a skipped surface's file",
                                          "the input's index")]
    # Each refusal names the surface, the `writes` it read and the file that
    # would be landed on: a sentence that named only the extension would send
    # a reader to the wrong key of a manifest with several written surfaces.
    refused_well = all(
        text.startswith("REFUSED: ") and "[surfaces.surfaces]" in text
        and "written" in text for text in reserved)
    names_streams = all(name in reserved[0] for name in
                        (".out", ".err", ".exit", ".skip"))
    # The `.skip` row's own sentence: it is reserved for what `compare` reads
    # it as, and not because something else is written over.
    names_skip = ("a skipped surface records its reason in" in reserved[2]
                  and "ran on neither side" in reserved[2])
    names_index = "surfaces.json" in reserved[3]
    # The same names in another case, each refused as the name it folds to.
    cased = [verdicts[why] for why in (
        "a stream extension in upper case", "a stream extension in mixed case",
        "a skipped surface's file in upper case",
        "the input's index in upper case")]
    cased_well = all(
        text.startswith("REFUSED: ") and "[surfaces.surfaces]" in text
        and "whatever its case" in text for text in cased)
    loads = verdicts["an extension of its own"] == "loaded, recorded as report.json"

    check(label, refused_well and names_streams and names_skip and names_index
          and cased_well and loads,
          ACTUAL
          + "; ".join(f"{why} -> {_one_line(verdicts[why], DIFFERENCE)}"
                      for why in _WRITES_PLANTS))


# ----------------------------------------------- a surface set inside a list
#
# A set name is an entry of an input's `surfaces` list like any other, and an
# entry that is neither a surface nor a set is refused saying both things it
# could have been. The plants below are one manifest with three surfaces and
# one set over two of them.

_SET_MANIFEST = _subject("sets") + '''
[surface-sets]
pair = ["help", "flag"]

[inputs._subject]
args     = []
surfaces = {surfaces}

[surfaces.help]
args = ["--help"]

[surfaces.flag]
args = ["--flag", "x"]

[surfaces.plain]
args = []
'''


def _surfaces_of(box: str, surfaces: str) -> tuple[str, str]:
    """`(the row keys this manifest resolves to, the refusal it earned)`.

    The refusal comes back as the two lines a READER sees: the `next:` line is
    half of what this arm asserts, and `str(refusal)` is only the first line.
    """
    path = _scratch(box, manifest_text=_SET_MANIFEST.format(surfaces=surfaces))
    try:
        return ", ".join(load_manifest(path).row_keys()), ""
    except Refusal as refused:
        return "", refusal_text(refused)


def _surface_set_control(check: CheckRow) -> None:
    """(gggg) a surface-set name expands IN PLACE, inside the list."""
    label = ("gggg  a `[surface-sets]` name is an entry of an input's "
             "`surfaces` list like any other and expands in place, so "
             "`[\"pair\", \"plain\"]` is the set plus one, in that order, and a "
             "list naming the set and one of its own members records that "
             "surface once. The positive control is an entry that is neither: "
             "it refuses, and the `next:` line names BOTH things an entry can "
             "be")
    cases = {
        "the bare set name": '"pair"',
        "the set inside a list": '["pair", "plain"]',
        "the set after a surface": '["plain", "pair"]',
        "the set beside its own member": '["pair", "help"]',
        "an unknown word": '["pair", "nope"]',
    }
    keys: dict[str, str] = {}
    refusals: dict[str, str] = {}
    for name, spelling in cases.items():
        with _box("golden-census-sets-") as box:
            keys[name], refusals[name] = _surfaces_of(box, spelling)
    unknown = refusals["an unknown word"]
    # Both halves of the sentence and the word that is wrong, asked of the
    # WHOLE refusal — message and `next:` line — because the two-way answer is
    # what the reader of a mistyped entry needs and half of it is in each.
    two_ways = ("[surfaces.<name>] table" in unknown
                and "[surface-sets] entry" in unknown
                and "'nope'" in unknown)
    ok = (keys["the bare set name"] == "_subject/help, _subject/flag"
          and keys["the set inside a list"]
          == "_subject/help, _subject/flag, _subject/plain"
          and keys["the set after a surface"]
          == "_subject/plain, _subject/help, _subject/flag"
          and keys["the set beside its own member"]
          == "_subject/help, _subject/flag"
          and two_ways)
    # The row keys are the manifest's own words and carry no machine; the
    # refusal carries the scratch manifest's path, so it is reported as the
    # verdict it earned and not quoted.
    check(label, ok,
          ACTUAL + "; ".join(
              f"{name} -> {keys[name] or 'REFUSED'}"
              for name in cases)
          + f"; the unknown word's refusal names both kinds and the word "
            f"itself={two_ways}")


# -------------------------------------- a surface set named as a surface
#
# `_resolve_surfaces` reads an entry of an input's `surfaces` list as the set
# when it names one, so a surface of the same name is never run or recorded.

#: The stub manifest with a `[surfaces.p]` table beside a `[surface-sets]`
#: entry over `help` whose name is the `{name}` the caller fills in, and an
#: input listing `p`.
_SET_AS_SURFACE = _STUB_MANIFEST.replace(
    'surfaces = ["help"]', 'surfaces = ["p", "help"]') + '''
[surfaces.p]
args = ["--help", "--flag", "x"]

[surface-sets]
{name} = ["help"]
'''


def _set_as_surface_control(check: CheckRow) -> None:
    """(ooooooo) a `[surface-sets]` name that is also a `[surfaces.<name>]`
    name is refused at load."""
    label = ("ooooooo  a `[surface-sets]` entry that has the name of a "
             "`[surfaces.<name>]` table is refused at LOAD, naming both: an "
             "entry of an input's `surfaces` list is read as the set when it "
             "names one, so the surface of that name would never run and "
             "nothing would say so. The control is a set and a surface with "
             "different names, which loads")
    verdicts: dict[str, str] = {}
    for name, text in (("the shared name", _SET_AS_SURFACE.format(name="p")),
                       ("different names", _SET_AS_SURFACE.format(name="q"))):
        with _box("golden-census-set-as-surface-") as box:
            path = _scratch(box, manifest_text=text)
            verdicts[name] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")
    said = verdicts["the shared name"]
    refused = (said.startswith("REFUSED: ")
               and "[surface-sets] p and [surfaces.p] are one name" in said
               and said.endswith(
                   "\n  next: Rename the set or the surface, so that no "
                   "[surface-sets] entry has the name of a [surfaces.<name>] "
                   "table."))
    check(label, refused and verdicts["different names"] == "LOADED",
          ACTUAL + "set `p` beside surface `p` -> "
          + ("refused at load naming both" if refused
             else _one_line(said, DIFFERENCE))
          + f"; set `q` beside surface `p` -> {verdicts['different names']}")


# ------------------------------------------- `args` on a matrix surface
#
# A matrix row runs `command + input.args + row.args`: nothing reads the
# surface's own `args`.

#: The stub manifest with a `matrix` surface over a one-row include file;
#: `{args}` is the line the caller fills in, or nothing.
_MATRIX_ARGS = _STUB_MANIFEST.replace(
    'surfaces = ["help"]', 'surfaces = ["help", "rows"]') + '''
[surfaces.rows]
kind    = "matrix"
{args}include = "rows.json"
'''


def _matrix_args_control(check: CheckRow) -> None:
    """(uuuuuuu) `args` on a `matrix` surface is refused at load."""
    label = ("uuuuuuu  an `args` key on a `matrix` surface is refused at "
             "LOAD, naming the surface: a matrix row runs the command with "
             "the input's `args` and the row's own, and nothing reads the "
             "surface's, so the key would sit in the manifest doing nothing. "
             "The control is the same surface with no `args`, which loads")
    verdicts: dict[str, str] = {}
    for name, line in (("with args", 'args    = ["--flag", "x"]\n'),
                       ("with no args", "")):
        with _box("golden-census-matrix-args-") as box:
            path = _scratch(box, manifest_text=_MATRIX_ARGS.format(args=line),
                            extra={"rows.json": '[{"label": "one", "args": '
                                   '["--help"]}]\n'})
            verdicts[name] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")
    said = verdicts["with args"]
    refused = (said.startswith("REFUSED: ")
               and "[surfaces.rows]: `args` is not read for a `matrix` "
               "surface." in said
               and said.endswith(
                   "\n  next: Move the arguments to the `args` of the rows "
                   "in the include file, or to the input's `args`, and drop "
                   "the key from this surface."))
    check(label, refused and verdicts["with no args"] == "LOADED",
          ACTUAL + "a matrix surface with `args` -> "
          + ("refused at load naming the surface" if refused
             else _one_line(said, DIFFERENCE))
          + f"; with none -> {verdicts['with no args']}")


# ------------------------------------------------- pins that cannot all hold
#
# A subject's environment is built from the pin rows. A variable pinned twice
# keeps the later value, every `<FIXED-WIDTH-DIR:N>` pin resolves to one
# directory of the first width, and the `fixed-width-dir` control measures
# that one width whichever pin carries it. Three census rows that say
# otherwise are three claims the capture does not keep.

#: A pin row appended to the stub census: `{variable}` pinned to `{value}`,
#: measured by `{control}`.
_PLANTED_PIN = '''
[[input]]
name        = "{name}"
disposition = "pin"
variable    = "{variable}"
value       = "{value}"
finding     = "planted: a pin row for the loader to read"
control     = {control}
'''

_VARY_CONTROL = '{ shape = "vary", surface = "_subject/help", value = "40" }'
_FIXED_CONTROL = '{ shape = "builtin", name = "fixed-width-dir" }'


def _planted_pin(name: str, variable: str, value: str, control: str) -> str:
    return _PLANTED_PIN.format(name=name, variable=variable, value=value,
                               control=control)


def _census_refusal(extra: str) -> str:
    """The stub census with `extra` appended, loaded as a file: the block it
    is refused with, or `LOADED`."""
    with _box("golden-census-pins-") as box:
        _scratch(box, census_text=_STUB_CENSUS + extra)
        return _printed_refusal(
            functools.partial(load_census, os.path.join(box, "census.toml")),
            unrefused="LOADED")


def _repeated_pin_control(check: CheckRow) -> None:
    """(ffffffff) one variable pinned by two rows is refused at load."""
    label = ("ffffffff  two census rows that pin one variable are refused "
             "at LOAD, naming both rows and both values: the environment "
             "holds one value, so the later row replaces the earlier and "
             "the earlier pins nothing, while the controls of both pass. "
             "The control is two rows that pin two variables, which loads")
    verdicts = {
        "one variable twice": _census_refusal(
            _planted_pin("terminal width again", "COLUMNS", "100",
                         _VARY_CONTROL)),
        "two variables": _census_refusal(
            _planted_pin("terminal height", "LINES", "24", _VARY_CONTROL)),
    }
    said = verdicts["one variable twice"]
    refused = (said.startswith("REFUSED: ")
               and ": rows 'terminal width' and 'terminal width again' both "
               "pin COLUMNS, to '80' and to '100'. " in said
               and said.endswith(
                   "\n  next: Write each pinned variable in one row only: "
                   "drop one of the two rows, or pin a different variable "
                   "in one of them."))
    check(label, refused and verdicts["two variables"] == "LOADED",
          ACTUAL + "COLUMNS pinned twice -> "
          + ("refused naming both rows and both values" if refused
             else _one_line(said, DIFFERENCE))
          + f"; COLUMNS and LINES -> {verdicts['two variables']}")


def _fixed_widths_control(check: CheckRow) -> None:
    """(gggggggg) two `<FIXED-WIDTH-DIR:N>` pins of different widths are
    refused at load."""
    label = ("gggggggg  two census pins whose values are "
             "`<FIXED-WIDTH-DIR:N>` of different widths are refused at "
             "LOAD, naming both rows and both values: a capture makes one "
             "fixed-width directory, of the first width, so the other pin "
             "would run at a width its row does not state, while the "
             "controls pass. The control is two such pins of ONE width, "
             "which loads")
    first = _fixed_pin(FIXED_DIR_WIDTH, "a temp path is sliced at a fixed width",
                       "the subject's temp root, and its width")
    verdicts = {
        "two widths": _census_refusal(first + _planted_pin(
            "another temp root", "OTHERDIR", "<FIXED-WIDTH-DIR:40>",
            _FIXED_CONTROL)),
        "one width": _census_refusal(first + _planted_pin(
            "another temp root", "OTHERDIR",
            f"<FIXED-WIDTH-DIR:{FIXED_DIR_WIDTH}>",
            _FIXED_CONTROL)),
    }
    said = verdicts["two widths"]
    refused = (said.startswith("REFUSED: ")
               and ": rows \"the subject's temp root, and its width\" and "
               "'another temp root' pin "
               f"<FIXED-WIDTH-DIR:{FIXED_DIR_WIDTH}> and "
               "<FIXED-WIDTH-DIR:40>. " in said
               and said.endswith(
                   "\n  next: Use one width in every <FIXED-WIDTH-DIR:N> "
                   "pin of this census."))
    check(label, refused and verdicts["one width"] == "LOADED",
          ACTUAL + f"widths {FIXED_DIR_WIDTH} and 40 -> "
          + ("refused naming both rows and both values" if refused
             else _one_line(said, DIFFERENCE))
          + f"; widths {FIXED_DIR_WIDTH} and {FIXED_DIR_WIDTH} -> "
            f"{verdicts['one width']}")


def _fixed_control_control(check: CheckRow) -> None:
    """(hhhhhhhh) a `fixed-width-dir` control on a pin that is not
    `<FIXED-WIDTH-DIR:N>` is refused at load."""
    label = ("hhhhhhhh  a `fixed-width-dir` control on a pin whose value is "
             "not `<FIXED-WIDTH-DIR:N>` is refused at LOAD, naming the row "
             "and its value: the control measures the width of the census's "
             "fixed-width pin, a different row, so it would pass and say "
             "nothing about the pin it sits on. The control is that "
             "control on the fixed-width pin itself, which loads")
    fixed = _fixed_pin(FIXED_DIR_WIDTH, "a temp path is sliced at a fixed width",
                       "the subject's temp root, and its width")
    verdicts = {
        "on a plain value": _census_refusal(fixed + _planted_pin(
            "a plain pin", "LINES", "24", _FIXED_CONTROL)),
        "on the fixed-width pin": _census_refusal(fixed),
    }
    said = verdicts["on a plain value"]
    refused = (said.startswith("REFUSED: ")
               and ": row 'a plain pin': the `fixed-width-dir` control "
               "measures a pin whose value is `<FIXED-WIDTH-DIR:N>`, and "
               "this pin's value is '24'. " in said
               and said.endswith(
                   "\n  next: Give the control only to the pin whose value "
                   "is `<FIXED-WIDTH-DIR:N>`, and give this pin a `vary` or "
                   "`drift` control."))
    check(label, refused and verdicts["on the fixed-width pin"] == "LOADED",
          ACTUAL + "the control on a pin of '24' -> "
          + ("refused naming the row and its value" if refused
             else _one_line(said, DIFFERENCE))
          + f"; on the fixed-width pin -> "
            f"{verdicts['on the fixed-width pin']}")


# --------------------------------------- two input names that are one name
#
# A capture writes one directory per input, `<out>/<input>/`. Two inputs whose
# names differ only as `_surfaces` reads names alike are one directory on the
# file systems golden-census runs on, and the later input's record replaces
# the earlier's.

def _alike_inputs(first: str, second: str) -> str:
    """The stub manifest with two more inputs, named `first` and `second`,
    each recording `help`."""
    return _STUB_MANIFEST + "".join(
        f'\n[inputs."{name}"]\nsurfaces = ["help"]\n'
        for name in (first, second))


def _alike_inputs_control(check: CheckRow) -> None:
    """(iiiiiiii) two `[inputs.<name>]` keys that are one name once case and
    Unicode normalization are folded are refused at load."""
    label = ("iiiiiiii  two `[inputs.<name>]` keys that are the same name "
             "once case and Unicode normalization are folded — `Café` beside "
             "`café`, `é` as one character beside `e` and a combining "
             "accent, U+F900 beside U+8C48 — are refused at LOAD naming both "
             "keys, each with its code points when the two print alike: a "
             "capture writes one directory per input, and on a file system "
             "that folds case or Unicode normalization the later input's "
             "record replaces the earlier's, so a change to the earlier one "
             "compares IDENTICAL. The controls, `café` beside `cafe` and "
             "`row①` beside `row1`, load")
    verdicts: dict[str, str] = {}
    for name, (first, second) in _NORMAL_PAIRS.items():
        with _box("golden-census-alike-inputs-") as box:
            path = _scratch(box, manifest_text=_alike_inputs(first, second))
            verdicts[name] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")

    def named(pair: str) -> bool:
        """`pair` was refused naming both keys, with their code points when
        they print alike, and the `next:` line whole."""
        one, other = _NORMAL_PAIRS[pair]
        points = ("", "") if pair == "a case" else (_points(one),
                                                    _points(other))
        said = verdicts[pair]
        return (said.startswith("REFUSED: ")
                and f"[inputs.{one}]{points[0]} and "
                f"[inputs.{other}]{points[1]} are the same name once case "
                "and Unicode normalization are folded. " in said
                and said.endswith(
                    f"\n  next: Rename {one!r}{points[0]} or "
                    f"{other!r}{points[1]} so the two are different names "
                    "once case and Unicode normalization are folded."))

    refused = [pair for pair in ("one name", "an ideograph", "a case")
               if named(pair)]
    loads = [pair for pair in ("an accent", "a compatibility form")
             if verdicts[pair] == "LOADED"]
    check(label, len(refused) == 3 and len(loads) == 2,
          ACTUAL + "; ".join(
              f"{pair} -> "
              + ("refused naming both keys" if pair in refused
                 else "loaded" if pair in loads
                 else _one_line(verdicts[pair], DIFFERENCE))
              for pair in _NORMAL_PAIRS))


# ------------------------------------------- two counted surfaces, one input
#
# `surfaces.json` holds one `_counts` per INPUT (`capture.Recorder.note_counts`
# sets it by input name), so a second counted surface under an input replaces
# the first's numbers in the golden while the log prints both.

def _two_counters(listing: str, sets: str = "") -> str:
    """The stub manifest with the input `_subject` recording `listing` and
    three surfaces that each write a file and carry a `counter`: `one`,
    `two` and `three`, and `plain`, which writes and counts nothing."""
    body = "".join(
        f'''
[surfaces.{name}]
args    = ["--json", "<WRITES>"]
writes  = "<WORK>/<input>-<surface>.json"
''' + ('counter = ["<PYTHON>", "stub.py"]\n' if name != "plain" else "")
        for name in ("one", "two", "three", "plain"))
    return _STUB_MANIFEST.replace('surfaces = ["help"]',
                                  f"surfaces = {listing}") + body + sets


def _two_counters_control(check: CheckRow) -> None:
    """(kkkkkkkk) an input recording two surfaces that carry a `counter` is
    refused at load."""
    label = ("kkkkkkkk  an input whose surfaces include two with a `counter` "
             "— listed one beside the other, or one of them through a "
             "[surface-sets] entry — is REFUSED when the manifest is read, "
             "naming the input and both surfaces, with `next:` saying to "
             "keep one counted surface per input: `surfaces.json` holds one "
             "`_counts` per input, so the second surface's numbers replaced "
             "the first's in the golden while the log printed both, and a "
             "change in the first counter's numbers compared IDENTICAL. The "
             "controls, one counted surface beside an uncounted one, and the "
             "same two counted surfaces under two inputs, load")
    plants = {
        "two listed": ('["help", "one", "two"]', ""),
        "one through a set": ('["help", "one", "pair"]',
                              '\n[surface-sets]\npair = ["two", "plain"]\n'),
        "three listed": ('["help", "one", "two", "three"]', ""),
        "one counted": ('["help", "one", "plain"]', ""),
    }
    verdicts: dict[str, str] = {}
    for name, (listing, sets) in plants.items():
        with _box("golden-census-two-counters-") as box:
            path = _scratch(box, manifest_text=_two_counters(listing, sets))
            verdicts[name] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")
    with _box("golden-census-two-counters-") as box:
        path = _scratch(box, manifest_text=_two_counters(
            '["help", "one"]') + '\n[inputs.other]\nsurfaces = ["one"]\n')
        verdicts["under two inputs"] = _printed_refusal(
            functools.partial(load_manifest, path), unrefused="LOADED")
    refused = {
        "two listed": "`one` and `two`",
        "one through a set": "`one` and `two`",
        "three listed": "`one`, `two` and `three`",
    }
    named = [name for name, surfaces in refused.items()
             if verdicts[name].startswith("REFUSED: ")
             and "[inputs._subject] names " in verdicts[name]
             and f"with a `counter`, {surfaces}, " in verdicts[name]
             and "one `_counts` per input" in verdicts[name]
             and "\n  next: Keep one counted surface per input" in verdicts[name]]
    loads = [name for name in ("one counted", "under two inputs")
             if verdicts[name] == "LOADED"]
    check(label, len(named) == 3 and len(loads) == 2,
          ACTUAL + "; ".join(
              f"{name} -> "
              + ("refused naming the input and the surfaces" if name in named
                 else "loaded" if name in loads
                 else _one_line(verdicts[name], DIFFERENCE))
              for name in plants | {"under two inputs": ("", "")}))


# ------------------------------------------------ <HERE> in [subject] command
#
# The token's third home, and the one that makes a manifest committed beside a
# runner portable: without it the only spelling of an entry point that is not
# under `root` is this machine's absolute path.

#: The runner this arm's manifest names. It sits BESIDE THE MANIFEST and
#: nowhere else, and its `prog` is the marker: what reaches the golden says
#: which file golden-census ran. Otherwise the stub subject, so the census's
#: COLUMNS pin still has the wrapped help text its control varies.
_HERE_COMMAND_RUNNER = _STUB_SUBJECT.replace(
    'prog="stub"', 'prog="beside-the-manifest"').replace(
    'parser.parse_args()\n',
    'flag = parser.parse_args().flag\n'
    'if flag:\n'
    '    open(flag, "w", encoding="utf-8").write("written\\n")\n')

#: A manifest whose `command` opens with `<HERE>` and whose `root` is a
#: DIFFERENT, empty directory: no resolution but the token's can find the
#: runner, so a green row cannot be a relative path that happened to work.
#: Its one setup step and the counter of the file its second surface writes
#: each copy that runner, named by `<HERE>`, to `kept.txt`, a RELATIVE name
#: that a file beside the manifest also carries: both run in `<WORK>`, so
#: the copy lands there and the file beside the manifest is left as it was.
_HERE_COMMAND_MANIFEST = _STUB_MANIFEST.replace(
    'root    = "."', 'root    = "../elsewhere"').replace(
    'command = ["<PYTHON>", "stub.py"]',
    'command = ["<PYTHON>", "<HERE>/runner.py"]').replace(
    'args = ["--help"]', 'args  = ["--help"]\nneeds = ["copy"]').replace(
    'surfaces = ["help"]', 'surfaces = ["help", "written"]') + '''
[surfaces.written]
args    = ["--flag", "<WRITES>"]
writes  = "<WORK>/written.txt"
counter = ["<PYTHON>", "-c",
           "import shutil, sys; shutil.copy(*sys.argv[1:]); print('{}')",
           "<HERE>/runner.py", "kept.txt"]

[[setup]]
name    = "copy"
command = ["<PYTHON>", "-c", "import shutil, sys; shutil.copy(*sys.argv[1:])",
           "<HERE>/runner.py", "kept.txt"]
'''

#: What the file beside the manifest that shares the setup step's and the
#: counter's relative argument reads, before the capture and after it.
_HERE_KEPT = "the reader's own\n"

#: The positive control: the same token over a file that is not there. The
#: path is known before anything runs, so this is a refusal at load and not an
#: interpreter's own error mid-capture.
_HERE_MISSING_MANIFEST = _STUB_MANIFEST.replace(
    'command = ["<PYTHON>", "stub.py"]',
    'command = ["<PYTHON>", "<HERE>/missing.py"]')

#: The same control in the two other argvs that may spell `<HERE>`: a
#: `[[setup]]` command and a `counter`, each refused at load by its own key.
_HERE_MISSING_ELSEWHERE = {
    "[[setup]] step command": _STUB_MANIFEST + '''
[[setup]]
name    = "step"
command = ["<PYTHON>", "<HERE>/missing.py"]
''',
    "[surfaces.help] counter": _STUB_MANIFEST.replace(
        'args = ["--help"]',
        'args    = ["--help", "<WRITES>"]\nwrites  = "<WORK>/help.json"\n'
        'counter = ["<PYTHON>", "<HERE>/missing.py"]'),
}


def _here_command_control(check: CheckRow) -> None:
    """(dddd) `<HERE>` resolves against the manifest; nothing else does."""
    label = ("dddd  `<HERE>` in `[subject] command` is the directory the "
             "MANIFEST sits in: a command spelling `<HERE>/runner.py`, under a "
             "`root` that is a different and empty directory, runs the runner "
             "beside the manifest and that runner's own name reaches the "
             "golden; and a `[[setup]]` step and a `counter` each copying "
             "`<HERE>/runner.py` to `kept.txt`, a relative name a file beside "
             "the manifest also carries, copy it into <WORK> and leave that "
             "file as it was. "
             "The positive control is the same command naming a file that is "
             "not there, refused at LOAD — before the capture — with the "
             "resolved path in the sentence, and so is a `[[setup]]` command "
             "or a `counter` naming one, each by its own key")
    with _box("golden-census-herecmd-") as box:
        beside = os.path.join(box, "beside")
        elsewhere = os.path.join(box, "elsewhere")
        control = os.path.join(box, "control")
        # `_scratch` makes `beside` and `control`; `elsewhere` is the
        # manifest's `root`, which it does not make.
        os.makedirs(elsewhere)
        path = _scratch(beside, manifest_text=_HERE_COMMAND_MANIFEST,
                        census_text=_STUB_CENSUS + _STUB_WORK_FOLD,
                        extra={"runner.py": _HERE_COMMAND_RUNNER,
                               "kept.txt": _HERE_KEPT})
        out_dir = os.path.join(box, "out")
        log = io.StringIO()
        code = capture(load_manifest(path), out_dir, log)
        recorded = read_capture(out_dir, "--out") if code == 0 else {}
        printed = recorded.get(os.path.join("_subject", "help.out"), "")
        kept = pathlib.Path(os.path.join(beside, "kept.txt")).read_text(
            encoding="utf-8")

        _scratch(control, manifest_text=_HERE_MISSING_MANIFEST)
        refused = _refused_by(functools.partial(
            load_manifest, os.path.join(control, "manifest.toml")))
        # The VERDICTS, never the paths: this box sits under the machine's
        # temp root, and a detail line quoting it would print a directory
        # whose width is this machine's.
        names_path = ("missing.py" in refused and control in refused)
        elsewhere_said = {}
        for key, text in _HERE_MISSING_ELSEWHERE.items():
            _scratch(control, manifest_text=text)
            said = _printed_refusal(functools.partial(
                load_manifest, os.path.join(control, "manifest.toml")))
            elsewhere_said[key] = (
                f"{key} names {os.path.join(control, 'missing.py')}" in said
                and "path under <WORK>, where the command runs" in said)
    marker = "beside-the-manifest" in printed
    left = kept == _HERE_KEPT
    check(label, code == 0 and marker and left and names_path
          and all(elsewhere_said.values()),
          f"{ACTUAL}the capture exited {code}, the runner's own name reached "
          f"the golden={marker}, the file beside the manifest the setup "
          f"step's and the counter's relative argument share a name with "
          f"was left as it was={left}; the missing runner -> "
          + ("refused at load naming the resolved path" if names_path
             else _one_line(refused, DIFFERENCE))
          + "; refused at load by its own key, naming the resolved path: "
          + ", ".join(f"{key}={said}" for key, said in elsewhere_said.items()))


#: (ccc) a program this machine does not have, named as a subject's whole
#: command. It is the first thing an `init`-first reader meets when the COMMAND
#: hole is filled with a guess, and unguarded it is a Python traceback out of
#: `run_subject`, exit 1, with an empty `--out` left behind.
_ABSENT_PROGRAM = "no-such-program-ccc"

_ABSENT_MANIFEST = _STUB_MANIFEST.replace(
    'command = ["<PYTHON>", "stub.py"]', f'command = ["{_ABSENT_PROGRAM}"]')

#: The SAME fault in a `census state` row. A state block is a diagnostic —
#: what this machine has is exactly what the reader is looking at — so the
#: line names the fault in parentheses and the command does not refuse. One
#: sentence, two line shapes.
_ABSENT_STATE_CENSUS = _STUB_CENSUS + f'''
[[input]]
name        = "a tool this machine does not have"
disposition = "state"
finding     = "planted: the state block reports what is here, refusing nothing"
commands    = [["{_ABSENT_PROGRAM}", "--version"]]
'''


def _absent_program_control(check: CheckRow) -> None:
    """(ccc) a child that would not launch is ONE sentence and exit 2.

    Four things in one row, because they are one decision: the refusal names
    the subject, it carries a `next:`, nothing of Python's is printed, and the
    `--out` directory this command made is gone. The state half is the OTHER
    verdict the same fault earns, and it must not have become a refusal: a
    diagnostic that refuses tells the reader nothing about the machine.
    """
    label = ("ccc  a subject that will not launch — the COMMAND hole filled "
             "with a program that is not there — is ONE refusal naming the "
             "subject, with a next: line and exit 2, never the Python "
             "traceback and exit 1 it was; and the `--out` directory this "
             "capture made is removed, because nothing was written into it. "
             "The SAME fault in a `census state` row stays a diagnostic line "
             "naming it in parentheses and saying the refusal's `next:` after "
             "them, which is what a block that reports what this machine has "
             "owes the reader")
    verdict, left, state_line = "", True, ""
    with _box("golden-census-absent-") as box:
        path = _scratch(box, manifest_text=_ABSENT_MANIFEST,
                        census_text=_ABSENT_STATE_CENSUS)
        manifest = load_manifest(path)
        out_dir = os.path.join(box, "out")
        log = io.StringIO()
        try:
            verdict = f"exit {capture(manifest, out_dir, log)}, no refusal"
        except Refusal as refused:
            verdict = refusal_text(refused)
        except Exception as exc:          # a traceback IS the defect this row
            if isinstance(exc, UNREPORTABLE):   # is about, so it is reported
                raise
            verdict = f"raised {type(exc).__name__}: {exc}"
        left = os.path.exists(out_dir)
        roots = Roots(root=box, work=box, clone=None, fixed=None)
        census = manifest.census
        state_log = io.StringIO()
        try:
            state(census, roots, build_env(census, roots), state_log)
        except Exception as exc:          # reported, as the capture's is
            if isinstance(exc, UNREPORTABLE):
                raise
            state_log.write(f"raised {type(exc).__name__}: {exc}")
        state_line = _one_line(state_log.getvalue(), 200,
                               needles=(_ABSENT_PROGRAM,))
    check(label,
          verdict.startswith("REFUSED: the subject would not run: "
                             "FileNotFoundError")
          and "\n  next: " in verdict and not left
          and state_line.startswith(f"{_ABSENT_PROGRAM} --version -> "
                                    "(FileNotFoundError:")
          and ") — next: " in state_line,
          f"{ACTUAL}capture -> {_one_line(verdict, 150)!r}; --out left "
          f"behind={left}; the state row -> {state_line[:110]!r}")


# ------------------- a state row's expansion refuses, per command (mmmm)
#
# A placeholder a census does not know is refused at LOAD, before anything
# runs. One it DOES know and has no value for in this run — `<CLONE>` outside
# a mutants run — can only be found when the row is expanded, and a state
# block is the one place that is a diagnostic rather than a fault: the block
# exists to say what this machine has, so one command that cannot be spelled
# costs its own line and nothing else.

#: The token: a name of the census's own vocabulary, so the row LOADS, and
#: without a value in a run that makes no clone, so the expansion refuses.
_STATE_TOKEN = "<CLONE>"

#: Three commands in one row. The first and the third are there to be read
#: after the second: a catch that took the row with it would lose the third,
#: and one that took the block would lose both.
_STATE_EXPAND_CENSUS = _STUB_CENSUS + f'''
[[input]]
name        = "a tool under a directory this run never made"
disposition = "state"
finding     = "planted: one command of a state row cannot be spelled, and the block still prints"
commands    = [["<PYTHON>", "--version"],
                ["{_STATE_TOKEN}/tool", "--version"],
                ["<PYTHON>", "-c", "print('after')"]]
'''


def _state_expand_control(check: CheckRow) -> None:
    """(mmmm) a `state` row's expansion refusal is caught per command.

    The control is the SAME expansion made outside the line, which raises the
    `Refusal` the line catches: a green row over a token that turned out to
    expand cleanly would say nothing at all.
    """
    label = ("mmmm  a `state` row whose command spells a token with no value "
             "in this run — a name the census defines, for a directory this "
             "run never made — costs that command its own line in the block "
             "and nothing more: the commands before and after it print "
             "theirs, the line names the row and the token and says the "
             "refusal's `next:` after them, and the command "
             "does not refuse; the SAME expansion made outside the line "
             "raises the Refusal the line catches, which is how this row is "
             "known to be able to go red")
    with _box("golden-census-state-expand-") as box:
        path = _scratch(box, manifest_text=_STUB_MANIFEST,
                        census_text=_STATE_EXPAND_CENSUS)
        census = load_manifest(path).census
        roots = Roots(root=box, work=box, clone=None, fixed=None)
        log = io.StringIO()
        try:
            state(census, roots, build_env(census, roots), log)
            verdict = "printed, nothing refused"
        except Refusal as refused:
            verdict = refusal_text(refused)
        except Exception as exc:          # a traceback IS the defect this row
            if isinstance(exc, UNREPORTABLE):   # is about, so it is reported
                raise
            verdict = f"raised {type(exc).__name__}: {exc}"
        try:
            _env_context(roots, census.directory or None).expand(
                f"{_STATE_TOKEN}/tool", "the control")
            control = "expanded — the token HAS a value in this run"
        except Refusal as refused:
            control = f"Refusal: {_one_line(str(refused), 70)}"
    said = [line.strip() for line in log.getvalue().splitlines()]
    refused_line = next((line for line in said
                         if line.startswith(f"{_STATE_TOKEN}/tool ")), "")
    after = any(line.endswith("-> after") for line in said)
    check(label,
          verdict == "printed, nothing refused" and after
          and any(line.startswith("<PYTHON> --version ->") for line in said)
          and _STATE_TOKEN in refused_line
          and "has no value in this run" in refused_line
          and " — next: " in refused_line
          and control.startswith("Refusal: "),
          f"{ACTUAL}the block {verdict!r}, {len(said)} line(s); the refused "
          f"command's line read {_one_line(refused_line, 150)!r}; the command "
          f"after it printed={after}; the control — the same expansion "
          f"outside the line — {control!r}")


#: (ddd) the fifth loader: a matrix surface's GENERATED include file, read
#: through the three seams the other four loaders have — one read, the hole
#: check, the placeholder check. Without them an include row spelling `<TMP>`
#: loads and refuses mid-capture from inside the thread pool, and one spelling
#: `<<HOLE:ARG>>` is read as an unknown PLACEHOLDER and refused with the wrong
#: sentence about the wrong rule.
_MATRIX_MANIFEST = _subject("stub") + '''
[inputs._subject]
args     = []
surfaces = ["flags"]

[surfaces.flags]
kind    = "matrix"
include = "rows.toml"
'''

#: The four planted include files, and the clean one every clause is measured
#: against. The bytes one: a row file that is not UTF-8 is otherwise a
#: `UnicodeDecodeError` traceback out of the parser.
_ROWS_CLEAN = '[[rows]]\nlabel = "one"\nargs  = ["--flag", "x"]\n'
_ROWS_HOLE = '[[rows]]\nlabel = "one"\nargs  = ["<<HOLE:ARG>>"]\n'
_ROWS_TOKEN = '[[rows]]\nlabel = "one"\nargs  = ["<TMP>/x"]\n'
_ROWS_BYTES = b'[[rows]]\nlabel = "one"\nargs  = ["\xff\xfe"]\n'

#: The other census string a loader must check: the fixtures directory. A
#: `dir` of `<TMP>/fx` otherwise becomes a path with the token still in it.
_FIXTURES_TOKEN = _STUB_CENSUS + '\n[fixtures]\ndir = "<TMP>/fx"\n'
_FIXTURES_CLEAN = _STUB_CENSUS + '\n[fixtures]\ndir = "fx"\n'
#: The token again, spelling a directory nobody made: the placeholder is the
#: refusal, because the loader checks the string before it asks the file
#: system.
_FIXTURES_TOKEN_ABSENT = _STUB_CENSUS + '\n[fixtures]\ndir = "<TMP>/gone"\n'
#: `<HERE>` in the directory, the one token with a value when the census is
#: read: it is the census's own directory, beside a directory planted under
#: the token's literal name that a `dir` joined as written would load.
_FIXTURES_HERE = _STUB_CENSUS + '\n[fixtures]\ndir = "<HERE>/fx"\n'
#: `<ROOT>`, `<WORK>`, `<CLONE>` and `<PYTHON>` in the directory, the four
#: tokens of the census's vocabulary that `dir` does not take: each refused
#: in `dir`'s own sentence, beside a directory planted under its literal
#: name, so the refusal can come from nothing but the token check.
_FIXTURES_ROOT = _STUB_CENSUS + '\n[fixtures]\ndir = "<ROOT>/fx"\n'
_FIXTURES_WORK = _STUB_CENSUS + '\n[fixtures]\ndir = "<WORK>/fx"\n'
_FIXTURES_CLONE = _STUB_CENSUS + '\n[fixtures]\ndir = "<CLONE>/fx"\n'
_FIXTURES_PYTHON = _STUB_CENSUS + '\n[fixtures]\ndir = "<PYTHON>/fx"\n'
#: The block `[fixtures] dir` is refused with when it spells any placeholder
#: but `<HERE>`, whole, as `core.refusal_text` prints it, with the census's
#: path and the value it was given filled in by the arm.
_FIXTURES_REFUSED = (
    "REFUSED: census {census}: [fixtures] dir takes a path, relative to this "
    "census's directory or absolute, in which <HERE> is the one placeholder "
    "it may spell; it was given {given!r}.\n"
    "  next: Spell `dir` relative to this census's directory, begin it with "
    "<HERE>, or give an absolute path.")

#: A census that is not UTF-8 at all. Decoded inside the parse it is a
#: `UnicodeDecodeError` traceback out of `tomllib.load`, in every one of the
#: four loaders, because `UnicodeDecodeError` is not a `TOMLDecodeError`; read
#: first and decoded by `core._read_source`, it is one sentence.
_CENSUS_BYTES = b'[environment]\ninherit = false\nname = "\xff\xfe"\n'


def _include_loader_control(check: CheckRow) -> None:
    """(ddd) the fifth loader's three seams, and the census key that had none.

    Every clause is a planted file beside a clean sibling that must LOAD, so
    no clause can pass by refusing everything.
    """
    label = ("ddd  the matrix surface's generated include file is read "
             "through the same seam the other four loaders use: a row "
             "spelling <<HOLE:ARG>> is refused at LOAD naming the hole, the "
             "surface row and the file — not mid-capture as an unknown "
             "placeholder — a row spelling <TMP> is refused naming the token "
             "and the row, a row file that is not UTF-8 is a sentence rather "
             "than a traceback, a census `[fixtures] dir` spelling <TMP> "
             "— whether or not it names a directory — <ROOT>, <WORK>, <CLONE> "
             "or <PYTHON> is refused when the census is read in the one "
             "sentence that names the key, what it takes and the value it "
             "was given, "
             "while one spelling <HERE> loads as the census's own directory "
             "and never as a directory of that literal name, "
             "and a census file that is not UTF-8 at all is a sentence, "
             "never a UnicodeDecodeError traceback from inside the parser; "
             "each "
             "beside a clean sibling that loads, so no clause passes by "
             "refusing everything")
    said: dict[str, str] = {}
    with _box("golden-census-fifth-") as box:
        # No pin: the stub's `vary` control names `_subject/help`, which
        # this matrix-only manifest does not record.
        path = _scratch(box, manifest_text=_MATRIX_MANIFEST,
                        census_text=_STUB_WORK_CENSUS)
        rows_path = os.path.join(box, "rows.toml")

        def load_with(text: str) -> str:
            pathlib.Path(rows_path).write_text(text, encoding="utf-8")
            return _refused_by(lambda: load_manifest(path))

        said["a hole in an include row"] = load_with(_ROWS_HOLE)
        said["a placeholder in an include row"] = load_with(_ROWS_TOKEN)
        pathlib.Path(rows_path).write_bytes(_ROWS_BYTES)
        said["an include file that is not UTF-8"] = _refused_by(
            lambda: load_manifest(path))
        said["a clean include file"] = load_with(_ROWS_CLEAN)

        census_path = os.path.join(box, "fixtures.toml")
        # The clean sibling's `dir = "fx"` must name a directory. So must
        # the token's `<TMP>/fx`, read literally: then the directory check
        # passes and only the placeholder check can refuse it.
        os.makedirs(os.path.join(box, "fx"))
        os.makedirs(os.path.join(box, "<TMP>", "fx"))
        os.makedirs(os.path.join(box, "<HERE>", "fx"))
        os.makedirs(os.path.join(box, "<ROOT>", "fx"))
        os.makedirs(os.path.join(box, "<WORK>", "fx"))
        os.makedirs(os.path.join(box, "<CLONE>", "fx"))
        os.makedirs(os.path.join(box, "<PYTHON>", "fx"))

        def census_with(text: str) -> str:
            # The census's path made `<census>`, so the detail shows the
            # sentence and not the box it was planted in.
            pathlib.Path(census_path).write_text(text, encoding="utf-8")
            return _printed_refusal(lambda: load_census(census_path)).replace(
                census_path, "<census>")

        said["a placeholder in [fixtures] dir"] = census_with(_FIXTURES_TOKEN)
        said["a placeholder in [fixtures] dir, no such directory"] = (
            census_with(_FIXTURES_TOKEN_ABSENT))
        said["a clean [fixtures] dir"] = census_with(_FIXTURES_CLEAN)
        said["<ROOT> in [fixtures] dir"] = census_with(_FIXTURES_ROOT)
        said["<WORK> in [fixtures] dir"] = census_with(_FIXTURES_WORK)
        said["<CLONE> in [fixtures] dir"] = census_with(_FIXTURES_CLONE)
        said["<PYTHON> in [fixtures] dir"] = census_with(_FIXTURES_PYTHON)
        pathlib.Path(census_path).write_text(_FIXTURES_HERE, encoding="utf-8")
        here: list[str] = []
        said["<HERE> in [fixtures] dir"] = _refused_by(
            lambda: here.append(load_census(census_path).fixtures or ""))
        # Which of the two directories loaded: `fx` beside the census, or
        # `<HERE>/fx`, the token's literal name.
        here_names = (os.path.relpath(here[0], box) if here and here[0]
                      else "nothing")
        pathlib.Path(census_path).write_bytes(_CENSUS_BYTES)
        said["a census file that is not UTF-8"] = _refused_by(
            lambda: load_census(census_path))

    wanted = {
        "a hole in an include row": ("<<HOLE:ARG>>", "[surfaces.flags]",
                                     "include", "rows.toml"),
        "a placeholder in an include row": ("<TMP>", "include row args"),
        "an include file that is not UTF-8": ("is not UTF-8 text",
                                              "UnicodeDecodeError"),
        "a census file that is not UTF-8": ("is not UTF-8 text",
                                            "UnicodeDecodeError"),
    }
    # `dir`'s refusal, whole, for each value it was given; the detail
    # quotes one that differs whole, uncut, so the clause it breaks shows.
    refused_dir = {
        key: _FIXTURES_REFUSED.format(census="<census>", given=given)
        for key, given in (
            ("a placeholder in [fixtures] dir", "<TMP>/fx"),
            ("a placeholder in [fixtures] dir, no such directory",
             "<TMP>/gone"),
            ("<ROOT> in [fixtures] dir", "<ROOT>/fx"),
            ("<WORK> in [fixtures] dir", "<WORK>/fx"),
            ("<CLONE> in [fixtures] dir", "<CLONE>/fx"),
            ("<PYTHON> in [fixtures] dir", "<PYTHON>/fx"))}
    ok = (all(all(needle in said[key] for needle in needles)
              for key, needles in wanted.items())
          and all(said[key] == whole for key, whole in refused_dir.items())
          and said["a clean include file"] == "NOT REFUSED"
          and said["a clean [fixtures] dir"] == "NOT REFUSED"
          and said["<HERE> in [fixtures] dir"] == "NOT REFUSED"
          and here_names == "fx")
    check(label, ok,
          ACTUAL + "; ".join(
              f"{key} -> "
              + ("as the label says" if text == refused_dir[key]
                 else repr(text)) if key in refused_dir
              else f"{key} -> {_one_line(text, 100)!r}"
              for key, text in said.items())
          + f"; the <HERE> directory names <box>/{here_names}")


#: (jjj) a subject told where to write through a VARIABLE rather than through
#: an argument — the shape every Swift test runner has, because a test binary's
#: own argv belongs to the test tool. Without the token valued in `env`, such a
#: subject has to spell the path twice — in `env` and again in `writes` — and
#: keep the two in agreement by hand.
_ENV_WRITES_SUBJECT = '''\
import os
import sys

out = os.environ.get("GOLDEN_CENSUS_OUT")
if not out:
    sys.stderr.write("GOLDEN_CENSUS_OUT is unset\\n")
    sys.exit(2)
with open(out, "w", encoding="utf-8", newline="\\n") as handle:
    handle.write("written through the variable\\n")
'''

_ENV_WRITES_MANIFEST = _subject("envwrites") + '''
[inputs._subject]
args     = []
surfaces = ["out"]

[surfaces.out]
args   = []
env    = { GOLDEN_CENSUS_OUT = "<WRITES>" }
writes = "<WORK>/<input>-<surface>.txt"
'''

#: The half that must STAY red: the same token, in the same key, on a surface
#: that declares no `writes` at all. There is no path to value it from, and a
#: change that valued `<WRITES>` everywhere rather than from the surface's own
#: `writes` would turn this green and go unnoticed.
_ENV_NO_WRITES_MANIFEST = _ENV_WRITES_MANIFEST.replace(
    'writes = "<WORK>/<input>-<surface>.txt"\n', "")


def _writes_in_env_control(check: CheckRow) -> None:
    """(jjj) `<WRITES>` is valued in a surface's `env` exactly as in its `args`.

    Two halves and they are one rule: the token names THIS surface's written
    path, so a surface that has one records the file the subject wrote to the
    variable, and a surface that has none is refused by the sentence that says
    the token has no value in this run.
    """
    label = ("jjj  `<WRITES>` is valued in a surface's `env` exactly as it is "
             "in its `args`: a subject told where to write through "
             "`GOLDEN_CENSUS_OUT=<WRITES>` — the shape a test runner has, whose own "
             "argv belongs to the test tool — captures the file it wrote, "
             "so the path is spelled once and never kept in agreement by hand; "
             "and the SAME token on a surface "
             "that declares no `writes` is still REFUSED naming the row, "
             "because there is no path to value it from")
    with _box("golden-census-envwrites-") as box:
        green_box = os.path.join(box, "green")
        path = _scratch(green_box, manifest_text=_ENV_WRITES_MANIFEST,
                        census_text=_STUB_WORK_CENSUS,
                        extra={"stub.py": _ENV_WRITES_SUBJECT})
        log = io.StringIO()
        # Caught here rather than left to propagate: a refusal out of a
        # control ends the whole self-check at this row, and the arm's red has
        # to be a FAIL row with the sentence in it so the arms after it still
        # run.
        code, green = -1, "NOT REFUSED"
        try:
            code = capture(load_manifest(path), os.path.join(box, "out"), log)
        except Refusal as env_refusal:
            green = str(env_refusal)
        recorded = (read_capture(os.path.join(box, "out"), "--out")
                    if code == 0 else {})

        red_box = os.path.join(box, "red")
        red_path = _scratch(red_box, manifest_text=_ENV_NO_WRITES_MANIFEST,
                            census_text=_STUB_WORK_CENSUS,
                            extra={"stub.py": _ENV_WRITES_SUBJECT})
        red_log = io.StringIO()
        refused = _refused_by(lambda: capture(load_manifest(red_path),
                                              os.path.join(box, "red-out"),
                                              red_log))
    written = recorded.get("_subject/out.txt", "")
    exit_row = recorded.get("_subject/out.exit", "")
    still_red = ("<WRITES> has no value in this run" in refused
                 and "[surfaces.out] env" in refused)
    check(label,
          code == 0 and written == "written through the variable\n"
          and exit_row.strip() == "0" and still_red,
          f"{ACTUAL}the env row -> capture exit {code} "
          f"({_one_line(green, 100)}), _subject/out.exit "
          f"{exit_row.strip()!r}, _subject/out.txt {written!r}; the "
          "no-`writes` surface -> " + _one_line(refused, 140),
          next="Read `run.row_start`: the written path is expanded "
               "BEFORE the `env` block so `context(roots, writes)` can value "
               "the token, and a surface with no `writes` leaves it None.")


#: (kkk) `<PYTHON>` folded by ONE decider. `census`'s state line and its
#: `command` precondition line join the EXPANDED argv, whose argv[0] is
#: `sys.executable` — this machine's absolute interpreter path — so without the
#: fold a census naming `<PYTHON>` prints the machine into every record of a
#: run. The planted census carries one of each line, and the arm asks a third
#: thing at the same time: that `probe`'s banner, which owns no copy of the
#: fold, still reads `<PYTHON>`. It passes `HOME` through and lists it in a
#: `state` row, so the arm can plant a home and read the variable's line; a
#: third `state` row's command prints that home after a hundred characters of
#: its own, so the arm reads the command's line for the home folded and for the
#: fold made before the cut.
_PYTHON_STATE_CENSUS = _STUB_CENSUS.replace(
    'passthrough = ["PATH"]', 'passthrough = ["PATH", "HOME"]') + '''
[[input]]
name        = "the home directory"
disposition = "state"
finding     = "planted: the state block prints a variable's value, and a home is a machine's"
variables   = ["HOME"]

[[input]]
name        = "the interpreter this control names"
disposition = "state"
finding     = "planted: the state line joins the EXPANDED argv, so <PYTHON> leaves it unfolded"
commands    = [["<PYTHON>", "--version"]]

[[input]]
name        = "the interpreter answers"
disposition = "precondition"
check       = "command"
expect      = "empty stdout"
finding     = "planted: the [OK] line joins the same EXPANDED argv, and is the second site"
command     = ["<PYTHON>", "-c", "pass"]

[[input]]
name        = "the home directory, printed by a command"
disposition = "state"
finding     = "planted: a state command's first line is folded, then cut, and carries the home"
commands    = [["<PYTHON>", "-c", "import os; print('x' * 100 + os.environ['HOME'])"]]
'''

#: (kkk) a `command` precondition whose program is not there: `launch`'s
#: refusal names the EXPANDED argv[0] twice, in its own words and in the
#: operating system's, and the subject root folds to `<REPO>` in both.
_UNSTARTED_CENSUS = _STUB_CENSUS + _STUB_ROOT_FOLD + '''
[[input]]
name        = "a program that is not there"
disposition = "precondition"
check       = "command"
expect      = "exit 0"
finding     = "planted: the refusal names the program by its expanded path"
command     = ["<ROOT>/no-such-program"]
'''


def _python_fold_control(check: CheckRow) -> None:
    """(kkk) the interpreter is folded to `<PYTHON>` by ONE decider, for every
    line golden-census prints.

    Three lines, one rule. `census`'s state row and its `command` precondition
    row print `' '.join(argv)` AFTER the placeholder table expanded it, so
    without a fold in `own_log` the token leaves the log as an absolute path;
    `probe.banner` would fold the two interpreter forms itself, two lines above
    the `own_log` call that folds everything else. The fold belongs to
    `own_log`, and this arm holds both ends of that: the two census lines carry
    the token and the banner does not lose it.

    `banner` directly rather than a whole `probe`: the arm runs under a
    PRIVATE temp root inside `_made_under`, which is a directory under this
    machine's root and therefore too deep to host the fixed-width `TMPDIR` a
    probe makes. `banner` makes no directory and is the exact construct the
    change edits; arm `rr` holds the end-to-end claim about a real probe's
    block.
    """
    label = ("kkk  `<PYTHON>` is folded by ONE decider, so no line the "
             "golden-census prints names this machine's interpreter: a "
             "census "
             "`state` row and a `command` precondition row both join the "
             "EXPANDED argv — the token never leaves as an absolute path for a "
             "reader to fold by hand — and `probe`'s banner, "
             "which folded the two interpreter forms itself, still reads "
             "`<PYTHON>` now that the fold belongs to `census.own_log`; "
             "and a `state` row's variable AND a `state` command's first "
             "line are folded as a refusal's block folds one, the fold "
             "made before the line is cut, so a planted `HOME` prints "
             "`<HOME>` in both; and the refusal of a `command` "
             "precondition whose program will not start names it folded, "
             "`<REPO>` both times and the subject root never, and keeps "
             "its `next:`")

    def body() -> tuple[str, str, str]:
        with _box("golden-census-python-") as box:
            path = _scratch(box, census_text=_PYTHON_STATE_CENSUS)
            manifest = load_manifest(path)
            log = io.StringIO()
            # A home of the arm's own, so the `HOME` line is judged on input
            # it was given and not on the reader's.
            with _env_as({"HOME": os.path.join(box, "home")}):
                run_census(manifest, log)
            printed = banner([sys.executable, "-c", "pass"], manifest.census,
                             Roots(root=box, work=box, clone=None,
                                   fixed=None), os.getcwd())
            unstarted = load_manifest(_scratch(
                os.path.join(box, "unstarted"), census_text=_UNSTARTED_CENSUS))
            refused = _printed_refusal(
                lambda: run_census(unstarted, io.StringIO())).replace(
                    box, "<box>")
            return log.getvalue(), printed, refused

    (log_text, printed, told), _left = _made_under(temp_base(), body)
    # The refusal as it prints: its sentence, then the `next:` line `launch`
    # gave it, which the fold must carry over.
    refused, _newline, rest = told.partition("\n")
    refused_next = next((one for one in rest.splitlines()
                         if one.startswith("  next: ")), "")
    lines = log_text.splitlines()
    state_line = next((one for one in lines if " --version -> " in one), "")
    ok_line = next((one for one in lines if one.startswith("    [OK] ")), "")
    home_line = next((one for one in lines if one.startswith("    HOME = ")),
                     "")
    printed_line = next((one for one in lines
                         if one.startswith("    <PYTHON> -c import os; ")), "")
    forms = path_forms(sys.executable)
    # Lengths, never the paths: a detail line that quoted an unfolded form to
    # prove it was there would print the machine this row exists to keep out
    # of the log. The two census lines above are quoted whole because at green
    # they carry the token and nothing else.
    unfolded = sorted({len(one) for one in forms
                       if one in log_text or one in printed})
    check(label,
          state_line.startswith("    <PYTHON> --version -> ")
          and "<PYTHON> -c pass" in ok_line
          and not unfolded
          and printed.startswith("PROBE  <PYTHON> ")
          and home_line == "    HOME = '<HOME>'"
          and printed_line.endswith(" -> " + "x" * 100 + "<HOME>")
          and refused.count("'<REPO>/no-such-program'") == 2
          and "<box>" not in told
          and refused_next == ("  next: Check that the program named above "
                               "is on PATH and executable, then run the "
                               "command again."),
          f"{ACTUAL}the state line {_one_line(state_line, 90)!r}; the [OK] "
          f"line {_one_line(ok_line, 100)!r}; the banner "
          f"{_one_line(printed, 60)!r}; the planted home's line "
          f"{_one_line(home_line, 60)!r}; what a state command printed, "
          f"a hundred characters and then the home: "
          f"{printed_line.partition(' -> ')[2]!r}; "
          "unfolded interpreter form(s) of "
          f"{unfolded} characters; the program that will not start -> "
          f"{_one_line(refused, 200)!r}, its next: line -> "
          f"{_one_line(refused_next.strip(), 60)!r}",
          next="Read `census.own_log`: it folds every interpreter spelling, "
               "longest first, before the census's `path` rows, and the two "
               "`census` lines and `probe.banner` all print through it; a "
               "`state` variable's value and a `state` command's output "
               "go through `census.folded_for_reader`, which adds the "
               "home, before the command's line is cut.")


def _spelled_root_fold_control(check: CheckRow) -> None:
    """(ppppppp) golden-census's own log folds the temp root however an
    absolute TMPDIR spells it after its first name.

    Every path golden-census prints under the temp root is spelled as
    `os.path.abspath` and `tempfile.mkdtemp` give it — `/./` resolved, a
    doubled slash after the first name made one — whatever TMPDIR holds. The
    arm hands `census.own_log` one line naming `out` under a box of its own,
    in that spelling, with TMPDIR set to the box three ways: as its plain
    path, which is the control, with `/./` and with a doubled slash. The
    census is the stub's environment and the work directory's fold, and
    nothing else.
    """
    label = ("ppppppp  a line golden-census prints about a path under the "
             "temp root names it by the census's work token, and never by "
             "the root, whether TMPDIR spells that root plainly, with `/./` "
             "or with a doubled slash after its first name")
    folded: dict[str, str] = {}
    with _box("golden-census-spelled-root-") as box:
        plain = os.path.normpath(box)
        census_path = os.path.join(plain, "census.toml")
        pathlib.Path(census_path).write_text(
            _STUB_ENVIRONMENT + _STUB_WORK_FOLD, encoding="utf-8")
        census = load_census(census_path)
        parent, name = os.path.split(plain)
        line = f"capture -> {os.path.join(plain, 'out')}"
        for spelling, root in (("plainly", plain),
                               ("with /./", f"{parent}/./{name}"),
                               ("with a doubled slash", f"{parent}//{name}")):
            with _tmpdir_as(root):
                folded[spelling] = own_log(line, census, plain)
    wanted = "capture -> <WORK>/out"
    check(label,
          all(text == wanted for text in folded.values()),
          ACTUAL + "; ".join(
              f"TMPDIR spelled {spelling} -> "
              + repr(text.replace(os.path.realpath(plain), "<box>")
                     .replace(plain, "<box>"))
              for spelling, text in folded.items()),
          next="`census.own_log` folds the temp root as "
               "`os.path.normpath(temp_base())` spells it, which is how "
               "every path made under it is printed.")


def _short_name_fold_control(check: CheckRow, skip: SkipRow) -> None:
    """(ffff) the interpreter's SHORT NAME folds, and the gap that stays."""
    label = ("ffff  the interpreter folds by every spelling of the SAME file: "
             "a `probe` banner typed with the short name PATH resolves — a "
             "third string, neither `sys.executable` nor its realpath — reads "
             "`<PYTHON>`. The control is the disclosed gap `docs/contract.md` "
             "names: a fourth link to the same interpreter, a symlink this arm "
             "plants, is printed AS TYPED, because a fold is of the spellings "
             "this machine offers and not of every path that could ever point "
             "at the file")
    short = shutil.which(os.path.basename(sys.executable))
    real = os.path.realpath(sys.executable)
    if (not short or os.path.realpath(short) != real
            or short in (sys.executable, real)):
        skip(label,
             "the interpreter's own basename does not resolve on this PATH to "
             "a third spelling of the interpreter this command is running "
             "under — it resolves to nothing, to another file, or to "
             "`sys.executable` or its realpath, the two already folded — so "
             "there is no third spelling to fold. Nothing is claimed.")
        return
    census = Census.builtin()
    with _box("golden-census-shortname-") as box:
        roots = Roots(root=box, work=box, clone=None, fixed=None)
        printed = banner([short, "-c", "pass"], census, roots, os.getcwd())
        planted = os.path.join(box, "a-fourth-link")
        os.symlink(sys.executable, planted)
        as_typed = banner([planted, "-c", "pass"], census, roots,
                          os.getcwd())
        # The banner folds the box to a census `path` token, so what is left
        # of the planted link is its leaf. The LEAF is the evidence, and it
        # carries no directory of this machine.
        gap = os.path.basename(planted) in as_typed
    folded = printed == "PROBE  <PYTHON> -c pass"
    check(label, folded and gap,
          f"{ACTUAL}the short name ({len(short)} characters, neither of the "
          f"two already folded) -> {printed!r}; the planted fourth link -> "
          f"printed as typed={gap}")


def manifest_free_folds() -> tuple[Row, ...]:
    """The bundled fixture's `path` fold rows, read from its census.

    Arm `uu` asserts the priced block carries the tokens those rows name —
    `<REPO>`, `<TMPROOT>` — rather than a hand-typed pair, so a census that
    renames a placeholder moves the assertion with it.
    """
    fixture = Layout.detect().fixture
    if fixture is None or not os.path.isfile(
            os.path.join(fixture, "census.toml")):
        return ()
    return load_census(os.path.join(fixture, "census.toml")).folds_of("path")


#: The planted census arm `zzzz` runs: one row of each shape a consumer meets,
#: each planted to go RED. The drift pin's command is steady, so the unpinned
#: pair agrees and the pin is not shown to matter; the regex pattern matches
#: neither sample; the JSON field list names no key either document carries;
#: the path fold's `root` is a prefix of the stranger path the control
#: expects to survive, so the fold swallows it; and the `vary` pin names a
#: variable no surface reads, so its three runs agree (`_UNPROVEN_PIN`).
_RED_CENSUS = _STUB_ENVIRONMENT + '''
[fixtures]
dir = "."

[[input]]
name        = "a clock the control cannot show moving"
disposition = "pin"
variable    = "SOURCE_DATE_EPOCH"
value       = "0"
finding     = "planted: the control's command prints a constant, so the unpinned pair agrees"
control     = { shape = "drift", command = ["<PYTHON>", "-c", "print('steady')"], wait = 0.0 }

[[input]]
name        = "a pattern that matches neither sample"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>\\bNOWHERE\\b)'
placeholder = "<DURATION>"
finding     = "planted: the pattern fires on neither text, so the fold folds nothing"
control     = { sample = "scan finished in 137us", moved = "scan finished in 2041us" }

[[input]]
name        = "a field list naming no key the document carries"
disposition = "fold"
kind        = "json-fields"
paths       = ["provenance"]
fields      = ["absent"]
placeholder = "<PROVENANCE>"
serialization = { indent = 2, ensure_ascii = false }
finding     = "planted: neither document carries the named field, so the fold blanks nothing"
control     = { sample = "sample.json", moved = "moved.json" }
''' + _root_fold(
    "planted: the root is a prefix of the path the control expects to survive"
) + _UNPROVEN_PIN

#: The two documents the planted `json-fields` row's control names, written
#: exactly as its `serialization` would re-serialize them: `normalize_json`
#: asserts that round trip before it folds anything, and a fixture the census
#: could not reproduce would refuse rather than report a verdict.
_RED_SAMPLE = '{\n  "provenance": {\n    "commit": "aaaaaaa"\n  }\n}'
_RED_MOVED = '{\n  "provenance": {\n    "commit": "bbbbbbb"\n  }\n}'

#: The root the planted path fold folds. It is a PREFIX of the stranger path
#: `_path_fold_control` plants ("/nowhere/that/golden-census/made"), which is
#: what makes that control's "a path golden-census did not make survives" half
#: report red.
_RED_ROOT = "/nowhere/that"


def _control_next_control(check: CheckRow, skip: SkipRow) -> None:
    """(zzzz) every census control row a consumer meets ends a RED verdict in
    a `next:` line — and the row a raise produces does not.

    The six rows are the whole of what a consumer's census can put in front
    of them: the `vary`, drift and fixed-width pins, and the regex, JSON and
    path folds. Five are planted red through the row's own keys. The sixth
    cannot be: the width rule is golden-census's own arithmetic and no census key
    reaches it, so it goes red on a second, independent copy of `controls`
    whose `fixed_dir_room` is rebound — an ATTRIBUTE and never a patched
    source, so rewording a line of `controls.py` does not break the control.

    The negative half is the point of the sentence the documents now carry: a
    red row may carry no `next:` at all, and `Report.raised` is the row that
    never does. An arm that only asserted the six would leave the narrowed
    claim unmeasured.
    """
    label = ("zzzz  the six census control rows a consumer meets — the `vary` "
             "pin, the drift pin, the fixed-width pin and the regex, JSON and "
             "path folds — each end a RED verdict in a `next:` line, printed under the "
             "row; and the `[FAIL]  !` row of a control that RAISED carries "
             "none, which is the narrowed claim the three documents state")
    fresh = _fresh_module("controls")
    if fresh is None:
        skip(label, "this install carries no importable source for `controls`, "
                    "so the fixed-width row cannot be driven red without "
                    "patching a file. Nothing was measured and nothing is "
                    "claimed.")
        return

    with _box("golden-census-nexts-") as box:
        manifest_path = _scratch(box, census_text=_RED_CENSUS,
                                 extra={"sample.json": _RED_SAMPLE,
                                        "moved.json": _RED_MOVED})
        manifest = load_manifest(manifest_path)
        roots = Roots(root=_RED_ROOT, work=box, clone=None)
        # What this arm asks of a row is whether it CARRIES a next sentence,
        # which the printed block shows only when the row is red; the printed
        # shape is asserted separately, through the one printer.
        planted, _skips = _census_rows(manifest, roots)

        width_row = Row("the subject's temp root, and its width", "pin",
                        "planted: the width rule's own arithmetic is rebound "
                        "on a copy of the module",
                        # Built from the one place the width is written, never
                        # typed: arm `zzz` walks the package for a second
                        # spelling of it and this string would be one.
                        variable="TMPDIR",
                        value=f"<FIXED-WIDTH-DIR:{FIXED_DIR_WIDTH}>",
                        control={"shape": "builtin",
                                 "name": "fixed-width-dir"})
        width_census = Census(path="<planted>", directory=box, fixtures=None,
                              passthrough=("PATH",), rows=(width_row,))
        was = fresh.fixed_dir_room

        def always_room(base: str, width: int) -> tuple[str, int]:
            """Room for a leaf under every CONSTRUCTED width, and the truth
            under the machine's own temp root.

            The control walks six constructed widths that touch no disk and
            then makes one real directory when the live root fits. Rebinding
            both halves would send `make_fixed_dir` at a root that cannot hold
            one, and its refusal — a statement about this machine — would
            travel out of the arm and stop the self-check. Only the
            constructed widths are faked, which is exactly the arithmetic the
            control asserts.
            """
            if set(base.strip("/")) == {"b"}:
                return base, 1
            return was(base, width)

        try:
            fresh.fixed_dir_room = always_room
            planted += _rows_of(
                lambda check_row, skip_row: fresh._fixed_width_control(
                    width_row, width_census, check_row, skip_row))[0]
        finally:
            fresh.fixed_dir_room = was

    reds = [row for row in planted if not row[1]]
    with_next = [row for row in reds if row[3]]

    # The printed shape, through the ONE printer: a `next:` line under a red
    # row is `core.Report`'s to write, and a control that only read the field
    # would not have shown the reader anything.
    buffer = io.StringIO()
    report = Report(buffer, "PLANTED", quiet=True)
    for row_label, ok, detail, next_ in reds[:1]:
        report.check(row_label, ok, detail, next=next_)
    report.finish()
    printed = buffer.getvalue()

    raised = Report(io.StringIO(), "PLANTED")
    raised.raised(ImportError("a planted ImportError, on no list anywhere"))
    raised_next = raised.rows[0][3]

    check(label,
          len(planted) == 6 and len(reds) == 6 and len(with_next) == 6
          and "\n           next: " in printed and not raised_next,
          f"{ACTUAL}{len(planted)} planted row(s), {len(reds)} red, "
          f"{len(with_next)} carrying a next sentence "
          f"{[_one_line(row[0], 60) for row in reds if not row[3]]}; the one "
          f"printed red row shows a next: line="
          f"{chr(10) + '           next: ' in printed}; the raised row's next "
          f"is {raised_next!r}",
          next="Give every census control row a `next=`: a consumer meets "
               "these rows and no other, and a red one that says nothing "
               "about what to do sends them back to the census with only a "
               "detail line. If a plant above stopped going red, the control "
               "it plants has changed and this arm is the thing to read "
               "first.")


#: What arm `aaaaa` plants: one surface of each kind carrying `record_argv`.
#: Every kind but `matrix` must be refused at load, and `matrix` must still
#: load — a guard that refused everything would be as wrong as one that
#: refused nothing.
_RECORD_ARGV_PLANTS: dict[str, str] = {
    "run": """
[surfaces.recorded]
args        = ["--json"]
record_argv = ["SAME"]
""",
    "tallies": """
[surfaces.recorded]
kind        = "tallies"
args        = ["--tallies"]
rule        = "="
verdict     = '^\\s*\\d+/\\d+ passed\\s*$'
record_argv = ["SAME"]
""",
    "skip": """
[surfaces.recorded]
skip        = "a surface declared unrunnable"
record_argv = ["SAME"]
""",
    "matrix": """
[surfaces.recorded]
kind        = "matrix"
include     = "rows.json"
record_argv = ["<the rows of rows.json>"]
""",
}

#: The same for `failing`, which only a `tallies` surface reads: every other
#: kind refused at load, and `tallies` loading with the pattern compiled.
_FAILING_PLANTS: dict[str, str] = {
    "run": """
[surfaces.recorded]
args    = ["--json"]
failing = '^x'
""",
    "matrix": """
[surfaces.recorded]
kind    = "matrix"
include = "rows.json"
failing = '^x'
""",
    "skip": """
[surfaces.recorded]
skip    = "a surface declared unrunnable"
failing = '^x'
""",
    "tallies": """
[surfaces.recorded]
kind    = "tallies"
args    = ["--tallies"]
rule    = "="
verdict = '^\\s*\\d+/\\d+ passed\\s*$'
failing = '^x'
""",
}

#: The generated row file the `matrix` plant includes, so the one plant that
#: must LOAD is a whole matrix surface and not a matrix row file's refusal
#: wearing this arm's name.
_RECORD_ARGV_ROWS = '[{"label": "one", "args": ["--one"]}]\n'

#: A `run` surface that writes a file and counts it, for arm `aaaaa`'s
#: cases whose counter is in its place.
_COUNTED_SURFACE = """
[surfaces.recorded]
args    = ["--json", "<WRITES>"]
writes  = "<WORK>/<input>-<surface>.json"
counter = ["<PYTHON>", "stub.py"]
"""

#: What arm `aaaaa` plants for the two keys whose use another key decides:
#: a `counter` runs only on the file a `run` surface writes, and
#: `expect_counts` is checked only against a counter's numbers. Each case is
#: what the stub manifest's `surfaces = ["help"]` line becomes, the text
#: appended, the table the refusal must name (None for a case that must
#: load) and the words its first line must hold besides. The counted input
#: names its surface through a [surface-sets] entry, so a check that read the
#: input's list before the sets expand would refuse it.
_HALF_PLANTS: dict[str, tuple[str, str, str | None, tuple[str, ...]]] = {
    "counter without writes": (
        'surfaces = ["help", "recorded"]',
        '\n[surfaces.recorded]\nargs    = ["--json"]\n'
        'counter = ["<PYTHON>", "stub.py"]\n',
        "[surfaces.recorded]", ("`counter`", "`writes`")),
    "counter on matrix": (
        'surfaces = ["help", "recorded"]',
        '\n[surfaces.recorded]\nkind    = "matrix"\ninclude = "rows.json"\n'
        'counter = ["<PYTHON>", "stub.py"]\n',
        "[surfaces.recorded]", ("`counter`", "`run`", "`matrix`")),
    "counter on skip": (
        'surfaces = ["help", "recorded"]',
        '\n[surfaces.recorded]\nskip    = "a surface declared unrunnable"\n'
        'counter = ["<PYTHON>", "stub.py"]\n',
        "[surfaces.recorded]", ("`counter`", "`run`", "`skip`")),
    "counter on tallies": (
        'surfaces = ["help", "recorded"]',
        '\n[surfaces.recorded]\nkind    = "tallies"\nargs    = ["--tallies"]\n'
        'rule    = "="\nverdict = \'^\\s*\\d+/\\d+ passed\\s*$\'\n'
        'writes  = "<WORK>/<input>-<surface>.json"\n'
        'counter = ["<PYTHON>", "stub.py"]\n',
        "[surfaces.recorded]", ("`counter`", "`run`", "`tallies`")),
    "counter with writes": (
        'surfaces = ["help", "recorded"]', _COUNTED_SURFACE, None, ()),
    # A counter in its place that spells `<input>`, a name `writes` alone
    # defines: the run would refuse it after the subject ran, so the load
    # refuses it first, in the vocabulary the run expands it with.
    "counter spelling <input>": (
        'surfaces = ["help", "recorded"]',
        _COUNTED_SURFACE.replace('"stub.py"]', '"stub.py", "<input>"]'),
        "[surfaces.recorded]", ("counter", "<input>")),
    "expect_counts without a counter": (
        'surfaces = ["help"]\nexpect_counts = { rows = 1 }', "",
        "[inputs._subject]", ("`expect_counts`", "`counter`")),
    "expect_counts empty": (
        'surfaces = ["help", "recorded"]\nexpect_counts = {}',
        _COUNTED_SURFACE, "[inputs._subject]",
        ("`expect_counts`", "empty table")),
    "expect_counts with a counter": (
        'surfaces = ["help", "counted"]\nexpect_counts = { rows = 1 }',
        _COUNTED_SURFACE + '\n[surface-sets]\ncounted = ["recorded"]\n',
        None, ()),
}


def _record_argv_control(check: CheckRow) -> None:
    """(aaaaa) `record_argv` outside a `matrix` surface, and `failing`
    outside a `tallies` one, are refused at LOAD.

    Each is read at exactly one site — `record_argv` by
    `capture.record_matrix`, `failing` by `capture.record_tallies` — so on
    every other kind it is a key that does nothing, silently: for
    `record_argv` while `shares_invocation_with` goes on being derived from
    the argvs that really ran, for `failing` while a reader takes the failing
    rows' evidence to be recorded. A key a reader can write and golden-census
    will not read is the worst shape there is: refuse, don't guess.

    A `counter` is the same shape, decided by the kind and by another key:
    `capture._record_surface` runs it only on the file a `run` surface wrote,
    so on any other kind, or on a `run` surface with no `writes`, it never
    runs; and an input's `expect_counts` is checked only against a counter's
    numbers, so an empty one checks nothing. Each is refused at load, on the
    refusal's first line, and loads where its other half is there. A counter
    is planted on every kind `manifest.SURFACE_KINDS` names but `run`, the
    `tallies` one with a `writes` beside it, so that only the kind can be
    what refuses it. A counter in its place that spells `<input>` is refused
    at load too, in the vocabulary its run expands it with, before the
    subject runs.
    """
    label = ("aaaaa  `record_argv` on a surface that is not `matrix`, and "
             "`failing` on one that is not `tallies`, are REFUSED when the "
             "manifest is read, naming the surface, the key and the kind it "
             "belongs to — every other kind and a `skip` surface each — while "
             "the one kind that reads the key still loads and keeps it; a "
             "`counter` anywhere but on a `run` surface with `writes` — a "
             "`run` surface without it, and a `matrix`, a `tallies` and a "
             "`skip` one, every kind but `run` the loader names — is "
             "REFUSED likewise, and so is a counter in its place that spells "
             "`<input>`, a name only `writes` defines, and an "
             "`expect_counts` that is an empty "
             "table or sits on an input none of whose surfaces has a "
             "`counter`, each refusal's first line naming its table, its key "
             "and why the key does nothing — the kind, the missing `writes` or "
             "`counter`, or the empty table — while a counter on a `run` "
             "surface with `writes`, and an `expect_counts` whose input names "
             "that surface through a surface set, load and keep their values")
    verdicts: dict[str, str] = {}
    kept: dict[str, str] = {}
    owners = (("record_argv", "matrix", _RECORD_ARGV_PLANTS),
              ("failing", "tallies", _FAILING_PLANTS))
    for key, _owner, plants in owners:
        for kind, block in plants.items():
            with _box("golden-census-record-argv-") as box:
                path = _scratch(
                    box,
                    manifest_text=_STUB_MANIFEST.replace(
                        'surfaces = ["help"]',
                        'surfaces = ["help", "recorded"]') + block,
                    extra={"rows.json": _RECORD_ARGV_ROWS})
                try:
                    loaded = load_manifest(path).surfaces["recorded"]
                    verdicts[f"{key} on {kind}"] = "LOADED"
                    kept[key] = (
                        str(loaded.record_argv) if key == "record_argv"
                        else loaded.failing.pattern if loaded.failing
                        else "None")
                except Refusal as refused:
                    verdicts[f"{key} on {kind}"] = refusal_text(refused)
    halves: dict[str, str] = {}
    halves_kept: dict[str, str] = {}
    for case, (line, block, _table, _words) in _HALF_PLANTS.items():
        with _box("golden-census-record-argv-") as box:
            path = _scratch(box, manifest_text=_STUB_MANIFEST.replace(
                'surfaces = ["help"]', line) + block,
                extra={"rows.json": _RECORD_ARGV_ROWS})
            try:
                manifest = load_manifest(path)
                halves[case] = "LOADED"
                halves_kept[case] = (
                    str(manifest.surfaces["recorded"].counter)
                    if case.startswith("counter")
                    else str(manifest.inputs[0].expect_counts))
            except Refusal as refused:
                halves[case] = refusal_text(refused)
    # The first line only: the `next:` below it names keys of its own, and
    # a sentence that lost one would still pass on the advice's words.
    halves_named = all(
        halves[case].startswith("REFUSED: ")
        and table in halves[case].partition("\n")[0]
        and all(word in halves[case].partition("\n")[0] for word in words)
        for case, (_line, _block, table, words) in _HALF_PLANTS.items()
        if table is not None)
    # Every kind the rule names, read off the loader's own tuple: a kind
    # added there with no plant here is a clause of the rule no plant holds.
    planted_kinds = sorted(case.removeprefix("counter on ")
                           for case in _HALF_PLANTS
                           if case.startswith("counter on "))
    other_kinds = sorted(kind for kind in SURFACE_KINDS if kind != "run")

    # The sentence has to carry all three, because all three are what a reader
    # needs to fix the row: which surface, which key, and which kind it is —
    # a refusal naming only the key sends them looking through every surface.
    named = all(
        verdicts[f"{key} on {kind}"].startswith("REFUSED: ")
        and "[surfaces.recorded]" in verdicts[f"{key} on {kind}"]
        and f"`{key}`" in verdicts[f"{key} on {kind}"]
        and f"`{owner}`" in verdicts[f"{key} on {kind}"]
        and f"`{kind}`" in verdicts[f"{key} on {kind}"]
        for key, owner, plants in owners for kind in plants if kind != owner)
    check(label,
          named and verdicts["record_argv on matrix"] == "LOADED"
          and verdicts["failing on tallies"] == "LOADED"
          and kept == {"record_argv": "('<the rows of rows.json>',)",
                       "failing": "^x"}
          and halves_named and planted_kinds == other_kinds
          and halves_kept == {"counter with writes": "('<PYTHON>', 'stub.py')",
                              "expect_counts with a counter": "{'rows': 1}"},
          ACTUAL + ", ".join(
              # From the surface's own table onward: the whole sentence opens
              # with the scratch manifest's absolute path, which says nothing
              # about the rule and would put a temp directory in a pasted row.
              f"{case} -> {_one_line(text.partition('[surfaces.')[2] or text, 110)}"
              for case, text in verdicts.items())
          + f"; the owning kinds kept {kept}; "
          + ", ".join(
              # From the table onward, for the same reason.
              f"{case} -> {_one_line(text[text.find(': [') + 2:] if ': [' in text else text, 110)}"
              for case, text in halves.items())
          + f"; the cases that load kept {halves_kept}; a counter planted on "
            f"{planted_kinds}, the kinds that are not `run` "
            f"{other_kinds}",
          next="`record_argv` is read at one site, `capture.record_matrix`, "
               "and `failing` at one, `capture.record_tallies`. If a kind "
               "above now loads its key, either another site reads it too — "
               "in which case say so in docs/manifest-format.md and widen "
               "this arm — or `manifest._ONE_KIND_KEYS`' guard in "
               "`manifest._surface` has gone, and a manifest key that does "
               "nothing silently is back. A `counter` is run at one site, "
               "`capture._record_surface`, only on a `run` surface's written "
               "file, and `expect_counts` is read beside it: if a case above "
               "that must be refused loads, the guard in `manifest._surface`, "
               "`manifest._inputs` or `manifest._resolve_surfaces` has gone; "
               "if one that must load is refused, the guard refuses more than "
               "its rule.")


#: The three fold kinds arm `bbbbb` plants a `scope` on, each written twice —
#: once narrowing, once as the `"*"` that is the default said out loud.
_SCOPE_PLANTS: dict[str, str] = {
    "regex": '''
[[input]]
name        = "a token that moves inside a line"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>\\bstamp-\\w+\\b)'
placeholder = "<STAMP>"
{scope}finding     = "a planted fold, for the scope guard"
control     = { sample = "read stamp-aaa", moved = "read stamp-bbb" }
''',
    "path": _root_fold("a planted fold, for the scope guard", "{scope}"),
    "json-fields": '''
[[input]]
name        = "a field that moves in a written document"
disposition = "fold"
kind        = "json-fields"
paths       = ["provenance"]
fields      = ["commit"]
placeholder = "<PROVENANCE>"
serialization = { indent = 2, ensure_ascii = false }
{scope}finding     = "a planted fold, for the scope guard"
control     = { sample = "sample.json", moved = "moved.json" }
''',
}


def _scope_census(kind: str, scope: str) -> str:
    """The stub census plus one planted fold of `kind`, carrying `scope`."""
    return (_STUB_CENSUS + '\n[fixtures]\ndir = "."\n'
            + _SCOPE_PLANTS[kind].replace("{scope}", scope))


def _from_row(text: str) -> str:
    """A census refusal from the ROW it names onward.

    The sentence opens with the scratch census's absolute path, which says
    nothing about the rule and would put a temp directory into a printed row.
    """
    row, sep, rest = text.partition(": row ")
    return f"row {rest}" if sep else text


def _scope_control(check: CheckRow) -> None:
    """(bbbbb) a NARROWING `scope` outside a `regex` fold is refused when the
    census is read.

    `Row.in_scope` is consulted at one site, inside `normalize_text`'s regex
    loop. `normalize_paths` takes no row key at all, and `normalize_json`
    applies a `json-fields` fold to the whole document before the row's regex
    folds see it, so a scoped `path` or `json-fields` fold was a key the
    loader checked and the comparator then ignored — the shape this project
    exists to refuse. The REGEX half of a `.json` file honors a narrowing
    scope: it goes through `normalize_text` under the row's key. `"*"`
    is not narrowing and stays legal on every kind: it is the fold's own rule
    said out loud, and a guard that refused it would refuse a sentence rather
    than a mistake.
    """
    label = ("bbbbb  a NARROWING `scope` on a `path` or `json-fields` fold is "
             "REFUSED when the census is read, naming the row and its kind, "
             "because only the regex loop is given a row key to match one "
             "against; `scope = \"*\"` — the default said out loud — loads on "
             "every kind, and a narrowing scope on a `regex` fold loads and "
             "is kept")
    verdicts: dict[str, str] = {}
    kept = ""
    for kind in _SCOPE_PLANTS:
        for spelling, text in (("narrowing", 'scope       = ["_subject/help"]\n'),
                               ("*", 'scope       = "*"\n')):
            with _box("golden-census-scope-") as box:
                path = _scratch(box, census_text=_scope_census(kind, text),
                                extra={"sample.json": _RED_SAMPLE,
                                       "moved.json": _RED_MOVED})
                try:
                    loaded = load_manifest(path).census.folds_of(kind)[0]
                    verdicts[f"{kind} {spelling}"] = "LOADED"
                    if kind == "regex" and spelling == "narrowing":
                        kept = str(loaded.scope)
                except Refusal as refused:
                    verdicts[f"{kind} {spelling}"] = refusal_text(refused)

    refusals = [verdicts["path narrowing"], verdicts["json-fields narrowing"]]
    # The kind has to be in the sentence: a reader with a census of several
    # folds needs to know which row to open, and "scope narrows a regex fold"
    # alone does not say which of theirs does not.
    named = all(text.startswith("REFUSED: ") and "`scope`" in text
                and "`regex`" in text for text in refusals)
    kinds_named = ("`path` fold" in refusals[0]
                   and "`json-fields` fold" in refusals[1])
    loads = [key for key, text in verdicts.items() if text == "LOADED"]
    check(label,
          named and kinds_named
          and sorted(loads) == ["json-fields *", "path *", "regex *",
                                "regex narrowing"]
          and kept == "('_subject/help',)",
          ACTUAL + ", ".join(
              # From the row's own name onward: the sentence opens with the
              # scratch census's absolute path, which says nothing about the
              # rule and would put a temp directory in a pasted row.
              f"{key} -> {_one_line(_from_row(text), 95)}"
              for key, text in verdicts.items())
          + f"; the scoped regex fold kept scope={kept}",
          next="`Row.in_scope` is read at one site, inside `normalize_text`'s "
               "regex loop. If a path or json-fields fold now loads a "
               "narrowing scope, either those normalizers take a row key now "
               "— say so in docs/census-format.md and widen this arm — or the "
               "guard in `_fold_row` has gone and a census key the comparator "
               "ignores is back.")


#: The one fold arm `rrrrr` plants, written once and given five `scope`
#: spellings. A `regex` fold, because `scope` is a `regex` fold's key. The
#: pattern names an invented root and not a real platform's home root: what
#: the arm is about is the `scope` spelling, and a shipped file that spells a
#: real home root spells one machine's.
_STAR_SCOPE_PLANT = '''
[[input]]
name        = "the user's home directory"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>/homes-of/[^/\\s]+)'
placeholder = "<HOME>"
{scope}finding     = "a row that prints a path under a home carries the user's name"
control     = { sample = "read /homes-of/aa/x", moved = "read /homes-of/bb/x" }
'''

#: The same plant as a `path` fold, for the one case that is about a kind
#: rather than about a spelling.
_STAR_SCOPE_PATH = _root_fold("a planted path fold, for the star-scope guard",
                              "{scope}")


def _star_scope_control(check: CheckRow) -> None:
    """(rrrrr) `scope = ["*"]` means what `scope = "*"` means, and a list that
    mixes `"*"` with row names is refused.

    The format offers a bare string and a list, and its own example is
    list-valued beside a sentence saying `"*"` is every row — so a reader who
    took the list to be the form wrote the default in the spelling their file
    already used, and was refused for a difference that carries no meaning.
    A list that MIXES the two is the other case and stays refused: it says
    every row and these rows at once, and only one of them can be what the
    fold does.

    The last condition is about the refusal a reader meets NEXT. While `["*"]`
    was refused, `check_scopes` offered `"*"` as the remedy for the value it
    had just refused; with `["*"]` legal that clause can no longer be reached
    by the spelling it names, so it would be advice pointing at nothing.
    """
    label = ("rrrrr  `scope = [\"*\"]` LOADS and means every row, the same as "
             "`scope = \"*\"` — on a `path` fold as well, which is no longer a "
             "narrowing scope — while a list mixing `\"*\"` with row names is "
             "REFUSED naming both spellings, and the refusal for a row the "
             "manifest does not define no longer offers `\"*\"` as the remedy")
    verdicts: dict[str, str] = {}
    scoped: dict[str, str] = {}
    plants = (
        ("regex *", _STAR_SCOPE_PLANT, 'scope       = "*"\n'),
        ("regex [*]", _STAR_SCOPE_PLANT, 'scope       = ["*"]\n'),
        ("regex [*, row]", _STAR_SCOPE_PLANT,
         'scope       = ["*", "_subject/help"]\n'),
        ("regex [no such row]", _STAR_SCOPE_PLANT,
         'scope       = ["no/such-row"]\n'),
        ("path [*]", _STAR_SCOPE_PATH, 'scope       = ["*"]\n'),
    )
    for key, plant, scope in plants:
        with _box("golden-census-star-scope-") as box:
            path = _scratch(box, census_text=_STUB_CENSUS
                            + plant.replace("{scope}", scope))
            try:
                loaded = load_manifest(path)
                kind = "path" if key.startswith("path") else "regex"
                row = loaded.census.folds_of(kind)[0]
                verdicts[key] = "LOADED"
                # The claim is not that it loaded but that it means EVERY row:
                # a scope of `()` would load too and fold nothing.
                scoped[key] = (f"scope={row.scope!r} "
                               f"applies to _subject/help="
                               f"{row.in_scope('_subject/help')}")
            except Refusal as refused:
                verdicts[key] = refusal_text(refused)

    every_row = "scope=None applies to _subject/help=True"
    mixed = verdicts["regex [*, row]"]
    unknown = verdicts["regex [no such row]"]
    check(label,
          all(verdicts[key] == "LOADED"
              for key in ("regex *", "regex [*]", "path [*]"))
          and all(scoped[key] == every_row
                  for key in ("regex *", "regex [*]"))
          and scoped["path [*]"] == every_row
          # Both spellings in the sentence, because the reader's fix is to
          # choose between them and a refusal naming one says nothing about it.
          and mixed.startswith("REFUSED: ") and '"*"' in mixed
          and "_subject/help" in mixed
          and unknown.startswith("REFUSED: ") and "no/such-row" in unknown
          and "widen it to" not in unknown,
          ACTUAL + ", ".join(
              f"{key} -> {_one_line(_from_row(text), 90)}"
              + (f" [{scoped[key]}]" if key in scoped else "")
              for key, text in verdicts.items()),
          next="`_fold_row` reads the two spellings of every row at one site. "
               "If `[\"*\"]` is refused again, that site has gone back to "
               "testing the raw value against the string `\"*\"`; if the mixed "
               "list loads, the refusal beside it has gone and a census says "
               "two things at once; if `widen it to` is back in the last "
               "refusal, `check_scopes` is recommending a spelling it never "
               "sees.")


#: Arm `sssss`'s two folds: the `path` fold whose control the false
#: attribution reddened, and the `regex` fold that reddened it. The pattern is
#: the consumer's own shape — a directory one level under a fixed prefix —
#: aimed at the prefix every box of this self-check is made under.
_OVERLAP_PLANT = _root_fold(
    "every report header carries the checkout's own directory") + '''
[[input]]
name        = "the scratch directories of this machine"
disposition = "fold"
kind        = "regex"
pattern     = '{pattern}'
placeholder = "<SCRATCHROOT>"
{scope}finding     = "a scratch path reaches a report and moves with the machine"
control     = { sample = "read A/x", moved = "read B/x" }
'''


def _swallowing_census(box: str) -> tuple[Census, Roots]:
    """The census arms `sssss` and `yyyyy` both plant, and the roots it is
    read against: a `*` regex fold whose `volatile` group takes the directory
    one level under `box` — so it swallows part of both the subject root
    `<box>/checkout` and the work directory `<box>/work` — beside a `path`
    fold for each — the work fold being the one arm `sssss` reads, because
    the work directory is not the subject root and its control is the one
    the capture-time refusal does not cover.

    Loaded with `load_census`, because `load_manifest` refuses this census
    before any control can be reached, and the controls are what the two
    arms are about.
    """
    planted_root = os.path.join(box, "checkout")
    os.makedirs(planted_root, exist_ok=True)
    parent = os.path.basename(box)
    census_path = os.path.join(box, "red-census.toml")
    pathlib.Path(census_path).write_text(_STUB_CENSUS + _OVERLAP_PLANT
                                         .replace("{pattern}", f"/{parent}/(?P<volatile>[^/ ]+)")
                                         .replace("{scope}", 'scope       = "*"\n')
                                         + _STUB_WORK_FOLD, encoding="utf-8")
    return load_census(census_path), Roots(
        root=planted_root, work=os.path.join(box, "work"), clone=None)


def _path_fold_rows(census: Census, roots: Roots, source: str
                    ) -> list[tuple[str, bool, str, str]]:
    """Every row the `path` fold control reports for the folds of `source`,
    as `(label, ok, detail, next)`."""
    return [row for fold in census.folds_of("path") if fold.source == source
            for row in _rows_of(functools.partial(
                _path_fold_control, fold, census, roots))[0]]


#: The two `path` fold rows whose directories the controls' work directory
#: never holds, for arm `kkkkk`.
_STAND_IN_FOLDS = '''
[[input]]
name        = "an input's clone directory"
disposition = "fold"
kind        = "path"
source      = "clone"
placeholder = "<CLONE>"
finding     = "a row's argv names its input's clone"

[[input]]
name        = "the fixed-width temp directory"
disposition = "fold"
kind        = "path"
source      = "fixed-width-dir"
placeholder = "<ENGINE-TMPDIR>"
finding     = "a surface prints its temp path"
'''

#: Arm `kkkkk`'s planted red: a `regex` fold over every row that rewrites the
#: clone stand-in's name before the path fold sees the path.
_STAND_IN_EATER = '''
[[input]]
name        = "the eater"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>stand-in-clone)'
placeholder = "<EATEN>"
scope       = "*"
finding     = "planted: a fold that rewrites the stand-in's name"
control     = { sample = "read stand-in-clone/x", moved = "read stand-in-other/x" }
'''


def _stand_in_fold_control(check: CheckRow) -> None:
    """(kkkkk) the `clone` and `fixed-width-dir` path folds get a verdict from
    the census's own controls, whose work directory holds neither directory:
    `_path_fold_control` makes a stand-in under that work directory and folds
    it. Both stand-ins sit under the work directory and nowhere else. Planted
    red: a `regex` fold that rewrites the stand-in's name before the path
    fold sees the path, so the placeholder never appears.
    """
    label = ("kkkkk  the `clone` and `fixed-width-dir` path fold controls PASS "
             "on a stand-in directory made under the controls' work "
             "directory, where they used to SKIP; both stand-ins sit under "
             "that directory and nowhere else; and a `regex` fold that "
             "rewrites the clone stand-in's name turns the clone row red")
    stranger = "/nowhere/that/golden-census/made/App"
    with _box("golden-census-stand-in-") as box:
        work = os.path.join(box, "work")
        os.makedirs(work)
        roots = Roots(root=box, work=work)
        green_path = os.path.join(box, "green.toml")
        pathlib.Path(green_path).write_text(_STUB_CENSUS + _STAND_IN_FOLDS,
                                            encoding="utf-8")
        green = load_census(green_path)
        clone_rows = _path_fold_rows(green, roots, "clone")
        fixed_rows = _path_fold_rows(green, roots, "fixed-width-dir")
        made = sorted(os.listdir(work))
        outside = sorted(name for name in os.listdir(box)
                         if name not in ("work", "green.toml", "red.toml"))
        red_path = os.path.join(box, "red.toml")
        pathlib.Path(red_path).write_text(
            _STUB_CENSUS + _STAND_IN_FOLDS + _STAND_IN_EATER, encoding="utf-8")
        red_rows = _path_fold_rows(load_census(red_path), roots, "clone")
    clone_ok = (len(clone_rows) == 1 and clone_rows[0][1]
                and f"scanned <CLONE>/App and {stranger}" in clone_rows[0][2])
    fixed_ok = (len(fixed_rows) == 1 and fixed_rows[0][1]
                and f"scanned <ENGINE-TMPDIR>/App and {stranger}"
                in fixed_rows[0][2])
    placed = (made == ["stand-in-clone", "stand-in-fixed-width-dir"]
              and outside == [])
    red_ok = len(red_rows) == 1 and not red_rows[0][1]

    def row_text(rows: list[tuple[str, bool, str, str]]) -> str:
        if len(rows) != 1:
            return f"{len(rows)} row(s)"
        return ("PASS " if rows[0][1] else "FAIL ") + _one_line(rows[0][2],
                                                              DIFFERENCE)

    check(label, clone_ok and fixed_ok and placed and red_ok,
          f"{ACTUAL}the clone row -> {row_text(clone_rows)}; the fixed-width "
          f"row -> {row_text(fixed_rows)}; made under the work directory: "
          f"{made}, outside it: {outside}; with the eater the clone row -> "
          f"{row_text(red_rows)}",
          next="In `controls._path_fold_control`, where `roots.by_source` "
               "holds no directory for the row's source, make "
               "`stand-in-<source>` under `roots.work` and fold that; the "
               "sample line is golden-census's own, and a `regex` fold that "
               "rewrites the stand-in's name must leave the row red, not "
               "raise.")


#: Arm `mmmmmmmm`'s folds: `build 42 done` becomes `build <N> done` under
#: `matches`; `nothing` is a fold whose pattern matches no text the controls
#: hold. All three carry the same `control`.
_OWN_PATTERN_FOLDS = {
    "nothing": "nothing here: (?P<volatile>\\d+)",
    "matches": "build (?P<volatile>\\d+) done",
    "also matches": "build (?P<volatile>\\d+)",
}


def _own_pattern_census(names: tuple[str, ...]) -> str:
    """The stub census with the `regex` folds of `_OWN_PATTERN_FOLDS` named
    here, in this order."""
    return _STUB_CENSUS + "".join(f'''
[[input]]
name        = "{name}"
disposition = "fold"
kind        = "regex"
pattern     = '{_OWN_PATTERN_FOLDS[name]}'
placeholder = "<N>"
finding     = "planted: a build number that is new on every run"
control     = {{ sample = "build 42 done", moved = "build 43 done" }}
''' for name in names)


def _own_pattern_control(check: CheckRow) -> None:
    """(mmmmmmmm) a `regex` fold's control asks the ROW's own pattern.

    The control normalized the sample and the moved text through the whole
    fold set and asked whether the token moved, so a fold whose pattern
    matched nothing went green beside a second fold that matched the same
    token. Planted: `nothing`, whose pattern matches neither text, before
    and after `matches`, which folds the token; each fold's row is read as
    `controls._regex_fold_control` reports it. The controls are
    `matches` alone and `matches` beside `also matches` — two folds that both
    match the token, each on its own — which stay green.
    """
    label = ("mmmmmmmm  a `regex` fold whose own `pattern` matches neither "
             "its `control.sample` nor its `control.moved` is a RED control "
             "row naming the row, the pattern and the text — before a second "
             "fold that folds the same token and after it — while the fold "
             "that folds the token stays green, and so do two folds that "
             "each match the token on their own. Unguarded the first fold's "
             "control passed, because the second fold had folded the token")
    verdicts: dict[str, list[tuple[bool, str]]] = {}
    with _box("golden-census-own-pattern-") as box:
        manifest = load_manifest(_scratch(box))
        roots = Roots(root=box, work=os.path.join(box, "work"))
        for case, names in {
                "nothing, matches": ("nothing", "matches"),
                "matches, nothing": ("matches", "nothing"),
                "matches": ("matches",),
                "matches, also matches": ("matches", "also matches"),
        }.items():
            path = os.path.join(box, f"{len(verdicts)}.toml")
            pathlib.Path(path).write_text(_own_pattern_census(names),
                                          encoding="utf-8")
            census = load_census(path)
            verdicts[case] = [
                (ok, detail) for fold in census.folds_of("regex")
                for _label, ok, detail, _next in _rows_of(functools.partial(
                    _regex_fold_control, fold, census, manifest, roots))[0]]
    greens = {"matches": [True], "matches, also matches": [True, True]}
    reds = {"nothing, matches": [False, True], "matches, nothing": [True, False]}
    named = all(
        "nothing here" in verdicts[case][position][1]
        and "'build 42 done'" in verdicts[case][position][1]
        for case, oks in reds.items() for position, ok in enumerate(oks)
        if not ok)
    check(label,
          all([ok for ok, _ in verdicts[case]] == oks
              for case, oks in (greens | reds).items()) and named,
          ACTUAL + "; ".join(
              f"{case} -> "
              + ", ".join("PASS" if ok else "FAIL" for ok, _ in rows)
              for case, rows in verdicts.items())
          + "; the red row names its pattern and sample="
          + str(named))


def _fold_overlap_control(check: CheckRow) -> None:
    """(sssss) a fold that applies to EVERY row, whose `volatile` group
    SPLITS the subject root, is REFUSED when the manifest is read — and the
    path fold control's red row stops blaming golden-census for it.

    A `regex` fold sees the raw text, before the built-in `path` folds. A
    pattern broad enough to match inside the subject root therefore replaces
    part of that root first, the root fold no longer recognizes what is left,
    and the row that goes red is golden-census's own control — which used to
    tell the reader to report a golden-census defect for a row they had
    written themselves. The refusal moves that discovery to the manifest load,
    and the control's `next:` sends them to their own census before it sends
    them to a bug report.

    The narrowing-scope half is the control, and it is the workaround the
    first consumer to hit this found for themselves: a fold that names its
    rows is not refused at load. If a row it names prints the root, the
    capture refuses it there, which is arm `yyyyy`'s.

    The alternation is the other control, and it is about the `volatile`
    GROUP: `fold_regex` replaces that group and nothing else, so a match the
    group took no part in moves not one byte of the root. What the refusal
    quotes is the same fact read the other way — the group's text, never the
    whole match. A group that takes the whole root is the third: it leaves
    nothing of the root for the root fold to miss, so it is no split.
    """
    label = ("sssss  a `regex` fold applying to EVERY row whose `volatile` "
             "group SPLITS the subject root — takes part of it and leaves a "
             "fragment — is REFUSED when the manifest is read, quoting the "
             "group's own text and not the whole match — while the same fold "
             "scoped to the rows that need it, a fold that matches nothing in "
             "the root, an alternation whose matching branch the `volatile` "
             "group takes no part in, and a group that takes the WHOLE root "
             "all load; "
             "and a red path fold control names the reader's own regex folds "
             "BEFORE a golden-census defect")
    verdicts: dict[str, str] = {}
    with _box("golden-census-fold-overlap-") as box:
        # The box IS the subject root, so a pattern aimed at the directory
        # the box sits in matches inside it by construction — the same
        # arithmetic as a consumer's home-directory pattern, with no path of
        # this machine written down.
        # The FULL path of the directory the box sits in, escaped, so the
        # pattern can match only where the box's own parent is: its last
        # component alone matches the first place that name occurs, which is
        # earlier in the path under a TMPDIR like `/tmp/x/tmp`.
        parent = re.escape(os.path.dirname(box))
        # What the group alone would take, kept beside the pattern that takes
        # it: the assertion below is that the refusal quotes THIS and not the
        # whole match, which is a byte the fold leaves alone.
        swallowed = os.path.basename(box)
        matching = f"{parent}/(?P<volatile>[^/ ]+)"
        plants = (
            ("* and matching", matching, 'scope       = "*"\n'),
            ("scoped and matching", matching,
             'scope       = ["_subject/help"]\n'),
            ("* and matching nothing",
             "(?P<volatile>/nothing-this-root-can-hold/[^/ ]+)",
             'scope       = "*"\n'),
            # An alternation whose OTHER branch matches inside the root. The
            # `volatile` group takes no part in that match, `fold_regex`
            # replaces only that group, so not one byte of the root moves and
            # there is no overlap to refuse.
            ("* and an alternation the group takes no part in",
             f"(?P<volatile>/nothing-this-root-can-hold/[^/ ]+)|{parent}/",
             'scope       = "*"\n'),
            # A group that takes the whole root leaves no fragment for the
            # root fold to miss: it replaces the root with its placeholder,
            # the same on every machine.
            ("* and taking the whole root", r"(?P<volatile>/\S+)",
             'scope       = "*"\n'),
        )
        for key, pattern, scope in plants:
            path = _scratch(box, census_text=_STUB_CENSUS + _OVERLAP_PLANT
                            .replace("{pattern}", pattern)
                            .replace("{scope}", scope))
            verdicts[key] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")

    # The fourth condition is about the CONTROL rather than the loader: what
    # a reader is told when a path fold control really does go red. The load
    # this arm makes is `load_census`, not `load_manifest`, because the
    # refusal above is what a manifest load is for — the control has to be
    # reached with the very census that refusal exists to stop, so the row a
    # reader would have met is the row this arm reads. It is the WORK row's
    # control: the root row's sample holds the subject root, and there the
    # swallow is caught by the capture-time test and reported as that row's
    # own red line naming the fold, which arm `yyyyy` asserts.
    advice = ""
    verdict = ""
    with _box("golden-census-fold-overlap-") as box:
        census, roots = _swallowing_census(box)
        rows = _path_fold_rows(census, roots, "work")
        if rows:
            verdict = "red" if not rows[0][1] else "green"
            advice = rows[0][3]

    swallows = verdicts["* and matching"]
    check(label,
          swallows.startswith("REFUSED: ")
          # The matched text IS the evidence: the root is already named, and a
          # reader fixing a pattern needs to see what it caught.
          and "folds EVERY row" in swallows
          # The `volatile` GROUP's own text, which is all `fold_regex`
          # replaces: quoting the whole match would hand a reader a span to
          # narrow that their pattern never touches.
          and f"it would replace {swallowed!r} in it" in swallows
          and verdicts["scoped and matching"] == "LOADED"
          and verdicts["* and matching nothing"] == "LOADED"
          and verdicts[
              "* and an alternation the group takes no part in"] == "LOADED"
          and verdicts["* and taking the whole root"] == "LOADED"
          # The control really went RED — an assertion about the advice on a
          # row that stayed green would be an assertion about nothing.
          and verdict == "red"
          and advice.startswith("Check your census's regex folds first")
          and advice.index("regex folds") < advice.index("defect"),
          ACTUAL + ", ".join(
              f"{key} -> {_one_line(_from_row(text), 95)}"
              for key, text in verdicts.items())
          + f"; the path fold control went {verdict}, its next: "
          + _one_line(advice, 70),
          next="`census.check_fold_overlap` is called from `load_manifest`, "
               "once, and walks only `*`-scoped regex folds against the "
               "subject root. If the first case loads, that call has gone and "
               "a consumer's fold can swallow the root again with "
               "golden-census's own control taking the blame; if the scoped "
               "case is refused, the rule has stopped honoring the one "
               "workaround it sends readers to.")


#: (jjjjjj) the stub census with its `vary` control pointed at a row the stub
#: manifest does not record — one letter transposed, the typo a reader makes.
_VARY_TYPO_CENSUS = _STUB_CENSUS.replace('"_subject/help"', '"_subject/hlep"')

#: The stub census with its `vary` control on a surface declared unrunnable,
#: and the manifest that records that surface as a `skip` row.
_VARY_SKIP_CENSUS = _STUB_CENSUS.replace('"_subject/help"', '"_subject/gone"')
_VARY_SKIP_MANIFEST = (_STUB_MANIFEST.replace('surfaces = ["help"]',
                                              'surfaces = ["help", "gone"]')
                       + '\n[surfaces.gone]\n'
                         'skip = "planted: a surface declared unrunnable"\n')

#: A json-fields census whose control's two files sit beside it — arm
#: `bbbbb`'s plant with no `scope` — and the three ways its fixtures key can
#: fail to resolve are edits of it.
_JSON_FIXTURES_CENSUS = _scope_census("json-fields", "")

#: The json-fields census with a second json-fields row that asks for
#: another `serialization`: one document cannot be re-serialized two ways.
_JSON_TWO_WAYS_CENSUS = _JSON_FIXTURES_CENSUS + _SCOPE_PLANTS[
    "json-fields"].replace("{scope}", "").replace(
    '"a field that moves in a written document"', '"a second field"').replace(
    '["commit"]', '["date"]').replace("indent = 2", "indent = 4")
#: The same two rows, alike in `indent` and different in `ensure_ascii`.
_JSON_TWO_ASCII_CENSUS = _JSON_TWO_WAYS_CENSUS.replace(
    "indent = 4, ensure_ascii = false", "indent = 2, ensure_ascii = true")


def _unresolved_key_control(check: CheckRow) -> None:
    """(jjjjjj) a census key that does not resolve is refused at load.

    A `vary` control naming a row nobody records, a `[fixtures] dir` that is
    not a directory, a json-fields sample that will not read: each is a fact
    about the census and the manifest, knowable before anything runs, and
    each was a disclosed SKIP of its control under `capture complete` — a
    golden written under a pin or a fold nobody proved. `check_controls`
    holds the first, `load_census` the rest.

    Every refused case sits beside a sibling that LOADS, so no case passes by
    refusing everything; the loading control is the SKIP that stays — a
    `vary` control on a row whose command is not on this machine. The last
    clause is the defect refusal left in the control's place: a census handed
    to the controls with a manifest it was not loaded with is golden-census's
    own fault, and it says so rather than filing a SKIP.
    """
    label = ("jjjjjj  a census key that does not resolve is REFUSED when the "
             "files are read, naming the key, where it was a SKIP under "
             "`capture complete`: a `vary` control on a row the manifest does "
             "not record, a `vary` control on a `skip` surface, a `[fixtures] "
             "dir` that is not a directory, a json-fields `sample` or "
             "`moved` file that is missing, one that is not UTF-8 text, "
             "a json-fields row in a census with no `[fixtures]`, and two "
             "json-fields rows that ask for different `serialization`; "
             "while a `vary` control on a row "
             "whose command is not on this machine still LOADS and is a "
             "disclosed SKIP when the controls run, the controls handed a "
             "manifest the census was not loaded with refuse as a "
             "golden-census defect")
    said: dict[str, str] = {}
    control_rows: list[tuple[str, bool, str, str]] = []
    control_skips: list[tuple[str, str]] = []

    def loaded(box: str, census: str, manifest: str = _STUB_MANIFEST,
               sample: bytes | None = _RED_SAMPLE.encode(),
               moved: bytes | None = _RED_MOVED.encode()) -> str:
        path = _scratch(box, manifest_text=manifest, census_text=census)
        for name, content in (("sample.json", sample), ("moved.json", moved)):
            if content is not None:
                pathlib.Path(os.path.join(box, name)).write_bytes(content)
        return _printed_refusal(functools.partial(load_manifest, path),
                                unrefused="LOADED").replace(box, "<box>")

    no_fixtures = _JSON_FIXTURES_CENSUS.replace('\n[fixtures]\ndir = "."\n', "")
    # Each case: the census, the manifest, and the fixture files that differ
    # from the two good ones (`None` leaves a file out).
    cases: dict[str, tuple[str, str, dict[str, bytes | None]]] = {
        "a `vary` on a row not recorded": (_VARY_TYPO_CENSUS, _STUB_MANIFEST,
                                            {}),
        "a `vary` on a `skip` surface": (_VARY_SKIP_CENSUS,
                                         _VARY_SKIP_MANIFEST, {}),
        "a json-fields census beside its files": (_JSON_FIXTURES_CENSUS,
                                                  _STUB_MANIFEST, {}),
        "a [fixtures] dir that is not a directory": (
            _JSON_FIXTURES_CENSUS.replace('dir = "."', 'dir = "fixtrues"'),
            _STUB_MANIFEST, {}),
        "a missing sample": (_JSON_FIXTURES_CENSUS, _STUB_MANIFEST,
                             {"sample": None}),
        "a missing moved file": (_JSON_FIXTURES_CENSUS, _STUB_MANIFEST,
                                 {"moved": None}),
        "a sample that is not UTF-8": (_JSON_FIXTURES_CENSUS, _STUB_MANIFEST,
                                       {"sample": b'{"commit": "\xff\xfe"}'}),
        "no [fixtures]": (no_fixtures, _STUB_MANIFEST, {}),
        "two serializations": (_JSON_TWO_WAYS_CENSUS, _STUB_MANIFEST, {}),
        "two ensure_ascii": (_JSON_TWO_ASCII_CENSUS, _STUB_MANIFEST, {}),
    }
    for key, (census, manifest, files) in cases.items():
        with _box("golden-census-unresolved-") as box:
            said[key] = loaded(box, census, manifest, **files)

    with _box("golden-census-unresolved-") as box:
        manifest_loaded = load_manifest(_scratch(box, manifest_text=_ABSENT_MANIFEST))
        roots = Roots(root=manifest_loaded.subject.root, work=box, clone=None)
        control_rows, control_skips = _census_rows(manifest_loaded, roots)

    with _box("golden-census-unresolved-") as box:
        clean = load_manifest(_scratch(box))
        typo_path = os.path.join(box, "typo-census.toml")
        pathlib.Path(typo_path).write_text(_VARY_TYPO_CENSUS, encoding="utf-8")
        typo = load_census(typo_path)
        roots = Roots(root=clean.subject.root, work=box, clone=None)
        said["the controls handed another census"] = _printed_refusal(
            lambda: census_controls(typo, clean, roots,
                                    lambda *_row, **_next: None,
                                    lambda *_skip: None),
            unrefused="NO REFUSAL").replace(box, "<box>")


    wanted = {
        "a `vary` on a row not recorded": (
            "'_subject/hlep', which is no `run` row this manifest records",),
        "a `vary` on a `skip` surface": (
            "'_subject/gone', which is no `run` row this manifest records",),
        "a [fixtures] dir that is not a directory": (
            "[fixtures] dir 'fixtrues' names <box>/fixtrues, which is not a "
            "directory",),
        "a missing sample": (
            "`sample` file <box>/sample.json cannot be read",),
        "a missing moved file": (
            "`moved` file <box>/moved.json cannot be read",),
        "a sample that is not UTF-8": (
            "`sample` file <box>/sample.json is not UTF-8 text",),
        "no [fixtures]": ("has no [fixtures] dir",
                          "holds sample.json and moved.json"),
        "two serializations": (
            "rows 'a field that moves in a written document' and 'a second "
            "field' ask for different `serialization`",),
        "two ensure_ascii": (
            "rows 'a field that moves in a written document' and 'a second "
            "field' ask for different `serialization`",),
        "the controls handed another census": ("'_subject/hlep'",
                                               "golden-census defect"),
    }
    refused_right = all(said[key].startswith("REFUSED: census <box>/")
                        and all(needle in said[key] for needle in needles)
                        for key, needles in wanted.items())
    skipped_here = (not control_rows and len(control_skips) == 1
                    and control_skips[0][1].startswith(
                        "the first run under the pin would not start: "))
    check(label,
          refused_right
          and said["a json-fields census beside its files"] == "LOADED"
          and skipped_here,
          ACTUAL + "; ".join(f"{key} -> {_one_line(_from_row(text), DIFFERENCE)}"
                                 for key, text in said.items())
          + f"; a `vary` on a command not on this machine -> "
          f"{len(control_rows)} row(s), skip(s) "
          f"{[_one_line(reason, 60) for _label, reason in control_skips]}",
          next="`census.check_controls`, called by `load_manifest` beside "
               "`check_scopes`, refuses a `vary` control outside the "
               "manifest's `run` rows; `load_census` refuses the `[fixtures] "
               "dir` and reads each json-fields control's two files. If a "
               "planted case loads, that check has gone and its control is a "
               "SKIP again; if the clean sibling is refused, the check is "
               "refusing a census that resolves.")


#: (kkkkkk) a census file carrying a key golden-census does not read, at the
#: top of the file where no table has opened yet.
_UNREAD_TOP_KEY_CENSUS = "planted = 1\n" + _STUB_CENSUS


def _census_prefix_control(check: CheckRow, skip: SkipRow) -> None:
    """(kkkkkk) every refusal about a census file opens `census <path>: `.

    The census's other refusals always did; the four `load_toml` raises for
    a file that is missing, does not parse, will not open or is not UTF-8
    opened `census: <path>` instead — the one spelling a reader matching the
    rest would miss. The manifest's own sentences are the control: they have
    no prefix and must not move. A census path that exists and is not a file
    — a directory — reads `is not a file`: `no such file` would be false. A
    link to nothing does not exist and stays `no such file`; a manifest path
    that is a directory stays `no manifest at <path>`.
    """
    label = ("kkkkkk  a census that is missing, is a link to nothing, is a "
             "directory, does not parse, is not UTF-8 text or carries a key "
             "golden-census does not read is refused in one spelling, "
             "`census <path>: ` and then what is wrong — the opening every "
             "other census refusal has, and for a directory `is not a "
             "file`, never `no such file` — while a manifest that "
             "does not parse still reads `the manifest <path> does not "
             "parse` and one that is a directory `no manifest at <path>`")
    said: dict[str, str] = {}
    with _box("golden-census-census-prefix-") as box:
        path = os.path.join(box, "census.toml")

        def census_said(content: bytes | None) -> str:
            if content is not None:
                pathlib.Path(path).write_bytes(content)
            return _printed_refusal(functools.partial(load_census, path),
                                    unrefused="LOADED").replace(box, "<box>")

        said["missing"] = census_said(None)
        os.symlink(os.path.join(box, "absent"), path)
        said["a link to nothing"] = census_said(None)
        os.remove(path)
        os.mkdir(path)
        said["a directory"] = census_said(None)
        os.rmdir(path)
        said["unparsable"] = census_said(
            (_STUB_CENSUS + "\nthis line is not TOML =\n").encode())
        said["not UTF-8"] = census_said(_CENSUS_BYTES)
        said["an unread key"] = census_said(_UNREAD_TOP_KEY_CENSUS.encode())
        manifest = _scratch(box, manifest_text=_STUB_MANIFEST
                            + "\nthis line is not TOML =\n")
        said["an unparsable manifest"] = _printed_refusal(
            functools.partial(load_manifest, manifest),
            unrefused="LOADED").replace(box, "<box>")
        os.remove(manifest)
        os.mkdir(manifest)
        said["a manifest that is a directory"] = _printed_refusal(
            functools.partial(load_manifest, manifest),
            unrefused="LOADED").replace(box, "<box>")
    here = "REFUSED: census <box>/census.toml: "
    wanted = {
        "missing": here + "no such file",
        "a link to nothing": here + "no such file",
        "a directory": here + "is not a file",
        "unparsable": here + "does not parse: TOMLDecodeError",
        "not UTF-8": here + "is not UTF-8 text: UnicodeDecodeError",
        "an unread key": here + "the census carries a key",
        "an unparsable manifest": "REFUSED: the manifest <box>/manifest.toml "
                                  "does not parse: TOMLDecodeError",
        "a manifest that is a directory": "REFUSED: no manifest at "
                                          "<box>/manifest.toml",
    }
    check(label,
          all(said[key].startswith(opening) for key, opening in wanted.items()),
          ACTUAL + "; ".join(f"{key} -> {_one_line(text, 110)}"
                                 for key, text in said.items()),
          next="`census.load_census` hands `load_toml` the prefix "
               "`census <path>: `, and `load_toml` names a prefixed file by "
               "that prefix alone. If a line opens `census: <path>`, the old "
               "prefix is back; if the directory reads `no such file`, "
               "`load_toml` lost its test for a path that exists; if the "
               "manifest's line moved, a sentence without a prefix changed "
               "too.")


#: Arm `yyyyy`'s subject. It lives in `tree/` under the arm's box, so the
#: subject root can be that directory or a symbolic link to it.
_ROOT_SWALLOW_SUBJECT = '''\
import os
import sys

mode = sys.argv[1]
if mode == "--scan":
    print("scanned", os.path.join(sys.argv[2], "out", "artifacts"))
elif mode == "--cwd":
    print("scanned", os.path.join(os.getcwd(), "out", "artifacts"))
elif mode == "--timed":
    print("scanned", sys.argv[2], "in 12ms")
elif mode == "--made":
    made = os.path.join(os.environ["TMPDIR"], "sub-abc123")
    os.makedirs(made, exist_ok=True)
    print("made", made)
else:
    print("nothing of the root here")
'''

_ROOT_SWALLOW_MANIFEST = _subject("swallow", root="{root}") + '''
[inputs._subject]
args     = []
surfaces = ["scan", "other"]

[surfaces.scan]
args = [{scan}]

[surfaces.other]
args = ["--other"]
'''

_ROOT_SWALLOW_CENSUS = _STUB_ENVIRONMENT + '''{pin}{root}
[[input]]
name        = "the swallowing fold"
disposition = "fold"
kind        = "regex"
pattern     = '{pattern}'
placeholder = "{placeholder}"
{scope}finding     = "a path reaches a report and moves with the machine"
control     = { sample = "read A/x", moved = "read B/x" }
'''


def _root_swallow_pin(width: int) -> str:
    """A consumer's shape: the subject's TMPDIR pinned to the fixed-width
    directory, which a fold of the consumer's own rewrites whole."""
    return (_fixed_pin(width, "the subject makes its own directories under TMPDIR")
            + _fixed_fold("the directory golden-census made for the subject to run under"))


#: The consumer's shape: the directory one level under a fixed prefix — here
#: the case's own directory, `{name}` — so the group takes `tree`, the root's
#: last component, and leaves the rest of the root: a SPLIT. Scoped to the
#: row that prints the root, as the load-time refusal would have sent a
#: reader to scope it, and `check_fold_overlap` walks no scoped fold.
_SPLIT_PATTERN = "/{name}/(?P<volatile>[^/ ]+)"
_TO_SCAN = 'scope       = ["_subject/scan"]\n'

#: A group that takes the whole root and the text after it: nothing of the
#: root is left for the root fold to miss.
_WHOLE_PATTERN = r"(?P<volatile>/\S+/out/artifacts)"


def _root_swallow_capture(box: str, name: str, *, scan: str,
                          pattern: str = _SPLIT_PATTERN,
                          placeholder: str = "<SCRATCHROOT>",
                          scope: str = 'scope       = "*"\n', pin: str = "",
                          link: bool = False) -> tuple[bool, str, str, str]:
    """One scratch subject captured into `<box>/<name>/out`, `{name}` in the
    pattern spelled as `name`.

    `(loaded, verdict, the recorded _subject/scan.out, the subject root)`,
    the verdict being `exit N` or the refusal's text. `capture.capture` is
    called directly, so the scratch census's controls do not run: what this
    arm is about is the capture's own refusal.
    """
    where = os.path.join(box, name)
    tree = os.path.join(where, "tree")
    os.makedirs(tree)
    pathlib.Path(os.path.join(tree, "stub.py")).write_text(_ROOT_SWALLOW_SUBJECT, encoding="utf-8")
    root = "tree"
    if link:
        os.symlink(tree, os.path.join(where, "link"))
        root = "link"
    path = _scratch(
        where,
        manifest_text=_ROOT_SWALLOW_MANIFEST.replace("{root}", root)
        .replace("{scan}", scan),
        census_text=_ROOT_SWALLOW_CENSUS.replace("{pin}", pin)
        .replace("{root}", _STUB_ROOT_FOLD)
        .replace("{pattern}", pattern.replace("{name}", name))
        .replace("{placeholder}", placeholder)
        .replace("{scope}", scope))
    try:
        manifest = load_manifest(path)
    except Refusal as refused:
        return False, refusal_text(refused), "", ""
    out = os.path.join(where, "out")
    try:
        verdict = f"exit {capture(manifest, out, io.StringIO())}"
    except Refusal as refused:
        return True, refusal_text(refused), "", manifest.subject.root
    # Read only what a capture landed: one that exited non-zero landed
    # nothing, and its exit code is the verdict.
    recorded = (read_capture(out, "--out").get("_subject/scan.out", "")
                if verdict == "exit 0" else "")
    return True, verdict, recorded, manifest.subject.root


def _root_swallow_control(check: CheckRow, skip: SkipRow) -> None:
    """(yyyyy) a `regex` fold whose `volatile` group would SPLIT the subject
    root in what a row printed — replace part of it and leave a fragment —
    is REFUSED during the capture, naming the row, the fold, the pattern and
    the replaced text.

    `check_fold_overlap` tests the bare root at load, and only for folds that
    apply to every row; the claim case is the consumer's shape scoped to the
    row that prints the root, which loads, and this is the test that sees it,
    in `normalize_text`, where every regex fold a recorded row meets runs. The
    root is found in both spellings `core.path_forms` names, so a subject
    that prints its resolved working directory under a root reached through a
    link is caught too.

    A group that takes the WHOLE root and the text after it is no split: it
    loads and captures its placeholder, the same on every machine. Three more
    controls say it is about the subject root and nothing wider: the same
    fold scoped to a row that prints no root captures; a fold whose group
    sits BESIDE the root on the same line captures; and a fold
    that rewrites a directory the subject made under its pinned fixed-width
    TMPDIR captures — the directory a consumer's fold is allowed to rewrite.
    That last case needs a temp root narrow enough for the pin, and is a
    disclosed SKIP of its own under a wider one. The census's own path fold
    control reaches the same test through the same function, and reports it
    as its own red row naming the reader's fold — not as a refusal naming
    `control/path`, a row no manifest has.

    Each capture calls `capture.capture` directly, so the scratch census's
    controls do not run.
    """
    label = ("yyyyy  a `regex` fold whose `volatile` group would SPLIT the "
             "subject root in a row's text — replace part of it and leave a "
             "fragment — is REFUSED during the capture, naming the row, the "
             "fold, the pattern and the text it replaces, where a fold scoped "
             "to that row loads; the root is found in its resolved spelling "
             "too; a group taking the whole root and more captures its "
             "placeholder; the same fold scoped to a row that prints no root, "
             "a fold beside the root and not over it, and a fold rewriting "
             "the subject's pinned fixed-width temp directory all capture; "
             "and the path fold control over the root reports the same fault "
             "as its own red row, naming the fold")
    _normalized, room = fixed_dir_room(temp_base(), FIXED_DIR_WIDTH)
    with _box("golden-census-root-swallow-") as box:
        claim = _root_swallow_capture(box, "claim", scan='"--scan", "<ROOT>"',
                                      scope=_TO_SCAN)
        whole = _root_swallow_capture(box, "whole", scan='"--scan", "<ROOT>"',
                                      pattern=_WHOLE_PATTERN)
        resolved = _root_swallow_capture(box, "resolved", scan='"--cwd"',
                                         scope=_TO_SCAN, link=True)
        link_path = os.path.join(box, "resolved", "link")
        real_path = os.path.realpath(link_path)
        remedy = _root_swallow_capture(
            box, "remedy", scan='"--scan", "<ROOT>"',
            scope='scope       = ["_subject/other"]\n')
        beside = _root_swallow_capture(
            box, "beside", scan='"--timed", "<ROOT>"',
            pattern=r"(?P<volatile>\b\d+ms\b)", placeholder="<DURATION>")
        fixed: tuple[bool, str, str, str] | None = None
        if room >= 1:
            fixed = _root_swallow_capture(
                box, "fixed", scan='"--made"',
                pin=_root_swallow_pin(FIXED_DIR_WIDTH),
                pattern=r"(?P<volatile>/(?:\S*/)?sub-[A-Za-z0-9]+)",
                placeholder="<SUBDIR>")
        control = "no row"
        census, roots = _swallowing_census(os.path.join(box, "control"))
        try:
            rows = _path_fold_rows(census, roots, "root")
            if rows:
                control = ("red" if not rows[0][1] else "green") + ": " \
                    + rows[0][2]
        except Refusal as refused:
            control = "raised: " + refusal_text(refused)
        root = claim[3]
    if fixed is None:
        skip("yyyyy  (the fixed-width temp directory case)",
             f"the temp root {_normalized!r} is {len(_normalized)} characters "
             f"wide, too wide for the pinned <FIXED-WIDTH-DIR:"
             f"{FIXED_DIR_WIDTH}>, so this case cannot be built. The other "
             "cases ran. Nothing is claimed for this one.")
    said = claim[1]
    claimed = (claim[0] and said.startswith("REFUSED: ")
               and "the text of _subject/scan" in said
               and "row 'the swallowing fold'" in said
               and "its pattern " + repr(_SPLIT_PATTERN.replace(
                   "{name}", "claim")) in said
               and f"replaces {os.path.basename(root)!r}" in said)
    # The group takes everything from the first `/` after "scanned " to the
    # end of the line: the whole root, so nothing is left of it to miss.
    whole_ok = (whole[0] and whole[1] == "exit 0"
                and whole[2] == "scanned <SCRATCHROOT>\n")
    resolved_ok = (link_path != real_path
                   and resolved[1].startswith("REFUSED: ")
                   and "the text of _subject/scan" in resolved[1]
                   and f"replaces {os.path.basename(real_path)!r}"
                   in resolved[1])
    remedied = (remedy[1] == "exit 0"
                and remedy[2] == "scanned <REPO>/out/artifacts\n")
    beside_ok = (beside[1] == "exit 0"
                 and beside[2] == "scanned <REPO> in <DURATION>\n")
    fixed_ok = fixed is None or (fixed[1] == "exit 0"
                                 and fixed[2] == "made <SUBDIR>\n")
    # A red ROW of the control's own, naming the reader's fold — never a
    # refusal naming `control/path`, a row no manifest has.
    controlled = (control.startswith("red: ")
                  and "your fold 'the scratch directories of this machine' "
                      "rewrites the subject root in golden-census's sample "
                      "text" in control
                  and "control/path" not in control)

    def shown(text: str) -> str:
        return _one_line(text.replace(box, "<box>"), 150)

    check(label,
          claimed and whole_ok and resolved_ok and remedied and beside_ok
          and fixed_ok and controlled,
          f"{ACTUAL}the splitting fold scoped to the row -> "
          f"loaded={claim[0]}, {shown(said)}; the whole-root fold -> "
          f"loaded={whole[0]}, {shown(whole[1])}, {whole[2]!r}; "
          f"the root through a link, the subject printing its resolved cwd "
          f"-> {shown(resolved[1])}; scoped to _subject/other -> "
          f"{remedy[1]}, {remedy[2]!r}; beside the root -> {beside[1]}, "
          f"{beside[2]!r}; the fixed-width temp directory -> "
          + (f"{fixed[1]}, {fixed[2]!r}" if fixed is not None
             else "SKIPPED (see below)")
          + f"; the path fold control over the root -> {shown(control)}",
          next="`census.normalize_text` runs `census._root_overlap` before "
               "each in-scope regex fold; read the detail for which case "
               "moved.")


#: One planted key per table arm `qqqqq` covers, as (the text a table is found
#: by, the key planted under it). Every one is spelled the way a reader would
#: mistype it: `command` is a real key of another table, `sha256` is what a
#: reader writes for `sha`, and `width` is a key no census has ever had.
_UNKNOWN_KEY_PLANTS: tuple[tuple[str, str, str], ...] = (
    ("manifest", "[surfaces.help]", 'command = ["nonsense"]'),
    ("manifest", "[subject]", "misspelled = true"),
    ("manifest", "[inputs._subject]", 'sha256 = "abc"'),
    ("manifest", "[[setup]]", 'cwd = "."'),
    ("manifest", "[[movements]]", 'why = "it moved"'),
    ("census", 'disposition = "state"', "width = 80"),
    # A key of ANOTHER disposition, and the one the common list used to carry:
    # only a pin and a fold read a `control`, and on a `state` row it was
    # accepted and dropped — the defect this arm exists for, let through by
    # this arm's own list.
    ("census", 'disposition = "state"',
     'control = { shape = "vary", surface = "_subject/help", value = "40" }'),
    # A key of a table INSIDE a row: a json-fields fold's `serialization`,
    # with `indent` spelled in the wrong case.
    ("census", 'kind        = "json-fields"', "serialization = { Indent = 2 }"),
    # `serialization` itself, spelled right, on the two fold kinds that do
    # not read it: a `regex` fold with a table a json-fields fold would take
    # whole, and a `path` fold.
    ("census", 'kind        = "regex"',
     "serialization = { indent = 2, ensure_ascii = false }"),
    ("census", 'kind        = "path"', "serialization = { indent = 2 }"),
)

#: The two tables the stub files do not carry, added so the plants above have
#: something to land in. Both are clean: the arm loads this pair untouched as
#: its own control.
_UNKNOWN_KEY_MANIFEST = _STUB_MANIFEST + '''
[[setup]]
name    = "a setup the plants land in"
command = ["<PYTHON>", "stub.py"]

[[movements]]
path        = "_subject/help.out"
attribution = "a movement the plants land in"
'''

_UNKNOWN_KEY_CENSUS = _STUB_CENSUS + '''
[[input]]
name        = "the tool versions this capture was taken under"
disposition = "state"
commands    = [["<PYTHON>", "--version"]]
finding     = "a planted state row, for the unknown-key guard"

[[input]]
name        = "a planted json-fields fold, for the unknown-key guard"
disposition = "fold"
kind        = "json-fields"
paths       = ["provenance"]
fields      = ["commit"]
placeholder = "<PROVENANCE>"
finding     = "a planted json-fields fold, for the unknown-key guard"
control     = { sample = "sample.json", moved = "moved.json" }

[[input]]
name          = "a json-fields fold whose serialization is clean"
disposition   = "fold"
kind          = "json-fields"
paths         = ["provenance"]
fields        = ["commit"]
placeholder   = "<PROVENANCE>"
serialization = { indent = 2, ensure_ascii = false }
finding       = "a clean json-fields fold, for the unknown-key guard's control"
control       = { sample = "sample.json", moved = "moved.json" }

[[input]]
name        = "a planted regex fold, for the unknown-key guard"
disposition = "fold"
kind        = "regex"
pattern     = 'built (?P<volatile>[0-9]+)'
placeholder = "<STAMP>"
finding     = "a planted regex fold, for the unknown-key guard"
control     = { sample = "built 1", moved = "built 2" }

[[input]]
name        = "a planted path fold, for the unknown-key guard"
disposition = "fold"
kind        = "path"
source      = "work"
placeholder = "<WORK>"
finding     = "a planted path fold, for the unknown-key guard"

[fixtures]
dir = "."
'''

#: The two documents the planted json-fields fold's control names.
_UNKNOWN_KEY_FIXTURES = {"sample.json": _RED_SAMPLE, "moved.json": _RED_MOVED}

#: A mutants file the plant lands in. Nothing runs it: `load_mutants` is the
#: whole of what this arm asks of it, so no subject and no clone is needed.
_UNKNOWN_KEY_MUTANTS = '''\
[checks.version]
command = ["<PYTHON>", "stub.py", "--version"]
fires   = "exit-nonzero"

[[mutant]]
name    = "a planted mutant, for the unknown-key guard"
file    = "stub.py"
find    = "VERSION"
replace = "RELEASE"
expect  = ["version"]
'''


def _unknown_key_control(check: CheckRow) -> None:
    """(qqqqq) a table of any of the three files carrying a key its loader does
    not read is REFUSED when the file is read.

    A key nobody reads is a key its author believes is doing something, and
    that belief is the whole defect: the manifest goes on saying what the
    author meant and golden-census goes on doing something else, in silence.
    The mutants file is in for a reason of its own — an agent should not have
    to remember which of the three files golden-census reads is the strict one.

    Both halves matter equally. The refusal has to name the key, the table and
    the keys the table takes, because those three are what a reader needs to
    fix the line without opening a document; and the same files with the keys
    removed have to LOAD, because a rule that refuses a good file is not a
    stricter rule, it is a broken one.

    A json-fields fold's `serialization` is a table inside a row: its
    refusal names the row and `serialization`, and the two keys that table
    takes, never the row's. On a `regex` or a `path` fold, `serialization`
    is a key the row does not read, refused as one. Every refusal's `next:`
    names the format document of the file it was found in. A json-fields
    fold carrying a clean `serialization`, and a regex and a path fold
    carrying none, are in the files the control loads.
    """
    label = ("qqqqq  a key golden-census does not read, in a manifest table, "
             "an input table, a setup, a movement, a census row, a "
             "json-fields fold's `serialization` table, and the key on any "
             "other fold, or a mutant, "
             "is REFUSED when the file is read — naming the key, the table it "
             "is in and the keys that table takes, with a `next:` naming that "
             "file's format document — while the same files without those "
             "keys load")
    verdicts: dict[str, str] = {}
    for which, anchor, plant in _UNKNOWN_KEY_PLANTS:
        with _box("golden-census-unknown-key-") as box:
            manifest_text, census_text = (_UNKNOWN_KEY_MANIFEST,
                                          _UNKNOWN_KEY_CENSUS)
            planted = anchor + "\n" + plant
            if which == "manifest":
                manifest_text = manifest_text.replace(anchor, planted, 1)
            else:
                census_text = census_text.replace(anchor, planted, 1)
            path = _scratch(box, manifest_text=manifest_text,
                            census_text=census_text,
                            extra=_UNKNOWN_KEY_FIXTURES)
            verdicts[plant] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")

    # The mutants file is read by a loader of its own, which no manifest load
    # reaches, so its plant is a load of its own.
    with _box("golden-census-unknown-key-") as box:
        mutants_path = os.path.join(box, "mutants.toml")
        planted_mutant = "why = \"it was planted\""
        pathlib.Path(mutants_path).write_text(_UNKNOWN_KEY_MUTANTS.replace(
            "[[mutant]]", "[[mutant]]\n" + planted_mutant, 1), encoding="utf-8")
        verdicts[planted_mutant] = _printed_refusal(
            functools.partial(load_mutants, mutants_path), unrefused="LOADED")

    # The control: the same three files with nothing planted. A guard that
    # cannot say yes is a guard that says nothing.
    clean = ""
    with _box("golden-census-unknown-key-") as box:
        path = _scratch(box, manifest_text=_UNKNOWN_KEY_MANIFEST,
                        census_text=_UNKNOWN_KEY_CENSUS,
                        extra=_UNKNOWN_KEY_FIXTURES)
        mutants_path = os.path.join(box, "mutants.toml")
        pathlib.Path(mutants_path).write_text(_UNKNOWN_KEY_MUTANTS, encoding="utf-8")
        clean = _printed_refusal(
            lambda: (load_manifest(path), load_mutants(mutants_path)),
            unrefused="LOADED")

    planted_keys = ("command", "misspelled", "sha256", "cwd", "why", "width",
                    "control", "Indent", "serialization", "serialization",
                    "why")
    said = list(verdicts.values())
    # Three things in every sentence: the key, so the reader knows which line;
    # the table, so they know which of their tables; and the keys that table
    # takes, which is the answer to the question a misspelling asks.
    named = all(
        text.startswith("REFUSED: ")
        and "does not read: " in text and "That table takes " in text
        for text in said)
    # `strict`: the plants and the verdicts are one list said twice, and a
    # length that has drifted is a plant nobody checked, not a shorter loop.
    keys_named = all(f"does not read: {key}" in text
                     for key, text in zip(planted_keys, said, strict=True))
    # A table INSIDE a row is named by the row and its own key, and the keys
    # it takes are its own two, not the row's.
    serialized = ("row 'a planted json-fields fold, for the unknown-key "
                  "guard': serialization carries a key golden-census does "
                  "not read: Indent. That table takes ensure_ascii, indent.\n"
                  in verdicts["serialization = { Indent = 2 }"])
    # Each refusal's `next:` sends the reader to the format document of the
    # file the key was found in, by its full path under this layout's `docs`:
    # the name is spelled here and not imported, so a loader handed another
    # file's document is seen, and the directory is the layout's, so the
    # arm holds in a checkout and in an install alike.
    docs = os.path.join(Layout.detect().data, "docs")
    documents = {"manifest": os.path.join(docs, "manifest-format.md"),
                 "census": os.path.join(docs, "census-format.md"),
                 "mutants": os.path.join(docs, "mutants-format.md")}
    pointed = all(
        "\n  next: Fix the spelling, or delete that key. "
        f"{documents[which]} is authoritative for every key of this table."
        in verdicts[plant]
        for which, plant in [(which, plant)
                             for which, _, plant in _UNKNOWN_KEY_PLANTS]
        + [("mutants", planted_mutant)])
    check(label,
          named and keys_named and serialized and pointed
          and clean == "LOADED",
          ACTUAL + ", ".join(
              # After `REFUSED: ` and nothing more: each sentence still opens
              # with the scratch file's absolute path, which a red row prints
              # and a green one never shows.
              f"{plant.partition(' =')[0]} -> "
              f"{_one_line(text.partition(': ')[2] or text, 95)}"
              for plant, text in verdicts.items())
          + "; the serialization refusal names its row, `serialization` and "
          f"the two keys that table takes={serialized}"
          + f"; every `next:` names its own file's format document={pointed}"
          + f"; the same three files with none of them: {clean}",
          next="Each loader declares the keys it reads in a tuple beside the "
               "function that reads them, and `core.only_keys` is the one "
               "place the refusal is written. If a plant above now loads, "
               "either that key is read now — add it to that tuple and to its "
               "format document — or the `only_keys` call for that table has "
               "gone and a key golden-census ignores is silent again.")


#: The names arm `wwwww` plants, as (what is planted, the table appended to the
#: stub manifest). Each is added BESIDE the stub's good rows rather than
#: renaming them, so the census control's `_subject/help` still names a row
#: that exists and every refusal below is the name rule's and not a
#: cross-reference's. The absolute spellings are built from `os.sep` — a path
#: typed here would be a path of whichever machine it was typed on.
_ESCAPING_NAME_PLANTS: tuple[tuple[str, str], ...] = (
    ("surface a/b", '\n[surfaces."a/b"]\nargs = ["--help"]\n'),
    ("surface ../escaped", '\n[surfaces."../escaped"]\nargs = ["--help"]\n'),
    ("surface absolute",
     f'\n[surfaces."{os.path.join(os.sep, "absolute")}"]\nargs = ["--help"]\n'),
    ("surface empty", '\n[surfaces.""]\nargs = ["--help"]\n'),
    ("input ../up", '\n[inputs."../up"]\nargs = []\nsurfaces = ["help"]\n'),
    ("input ..", '\n[inputs.".."]\nargs = []\nsurfaces = ["help"]\n'),
    ("files ../escaped-file.txt",
     '\n[files."../escaped-file.txt"]\nlines = ["one line"]\n'),
    ("files absolute",
     f'\n[files."{os.path.join(os.sep, "escaped-file.txt")}"]\n'
     'lines = ["one line"]\n'),
    # The two that leave nothing: they resolve to a DIRECTORY under the work
    # directory rather than above it, and `write_files` opened each of them
    # and raised `IsADirectoryError` at exit 1.
    ("files fixtures/", '\n[files."fixtures/"]\nlines = ["one line"]\n'),
    ("files .", '\n[files."."]\nlines = ["one line"]\n'),
)

#: The same two spellings asked as a mutant's `file`, which `mutants.preflight`
#: puts to the same helper with the other noun and the other directory. No
#: clone and no `git`: `preflight` runs before either.
_ESCAPING_MUTANT_FILES = ("fixtures/", os.curdir)

#: Rule 2's control, and the case the rule must not break: a nested relative
#: path is what a `files` key exists for.
_NESTED_FILES_PLANT = '''
[files."fixtures/a.txt"]
lines = ["a line of a nested fixture"]

[files."a.txt"]
lines = ["a line of a fixture beside it"]
'''


def _escaping_name_control(check: CheckRow) -> None:
    """(wwwww) a surface or input name that is not one path component, and a
    `files` key that does not stay under the work directory, are each REFUSED
    when the manifest is read.

    All three names become paths: `<out>/<input>/<surface>.<ext>` for the
    first two and a file under the work directory for the third. `os.path.join`
    discards what it is joining onto when the second element is absolute and
    the filesystem resolves `..` without comment, so before this rule a surface
    named `../escaped` wrote its three files one directory above the input's
    own, an input named `../up` wrote a whole directory outside `--out`, and a
    `files` key could be written anywhere on the machine — every one of them
    with the capture exiting 0 and printing `capture complete`. A key that
    resolves to a DIRECTORY leaves nothing at all and is the same rule read
    the other way: `fixtures/` and `.` were joined onto the work directory and
    opened, and `IsADirectoryError` came out of `write_files` at exit 1.

    The two controls are the point of the arm as much as the refusals.
    A nested `files` key has to go on loading, because that is what the key is
    for; and the stub's own ordinary names have to load, because a rule that
    refuses a good manifest is not a stricter rule.
    """
    label = ("wwwww  a surface name or an input name that is not one path "
             "component, and a `files` key whose every component does not "
             "NAME something under <WORK> — absolute, climbing with `..`, or "
             "resolving to a directory — are each REFUSED when the manifest "
             "is read, naming the table as the author wrote it; the same two "
             "directory spellings are refused "
             "as a mutant's `file`; while a nested relative `files` key and "
             "the ordinary names beside them load")
    verdicts: dict[str, str] = {}
    for key, plant in (_ESCAPING_NAME_PLANTS
                       + (("nested files", _NESTED_FILES_PLANT),
                          ("ordinary names", ""))):
        with _box("golden-census-escaping-name-") as box:
            path = _scratch(box, manifest_text=_STUB_MANIFEST + plant)
            try:
                verdicts[key] = _printed_refusal(
                    functools.partial(load_manifest, path), unrefused="LOADED")
            except Exception as exc:    # a load that raises is this row's red
                if isinstance(exc, UNREPORTABLE):
                    raise
                verdicts[key] = f"RAISED {type(exc).__name__}: {exc}"

    # The mutant half, through `preflight` and not through the helper: what is
    # being shown is that the OTHER caller of the one rule is still wired to
    # it, which a direct call to the helper would not show.
    mutant_said: dict[str, str] = {}
    with _box("golden-census-escaping-name-mutant-") as box:
        manifest = load_manifest(_scratch(box))
        for spelled in _ESCAPING_MUTANT_FILES:
            try:
                preflight(manifest, (Mutant("m", spelled, "find", "replace"),))
                mutant_said[spelled] = "ACCEPTED"
            except Refusal as refused:
                mutant_said[spelled] = refusal_text(refused)

    # The bracket the refusal must print is the plant's own first line, read
    # from the plant rather than listed a second time: a table named one way
    # in the plant and another in the assertion is an assertion about nothing.
    named = True
    for key, plant in _ESCAPING_NAME_PLANTS:
        bracket = plant.strip().splitlines()[0]
        rule = ("must be a relative path under <WORK>"
                if bracket.startswith("[files.")
                else "is one path component")
        named = named and (verdicts[key].startswith("REFUSED: ")
                           and bracket in verdicts[key]
                           and rule in verdicts[key])
    mutant_rule = ("a mutant's `file` must be a relative path under the "
                   "subject root")
    mutants_refused = all(
        said.startswith("REFUSED: ") and mutant_rule in said
        for said in mutant_said.values())
    check(label,
          named and mutants_refused
          and verdicts["nested files"] == "LOADED"
          and verdicts["ordinary names"] == "LOADED",
          ACTUAL + ", ".join(
              # From the bracket onward: every sentence opens with the scratch
              # manifest's absolute path, which says nothing about the rule and
              # would put a temp directory in a pasted row.
              f"{key} -> {_one_line(text.partition(': [')[2] or text, 70)}"
              for key, text in verdicts.items())
          + "; as a mutant's `file`: " + ", ".join(
              f"{spelled!r} -> {_one_line(said.partition('REFUSED: ')[2] or said, 70)}"
              for spelled, said in mutant_said.items()),
          next="`manifest._one_component` and `manifest._stays_under` own "
               "these two rules, called from `_surfaces`, `_inputs`, `_files` "
               "and `mutants.preflight`. If a plant above now loads, one of "
               "those calls has gone and a manifest can write outside the "
               "capture directory, outside the work directory, or over a "
               "directory again; if `nested files` is refused, the second "
               "rule has stopped allowing the nested fixture path a `files` "
               "key exists for.")


#: The `files` keys arm `tttttt` plants beside the stub's good rows, in the
#: manifest's order, each with the pairs its refusal must name, in the order
#: it must name them: (the key that is the directory, the key below it,
#: whether the two match only once case is folded). The fifth plant has three
#: pairs, spelled so that naming them by the key below would change their
#: order; the sixth spells a pair that matches only once case is folded
#: before one that matches as spelled.
_FILE_ABOVE_FILE_PLANTS: tuple[
        tuple[tuple[str, ...], tuple[tuple[str, str, bool], ...]], ...] = (
    (("a", "a/b.txt"), (("a", "a/b.txt", False),)),
    (("a/b.txt", "a"), (("a", "a/b.txt", False),)),
    (("a", "a/b/c.txt"), (("a", "a/b/c.txt", False),)),
    (("A", "a/b.txt"), (("A", "a/b.txt", True),)),
    (("a", "a/b/c.txt", "a/b"), (("a", "a/b/c.txt", False),
                                 ("a", "a/b", False),
                                 ("a/b", "a/b/c.txt", False))),
    (("A", "a", "a/b.txt"), (("a", "a/b.txt", False),
                             ("A", "a/b.txt", True))),
)

#: The control: keys that share a leading character, a leading name or a
#: directory with another without either being a directory above the other.
_FILE_BESIDE_FILE_PLANTS: tuple[tuple[str, ...], ...] = (
    ("a.txt", "a/b.txt"),
    ("ab", "a/b.txt"),
    ("a/x.txt", "a/b.txt"),
    ("a", "ab"),
    ("a", "a.txt"),
)


#: What the refusal says after the pairs: that the keys name files `capture`
#: writes, and that every command that reads the manifest is refused.
_FILE_ABOVE_FILE_REASON = (
    "A manifest's `files` keys name files `capture` writes under <WORK>, "
    "so a key that is a directory above another would have to be a file and "
    "a directory at once; the manifest is refused for every command, because "
    "no capture could run it.")


def _files_plant(*keys: str) -> str:
    """The `[files."<key>"]` tables for `keys`, in that order, each holding
    one line, to append to `proof._STUB_MANIFEST`."""
    return "".join(f'\n[files."{key}"]\nlines = ["one line"]\n' for key in keys)


def _file_above_file_control(check: CheckRow) -> None:
    """(tttttt) `files` keys of which one is a directory above another are
    REFUSED when the manifest is read, naming every such pair.

    `run.write_files` writes every key as a file under the work directory and
    makes the directories above it first, so `a` and `a/b.txt` ask for `a` to
    be a file and a directory at once. The loader refuses the pair for every
    command, so `capture`, `compare`, `mutants`, `census` and `compare
    --against` all meet the refusal, and none reaches `write_files`, which
    would raise `FileExistsError`, `IsADirectoryError` or
    `NotADirectoryError`, depending on the keys and their order.

    Each plant carries the pairs its refusal must name, in order, and the arm
    asserts exactly that list: which key of a pair is the directory, every
    pair when there are several, and the pairs that match as spelled before
    those that match only once case is folded. The control is the point of
    the arm as much as the refusals: a key that merely starts with the same
    characters as another, or shares its directory, is an ordinary fixture
    and has to go on loading.
    """
    label = ("tttttt  a manifest whose `[files]` names a key that is a "
             "directory above another — `a` and `a/b.txt` in either order, "
             "`a` and `a/b/c.txt`, `A` and `a/b.txt` on a case-insensitive "
             "filesystem, `a`, `a/b/c.txt` and `a/b` (three pairs), and `A`, "
             "`a` and `a/b.txt` (two) — is ONE refusal when the manifest is "
             "read, naming every pair as its two `[files.\"<key>\"]` tables, "
             "the directory first and the pairs that match as spelled before "
             "the others, with a `next:` line, raised by `load_manifest` "
             "itself; the control is `a.txt`, "
             "`ab` and `a/x.txt`, each beside `a/b.txt`, and `ab` and `a.txt`, "
             "each beside `a`, which load")

    def named(pairs: tuple[tuple[str, str, bool], ...]) -> str:
        """The pairs as the refusal must name them, between the manifest's
        path and the sentence that gives the reason."""
        return ": " + "; ".join(
            f'[files."{upper}"] is a directory above [files."{lower}"]'
            + (" on a filesystem that folds case or Unicode normalization"
               if folded_only else "")
            for upper, lower, folded_only in pairs) + ". "

    verdicts: dict[str, str] = {}
    for keys in ([keys for keys, _pairs in _FILE_ABOVE_FILE_PLANTS]
                 + list(_FILE_BESIDE_FILE_PLANTS)):
        with _box("golden-census-file-above-file-") as box:
            path = _scratch(box, manifest_text=_STUB_MANIFEST
                            + _files_plant(*keys))
            verdicts[" + ".join(keys)] = _printed_refusal(
                functools.partial(load_manifest, path), unrefused="LOADED")
    refused = all(
        (said := verdicts[" + ".join(keys)]).startswith("REFUSED: ")
        and named(pairs) in said and "\n  next: " in said
        and _FILE_ABOVE_FILE_REASON in said
        for keys, pairs in _FILE_ABOVE_FILE_PLANTS)
    loaded = all(verdicts[" + ".join(keys)] == "LOADED"
                 for keys in _FILE_BESIDE_FILE_PLANTS)
    check(label, refused and loaded,
          ACTUAL + ", ".join(
              # The pairs a refusal names, between the scratch manifest's
              # absolute path and the reason after them. A load that went
              # through reads `LOADED`.
              f"{key} -> "
              + _one_line(text.partition(".toml: ")[2].partition(
                  ". A manifest's")[0] or text, 200)
              for key, text in verdicts.items()),
          next="`manifest._refuse_file_above_file` owns this rule, called "
               "from `_files`. If a plant above now loads, that call has gone "
               "and the pair reaches `write_files` again; if a refusal names "
               "other pairs, fewer, or another order than its plant expects, "
               "the rule no longer names what it measured; if a control is "
               "refused, the rule has stopped comparing whole path "
               "components.")


#: The state arm `iiiiiii` hands `run.write_files` under a scratch work
#: directory of its own: the keys it is handed, the last of which must be
#: refused, and the number of the error the operating system answers it
#: with. The pair is a plant of the file system, which keeps `A.txt` and
#: `a.txt` apart where it is case-sensitive.
_UNWRITABLE_FILE_PLANTS: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("two spellings of one name", ("A.txt", "a.txt"), errno.EEXIST),
)


def _unwritable_file_control(check: CheckRow, skip: SkipRow) -> None:
    """(iiiiiii) a `[files]` key the operating system will not write is ONE
    refusal from `run.write_files`, on one line, naming the table, the path
    and the operating system's reason, and a capture it stops shows the
    environment as built and leaves nothing behind.

    The loader refuses what the keys alone show; what a file system makes of
    a key only the write finds out: two keys the file system reads as one
    name. The two keys are `A.txt` and `a.txt`: they are one name only on
    some file systems, so the arm first asks whether this one reads them so,
    and where it does not the arm is a disclosed SKIP, never a pass.

    Two halves. The pair is handed to `write_files` directly, under a
    scratch work directory of the arm's own: the refusal's first line must
    end in the table of the second key, `<WORK>/<key>` and `os.strerror` of
    the error, so no exception's name is printed, and its second line must
    be the `next:`. Then one `capture` of the pair, under a private temp
    root, with the subject's TMPDIR pinned to a fixed-width directory that
    the census folds to `<ENGINE-TMPDIR>`: its block opens `about to run`
    over the environment `run.place` built, its TMPDIR line reads
    `<ENGINE-TMPDIR>`, and the root is empty after it although `A.txt` was
    written. The pinned directory is 14 characters wider than the private
    root, at whatever width that is: a block folds a value before it cuts
    it. The control is a capture of `a.txt` and `a/b.txt`, which completes
    and leaves the root empty.
    """
    label = ("iiiiiii  a `[files]` key the operating system will not write — "
             "spelled as another key is on a case-insensitive file system — "
             "is ONE refusal from `write_files` on one line, naming its "
             "`[files.\"<key>\"]` table and `<WORK>/<key>`, the operating "
             "system's reason and no exception's name, with a `next:` line; "
             "through `capture` of the two keys, its block opens `about to "
             "run` over the environment as built, its TMPDIR line reads "
             "`<ENGINE-TMPDIR>`, and the temp root holds nothing of the run; "
             "the control, `a.txt` and `a/b.txt`, is captured and leaves "
             "nothing")

    def written(keys: tuple[str, ...]) -> str:
        """What `write_files` did with `keys` in an empty work directory: its
        refusal as printed, what it raised, or `WROTE`."""
        with _box("golden-census-unwritable-file-") as box:
            work = os.path.join(box, "work")
            os.makedirs(work)
            manifest = load_manifest(_scratch(box))._replace(
                files={key: ("one line",) for key in keys})
            try:
                write_files(manifest, Roots(root=box, work=work, clone=None,
                                            fixed=None), io.StringIO())
            except Refusal as refused:
                said = refusal_text(refused)
            except OSError as raised:
                said = f"RAISED {type(raised).__name__}: {raised}"
            else:
                said = "WROTE"
            return said.replace(os.path.realpath(box), "<box>").replace(
                box, "<box>")

    # Whether this file system reads `A.txt` and `a.txt` as one name: ask it.
    with _box("golden-census-unwritable-case-") as probe:
        pathlib.Path(probe, "A.txt").write_text("", encoding="utf-8")
        one_name = os.path.exists(os.path.join(probe, "a.txt"))
    if not one_name:
        skip(label, "the file system under the temp root keeps `A.txt` and "
                    "`a.txt` as two files, so no key of this arm is one the "
                    "operating system will not write. Nothing is claimed.")
        return
    plants = _UNWRITABLE_FILE_PLANTS
    verdicts = {what: written(keys) for what, keys, _number in plants}
    refused = all(
        (said := verdicts[what]).startswith("REFUSED: ")
        and said.partition("\n")[0].endswith(
            f"could not write [files.{json.dumps(keys[-1], ensure_ascii=False)}] "
            f"to <WORK>/{json.dumps(keys[-1], ensure_ascii=False)[1:-1]}: "
            f"{os.strerror(number)}.")
        and said.split("\n")[1].startswith("  next: ")
        for what, keys, number in plants)

    def captured(keys: tuple[str, ...]) -> tuple[str, list[str]]:
        """What a `capture` of the stub with `keys` as its `[files]` said —
        its refusal, what it raised, or its exit code — and what it left
        under its private temp root."""
        with _box("golden-census-unwritable-capture-") as box:

            def body() -> str:
                width = len(temp_base()) + 14
                path = _scratch(
                    box, manifest_text=_STUB_MANIFEST + _files_plant(*keys),
                    census_text=_STUB_WORK_CENSUS
                    + _root_swallow_pin(width))
                try:
                    code = capture(load_manifest(path),
                                   os.path.join(box, "out"), io.StringIO())
                except Refusal as refused:
                    return refusal_text(refused)
                except OSError as raised:
                    return f"RAISED {type(raised).__name__}: {raised}"
                return f"CAPTURED exit {code}"
            said, left = _made_under(temp_base(), body)
            return said.replace(box, "<box>"), left

    long_said, long_left = captured(_UNWRITABLE_FILE_PLANTS[0][1])
    lines = long_said.split("\n")
    block = lines[2:4]
    tmpdir = [line.strip() for line in lines if line.startswith("    TMPDIR=")]
    through = (long_said.startswith("REFUSED: ") and len(block) == 2
               and block[0].startswith("  about to run")
               and block[1].startswith("  the environment it was built with (")
               and "    TMPDIR=<ENGINE-TMPDIR>" in lines
               and not long_left)
    control_said, control_left = captured(("a.txt", "a/b.txt"))
    check(label,
          refused and through and control_said == "CAPTURED exit 0"
          and not control_left,
          ACTUAL + ", ".join(
              # From the table onward: the sentence opens with the scratch
              # manifest's path, which says nothing about the write.
              f"{what} -> "
              + _one_line(said.partition("could not write ")[2].partition(
                  "\n")[0] or said, DIFFERENCE)
              for what, said in verdicts.items())
          + "; capture of A.txt, then a.txt -> "
          + (" | ".join([line.strip() for line in block] + tmpdir[:1])
             or _one_line(long_said, DIFFERENCE))
          + f", left {long_left or 'nothing'}; control -> {control_said}, left "
          f"{control_left or 'nothing'}",
          next="`run.write_files` owns this refusal and `capture._capture_once` "
               "the environment and the fold its block shows. If a plant "
               "RAISED, the `try` around the write has gone and the key ends "
               "in a traceback again; if the block reads `not built yet`, "
               "the capture's outermost `Pending` "
               "is no longer given the environment in `built`; if its TMPDIR "
               "line is not `<ENGINE-TMPDIR>`, the outermost window no longer "
               "folds the fixed-width directory; if the root is not empty, "
               "the refusal left the run's directories behind.")


# ------------------------------------------ the `vary` control's runs (oooooo)

#: One subject, fourteen modes: print the named variable, write it to the
#: file `writes` names, write it only when the surface's own `env` says so,
#: write a constant, print it and write a number that is new on every run —
#: as text or in a JSON document — print it inside a token a fold replaces,
#: write a fixed text in the encoding it names, write a JSON document that
#: does not parse when the variable is 2, or count its own runs in the file
#: its third argument names, a file of its tree, and show the count in one
#: place: stdout as the count's parity or beside the variable, the file
#: `writes` names, stderr or the exit code, the three of which print a
#: constant on stdout. Each run of the `vary` control is compared as a
#: capture records it, after the census's folds; the stdout, folded and
#: counting modes write no file `writes` names but `written-count`'s.
_VARY_SUBJECT = '''\
import json
import os
import sys
import time

mode, variable = sys.argv[1], sys.argv[2]
value = os.environ.get(variable, "unset")
if mode == "stdout":
    print(value)
elif mode == "folded":
    print(f"id {value}")
elif mode == "clock":
    print(value)
    with open(sys.argv[3], "w", encoding="utf-8") as handle:
        handle.write(f"took {time.time_ns()}ns\\n")
elif mode == "json":
    print(value)
    with open(sys.argv[3], "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"run": {"took": time.time_ns()},
                                 "status": "ok"}, indent=2) + "\\n")
elif mode == "encoding":
    with open(sys.argv[3], "w", encoding=value) as handle:
        handle.write("caf\\u00e9\\n")
elif mode == "badjson":
    with open(sys.argv[3], "w", encoding="utf-8") as handle:
        handle.write("not json\\n" if value == "2" else json.dumps(
            {"run": {"took": 1}, "status": "ok"}, indent=2) + "\\n")
elif mode == "width":
    print(value)
    with open(sys.argv[3], "a", encoding="utf-8") as handle:
        handle.write(f"{len(sys.argv[4])}\\n")
elif mode in ("parity", "count", "written-count", "err-count", "exit-count"):
    counter = sys.argv[3]
    runs = 0
    if os.path.exists(counter):
        with open(counter, encoding="utf-8") as handle:
            runs = int(handle.read())
    with open(counter, "w", encoding="utf-8") as handle:
        handle.write(f"{runs + 1}\\n")
    if mode == "written-count":
        print("steady")
        with open(sys.argv[4], "w", encoding="utf-8") as handle:
            handle.write(f"{runs}\\n")
    elif mode == "err-count":
        print("steady")
        sys.stderr.write(f"{runs}\\n")
    elif mode == "exit-count":
        print("steady")
        sys.exit(runs)
    else:
        print(runs % 2 if mode == "parity" else f"{value} {runs}")
else:
    shown = mode == "file" or os.environ.get("VARY_MODE") == "on"
    with open(sys.argv[3], "w", encoding="utf-8") as handle:
        handle.write(f"{variable}={value}\\n" if shown else "no mode\\n")
'''

_VARY_MANIFEST = _subject("vary", '["<PYTHON>", "vary.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["file", "env", "stdout", "marker", "clock", "json", "folded",
            "encoding", "parity", "count", "written-count", "err-count",
            "exit-count", "cache", "unwritten", "badjson", "width"]

[surfaces.file]
args   = ["file", "VARY_FILE", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"

[surfaces.env]
args   = ["env", "VARY_ENV", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"
env    = { VARY_MODE = "on" }

[surfaces.stdout]
args = ["stdout", "VARY_STDOUT"]

[surfaces.marker]
args   = ["env", "VARY_MARKER", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"
env    = { VARY_MODE = "on" }

[surfaces.clock]
args   = ["clock", "VARY_CLOCK", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"

[surfaces.json]
args   = ["json", "VARY_JSON", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.json"

[surfaces.folded]
args = ["folded", "VARY_FOLDED"]

[surfaces.encoding]
args   = ["encoding", "VARY_ENCODING", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"

[surfaces.parity]
args = ["parity", "VARY_PARITY", "parity-runs.txt"]

[surfaces.count]
args = ["count", "VARY_COUNT", "count-runs.txt"]

[surfaces.written-count]
args   = ["written-count", "VARY_WRITTEN_COUNT", "written-count-runs.txt", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.txt"

[surfaces.err-count]
args = ["err-count", "VARY_ERR_COUNT", "err-count-runs.txt"]

[surfaces.exit-count]
args = ["exit-count", "VARY_EXIT_COUNT", "exit-count-runs.txt"]

[surfaces.cache]
args = ["count", "VARY_CACHE", "<WORK>/cache-runs.txt"]

[surfaces.badjson]
args   = ["badjson", "VARY_BADJSON", "<WRITES>"]
writes = "<WORK>/<input>-<surface>.json"

[surfaces.unwritten]
args   = ["stdout", "VARY_ABSENT"]
writes = "<WORK>/<input>-<surface>.txt"

[surfaces.width]
args = ["width", "VARY_WIDTH", "width-runs.txt", "<WORK>"]
'''

#: The file of its tree the `width` surface adds the width of its <WORK> to,
#: one line a run.
_VARY_WIDTHS = "width-runs.txt"

#: A manifest of the `width` surface alone, for the one capture arm `oooooo`
#: makes: the width of a capture's <WORK>, which the `vary` control's three
#: runs must match, since a path that fits under one has to fit under the
#: other.
_VARY_WIDTH_MANIFEST = _subject("vary", '["<PYTHON>", "vary.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["width"]

[surfaces.width]
args = ["width", "VARY_WIDTH", "width-runs.txt", "<WORK>"]
'''

#: One pin per surface, each proven by varying it on its own surface.
_VARY_PIN = '''
[[input]]
name        = "{surface}"
disposition = "pin"
variable    = "{variable}"
value       = "{value}"
finding     = "planted: the {surface} surface carries this variable"
control     = {{ shape = "vary", surface = "_subject/{surface}", value = "{varied}" }}
'''

#: A regex fold scoped to one surface: the clock surface's number, which
#: moves on every run, and the folded surface's printed value.
_VARY_FOLD = '''
[[input]]
name        = "the {surface} surface's number"
disposition = "fold"
kind        = "regex"
pattern     = '{pattern}'
placeholder = "<N>"
scope       = ["_subject/{surface}"]
finding     = "planted: the {surface} surface prints a number this fold replaces"
control     = {{ sample = "{sample}", moved = "{moved}" }}
'''

#: A json-fields fold of the json surface's number, which moves on every
#: run; its control reads the two fixture documents `_VARY_JSON_FIXTURES`
#: writes.
_VARY_JSON_FOLD = '''
[[input]]
name          = "the json surface's number"
disposition   = "fold"
kind          = "json-fields"
paths         = ["run"]
fields        = ["took"]
placeholder   = "<N>"
serialization = { indent = 2, ensure_ascii = false }
finding       = "planted: the json surface writes a number this fold replaces"
control       = { sample = "took-sample.json", moved = "took-moved.json" }
'''

_VARY_JSON_FIXTURES = {
    f"took-{side}.json": json.dumps({"run": {"took": took}, "status": "ok"},
                                    indent=2) + "\n"
    for side, took in (("sample", 137), ("moved", 2041))}

#: A pin of a variable no surface reads, whose control names a surface that
#: writes a file: UNPROVEN, in the words that name the file it writes.
_VARY_UNREAD_PIN = '''
[[input]]
name        = "a variable the file surface does not read"
disposition = "pin"
variable    = "VARY_UNREAD"
value       = "1"
finding     = "planted: no surface reads this variable"
control     = { shape = "vary", surface = "_subject/file", value = "2" }
'''

_VARY_CENSUS = (_STUB_ENVIRONMENT + '\n[fixtures]\ndir = "."\n' + "".join(
    _VARY_PIN.format(surface=surface, variable=variable, value=value,
                     varied=varied)
    for surface, variable, value, varied in (
        ("file", "VARY_FILE", "1", "2"), ("env", "VARY_ENV", "1", "2"),
        ("stdout", "VARY_STDOUT", "1", "2"), ("marker", "VARY_MARKER", "1", "2"),
        ("clock", "VARY_CLOCK", "1", "2"), ("json", "VARY_JSON", "1", "2"),
        ("folded", "VARY_FOLDED", "1", "2"),
        ("encoding", "VARY_ENCODING", "utf-8", "latin-1"),
        ("parity", "VARY_PARITY", "1", "2"), ("count", "VARY_COUNT", "1", "2"),
        ("written-count", "VARY_WRITTEN_COUNT", "1", "2"),
        ("err-count", "VARY_ERR_COUNT", "1", "2"),
        ("exit-count", "VARY_EXIT_COUNT", "1", "2"),
        ("cache", "VARY_CACHE", "1", "2"),
        ("unwritten", "VARY_UNWRITTEN", "1", "2"),
        ("badjson", "VARY_BADJSON", "1", "2"),
        ("width", "VARY_WIDTH", "1", "2")))
    + _VARY_FOLD.format(surface="clock", pattern="took (?P<volatile>\\d+)ns",
                        sample="took 137ns", moved="took 2041ns")
    + _VARY_FOLD.format(surface="folded", pattern="id (?P<volatile>\\d+)",
                        sample="id 1", moved="id 2")
    + _VARY_JSON_FOLD + _VARY_UNREAD_PIN)

#: A subject found on the pinned `PATH` by its bare name: under the pin both
#: runs start, and under the varied `PATH`, a directory that does not exist,
#: the third would not start.
_VARY_START_MANIFEST = _subject("vary-start", '[{program}, "vary.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["stdout"]

[surfaces.stdout]
args = ["stdout", "VARY_STDOUT"]
'''

_VARY_START_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the program's directory"
disposition = "pin"
variable    = "PATH"
value       = {directory}
finding     = "planted: the command is found on PATH"
control     = {{ shape = "vary", surface = "_subject/stdout", value = "{varied}" }}
'''

_VARY_NO_DIRECTORY = "/no-such-directory-oooooo"


#: Every pin of arm `oooooo`'s census and what the `vary` control comes to
#: on it: `PASS`; `SKIP`; or one of the two kinds of FAIL, `UNPROVEN` — the
#: pin's three runs agree — and `unsteady` — the two runs under the pin
#: differ, whatever the varied run did.
_VARY_VERDICTS = {
    "file": "PASS", "env": "PASS", "stdout": "PASS", "clock": "PASS",
    "json": "PASS", "cache": "PASS", "width": "PASS",
    "marker": "PASS", "encoding": "SKIP", "badjson": "SKIP",
    "folded": "UNPROVEN", "unwritten": "UNPROVEN",
    "a variable the file surface does not read": "UNPROVEN",
    "parity": "unsteady", "count": "unsteady", "written-count": "unsteady",
    "err-count": "unsteady", "exit-count": "unsteady"}

#: The files the subject counts its runs in, in its own tree: the five
#: surfaces whose count differs between two runs under the pin. `cache` keeps
#: its count under the work directory.
_VARY_COUNTERS = ("parity-runs.txt", "count-runs.txt",
                  "written-count-runs.txt", "err-count-runs.txt",
                  "exit-count-runs.txt")


def _vary_verdict(rows: list[tuple[str, bool, str, str]],
                  skips: list[tuple[str, str]], name: str) -> str:
    """What the `vary` control came to on census pin `name`: `PASS`, `SKIP`,
    `UNPROVEN` or `unsteady` — the two kinds of FAIL, told apart by the
    verdict's own name in the detail — or how many rows and SKIPs it made
    where it did not make exactly one."""
    mine = [(ok, detail) for label, ok, detail, _next in rows
            if label.startswith(f"census pin {name!r}: ")]
    said = [reason for label, reason in skips
            if label.startswith(f"census pin {name!r}: ")]
    if len(mine) + len(said) != 1:
        return f"{len(mine)} rows and {len(said)} SKIPs"
    if said:
        return "SKIP"
    ok, detail = mine[0]
    if ok:
        return "PASS"
    return "UNPROVEN" if "UNPROVEN" in detail else "unsteady"


def _refused_run(manifest: Manifest, surface_name: str,
                 change: dict[str, str] | None) -> Refusal | None:
    """The refusal one run of `surface_name` ends in, in a place `run.place`
    makes with `change` on top of the environment; None when it ends in
    none. The refusal is the run's own, asked outside the control."""
    subject_input = manifest.inputs[0]
    surface = manifest.surfaces[surface_name]
    try:
        with place(manifest, "golden-census-vary-", io.StringIO(),
                   rows=[(subject_input, surface)], change=change) as where:
            run_row(where, subject_input, surface)
    except Refusal as refused:
        return refused
    return None


def _vary_skip_says(reason: str, run: str, inner: Refusal | None
                    ) -> list[bool]:
    """Four facts of the SKIP of a run that was refused: it names the run
    (`run`); it carries the refusal's own `next:` where the refusal has one
    and none where it has none (`inner` is that refusal, asked of the same
    run outside the control); it is not the SKIP of a child that would not
    start; and it ends on the one period `DISCLOSED` follows."""
    if inner is None:
        return [False] * 4
    advice = unpunctuated(inner.next)
    return [run in reason,
            advice in reason if advice else " — next: " not in reason,
            "would not start" not in reason,
            reason.endswith(DISCLOSED) and ".." not in reason]


def _vary_runs_control(check: CheckRow) -> None:
    """(oooooo) the `vary` control reaches its verdict from what a capture
    records of each run, and a run it cannot compare is a SKIP that names
    the run.

    One run of the controls over a manifest of surfaces, and each pin's
    verdict (`_vary_verdict`) is held against `_VARY_VERDICTS`; nothing
    here is held against the control's sentences but where a sentence is the
    fact under test: which run a SKIP names, that it carries the refusal's
    `next:` (asked of the same run outside the control, never typed here),
    what an UNPROVEN row says it compared, and that a FAIL of two unequal
    runs names no cause. The facts the surfaces plant:

    - A pin that reaches only the written file, one the surface's `env` is
      needed for, and one on stdout are PASS. A written number that is new on
      every run, in text under a `regex` fold and in a `.json` file under a
      `json-fields` fold, leaves the pinned runs identical.
    - A pin whose printed value a fold replaces, a pin no surface reads on a
      surface that writes a file and one on a surface that declares a file
      and writes none are UNPROVEN: the row says whether the file was
      compared, that the run under the varied value is or is not different
      before the folds, and gives a `next:` that names no fold.
    - A surface that counts its own runs in a file of its tree is a FAIL
      that is never UNPROVEN and names no cause, whichever channel carries
      the count: stdout as a parity or beside the variable, the file
      `writes` names, stderr, or the exit code (the last three print a
      constant on stdout). Each pin is run three times, which the counters
      the subject leaves in its tree show. The same count kept under the
      work directory is steady, because each run has a place of its own,
      and no place is left under the temp root, which is a private one here.
    - A surface whose `env` the census does not pin is a PASS.
    - A subject that writes in the encoding the variable names is
      refused on the varied run alone, and a subject that writes a `.json`
      file no fold can parse when the variable is 2 is refused by the fold
      on the varied run alone: each is a SKIP that names that run — not
      "would not start", which is a child that would not start — and ends on
      one period. A subject found on the pinned `PATH` starts twice under the
      pin and not under the varied `PATH`: a SKIP that names the run under
      the varied value, because the surface does run here.
    """
    label = ("oooooo  the `vary` control reaches its verdict from what a "
             "capture records of each run, after the census's folds — the "
             "exit code, stdout, stderr and the written file: a pin only the "
             "written file carries, one the surface's `env` is needed for and "
             "one on stdout are PASS, and so is one whose written number a "
             "fold replaces, in text and in `.json`; a pin whose three runs "
             "agree is UNPROVEN, saying what was compared and giving a "
             "`next:`; a surface whose two runs under the pin differ is a "
             "FAIL that is never UNPROVEN and names no cause, whether the "
             "difference is on stdout, in the written file, on stderr or in "
             "the exit code; a count kept under the work directory is "
             "steady, and no place is left behind; a run refused before it "
             "could be compared, a fold's refusal of its text included, is "
             "a SKIP naming that run and carrying the refusal's `next:`, "
             "and so is a run that would not start under the varied value "
             "alone; each of its three runs is given a <WORK> exactly as "
             "wide as a capture's, so a path that fits under one fits under "
             "the other")
    with (_box("golden-census-vary-runs-") as box,
          _box("golden-census-vary-width-") as wide):
        manifest = load_manifest(_scratch(
            box, manifest_text=_VARY_MANIFEST,
            census_text=_VARY_CENSUS,
            extra={"vary.py": _VARY_SUBJECT, **_VARY_JSON_FIXTURES}))
        roots = Roots(root=manifest.subject.root, work=box, clone=None)
        widest = load_manifest(_scratch(
            wide, manifest_text=_VARY_WIDTH_MANIFEST,
            census_text=_STUB_WORK_CENSUS, extra={"vary.py": _VARY_SUBJECT}))
        before = set(os.listdir(box))

        plans: tuple[tuple[str, dict[str, str] | None], ...] = (
            ("encoding", {"VARY_ENCODING": "latin-1"}),
            ("badjson", {"VARY_BADJSON": "2"}))

        def controls() -> tuple[list[tuple[str, bool, str, str]],
                                list[tuple[str, str]],
                                dict[str, Refusal | None], int]:
            rows, skips = _census_rows(manifest, roots)
            # A capture of the `width` surface under the same temp root,
            # for the width of a capture's <WORK>.
            captured = capture(widest, os.path.join(wide, "golden"),
                               io.StringIO())
            return rows, skips, {
                name: _refused_run(manifest, name, change)
                for name, change in plans}, captured

        # The places are made under the temp root, so the runs are made
        # under a private one and what they left there is its listing.
        (rows, skips, refused, captured), private = _made_under(temp_base(),
                                                                controls)
        # The counters the subject keeps in its own tree, and nothing else,
        # in the box; nothing under the private root.
        left = (sorted(set(os.listdir(box)) - before - set(_VARY_COUNTERS)
                       - {_VARY_WIDTHS})
                + [f"private root: {name}" for name in private])
        widths = {name: pathlib.Path(where, _VARY_WIDTHS).read_text(
                      encoding="utf-8").split()
                  if pathlib.Path(where, _VARY_WIDTHS).is_file() else []
                  for name, where in (("the control", box),
                                      ("a capture", wide))}
        counted: dict[str, str | None] = {}
        for name in _VARY_COUNTERS:
            counter = pathlib.Path(box, name)
            counted[name] = (counter.read_text(encoding="utf-8")
                             if counter.is_file() else None)
    with _box("golden-census-vary-start-") as box:
        started = load_manifest(_scratch(
            box, manifest_text=_VARY_START_MANIFEST.format(
                program=json.dumps(os.path.basename(sys.executable),
                                   ensure_ascii=False)),
            census_text=_VARY_START_CENSUS.format(
                directory=json.dumps(os.path.dirname(sys.executable),
                                     ensure_ascii=False),
                varied=_VARY_NO_DIRECTORY),
            extra={"vary.py": _VARY_SUBJECT}))
        start_rows, start_skips = _census_rows(
            started, Roots(root=started.subject.root, work=box, clone=None))
    verdicts = {name: _vary_verdict(rows, skips, name)
                for name in _VARY_VERDICTS}
    differing = {name: (verdicts[name], wanted)
                 for name, wanted in _VARY_VERDICTS.items()
                 if verdicts[name] != wanted}

    def pin_rows(name: str) -> list[tuple[str, bool, str, str]]:
        return [row for row in rows if row[0].startswith(f"census pin {name!r}: ")]

    # What an UNPROVEN row says: whether it names the file it writes, whether
    # it says what the run under the varied value did before the folds, and
    # whether that run did not differ; and a `next:` that names no fold.
    unproven = {name: [(("the file it writes" in detail),
                        ("Before the census's folds" in detail),
                        ("does not differ from" in detail),
                        bool(next_) and "fold" not in next_)
                       for _label, _ok, detail, next_ in pin_rows(name)]
                for name in ("folded", "unwritten",
                             "a variable the file surface does not read")}
    # The fact of a FAIL of two unequal runs: a `next:` that names no cause.
    unsteady = {name: [bool(next_) and not any(word in next_ for word in (
                    "a capture records", "clock", "counter"))
                       for _label, _ok, _detail, next_ in pin_rows(name)]
                for name in ("parity", "count", "written-count", "err-count",
                             "exit-count")}
    skip_reasons = {name: [reason for label, reason in skips
                           if label.startswith(f"census pin {name!r}: ")]
                    for name in ("encoding", "badjson")}
    named = {"encoding": "the run under VARY_ENCODING='latin-1'",
             "badjson": "the run under VARY_BADJSON='2'"}
    skip_says = {name: [_vary_skip_says(reason, named[name], refused[name])
                        for reason in reasons]
                 for name, reasons in skip_reasons.items()}
    unstarted = [reason for _skip_label, reason in start_skips]
    unexpected = [label[:60] for label, ok, _detail, _next in rows
                  if not ok and not any(
                      label.startswith(f"census pin {name!r}: ")
                      for name, wanted in _VARY_VERDICTS.items()
                      if wanted in ("UNPROVEN", "unsteady"))]
    check(label,
          differing == {}
          and unproven == {
              "folded": [(False, True, False, True)],
              "unwritten": [(False, True, True, True)],
              "a variable the file surface does not read": [
                  (True, True, True, True)]}
          and unsteady == {name: [True] for name in unsteady}
          and skip_says == {name: [[True] * 4] for name in skip_says}
          and counted == {name: "3\n" for name in _VARY_COUNTERS}
          and left == []
          and captured == 0
          and len(widths["the control"]) == 3
          and widths["the control"] == widths["a capture"] * 3
          and unexpected == []
          and not start_rows
          and len(unstarted) == 1
          and unstarted[0].startswith(
              f"the run under PATH={_VARY_NO_DIRECTORY!r} ")
          and "would not start" in unstarted[0]
          and " — next: " in unstarted[0]
          and unstarted[0].endswith(DISCLOSED) and ".." not in unstarted[0],
          ACTUAL + f"verdicts differing from the wanted ones -> {differing}"
          + f"; UNPROVEN rows (names the file, says before the folds, does "
          f"not differ, a `next:` with no fold) -> {unproven}"
          + f"; FAILs of two unequal runs (a `next:` naming no cause) -> "
          f"{unsteady}"
          + f"; SKIPs (names the run, carries the refusal's `next:`, is not "
          f"a would-not-start, ends on one period) -> {skip_says}"
          + f"; the counters the subject left (runs counted) -> "
          f"{[(name, count and count.strip()) for name, count in counted.items()]}"
          + f"; left in the scratch subject -> {left}"
          + f"; the width of <WORK> in characters, in the control's runs -> "
          f"{widths['the control']}, in a capture (exit {captured}) -> "
          f"{widths['a capture']}"
          + f"; red rows nobody wanted -> {unexpected}"
          + f"; the varied PATH -> rows {len(start_rows)}, SKIPs "
          f"{len(unstarted)}")


# ------------------------------ the `vary` control's place (rrrrrr, ssssss)

#: One subject for the two arms over the place a `vary` run is made in: its
#: first argument is a mode, its second the variable it prints, and its
#: third a path or a number. `build` writes the file a setup step makes;
#: `exit` exits with the code it is handed, saying why on stderr when it is
#: not 0; `tmpdir` exits 3 without TMPDIR and keeps a cache under it;
#: `files` and `setup` read a file a `[files]` entry or a setup step makes,
#: and exit 4 or 5 naming the path when it is not there; `count` counts its
#: runs in its file; `read-only` leaves a directory it may not write under
#: its path; `removes` removes its path on every run and `removes-varied`
#: under the value 2 alone; `value` prints the variable and nothing else.
_PLACE_SUBJECT = '''\
import os
import shutil
import sys

mode, variable = sys.argv[1], sys.argv[2]
value = os.environ.get(variable, "unset")
if mode == "build":
    with open(sys.argv[3], "w", encoding="utf-8") as handle:
        handle.write("built\\n")
elif mode == "exit":
    code = int(sys.argv[3])
    if code:
        sys.stderr.write("did the build fail?\\n")
    sys.exit(code)
elif mode == "tmpdir":
    root = os.environ.get("TMPDIR")
    if root is None:
        sys.stderr.write("no TMPDIR in this environment\\n")
        sys.exit(3)
    cache = os.path.join(root, "module-cache")
    warm = os.path.isdir(cache)
    os.makedirs(cache, exist_ok=True)
    print(value, "warm" if warm else "cold")
elif mode in ("files", "setup"):
    try:
        with open(sys.argv[3], encoding="utf-8") as handle:
            print(value, handle.read().strip())
    except OSError:
        sys.stderr.write(f"nothing at {sys.argv[3]}\\n")
        sys.exit(4 if mode == "files" else 5)
elif mode == "count":
    runs = 0
    if os.path.exists(sys.argv[3]):
        with open(sys.argv[3], encoding="utf-8") as handle:
            runs = int(handle.read())
    with open(sys.argv[3], "w", encoding="utf-8") as handle:
        handle.write(f"{runs + 1}\\n")
    print(value, runs)
elif mode == "read-only":
    mod = os.path.join(sys.argv[3], "cache", "mod")
    if not os.path.isdir(mod):
        os.makedirs(mod)
        with open(os.path.join(mod, "f"), "w", encoding="utf-8") as handle:
            handle.write("x")
        os.chmod(mod, 0o555)
    print(value)
else:
    print(value)
    if mode == "removes" or (mode == "removes-varied" and value == "2"):
        shutil.rmtree(sys.argv[3], ignore_errors=True)
'''

#: Arm `rrrrrr`'s manifest: one surface per thing a place holds, and
#: `also-built`, which no pin names and which needs the same setup step as
#: `setup`, so a step run for a row the control does not run shows.
_PLACE_MANIFEST = _subject("vary-place", '["<PYTHON>", "place.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["tmpdir", "files", "setup", "also-built", "count", "read-only",
            "removes", "removes-varied"]

[surfaces.tmpdir]
args = ["tmpdir", "VARY_TMPDIR"]

[surfaces.files]
args = ["files", "VARY_FILES", "<WORK>/config.txt"]

[surfaces.setup]
args  = ["setup", "VARY_SETUP", "<WORK>/built.txt"]
needs = ["build"]

[surfaces.also-built]
args  = ["setup", "VARY_ALSO", "<WORK>/built.txt"]
needs = ["build"]

[surfaces.count]
args = ["count", "VARY_COUNT", "<WORK>/runs.txt"]

[surfaces.read-only]
args = ["read-only", "VARY_READ_ONLY", "<WORK>"]

[surfaces.removes]
args = ["removes", "VARY_REMOVES", "<WORK>"]

[surfaces.removes-varied]
args = ["removes-varied", "VARY_REMOVES_VARIED", "<WORK>"]

[files."config.txt"]
lines = ["fast"]

[[setup]]
name    = "build"
command = ["<PYTHON>", "<HERE>/place.py", "build", "-", "<WORK>/built.txt"]
'''


def _place_tmpdir(width: int) -> str:
    """The census's pin of the subject's TMPDIR at a width the arm computes."""
    return _fixed_pin(width, "planted: the tmpdir surface exits 3 without TMPDIR",
                      name="the temp root, at a fixed width")


#: `rrrrrr`'s pins, (surface, variable): each pin's name is its surface's.
_PLACE_PINS = (("tmpdir", "VARY_TMPDIR"), ("files", "VARY_FILES"),
               ("setup", "VARY_SETUP"), ("count", "VARY_COUNT"),
               ("read-only", "VARY_READ_ONLY"), ("removes", "VARY_REMOVES"),
               ("removes-varied", "VARY_REMOVES_VARIED"))

def _place_census(width: int | None, pins: tuple[tuple[str, str], ...]) -> str:
    """`rrrrrr`'s census: the work directory's fold, the TMPDIR pin when a
    `width` is given, and one `vary` pin per `(surface, variable)`."""
    return (_STUB_ENVIRONMENT + _STUB_WORK_FOLD
            + ("" if width is None else _place_tmpdir(width))
            + "".join(_VARY_PIN.format(surface=surface, variable=variable,
                                       value="1", varied="2")
                      for surface, variable in pins))


#: A census pin's rows `(ok, detail)` and its SKIP reasons.
_PinFound = tuple[list[tuple[bool, str]], list[str]]


def _proven(found: _PinFound) -> bool:
    """One PASS row and no SKIP: the `vary` control's verdict, which holds
    no sentence of the control's."""
    rows, skips = found
    return [ok for ok, _detail in rows] == [True] and skips == []


def _pin_rows(rows: list[tuple[str, bool, str, str]],
              skips: list[tuple[str, str]], name: str,
              disposition: str = "pin") -> _PinFound:
    """The rows `(ok, detail)` and the SKIP reasons of the census row `name`,
    a pin unless `disposition` says a fold."""
    prefix = f"census {disposition} {name!r}: "
    return ([(ok, detail) for label, ok, detail, _n in rows
             if label.startswith(prefix)],
            [reason for label, reason in skips if label.startswith(prefix)])


def _vary_place_control(check: CheckRow, skip: SkipRow) -> None:
    """(rrrrrr) the `vary` control runs its row in a place a capture would
    make, and each case is shown to depend on what it names.

    One run of the controls on a manifest whose pins each need something
    only a capture's place holds — the census's fixed-width TMPDIR, a
    `[files]` entry, a setup step the row needs, a work directory no other
    run has counted in — or whose subject leaves a place hard to remove: a
    read-only directory under `<WORK>`, or no `<WORK>` at all. Every pin is
    PROVEN, and the private temp root holds nothing afterwards. Each red half
    takes the one thing away, or shows the plant is there: with no TMPDIR
    pin, no `[files]` table or no `needs`, the pin is UNPROVEN — and the
    `[files]` row's UNPROVEN says nothing of the unfolded texts, because its
    two pinned runs name two work directories; with the counter in the
    subject's tree the pinned runs differ; and a row run once in a place of
    `run.place` leaves the read-only directory, or removes the work
    directory, inside it. The setup step is also needed by a row no pin
    names, so a step run for a row the control does not run shows. The
    TMPDIR width is the private root's length plus 14, computed and not
    typed; where the machine's root leaves no such width, the whole arm is
    a disclosed SKIP.
    """
    label = ("rrrrrr  the `vary` control runs its row in a place a capture "
             "would make: a row that needs the census's fixed-width TMPDIR, "
             "one that reads a [files] entry, one that needs a setup step and "
             "one that keeps state under <WORK> are each PROVEN, a row that "
             "leaves a read-only directory under <WORK> or removes <WORK> is "
             "PROVEN too, and no place is left behind; and each is shown to "
             "depend on what it names")
    with _box("golden-census-vary-place-") as box:

        def controls(manifest_text: str, census_text: str, name: str
                     ) -> _PinFound:
            manifest = load_manifest(_scratch(
                box, manifest_text=manifest_text, census_text=census_text,
                extra={"place.py": _PLACE_SUBJECT}))
            roots = Roots(root=manifest.subject.root, work=box, clone=None)
            rows, skips = _census_rows(manifest, roots)
            return _pin_rows(rows, skips, name)

        def body() -> tuple[dict[str, _PinFound], dict[str, bool]] | None:
            private = temp_base()
            width = len(private) + 14
            _base, room = fixed_dir_room(private, width)
            if not 1 <= room <= 64:
                skip(label, f"the private temp root is {len(private)} "
                     f"characters long, and a TMPDIR of {width} characters "
                     "cannot be made under it, so the fixed-width case has "
                     "no width to run at. Nothing is claimed.")
                return None
            found: dict[str, _PinFound] = {}
            manifest = load_manifest(_scratch(
                box, manifest_text=_PLACE_MANIFEST,
                census_text=_place_census(width, _PLACE_PINS),
                extra={"place.py": _PLACE_SUBJECT}))
            roots = Roots(root=manifest.subject.root, work=box, clone=None)
            rows, skips = _census_rows(manifest, roots)
            for name, _variable in _PLACE_PINS:
                found[name] = _pin_rows(rows, skips, name)
            # The red halves: each takes away the one thing its case names.
            found["red tmpdir"] = controls(
                _PLACE_MANIFEST, _place_census(None, _PLACE_PINS[:1]),
                "tmpdir")
            found["red files"] = controls(
                _PLACE_MANIFEST.replace(
                    '[files."config.txt"]\nlines = ["fast"]\n', ""),
                _place_census(width, _PLACE_PINS[1:2]), "files")
            found["red setup"] = controls(
                _PLACE_MANIFEST.replace(
                    '"<WORK>/built.txt"]\nneeds = ["build"]\n\n'
                    '[surfaces.also-built]',
                    '"<WORK>/built.txt"]\n\n[surfaces.also-built]'),
                _place_census(width, _PLACE_PINS[2:3]), "setup")
            found["red count"] = controls(
                _PLACE_MANIFEST.replace('"<WORK>/runs.txt"', '"runs.txt"'),
                _place_census(width, _PLACE_PINS[3:4]), "count")
            # The two plants, shown to be there: the row run once in a place
            # of `run.place`, and what it left looked at before the place
            # goes.
            planted: dict[str, bool] = {}
            subject_input = manifest.inputs[0]
            for surface_name in ("read-only", "removes"):
                surface = manifest.surfaces[surface_name]
                with place(manifest, "golden-census-vary-place-",
                           io.StringIO(), rows=[(subject_input, surface)]
                           ) as where:
                    run_row(where, subject_input, surface)
                    mod = os.path.join(where.roots.work, "cache", "mod")
                    planted[surface_name] = (
                        os.path.isdir(mod)
                        and stat.S_IMODE(os.stat(mod).st_mode) == 0o555
                        if surface_name == "read-only"
                        else not os.path.isdir(where.roots.work))
            return found, planted

        said, left = _made_under(temp_base(), body)
    if said is None:
        return
    found, planted = said
    green = {surface: found[surface] for surface, _v in _PLACE_PINS}
    red = {case: found[f"red {case}"] for case in ("tmpdir", "files", "setup")}

    def unproven(pin: _PinFound, *, unfolded: bool = True) -> bool:
        """One UNPROVEN row and no SKIP; with `unfolded` False, a row that
        says nothing of the texts before the census's folds."""
        rows, skips = pin
        return (len(rows) == 1 and not skips and not rows[0][0]
                and "UNPROVEN" in rows[0][1]
                and (unfolded or "Before the census's folds" not in rows[0][1]))
    check(label,
          all(_proven(pin) for pin in green.values())
          and left == []
          and unproven(red["tmpdir"])
          and unproven(red["files"], unfolded=False)
          and unproven(red["setup"])
          and [ok for ok, _detail in found["red count"][0]] == [False]
          and "UNPROVEN" not in found["red count"][0][0][1]
          and found["red count"][1] == []
          and planted == {"read-only": True, "removes": True},
          ACTUAL + "; ".join(
              f"{surface} -> {rows} {[_one_line(r, 90) for r in skips]}"
              for surface, (rows, skips) in green.items())
          + f"; left under the private root -> {left}"
          # A red half's detail from its end, where the UNPROVEN sentence
          # says what was compared and, or not, what was measured unfolded.
          + "".join(f"; without its {case} -> "
                    f"{[(ok, '…' + detail[-120:]) for ok, detail in rows]}"
                    f" {[_one_line(r, 90) for r in skips]}"
                    for case, (rows, skips) in red.items())
          + f"; the counter in the subject's tree -> {found['red count']}"
          + "; a read-only directory at 0o555 under <WORK> -> "
          f"{planted['read-only']}"
          + f"; <WORK> gone after the removing row -> {planted['removes']}")


#: Arm `ssssss`'s manifest: one surface that needs one setup step, which
#: exits with `{code}`; `{git}` is the input's pinned tree, or nothing.
_REFUSED_PLACE_MANIFEST = _subject("vary-refused-place", '["<PYTHON>", "place.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["out"]{git}

[surfaces.out]
args  = ["value", "V"]
needs = ["build"]

[[setup]]
name    = "build"
command = ["<PYTHON>", "<HERE>/place.py", "exit", "-", "{code}"]
'''

_REFUSED_PLACE_GIT = '''
git      = "/no-such-repository-ssssss"
sha      = "0123456"'''

_REFUSED_PLACE_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the V variable"
disposition = "pin"
variable    = "V"
value       = "1"
finding     = "planted: the out surface prints V"
control     = { shape = "vary", surface = "_subject/out", value = "2" }
'''

#: A `command` precondition that exits with `{code}`.
_REFUSED_PLACE_PRECONDITION = '''
[[input]]
name        = "a command that must exit 0"
disposition = "precondition"
check       = "command"
command     = [{python}, "-c", "raise SystemExit({code})"]
expect      = "exit 0"
finding     = "planted: the command exits {code}"
'''

#: The opening of the SKIP of a place whose preparation was refused.
_PREPARED_REFUSED = ("the first run under the pin was refused while its place "
                     "was being prepared, before the surface ran: ")


def _vary_refused_place_control(check: CheckRow, skip: SkipRow) -> None:
    """(ssssss) a place the `vary` control could not prepare is a SKIP that
    names the run and quotes why, never a verdict.

    Five faults, each planted in a manifest that gives a PASS row once the
    fault is taken out: a setup step the row needs that exits 7 and ends its
    message on a question mark, which the SKIP quotes whole and ends with no
    period of its own, a `command` precondition that exits 5, an input whose
    pinned tree cannot be cloned — with or without `git` on this machine,
    since a `git` that will not start is a reason of the clone's too — a
    census whose fixed-width TMPDIR is one character wider than the private
    temp root, and a temp root that is not there, which the step exiting 0 is
    the other half of. Each fault is exactly one SKIP of the pin and no row,
    and a refusal it quotes brings its `next:` as a second clause
    (`core.with_next`), in front of the period that ends the sentence. Every
    case runs with the clone cache in the arm's box (`_cache_in`), and
    nothing is left under the private root: the clone cache is not there. The
    unpinned clone is the one case that reaches `git clone`; it runs over the
    `git` `_clone_that_fails` plants, so its reason names the clone step
    (`git clone exited 128: `) whatever the network, the cache or the real
    git would have said.
    """
    label = ("ssssss  a place the `vary` control could not prepare is a SKIP "
             "that names the run and quotes why, never a verdict: a setup "
             "step that exits non-zero, a precondition that does not hold, a "
             "pinned tree that cannot be cloned — its clone failing under a "
             "`git` planted to fail it — a temp root too wide for "
             "the pin and a temp root that is not there, each carrying the "
             "refusal's `next:` where it has one; and each manifest "
             "gives a verdict once the fault is taken out")
    python = json.dumps(sys.executable, ensure_ascii=False)
    with _box("golden-census-vary-refused-") as box, _cache_in(box):

        def controls(code: int = 0, git: str = "", extra_census: str = ""
                     ) -> _PinFound:
            manifest = load_manifest(_scratch(
                box, manifest_text=_REFUSED_PLACE_MANIFEST.format(
                    git=git, code=code),
                census_text=_REFUSED_PLACE_CENSUS + extra_census,
                extra={"place.py": _PLACE_SUBJECT}))
            roots = Roots(root=manifest.subject.root, work=box, clone=None)
            rows, skips = _census_rows(manifest, roots)
            return _pin_rows(rows, skips, "the V variable")

        def body() -> tuple[dict[str, tuple[_PinFound, _PinFound]], str]:
            private = temp_base()
            return {
                "a setup step exits 7": (controls(code=7), controls(code=0)),
                "a precondition exits 5": (
                    controls(extra_census=_REFUSED_PLACE_PRECONDITION.format(
                        python=python, code=5)),
                    controls(extra_census=_REFUSED_PLACE_PRECONDITION.format(
                        python=python, code=0))),
                "no pinned tree": (controls(git=_REFUSED_PLACE_GIT),
                                   controls()),
                "a temp root too wide": (
                    controls(extra_census=_place_tmpdir(len(private) + 1)),
                    controls(extra_census=_place_tmpdir(len(private) + 15))),
            }, private

        # The pinned input's clone fails the same way in every run: the `git`
        # of `_clone_that_fails` answers it, so the reason the row quotes
        # cannot move with this machine's network, its cache or its git.
        with _clone_that_fails(box) as planted:
            (said, private), left = _made_under(temp_base(), body)
        # The fault taken out is the setup step's clean half: the same
        # manifest, under a root that is there.
        with _tmpdir_as(os.path.join(box, "no-such-root")):
            said["no temp root"] = (controls(),
                                    said["a setup step exits 7"][1])
    wanted = {
        "a setup step exits 7": lambda reason: reason == (
            _PREPARED_REFUSED + "[[setup]] 'build' exited 7: did the build "
            "fail? — next: Run that setup command by hand in a scratch "
            "directory, as a capture runs it in <WORK>, and fix what it "
            "reports; a capture does not start from a setup that failed. "
            "Disclosed, never a pass."),
        "a precondition exits 5": lambda reason: (
            reason.startswith(_PREPARED_REFUSED)
            and reason.endswith(" exited 5, it printed no text on stderr — "
                                "next: Run that command by hand from the "
                                "subject root and fix what it reports; the "
                                "row's `finding` says why the capture "
                                "depends on it. Disclosed, never a pass.")),
        "no pinned tree": lambda reason: reason.startswith(
            "the first run under the pin could not be given its input's "
            "pinned tree: " + (_PLANTED_CLONE_STEP if planted else "")),
        "a temp root too wide": lambda reason: (
            reason.startswith(_PREPARED_REFUSED)
            and "needs a root of at most" in reason
            and "runs at any width.) — next: Run the same command with TMPDIR="
            in reason),
        "no temp root": lambda reason: reason == (
            "the first run under the pin could not be given a place to run "
            "in: FileNotFoundError: No such file or directory. Disclosed, "
            "never a pass."),
    }
    faulted = {case: (not found[0] and len(found[1]) == 1
                      and wanted[case](found[1][0]))
               for case, (found, _clean) in said.items()}
    cleaned = {case: _proven(clean)
               for case, (_found, clean) in said.items()}

    def _shown(reason: str) -> str:
        """A SKIP reason as the row quotes it: the too-wide root's names the
        private root and the absent root's names the box, machine paths that
        are new on every run."""
        return _one_line(reason.replace(private, "<private root>")
                         .replace(box, "<box>"), 160)
    check(label,
          all(faulted.values()) and all(cleaned.values()) and left == [],
          ACTUAL + "; ".join(
              f"{case} -> SKIP as wanted={faulted[case]}, "
              f"{[(ok, _one_line(d, 60)) for ok, d in found[0]]} "
              f"{[_shown(r) for r in found[1]]}"
              ", a PASS row without "
              f"it={cleaned[case]}"
              for case, (found, _clean) in said.items())
          + f"; left under the private root -> {left}"
          + f"; {_PLANTED_SAID[planted]}")


# ----------------------------------------- the order `run.place` prepares in (lllllll)

#: One subject for the arm over the order of a place's preparation: it notes
#: in a log what it found at a path and exits 1 when that is the wrong
#: thing to find — a `precondition` that finds the file, a `step` that does
#: not.
_ORDER_SUBJECT = '''\
import os
import sys

mode, log, path = sys.argv[1:4]
found = os.path.isfile(path)
if found:
    with open(path, encoding="utf-8") as handle:
        note = handle.read().strip()
else:
    note = "absent"
with open(log, "a", encoding="utf-8") as handle:
    handle.write(f"{mode}: {note}\\n")
sys.exit(1 if (mode == "precondition") == found else 0)
'''

#: The manifest: a `[files]` entry and a `[[setup]]` step the one surface
#: needs, which reads that entry. `{log}` is a TOML string.
_ORDER_MANIFEST = _subject("order", '["<PYTHON>", "order.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["out"]

[surfaces.out]
args  = ["row", "-", "-"]
needs = ["read"]

[files."config.txt"]
lines = ["fast"]

[[setup]]
name    = "read"
command = ["<PYTHON>", "<HERE>/order.py", "step", {log}, "<WORK>/config.txt"]
'''

#: A `command` precondition that fails when the `[files]` entry exists.
_ORDER_CENSUS = _STUB_ENVIRONMENT + '''
[[input]]
name        = "the config does not exist yet"
disposition = "precondition"
check       = "command"
command     = [{python}, "order.py", "precondition", {log}, "<WORK>/config.txt"]
expect      = "exit 0"
finding     = "planted: the command exits 1 when the file exists"
'''


def _place_order_control(check: CheckRow) -> None:
    """(lllllll) `run.place` writes the manifest's `[files]` after the
    census's preconditions and before the `[[setup]]` steps a row needs.

    One place is made for a manifest whose precondition exits 1 when
    `<WORK>/config.txt` exists and whose setup step exits 1 when it does
    not, and records what each found there in a log the arm owns. The place
    is made without a refusal, the log reads that the precondition found
    nothing and then that the step read the entry's text, and the file is
    in the place. A `[files]` write moved in front of the preconditions
    makes the precondition refuse; one moved behind the setup steps makes
    the step refuse.
    """
    label = ("lllllll  `run.place` prepares a place in an order: the "
             "census's preconditions run first and find no `[files]` entry "
             "yet, the entry is written next, and the `[[setup]]` step a row "
             "needs runs last and reads it, so the place is made without a "
             "refusal")
    with _box("golden-census-order-") as box:
        log = os.path.join(box, "order.log")
        manifest = load_manifest(_scratch(
            box, manifest_text=_ORDER_MANIFEST.replace(
                "{log}", json.dumps(log)),
            census_text=_ORDER_CENSUS.replace("{log}", json.dumps(log)).replace(
                "{python}", json.dumps(sys.executable, ensure_ascii=False)),
            extra={"order.py": _ORDER_SUBJECT}))
        refused: Refusal | None = None
        in_place: str | None = None
        try:
            with place(manifest, "golden-census-order-", io.StringIO(),
                       rows=[(manifest.inputs[0], manifest.surfaces["out"])]
                       ) as where:
                entry = os.path.join(where.roots.work, "config.txt")
                in_place = (pathlib.Path(entry).read_text(encoding="utf-8")
                            if os.path.isfile(entry) else None)
        except Refusal as raised:
            refused = raised
        logged = (pathlib.Path(log).read_text(encoding="utf-8").splitlines()
                  if os.path.isfile(log) else [])
    check(label,
          refused is None and logged == ["precondition: absent",
                                         "step: fast"]
          and in_place == "fast\n",
          ACTUAL + f"refusal -> {refused is not None}"
          + (f" ({_one_line(str(refused), 120)})" if refused else "")
          + f"; what the precondition and the step found, in order -> "
          f"{logged}; the entry in the place -> {in_place!r}")


# ------------------------------- the verdicts of two controls (mmmmmmm, nnnnnnn)
#
# Two controls of `controls.py` whose verdicts no arm held: the `drift` pin's
# and the regex fold's. Each arm plants one census row per outcome and asserts what the
# control DECIDED — whether its row passed, how many SKIPs it made, and the
# one fragment of its detail that says which half of the control held — and
# not the control's sentences.

def _census_found(box: str, census_text: str, *, name: str,
                  disposition: str = "pin",
                  manifest_text: str = _STUB_MANIFEST,
                  extra: dict[str, str] | None = None,
                  work: str | None = None) -> _PinFound:
    """The rows `(ok, detail)` and the SKIP reasons the census controls make
    for the census row `name`, over a scratch manifest and census written
    into `box`. The work directory is `work` where one is named, else `box`
    itself."""
    manifest = load_manifest(_scratch(box, manifest_text=manifest_text,
                                      census_text=census_text, extra=extra))
    roots = Roots(root=manifest.subject.root, work=work or box, clone=None)
    rows, skips = _census_rows(manifest, roots)
    return _pin_rows(rows, skips, name, disposition)


def _outcome(found: _PinFound) -> str:
    """A census row's outcome as the arms below print it: `PASS` or `FAIL`
    for its one row, `no row` or the count when it made none or several,
    then its number of SKIPs."""
    rows, skips = found
    shown = ("no row" if not rows else
             ("PASS" if rows[0][0] else "FAIL") if len(rows) == 1 else
             f"{len(rows)} rows")
    return f"{shown}, {len(skips)} SKIP(s)"


#: Arm `mmmmmmm`'s `drift` pins: (name, variable, the Python the command
#: runs, or None for a program that is not there, the control's `output`
#: file or None for its standard output, the rows' `ok`, the number of
#: SKIPs, and the fragments of the detail that say which half of the
#: control held). A command reads the pin's variable or the clock, so the
#: unpinned pair differs or agrees by what the command does. The one with
#: an `output` counts its calls in the work directory, which every census
#: run of the arm shares, and writes `A`, `A`, nothing, `B` on the four
#: runs of each: its second pinned run, read as the file the run before it
#: left, would make the pinned pair identical. The removal's boundary is
#: held apart, in `_DRIFT_KEPT`.
_DRIFT_CASES: tuple[tuple[str, str, str | None, str | None, list[bool],
                          int, tuple[str, ...]], ...] = (
    ("holds the pin and moves without it", "DRIFT_HELD",
     'import os, time; print(os.environ.get("DRIFT_HELD") or time.time_ns())',
     None, [True], 0, ()),
    ("moves under the pin", "DRIFT_IGNORED",
     "import time; print(time.time_ns())",
     None, [False], 0, ("identical=False", "differ=True")),
    ("does not move without the pin", "DRIFT_STEADY",
     'print("steady")',
     None, [False], 0, ("identical=True", "differ=False")),
    ("exits 3", "DRIFT_FAILING",
     "raise SystemExit(3)",
     None, [False], 0, ("exits [3, 3, 3, 3]",)),
    ("writes no output file on its second pinned run", "DRIFT_UNWRITTEN",
     'import os; c = "<WORK>/unwritten.count"; '
     'n = int(open(c).read()) if os.path.exists(c) else 0; '
     'open(c, "w").write(str(n + 1)); '
     'n % 4 == 2 or open("<WORK>/unwritten.txt", "w").write("AB"[n % 4 // 3])',
     "<WORK>/unwritten.txt", [False], 0, ("identical=False", "differ=True")),
    ("writes its output file by a path relative to <WORK>", "DRIFT_RELATIVE",
     'import os, time; open("relative.txt", "w").write('
     'os.environ.get("DRIFT_RELATIVE") or str(time.time_ns()))',
     "relative.txt", [True], 0, ()),
    ("is not a program on PATH", "DRIFT_ABSENT", None, None, [], 1, ()))

#: How the refusal of an `output` that names no file under <WORK> ends,
#: when the census is read, `{output}` the `output` as `repr` spells it.
_DRIFT_READ = ("row 'kept': the `drift` control's `output` {output} is not "
               "a file under <WORK>")

#: Arm `mmmmmmm`'s `output` files outside <WORK>, which the control must
#: never remove or read, before a run or after it: (name, the Python the
#: command runs, the file, relative to the box the arm keeps it in, the
#: `output` that names it, `{file}` standing for the file's own absolute
#: path, and how the refusal the census meets ends). Each runs in a census
#: of its own, over a work directory of its own, beside the box's
#: `kept.txt`, so that no case's runs reach another's. They name it by an
#: absolute path, under `<ROOT>` — the box — by two spellings that climb out
#: of `<WORK>` with `..`, and as `<WORK>` itself.
_DRIFT_KEPT: tuple[tuple[str, str, str, str, str], ...] = (
    ("an absolute `output` outside <WORK>", "pass", "kept.txt", "{file}",
     _DRIFT_READ),
    ("an `output` under <ROOT>", "pass", "kept.txt", "<ROOT>/kept.txt",
     _DRIFT_READ),
    ("a relative `output` that climbs out of <WORK>", "pass", "kept.txt",
     "../kept.txt", _DRIFT_READ),
    ("an `output` under <WORK> that climbs out of it", "pass", "kept.txt",
     "<WORK>/../kept.txt", _DRIFT_READ),
    ("an `output` that names <WORK> itself", "pass", "kept.txt", "<WORK>/.",
     _DRIFT_READ))

#: Arm `mmmmmmm`'s `output` values the census refuses for what they are
#: before it reads them as a spelling: (name, the value as TOML writes it,
#: how the refusal ends). An empty string, read as absent, would compare
#: standard output in silence, and so would an array, `false` and a table;
#: an integer would be read as a file of that name. Each is a census of its
#: own; its command never runs.
_DRIFT_UNREAD: tuple[tuple[str, str, str], ...] = (
    ("an empty `output`", '""',
     "row 'kept': the `drift` control's `output` is empty"),
    ("an `output` that is an array", "[]",
     "row 'kept': the `drift` control's `output` must be a string, not "
     "the list []"),
    ("an `output` that is a boolean", "false",
     "row 'kept': the `drift` control's `output` must be a string, not "
     "the bool False"),
    ("an `output` that is a table", "{}",
     "row 'kept': the `drift` control's `output` must be a string, not "
     "the dict {}"),
    ("an `output` that is an integer", "7",
     "row 'kept': the `drift` control's `output` must be a string, not "
     "the int 7"))

#: The census row every case of `_DRIFT_KEPT` and `_DRIFT_UNREAD` is, after
#: the stub's environment: `{file}` is what the row's `finding` says the
#: command leaves, `{command}` the command and `{output}` the `output`, each
#: as TOML writes it.
_DRIFT_KEPT_PIN = '''
[[input]]
name        = "kept"
disposition = "pin"
variable    = "DRIFT_KEPT"
value       = "0"
finding     = "planted: a command that leaves {file}"
control     = {{ shape = "drift", command = {command}, output = {output}, wait = 0.0 }}
'''

#: Arm `mmmmmmm`'s census of a program found on the PATH the census pins and
#: not on golden-census's own: one pin sets PATH to a directory of the arm's
#: — its own control's command is the interpreter's absolute path, so its
#: unpinned runs need no PATH — and the other's command is a bare name only
#: that directory holds.
_DRIFT_ON_CENSUS_PATH = f'''
[[input]]
name        = "the census's PATH"
disposition = "pin"
variable    = "PATH"
value       = "<HERE>/bin"
finding     = "planted: the census pins PATH to a directory of its own"
control     = {{ shape = "drift", command = {json.dumps([
    "<PYTHON>", "-c",
    "import os, time; print(os.environ.get('PATH') or time.time_ns())"])}, wait = 0.0 }}

[[input]]
name        = "is on the census's PATH alone"
disposition = "pin"
variable    = "DRIFT_ON_PATH"
value       = "0"
finding     = "planted: a command on the census's PATH and not on golden-census's"
control     = {{ shape = "drift", command = ["mmmmmmm-clock"], wait = 0.0 }}
'''

#: Arm `mmmmmmm`'s programs spelled with a `/`, which no PATH is asked
#: about: (name, the command, and how the refusal the census meets when it
#: is read ends, "" where it loads and the control PASSES, or None where it
#: loads and the control SKIPs). A relative one names a file of the box,
#: beside the census, which the command would look for in the work
#: directory it runs in; an absolute one that is not there is a SKIP that
#: says where it looked and says nothing of PATH; `/bin/sh`, absolute and
#: there, runs, printing the pin's value or its own process id.
_DRIFT_SLASHED: tuple[tuple[str, list[str], str | None], ...] = (
    ("a program named by a relative path", ["./bin/mmmmmmm-clock"],
     "row 'slashed': the `drift` control's command names its program "
     "'./bin/mmmmmmm-clock' by a relative path, which is looked for in the "
     "work directory the command runs in, not beside this census or under "
     "the subject root."),
    ("a program named by an absolute path that is not there",
     ["<HERE>/no-such-program-mmmmmmm"], None),
    ("a program named by an absolute path that is there",
     ["/bin/sh", "-c", 'echo "${DRIFT_SLASHED:-$$}"'], ""))

#: The census row of each case of `_DRIFT_SLASHED`, after the stub's
#: environment: `{command}` the command as TOML writes it.
_DRIFT_SLASHED_PIN = '''
[[input]]
name        = "slashed"
disposition = "pin"
variable    = "DRIFT_SLASHED"
value       = "0"
finding     = "planted: a command named by a path"
control     = {{ shape = "drift", command = {command}, wait = 0.0 }}
'''

#: The same census with PATH pinned to the system's directories, run while
#: golden-census's own PATH holds the arm's directory: the bare name is on
#: the PATH golden-census runs with and not on the one the command runs
#: under, so it is a SKIP and never a refusal.
_DRIFT_ON_OWN_PATH = _DRIFT_ON_CENSUS_PATH.replace(
    '"<HERE>/bin"', '"/usr/bin:/bin"').replace(
    '"is on the census\'s PATH alone"', '"is on golden-census\'s PATH alone"')

#: A census whose one row pins PATH itself to the arm's directory, its drift
#: command a bare name only that directory holds: the row's unpinned runs
#: carry no PATH and look on `os.defpath`, so the name is not found for
#: them, and the row is a SKIP and never a refusal.
_DRIFT_PATH_ROW = '''
[[input]]
name        = "pins PATH itself"
disposition = "pin"
variable    = "PATH"
value       = "<HERE>/bin"
finding     = "planted: the row pins PATH, and its command is on that PATH alone"
control     = { shape = "drift", command = ["mmmmmmm-clock"], wait = 0.0 }
'''


def _drift_verdict_control(check: CheckRow) -> None:
    """(mmmmmmm) the `drift` control's verdict follows what its four runs did.

    One pin per outcome, over a command the arm writes. The pinned pair and
    the unpinned pair are told apart in the detail by `identical=` and
    `differ=`, a command that exits non-zero by the list of the four codes,
    and a program not on PATH makes a SKIP and no row. A command whose
    first pinned run writes its `output` file under <WORK> and whose second
    does not is read as nothing on that second run, never as the file the
    unpinned run before it wrote. A command that writes its `output` file by
    a path relative to its working directory, named by the same relative
    path, PASSES: the file is read under <WORK>, and never in
    golden-census's own working directory, where no such file is.

    Then the boundary of that removal: a file of the box beside the work
    directory, named as `output` by its absolute path, under `<ROOT>`, and
    by two spellings that climb out of <WORK> with `..`, is refused when
    the census is read, and so is `<WORK>` itself. Each is a census and a
    work directory of its own, each refusal is asserted by how it ends, and
    the file must hold its bytes after it.

    An `output` that is empty, an array, a boolean or a table, each read as
    absent where it is empty or false, or an integer, read as a file of
    that name, is refused when the census is read, before any spelling
    rule is asked, each in a census of its own: the empty one by its own
    sentence, the other four by one that names the type and the value.

    A program is looked for on the PATH of each environment it runs under,
    and never on golden-census's own: a bare name only a directory of the
    census's PATH holds PASSES, and one only golden-census's PATH holds is a
    SKIP; so is one a row's own PATH pin alone holds, which its unpinned
    runs lack. A program spelled with a `/` is asked of no PATH: a relative
    one, which the command would look for in the work directory it runs
    in, is refused when the census is read, naming it, though a file of
    that name sits beside the census; an absolute one that is not there is
    a SKIP whose reason names it and says nothing of PATH; and `/bin/sh`,
    absolute and there, loads and PASSES.
    """
    label = ("mmmmmmm  the `drift` control reaches its verdict from what its "
             "four runs did: a command that prints the pinned value and the "
             "clock without it PASSES; a command whose two pinned runs "
             "differ, one whose two unpinned runs agree and one that exits "
             "non-zero are each a FAIL, the detail naming which pair held; "
             "one whose `output` file under <WORK> its first pinned run "
             "writes and its second does not is a FAIL whose pinned pair "
             "differs, that run read as nothing and never as the file the "
             "run before it left; one that writes its `output` file by a "
             "path relative to <WORK>, named so, PASSES, the file read there "
             "and never in golden-census's own working directory; an "
             "`output` spelled as an absolute path outside <WORK>, under "
             "<ROOT>, climbing out of <WORK> with `..`, or naming <WORK> "
             "itself is refused when the census is read; each refusal names "
             "the `output`, and the file "
             "each names is still there; an `output` that is empty, an "
             "array, a boolean, a table or an integer is refused when the "
             "census is read, the first by a sentence saying it is empty "
             "and the other four by one naming the type and the value, all "
             "five with one and the same `next:`; "
             "a program that is not on PATH is a SKIP and makes no row; and "
             "PATH is the census's, so a program only the PATH the census "
             "pins holds PASSES and one only golden-census's own PATH holds "
             "is a SKIP, as is one only the PATH a row pins for itself "
             "holds, never a refusal; a program named by a relative path "
             "with a `/` is refused when the census is read, naming it, and "
             "one named by an absolute path that is not there is a SKIP "
             "whose reason names it and not PATH, and `/bin/sh`, named by "
             "an absolute path that is there, PASSES")
    pins = ""
    for name, variable, code, output, *_wanted in _DRIFT_CASES:
        command = (["<PYTHON>", "-c", code] if code is not None
                   else ["no-such-program-mmmmmmm"])
        written = f", output = {json.dumps(output)}" if output else ""
        pins += f'''
[[input]]
name        = "{name}"
disposition = "pin"
variable    = "{variable}"
value       = "0"
finding     = "planted: a command that {name}"
control     = {{ shape = "drift", command = {json.dumps(command)}{written}, wait = 0.0 }}
'''
    with _box("golden-census-drift-") as box:
        census_text = _STUB_ENVIRONMENT + pins
        found = {name: _census_found(box, census_text, name=name)
                 for name, *_rest in _DRIFT_CASES}
        clock = pathlib.Path(box, "bin", "mmmmmmm-clock")
        clock.parent.mkdir()
        _planted_script(
            str(clock), f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -c "
            "'import os, time; print(os.environ.get(\"DRIFT_ON_PATH\") or "
            "time.time_ns())'\n")
        on_path = _census_found(box, _STUB_ENVIRONMENT + _DRIFT_ON_CENSUS_PATH,
                                name="is on the census's PATH alone")
        path_row = _census_found(box, _STUB_ENVIRONMENT + _DRIFT_PATH_ROW,
                                 name="pins PATH itself")
        own = os.environ.get("PATH")
        with _env_as({"PATH": os.pathsep.join(
                [str(clock.parent)] + ([own] if own else []))}):
            off_path = _census_found(
                box, _STUB_ENVIRONMENT + _DRIFT_ON_OWN_PATH,
                name="is on golden-census's PATH alone")
        # Asked from the box, where the relative name resolves to the
        # clock: what golden-census's own working directory holds must not
        # decide it.
        slashed: dict[str, str] = {}
        with contextlib.chdir(box):
            for name, command, ends in _DRIFT_SLASHED:
                try:
                    rows, skips = _census_found(
                        box, _STUB_ENVIRONMENT + _DRIFT_SLASHED_PIN.format(
                            command=json.dumps(command)), name="slashed")
                    said = (f"{len(rows)} row(s), SKIP "
                            + "; ".join(skips))
                    passed = [ok for ok, _detail in rows] == [True]
                except Refusal as refused:
                    said = "REFUSED " + str(refused).partition("\n")[0]
                    passed = False
                if ends:
                    as_said = said.endswith(ends)
                elif ends == "":
                    as_said = passed and not skips
                else:
                    as_said = (said.startswith(
                        f"0 row(s), SKIP nothing to run at {command[0]!r}")
                        and "PATH" not in said)
                slashed[name] = ("as the label says" if as_said
                                 else said.replace(box, "<box>"))
    kept: dict[str, tuple[bool, bool]] = {}
    with _box("golden-census-drift-") as box:
        for name, code, file, output, ends in _DRIFT_KEPT:
            path = os.path.join(box, file)
            pathlib.Path(path).write_text("kept", encoding="utf-8")
            work = os.path.join(box, f"work{len(kept)}")
            os.mkdir(work)
            spelled = json.dumps(["<PYTHON>", "-c", code])
            named = output.format(file=path)
            try:
                _census_found(box, _STUB_ENVIRONMENT + _DRIFT_KEPT_PIN.format(
                    file=file, command=spelled, output=json.dumps(named)),
                    name="kept", work=work)
                said = "not refused"
            except Refusal as refused:
                said = str(refused).partition("\n")[0]
            kept[name] = (said.endswith(ends.format(output=repr(named))),
                          os.path.isfile(path) and pathlib.Path(path)
                          .read_text(encoding="utf-8") == "kept")
        unread: dict[str, str] = {}
        # Each refusal's `next:`, read off the refusal and not its first
        # line: the empty `output` and the four of another type are told
        # ONE remedy, and a sentence of its own at either site is a second.
        unread_next: set[str] = set()
        for name, output, ends in _DRIFT_UNREAD:
            try:
                _census_found(box, _STUB_ENVIRONMENT + _DRIFT_KEPT_PIN.format(
                    file="nothing", command='["<PYTHON>", "-c", "pass"]',
                    output=output), name="kept")
                unread[name] = "not refused"
            except Refusal as refused:
                said = str(refused).partition("\n")[0]
                unread[name] = ("refused as the label says"
                                if said.endswith(ends)
                                else said.replace(box, "<box>"))
                unread_next.add(refused.next)
    held = {name: [fragment in "".join(detail for _ok, detail in
                                       found[name][0])
                   for fragment in fragments]
            for name, _variable, _code, _output, _oks, _skips, fragments
            in _DRIFT_CASES}
    check(label,
          all([ok for ok, _detail in found[name][0]] == oks
              and len(found[name][1]) == skips and all(held[name])
              for name, _variable, _code, _output, oks, skips, _fragments
              in _DRIFT_CASES) and all(all(seen) for seen in kept.values())
          and all(said == "refused as the label says"
                  for said in unread.values())
          and len(unread_next) == 1 and "" not in unread_next
          and _outcome(on_path) == "PASS, 0 SKIP(s)"
          and _outcome(off_path) == "no row, 1 SKIP(s)"
          and _outcome(path_row) == "no row, 1 SKIP(s)"
          and all(said == "as the label says" for said in slashed.values()),
          ACTUAL + "; ".join(
              [f"a command that {name} -> {_outcome(found[name])}"
               + "".join(f", {fragment!r} in the detail={seen}"
                         for fragment, seen in zip(fragments, held[name], strict=True))
               for name, _variable, _code, _output, _oks, _skips, fragments
               in _DRIFT_CASES]
              + [f"{name} -> refused as the label says={refused}, still "
                 f"there={there}"
                 for name, (refused, there) in kept.items()]
              + [f"{name} -> {said}" for name, said in unread.items()])
          + f"; the {len(unread)} refusals carry {len(unread_next)} "
            "distinct `next:`"
          + f"; a command that is on the census's PATH alone -> "
            f"{_outcome(on_path)}; one on golden-census's PATH alone -> "
            f"{_outcome(off_path)}; a row that pins PATH itself -> "
            f"{_outcome(path_row)}"
          + "".join(f"; {name} -> {said}" for name, said in slashed.items()))


#: Arm `nnnnnnn`'s regex folds: (name, pattern, sample, moved, scope, the
#: rows' `ok`, the number of SKIPs, and the fragment of the detail that
#: says which half of the control held). A pattern that matches nothing has
#: no byte to change, so its one-byte half is a SKIP too. Each is a census
#: of its own, because two unscoped folds of one document overlap and the
#: loader refuses that. The unit is `US`, in capitals, which no `mkdtemp`
#: name can hold: the box is the subject root, and an unscoped pattern that
#: matched inside its random name (`…go4us`) would be refused at load for
#: rewriting the root.
_REGEX_CASES: tuple[tuple[str, str, str, str, str | None, list[bool], int,
                          tuple[str, ...]], ...] = (
    ("a pattern the sample matches", r"(?P<volatile>\d+)US",
     "scan finished in 137US", "scan finished in 2041US", None,
     [True], 0, ()),
    ("a pattern that matches neither text", r"(?P<volatile>\bNOWHERE\b)",
     "scan finished in 137US", "scan finished in 2041US", None,
     [False], 1, ("normalized identical=False",)),
    ("a sample that is its moved copy", r"(?P<volatile>\d+)US",
     "scan finished in 137US", "scan finished in 137US", None,
     [False], 0, ("unnormalized differs=False",)),
    ("a sample that is only the token", r"(?P<volatile>\d+US)",
     "137US", "2041US", None,
     [True], 1, ()),
    ("a fold scoped to one surface", r"(?P<volatile>\d+)US",
     "scan finished in 137US", "scan finished in 2041US", "_subject/help",
     [True], 0, ()))

#: The stub subject's manifest with a second surface, so a scoped fold has a
#: surface outside its scope.
_TWO_SURFACE_MANIFEST = _STUB_MANIFEST.replace(
    'surfaces = ["help"]', 'surfaces = ["help", "flag"]') + '''
[surfaces.flag]
args = ["--flag", "x"]
'''


def _regex_verdict_control(check: CheckRow) -> None:
    """(nnnnnnn) the regex fold's control decides from a planted line.

    A fold that folds the volatile token of the sample into its moved copy,
    leaves the pair different without it and still reports a byte outside
    the group PASSES; a pattern that matches neither text and a sample that
    is its own moved copy are each a FAIL, the detail naming the half that
    did not hold; a sample that is only the token has no byte outside the
    group to change, and that half is a SKIP beside a PASS row; and a fold
    scoped to one surface PASSES.
    """
    label = ("nnnnnnn  the regex fold's control decides from a planted line: "
             "a pattern that matches the sample PASSES; a pattern that "
             "matches neither text and a sample identical to its moved copy "
             "are each a FAIL, the detail naming the half that did not "
             "hold; a sample that is only the volatile token PASSES with "
             "the one-byte half SKIPPED; and a fold scoped to one surface "
             "PASSES")
    found: dict[str, _PinFound] = {}
    with _box("golden-census-regex-") as box:
        for name, pattern, sample, moved, scope, *_wanted in _REGEX_CASES:
            scoped = f'scope       = ["{scope}"]' if scope else ""
            census_text = _STUB_ENVIRONMENT + f'''
[[input]]
name        = "{name}"
disposition = "fold"
kind        = "regex"
pattern     = '{pattern}'
placeholder = "<DURATION>"
{scoped}
finding     = "planted: {name}"
control     = {{ sample = "{sample}", moved = "{moved}" }}
'''
            found[name] = _census_found(box, census_text, name=name,
                                        disposition="fold",
                                        manifest_text=_TWO_SURFACE_MANIFEST)
    held = {name: [fragment in "".join(detail for _ok, detail in
                                       found[name][0])
                   for fragment in fragments]
            for name, *_mid, fragments in _REGEX_CASES}
    check(label,
          all([ok for ok, _detail in found[name][0]] == oks
              and len(found[name][1]) == skips and all(held[name])
              for name, *_mid, oks, skips, _fragments in _REGEX_CASES),
          ACTUAL + "; ".join(
              f"{name} -> {_outcome(found[name])}"
              + "".join(f", {fragment!r} in the detail={seen}"
                        for fragment, seen in zip(fragments, held[name], strict=True))
              for name, *_mid, fragments in _REGEX_CASES))


# -------------------------------- the json-fields control over arrays (pppppp)

#: One json-fields row per shape. Every row but the top-level array's folds
#: `prov.commit`, where its sample and moved copy differ; a path names dict
#: keys from the top, so the top-level array's two copies differ instead in a
#: work-directory path the `path` fold folds. Every row applies to every
#: document, as a census's rows do, and folds nothing it does not name.
_JSON_SHAPE_ROW = """
[[input]]
name          = "{name}"
disposition   = "fold"
kind          = "json-fields"
paths         = {paths}
fields        = {fields}
placeholder   = "<C>"
serialization = {{ indent = 2, ensure_ascii = false }}
finding       = "planted: {name}"
control       = {{ sample = "{stem}-sample.json", moved = "{stem}-moved.json" }}
"""

_UNDER_A_KEY = ({"items": [{"n": 1}], "prov": {"commit": "aaa"}},
                {"items": [{"n": 1}], "prov": {"commit": "bbb"}})

#: (name, stem, paths, fields, sample, moved, the detail's end)
_JSON_SHAPES = (
    ("an array under a key", "under", '["prov"]', '["commit"]', *_UNDER_A_KEY,
     "a change at items[0].n reported=True"),
    ("a top-level array", "top", '["prov"]', '["commit"]',
     [{"n": 1, "where": "{box}/out"}], [{"n": 1, "where": "<WORK>/out"}],
     "a change at [0].n reported=True"),
    # The folded field FIRST, so a leaf search that stopped asking whether a
    # key is folded would pick it and see no change.
    ("a key holding a dot", "dot", '["prov"]', '["commit"]',
     {"prov": {"commit": "aaa"}, "a.b": {"n": 1}},
     {"prov": {"commit": "bbb"}, "a.b": {"n": 1}},
     "a change at a.b.n reported=True"),
    # A path spelled `items.0` names the key "0" of a dict, never the list's
    # first element, so `items[0].n` is outside it and is the leaf to move.
    ("a path spelled with an index", "index", '["prov", "items.0"]',
     '["commit", "n"]', *_UNDER_A_KEY,
     "a change at items[0].n reported=True"))


def _json_shapes_control(check: CheckRow) -> None:
    """(pppppp) the json-fields control reports a verdict over a sample that
    holds an array, is one, or has a key holding a `.` — never a `KeyError`.

    The control's third arm changes one scalar outside the folded fields and
    expects the change REPORTED. A leaf found as a dotted string and set by
    splitting that string on `.` again indexes a dict with `"items[0]"`, and
    the control raises, turning the row into a `[FAIL]  !` that says nothing
    about the fold; so the leaf is found and set by a trail of keys and
    indexes, and printed as a reader types it. The arm catches what the
    controls raise, so a raise is this arm's own red row.
    """
    label = ("pppppp  the json-fields control reports a verdict, never a "
             "KeyError, over a sample holding an array (a change at "
             "items[0].n), a top-level array ([0].n), a key holding a `.` — "
             "printed as it is, a.b.n, which reads like two keys — and a "
             "path spelled items.0, which folds no list element")
    said: dict[str, str] = {}
    with _box("golden-census-json-shapes-") as box:
        files: dict[str, str] = {}
        for _name, stem, _p, _f, sample, moved, _end in _JSON_SHAPES:
            for side, document in (("sample", sample), ("moved", moved)):
                files[f"{stem}-{side}.json"] = json.dumps(
                    document, indent=2, ensure_ascii=False).replace("{box}", box)
        census_text = (_STUB_ENVIRONMENT + '\n[fixtures]\ndir = "."\n'
                       + _STUB_WORK_FOLD
                       + "".join(_JSON_SHAPE_ROW.format(name=name, stem=stem,
                                                        paths=paths,
                                                        fields=fields)
                                 for name, stem, paths, fields, *_rest
                                 in _JSON_SHAPES))
        manifest = load_manifest(_scratch(box, census_text=census_text,
                                          extra=files))
        roots = Roots(root=manifest.subject.root, work=box, clone=None)
        try:
            rows, _skips = _census_rows(manifest, roots)
        except Exception as exc:      # noqa: BLE001 — the arm's subject
            if isinstance(exc, UNREPORTABLE):
                raise
            rows = []
            said["raised"] = f"{type(exc).__name__}: {exc}"
    for name, *_rest in _JSON_SHAPES:
        found = [(ok, detail) for row_label, ok, detail, _n in rows
                 if f"'{name}'" in row_label]
        said[name] = (f"{'PASS' if found[0][0] else 'FAIL'} {found[0][1]}"
                      if len(found) == 1 else f"{len(found)} row(s)")
    check(label,
          "raised" not in said
          and all(said[name].startswith("PASS ") and said[name].endswith(end)
                  for name, *_mid, end in _JSON_SHAPES),
          ACTUAL + "; ".join(f"{name} -> {_one_line(text, 140)}"
                                 for name, text in said.items()))
