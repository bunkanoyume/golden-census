"""The arms over `mutants`: a planted subject, four mutants files, the
verdicts a mutant that nothing catches earns, and the two that prove a run
against a copy of the subject executes the COPY's code.
"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import os
import pathlib
import re
import shutil
import stat

from .capture import capture
from .checks_base import PACKAGE, _capture_broke, _printed_refusal
from .census import git_env
from .cli import main
from .compare import compare
from .controls import CheckRow, SkipRow
from .core import (
    ACTUAL,
    DIFFERENCE,
    IMPORT_NAME,
    Platform,
    Refusal,
    Roots,
    UNREPORTABLE,
    launch,
    not_removed,
    refusal_text,
    temp_base,
)
from .manifest import Manifest, load_manifest
from .mutants import (
    Mutant,
    Mutants,
    Refused,
    Row,
    Verdict,
    _chosen,
    _report,
    clone_subject,
    load_mutants,
    plant,
    run_check,
    run_mutants,
)
from .proof import (
    _STUB_CENSUS,
    _STUB_ENVIRONMENT,
    _STUB_WORK_FOLD,
    _box,
    _chmod_bites,
    _env_as,
    _heard,
    _one_line,
    _package_argv,
    _quietly,
    _repo_of,
    _root_fold,
    _subject,
    _tmpdir_as,
)
from .run import (
    clone_input,
    repository_folder,
    resolve_command,
    resolved_address,
    subject_command,
)

# -------------------------------------------------- the mutants command (x-aa)
#
# A throwaway subject in a git repository, so the `mutants` command can be
# driven end to end without a consumer: `git clone --local` needs a repository,
# and the whole point of the command is the repo-shaped copy. Nothing here is
# committed anywhere — the box is a temporary directory and goes with it.
#
# The four arms are the ones `docs/mutants-format.md` names in its last
# section. All four go RED by construction: a refusal, a FAIL row, a refusal
# and a FAIL row. The one PASS in the set rides inside (y), whose first mutant
# IS caught — a table of FAILs would prove only that the failure path works.

_MUTANT_SUBJECT = '''\
import sys

VERSION = "1.0"


def main(argv):
    if "--version" in argv:
        print(VERSION)
        return 0
    print("rows: 3")
    return 0


sys.exit(main(sys.argv[1:]))
'''

#: The consumer's own script, BESIDE the mutants file rather than in the
#: subject: it exercises the other half of the cwd rule.
_MUTANT_PROBE = '''\
import sys

with open(sys.argv[1] + "/tool.py", encoding="utf-8") as handle:
    text = handle.read()
sys.stdout.write("MOVED\\n" if 'rows: 3' not in text else "SAME\\n")
'''

_MUTANT_CENSUS = _STUB_ENVIRONMENT + _root_fold(
    "the clone's path is a different directory on every run")

_MUTANT_MANIFEST = _subject("mutant-stub", '["<PYTHON>", "tool.py"]', root="subject") + '''
[inputs._subject]
args     = []
surfaces = ["rows"]

[surfaces.rows]
args = []
'''

_CHECK_VERSION = '''\
[checks.version]
command = ["<PYTHON>", "tool.py", "--version"]
fires   = { absent = "1.0" }
'''

_CHECK_PROBE = '''\
[checks.probe]
command = ["<PYTHON>", "probe.py", "<ROOT>"]
fires   = { pattern = "MOVED" }
'''

#: (x) a `find` that occurs twice — `print` is on two lines of the subject.
_MUTANTS_X = _CHECK_VERSION + '''
[[mutant]]
name    = "the two prints"
file    = "tool.py"
find    = "print"
replace = "sys.stdout.write"
expect  = ["version"]
'''

#: (y) one mutant every expected check catches, and one it does not.
_MUTANTS_Y = _CHECK_VERSION + _CHECK_PROBE + '''
[[mutant]]
name    = "the version string"
file    = "tool.py"
find    = 'VERSION = "1.0"'
replace = 'VERSION = "9.9"'
expect  = ["version"]

[[mutant]]
name    = "the row count"
file    = "tool.py"
find    = 'print("rows: 3")'
replace = 'print("rows: 4")'
expect  = ["version"]
'''

#: (z) a check that fires on anything at all, the null mutant included.
_MUTANTS_Z = _CHECK_VERSION + '''
[checks.always]
command = ["<PYTHON>", "-c", "raise SystemExit(3)"]
fires   = "exit-nonzero"

[[mutant]]
name    = "the version string"
file    = "tool.py"
find    = 'VERSION = "1.0"'
replace = 'VERSION = "9.9"'
expect  = ["version"]
'''

#: (aa) a mutant no check in the file can see, expecting none of them: the
#: hole in the net that `expect` alone would never report.
_MUTANTS_AA = _CHECK_VERSION + '''
[[mutant]]
name    = "the row count"
file    = "tool.py"
find    = 'print("rows: 3")'
replace = 'print("rows: 4")'
expect  = []
'''


def _mutant_box(box: str, repository: bool = True
                ) -> tuple[str | None, str]:
    """Write the throwaway subject, its repository and the four mutants files.
    Returns (manifest path, "") or (None, why this machine cannot run them).
    `repository` False writes the files and makes no repository: a capture
    of the subject needs none, and only `mutants` clones it."""
    root = os.path.join(box, "subject")
    os.makedirs(root)
    files = {os.path.join(root, "tool.py"): _MUTANT_SUBJECT,
             os.path.join(box, "probe.py"): _MUTANT_PROBE,
             os.path.join(box, "census.toml"): _MUTANT_CENSUS,
             os.path.join(box, "manifest.toml"): _MUTANT_MANIFEST,
             os.path.join(box, "x.toml"): _MUTANTS_X,
             os.path.join(box, "y.toml"): _MUTANTS_Y,
             os.path.join(box, "z.toml"): _MUTANTS_Z,
             os.path.join(box, "aa.toml"): _MUTANTS_AA}
    for path, text in files.items():
        pathlib.Path(path).write_text(text, encoding="utf-8", newline="\n")
    if not repository:
        return os.path.join(box, "manifest.toml"), ""
    try:
        code, head, stderr = _repo_of(root, "the stub")
    except Refusal as refused:
        # The SKIP's reason, not the arm's verdict: a machine with no
        # `git` cannot run the mutants arms, which is a fact about the
        # machine and never a pass.
        return None, str(refused)
    if code != 0:
        return None, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}"
    return os.path.join(box, "manifest.toml"), ""


def _mutants_run(manifest: Manifest, box: str, name: str) -> tuple[int, str]:
    """One mutants file, run to completion. A refusal comes back as exit 2 with
    its sentence, which is what the command line prints; a raise comes back
    as exit -1 naming it, so the arm that ran it reports its own verdict."""
    buf = io.StringIO()
    try:
        code = run_mutants(manifest, load_mutants(os.path.join(box, name)), buf)
    except Refusal as refused:
        return 2, refusal_text(refused)
    except Exception as exc:                    # reported, not raised
        if isinstance(exc, UNREPORTABLE):
            raise
        return -1, f"raised {type(exc).__name__}: {exc}"
    return code, buf.getvalue()


def _mutants_controls(check: CheckRow, skip: SkipRow) -> None:
    """(x) (y) (z) (aa) the `mutants` command's own four arms."""
    label = ("x, y, z, aa  the mutants command's four arms (a non-unique "
             "`find`, an expected check that stays silent, a check that fires "
             "on the null mutant, a mutant every check misses)")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, and every arm needs `git clone "
                    "--local` to make the repo-shaped copy the command plants "
                    "in. Nothing was made and nothing is claimed.")
        return
    with _box("golden-census-mutant-arms-") as box:
        path, why = _mutant_box(box)
        if path is None:
            skip(label, f"the throwaway subject could not be put in a git "
                        f"repository: {why}. Nothing is claimed.")
            return
        try:
            manifest = load_manifest(path)
        except Refusal as refused:
            skip(label, f"the scratch manifest would not load: {refused}. "
                        "Nothing is claimed.")
            return
        x_code, x_text = _mutants_run(manifest, box, "x.toml")
        y_code, y_text = _mutants_run(manifest, box, "y.toml")
        z_code, z_text = _mutants_run(manifest, box, "z.toml")
        a_code, a_text = _mutants_run(manifest, box, "aa.toml")

    check("x  a mutant whose `find` occurs twice in the file is REFUSED by "
          "name, before a single clone is made — a mutant the code moved out "
          "from under is never a silent pass",
          x_code == 2 and "the two prints" in x_text
          and "occurs 2 times" in x_text
          and "a mutant is one edit to one place" in x_text,
          f"{ACTUAL}exit {x_code}, {_one_line(x_text, 150)!r}")

    check("y  a check a mutant's `expect` names that stays SILENT is a FAIL "
          "row and the exit is 1, while the mutant the same check does catch "
          "passes in the same table, and a check that fires without being "
          "expected is annotated rather than failed",
          y_code == 1
          and re.search(r"the version string\s+FIRED\s+SILENT", y_text)
              is not None
          and "(version: expected, SILENT)" in y_text
          and "(probe: unexpected)" in y_text
          and "1/2 mutants caught" in y_text
          and "FAIL  the row count" in y_text,
          f"{ACTUAL}exit {y_code}, {_one_line(y_text)!r}")

    check("z  a check that FIRES on the null mutant — the unmutated copy — "
          "REFUSES the whole run naming that check, rather than printing a "
          "column of FIREDs that mean nothing",
          z_code == 2 and "null mutant" in z_text and "always" in z_text,
          f"{ACTUAL}exit {z_code}, {_one_line(z_text, 150)!r}")

    check("aa  a mutant no check catches is a FAIL even though its `expect` "
          "names nobody: an uncaught mutant is a hole in the net, and a table "
          "that only read `expect` would call it a pass",
          a_code == 1 and "(no check fired)" in a_text
          and "0/1 mutants caught" in a_text,
          f"{ACTUAL}exit {a_code}, {_one_line(a_text)!r}")


# ------------------- the refusals that only read files come first (uuuuuuuu)
#
# `--only` naming no mutant and a mutant whose `find` has moved are both found
# by reading files, so `cli.main` refuses them above the census's controls,
# which start the subject. The third run is the positive control: a command
# that is not refused still prints the controls above its `MUTANTS` header, so
# the arm can tell the two orders apart.

def _refused_first_control(check: CheckRow, skip: SkipRow) -> None:
    """(uuuuuuuu) a typo in `--only` and a stale mutant are refused before the
    census's controls run."""
    label = ("uuuuuuuu  `mutants` refuses an `--only` name no mutant has and a "
             "mutant whose `find` occurs twice at exit 2 without printing the "
             "census's controls first, while a run that is not refused prints "
             "them above its MUTANTS header")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, and every arm needs `git clone "
                    "--local` to make the repo-shaped copy the command plants "
                    "in. Nothing was made and nothing is claimed.")
        return
    with _box("golden-census-refused-first-") as box:
        path, why = _mutant_box(box)
        if path is None:
            skip(label, f"the throwaway subject could not be put in a git "
                        f"repository: {why}. Nothing is claimed.")
            return
        runs = [_quietly(main, ["mutants", "--manifest", path, "--mutants",
                                os.path.join(box, name), *extra])
                for name, extra in (("y.toml", ["--only", "renmae"]),
                                    ("x.toml", []), ("y.toml", []))]

    def after_group(text: str) -> str:
        lines = text.splitlines()
        for at, line in enumerate(lines):
            if line.startswith("process group "):
                return next((rest for rest in lines[at + 1:] if rest), "")
        return ""

    def before(text: str, mark: str) -> str:
        return text.split(mark)[0] if mark in text else text

    (only_code, only_text), (stale_code, stale_text), (plain_code, plain_text) = runs
    check(label,
          only_code == 2 and "--only 'renmae': no [[mutant]] has that name." in only_text
          and "census controls" not in before(only_text, "REFUSED:")
          and stale_code == 2 and "`find` occurs 2 times in tool.py" in stale_text
          and "census controls" not in before(stale_text, "REFUSED:")
          and "census controls passed" in before(plain_text, "\nMUTANTS  "),
          f"{ACTUAL}--only: exit {only_code}, {after_group(only_text)!r}; "
          f"stale: exit {stale_code}, {after_group(stale_text)!r}; "
          f"plain: exit {plain_code}, {after_group(plain_text)!r}")


# ------------------- the null mutant names the uncommitted paths (tttttttt)
#
# The clone is the last COMMIT, so a file the subject needs that nobody
# committed is missing from it. The arm runs `z.toml` (a check that always
# fires) on a clean tree and on a dirty one.

def _dirty_tree_control(check: CheckRow, skip: SkipRow) -> None:
    """(tttttttt) the null-mutant refusal names what `git status` lists."""
    label = ("tttttttt  a null-mutant refusal from a subject whose tree holds "
             "an uncommitted new file and a modified committed file adds one "
             "sentence naming `2 path(s)` and both `git status --porcelain` "
             "lines, with the `next:` unchanged; the same refusal from a "
             "clean tree has no such sentence")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, and the arm needs a repository to "
                    "ask `git status` of. Nothing was made and nothing is "
                    "claimed.")
        return
    with _box("golden-census-dirty-tree-") as box:
        path, why = _mutant_box(box)
        if path is None:
            skip(label, f"the throwaway subject could not be put in a git "
                        f"repository: {why}. Nothing is claimed.")
            return
        try:
            manifest = load_manifest(path)
        except Refusal as refused:
            skip(label, f"the scratch manifest would not load: {refused}. "
                        "Nothing is claimed.")
            return
        _clean_code, clean = _mutants_run(manifest, box, "z.toml")
        root = os.path.join(box, "subject")
        with open(os.path.join(root, "tool.py"), "a", encoding="utf-8",
                  newline="\n") as tool:
            tool.write("# edited after the commit\n")
        pathlib.Path(root, "extra.py").write_text("X = 1\n", encoding="utf-8",
                                                  newline="\n")
        _dirty_code, dirty = _mutants_run(manifest, box, "z.toml")

    def last_sentence(text: str) -> str:
        return text.split("\n  next:")[0].rsplit(". ", 1)[-1]

    next_line = ("\n  next: Fix the check(s) named above so they are silent "
                 "on an unchanged subject, then run `mutants` again.")
    check(label,
          "`git status --porcelain` in the subject root lists 2 path(s)" in dirty
          and "` M tool.py`" in dirty
          and "`?? extra.py`" in dirty
          and dirty.endswith(next_line)
          and "git status" not in clean and clean.endswith(next_line)
          and "null mutant" in clean,
          f"{ACTUAL}dirty: {_one_line(last_sentence(dirty), 200)!r}; "
          f"clean: {_one_line(last_sentence(clean), 200)!r}")


