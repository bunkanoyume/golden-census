"""How a row of a manifest is prepared and run: the place rows run in and the
order it is prepared in, the subject's argv and its subprocess, the row's
environment, the clone of a pinned input, the setup steps, the `[files]` and
the counter, and what is recorded of a run's texts.

`capture` records with these; nothing here writes a capture directory.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, NamedTuple

from .census import (
    Census,
    _child_failed,
    _git_failed,
    build_env,
    describing,
    git_env,
    normalize_json,
    normalize_text,
    preconditions,
    surface_env,
)
from .core import (
    GIT_UNTRACKED,
    QUOTE_SHORT,
    Pending,
    Platform,
    Refusal,
    Roots,
    _capture_text,
    folded_name,
    git_command,
    launch,
    made_in_place,
    require_cache_dir,
    row_key,
    under,
    unpunctuated,
    with_next,
    workspace,
)
from .manifest import (
    Input,
    Manifest,
    Surface,
    command_context,
    context,
    expand_writes,
    files_key,
    files_table,
)


class RunResult(NamedTuple):
    tail: list[str]            # everything after `command` — what a golden records
    exit: int
    out: str
    err: str
    written: str | None        # the text of the file the run wrote, or None


class Texts(NamedTuple):
    """One run's three texts."""

    out: str
    err: str
    written: str | None        # the text of the file the run wrote, or None


class RowRun(NamedTuple):
    """One row, run once: what the subject produced, and what a capture
    records of it."""

    key: str                   # "<input>/<surface>"
    tail: list[str]            # everything after `command`
    exit: int
    raw: Texts                 # as the subject produced them
    recorded: Texts            # after the census's folds for `key`
    extension: str | None      # the one the written file is recorded under
    writes: str | None         # the written file's path in this place
    env: dict[str, str]        # the environment the row ran under


# ------------------------------------------------------------------- running


def surface_argv(manifest: Manifest, subject_input: Input, surface: Surface,
                 roots: Roots, writes: str | None) -> list[str]:
    """`command + input.args + surface.args`, expanded.

    Everything after `command` is what `surfaces.json` records, so a golden
    never carries the interpreter path or the entry-point path.
    """
    table = context(roots, writes)
    where = (f"{manifest.path}: [inputs.{subject_input.name}] / "
             f"[surfaces.{surface.name}]")
    return [table.expand(arg, where) for arg in subject_input.args + surface.args]


def subject_command(manifest: Manifest, roots: Roots) -> list[str]:
    """The argv prefix of every run, expanded. `<PYTHON>` is the interpreter
    running golden-census and `<HERE>` is `Manifest.here` — the manifest's own
    directory, or its place in the copy of the subject a run is against; a
    golden carries neither, because `surfaces.json` records only what comes
    AFTER this prefix.

    Expansion is all that happens to these strings. An element that is neither
    absolute nor a placeholder is passed exactly as the author wrote it, and
    resolves against the cwd of the run, which is `<ROOT>`: golden-census does
    not go looking for an entry point it was not told the path of.
    """
    table = command_context(roots, manifest.here)
    return [table.expand(arg, f"{manifest.path}: [subject] command")
            for arg in manifest.subject.command]


def _outside(path: str, work: str) -> str | None:
    """Where a row's `writes` path `path` resolves, its directory's links
    followed, when that is outside the work directory `work`; None when it
    stays under it.

    The ONE test of "this path is golden-census's", asked by
    `_clear_written` before a row runs and by `run_subject` after it: the
    work directory itself must not be a link, the levels above it must
    resolve where they did when `workspace` made it (`core.made_in_place`),
    and the path's directory must resolve under it (`core.under`). Before
    the run the path's own last name is not followed: a `writes` path that
    is itself a link to a file stays inside, where its link is removed and
    its file kept. After the run `run_subject` hands it the path with every
    link on it followed, the last name's too.
    """
    if (os.path.islink(work) or not made_in_place(work)
            or not under(os.path.dirname(path), work, strict=False)):
        return os.path.join(os.path.realpath(os.path.dirname(path)),
                            os.path.basename(path))
    return None


def _clear_written(path: str, where: str, writes_as: str, work: str) -> None:
    """Remove whatever file is at a row's `writes` path, just before the row
    runs, so the written file a capture records is the one THIS run wrote.

    The ONE owner of "clear the writes path". Rows run one after another
    under one work directory, and a `[files]` entry or a `[[setup]]` step can
    create the same path first, so without this a row that wrote nothing
    recorded a file somebody else left there. Nothing tries to tell a seed
    from a leftover: the path is cleared, and the documents say so. The
    loader holds the SPELLING of `writes` under `<WORK>/`; a link made on the
    way after the load — a setup step's, an earlier row's — can still lead
    out of `work`, so `_outside` is asked first, and a path that resolves
    outside `work` is a refusal and never a removal.
    Nothing there is not a fault; anything else that stops the removal — a
    directory at the path, a permission — is a refusal naming the row
    (`where`) and the manifest's spelling (`writes_as`).
    """
    resolved = _outside(path, work)
    if resolved is not None:
        raise Refusal(
            f"{where} writes {writes_as}, which resolves to {resolved}, "
            "outside golden-census's work directory. golden-census clears "
            "that path before the run, and it removes nothing outside the "
            "work directory.",
            next="Point `writes` at a path that stays under <WORK> when its "
            "links are followed: nothing that runs before the row may make a "
            "directory on its way a link that leads out of <WORK>.")
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as blocked:
        raise Refusal(
            f"{where} writes {writes_as}, and golden-census could not clear "
            f"that path before the run: {type(blocked).__name__}: "
            f"{blocked.strerror}. A written file is recorded only when this "
            "run wrote it, so whatever is at the path goes first.",
            next="Point `writes` at a file path under <WORK> that nothing else creates — no "
            "`[files]` entry, setup step or other row makes a directory there.") from blocked


