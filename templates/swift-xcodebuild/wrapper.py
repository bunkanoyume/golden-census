"""The subject command for a Swift app or framework under `xcodebuild test`:
one test, quietly.

    wrapper.py --project P --scheme S --test ID --entitlements E [--destination D] <root> <out>
    wrapper.py --project P --scheme S --test ID --entitlements E [--destination D] <root> --version

A Swift app has no command line, so golden-census's subject is this wrapper. It
runs ONE test — the `-only-testing:` id `--test` names, the GoldenCensusRunner —
with `TEST_RUNNER_GOLDEN_CENSUS_OUT=<out>` in xcodebuild's environment (that prefix
is how xcodebuild forwards a variable to the test process), and the file that
test writes is the whole record. Nothing this script prints on success is a
golden, because a build log is paths and timings: it prints NOTHING and exits
0 when the run worked, and the last 40 log lines on stderr with exit 1 when it
did not. A wrong argument, a missing project or a missing entitlements file is
one sentence and a `next:` line on stderr, exit 2, before xcodebuild starts.

THE OUT FILE IS THE VERDICT, not the exit code. An `-only-testing:` filter
that matches no test still reports `TEST SUCCEEDED` and exits 0 — a renamed
suite would otherwise record an empty capture as a pass. So both conditions
are required, and the out file is removed before the run so a leftover from
an earlier run cannot answer for this one.

The five facts about the project are ARGUMENTS, never edits to this file, so
the manifest's `command` is the whole description of the subject:

  --project       the .xcodeproj, relative to <root>
  --scheme        the scheme that builds the test target
  --test          the -only-testing: id, `<TestTarget>/<Suite>`
  --entitlements  the app's own entitlements plist, relative to <root>
  --destination   the xcodebuild destination; default platform=macOS,arch=arm64

Three things this wrapper has to say out loud about the project it drives:

1. DERIVED DATA lives in a persistent cache (`golden-census-dd/<scheme>/<hash of the
   root>/dd`), one entry per subject root, so an ordinary capture is a test run
   and not a rebuild. It is NOT under the subject's `$TMPDIR`: the census pins
   that to a fresh fixed-width directory golden-census removes after every
   capture, so a cache there would be a full build every time. The base is the
   machine's own per-user temp root, read from `getconf DARWIN_USER_TEMP_DIR`,
   which is the same directory whatever `$TMPDIR` says. Entries whose root has
   gone (a `mutants` clone, deleted with its scratch) are pruned on the next
   run, so mutant builds cannot accumulate.

2. THE TEST HOST IS SANDBOXED. An app whose entitlements carry
   `com.apple.security.app-sandbox` runs its test bundle inside the app, and
   that process cannot write golden-census's out file, which lives in
   golden-census's work directory (`NSCocoaErrorDomain 513 … Operation not
   permitted`). The wrapper builds the test host against a DERIVED entitlements
   file: the project's own plist plus
   `com.apple.security.temporary-exception.files.absolute-path.read-write`.
   Derived, never a committed copy, so it cannot drift from the project's; and
   the sandbox itself stays on, so nothing else about the host changes.
   `CODE_SIGN_ENTITLEMENTS=` (empty) is silently ignored, which is why the
   derived file is always passed.

3. PARALLEL TESTING IS OFF. A scheme that marks the test bundle
   `parallelizable = "YES"` launches two test hosts, and two hosts running this
   suite at once write the same out file concurrently.
   `-parallel-testing-enabled NO` makes the write single.

golden-census never imports any of this: it runs the script, records the bytes.
This file imports nothing from golden-census either.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

#: The key added to the project's plist for the test host, and nothing else.
READ_WRITE_EXCEPTION = "com.apple.security.temporary-exception.files.absolute-path.read-write"

DEFAULT_DESTINATION = "platform=macOS,arch=arm64"

TAIL_LINES = 40


def refuse(sentence: str, next_step: str) -> int:
    """One sentence and a `next:` line on stderr, exit 2 — before xcodebuild
    starts. The wrapper's own refusals never print a traceback."""
    sys.stderr.write(f"REFUSED: {sentence}\n  next: {next_step}\n")
    return 2


def cache_base() -> str:
    """The machine's per-user temp root, independent of `$TMPDIR`.

    `getconf DARWIN_USER_TEMP_DIR` prints the root macOS gives this user
    whatever `$TMPDIR` is set to — which is the point, because under the census
    `$TMPDIR` is a fixed-width directory that exists for one capture. A machine
    without `getconf` (or not macOS, where nothing here would run anyway) falls
    back to the interpreter's own answer.
    """
    try:
        proc = subprocess.run(["getconf", "DARWIN_USER_TEMP_DIR"], check=False,
                              capture_output=True, text=True)
    except OSError:
        return tempfile.gettempdir()
    root = proc.stdout.strip()
    if proc.returncode != 0 or not os.path.isdir(root):
        return tempfile.gettempdir()
    return root


def derived_data(root: str, scheme: str) -> str:
    """This subject root's derived-data directory, made if it is not there.

    Keyed by a hash of the root so the worktree and every `mutants` clone build
    into their own store: one shared store would mean each build invalidating
    the last, and two trees writing one `Build/Products` is a hazard nobody
    should have to reason about. Entries whose root no longer exists are removed
    first — that is what keeps a run of mutants from leaving a build tree per
    clone behind.
    """
    if scheme in ("", ".", "..") or "/" in scheme or "\\" in scheme:
        sys.exit(refuse(
            f"--scheme must be a name, never a path: {scheme!r} holds a path "
            "separator or is '.' or '..', and the wrapper keys its build "
            "cache by the scheme.",
            "Pass the scheme's name as Xcode lists it, and nothing else."))
    home = os.path.join(cache_base(), "golden-census-dd", scheme)
    os.makedirs(home, exist_ok=True)
    for name in os.listdir(home):
        entry = os.path.join(home, name)
        marker = os.path.join(entry, "root.txt")
        if not os.path.isdir(entry):
            continue
        try:
            with open(marker, encoding="utf-8") as handle:
                built_from = handle.read().strip()
        except OSError:
            continue                      # not ours, or half-made: leave it
        if not os.path.isdir(built_from):
            shutil.rmtree(entry, ignore_errors=True)
    mine = os.path.join(home, hashlib.sha256(root.encode()).hexdigest()[:16])
    os.makedirs(mine, exist_ok=True)
    with open(os.path.join(mine, "root.txt"), "w", encoding="utf-8") as handle:
        handle.write(root + "\n")
    return mine