# ------------------------- a commit that leaves the clone not clean (ggggggggg)


def _unclean_commit_control(check: CheckRow, skip: SkipRow) -> None:
    """(ggggggggg) `plant` after its commit: a clone git still lists
    something in is refused with the facts the run has, a `git status`
    that fails is refused in git's words, and a clean one is planted.

    The dirt comes from the repository's own `.gitattributes`: `a.txt
    filter=f`, with the filter's `clean` given through
    `GIT_CONFIG_PARAMETERS`, which `census.git_env` keeps, as `cat; touch
    junk.txt`. The commit runs the filter, the filter leaves an untracked
    file, and `git status --porcelain` lists it whatever the index's stat
    cache says of `a.txt`. The failing `git status` is a `git` in front of
    the real one on PATH that fails that one word. The clone is made by
    hand, so no other step of `mutants` is between the plant and the row.
    """
    label = ("ggggggggg  a mutant whose commit leaves the clone not clean is "
             "refused naming the mutant, the file and what `git status "
             "--porcelain` lists, saying the edit was committed in a clone of "
             "golden-census's own with every hook off and no global ignore "
             "file, and saying to reproduce it by hand in a clone of the "
             "subject; a `git status` that fails after the commit is refused "
             "in git's own words with the commit refusal's `next:`; and a "
             "mutant whose commit leaves the clone clean is planted at a new "
             "HEAD")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, so no clone can be made; nothing "
                    "was made and nothing is claimed.")
        return
    mutant = Mutant("m", "a.txt", "alpha", "beta")
    results: dict[str, str] = {}
    with _box("golden-census-unclean-commit-") as box:
        root = os.path.join(box, "subject")
        os.makedirs(root)
        pathlib.Path(root, "a.txt").write_text("alpha\n", encoding="utf-8",
                                               newline="\n")
        pathlib.Path(root, ".gitattributes").write_text(
            "a.txt filter=f\n", encoding="utf-8", newline="\n")
        try:
            code, head, stderr = _repo_of(root, "the subject")
        except Refusal as refused:
            skip(label, f"{refused}; nothing was made and nothing is claimed.")
            return
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing was made and nothing is claimed.")
            return
        failing = os.path.join(box, "failing")
        os.makedirs(failing)
        script = os.path.join(failing, "git")
        pathlib.Path(script).write_text(
            '#!/bin/sh\nfor word in "$@"; do if [ "$word" = status ]; then '
            'echo "fatal: planted" >&2; exit 128; fi; done\n'
            f'exec {json.dumps(shutil.which("git"))} "$@"\n',
            encoding="utf-8", newline="\n")
        os.chmod(script, os.stat(script).st_mode | stat.S_IXUSR)
        for key, variables in (
                ("dirty", {"GIT_CONFIG_PARAMETERS":
                           "'filter.f.clean=cat; touch junk.txt'"}),
                ("failing", {"PATH": failing + os.pathsep
                             + os.environ.get("PATH", "")}),
                ("clean", {})):
            clone = os.path.join(box, "clone-" + key)
            made = launch(["git", "clone", "-q", root, clone], "git clone",
                          env=git_env())
            if made.returncode != 0:
                skip(label, f"`git clone` exited {made.returncode}: "
                            f"{made.stderr[:DIFFERENCE]}; nothing is claimed.")
                return
            before = launch(["git", "-C", clone, "rev-parse", "HEAD"],
                            "git rev-parse", env=git_env()).stdout.strip()
            try:
                with _env_as(variables):
                    plant(clone, mutant)
            except Refusal as refused:
                results[key] = refusal_text(refused)
                continue
            after = launch(["git", "-C", clone, "rev-parse", "HEAD"],
                           "git rev-parse", env=git_env()).stdout.strip()
            listed = launch(["git", "-C", clone, "status", "--porcelain"],
                            "git status", env=git_env()).stdout.strip()
            results[key] = (f"planted, HEAD {'moved' if after != before else 'unmoved'}, "
                            f"status lists {listed!r}")
    dirty = results.get("dirty", "")
    sentence = ("mutant 'm': the clone is not clean after the commit of its "
                "edit to a.txt: `git status --porcelain` lists '?? junk.txt'. "
                "golden-census committed the edit in a clone of its own under "
                "the temp root, with every hook off and no global ignore file, "
                "so what git lists comes from the repository itself.")
    advice = ("next: Clone the subject by hand, make this mutant's edit to "
              "a.txt, run `git commit -a` and then `git status --porcelain` "
              "there: what it lists is the cause, usually a .gitattributes "
              "rule that does not round-trip that file, or two committed "
              "names this disk reads as one. Fix it in the repository and run "
              "`mutants` again.")
    failed = results.get("failing", "")
    check(label,
          dirty.startswith("REFUSED: " + sentence) and dirty.endswith(advice)
          and failed.startswith("REFUSED: mutant 'm': `git status --porcelain` "
                                "in the clone exited 128")
          and "fatal: planted" in failed
          and failed.endswith("next: Run `mutants` again; if it repeats, fix "
                              "what git reports above.")
          and results.get("clean") == "planted, HEAD moved, status lists ''",
          f"{ACTUAL}dirty: {_one_line(dirty, 400)!r}; failing: "
          f"{_one_line(failed, 200)!r}; clean: {results.get('clean')!r}")


# ------------------------------- a key of the other check kind (yyyyyyy)
#
# `fires` is read for a `command` check and `golden` for a `builtin = "compare"`
# one. The arm only LOADS the file, so it needs no `git` and no clone.

#: A mutants file with the one check `{check}` and one mutant that expects
#: nothing; the mutant only has to be a row `load_mutants` accepts.
_OTHER_KIND = '''\
[checks.c]
{check}
[[mutant]]
name    = "m"
file    = "tool.py"
find    = "x"
replace = "y"
expect  = []
'''

#: The four checks the arm plants: each kind with a key of its own and with a
#: key of the other kind.
_OTHER_KIND_CHECKS = {
    "a builtin check with `fires`":
        'builtin = "compare"\ngolden  = "golden"\nfires   = "exit-nonzero"\n',
    "a command check with `golden`":
        'command = ["<PYTHON>", "tool.py"]\nfires   = "exit-nonzero"\n'
        'golden  = "golden"\n',
    "a builtin check with `golden`":
        'builtin = "compare"\ngolden  = "golden"\n',
    "a command check with `fires`":
        'command = ["<PYTHON>", "tool.py"]\nfires   = "exit-nonzero"\n',
}


def _other_kind_control(check: CheckRow) -> None:
    """(yyyyyyy) a mutants-file key of the other check kind is refused."""
    label = ("yyyyyyy  a `fires` key on a `builtin = \"compare\"` check and a "
             "`golden` key on a `command` check are each refused at LOAD, "
             "naming the check and the key: the check runs without the key, "
             "so it would sit in the file doing nothing. The controls are "
             "each kind with only its own key, which load")
    verdicts: dict[str, str] = {}
    for name, body in _OTHER_KIND_CHECKS.items():
        with _box("golden-census-other-kind-") as box:
            path = os.path.join(box, "mutants.toml")
            pathlib.Path(path).write_text(_OTHER_KIND.format(check=body),
                                          encoding="utf-8", newline="\n")
            verdicts[name] = _printed_refusal(
                functools.partial(load_mutants, path), unrefused="LOADED")
    fires = verdicts["a builtin check with `fires`"]
    golden = verdicts["a command check with `golden`"]
    fires_refused = (fires.startswith("REFUSED: ")
                     and "[checks.c]: `fires` is not read for a "
                     "`builtin = \"compare\"` check." in fires
                     and fires.endswith(
                         "\n  next: Drop `fires` from this check, or replace "
                         "`builtin` with a `command` to have a check that "
                         "reads it."))
    golden_refused = (golden.startswith("REFUSED: ")
                      and "[checks.c]: `golden` is not read for a `command` "
                      "check." in golden
                      and golden.endswith(
                          "\n  next: Drop `golden` from this check, or "
                          "replace `command` with `builtin = \"compare\"` to "
                          "compare against that golden directory."))
    loads = all(verdicts[name] == "LOADED" for name in list(verdicts)[2:])
    check(label, fires_refused and golden_refused and loads,
          ACTUAL + "; ".join(
              f"{name} -> "
              + ("REFUSED naming the check and the key"
                 if verdicts[name].startswith("REFUSED: ")
                 else verdicts[name])
              for name in verdicts))


# ------------------------- every unknown `--only` name, in one refusal (lll)
#
# `--only` repeats, and the names are checked before the first clone, so the
# arm needs no `git`: the refusal it reads is raised before `mutants` makes
# anything.

def _only_names_control(check: CheckRow, skip: SkipRow) -> None:
    """(lll) every `--only` name no mutant has is quoted in one refusal."""
    label = ("lll  every `--only` name no [[mutant]] has is quoted in ONE "
             "refusal, in the order given, above the file's names one per "
             "line, before a single clone is made; a name the file has passes "
             "through and is not quoted among them")
    with _box("golden-census-only-names-") as box:
        path, why = _mutant_box(box, repository=False)
        if path is None:
            skip(label, f"the scratch subject could not be written: {why}. "
                        "Nothing is claimed.")
            return
        try:
            manifest = load_manifest(path)
            mutants = load_mutants(os.path.join(box, "y.toml"))
        except Refusal as refused:
            skip(label, f"the scratch files would not load: {refused}. "
                        "Nothing is claimed.")
            return
        two = _printed_refusal(functools.partial(
            run_mutants, manifest, mutants, io.StringIO(), ("renmae", "nul")))
        mixed = _printed_refusal(functools.partial(
            run_mutants, manifest, mutants, io.StringIO(), ("the row count", "nul")))
        passed = [m.name for m in _chosen(mutants, ("the row count",))]
        expected = ("REFUSED: --only 'renmae', 'nul': no [[mutant]] has that name.\n"
                    f"  {mutants.path} has\n"
                    "  'the version string'\n"
                    "  'the row count'\n"
                    "  next: Use --only with any of the names in y.toml, or "
                    "drop --only to plant every mutant in the file.")
    check(label,
          two == expected
          and mixed.startswith("REFUSED: --only 'nul': no [[mutant]] has that name.\n")
          and passed == ["the row count"],
          f"{ACTUAL}two bad names -> {_one_line(two, 220)!r}; one good and one "
          f"bad -> {_one_line(mixed, 60)!r}; one good -> {passed}")


# ------------------------------------------- each stream on its own (zzzzzz)
#
# A `command` check's pattern and its `absent` text are searched over stdout
# and over stderr, each on its own. Joined, a stdout with no final newline
# puts its last line and stderr's first on one line: `^` cannot anchor at
# the start of stderr, and a text can match across the join, a FIRED that
# no stream printed. The arm asks `run_check` directly over a planted check
# script, so it needs no `git` and no clone.

#: The planted check: `--anchor` prints `checked` with no newline, then
#: `boom` on stderr; `--split` prints `che` with no newline, then `cked` on
#: stderr, so `checked` exists only across the join.
_STREAMS_CHECK = '''\
import sys

if "--anchor" in sys.argv:
    sys.stdout.write("checked")
    sys.stderr.write("boom\\n")
else:
    sys.stdout.write("che")
    sys.stderr.write("cked\\n")
'''

#: Three checks over that script, and one mutant the loader needs to read a
#: mutants file at all; it is never planted.
_STREAMS_MUTANTS = '''\
[checks.anchored]
command = ["<PYTHON>", "check.py", "--anchor"]
fires   = { pattern = "^boom" }

[checks.joined]
command = ["<PYTHON>", "check.py", "--split"]
fires   = { pattern = "checked" }

[checks.split]
command = ["<PYTHON>", "check.py", "--split"]
fires   = { absent = "checked" }

[[mutant]]
name    = "the row count"
file    = "tool.py"
find    = 'print("rows: 3")'
replace = 'print("rows: 4")'
expect  = ["anchored"]
'''


#: The planted check of the TMPDIR half: one temporary file made through
#: `tempfile` and removed, then what it saw written to the report path it is
#: handed — its TMPDIR, `tempfile.gettempdir()` and the file's path, one a
#: line —
#: and, handed a second path, that directory made read-only: the arm hands
#: it the scratch directory a TMPDIR of the check's own sits in, so that
#: TMPDIR cannot be removed, and restores it. Only the path handed is
#: changed, whatever TMPDIR names.
_TMPDIR_CHECK = '''\
import os
import sys
import tempfile

handle, path = tempfile.mkstemp()
os.close(handle)
os.remove(path)
seen = os.environ.get("TMPDIR", "")
with open(sys.argv[1], "w", encoding="utf-8") as report:
    report.write(f"{seen}\\n{tempfile.gettempdir()}\\n{path}\\n")
if sys.argv[2:]:
    os.chmod(sys.argv[2], 0o555)
'''

_TMPDIR_MUTANTS = '''\
[checks.temp]
command = ["<PYTHON>", "tmp.py", "<HERE>/temp.txt"]
fires   = "exit-nonzero"

[checks.locked]
command = ["<PYTHON>", "tmp.py", "<HERE>/locked.txt", "<HERE>/work"]
fires   = "exit-nonzero"

[checks.unstarted]
command = ["golden-census-no-such-command"]
fires   = "exit-nonzero"

[[mutant]]
name    = "the row count"
file    = "tool.py"
find    = 'print("rows: 3")'
replace = 'print("rows: 4")'
expect  = ["temp"]
'''