def run_subject(manifest: Manifest, argv: list[str], roots: Roots,
                env: dict[str, str], written_path: str | None = None,
                where: str = "", writes_as: str = "",
                pending: Pending | None = None) -> RunResult:
    """One subprocess. Its standard input is the null device, `launch`'s
    default; the cwd is the subject root, and the environment is the
    census's — golden-census never imports the subject.

    `where` is the row key — `<input>/<surface>` — and `writes_as` is the
    manifest's own spelling of `writes`. They are the refusal's two nouns, and
    they are parameters because this function has neither of its own: the
    window its caller opens names the expanded argv and the built environment
    and no row at all. `run_row` passes a `written_path`, and both nouns;
    the other two callers pass no written file and reach neither refusal
    over one.

    `pending` is the record that window describes a refusal from, and it is
    handed to `launch`, which alone says the subject ended: a refusal raised
    after the subject ran — `launch`'s own over a byte that is not UTF-8,
    the two below over the written file, or a fold's over what the subject
    printed — carries a block that opens `ran:`. Every caller that opens a
    window hands it.

    The written file is read only where `_outside` says its path, every
    link on it followed, stays under the work directory once the subject has
    run: the subject's own command can make the path, or a directory on its
    way, a link that leads out, after `_clear_written` asked, and a file read
    through it is not one this run wrote under `<WORK>`. Such a path is a
    refusal after the run, whether or not a file is there, and nothing is
    read from it.

    The read that SUCCEEDS keeps the subject's line endings: `newline=""`
    turns off the universal-newlines translation `open` would otherwise
    apply, for the reason `launch` runs its child for bytes — a `\\r\\n` the
    subject wrote is a byte of the golden, and a subject that changes its
    line endings has changed what it writes. `_capture_text` is asked
    only after this read has already failed, on a path that ends the run —
    and because it is a SECOND read it can disagree with the first and come
    back with nothing to say, which is why the refusal has a sentence of its
    own for that.
    """
    whole = subject_command(manifest, roots) + argv
    if written_path is not None:
        _clear_written(written_path, where, writes_as, roots.work)
    proc = launch(whole, "the subject", cwd=roots.root, env=env,
                  pending=pending)
    if written_path is not None:
        resolved = _outside(os.path.realpath(written_path), roots.work)
        if resolved is not None:
            raise Refusal(
                f"{where} writes {writes_as}, which resolves to {resolved} "
                "once the row has run, outside golden-census's work "
                "directory. golden-census records a written file only from "
                "under the work directory, and it recorded nothing from that "
                "path.",
                next="Point `writes` at a path that stays under <WORK> when "
                "its links are followed: the row's own command may not make "
                "that path, or a directory on its way, a link that leads out "
                "of <WORK>.")
    written = None
    if written_path is not None and os.path.isfile(written_path):
        try:
            with open(written_path, encoding="utf-8", newline="") as handle:
                written = handle.read()
        except (OSError, UnicodeDecodeError) as unrecordable:
            # The WHY has one owner, `_capture_text`, and it is quoted as it
            # comes back: "not text: 0x.. at byte offset N (...)" or "cannot
            # be read: <Error>: <strerror>". Only the sentence around it is
            # written here.
            _, why = _capture_text(written_path)
            # That second read can SUCCEED — a lock or a permission that was
            # there for the first one and gone a moment later — and then it
            # has no reason to give and returns "". A refusal with a hole
            # where its reason goes is worse than one that says less: what is
            # known either way is that the read this capture depended on
            # failed, so that is what the sentence says.
            why = why or ("could not be read as UTF-8 text when this capture "
                          "read it, and read cleanly a moment later")
            raise Refusal(
                f"{where} writes {writes_as} — {why}. golden-census "
                "records text — a written file is read, normalized and "
                "compared line by line, and bytes it cannot decode have no "
                "golden and no diff.",
                next="Record a text DUMP of that file instead: make the row's command a "
                "wrapper that writes the file under <WORK> and a deterministic dump of it "
                "to <WRITES> — for a database, one ORDER BY per table — and give `writes` "
                "the dump's extension."
                ) from unrecordable
    return RunResult(argv, proc.returncode, proc.stdout, proc.stderr, written)


def _row_env(census: Census, surface: Surface, roots: Roots,
             writes: str | None, env: Mapping[str, str]) -> dict[str, str]:
    """One surface's environment: `env` with the surface's own `env` on top,
    each value expanded in the vocabulary its `args` use — `<WRITES>`
    included, which is why the caller computes `writes` first. The one
    owner of that expansion: a capture's row and the `vary` control's run
    both come through here."""
    table = context(roots, writes)
    extra = {name: table.expand(value, f"[surfaces.{surface.name}] env")
             for name, value in (surface.env or {}).items()}
    return surface_env(census, env, extra)


def recorded_texts(result: RunResult, census: Census, roots: Roots, key: str,
                   extension: str | None) -> Texts:
    """What a capture records of one run's texts: stdout, stderr and the
    written file (None when nothing was written), each after the census's
    folds for row `key` — a written `.json` through `normalize_json`, any
    other through `normalize_text`. `extension` is the one the written file
    is recorded under. The one owner, read by `run_row` and by
    `Recorder.record`; the `vary` control's run is a `run_row`, so the
    control compares what the golden holds.
    A fold's refusal propagates, stdout's first."""
    out = normalize_text(result.out, census, roots, key)
    err = normalize_text(result.err, census, roots, key)
    if result.written is None:
        return Texts(out, err, None)
    is_json = extension is not None and folded_name(extension) == "json"
    written = (normalize_json(result.written, census, roots, key) if is_json
               else normalize_text(result.written, census, roots, key))
    return Texts(out, err, written)