def test_host_entitlements(source: str, cache: str) -> str:
    """The project's entitlements plus a read-write file exception, on disk.

    The exception is what lets the sandboxed test host write the out file at
    all. Everything else in the plist is the project's, read fresh every run: a
    committed copy would be a second place the app's entitlements live, and the
    day they diverged this wrapper would be running a host the project does not
    describe.
    """
    with open(source, "rb") as handle:
        document = plistlib.load(handle)
    document[READ_WRITE_EXCEPTION] = ["/"]
    path = os.path.join(cache, "golden-census-test-host.entitlements")
    with open(path, "wb") as handle:
        plistlib.dump(document, handle)
    return path


def print_version(root: str) -> int:
    """`xcodebuild -version`, one line, for the capture log's version note."""
    proc = subprocess.run(["xcodebuild", "-version"], check=False,
                          capture_output=True, text=True, cwd=root)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-2000:])
        return 1
    sys.stdout.write(" ".join(proc.stdout.split()) + "\n")
    return 0


def run(args: argparse.Namespace, root: str, out: str) -> int:
    cache = derived_data(root, args.scheme)
    try:
        entitlements = test_host_entitlements(
            os.path.join(root, args.entitlements), cache)
    except (ValueError, OSError) as exc:
        return refuse(
            f"the entitlements file {args.entitlements} could not be read "
            f"as a property list: {exc}",
            "Point --entitlements at the target's .entitlements plist, "
            "relative to the project root.")
    if os.path.exists(out):
        os.remove(out)                    # nothing earlier may answer for this run
    argv = [
        "xcodebuild", "test",
        "-project", os.path.join(root, args.project),
        "-scheme", args.scheme,
        "-destination", args.destination,
        "-derivedDataPath", os.path.join(cache, "dd"),
        "-only-testing:" + args.test,
        "-parallel-testing-enabled", "NO",
        "CODE_SIGN_ENTITLEMENTS=" + entitlements,
    ]
    environment = dict(os.environ)
    environment["TEST_RUNNER_GOLDEN_CENSUS_OUT"] = out
    proc = subprocess.run(argv, check=False, capture_output=True, text=True,
                          cwd=root, env=environment, stdin=subprocess.DEVNULL)
    if proc.returncode == 0 and os.path.isfile(out):
        return 0
    # The out file's NAME is never printed: it is an absolute path under
    # golden-census's work directory, and stderr is recorded.
    sys.stderr.write(
        f"xcodebuild exited {proc.returncode}; the out file "
        f"{'exists' if os.path.isfile(out) else 'was not written'}\n")
    for line in (proc.stdout + proc.stderr).splitlines()[-TAIL_LINES:]:
        sys.stderr.write(line + "\n")
    sys.stderr.write(
        "  next: read the log lines above; if xcodebuild succeeded and no file "
        f"was written, the -only-testing: id {args.test!r} matched no test "
        "(a renamed suite, or a runner not yet moved into the test target).\n")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wrapper.py", add_help=True,
        description="run one xcodebuild test quietly and let it write "
                    "golden-census's out file")
    parser.add_argument("--project", required=True,
                        help="the .xcodeproj, relative to <root>")
    parser.add_argument("--scheme", required=True,
                        help="the scheme that builds the test target")
    parser.add_argument("--test", required=True,
                        help="the -only-testing: id, <TestTarget>/<Suite>")
    parser.add_argument("--entitlements", required=True,
                        help="the app's own entitlements plist, relative to <root>")
    parser.add_argument("--destination", default=DEFAULT_DESTINATION,
                        help=f"the xcodebuild destination (default {DEFAULT_DESTINATION})")
    parser.add_argument("--version", action="store_true",
                        help="print `xcodebuild -version` on one line instead of running")
    parser.add_argument("root", help="the subject root: the directory the project sits in")
    parser.add_argument("out", nargs="?", default=None,
                        help="the file the test writes; omitted with --version")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as exited:
        # argparse printed its usage; the exit code is its own (2 on a usage
        # error, 0 on --help). Never a traceback.
        return int(exited.code or 0)
    if (args.out is None) == (not args.version):
        return refuse(
            "the wrapper takes <root> and then EXACTLY ONE of <out> or "
            "--version, and got " + ("both" if args.out else "neither") + ".",
            "Pass the out file as the last argument, or --version alone "
            "after <root>.")
    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, args.project)):
        return refuse(
            f"--project {args.project!r} is not a directory under <root>.",
            "Spell --project as the .xcodeproj's path relative to the "
            "subject root.")
    if args.version:
        return print_version(root)
    if not os.path.isfile(os.path.join(root, args.entitlements)):
        return refuse(
            f"--entitlements {args.entitlements!r} is not a file under <root>; "
            "the test host is built against a copy of the app's own plist "
            "and there is none to copy.",
            "Spell --entitlements as the app's .entitlements path relative "
            "to the subject root.")
    return run(args, root, os.path.abspath(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