def _streams_control(check: CheckRow, skip: SkipRow) -> None:
    """(zzzzzz) a `command` check reads stdout and stderr each on its own,
    and runs with a TMPDIR of its own.

    The TMPDIR half runs a check that makes a temporary file through
    `tempfile`, under a census that passes golden-census's own TMPDIR
    through: the check's TMPDIR is a directory made for it under the
    scratch directory `run_check` is handed, named by 8 characters and
    nothing more, so its path is 9 characters longer than that
    directory's — the room a Unix socket made under it has. `tempfile`
    makes the file there and not in the copy the check runs in, and the
    directory is gone when the check has ended — also when the check would
    not start, which is a refusal. A second check makes the directory its
    TMPDIR sits in read-only: that TMPDIR is named on the stream
    `run_check` is handed, in the one line every directory golden-census
    could not remove is named in, and the verdict is the one its `fires`
    condition gives.
    """
    label = ("zzzzzz  a `command` check searches its pattern and its `absent` "
             "text over stdout and over stderr each on its own, never the two "
             "joined: after a stdout with no final newline, `^boom` matches "
             "the `boom` stderr opens with and FIRES, `checked` printed as "
             "`che` on stdout and `cked` on stderr does NOT match and stays "
             "SILENT, and `absent = \"checked\"` over the same two FIRES; "
             "and it runs with TMPDIR a directory of its own, made under the "
             "run's scratch directory and named by 8 characters, its path 9 "
             "longer than that directory's, whatever the census passes "
             "through: "
             "its `tempfile` makes its files there and not in the copy it "
             "runs in, the directory is gone when the check has ended, one "
             "that would not start included, one the check left unremovable "
             "is named in the one line on the run's stream and the verdict "
             "stands")
    with _box("golden-census-streams-") as box:
        root = os.path.join(box, "subject")
        work = os.path.join(box, "work")
        os.makedirs(root)
        os.makedirs(work)
        files = {os.path.join(root, "tool.py"): _MUTANT_SUBJECT,
                 os.path.join(root, "check.py"): _STREAMS_CHECK,
                 os.path.join(root, "tmp.py"): _TMPDIR_CHECK,
                 os.path.join(box, "census.toml"): _MUTANT_CENSUS.replace(
                     'passthrough = ["PATH"]',
                     'passthrough = ["PATH", "TMPDIR"]'),
                 os.path.join(box, "manifest.toml"): _MUTANT_MANIFEST,
                 os.path.join(box, "mutants.toml"): _STREAMS_MUTANTS,
                 os.path.join(box, "tmpdir.toml"): _TMPDIR_MUTANTS}
        for path, text in files.items():
            pathlib.Path(path).write_text(text, encoding="utf-8", newline="\n")
        manifest = load_manifest(os.path.join(box, "manifest.toml"))
        mutants = load_mutants(os.path.join(box, "mutants.toml"))
        verdicts = {one.name: run_check(one, mutants, manifest, root, work,
                                        io.StringIO())
                    for one in mutants.checks}
        tmpdir = load_mutants(os.path.join(box, "tmpdir.toml"))
        temp = run_check(tmpdir.checks[0], tmpdir, manifest, root, work,
                         io.StringIO())
        stream = io.StringIO()
        # Whether a directory made read-only keeps a directory in it from
        # being removed here: it does not for root. Asked of a plant of
        # the arm's own, put back before the check that locks `work` runs.
        lockbox = os.path.join(box, "lockbox")
        os.makedirs(os.path.join(lockbox, "inside"))
        lock_binds = _chmod_bites(
            lockbox, lambda path: os.rmdir(os.path.join(path, "inside")))
        try:
            locked = run_check(tmpdir.checks[1], tmpdir, manifest, root, work,
                               stream)
        finally:
            os.chmod(work, 0o755)
        unstarted = os.path.join(box, "unstarted")
        os.makedirs(unstarted)
        try:
            run_check(tmpdir.checks[2], tmpdir, manifest, root, unstarted,
                      io.StringIO())
            would_not = "it ran"
        except Refusal as refused:
            would_not = str(refused)
        stayed = os.listdir(unstarted)
        seen = {name: pathlib.Path(os.path.join(box, f"{name}.txt")).read_text(
            encoding="utf-8").splitlines() for name in ("temp", "locked")}
        own, gettempdir, made = (seen["temp"] + ["", "", ""])[:3]
        left = {name: os.path.lexists(lines[0]) if lines else None
                for name, lines in seen.items()}
    fired = {name: verdict.fired for name, verdict in verdicts.items()}
    named = not_removed((seen["locked"] or [""])[0])
    # The lock did not bind: the directory was removed AND a read-only
    # directory here lets one inside it be removed. The first alone would
    # also be a regression that removes what the lock held, so it is not
    # enough to skip on.
    unbound = not lock_binds and left["locked"] is False

    def shown(text: str) -> str:
        """`text` with the box as `<box>` and each TMPDIR's drawn name as
        its length: the name moves from one run to the next. A TMPDIR
        ending in a separator has no name to replace."""
        for lines in seen.values():
            drawn = os.path.basename(lines[0]) if lines else ""
            if drawn:
                text = text.replace(drawn, f"<{len(drawn)} characters>")
        return _in_box(text, box)
    check(label,
          fired == {"anchored": True, "joined": False, "split": True}
          and os.path.dirname(own) == work and len(own) == len(work) + 9
          and gettempdir == own and os.path.dirname(made) == own
          and left["temp"] is False and not temp.fired and temp.notes == ()
          and (unbound or stream.getvalue() == named) and locked.notes == ()
          and not locked.fired
          and "would not run" in would_not and stayed == [],
          ACTUAL + "; ".join(f"{name} -> "
                             f"{'FIRED' if verdict.fired else 'SILENT'} "
                             f"({verdict.detail})"
                             for name, verdict in verdicts.items())
          + f"; the TMPDIR check saw TMPDIR {shown(own)!r}, "
            f"{len(own) - len(work)} characters longer than the scratch "
            f"directory's, gettempdir {shown(gettempdir)!r}, its file "
            f"{shown(made)!r}, the directory left after it "
            f"{left['temp']}, its notes {temp.notes}; the check that locked "
            f"it -> {'FIRED' if locked.fired else 'SILENT'}, the directory "
            f"left {left['locked']}, its notes "
            f"{tuple(shown(note) for note in locked.notes)}, the run's "
            f"stream {shown(stream.getvalue())!r}; a "
            f"check that would not start -> "
            f"{_one_line(_in_box(would_not, box), 80)!r}, what it left "
            f"{stayed}",
          next="In `mutants._run_command`, search `proc.stdout` and "
               "`proc.stderr` one at a time, for the pattern and for the "
               "`absent` text, never `proc.stdout + proc.stderr`.")
    if unbound:
        skip(label, "a directory made read-only did not keep a directory "
                    "inside it from being removed here, and the TMPDIR of "
                    "the check that locked its scratch directory was "
                    "removed, so the lock could not be planted and the "
                    "naming of an unremovable directory could not be asked. "
                    "Nothing is claimed for it.")


# --------------------------------------- <HERE> follows the copy (nnnn, oooo)
#
# A manifest that sits INSIDE the subject root has its neighbors copied with
# the subject, so a path beside it names a file the copy has its own version
# of. `Manifest.with_root` re-anchors `<HERE>`, which only the argvs that
# EXECUTE spell — `[subject] command`, a `[[setup]]` command and a `counter`
# — and (nnnn) is the positive control for all three: for the first two the
# moved anchor names the copy's file and the unmoved one names the
# original's, in one box, one variable, and a neighbor the copy does not
# carry is refused for each of the three by its own key.
#
# The box is a file copy and needs no `git`: `with_root` is arithmetic on
# paths, and the repository is `mutants`' concern, which is (oooo)'s.

#: Beside the manifest and inside the subject root: the entry point, importing
#: a module beside it so the tree it was taken from is visible in its output.
_HERE_TOOL = '''\
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mark

print(mark.MARK)
'''

#: The `[[setup]]` script, the second thing `with_root` moves. It reads the
#: same module, so one word of output says which tree ran.
_HERE_FIXTURE = _HERE_TOOL

_HERE_MARK = 'MARK = "{}"\n'

#: `root = "."`: the manifest sits AT the subject root, the shortest spelling
#: of "inside it". A `[[setup]]` no surface `needs` is still resolved, and
#: resolving it is the whole of this arm's second half.
_HERE_INSIDE_MANIFEST = _subject("here-stub", '["<PYTHON>", "<HERE>/tool.py"]') + '''
[[setup]]
name    = "fixture"
command = ["<PYTHON>", "<HERE>/make_fixture.py", "<WORK>/fixture"]

[inputs._subject]
args     = []
surfaces = ["rows"]

[surfaces.rows]
args    = []
writes  = "<WORK>/rows.txt"
counter = ["<PYTHON>", "<HERE>/mark.py"]
'''

#: The same manifest from OUTSIDE the subject root — the case that must not
#: move, and the one a consumer whose goldens live in another repository has.
_HERE_OUTSIDE_MANIFEST = _HERE_INSIDE_MANIFEST.replace(
    'root    = "."', 'root    = "original"')


def _here_tree(where: str, mark: str) -> None:
    for leaf, text in (("tool.py", _HERE_TOOL),
                       ("make_fixture.py", _HERE_FIXTURE),
                       ("mark.py", _HERE_MARK.format(mark)),
                       ("census.toml", _MUTANT_CENSUS),
                       ("manifest.toml", _HERE_INSIDE_MANIFEST)):
        pathlib.Path(os.path.join(where, leaf)).write_text(text, encoding="utf-8", newline="\n")


def _ran(argv: list[str]) -> str:
    """The one word an expanded argv prints, or what stopped it."""
    proc = launch(argv, "the arm's entry point")
    return (proc.stdout.strip() or proc.stderr.strip()[:DIFFERENCE]
            or f"exit {proc.returncode}")


def _with_root_control(check: CheckRow) -> None:
    """(nnnn) `with_root` moves what executes and leaves what is read."""
    label = ("nnnn  a manifest INSIDE the subject root, run against a COPY of "
             "it: the `<HERE>` of `[subject] command` and of a `[[setup]]` "
             "command both name the COPY's file and "
             "run the COPY's code, and so does the `<HERE>` of the same "
             "manifest one directory down whose `root` spells the original "
             "in another case, where the file system says the two spellings "
             "are one directory; while the same manifest OUTSIDE the root "
             "keeps its own directory and a neighbor the copy does not carry, "
             "the command's, the setup step's or the counter's, "
             "is a refusal naming both paths")
    with _box("golden-census-here-anchor-") as box:
        original = os.path.join(box, "original")
        os.makedirs(original)
        _here_tree(original, "ORIGINAL")
        copy = os.path.join(box, "copy")
        shutil.copytree(original, copy)
        _here_tree(copy, "COPY")
        thin = os.path.join(box, "thin")
        shutil.copytree(original, thin)
        os.remove(os.path.join(thin, "tool.py"))
        thin_setup = os.path.join(box, "thin-setup")
        shutil.copytree(original, thin_setup)
        os.remove(os.path.join(thin_setup, "make_fixture.py"))
        thin_counter = os.path.join(box, "thin-counter")
        shutil.copytree(original, thin_counter)
        os.remove(os.path.join(thin_counter, "mark.py"))
        pathlib.Path(os.path.join(box, "outside.toml")).write_text(
            _HERE_OUTSIDE_MANIFEST, encoding="utf-8", newline="\n")
        shutil.copy(os.path.join(original, "census.toml"), box)
        shutil.copy(os.path.join(original, "tool.py"), box)
        shutil.copy(os.path.join(original, "mark.py"), box)
        shutil.copy(os.path.join(original, "make_fixture.py"), box)

        inside = load_manifest(os.path.join(original, "manifest.toml"))
        outside = load_manifest(os.path.join(box, "outside.toml"))
        # The same tree one directory down, `nested`, with a manifest whose
        # `root` names the original in the other case: `<HERE>` and the root
        # are two spellings of one tree only where the file system folds
        # case, which it is asked first. There, `core.resolved_below` must
        # hand `with_root` the path from the level the file system named,
        # `nested`, and never the one between the two spellings,
        # `../original/nested`, which leads back to the original tree.
        other_case = os.path.join(box, os.path.basename(original).swapcase())
        try:
            folds = os.path.samefile(other_case, original)
        except OSError:
            folds = False
        case_ran = ""
        if folds:
            for tree, mark in ((original, "ORIGINAL"), (copy, "COPY")):
                os.mkdir(os.path.join(tree, "nested"))
                _here_tree(os.path.join(tree, "nested"), mark)
            spelled_at = os.path.join(original, "nested", "other-case.toml")
            pathlib.Path(spelled_at).write_text(
                _HERE_INSIDE_MANIFEST.replace(
                    'root    = "."',
                    f'root    = "../../{os.path.basename(other_case)}"'),
                encoding="utf-8", newline="\n")
            spelled = load_manifest(spelled_at)
            case_ran = _ran(subject_command(spelled.with_root(copy),
                                            Roots(root=copy, work=box)))
        moved = inside.with_root(copy)
        # The red half, and the only honest way to write it: the same moved
        # manifest with the anchor put back where it was. Expanding through
        # `Manifest.directory` by hand would be a second implementation of the
        # rule, and a control that re-implements what it checks proves nothing.
        unmoved = moved._replace(here=inside.here)
        roots = Roots(root=copy, work=box)
        green_command = subject_command(moved, roots)
        red_command = subject_command(unmoved, roots)
        green_setup = resolve_command(inside.setups[0].command, moved, roots)
        red_setup = resolve_command(inside.setups[0].command, unmoved, roots)
        outside_here = outside.with_root(copy).here
        try:
            inside.with_root(thin)
            refused = ""
        except Refusal as refusal:
            refused = refusal_text(refusal)
        try:
            inside.with_root(thin_setup)
            refused_setup = ""
        except Refusal as refusal:
            refused_setup = refusal_text(refusal)
        try:
            inside.with_root(thin_counter)
            refused_counter = ""
        except Refusal as refusal:
            refused_counter = refusal_text(refusal)
        green_ran, red_ran = _ran(green_command), _ran(red_command)
        green_setup_ran = _ran(green_setup[:2])
        red_setup_ran = _ran(red_setup[:2])

    command_moved = (green_command[1] == os.path.join(copy, "tool.py")
                     and red_command[1] == os.path.join(original, "tool.py"))
    setup_moved = (green_setup[1] == os.path.join(copy, "make_fixture.py")
                   and red_setup[1] == os.path.join(original,
                                                    "make_fixture.py"))
    check(label,
          command_moved and setup_moved
          and (green_ran, red_ran) == ("COPY", "ORIGINAL")
          and (green_setup_ran, red_setup_ran) == ("COPY", "ORIGINAL")
          and case_ran in ("COPY", "") and folds == bool(case_ran)
          and outside_here == outside.here
          and os.path.join(thin, "tool.py") in refused
          and os.path.join(original, "tool.py") in refused
          and "[[setup]] fixture command names" in refused_setup
          and os.path.join(thin_setup, "make_fixture.py") in refused_setup
          and os.path.join(original, "make_fixture.py") in refused_setup
          and "[surfaces.rows] counter names" in refused_counter
          and os.path.join(thin_counter, "mark.py") in refused_counter
          and os.path.join(original, "mark.py") in refused_counter,
          f"{ACTUAL}command moved={command_moved} ran {green_ran!r} against "
          f"{red_ran!r}; setup moved={setup_moved} ran {green_setup_ran!r} "
          f"against {red_setup_ran!r}; the root spelled in another case ran "
          + (f"{case_ran!r}" if folds else "nothing: this file system holds "
             "the two spellings as two directories, so it was not asked")
          + "; the OUTSIDE manifest's anchor "
          f"{'stayed' if outside_here == outside.here else 'MOVED'}; "
          f"the missing neighbor -> {_one_line(refused, 240)!r}; the "
          f"missing setup script -> {_one_line(refused_setup, 120)!r}; the "
          f"missing counter script -> {_one_line(refused_counter, 120)!r}")