# ------------------------------------------------------------------ the clone


def _in_cache(target: str, what: str, *args: str,
              cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    """One git step INSIDE the clone cache `target`, asking that cache and
    no other repository: the ONE owner of the argv and the environment of
    every git that runs in a clone — `clone_input`'s, and `_porcelain`'s
    after the rows.

    A `checkout`, a `status` and a `rev-parse` name the cache's `.git` and
    work tree, so git neither walks up to a repository above the cache nor
    follows an inherited `GIT_DIR` or `GIT_WORK_TREE`. A `clone` names
    `target` as its destination only: handed a work tree, `clone` makes the
    work tree its repository. Every step runs under `census.git_env`'s
    environment, which says why. `cwd` is the directory the step runs in, the
    process's own where None: `clone_input` passes the manifest's directory
    to the `clone`, the one step that reads a path the manifest spelled.
    Every step is `core.git_command`'s argv, so a clone's content and
    whether it is clean are the repository's answer, whatever the global
    configuration of the user running golden-census says.
    """
    named_tree = ([] if args[:1] == ("clone",) else
                  ["--git-dir", os.path.join(target, ".git"),
                   "--work-tree", target])
    return launch(git_command(*named_tree, *args), what, cwd=cwd,
                  env=git_env(what))


def _porcelain(target: str, *, ignored: bool = False
               ) -> tuple[str | None, str]:
    """What `git status --porcelain` lists in the clone at `target`, with
    the white space at its end dropped, and "" — or (None, reason) where
    that git did not exit 0. With `ignored`, what `git status --porcelain
    --ignored` lists: the paths git ignores too, each on a line that opens
    `!! `.

    The one owner of that run, for `clone_input` before an input's rows
    and for `_refuse_written` after them, through `_in_cache` like every
    git step in a clone; `clone_input` passes `ignored` for a kept clone,
    so that one question is also the question about the paths git ignores
    there. Its return code is tested BEFORE its standard output is read,
    and the reason is `_git_failed`'s. A git that could not be started, or
    that did not answer `_in_cache`'s question, raises through —
    `launch`'s refusal or `_in_cache`'s — and each caller handles it.

    Whether a clone is clean is the repository's answer and not the
    caller's: the run is `_in_cache`'s, under `core.GIT_SETTINGS`, and asks
    `core.GIT_UNTRACKED`, so neither a global ignore file nor a
    `status.showUntrackedFiles = no` of the user running golden-census
    hides a file from it. The repository's own ignore rules — `.gitignore`
    and `.git/info/exclude` — still hold.
    """
    run = ["status", "--porcelain"] + (["--ignored"] if ignored else [])
    status = _in_cache(target, "git status", *run, GIT_UNTRACKED)
    if status.returncode != 0:
        return None, _git_failed("git " + " ".join(run), status)
    return status.stdout.rstrip(), ""


def _lists(listed: str) -> str:
    """How a sentence quotes what `git status --porcelain` listed: how many
    lines, then the listing cut at `QUOTE_SHORT`. A count of lines, because
    a rename is one line that names two paths."""
    count = len(listed.splitlines())
    return (f"`git status --porcelain` lists {count} "
            f"line{'' if count == 1 else 's'}, {listed[:QUOTE_SHORT]!r}")


#: How many of the paths git ignores in a kept clone `_residue` names.
RESIDUE_PATHS = 3

#: What each line `clone_input` writes to its log opens with: the `clone:`
#: line, and the residue line `_residue` words beside it. A `vary` control
#: picks its runs' lines out of their place's log by it, and `mutants` picks
#: a comparator's out of its capture's.
CLONE_LINE = "  clone: "


def _residue(listed: str) -> str:
    """The line that says what git ignores in a kept clone, or "" when it
    ignores nothing: `listed` is what `_porcelain` listed with `ignored`.

    One sentence, in the voice of the `clone:` line it follows: how many
    paths, then the first `RESIDUE_PATHS` of them as git spells them, then
    how many more. A path git quotes in its porcelain output, one that
    holds a space or a quote, is printed as git spelled it, inside this
    line's own quotes: nothing is unquoted. Git ignores those paths, so
    they are not the pinned content. The line changes no verdict and no
    exit code.
    """
    paths = [line[3:] for line in listed.splitlines()
             if line.startswith("!! ")]
    if not paths:
        return ""
    more = len(paths) - RESIDUE_PATHS
    one = len(paths) == 1
    return (f"{CLONE_LINE}git ignores {len(paths)} "
            f"path{'' if one else 's'} in it that {'is' if one else 'are'} "
            "not the pinned content: "
            + ", ".join(repr(path) for path in paths[:RESIDUE_PATHS])
            + (f" and {more} more" if more > 0 else "")
            + "; delete the clone's folder to start clean\n")


def repository_folder(url: str) -> str:
    """The folder name a repository's address is kept under: `url` with every
    character that is not an ASCII letter, a digit, `.`, `_` or `-` replaced
    by `-`, one for one.

    The ONE rule, with no list of hosts and no reading of the address: two
    addresses that differ only in the characters this replaces share one
    folder, and `clone_input` takes a kept clone only from the address it
    was asked for.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "-", url)


class GitMetadata(NamedTuple):
    """What `git_metadata_digest` holds of one clone: one SHA-256 hex digest
    for each part of its `.git` that a later git would act on."""

    config: str
    hooks: str
    info: str


#: The names of those three parts, in `GitMetadata`'s order, as a sentence
#: spells them.
GIT_METADATA_PARTS = (".git/config", ".git/hooks/", ".git/info/")


def git_metadata_digest(clone: str) -> GitMetadata:
    """One SHA-256 for each of `clone`'s `.git/config`, the files under its
    `.git/hooks/` and the files under its `.git/info/`: over the relative
    path and the bytes of each file, in sorted order. A part that is absent
    contributes nothing; a file that cannot be read contributes its path and
    a marker, so a file that becomes unreadable is a change too.

    The ONE rule for what `git status --porcelain` cannot see: it never
    lists `.git/`, and a hook or a configuration written there acts on a
    later capture's git. `Place.enter` takes this once and `_refuse_written`
    takes it again.
    """
    git = os.path.join(clone, ".git")
    parts = []
    for part in ("config", "hooks", "info"):
        digest = hashlib.sha256()
        found = [os.path.join(git, part)]
        if os.path.isdir(found[0]):
            found = sorted(os.path.join(folder, name)
                           for folder, _, names in os.walk(found[0])
                           for name in names)
        for path in found:
            try:
                with open(path, "rb") as handle:
                    content = handle.read()
            except FileNotFoundError:
                continue
            except OSError:
                content = b"\0unreadable"
            digest.update(os.path.relpath(path, git).encode("utf-8", "replace")
                          + b"\0" + content + b"\0")
        parts.append(digest.hexdigest())
    return GitMetadata(*parts)


def resolved_address(url: str, where: str | None) -> str:
    """The address `git clone` is handed: `url` as git resolves it, which is
    its real absolute path where `os.path.join(where, url)` names a file or
    a directory (a bundle, or a repository), and `url` unchanged otherwise.
    `where` is the directory `git clone` runs in, the process's working
    directory where None.

    The ONE rule, with no list of schemes and no classifier: git reads a
    path against the directory it runs in, so the same spelling in two
    manifests' directories is two repositories, and a `url` that names a
    path there is that path whichever way it was spelled, which is also the
    spelling git keeps as `remote.origin.url`. An address that names none,
    a URL or an scp-like address, is git's to read.
    """
    path = os.path.join(where or os.getcwd(), url)
    return os.path.realpath(path) if os.path.exists(path) else url


def clone_input(cache_dir: str, url: str, sha: str, out: Any, *,
                before_clone: Callable[[], None] | None = None,
                where: str | None = None) -> tuple[str | None, str]:
    """An input's tree at its pinned commit, or (None, reason).

    The tree is `golden-census-trees/<repository>/<sha>` under `cache_dir`,
    which every command passes as `Platform.cache_dir` names it: the user's
    cache directory, never the temp root, which the operating system empties.
    `<repository>` is `repository_folder` of the address `resolved_address`
    makes of `url`, and `<sha>` the pin as the manifest spells it.
    golden-census keeps no index of the cache: every
    folder at every level is self-contained, so deleting one pin, one
    repository or the whole cache by hand breaks nothing but the next run's
    need to clone again. A missing network is that input's rows SKIPPED with
    the error quoted — never a pass, and never a bypass of the network
    policy. The cache is deliberately persistent, so the next capture does
    not re-clone.

    `before_clone`, when given, is called once the tree is known not to be
    there and before anything is made for the clone, so the caller's
    question about the cache directory is asked right before a clone this
    call makes and never for a tree it finds. What it raises leaves through
    this call.

    `where` is the directory `git clone` runs in, the manifest's own, so a
    `url` spelled as a relative path names a repository beside the manifest,
    as every other path a manifest spells does; git reads an address that is
    not a path as it reads it from anywhere. `git clone` is handed
    `resolved_address(url, where)`, and the folder `<repository>` is named
    from that address, so two manifests that pin one relative path from two
    directories get two folders. The `clone:` line prints `url`, the address
    as spelled; a password never reaches either, `manifest._inputs` refuses
    it at load. A cache directory spelled
    relative is made absolute first, against the process's directory, so
    `where` moves only the repository.

    Where this call made no tree, the `golden-census-trees` and
    `<repository>` folders it made for the clone are removed again, each
    only if empty.

    A tree this call finds is shared: every input, of any manifest, that
    pins this repository at this commit meets the same folder, and a file
    a row wrote there where the repository's own ignore rules hide it
    stays for the next input, in
    this run or another. For a tree it finds and takes, the one `status`
    it runs is `status --porcelain --ignored`: the lines that do not open
    `!! ` are what `status --porcelain` lists and decide whether the tree
    is clean, and the lines that do are the paths git ignores, which
    `_residue` words as a line that follows the `clone:` line. A clone
    this call makes is asked the plain `status --porcelain` and has no such
    line. Nothing is removed and nothing is refused for the ignored paths.

    A tree this call finds is taken only when its `remote.origin.url` is the
    address `git clone` is handed: two addresses that differ only in
    characters `repository_folder` replaces meet one folder, and the second
    input is SKIPPED naming the folder and both addresses. Nothing is
    deleted.

    A clone's directory, or its `.git`, that is a symbolic link is never
    taken, whatever it points at: both are tested first, before any git,
    and either is that input SKIPPED with a reason that names the linked
    path. golden-census makes no link there.

    Every git step is `_in_cache`'s, which asks that cache and no other
    repository. A clone this call makes takes four runs of git — `clone`,
    `checkout`, `status --porcelain` and `rev-parse HEAD` — and a
    tree it finds takes four, `config --get remote.origin.url`, `checkout`,
    `status --porcelain --ignored` and `rev-parse HEAD`; the return code of
    each is tested BEFORE its standard output is read. One that did not exit 0 is the reason
    `_git_failed` words, whatever it printed on standard output.

    The pin is a commit's id, and it is tested as one. The checkout is
    `--no-guess`, so a remote branch named like the pin is never made a
    branch of the clone and checked out; and the clone is taken only where
    the FULL id `rev-parse HEAD` prints begins with the pin. Where a tag or
    a branch of the clone is named like the pin, git's checkout prefers it
    to a commit's id and the clone is then at that ref's commit, which is
    taken only where its id begins with the pin. A `rev-parse` that exits 0
    and prints nothing is never the pin. The `clone:` line names HEAD by
    that full id.
    """
    address = resolved_address(url, where)
    target = os.path.join(os.path.abspath(cache_dir), "golden-census-trees",
                          repository_folder(address), sha)
    # Read ONCE, before the clone, because it is two facts at one reading:
    # whether to clone, and — for every git step below — whether this tree is
    # one golden-census kept from an earlier run. A cache something else
    # has half-removed leaves a `.git` with no HEAD, and every later capture
    # then skipped the input with `git checkout … not a git repository`: a
    # sentence naming neither the cache nor what to do about it.
    linked = [path for path in (target, os.path.join(target, ".git"))
              if os.path.islink(path)]
    if linked:
        return None, (f"the clone cache {linked[0]} is a symbolic link, "
                      "which golden-census never takes for a clone and never "
                      "removes. Delete that link and capture again.")
    existing = os.path.isdir(os.path.join(target, ".git"))
    # The folder itself, read at the same moment: a clone cut short before
    # git made its `.git` leaves the folder with files in it and no
    # repository, and `git clone` then refuses it in git's own words, naming
    # no remedy. An empty folder takes the clone, so a clone that fails
    # there failed for its own reason: it is not found. `OSError` is a
    # folder that is not there, every fresh clone's case, and one that
    # cannot be listed, whose contents this run did not see: neither is
    # found.
    try:
        found = bool(os.listdir(target))
    except OSError:
        found = False

    def kept(reason: str) -> str:
        """`reason`, and where the tree it is about came from.

        Only for a folder that ALREADY existed: on a fresh clone the
        directory is this run's own and naming it would send the reader to
        delete something that is not the fault. A folder with a `.git`
        directory in it was taken as a kept clone; one with files in it and
        no `.git` directory was there before this run with no repository in
        it, and `git clone` would not clone over it. An EMPTY folder is not
        `found`: it takes the clone, which is then this run's own, and a
        clone that fails there fails for its own reason, so this function
        names nothing for it. Either way the sentence names the folder and
        says to delete it. `reason` goes in
        without the period or colon it ends on (`core.unpunctuated`),
        because the sentence goes on after it. No deletion and no repair —
        golden-census does not remove a directory it did not make this run,
        and a rotted clone may be the only copy of something.
        """
        if existing:
            return (f"{unpunctuated(reason)}; this input's clone was taken "
                    "from a cache golden-census kept from an earlier run: "
                    f"{target}. Delete that directory and capture again.")
        if found:
            return (f"{unpunctuated(reason)}; this input's clone folder "
                    f"{target} was there before this run, with no `.git` "
                    "directory in it. Delete that directory and capture "
                    "again.")
        return reason
    # Every one of the four git runs goes through `launch`, and its refusal
    # comes back as this input's SKIP reason rather than as an exception: a
    # missing network is that input's rows skipped with the error quoted, and
    # a missing `git` is the same kind of fact about this machine. None of the
    # four carries a deadline of its own: golden-census cannot know how long a
    # clone of somebody's repository takes, so the caller owns the deadline
    # and the process group printed at the top of the log is what kills a
    # clone left running behind a caller that gave up.
    made: list[str] = []
    if not existing:
        if before_clone is not None:
            before_clone()
        folder = os.path.dirname(target)
        made = [path for path in (folder, os.path.dirname(folder))
                if not os.path.isdir(path)]
    try:
        if not existing:
            # Inside the `try`: a `makedirs` that made the parent and failed
            # at the folder leaves the parent to the `finally` below.
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as blocked:
                return None, (f"{folder} could not be made: "
                              f"{type(blocked).__name__}: "
                              f"{blocked.strerror or blocked}")
            proc = _in_cache(target, "git clone",
                             "clone", "--quiet", "--", address, target,
                             cwd=where)
            if proc.returncode != 0:
                return None, kept(_git_failed("git clone", proc))
        if existing:
            configured = _in_cache(target, "git config", "config", "--get",
                                   "remote.origin.url")
            if configured.returncode != 0:
                return None, kept(_git_failed(
                    "git config --get remote.origin.url", configured))
            origin = configured.stdout.strip()
            if origin != address:
                return None, (
                    f"the clone kept at {target} was cloned from "
                    f"{origin!r}, not from {address!r}: both addresses name this "
                    "one cache folder. Delete that directory and capture "
                    "again, or give one of the two repositories an address "
                    "whose letters and digits differ from the other's.")
        checkout = _in_cache(target, f"git checkout {sha}",
                             "checkout", "--quiet", "--no-guess", sha)
        if checkout.returncode != 0:
            return None, kept(_git_failed(f"git checkout {sha}", checkout))
        listed, failed = _porcelain(target, ignored=existing)
        if listed is None:
            return None, kept(failed)
        residue = _residue(listed)
        listed = "\n".join(line for line in listed.splitlines()
                           if not line.startswith("!! ")).rstrip()
        if listed:
            dirty = f"the clone at {target} is not clean: {_lists(listed)}"
            if not existing:
                return None, dirty
            return None, (f"{dirty}. Delete that directory and capture "
                          "again. If a row or a setup step of this manifest "
                          "wrote those paths, it must write them under "
                          "<WORK> instead, or a later capture skips this "
                          "input again.")
        head = _in_cache(target, "git rev-parse",
                         "rev-parse", "HEAD")
        if head.returncode != 0:
            return None, kept(_git_failed("git rev-parse HEAD", head))
    except Refusal as refused:
        return None, kept(with_next(str(refused), refused))
    finally:
        for path in made:
            with contextlib.suppress(OSError):
                os.rmdir(path)
    # Read only now that `rev-parse` exited 0. Commit ids are compared, never
    # a name, and one way only: HEAD's FULL id must begin with the pin. The
    # other way round, a pin longer than an abbreviated HEAD began with it
    # while naming no commit at all. An EMPTY answer begins with no pin.
    got = head.stdout.strip()
    if not got.startswith(sha):
        return None, kept(f"HEAD is {got!r}, not the pinned {sha!r}")
    out.write(f"{CLONE_LINE}{url} @ {got}, clean\n{residue}")
    return target, ""


# ------------------------------------------------------------- setup and files


def resolve_command(command: Iterable[str], manifest: Manifest, roots: Roots,
                    *, writes: str | None = None,
                    where: str | None = None) -> list[str]:
    """A `[[setup]]` or `counter` argv, expanded.

    These commands RUN in the work directory, and expansion is all that
    happens to their strings: an element is passed as the author wrote it,
    so a relative one names a path under `<WORK>`, and a file beside the
    manifest is spelled `<HERE>/…`, as in `[subject] command`. golden-census
    never looks beside the manifest for a name it was not told the path of:
    an argument that happened to share a name with a file there would be
    rewritten to that file, and a step writing it would write over the
    consumer's own.

    `<HERE>` is `Manifest.here` and not `Manifest.directory`: a setup step
    and a counter are subprocesses like the subject's own, so a run against a
    copy of the subject takes them from the copy too, and a manifest that
    sits inside the subject has its neighbors copied with it. Taking them from
    the tree golden-census was invoked in would run code the copy does not
    have, and a change planted in the copy would go unreached in silence.

    `writes` and `where` are keyword-only and exist for `run_counter`: a
    counter expands `<WRITES>` and its refusal names the surface rather than
    "a command".
    """
    table = command_context(roots, manifest.here, writes=writes)
    place = where or f"{manifest.path}: a command"
    return [table.expand(raw, place) for raw in command]


def run_setup(manifest: Manifest, name: str, roots: Roots,
              env: dict[str, str], out: Any) -> None:
    """One setup step. A step that does not exit 0 is a REFUSAL of the
    capture with its stderr quoted: a fixture that half-exists would record
    goldens that are about the fixture, not the subject.

    The window stays open until the exit code is tested, so the refusal's
    block is this step's — its expanded argv and the environment it was
    given — and not the block of a window the caller opened over the
    subject's command."""
    setup = manifest.setup_named(name)
    if setup is None:
        raise Refusal(f"needs: no [[setup]] named {name!r}",
                      next="Add a [[setup]] table with that `name`, or drop the `needs` entry that "
                      "asks for it.")
    pending = Pending(setup.command)
    pending.env = env
    with describing(pending, manifest.census, roots.root, roots.fixed):
        argv = resolve_command(setup.command, manifest, roots)
        pending.ran_as(argv)
        proc = launch(argv, f"[[setup]] {name!r}", cwd=roots.work, env=env,
                      pending=pending)
        if proc.returncode != 0:
            raise Refusal(_child_failed(f"[[setup]] {name!r}", proc,
                                        manifest.census, roots.root,
                                        roots.fixed),
                          next="Run that setup command by hand in a scratch directory, as a "
                          "capture runs it in <WORK>, and fix what it reports; a capture does "
                          "not start from a setup that failed.")
    out.write(f"  setup {name}: exit 0\n")


def write_files(manifest: Manifest, roots: Roots, out: Any) -> None:
    """The `[files."<name>"]` tables, into the work directory, before any
    `[[setup]]` step or row runs.

    A key the operating system will not write is ONE refusal naming its
    table, the path as `<WORK>/<key>` and the reason in the operating
    system's words, never a traceback. The loader refuses what the keys
    alone show (`manifest._refuse_file_above_file`); what a file system makes
    of a key — a name too long, two spellings it reads as one name, a
    permission — only the write finds out, so every `OSError` it raises is
    reported the same way and none is told apart from another. The key is
    spelled with JSON's escapes, each of which a TOML basic string reads the
    same, so a key holding a newline keeps the refusal on one line.

    A file is opened for creation only: a key whose path already holds a
    file OR a directory is refused by the same sentence, with the
    operating system's "File exists". That is how two keys a
    case-insensitive file system reads as one name are told — the second
    is refused, and the first's text is never written over.
    """
    for name, lines in manifest.files.items():
        path = os.path.join(roots.work, name)
        try:
            os.makedirs(os.path.dirname(path) or roots.work, exist_ok=True)
            with open(path, "x", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines) + "\n")
        except OSError as blocked:
            raise Refusal(
                f"{manifest.path}: golden-census could not write "
                f"{files_table(name)} to <WORK>/{files_key(name)[1:-1]}: "
                f"{blocked.strerror or blocked}.",
                next="Rename that key in the manifest, or change what made the operating "
                "system refuse that path; the `[files]` are written under <WORK> before "
                "any `[[setup]]` step or row runs.") from None
        out.write(f"  file {name}: {len(lines)} line(s)\n")


def run_counter(manifest: Manifest, surface: Surface, written_path: str | None,
                roots: Roots, env: dict[str, str]) -> dict[str, Any]:
    """The consumer's counter, handed the written file, printing a JSON object.

    golden-census has no idea what the numbers mean — the consumer's script
    does, which is the point.

    The window stays open until the counts are handed back: a counter that
    did not exit 0, or exited 0 and printed something that is not a JSON
    object, is refused with the COUNTER's block — its expanded argv and the
    environment it was given — and not the block of the row whose subject
    ran before it.
    """
    if not surface.counter:
        return {}
    pending = Pending(surface.counter)
    pending.env = env
    with describing(pending, manifest.census, roots.root, roots.fixed):
        argv = resolve_command(surface.counter, manifest, roots,
                               writes=written_path,
                               where=f"[surfaces.{surface.name}] counter")
        pending.ran_as(argv)
        proc = launch(argv, "the counter", cwd=roots.work, env=env,
                      pending=pending)
        if proc.returncode != 0:
            raise Refusal(
                _child_failed(f"[surfaces.{surface.name}] counter", proc,
                              manifest.census, roots.root, roots.fixed),
                next="Run the counter command by hand in a scratch directory, as a "
                "capture runs it in <WORK>; it has to exit 0 and print a JSON object.")
        try:
            counts = json.loads(proc.stdout)
        except ValueError as exc:
            raise Refusal(f"[surfaces.{surface.name}] counter did not print a "
                          f"JSON object: {exc}",
                          next="Make the counter print one JSON object on stdout and send any "
                          "progress text to stderr.") from exc
        if not isinstance(counts, dict):
            raise Refusal(f"[surfaces.{surface.name}] counter printed "
                          f"{type(counts).__name__}, not a JSON object",
                          next="Make the counter print one JSON object on stdout and nothing "
                          "else.")
    return counts