#: The module the entry point imports, and the only file (oooo)'s mutant
#: edits: a change one step away from the command line is what a net that
#: executes the wrong tree stops seeing.
_CLONE_ROWS = "ROWS = 3\n"

_CLONE_TOOL = '''\
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rows

print("rows: %d" % rows.ROWS)
'''

#: `root = "."` with the manifest AT the subject root: the shipped example's
#: shape, and the one a `<HERE>` entry point is written for.
_CLONE_MANIFEST = _subject("clone-stub", '["<PYTHON>", "<HERE>/tool.py"]') + '''
[inputs._subject]
args     = []
surfaces = ["rows"]

[surfaces.rows]
args = []
'''

#: `golden = "golden"` — a bare path, resolved against the MUTATED COPY, so
#: the comparator reads the golden the copy carries and the whole verdict is
#: about one tree.
_CLONE_MUTANTS = '''\
[checks.comparator]
builtin = "compare"
golden  = "golden"

[[mutant]]
name    = "the row count the entry point imports"
file    = "rows.py"
find    = "ROWS = 3"
replace = "ROWS = 4"
expect  = ["comparator"]
'''


class _CaptureBroke(Exception):
    """golden-census's own capture of a planted subject refused or exited
    non-zero: raised by `_clone_box` and `_writer_box`, and turned into the
    arm's red row by `checks_base._capture_broke`."""


def _clone_box(box: str) -> tuple[Manifest | None, Manifest | None, str]:
    """The subject, its committed golden and its repository, plus the manifest
    whose `command` is an absolute path into it.

    Returns (the `<HERE>` manifest, the absolute-path manifest, "") or
    (None, None, why this machine cannot run the arm). The golden is captured
    BEFORE the commit, because a bare `golden` is read from the copy and a copy
    carries what was committed. A capture that refuses or exits non-zero is
    no reason of this machine's: it raises `_CaptureBroke`.
    """
    root = os.path.join(box, "subject")
    os.makedirs(root)
    # `.gitignore` because the golden capture runs the entry point and leaves
    # a `__pycache__` beside it: committed, the copy would carry bytecode
    # compiled from the UNMUTATED module, and CPython reuses a `.pyc` whose
    # recorded source mtime and size still match — which a one-byte mutant
    # planted in the same second does not change. Every Python project ignores
    # the directory for the same reason this box has to.
    files = {os.path.join(root, ".gitignore"): "__pycache__/\n",
             os.path.join(root, "rows.py"): _CLONE_ROWS,
             os.path.join(root, "tool.py"): _CLONE_TOOL,
             os.path.join(root, "census.toml"): _MUTANT_CENSUS,
             os.path.join(root, "manifest.toml"): _CLONE_MANIFEST,
             os.path.join(box, "m.toml"): _CLONE_MUTANTS}
    for path, text in files.items():
        pathlib.Path(path).write_text(text, encoding="utf-8", newline="\n")
    try:
        here = load_manifest(os.path.join(root, "manifest.toml"))
        code = capture(here, os.path.join(root, "golden"), io.StringIO())
    except Refusal as refused:
        raise _CaptureBroke(f"the golden would not capture: {refused}"
                            ) from refused
    if code != 0:
        raise _CaptureBroke(f"the golden capture exited {code}")
    absolute = os.path.join(root, "absolute.toml")
    pathlib.Path(absolute).write_text(
        _CLONE_MANIFEST.replace(
            '"<HERE>/tool.py"', '"' + os.path.join(root, "tool.py") + '"'),
        encoding="utf-8", newline="\n")
    try:
        exit_code, head, stderr = _repo_of(root, "the stub")
        if exit_code != 0:
            return None, None, f"`{head}` exited {exit_code}: {stderr[:DIFFERENCE]}"
        return here, load_manifest(absolute), ""
    except Refusal as refused:
        return None, None, str(refused)


def _clone_executes_control(check: CheckRow, skip: SkipRow) -> None:
    """(oooo) `mutants` runs the CLONE's code, and says so when it cannot."""
    label = ("oooo  a manifest inside the subject root whose `command` is "
             "`<HERE>/…`: `mutants` executes the CLONE's entry point, so a "
             "mutant in a module that entry point imports is CAUGHT, and so "
             "it is under a temp root inside the subject root, which puts the "
             "clone there too — and the "
             "same subject whose `command` is an absolute path into the "
             "checkout is REFUSED before the null mutant, naming the element "
             "and both roots, rather than printing a table of SILENTs")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, and this arm needs `git clone "
                    "--local` to make the copy whose code the run has to "
                    "execute. Nothing was made and nothing is claimed.")
        return
    with _box("golden-census-clone-executes-") as box:
        try:
            here, absolute, why = _clone_box(box)
        except _CaptureBroke as broke:
            _capture_broke(check, label, _one_line(str(broke), 400))
            return
        if here is None or absolute is None:
            skip(label, f"the throwaway subject could not be prepared: {why}. "
                        "Nothing is claimed.")
            return
        green_code, green_text = _mutants_run(here, box, "m.toml")
        # A temp root inside the subject root: the clone is made under it,
        # so its `<HERE>` entry point is a file of the subject root AND of
        # the clone, and `mutants.runs_in_the_clone` must take it as the
        # clone's. The directory is made after the commit, so the clone
        # does not carry it.
        inside = os.path.join(here.subject.root, "tmp")
        os.mkdir(inside)
        with _tmpdir_as(inside):
            inside_code, inside_text = _mutants_run(here, box, "m.toml")
        red_code, red_text = _mutants_run(absolute, box, "m.toml")

    check(label,
          green_code == 0
          and re.search(r"the row count the entry point imports\s+FIRED",
                        green_text) is not None
          and "1/1 mutants caught" in green_text
          and inside_code == 0 and "1/1 mutants caught" in inside_text
          and red_code == 2
          and "this runs in your tree, not the clone" in red_text
          and "null mutant" not in red_text,
          f"{ACTUAL}<HERE> -> exit {green_code}, "
          f"{_one_line(green_text, 150, needles=('FIRED', 'SILENT', 'caught'))!r}"
          f"; under a temp root inside the subject root -> exit "
          f"{inside_code}, "
          f"{_one_line(inside_text.replace(box, '<box>'), 150, needles=('REFUSED', 'caught'))!r}"
          f"; the absolute path -> exit {red_code}, "
          f"{_one_line(red_text, 400)!r}")


#: The one mutant arm `vvvvv` plants, spelled four ways. `find` really does
#: occur once in every file it is pointed at, including the one beside the
#: subject root: a refusal that fired because `find` was not unique would be a
#: refusal about something else.
_ESCAPING_MUTANT = _CHECK_VERSION + '''
[[mutant]]
name    = "{name}"
file    = "{file}"
find    = 'VERSION = "1.0"'
replace = 'VERSION = "9.9"'
expect  = ["version"]
'''


def _escaping_mutant_control(check: CheckRow, skip: SkipRow) -> None:
    """(vvvvv) a mutant's `file` is committed, and it stays under the subject
    root.

    Two holes in one key. `preflight` asks `os.path.isfile` against the
    SUBJECT ROOT and `plant` then opens the same relative path inside the
    CLONE, which `git clone --local` built from HEAD — so a file in the
    working tree and not in the last commit passed preflight and was a
    `FileNotFoundError` traceback at the plant. And `os.path.join` discards
    the root when the second element is absolute, so a `file` that is
    absolute or climbs with `..` resolved to a stranger's file, which
    `plant` then opened for WRITING: this arm's own planted file, beside the
    subject root, was rewritten by the base.

    A committed LINK is the third spelling and neither guard above sees it —
    `link.py` is one path component and `os.path.isfile` follows it — so the
    destination is asked of the filesystem as well as of the string, and the
    write happened again until it was.

    The last case is the control and it is not optional: a committed file
    inside the root still reaches the table, or the guards have not made the
    command stricter, they have made it useless.
    """
    label = ("vvvvv  a mutant naming a file the CLONE lacks is REFUSED "
             "naming the mutant and the file, because `mutants` plants in a "
             "clone of the last commit; a mutant whose `file` is absolute, "
             "climbs out of the subject root with `..`, or is a committed "
             "LINK that resolves out of it is REFUSED at preflight, before "
             "any clone — where the base rewrote the file it resolved to — "
             "while a mutant naming a committed file inside the root still "
             "reaches its table")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, and every case needs `git clone "
                    "--local` to make the repo-shaped copy the command plants "
                    "in. Nothing was made and nothing is claimed.")
        return
    verdicts: dict[str, str] = {}
    with _box("golden-census-escaping-mutant-") as box:
        path, why = _mutant_box(box)
        if path is None:
            skip(label, f"the throwaway subject could not be put in a git "
                        f"repository: {why}. Nothing is claimed.")
            return
        root = os.path.join(box, "subject")
        # The escape's target, beside the subject root and inside the box.
        escaped = os.path.join(box, "planted.py")
        pathlib.Path(escaped).write_text('VERSION = "1.0"\n', encoding="utf-8")
        # A COMMITTED link out of the root, made and committed BEFORE the
        # uncommitted file below: `link.py` is one path component, so the
        # spelling rule passes it, `os.path.isfile` follows it and answers
        # yes, and the base rewrote the file it points at.
        os.symlink(escaped, os.path.join(root, "link.py"))
        try:
            committed, head, stderr = _repo_of(root, "the link")
        except Refusal as refused:
            # A `git` that will not START, which `shutil.which` cannot see.
            skip(label, f"the link could not be committed to the throwaway "
                        f"subject: {refused}. Nothing is claimed.")
            return
        if committed != 0:
            skip(label, f"the link could not be committed to the throwaway "
                        f"subject: `{head}` exited {committed}: "
                        f"{stderr[:DIFFERENCE]}. Nothing is claimed.")
            return
        # Written AFTER every commit, so the working tree has it and the
        # clone does not.
        pathlib.Path(os.path.join(root, "uncommitted.py")).write_text(
            'VERSION = "1.0"\n', encoding="utf-8")
        before = pathlib.Path(escaped).read_text(encoding="utf-8")
        cases = (("the clone lacks it", "uncommitted.py"),
                 ("it climbs out", os.path.join("..", "planted.py")),
                 ("it is absolute", escaped),
                 ("it is a link out", "link.py"),
                 ("a committed file", "tool.py"))
        for key, spelled in cases:
            pathlib.Path(os.path.join(box, "escaping.toml")).write_text(
                _ESCAPING_MUTANT.replace("{name}", key).replace("{file}", spelled),
                encoding="utf-8")
            code, said = _mutants_run(load_manifest(path), box,
                                      "escaping.toml")
            # The REAL path too: a refusal that says where a link resolves
            # names the box through whatever `/tmp` is on this machine.
            verdicts[key] = (f"exit {code}: "
                             + said.replace(os.path.realpath(box), "<box>")
                             .replace(box, "<box>"))
        after = pathlib.Path(escaped).read_text(encoding="utf-8")

    lacks = verdicts["the clone lacks it"]
    climbs = verdicts["it climbs out"]
    absolute = verdicts["it is absolute"]
    link = verdicts["it is a link out"]
    rule = "a mutant's `file` must be a relative path under the subject root"
    check(label,
          lacks.startswith("exit 2: REFUSED: ")
          and "uncommitted.py is in the subject's working tree but not in "
              "the clone" in lacks
          and "Commit that file to the subject's repository" in lacks
          and all(one.startswith("exit 2: REFUSED: ") and rule in one
                  and "planted.py" in one
                  for one in (climbs, absolute))
          # The link is refused for what it RESOLVES to, before any clone —
          # never as a file the clone lacks, whose advice cannot help here.
          and link.startswith("exit 2: REFUSED: ")
          and "'link.py' resolves to " in link
          and ", outside the subject root." in link
          and "<box>/planted.py" in link
          and "not in the clone" not in link
          # The write the base made: the file beside the subject root is the
          # one `plant` opened, and it must come back untouched.
          and after == before
          and verdicts["a committed file"].startswith("exit 0")
          and "caught" in verdicts["a committed file"],
          ACTUAL + "; ".join(
              f"{key} -> {_one_line(text, 150)}"
              for key, text in verdicts.items())
          + f"; the file beside the subject root: "
          f"{'UNCHANGED' if after == before else 'REWRITTEN ' + after.strip()}",
          next="`mutants.preflight` calls `manifest._stays_under` at the top "
               "of its loop, before anything asks the filesystem about the "
               "path, then `mutants._refuse_outside` on where that path "
               "really goes; `mutants.plant` asks the same of the clone and "
               "refuses a file the clone lacks before it opens one. If a "
               "case above reaches the table, one of those has gone — and "
               "two of them guard a WRITE.")


# ------------------------------------ the comparator's own verdicts (llllll)
#
# A subject that WRITES a file, in a repository of its own: the comparator's
# capture of a clone reads that file back as text, so a mutant that turns it
# into UTF-16 makes the capture refuse — which is no comparison, and must
# read as REFUSED, the mutant not counted caught, rather than end the run.

_WRITER_TOOL = '''\
import sys

ENCODING = "utf-8"

with open(sys.argv[1], "w", encoding=ENCODING, newline="\\n") as handle:
    handle.write("rows: 3\\n")
'''

#: `_CLONE_MANIFEST` with the one surface writing its file.
_WRITER_MANIFEST = _CLONE_MANIFEST.replace(
    '[surfaces.rows]\nargs = []\n',
    '[surfaces.rows]\nargs   = ["<WRITES>"]\n'
    'writes = "<WORK>/<input>-<surface>.txt"\n')

#: The same surface writing a file whose name is long enough that the
#: refusal's first line runs past `DIFFERENCE` before it says "not text":
#: a refusal cut to fit the table's detail would lose its reason.
_WRITER_MANIFEST_LONG = _WRITER_MANIFEST.replace(
    "<surface>.txt", "<surface>-" + "a-long-file-name-" * 7 + "end.txt")

#: The surface's argv names the work directory, so the census folds it.
_WRITER_CENSUS = _MUTANT_CENSUS + _STUB_WORK_FOLD

#: One comparator and one mutant, the mutant's edit filled in per case.
_WRITER_MUTANTS = '''\
[checks.comparator]
builtin = "compare"
golden  = "golden"

[[mutant]]
name    = "{name}"
file    = "tool.py"
find    = '{find}'
replace = '{replace}'
expect  = ["comparator"]
'''