# ------------------------------------------------------------------ the place


class Entered(NamedTuple):
    """One input, entered: the roots its rows run under, and whether they can."""

    #: The place's roots with this input's clone; `clone` is None when the
    #: input pins no tree or its tree is unavailable.
    roots: Roots
    #: None when the input's rows can run; otherwise the reason the clone
    #: gave, which may be empty.
    unavailable: str | None


class Place:
    """The place a manifest's rows run in, prepared: its directories, the
    environment every row's own `env` goes on top of, and the clone of each
    input entered so far."""

    manifest: Manifest
    roots: Roots               # root, work, fixed; `clone` is None
    env: dict[str, str]
    cache_dir: str             # where `clone_input` keeps the clones
    out: Any                   # a text stream: `write` is all that is called
    clones: list[str]          # every clone entered so far, once each
    metadata: dict[str, GitMetadata]   # each clone's `git_metadata_digest`
                               # when it was first entered

    def __init__(self, manifest: Manifest, roots: Roots, env: dict[str, str],
                 cache_dir: str, out: Any) -> None:
        self.manifest = manifest
        self.roots = roots
        self.env = env
        self.cache_dir = cache_dir
        self.out = out
        self.clones = []
        self.metadata: dict[str, GitMetadata] = {}
        self._entered: dict[str, Entered] = {}
        self._cache_asked = False

    def enter(self, subject_input: Input) -> Entered:
        """`subject_input`'s roots, cloning its pinned tree the first time it
        is entered, after `_ask_cache`'s question where this is the place's
        first clone. The answer is kept by input name, so a second call
        clones nothing and prints nothing. The first time a clone is entered
        its `git_metadata_digest` is taken, for `_refuse_written`."""
        known = self._entered.get(subject_input.name)
        if known is not None:
            return known
        clone, reason = None, ""
        if subject_input.git and subject_input.sha:
            clone, reason = clone_input(self.cache_dir, subject_input.git,
                                        subject_input.sha, self.out,
                                        before_clone=self._ask_cache,
                                        where=self.manifest.directory)
            if clone and clone not in self.clones:
                self.clones.append(clone)
                self.metadata[clone] = git_metadata_digest(clone)
        entered = Entered(self.roots._replace(clone=clone),
                          reason if subject_input.git and clone is None
                          else None)
        self._entered[subject_input.name] = entered
        return entered

    def _ask_cache(self) -> None:
        """`core.require_cache_dir`, the first time a clone of this run is
        about to be made and never again in this place: the ONE asker of the
        question, held by the place, which lives for one run."""
        if not self._cache_asked:
            require_cache_dir()
            self._cache_asked = True