_UTF8 = 'ENCODING = "utf-8"'
_UTF16 = 'ENCODING = "utf-16"'

#: The writer tool printing a home path as well: the capture records it,
#: and its contraband scan prints its refusal and exits 2 rather than
#: raising one.
_LEAKS = _UTF8 + '\nprint("/Users/someone/secret")'

#: What that capture's refusal says.
_HOME_REFUSAL = "the capture would commit an absolute path."


#: A line the golden's stdout carries and the subject never prints, and the
#: `[[movements]]` row that permits it (arm `mmmmmm`).
_PLANTED_LINE = "a line the subject never prints\n"
_WRITER_MOVEMENT = '''
[[movements]]
path        = "_subject/rows.out"
attribution = "a line planted in the golden, permitted here"
'''


#: The writer subject's second input, pinning a repository arm `mmmmmm`
#: makes: every capture enters its kept clone.
_PINNED_INPUT = '''
[inputs.pinned]
args     = []
surfaces = ["rows"]
git      = "{url}"
sha      = "{sha}"
'''


#: A check that fires on the copy the UTF-16 mutant was planted in and on
#: no other: it reads the tool's committed text.
_SEES_UTF16 = '''
[checks.sees]
command = ["<PYTHON>", "-c", "import sys; print(open(sys.argv[1]).read())", "<ROOT>/tool.py"]
fires   = { pattern = "utf-16" }
'''


#: A check that fires on any copy at all, the unmutated one included.
_ALWAYS_FIRES = '''
[checks.always]
command = ["<PYTHON>", "-c", "raise SystemExit(3)"]
fires   = "exit-nonzero"
'''


def _writer_box(root: str, committed: str, moved: bool = False,
                manifest_text: str = _WRITER_MANIFEST
                ) -> tuple[Manifest | None, str]:
    """The writing subject at `root`, its golden captured from the UTF-8
    tool, then the tool as `committed` spells it committed to its own
    repository. `moved` plants `_PLANTED_LINE` in the golden's stdout and
    gives the manifest the `[[movements]]` row that permits it;
    `manifest_text` is the manifest before that row. Returns (the manifest,
    "") or (None, why this machine cannot run the arm); a capture that
    refuses or exits non-zero raises `_CaptureBroke`."""
    os.makedirs(root)
    # `.gitignore` for `_clone_box`'s reason: the golden capture compiles
    # the entry point beside itself.
    files = {".gitignore": "__pycache__/\n", "tool.py": _WRITER_TOOL,
             "census.toml": _WRITER_CENSUS,
             "manifest.toml": manifest_text + (_WRITER_MOVEMENT if moved
                                               else "")}
    for name, text in files.items():
        pathlib.Path(os.path.join(root, name)).write_text(
            text, encoding="utf-8", newline="\n")
    try:
        manifest = load_manifest(os.path.join(root, "manifest.toml"))
        code = capture(manifest, os.path.join(root, "golden"), io.StringIO())
    except Refusal as refused:
        raise _CaptureBroke(f"the golden would not capture: {refused}"
                            ) from refused
    if code != 0:
        raise _CaptureBroke(f"the golden capture exited {code}")
    if moved:
        pathlib.Path(os.path.join(root, "golden", "_subject", "rows.out")
                     ).write_text(_PLANTED_LINE, encoding="utf-8")
    pathlib.Path(os.path.join(root, "tool.py")).write_text(
        _WRITER_TOOL.replace(_UTF8, committed), encoding="utf-8", newline="\n")
    try:
        exit_code, head, stderr = _repo_of(root, "the writer")
    except Refusal as refused:
        return None, str(refused)
    if exit_code != 0:
        return None, f"`{head}` exited {exit_code}: {stderr[:DIFFERENCE]}"
    return manifest, ""


def _writer_mutants(box: str, file_name: str, name: str, find: str,
                    replace: str) -> str:
    """Write a mutants file of the one comparator into `box`; its name."""
    pathlib.Path(os.path.join(box, file_name)).write_text(
        _WRITER_MUTANTS.replace("{name}", name).replace("{find}", find)
        .replace("{replace}", replace), encoding="utf-8", newline="\n")
    return file_name


def _verdict_on(manifest: Manifest, box: str, file_name: str,
                planted: bool) -> Verdict:
    """The comparator's verdict on one clone, asked of `mutants.run_check`
    directly: the table prints FIRED, SILENT and REFUSED and no detail, and the
    detail is what the arm is about."""
    mutants = load_mutants(os.path.join(box, file_name))
    scratch = os.path.join(box, "direct")
    os.makedirs(scratch, exist_ok=True)
    clone = clone_subject(manifest.subject.root, scratch, file_name)
    try:
        if planted:
            plant(clone, mutants.mutants[0])
        return run_check(mutants.checks[0], mutants, manifest, clone, scratch,
                         io.StringIO())
    finally:
        shutil.rmtree(clone, ignore_errors=True)


def _null_and_own(manifest: Manifest, box: str, name: str, into: str
                  ) -> tuple[Refusal | None, Refusal | None]:
    """The refusal a `mutants` run ends with on the null mutant, and the one
    a capture of the same unmutated subject raises by itself, into `into`
    under `box`: the first has to carry the second whole — its sentence, its
    `next` and its `about`."""
    run: Refusal | None = None
    own: Refusal | None = None
    try:
        run_mutants(manifest, load_mutants(os.path.join(box, name)),
                    io.StringIO())
    except Refusal as refused:
        run = refused
    try:
        capture(manifest, os.path.join(box, into), io.StringIO())
    except Refusal as refused:
        own = refused
    return run, own


#: The one part of an `about` block two captures of one subject spell
#: differently: the temporary directory each made under `<WORK>`.
_WORK_DIRECTORY = re.compile(r"<WORK>/[^/\s]+/")


def _same_about(run: Refusal, own: Refusal) -> bool:
    """`run`'s `about` block is `own`'s, the work directory's name aside."""
    return (own.about != ""
            and _WORK_DIRECTORY.sub("<WORK>/", run.about)
            == _WORK_DIRECTORY.sub("<WORK>/", own.about))


def _carries_whole(run: Refusal | None, own: Refusal | None) -> bool:
    """`run` names the null mutant and the check, and ends in `own`'s
    sentence uncut, with `own`'s `next` and `about` as its own."""
    return (run is not None and own is not None
            and "null mutant" in str(run) and "comparator" in str(run)
            and str(run).endswith(f"The capture refused: {own}")
            and run.next == own.next != ""
            and _same_about(run, own))


def _null_detail(run: Refusal | None, own: Refusal | None) -> str:
    """One null-mutant case for the arm's `actual:` line: the run's refusal,
    whether it ends in the capture's own sentence, and whether its `next`
    and `about` are the capture's."""
    if run is None or own is None:
        return (f"the run refused={run is not None}, the capture by itself "
                f"refused={own is not None}")
    text = refusal_text(run)
    return (f"{_one_line(text, 240)!r}, the capture's sentence whole="
            f"{str(run).endswith(f'The capture refused: {own}')}, its next "
            f"the capture's={run.next == own.next}, its about the "
            f"capture's={_same_about(run, own)} ({len(run.about)} characters)")


def _refused_capture_control(check: CheckRow, skip: SkipRow) -> None:
    """(llllll) a mutant whose capture REFUSES is REFUSED, never FIRED.

    The comparator captures the mutated copy, and a capture that refuses —
    here, a written file the mutant turned into UTF-16, which golden-census
    will not record as text — made no comparison: the cell reads REFUSED,
    the refusal's first line follows under the row, whole and folded, and
    under it the first line of its block, naming the command that ran, the
    mutant is not counted caught, also where a second check fired on it,
    and the run exits 1. Read as FIRED, a capture that refused for a reason
    of the machine's would read as a catch. The fold is asked of `_report`
    directly, over a refusal naming the temp root, because no refusal this
    subject raises names a directory of the run; so are the FAIL line of a
    mutant both REFUSED and missed, whose REFUSED reason comes first, and
    the `next:` line of a table with a missed check and no REFUSED, which
    says nothing of a refusal. The same refusal on the UNMUTATED copy
    refuses the run naming the null mutant and the check, in the capture's
    own words: its sentence whole, its `next` and its `about`,
    compared with what a capture of that subject raises by itself, and
    naming a second check that fired there for a reason of its own, whether
    that check is listed after the comparator or before it. On two subjects:
    a cut to the table detail's width would take the sentence's tail on the
    first and the reason itself — "not text" — on the second. And once
    through the command line, which prints that refusal at exit 2 as
    `REFUSED:` with the capture's sentence and its `next:` line. A capture
    that prints its refusal and exits 2 instead of raising it — a mutant
    that makes the subject print a home path, which the contraband scan
    refuses — is REFUSED the same way, its first line under the row and no
    line of a block, for it carries none; the same on the unmutated copy
    refuses the run in the sentence and the `next:` line the capture
    printed, with the lines it quoted above them — the hits that `next:`
    line points to — between the two, four spaces in, and nothing more: no
    `about`.
    """
    label = ("llllll  a mutant whose capture REFUSES — its written file turned "
             "to UTF-16 — is REFUSED, never FIRED: the comparator's cell reads "
             "REFUSED with no note, the refusal's first line follows under the "
             "row whole, a line past the detail's width included, and folded, "
             "and under it its block's first line naming the command that "
             "ran, the verdict's detail quotes it cut to the detail's width, the "
             "tally counts the mutant not caught, a second check that fired "
             "on it included, a FAIL line names the check REFUSED, before "
             "any check it missed, the next: line says how to tell the "
             "mutant's refusal from the machine's, and a table with no "
             "REFUSED says nothing of one, and the table exits 1; "
             "the same refusal on "
             "the unmutated copy refuses the run naming the null mutant, "
             "carrying the capture's refusal whole with its own next: and its "
             "about block, a reason past the detail's width included, and a "
             "check that fires listed before the comparator included; the "
             "command line prints it at exit 2 as REFUSED: with the capture's "
             "sentence and its next: line; a capture that prints its refusal "
             "and exits 2 — a home path the mutant makes the subject print — "
             "is REFUSED the same way, its first line under the row and no "
             "block line, the "
             "mutant not caught, at exit 1, and on the unmutated copy refuses "
             "the run with the sentence and the next: line that capture "
             "printed, and the lines it quoted above them and nothing more")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, and this arm needs `git clone "
                    "--local` to make the copy the comparator captures. Nothing "
                    "was made and nothing is claimed.")
        return
    with _box("golden-census-refused-capture-") as box:
        try:
            caught, why = _writer_box(os.path.join(box, "caught"), _UTF8)
            null, why_null = _writer_box(os.path.join(box, "null"), _UTF16)
            long, why_long = _writer_box(os.path.join(box, "long"), _UTF16,
                                         manifest_text=_WRITER_MANIFEST_LONG)
            long_caught, why_long_caught = _writer_box(
                os.path.join(box, "long-caught"), _UTF8,
                manifest_text=_WRITER_MANIFEST_LONG)
            leaky, why_leaky = _writer_box(os.path.join(box, "leaky"), _LEAKS)
        except _CaptureBroke as broke:
            _capture_broke(check, label, _one_line(str(broke), 400))
            return
        if (caught is None or null is None or long is None
                or long_caught is None or leaky is None):
            skip(label, f"the throwaway subject could not be prepared: "
                        f"{why or why_null or why_long or why_long_caught}"
                        f"{why_leaky}. Nothing is claimed.")
            return
        utf16 = _writer_mutants(box, "utf16.toml", "the file turned to UTF-16",
                                _UTF8, _UTF16)
        rows = _writer_mutants(box, "rows.toml", "the row count", "rows: 3",
                               "rows: 4")
        table_code, table = _mutants_run(caught, box, utf16)
        leak = _writer_mutants(box, "leak.toml", "the home path", "rows: 3",
                               "/Users/someone/secret")
        leak_code, leak_table = _mutants_run(caught, box, leak)
        long_code, long_table = _mutants_run(long_caught, box, utf16)
        # A second check that fires on the planted copy: the mutant is still
        # not counted caught.
        pathlib.Path(os.path.join(box, "sees.toml")).write_text(
            pathlib.Path(os.path.join(box, utf16)).read_text(encoding="utf-8")
            + _SEES_UTF16, encoding="utf-8")
        sees_code, sees_table = _mutants_run(caught, box, "sees.toml")
        # The fold, asked of the table directly: a refusal whose first line
        # names the temp root.
        planted = load_mutants(os.path.join(box, utf16))
        folded = _asked_report(caught, planted, [Row(planted.mutants[0], (
            Verdict("comparator", False, "", Refused(
                f"under {os.path.join(temp_base(), 'x')}\nthe second line",
                "", "")),))])
        # The order of a FAIL line's reasons, and the `next:` line of a table
        # with no REFUSED, asked of the table directly too.
        both = load_mutants(os.path.join(box, "sees.toml"))
        stayed = Verdict("sees", False, "exited 0")
        ordered = _asked_report(caught, both, [Row(
            both.mutants[0]._replace(expect=("comparator", "sees")),
            (Verdict("comparator", False, "", Refused("a line", "", "")),
             stayed))])
        unrefused = _asked_report(caught, both, [Row(both.mutants[0], (
            Verdict("comparator", False, "IDENTICAL"), stayed))])
        try:
            direct = _verdict_on(caught, box, utf16, planted=True)
        except Refusal as refused:
            # What the base did: the refusal ended the check. Recorded as
            # this arm's red, not left to become a `[FAIL]  !` row.
            direct = Verdict("comparator", False, f"REFUSED: {refused}")
        # The same mutant on a subject whose refusal's first line runs past
        # the detail's width: the detail quotes the line cut, not whole.
        try:
            direct_long = _verdict_on(long_caught, box, utf16, planted=True)
        except Refusal as refused:
            direct_long = Verdict("comparator", False, f"REFUSED: {refused}")
        # A second check that fires on the null mutant for a reason of its
        # own: the capture's refusal is the run's, and this one is named in it.
        pathlib.Path(os.path.join(box, "also.toml")).write_text(
            pathlib.Path(os.path.join(box, rows)).read_text(encoding="utf-8")
            + _ALWAYS_FIRES, encoding="utf-8")
        null_run, null_own = _null_and_own(null, box, "also.toml", "own-null")
        # The same check listed BEFORE the comparator: the capture's refusal
        # is the run's whichever check fired first.
        pathlib.Path(os.path.join(box, "first.toml")).write_text(
            _ALWAYS_FIRES.lstrip("\n") + "\n"
            + pathlib.Path(os.path.join(box, rows)).read_text(encoding="utf-8"),
            encoding="utf-8")
        first_run, first_own = _null_and_own(null, box, "first.toml",
                                             "own-first")
        long_run, long_own = _null_and_own(long, box, rows, "own-long")
        # The unmutated copy that prints a home path: its capture prints its
        # refusal and exits 2, and the run refuses in those words.
        leaky_run, _ = _null_and_own(leaky, box, rows, "own-leaky")
        leaky_printed = io.StringIO()
        leaky_code = capture(leaky, os.path.join(box, "own-leaky-printed"),
                             leaky_printed)
        # What the command line prints of the null mutant's refusal.
        printed_code, printed = _quietly(main, [
            "mutants", "--manifest", null.path,
            "--mutants", os.path.join(box, rows)])
        # The control: a refusal about the RUN — a golden directory that is
        # not there — stays a refusal of the run, never a FIRED.
        pathlib.Path(os.path.join(box, "absent.toml")).write_text(
            (pathlib.Path(os.path.join(box, rows)).read_text(encoding="utf-8")
             .replace('golden  = "golden"', 'golden  = "absent"')),
            encoding="utf-8")
        absent_code, absent_text = _mutants_run(caught, box, "absent.toml")

    long_first = (str(long_own).splitlines() or [""])[0]
    # The line the detail cut, and the words it adds around the cut.
    cut_first = ((direct_long.refused.sentence.strip().splitlines() or [""])[0]
                 if direct_long.refused is not None else "")
    # The capture's sentence whole, then its `next:` line, under the word.
    printed_whole = (null_own is not None and null_own.next != ""
                     and f"\n  next: {null_own.next}\n" in printed
                     and f"The capture refused: {null_own}\n  next: "
                     in printed)
    under_long = f"\n    comparator: the capture refused: {cut_first}\n"
    # The block's first line under the refusal's: the command the row ran,
    # which a refusal raised inside the row's window names there alone.
    under_ran = re.search(r"\n    comparator: the capture refused: _subject/"
                          r"rows writes [^\n]*\n      ran: <PYTHON> \S+/tool\.py ",
                          table) is not None
    leak_ran = "\n      ran: " in leak_table
    fail_line = ("\n  FAIL  the file turned to UTF-16 — comparator REFUSED (its "
                 "capture of the mutated copy refused, so it gave no verdict)\n")
    fold_needles = ("comparator:", "_report raised")
    read_whole = ("A REFUSED is neither caught nor missed: run `compare` on a "
                  "copy of the subject with that mutant applied — a refusal "
                  "the mutant causes comes back there whole, and one that "
                  "does not came from the machine during this run — and act "
                  "on it before counting the mutant.")
    both_reasons = ("\n  FAIL  the file turned to UTF-16 — comparator REFUSED "
                    "(its capture of the mutated copy refused, so it gave no "
                    "verdict); sees expected to fire and stayed SILENT "
                    "(exited 0)\n")
    # The lines the capture quoted directly above its own REFUSED: line —
    # the hits its next: line points to — which the run's refusal carries
    # between its sentence and its next: line, and nothing more.
    above = leaky_printed.getvalue().split(
        f"\n  REFUSED: {_HOME_REFUSAL}\n")[0].splitlines()
    quoted: list[str] = []
    while above and above[-1].startswith("    "):
        quoted.insert(0, above.pop())
    leaky_whole = (leaky_run is not None and leaky_code == 2 and quoted != []
                   and str(leaky_run).endswith("\n".join(
                       [f"The capture refused: {_HOME_REFUSAL}", *quoted]))
                   and leaky_run.about == ""
                   and leaky_run.next != ""
                   and f"\n  REFUSED: {_HOME_REFUSAL}\n    next: "
                       f"{leaky_run.next}\n" in leaky_printed.getvalue())
    check(label,
          table_code == 1
          and re.search(r"\n  the file turned to UTF-16  REFUSED\n", table)
          is not None
          and leak_code == 1
          and re.search(r"\n  the home path\s+REFUSED\n", leak_table)
          is not None
          and f"\n    comparator: the capture refused: {_HOME_REFUSAL}\n"
              in leak_table
          and "0/1 mutants caught" in leak_table
          and leaky_whole
          and under_ran and not leak_ran
          and "\n    comparator: the capture refused: _subject/rows writes "
              "<WORK>/<input>-<surface>.txt — not text: " in table
          and "0/1 mutants caught" in table
          and fail_line in table
          and read_whole in table
          and long_code == 1 and under_long in long_table
          and sees_code == 1 and "0/1 mutants caught" in sees_table
          and re.search(r"UTF-16  REFUSED\s+FIRED\s+\(sees: unexpected\)\n",
                        sees_table) is not None
          and folded.count(
              "\n    comparator: the capture refused: under <WORK>/x\n") == 1
          and both_reasons in ordered
          and "\n  FAIL  " in unrefused and "\n  next: " in unrefused
          and "A REFUSED" not in unrefused
          and not direct.fired and direct.refused is not None
          and direct.detail.startswith("the capture refused: ")
          and "not text" in direct.detail
          and not direct_long.fired
          and direct_long.detail.startswith("the capture refused: ")
          and len(cut_first) > DIFFERENCE
          and direct_long.detail
          == "the capture refused: " + cut_first[:DIFFERENCE]
          and _carries_whole(null_run, null_own)
          and "also reported by always (exited 3)" in str(null_run)
          and _carries_whole(first_run, first_own)
          and "also reported by always (exited 3)" in str(first_run)
          and printed_code == 2
          and "\nREFUSED: the null mutant — the unmutated copy — was "
              "reported by comparator " in printed
          and printed_whole
          and len(long_first) > DIFFERENCE
          and "not text" not in long_first[:DIFFERENCE]
          and _carries_whole(long_run, long_own)
          and absent_code == 2 and "no golden directory" in absent_text
          and "null mutant" not in absent_text,
          f"{ACTUAL}the mutant -> exit {table_code}, "
          f"{_one_line(table, 300, needles=('FIRED', 'SILENT', 'REFUSED', 'caught', 'FAIL'))!r}; "
          f"the next: line's REFUSED sentence={read_whole in table}; the "
          f"block's ran: line under the refusal's={under_ran}; on the long "
          f"subject -> exit {long_code}, its first line whole under the "
          f"row={under_long in long_table}; with a second check that fired "
          f"-> exit {sees_code}, "
          f"{_one_line(sees_table, 120, needles=('UTF-16', 'caught'))!r}; "
          f"the fold -> {_one_line(folded, 120, needles=fold_needles)!r}; "
          f"a FAIL both REFUSED and missed, its reasons in order="
          f"{both_reasons in ordered}; a table with no REFUSED -> "
          f"{_one_line(unrefused, 120, needles=('FAIL', '_report raised'))!r}, "
          f"its REFUSED sentence={'A REFUSED' in unrefused}; "
          f"its verdict fired={direct.fired} refused={direct.refused is not None} "
          f"{direct.detail!r}; on a first line "
          f"of {len(cut_first)} characters its detail is "
          f"{len(direct_long.detail)} characters, the line cut to "
          f"{DIFFERENCE}="
          f"{direct_long.detail == 'the capture refused: ' + cut_first[:DIFFERENCE]}; the null "
          f"mutant -> {_null_detail(null_run, null_own)}; the null mutant, "
          f"the check that fires listed first -> "
          f"{_null_detail(first_run, first_own)}; the null mutant, "
          f"a first line of {len(long_first)} characters -> "
          f"{_null_detail(long_run, long_own)}; the command line on the null "
          f"mutant -> exit {printed_code}, the capture's sentence then its "
          f"next: line={printed_whole}, "
          f"{_one_line(printed, 160, needles=('REFUSED', 'next:'))!r}; "
          f"no golden directory -> exit {absent_code}, "
          f"{_one_line(absent_text, DIFFERENCE)!r}; a mutant that prints a "
          f"home path -> exit {leak_code}, "
          f"{_one_line(leak_table, 200, needles=('REFUSED', 'FIRED', 'caught'))!r}, "
          f"a ran: line under it={leak_ran}; "
          f"the unmutated copy printing it -> "
          f"{_one_line(refusal_text(leaky_run), 240) if leaky_run else None!r}, "
          f"the sentence, the lines it quoted above them {quoted!r} and the "
          f"next: line its capture printed, and no about block, at exit "
          f"{leaky_code}={leaky_whole}")


def _asked_report(manifest: Manifest, mutants: Mutants, rows: list[Row]
                  ) -> str:
    """What `mutants._report` prints over `rows`, asked directly."""
    printed = io.StringIO()
    try:
        _report(manifest, mutants, rows, printed)
    except TypeError as wrong:
        # What the base did: `_report` took no manifest to fold with.
        # Recorded as the arm's red, not left to become a `[FAIL]  !` row.
        printed.write(f"_report raised: {wrong}")
    return printed.getvalue()


def _in_box(text: str, box: str) -> str:
    """`text` with the arm's box written `<box>`, for a detail line."""
    return text.replace(box, "<box>")


#: The row arm `mmmmmm` adds once to the `--allow-diff` table and once to the
#: manifest's `[[movements]]`, which no moved row of its golden matches, and
#: the line `compare` names it on for each table.
_STALE_ROW = "_subject/never-moved.out"
_STALE_FILE_LINE = (f"  unused: --allow-diff row {_STALE_ROW!r} permits a "
                    "movement that did not happen")
_STALE_MANIFEST_LINE = (f"  unused: [[movements]] row {_STALE_ROW!r} permits "
                        "a movement that did not happen")


#: What arm `mmmmmm` quotes of a `mutants` table: its verdict lines, or what
#: ended the run instead.
_TABLE_NEEDLES = ("null", "FIRED", "SILENT", "caught", "REFUSED", "raised")