@contextlib.contextmanager
def place(manifest: Manifest, prefix: str, out: Any, *,
          rows: Iterable[tuple[Input, Surface]],
          change: Mapping[str, str] | None = None,
          opened: Callable[[Roots], None] | None = None,
          built: Callable[[Roots, dict[str, str]], None] | None = None,
          ) -> Iterator[Place]:
    """The place `rows` run in, made and prepared, and removed on the way out.

    In this order: the `core.workspace` directories, the fixed-width one
    first; `opened`; the census's preconditions; the environment, with
    `change` on top; `built`; the `[files]`; and every `[[setup]]` a surface
    of `rows` needs, in the manifest's order. After the rows, when they
    ended without raising, `_refuse_written` checks every clone they ran
    in. `opened` and `built` are the two moments a caller has lines of its
    own to print. No `attaching` window is opened here: a refusal leaves
    through the caller's. A setup step and a precondition open their own,
    over the command each of them runs.
    """
    census = manifest.census
    cache_dir = Platform.detect().cache_dir()
    with workspace(census, prefix, manifest.subject.root, out=out) as roots:
        if opened is not None:
            opened(roots)
        preconditions(census, roots, out)
        env = build_env(census, roots)
        if change is not None:
            env.update(change)
        if built is not None:
            built(roots, env)
        write_files(manifest, roots, out)
        needed = list(dict.fromkeys(name for _row, surface in rows
                                    for name in surface.needs))
        for setup in manifest.setups:
            if setup.name in needed:
                run_setup(manifest, setup.name, roots, env, out)
        where = Place(manifest, roots, env, cache_dir, out)
        yield where
        # After the rows, and only when they ended without raising: a
        # refusal already on its way out is the reader's first fact.
        _refuse_written(where)