def _permitted_movement_control(check: CheckRow, skip: SkipRow) -> None:
    """(mmmmmm) `mutants`' comparator reads `[[movements]]` as `compare` does.

    One manifest, one golden with a line planted in a row the manifest's
    `[[movements]]` permits. `compare` calls that golden IDENTICAL with one
    permitted movement; a comparator that counted every differing row
    instead fired on the NULL mutant and refused the whole run — two
    commands of one tool disagreeing about one golden. Both details carry
    the count of permitted rows: a SILENT that owes itself to a permitted
    row is what the reader of a `FAIL` line needs to be told.

    Two more rows that both name the row the real mutant moves make that
    mutant's comparison refuse, as `compare` refuses it: its cell reads
    REFUSED, the line under its row and its FAIL line say the comparison
    refused, the table still prints and the run exits 1. A row that names
    the planted row beside the manifest's own makes the comparison of the
    unmutated copy refuse, and the run is refused saying so.

    The same golden, compared with one more row in the `--allow-diff` table
    that no moved row matches, is still IDENTICAL with one permitted
    movement, and says so on a line in front of the verdict: that row
    permitted nothing, named as the `--allow-diff` row it is. The same
    stale row in the manifest's `[[movements]]` is named as one of those,
    so the reader opens the table the row is in. The plain comparison,
    whose one row is used, prints no such line.

    The comparator's capture prints what `capture` prints about a pinned
    input, which the table does not: over a subject with a second input
    pinning a repository the arm makes, its kept clone — in a cache under a
    HOME of the arm's own — holding a path git ignores, the null mutant's
    capture and the mutant's each print the `clone:` line and the residue
    line once, under a heading naming the copy and the check, with the
    clone's address folded. The block is printed as the capture ends: a
    check that fires on the null mutant after it refuses the run, and the
    null mutant's block is already printed. The subject that pins nothing
    prints no heading and no `clone:` line.
    """
    label = ("mmmmmm  `mutants`' comparator permits what the manifest's "
             "[[movements]] permit, as `compare` does: over one golden with a "
             "permitted planted line, `compare` is IDENTICAL (1 permitted "
             "movement), the null mutant is SILENT, a real mutant FIRES, and "
             "both details carry the permitted count; two more rows naming "
             "the row the mutant moves make its comparison refuse, as "
             "`compare` does: its cell reads REFUSED, the line under its row "
             "and its FAIL line say the comparison refused, the table still "
             "prints and the run exits 1, and a row naming the planted row "
             "too refuses the run on the null mutant, saying its comparison "
             "refused; a row that permits a movement that did not happen "
             "is named on an `unused:` line in front of that verdict by "
             "the table it is in, `--allow-diff` or `[[movements]]`, and "
             "a comparison whose every row is used prints none; over a subject with a "
             "pinned input whose kept clone holds a path git ignores, each "
             "capture the comparator makes — the null mutant's and the "
             "mutant's — prints its `clone:` line and its residue line once, "
             "under a heading naming the copy and the check, the clone's "
             "address folded, the null mutant's printed before a check that "
             "fires there refuses the run, and a subject that pins nothing "
             "prints no heading and no line")
    if shutil.which("git") is None:
        skip(label, "`git` is not on PATH, and this arm needs `git clone "
                    "--local` to make the copy the comparator captures. Nothing "
                    "was made and nothing is claimed.")
        return
    with _box("golden-census-permitted-") as box:
        try:
            manifest, why = _writer_box(os.path.join(box, "moved"), _UTF8,
                                        moved=True)
        except _CaptureBroke as broke:
            _capture_broke(check, label, _one_line(str(broke), 400))
            return
        if manifest is None:
            skip(label, f"the throwaway subject could not be prepared: {why}. "
                        "Nothing is claimed.")
            return
        rows = _writer_mutants(box, "rows.toml", "the row count", "rows: 3",
                               "rows: 4")
        table_code, table = _mutants_run(manifest, box, rows)
        # Rows that name a moved row beside another row: two more naming the
        # row the mutant moves, and one naming the planted row the manifest
        # already names, which moves on the unmutated copy.
        planted = manifest.movements[0]
        overlap_code, overlap_table = _mutants_run(manifest._replace(
            movements=manifest.movements + tuple(
                planted._replace(path=path, attribution=f"planted: {path}")
                for path in ("_subject/rows.txt", "_subject/*.txt"))),
            box, rows)
        null_code, null_text = _mutants_run(manifest._replace(
            movements=manifest.movements + (planted._replace(
                path="_subject/*.out", attribution="planted: every stdout"),)),
            box, rows)
        compared = io.StringIO()
        golden = os.path.join(manifest.subject.root, "golden")
        compare_code = compare(manifest, golden, None, None, compared)
        stale = io.StringIO()
        stale_code = compare(manifest, golden, None,
                             [(_STALE_ROW, "planted: nothing moves there")],
                             stale)
        stale_manifest = io.StringIO()
        stale_manifest_code = compare(manifest._replace(
            movements=manifest.movements + (planted._replace(
                path=_STALE_ROW, attribution="planted: nothing moves there"),)),
            golden, None, None, stale_manifest)
        try:
            null = _verdict_on(manifest, box, rows, planted=False)
            fired = _verdict_on(manifest, box, rows, planted=True)
        except Refusal as refused:
            null = fired = Verdict("comparator", True, f"REFUSED: {refused}")
        except Exception as exc:                # reported, not raised
            if isinstance(exc, UNREPORTABLE):
                raise
            null = fired = Verdict("comparator", True,
                                   f"raised {type(exc).__name__}: {exc}")
        # A pinned input, its tree kept in a cache under a HOME of this arm's.
        origin = os.path.join(box, "origin")
        os.makedirs(origin)
        for name, text in (("a.txt", "one line of a throwaway repository\n"),
                           (".gitignore", "junk/\n")):
            pathlib.Path(os.path.join(origin, name)).write_text(
                text, encoding="utf-8")
        code, head, stderr = _repo_of(origin, "the origin")
        if code != 0:
            skip(label, f"`{head}` exited {code}: {stderr[:DIFFERENCE]}; "
                        "nothing is claimed.")
            return
        sha = launch(["git", "-C", origin, "rev-parse", "HEAD"],
                     "git rev-parse", env=git_env()).stdout.strip()
        home = os.path.join(box, "home")
        with _env_as({"HOME": home, "XDG_CACHE_HOME": os.path.join(home, "xdg")}):
            try:
                pinned, why = _writer_box(
                    os.path.join(box, "pinned"), _UTF8,
                    manifest_text=_WRITER_MANIFEST + _PINNED_INPUT.replace(
                        "{url}", origin).replace("{sha}", sha))
            except _CaptureBroke as broke:
                _capture_broke(check, label, _one_line(str(broke), 400))
                return
            if pinned is None:
                skip(label, f"the pinned subject could not be prepared: {why}. "
                            "Nothing is claimed.")
                return
            # Residue in the kept clone the golden capture made.
            junk = os.path.join(Platform.detect().cache_dir(),
                                "golden-census-trees",
                                repository_folder(
                                    resolved_address(origin, None)),
                                sha, "junk")
            os.makedirs(junk)
            pathlib.Path(os.path.join(junk, "x")).write_text(
                "ignored\n", encoding="utf-8")
            pinned_code, pinned_table = _mutants_run(pinned, box, rows)
            # A check that fires on the null mutant after the comparator: the
            # run is refused there, and the comparator's block is printed.
            pathlib.Path(os.path.join(box, "always.toml")).write_text(
                pathlib.Path(os.path.join(box, rows)).read_text(
                    encoding="utf-8") + _ALWAYS_FIRES, encoding="utf-8")
            told = io.StringIO()
            try:
                run_mutants(pinned, load_mutants(
                    os.path.join(box, "always.toml")), told)
                null_refusal = ""
            except Refusal as refused:
                null_refusal = refusal_text(refused)
        said = {which: re.search(
            r"\n  " + re.escape(which) + r", check 'comparator':\n    clone: "
            + re.escape(f"<WORK>/{os.path.basename(box)}/origin @ ")
            + r"[0-9a-f]{7,}, clean\n    clone: git ignores 1 path in it "
            r"that is not the pinned content: 'junk/'; delete the clone's "
            r"folder to start clean\n\n", pinned_table)
            is not None for which in ("the null mutant",
                                       "mutant 'the row count'")}

        block = re.compile(
            r"\n  the null mutant, check 'comparator':\n    clone: "
            + re.escape(f"<WORK>/{os.path.basename(box)}/origin @ ")
            + r"[0-9a-f]{7,}, clean\n    clone: git ignores 1 path in it "
            r"that is not the pinned content: 'junk/'; delete the clone's "
            r"folder to start clean\n\n")
        before = (block.search("\n" + told.getvalue()) is not None
                  and "reported by always (exited 3)" in null_refusal)
        shown = _in_box(re.sub(r"@ [0-9a-f]{7,}, clean", "@ <sha>, clean",
                               _one_line(pinned_table, 400,
                                         needles=("check ", "clone:"))),
                        os.path.basename(box))

    check(label,
          table_code == 0
          and "null mutant: comparator SILENT" in table
          and "1/1 mutants caught" in table
          and overlap_code == 1
          and re.search(r"\n  the row count\s+REFUSED\n    comparator: the "
                        r"comparison refused: _subject/rows\.txt moved, and 2 "
                        r"rows that permit movements name it: ",
                        overlap_table) is not None
          and "\n  FAIL  the row count — comparator REFUSED (its comparison "
              "of the mutated copy refused, so it gave no verdict)\n"
              in overlap_table
          and null_code == 2
          and "because its comparison of that copy refused" in null_text
          and "The comparison refused: _subject/rows.out moved, and 2 rows "
              in null_text
          and compare_code == 0
          and "IDENTICAL (1 permitted movement)" in compared.getvalue()
          and "unused:" not in compared.getvalue()
          and stale_code == 0
          and stale.getvalue().count("unused:") == 1
          and _STALE_FILE_LINE + "\n\n  IDENTICAL (1 permitted movement)\n"
          in stale.getvalue()
          and "[[movements]]" not in stale.getvalue()
          and stale_manifest_code == 0
          and stale_manifest.getvalue().count("unused:") == 1
          and _STALE_MANIFEST_LINE + "\n\n  IDENTICAL (1 permitted movement)\n"
          in stale_manifest.getvalue()
          and "--allow-diff" not in stale_manifest.getvalue()
          and not null.fired
          and null.detail == "IDENTICAL (1 permitted movement)"
          and fired.fired
          and fired.detail == ("1 differing row(s), first _subject/rows.txt "
                               "(changed) (1 permitted)")
          and "clone:" not in table
          and ", check 'comparator':" not in table
          and pinned_code == 0 and all(said.values())
          and pinned_table.count("    clone: ") == 4
          and before,
          f"{ACTUAL}mutants -> exit {table_code}, "
          f"{_one_line(table, 200, needles=_TABLE_NEEDLES)!r}; "
          f"two rows naming the row the mutant moves -> exit {overlap_code}, "
          f"{_one_line(overlap_table, 300, needles=_TABLE_NEEDLES)!r}; "
          f"a row naming the planted row too -> exit {null_code}, "
          f"{_one_line(null_text, 160)!r}; "
          f"compare -> exit {compare_code}, "
          f"{_one_line(compared.getvalue(), 80, needles=('IDENTICAL', 'DIFF'))!r}; "
          f"with an --allow-diff row that permits nothing -> exit {stale_code}, "
          f"{_one_line(stale.getvalue(), 200, needles=('unused:', 'IDENTICAL'))!r}; "
          f"with a [[movements]] row that permits nothing -> exit "
          f"{stale_manifest_code}, "
          f"{_one_line(stale_manifest.getvalue(), 200, needles=('unused:', 'IDENTICAL'))!r}; "
          f"the null mutant's verdict {null.detail!r}; the mutant's "
          f"{fired.detail!r}; pinning nothing, `clone:` lines "
          f"{table.count('clone:')}, headings "
          f"{table.count(', check ')}; pinning an input -> exit "
          f"{pinned_code}, each copy's block whole {said}, `clone:` lines "
          f"{pinned_table.count('    clone: ')}, "
          # The origin's commit is new on every run: written `<sha>`.
          f"{shown!r}; a check that fires on the null mutant -> the "
          f"null mutant's block before the refusal={before}, "
          f"{_one_line(null_refusal, 100)!r}")


# ------------------------------------------- what a run leaves behind (xxxxxxx)

#: The plant arm `xxxxxxx` hands its `[[setup]]` steps and its `command`
#: check: an immutable file, which `core.remove_tree` cannot take away, in
#: the directory named by the first argument, or in each directory the
#: second argument matches there as a `glob` pattern, or in the directory
#: the step runs in when there is no argument; a `$NAME` in the first
#: argument is read from the environment, which is how a `command` check is
#: handed its own TMPDIR. A directory that holds one already is left as it
#: is.
_PIN_STEP = '''\
import glob
import os
import stat
import sys

base = os.path.expandvars(sys.argv[1]) if sys.argv[1:] else "."
found = (glob.glob(os.path.join(glob.escape(base), sys.argv[2]))
         if sys.argv[2:] else [base])
for directory in found:
    path = os.path.join(directory, "pinned")
    if not os.path.lexists(path):
        open(path, "w", encoding="utf-8").close()
        os.chflags(path, stat.UF_IMMUTABLE)
'''

#: The census row of arm `xxxxxxx`'s `capture` run: a `drift` control whose
#: command leaves an immutable file in the work directory the census's
#: controls run in, and prints what the pin moves.
_PIN_CONTROL = (
    '\n[[input]]\nname        = "the clock the control reads"\n'
    'disposition = "pin"\nvariable    = "SOURCE_DATE_EPOCH"\n'
    'value       = "0"\nfinding     = "planted: the drift control leaves an '
    'immutable file in its work directory"\ncontrol     = { shape = "drift", '
    'command = ' + json.dumps([
        "<PYTHON>", "-c",
        "import os, stat, time; p = os.path.join('<WORK>', 'pinned'); "
        "os.path.lexists(p) or (open(p, 'w').close(), "
        "os.chflags(p, stat.UF_IMMUTABLE)); "
        "print(os.environ.get('SOURCE_DATE_EPOCH') or repr(time.time()))"])
    + ', wait = 0.1 }\n')

#: What the `xxxxxxx` arm's runs print for each directory that stayed.
_LEFT_LINE = "  a directory golden-census made could not be removed: "
_LEFT_TAIL = " — delete it by hand and name it in your report"


def _left_path(line: str) -> str:
    """The path a `not_removed` line names: the line without its opening
    and without its closing instruction."""
    return line[len(_LEFT_LINE):].removesuffix(_LEFT_TAIL)

#: The manifest of arm `xxxxxxx`'s `census` run: one row that prints
#: COLUMNS and leaves an immutable file in the work directory it is handed,
#: under a census whose `vary` control varies COLUMNS on that row.
_VARY_MANIFEST = '''\
[subject]
name    = "vary-stub"
root    = "subject"
command = ''' + json.dumps([
    "<PYTHON>", "-c",
    "import os, stat, sys; p = os.path.join(sys.argv[1], 'pinned'); "
    "open(p, 'w').close(); os.chflags(p, stat.UF_IMMUTABLE); "
    "print(os.environ.get('COLUMNS'))"]) + '''
census  = "vary-census.toml"

[inputs._subject]
args     = []
surfaces = ["rows"]

[surfaces.rows]
args = ["<WORK>"]
'''

#: That census: the stub census, whose `vary` control varies COLUMNS,
#: pointed at that row.
_VARY_CENSUS = _STUB_CENSUS.replace('"_subject/help"', '"_subject/rows"')

#: The `command` check of arm `xxxxxxx`'s `cleaned` run, listed after the
#: comparator: on the planted mutant's copy alone, it makes read-only the
#: run's work directory its TMPDIR and the copy sit in, so neither can be
#: removed until that work directory's own removal makes it writable.
_LOCK_CHECK = json.dumps([
    "<PYTHON>", "-c",
    "import os, sys; 'rows: 4' in open(os.path.join(sys.argv[1], "
    "'tool.py')).read() and os.chmod(os.path.dirname("
    "os.environ['TMPDIR']), 0o555)", "<ROOT>"])

#: What a mkdtemp suffix of a directory golden-census made looks like: arm
#: `xxxxxxx`'s detail orders paths with it taken out, so the order does not
#: move with the names the run drew.
_DRAWN = re.compile(r"(golden-census-(?:[a-z]+-)*)[a-z0-9_]{8}(?=/|$)")


def _unpin(root: str) -> None:
    """Every flag on every file under `root` cleared, so the box can go."""
    # Looked up by name: `os.chflags` exists on macOS and the BSDs and not on
    # Linux, where the arm that pins a file SKIPs and nothing is pinned to
    # clear; the lookup keeps bare `mypy` clean on both.
    chflags = getattr(os, "chflags", None)
    if chflags is None:
        return
    for directory, _names, files in os.walk(root):
        for name in files:
            with contextlib.suppress(OSError):
                chflags(os.path.join(directory, name), 0)


def _left_under(root: str, nested: bool) -> list[str]:
    """Every entry under `root`, and with `nested` every directory one level
    further down: where the `xxxxxxx` arm's runs make theirs — `mutants`
    makes its copies inside its work directory."""
    found = []
    for name in sorted(os.listdir(root)):
        top = os.path.join(root, name)
        found.append(top)
        if nested and os.path.isdir(top) and not os.path.islink(top):
            found += [os.path.join(top, inner)
                      for inner in sorted(os.listdir(top))
                      if os.path.isdir(os.path.join(top, inner))]
    return found


def _pinned_manifest(box: str, name: str, step: list[str],
                     census: str = "census.toml") -> str:
    """`_MUTANT_MANIFEST` with a `[[setup]]` step `pin` running `step` before
    its one row, under `census`, written to `<box>/<name>`."""
    path = os.path.join(box, name)
    pathlib.Path(path).write_text(
        _MUTANT_MANIFEST.replace('"census.toml"', json.dumps(census))
        + "needs = [\"pin\"]\n\n[[setup]]\nname    = \"pin\"\ncommand = "
        + json.dumps(["<PYTHON>", os.path.join(box, "pin.py"), *step]) + "\n",
        encoding="utf-8")
    return path


def _left_behind_control(check: CheckRow, skip: SkipRow) -> None:
    """(xxxxxxx) a directory golden-census made that stays after its
    removal is named on standard output, one line each, and the exit code
    is the run's own.

    Commands run through the real command line in children, each under a
    temp root of its own in the box; in each, the directories named are
    every directory left under the root, each named once. `capture` whose
    census has a `drift` control that leaves an immutable file in the
    controls' work directory, and whose `[[setup]]` step leaves one in the
    work directory it runs in: the census's directory is named after the
    census controls' tally and before the capture starts, the capture's
    before `capture complete`, at exit 0. `capture --twice` whose step
    leaves one in the second capture's directory: that directory is named,
    at exit 2 with a refusal — the two captures differ by that file.
    `census` whose `vary` control's row leaves one in the work directory
    it is handed: the control's three places are named after the block's
    tally, at exit 0. `mutants` under a census that folds the temp root,
    whose `command` checks, listed before the comparator, leave one in the
    copy each checks and one in each check's own TMPDIR: the null mutant's
    copy, the planted mutant's copy, each TMPDIR and the run's work
    directory that holds them are named after the table, at exit 0.
    `mutants` with the comparator alone, whose step leaves one in the
    comparator's capture: that capture's directory and the run's work
    directory are named, at exit 2 with a refusal. `mutants` whose step
    leaves one in the work directory of each comparator capture, with a
    check after the comparator that makes the run's work directory
    read-only on the planted copy: each capture's work directory is named
    after the table, and the planted copy and that check's TMPDIR, which
    the removal of the run's work directory takes at the end, are not, at
    exit 0. Every line golden-census prints about a directory that could
    not be removed is that one line, naming the path unfolded. Then, in
    this process: `run.clone_input` handed an address whose folder name is
    too long to be made leaves no `golden-census-trees` in the cache it was
    given.

    SKIPPED, nothing claimed, where `os.chflags` or `stat.UF_IMMUTABLE` is
    missing, and where an immutable file can be unlinked here, which is
    then no plant. Where `git` is not on PATH the three `mutants` runs,
    which clone the subject, do not run and the row is a SKIP that says
    so; the rest runs, and a red one of it is a red row.
    """
    label = ("xxxxxxx  a directory golden-census made that stays after its "
             "removal is named on standard output, one line each, and the "
             "exit code is the run's own: `capture` whose census control and "
             "[[setup]] step each leave an immutable file in the work "
             "directory they run in names the census's after the census "
             "controls' tally and the capture's before `capture complete`, "
             "at exit 0; `capture --twice` whose step leaves one in the "
             "second capture's directory names it, at exit 2; `census` "
             "whose `vary` control's row leaves one in each place names the "
             "three places after the block's tally, at exit 0; `mutants` "
             "whose command checks leave one in each copy and in each "
             "check's TMPDIR names the null mutant's copy, the mutant's "
             "copy, the two TMPDIRs and the work directory holding them "
             "after its table, at exit 0; `mutants` whose step leaves one in "
             "the comparator's capture names that capture's directory and "
             "the work directory, at exit 2; `mutants` whose step leaves one "
             "in each comparator capture's work directory names those two "
             "after its table and not the copy and TMPDIR a check made "
             "read-only that the run's last removal took, at exit 0; each "
             "run names every directory left under its temp root and no "
             "other, and says it in that one line alone, the path unfolded "
             "under a census that folds the temp root; a clone folder whose "
             "name is too long to be made leaves no golden-census-trees in "
             "the cache")
    if not hasattr(os, "chflags") or not hasattr(stat, "UF_IMMUTABLE"):
        skip(label, "this platform has no `os.chflags` with "
                    "`UF_IMMUTABLE`, so no file can be made that a removal "
                    "cannot take. Nothing is claimed.")
        return
    git = shutil.which("git") is not None
    ran = {}
    named: dict[str, list[str]] = {}
    left: dict[str, list[str]] = {}
    with _box("golden-census-leftover-") as box:
        try:
            probe = os.path.join(box, "probe")
            os.mkdir(probe)
            pathlib.Path(probe, "f").write_text("", encoding="utf-8")
            os.chflags(os.path.join(probe, "f"), stat.UF_IMMUTABLE)
            try:
                os.unlink(os.path.join(probe, "f"))
            except OSError:
                pass
            else:
                skip(label, "an immutable file was unlinked here, so it is "
                            "no plant. Nothing is claimed.")
                return
            path, why = _mutant_box(box, repository=git)
            if path is None:
                skip(label, f"the throwaway subject could not be put in a "
                            f"git repository: {why}. Nothing is claimed.")
                return
            pathlib.Path(box, "pin.py").write_text(_PIN_STEP,
                                                   encoding="utf-8")
            pathlib.Path(box, "pin-census.toml").write_text(
                _MUTANT_CENSUS + _PIN_CONTROL, encoding="utf-8")
            pathlib.Path(box, "vary-census.toml").write_text(
                _VARY_CENSUS, encoding="utf-8")
            pathlib.Path(box, "vary.toml").write_text(_VARY_MANIFEST,
                                                       encoding="utf-8")
            pathlib.Path(box, "fold-census.toml").write_text(
                _MUTANT_CENSUS + _STUB_WORK_FOLD, encoding="utf-8")
            roots = {name: os.path.join(box, f"root-{name}") for name in
                     ("capture", "twice", "vary", "mutants", "comparator",
                      "cleaned")}
            argv = {
                "capture": ["capture", "--manifest", _pinned_manifest(
                    box, "pinned.toml", [], "pin-census.toml"),
                    "--out", os.path.join(box, "out")],
                "twice": ["capture", "--twice", "--manifest", _pinned_manifest(
                    box, "twice.toml", [roots["twice"],
                                        "golden-census-twice-*"]),
                    "--out", os.path.join(box, "out-twice")],
                "vary": ["census", "--manifest",
                         os.path.join(box, "vary.toml")]}
            if git:
                golden = os.path.join(box, "golden")
                made = io.StringIO()
                try:
                    code = capture(load_manifest(path), golden, made)
                except Refusal as refused:
                    code, made = 2, io.StringIO(refusal_text(refused))
                if code != 0:
                    _capture_broke(check, label,
                                   _one_line(made.getvalue(), 400))
                    return
                checks = os.path.join(box, "pin-mutants.toml")
                comparator = ("[checks.comparator]\nbuiltin = \"compare\"\n"
                              "golden  = \"<HERE>/golden\"\n\n[[mutant]]\n"
                              "name    = \"the row count\"\nfile    = "
                              "\"tool.py\"\nfind    = 'print(\"rows: 3\")'\n"
                              "replace = 'print(\"rows: 4\")'\nexpect  = "
                              "[\"comparator\"]\n")
                pathlib.Path(checks).write_text(
                    "[checks.pin]\ncommand = "
                    + json.dumps(["<PYTHON>", "<HERE>/pin.py", "<ROOT>"])
                    + "\nfires   = \"exit-nonzero\"\n\n[checks.keep]\n"
                    "command = "
                    + json.dumps(["<PYTHON>", "<HERE>/pin.py", "$TMPDIR"])
                    + "\nfires   = \"exit-nonzero\"\n\n" + comparator,
                    encoding="utf-8")
                only = os.path.join(box, "alone-mutants.toml")
                pathlib.Path(only).write_text(comparator, encoding="utf-8")
                locked = os.path.join(box, "locked-mutants.toml")
                pathlib.Path(locked).write_text(
                    comparator.replace(
                        "\n\n[[mutant]]", "\n\n[checks.lock]\ncommand = "
                        f"{_LOCK_CHECK}\nfires   = \"exit-nonzero\"\n\n"
                        "[[mutant]]"),
                    encoding="utf-8")
                folded = os.path.join(box, "folded.toml")
                pathlib.Path(folded).write_text(
                    _MUTANT_MANIFEST.replace('"census.toml"',
                                             '"fold-census.toml"'),
                    encoding="utf-8")
                argv["mutants"] = ["mutants", "--manifest", folded,
                                   "--mutants", checks]
                argv["comparator"] = [
                    "mutants", "--manifest", _pinned_manifest(
                        box, "inner.toml", [
                            roots["comparator"],
                            "golden-census-mutants-*/"
                            "golden-census-mutant-capture-*"]),
                    "--mutants", only]
                argv["cleaned"] = [
                    "mutants", "--manifest", _pinned_manifest(
                        box, "cleaned.toml", [], "fold-census.toml"),
                    "--mutants", locked]
            for name, args in argv.items():
                os.mkdir(roots[name])
                env = dict(os.environ, PYTHONPATH=os.path.dirname(PACKAGE),
                           TMPDIR=roots[name])
                ran[name] = launch(
                    _package_argv("-m", IMPORT_NAME, *args),
                    f"arm xxxxxxx's {name} run", env=env, cwd=box)
                named[name] = [_left_path(line)
                               for line in ran[name].stdout.splitlines()
                               if line.startswith(_LEFT_LINE)]
                left[name] = _left_under(roots[name], args[0] == "mutants")
            cache = os.path.join(box, "cache")
            os.mkdir(cache)
            _tree, reason = clone_input(cache, "/nowhere/" + "x" * 300,
                                        "0" * 40, io.StringIO())
            in_cache = sorted(os.listdir(cache))
        finally:
            _unpin(box)

    def shown(paths: list[str]) -> list[str]:
        """`paths` with the box's path as `<box>` and a check's TMPDIR as
        `<check TMPDIR>`, in the order they take with their drawn suffixes
        taken out."""
        return sorted(
            ((os.path.join(os.path.dirname(path), "<check TMPDIR>")
              if tmpdir(path) else path).replace(box, "<box>")
             for path in paths), key=lambda path: _DRAWN.sub(r"\1", path))

    def tmpdir(path: str) -> bool:
        """`path` is a check's own TMPDIR: inside a `mutants` work
        directory, and neither a copy nor the comparator's capture."""
        here, name = os.path.split(path)
        return (os.path.basename(here).startswith("golden-census-mutants-")
                and name not in ("null", "the-row-count")
                and not name.startswith("golden-census-mutant-capture-"))

    def kind(name: str, prefix: str) -> list[str]:
        """The directories run `name` left whose own name opens `prefix`."""
        return [path for path in left[name]
                if os.path.basename(path).startswith(prefix)]

    def each_once(name: str) -> bool:
        """Run `name` named every directory it left, each one once."""
        return (sorted(named[name]) == sorted(left[name])
                and len(named[name]) == len(set(named[name])))

    def after(name: str, opening: str) -> bool:
        """Every line run `name` named a directory in comes after its last
        line opening `opening`: the block's tally, or the table's."""
        said = lines[name]
        marks = [i for i, line in enumerate(said) if line.startswith(opening)]
        return bool(marks) and all(
            i > marks[-1] for i, line in enumerate(said)
            if line.startswith(_LEFT_LINE))

    lines = {name: run.stdout.splitlines() for name, run in ran.items()}
    elsewhere = "".join(_heard(run.stderr).not_from(PACKAGE)
                        for run in ran.values())
    # Any other wording of the fact, in any run: one fact, one line.
    stray = sorted({line.strip().replace(box, "<box>")
                    for said in lines.values() for line in said
                    if "could not be removed" in line
                    and not line.startswith(_LEFT_LINE)})
    said = lines["capture"]
    census = kind("capture", "golden-census-census-")
    tally = next((i for i, line in enumerate(said)
                  if line.startswith("  ") and " passed" in line), None)
    begun = next((i for i, line in enumerate(said)
                  if line.startswith("capture -> ")), None)
    done = (said.index("  capture complete")
            if "  capture complete" in said else None)
    census_at = [i for i, line in enumerate(said)
                 if census and line == _LEFT_LINE + census[0] + _LEFT_TAIL]
    work_at = [i for i, line in enumerate(said) if line.startswith(_LEFT_LINE)
               and _left_path(line) not in census]
    after_tally = (len(census) == 1 and len(census_at) == 1
                   and tally is not None and begun is not None
                   and tally < census_at[0] < begun)
    before_complete = (len(work_at) == 1 and done is not None
                       and begun is not None and begun < work_at[0] < done)
    captured = (ran["capture"].returncode == 0 and len(left["capture"]) == 2
                and each_once("capture") and after_tally and before_complete)
    twice = (ran["twice"].returncode == 2
             and any(line.startswith("REFUSED: ") for line in lines["twice"])
             and len(left["twice"]) == 1
             and len(kind("twice", "golden-census-twice-")) == 1
             and each_once("twice"))
    varied = (ran["vary"].returncode == 0 and len(left["vary"]) == 3
              and each_once("vary") and after("vary", "  1/1 passed"))
    detail = (f"capture -> exit {ran['capture'].returncode}, named "
              f"{shown(named['capture'])}, left {shown(left['capture'])}, "
              f"the census's line after its tally {after_tally}, the "
              f"capture's before 'capture complete' {before_complete}; "
              f"capture --twice -> exit {ran['twice'].returncode}, named "
              f"{shown(named['twice'])}, left {shown(left['twice'])}; "
              f"census -> exit {ran['vary'].returncode}, named "
              f"{shown(named['vary'])}, left {shown(left['vary'])}, after "
              f"its tally {after('vary', '  1/1 passed')}")
    if git:
        table = any(line.startswith("  1/1 mutants caught")
                    for line in lines["mutants"])
        work = [path for path in left["mutants"]
                if os.path.dirname(path) == roots["mutants"]]
        tmps = [path for path in left["mutants"] if tmpdir(path)]
        copies = [path for path in left["mutants"]
                  if path not in work and path not in tmps]
        alone = ran["comparator"]
        cleaned = ran["cleaned"]
        caught = "  1/1 mutants caught"
        mutated = (ran["mutants"].returncode == 0 and table
                   and len(work) == 1 and len(copies) == 2 and len(tmps) == 2
                   and each_once("mutants") and after("mutants", caught)
                   and alone.returncode == 2
                   and any(line.startswith("REFUSED: ")
                           for line in lines["comparator"])
                   and len(left["comparator"]) == 2
                   and len(kind("comparator", "golden-census-mutants-")) == 1
                   and len(kind("comparator",
                                "golden-census-mutant-capture-")) == 1
                   and each_once("comparator")
                   and cleaned.returncode == 0
                   and len(left["cleaned"]) == 2
                   and not kind("cleaned", "golden-census-mutants-")
                   and each_once("cleaned") and after("cleaned", caught))
        detail += (f"; mutants -> exit {ran['mutants'].returncode}, named "
                   f"{shown(named['mutants'])}, left "
                   f"{shown(left['mutants'])}, its table printed {table}; "
                   f"the comparator alone -> exit {alone.returncode}, named "
                   f"{shown(named['comparator'])}, left "
                   f"{shown(left['comparator'])}; the cleaned run -> exit "
                   f"{cleaned.returncode}, named {shown(named['cleaned'])}, "
                   f"left {shown(left['cleaned'])}, after its table "
                   f"{after('cleaned', caught)}")
    else:
        mutated = True
        detail += ("; the three mutants runs -> not run: `git` is not on "
                   "PATH")
    detail += (f"; any other wording {stray}{elsewhere}"
               f"; the overlong clone folder -> "
               f"{reason.replace(box, '<box>')[-60:]!r}, the cache holds "
               f"{in_cache}")
    held = (captured and twice and varied and mutated and not stray
            and "too long" in reason and in_cache == [] and not elsewhere)
    if held and not git:
        skip(label, "`git` is not on PATH, and the three `mutants` runs need "
                    "`git clone --local` to make the copies they check: they "
                    "did not run, and nothing is claimed for them. The rest "
                    f"ran and held: {detail}")
        return
    check(label, held, f"{ACTUAL}{detail}")