def _joined(names: list[str]) -> str:
    """`names` as a sentence names them: one alone, else all but the last
    joined by commas, then ` and ` and the last."""
    return (names[0] if len(names) == 1 else
            f"{', '.join(names[:-1])} and {names[-1]}")


def _refuse_written(where: Place) -> None:
    """Refuse the command when a clone its rows ran in is not clean after
    them.

    `clone_input` found each clone of `where` clean before that input's
    rows; `_porcelain` is run once more in each, in the order they were
    entered. Inputs that pin one repository at one commit share a clone,
    which is checked once and named by every input that entered it, in the
    order they entered, as theirs together: the run does not hold which of
    them wrote. A path it lists was written there while this command ran,
    and a later run would find that clone not clean and skip the input:
    this run is the one that is told. A `git status` that did not exit 0
    refuses with the reason `_porcelain` gives. Every clone is checked
    before the refusal, and it names each one that failed. A git that
    could not be started, or that did not answer `_in_cache`'s question,
    is refused at the first clone it was asked about, naming that clone
    as unchecked and carrying the `next:` of the refusal it raised: git
    is the fault there, and the clone is not. The sentence says what was
    found, never which row wrote it: the run does not hold that fact.
    Nothing is removed — golden-census does not repair a pinned tree, and
    the next run's SKIP names the same directory.

    `git status --porcelain` never lists `.git/`, so the clone's
    `git_metadata_digest`, taken when `Place.enter` first entered it, is
    taken again; each part that moved is one more line, naming the parts,
    so a clone both written into and changed has two.
    """
    dirty: list[str] = []
    failed: list[str] = []
    entering: dict[str, list[str]] = {}
    for name, entered in where._entered.items():
        if entered.roots.clone is not None:
            entering.setdefault(entered.roots.clone, []).append(name)
    for clone, names in entering.items():
        unchecked = (f"{names[0]}: after this run's rows, the clone at {clone} "
                     "could not be checked")
        try:
            listed, reason = _porcelain(clone)
        except Refusal as refused:
            raise Refusal(f"{unchecked}: {refused}",
                          next=refused.next) from refused
        who = _joined(names)
        shared = "" if len(names) == 1 else " that their rows shared"
        if listed is None:
            failed.append(f"{unchecked}: {reason}")
        elif listed:
            dirty.append(f"{who}: the clone at {clone}{shared} was clean "
                         f"when this run checked it out, and after this "
                         f"run's rows {_lists(listed)}")
        moved = [part for part, was, now in
                 zip(GIT_METADATA_PARTS, where.metadata[clone],
                     git_metadata_digest(clone), strict=True)
                 if was != now]
        if moved:
            dirty.append(f"{who}: the clone at {clone}{shared} was clean "
                         f"when this run checked it out, and after this "
                         f"run's rows its {_joined(moved)} changed: a later "
                         "capture of any manifest that pins this repository "
                         "and commit would read what was written there")
    if not dirty and not failed:
        return
    that = ("that directory" if len(dirty) + len(failed) == 1
            else "those directories")
    raise Refusal(
        "\n  ".join(dirty + failed),
        next=(f"Make the row or the setup step that writes there write under "
              "<WORK>, or where the pinned commit's own .gitignore ignores "
              f"it; then delete {that} and run "
              "again." if dirty else
              f"Delete {that} and run again: the next run clones it afresh."))


# -------------------------------------------------------------------- the row


def row_start(where: Place, subject_input: Input, surface: Surface,
              pending: Pending | None = None
              ) -> tuple[str | None, dict[str, str]]:
    """A row's written path, then its environment: what every kind of row
    needs before it runs. `pending`, when handed in, is given the row's
    environment."""
    roots = where.enter(subject_input).roots
    # The written path is computed BEFORE the `env` block, not after it.
    # A surface's `env` is one of the four places the format says
    # `<WRITES>` may be spelled, and the token can only be valued from a
    # path that already exists — a test runner told where to write
    # through a variable (`GOLDEN_CENSUS_OUT=<WRITES>`) is the shape that
    # needs it. Nothing else moves: `expand_writes` reads the surface and
    # the roots and touches no disk.
    writes = expand_writes(surface, roots, subject_input.name)
    row_env = _row_env(where.manifest.census, surface, roots, writes,
                       where.env)
    if pending is not None:
        pending.env = row_env
    return writes, row_env


def run_row(where: Place, subject_input: Input, surface: Surface,
            pending: Pending | None = None) -> RowRun:
    """One `run` row, run once in `where`: its written path and environment
    (`row_start`), its argv, the subject's run, and the census's folds of
    its texts. `pending`, when handed in, is the record the caller's
    `attaching` window describes a refusal from; it is given the row's
    environment and then its expanded argv before the subject runs, and is
    handed to `run_subject`, whose `launch` says when the subject ended. A
    fold's refusal leaves straight after the run, as the run's own does."""
    manifest = where.manifest
    roots = where.enter(subject_input).roots
    writes, row_env = row_start(where, subject_input, surface, pending)
    argv = surface_argv(manifest, subject_input, surface, roots, writes)
    if pending is not None:
        pending.ran_as(subject_command(manifest, roots) + argv, row_env)
    key = row_key(subject_input.name, surface.name)
    result = run_subject(manifest, argv, roots, row_env, writes,
                         where=key, writes_as=str(surface.writes),
                         pending=pending)
    recorded = recorded_texts(result, manifest.census, roots, key,
                              surface.extension)
    return RowRun(key, result.tail, result.exit,
                  Texts(result.out, result.err, result.written), recorded,
                  surface.extension, writes, row_env)
