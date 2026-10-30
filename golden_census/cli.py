"""The command line.

    golden-census capture  --manifest M --out DIR [--input NAME]... [--force] [--twice]
    golden-census compare  --manifest M --golden DIR [--allow-diff FILE]
                           [--against DIR | --command ARG...]
    golden-census census   --manifest M
    golden-census mutants  --manifest M --mutants FILE [--only NAME]...
    golden-census probe    [--census C] [--writes-env NAME] -- <command…>
    golden-census init     <dir> [--template NAME] | --list
    golden-census --selfcheck [--manifest M]
    golden-census --selftest
    golden-census --version

Exit codes: 0 a pass or IDENTICAL, 1 a FAIL or differing rows, 2 REFUSED, 130 or 143 interrupted.
Every refusal is one sentence on stdout — stderr when stdout is unusable —
followed by a `next:` line saying what to do about it, and never a traceback.

`probe` and `init` are the two subcommands that take no manifest, and for one
reason: both are asked BEFORE a manifest exists. `probe` answers whether a
candidate command can be a subject; `init` writes the manifest itself. That is
why the manifest load sits under the dispatch in `main` rather than above it,
while which controls precede which command is still decided once, in one
place, for all of them.

A tool with no consumer baked into it has no default manifest and no default
golden directory to point at, so no path argument here carries a default and
both are named every time.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from collections.abc import Callable
from typing import Any

# `selfcheck`, `selftest`, `docs` and the arm modules import this module: the
# controls run in this process, and they exercise `main`, `run_census`,
# `build_parser` and the usage text themselves — a proof needs the thing it
# proves. This module imports none of them back, so the imports sit at the top
# of their files like any other. `--selfcheck` and `--selftest` run the two
# runners `main` is handed, and `console.main`, the one module above this one
# and both self-test modules, hands them; arm `bbbbbbbb` holds the package to
# no import cycle.
from . import __version__
from .capture import capture, guard_capture
from .census import (
    build_env,
    load_census,
    own_log,
    preconditions,
    state,
)
from .compare import compare, read_allow, read_sides
from .controls import census_check
from .core import (
    EXIT_OK,
    EXIT_REFUSED,
    IMPORT_NAME,
    PROG,
    SKILL_DIR,
    Layout,
    Refusal,
    anchored,
    refusal_text,
    in_utf8,
    refuse_on_stderr,
    require_temp_root,
    to_null,
    usable,
    workspace,
)
from .manifest import Manifest, load_manifest
from .mutants import chosen_and_checked, load_mutants, run_mutants
from .probe import probe
from .templates import init


#: Why a run with nowhere to print is refused, in the words both refusals of
#: an unusable standard output share: the one closed before the run starts
#: and the one closed under it.
WHOLE_VERDICT = f"{PROG} writes its whole verdict to standard output"

#: The four subcommands that read a manifest, in the order the sentences
#: below name them. `_subcommand` gives exactly these a required `--manifest`,
#: so the parser and every refusal that names them state one fact.
MANIFEST_COMMANDS = ("census", "capture", "compare", "mutants")

#: `MANIFEST_COMMANDS` as a sentence names them.
_READS_A_MANIFEST = (", ".join(f"`{name}`" for name in MANIFEST_COMMANDS[:-1])
                     + f" and `{MANIFEST_COMMANDS[-1]}`")


#: What `--help` says of itself in the help of every parser: argparse's own
#: words, then what a reader of `--selfcheck --help` is not otherwise told.
#: argparse answers `--help` inside `parse_args`, the first time it reads the
#: flag, by printing the help and exiting 0, so no other flag and no
#: subcommand on the same command line is acted on. Typed ONCE, here;
#: `_Parser.__init__` gives it to every parser.
HELP_LINE = ("show this help message and exit; nothing else on the command "
             "line is run")


class _Kept(argparse.Action):
    """Put in front of a flag's own action by `_Parser.add_argument`: what
    the flag was given is kept on the parser that read it, and the flag's own
    action then stores it as it always did."""

    def __call__(self, parser: Any, namespace: argparse.Namespace,
                 values: Any, option_string: str | None = None) -> None:
        parser.given.append((self, values))
        super().__call__(parser, namespace, values, option_string)


class _Parser(argparse.ArgumentParser):
    """An `ArgumentParser` that says which flags were given more than once.

    argparse's default action keeps the LAST value a flag was given and says
    nothing about the others: `compare --manifest A --manifest B` read `B`,
    and an `IDENTICAL` under it was a verdict about a manifest the reader may
    not have meant. The rule is stated here ONCE: a flag repeats when its
    action is declared `append`, and any other flag that was given more than
    once is in `given_again`. No flag is named here. A flag is held by the
    rule when it is added by `add_argument` on a parser of this class, and
    the subcommands' parsers are this class too — `add_subparsers` makes
    them of the class of the parser it is called on. A flag added through a
    group (`add_argument_group`, `add_mutually_exclusive_group`) is NOT held:
    the group's own `add_argument` makes it, and arm `aaaaaaa` is red on it.

    What comes out is `args.given_again`: one `(flag, times, values)` per flag
    given more than once, in the order the command line first gave them. The
    flag is named by `named`, whatever spelling was typed — argparse resolves
    `--man` and `--manifest=M` before an action is called. `values` is every
    value in the order given, and empty for a flag that takes none. It is a
    fact and no verdict: `main` is what refuses.

    `given` is what `_Kept` writes to, and it is empty from `__init__` on. A
    parser entered by another door than `parse_known_args` — argparse enters
    a subcommand's parser by that one — leaves its flags out of
    `given_again`: the command runs as argparse parsed it, and arm `aaaaaaa`
    is red.

    It is also where `--help` gets its help line. argparse is told
    `add_help=False`, its documented way of adding no `-h, --help` of its
    own, and `__init__` adds the flag itself with `action="help"` and
    `HELP_LINE`. `add_subparsers` constructs the subcommands' parsers as this
    class, so each of them runs the same `__init__` and prints the same
    line. A caller that passes `add_help=False` gets a parser with no
    `-h, --help`, as argparse would give it. No parser is named.

    A flag added with `path=True` names a path, and `paths` holds it. What
    comes out is `args.given_empty`: the flags of `paths` given an empty or
    white-space value, named by `named`, in the order the command line gave
    them. Such a value names no file and no directory: a test of truth reads
    the empty one as the flag left out, `os.path.abspath` reads it as the
    working directory, and the white-space one is a directory no listing
    shows. A positional added with `path=True` is held the same way — it is
    named by its metavar, behind its subcommand — and an absent one, `None`,
    is not an empty one. It is
    a fact and no verdict: `main` is what refuses, and no command tests a
    path flag for emptiness again. A repeatable flag (`action="append"`)
    added with `path=True` is held the same way, every value it was given.

    A flag added with `variable=True` names an environment variable, and
    `variables` holds it. What comes out is `args.given_empty_names`: the
    flags of `variables` given an empty or white-space value, named as
    above. Such a value names no variable: `probe --writes-env ""` read it as
    the flag left out and ran the probe it would have run without it.

    A flag added with `command=True` names a command, one element per value,
    and `commands` holds it. What comes out is `args.given_empty_commands`,
    named as above. Such a value names no program and no argument: only the
    first element names a program, and the rule that refuses a blank shell
    variable is the same for every element.
    """

    given: list[tuple[argparse.Action, Any]]
    paths: list[argparse.Action]
    variables: list[argparse.Action]
    commands: list[argparse.Action]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.given = []
        self.paths = []
        self.variables = []
        self.commands = []
        add_help = kwargs.pop("add_help", True)
        kwargs["add_help"] = False
        if sys.version_info >= (3, 14):
            # argparse colors from 3.14 on, under `FORCE_COLOR` even into a
            # file; the help is text a reader saves and compares.
            kwargs.setdefault("color", False)
        super().__init__(*args, **kwargs)
        if add_help:
            self.add_argument("-h", "--help", action="help",
                              default=argparse.SUPPRESS, help=HELP_LINE)

    def add_argument(self, *names: Any, path: bool = False,
                     variable: bool = False, command: bool = False,
                     **kwargs: Any) -> argparse.Action:
        action = super().add_argument(*names, **kwargs)
        if action.option_strings and kwargs.get("action") != "append":
            kind = type(action)
            action.__class__ = type(kind.__name__, (_Kept, kind), {})
        if path:
            self.paths.append(action)
        if variable:
            self.variables.append(action)
        if command:
            self.commands.append(action)
        return action

    def named(self, action: argparse.Action) -> str:
        """A flag as a sentence names it: its long name, behind the
        subcommand whose parser declares it — `compare --manifest`, and
        `--manifest` for the one declared before any subcommand."""
        long = next((name for name in action.option_strings
                     if name.startswith("--")),
                    action.option_strings[0] if action.option_strings
                    else str(action.metavar or action.dest))
        return f"{self.prog} {long}".removeprefix(PROG).strip()

    def parse_known_args(self, args: Any = None, namespace: Any = None
                         ) -> tuple[Any, list[str]]:
        self.given = []
        namespace, rest = super().parse_known_args(args, namespace)
        seen: dict[argparse.Action, list[Any]] = {}
        for action, values in self.given:
            seen.setdefault(action, []).append(values)
        # A subcommand's parser has finished by now and its own list is on
        # the namespace already; every flag it read came after this one's.
        namespace.given_again = [
            (self.named(action), len(values),
             tuple(values) if action.nargs != 0 else ())
            for action, values in seen.items() if len(values) > 1
        ] + getattr(namespace, "given_again", [])
        # A positional is given once, as the value it was parsed to; `None` is
        # the one left out.
        for action in self.paths + self.variables + self.commands:
            value = getattr(namespace, action.dest, None)
            if not action.option_strings and value is not None:
                seen[action] = [value]
            elif action.option_strings and isinstance(value, list):
                # A repeatable flag: `_Kept` was not put in front of it, so
                # `given_again` never counted it, and its values are the
                # list its action built.
                seen[action] = value

        def emptied(held: list[argparse.Action]) -> list[str]:
            return [self.named(action) for action, values in seen.items()
                    if action in held
                    and any(not str(v).strip() for v in values)]

        namespace.given_empty = emptied(self.paths) + getattr(
            namespace, "given_empty", [])
        namespace.given_empty_names = emptied(self.variables) + getattr(
            namespace, "given_empty_names", [])
        namespace.given_empty_commands = emptied(self.commands) + getattr(
            namespace, "given_empty_commands", [])
        return namespace, rest


def _subcommand(sub: argparse._SubParsersAction[_Parser],
                name: str, summary: str) -> _Parser:
    """One subcommand's parser, with the required `--manifest` when `name`
    is one of `MANIFEST_COMMANDS` — the one place the parser learns which
    commands read a manifest."""
    parser = sub.add_parser(name, help=summary)
    if name in MANIFEST_COMMANDS:
        parser.add_argument("--manifest", dest="manifest", required=True,
                            metavar="FILE", path=True,
                            help="the manifest to read")
    return parser


def directories_section() -> str:
    """The `directories:` block the bare `--help` ends with: where this
    install keeps what a reader goes looking for — the format documents and
    the manual, the worked example, the README that links them, the skill an
    agent copies, and the templates `init` writes from — alphabetically,
    each as the path `core.Layout` reads, in the checkout's own shape,
    `(not present)` after one the layout does not carry. A person running
    `--help` needs help, and no document can name these paths: they differ
    by installer and by interpreter, and `--help` is the one place every
    stranger looks."""
    layout = Layout.detect()
    rows = (("docs", "docs"), ("examples", "examples"),
            ("README", "README.md"), ("skill", SKILL_DIR),
            ("templates", "templates"))  # alphabetical, case ignored
    lines = ["directories:"]
    for label, name in rows:
        path = os.path.join(layout.data, name)
        lines.append(f"  {label:<10} {path}"
                     + ("" if os.path.exists(path) else "  (not present)"))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    # The raw formatter keeps the epilog's lines; the description is wrapped
    # here by hand where argparse wrapped it, so the help's text above the
    # new section is byte for byte what it was.
    parser = _Parser(
        prog=PROG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Capture and compare a subject's surfaces, as a manifest "
                    "and a census describe\nthem.",
        epilog=directories_section())
    parser.add_argument("--version", action="store_true",
                        help="print golden-census's version and exit")
    parser.add_argument("--selfcheck", action="store_true",
                        help="run the controls and exit; with --manifest the "
                             "census's own controls run too")
    parser.add_argument("--selftest", action="store_true",
                        help="check golden-census on its own bundled fixture "
                             "and print the version; takes no manifest")
    # `top_manifest`, not `manifest`: the four subcommands' own `--manifest`
    # shares a namespace with this one, and one name for both hid a
    # `--manifest` given before a subcommand, which the subcommand's then
    # overwrote or ignored.
    parser.add_argument("--manifest", dest="top_manifest", default=None,
                        metavar="FILE", path=True,
                        help="the manifest --selfcheck reads its census from")
    sub = parser.add_subparsers(dest="command")

    cap = _subcommand(sub, "capture", "record every row of a manifest")
    cap.add_argument("--out", dest="out_dir", required=True, metavar="DIR",
                     path=True, help="where the capture is written")
    cap.add_argument("--input", dest="inputs", action="append", default=[],
                     metavar="NAME",
                     help="restrict to this input (repeatable)")
    cap.add_argument("--force", action="store_true",
                     help="overwrite an --out directory that already holds a "
                          "capture; required to re-baseline a golden set")
    cap.add_argument("--twice", action="store_true",
                     help="record the whole set twice and refuse if the two "
                          "captures differ")

    cmp_ = _subcommand(sub, "compare", "compare a golden set")
    cmp_.add_argument("--golden", dest="golden", required=True, metavar="DIR",
                      path=True,
                      help="the recorded golden set the fresh capture is "
                           "compared with")
    cmp_.add_argument("--against", dest="against", default=None, metavar="DIR",
                      path=True,
                      help="compare against a recorded capture directory "
                           "instead of running the subject")
    cmp_.add_argument("--allow-diff", dest="allow", default=None,
                      metavar="FILE", path=True,
                      help="extra permitted movements, one `path :: "
                           "attribution` line per row, on top of the "
                           "manifest's [[movements]]")
    # `override`, not `command`: the subparsers' own dest is `command`.
    # `command=True` because an empty element is refused like an empty path,
    # by a sentence that names a command and not a path.
    cmp_.add_argument("--command", dest="override", action="append",
                      default=[], metavar="ARG", command=True,
                      help="run the fresh capture's rows with this argv in "
                           "place of the manifest's [subject] command, one "
                           "element per flag (repeatable); not with "
                           "--against")

    _subcommand(sub, "census", "read a census, run its controls, print its state")

    mut = _subcommand(sub, "mutants", "plant every mutant of a mutants file in a copy "
                                      "of the subject and print which checks caught it")
    mut.add_argument("--mutants", dest="mutants", required=True, metavar="FILE",
                     path=True,
                     help="the mutants file (docs/mutants-format.md)")
    mut.add_argument("--only", dest="only", action="append", default=[],
                     metavar="NAME",
                     help="restrict to this mutant by name (repeatable); the "
                          "null mutant runs either way")

    pro = _subcommand(sub, "probe", "run a candidate command twice and report the "
                                    "five contract clauses")
    pro.add_argument("--census", dest="census", default=None, metavar="FILE",
                     path=True,
                     help="the census whose environment the candidate runs "
                          "under; without it golden-census's built-in default")
    pro.add_argument("--writes-env", dest="writes_env", default=None,
                     metavar="NAME", variable=True,
                     help="export the output path as this variable instead of "
                          "substituting <WRITES> in the argv")
    # `nargs="*"`, not `REMAINDER`: argparse strips the `--` and hands the
    # candidate's own `--json` and `<WRITES>` through as positionals, which is
    # what a reader typing `probe -- mytool --json '<WRITES>'` means.
    # `REMAINDER` keeps the `--` in the list and would run it as an argument.
    # `probe_command`, not `command`: the subparsers' own dest is `command`,
    # and a positional of that name would overwrite the subcommand with the
    # candidate's argv in the same namespace.
    pro.add_argument("probe_command", nargs="*", metavar="command",
                     help="the candidate, after `--`; <WRITES> where its "
                          "output path goes (quote it — a shell reads the "
                          "angle brackets as a redirection)")

    ini = _subcommand(sub, "init", "write a project's manifest, census and mutants "
                                   "file from a template, holes in place")
    # `nargs="?"`, because `--list` takes no directory and a required
    # positional would make `init --list` an argparse usage error rather than
    # the refusal that says which of the two forms to use. `init_dir`, not
    # `dir`: the subparsers' own dest is `command`, and every other name in
    # this namespace is already spoken for by another subcommand.
    ini.add_argument("init_dir", nargs="?", metavar="dir", path=True,
                     help="the directory the project's files are written into; "
                          "it is made if it does not exist, and no file in it "
                          "is ever overwritten")
    ini.add_argument("--template", dest="template", default=None,
                     metavar="NAME",
                     help="the template to write; not with --list")
    ini.add_argument("--list", dest="list_templates", action="store_true",
                     help="name the shipped templates and write nothing; not "
                          "with --template")
    return parser


def controls_before(args: argparse.Namespace) -> tuple[bool, bool]:
    """Which controls precede one parsed command, as `(the census's controls
    run, the block prints its verdict alone)`.

    golden-census's own arms are regression tests of code that does not move
    between one command of a reader's and the next, so they run where a reader
    asks for them — `--selfcheck`, `--selftest` — and in front of nothing else.
    The census's controls are about the reader's own subject, so they run in
    front of every command that turns that subject into a golden or a verdict,
    printing their verdict and standing aside, and a red one stops the command.

    `capture` and `mutants` make goldens and verdicts. `compare` does too when
    it captures; with `--against` it reads two recorded directories, starts no
    subject, and has nothing for a census to be about. `probe` and `init` are
    asked before a census exists. `census` is the command whose whole job IS
    the census, so its controls are what was asked for and print as a block.
    """
    if args.command == "census":
        return True, False
    if args.command in ("capture", "mutants"):
        return True, True
    return args.command == "compare" and args.against is None, True


def needs_temp_root(args: argparse.Namespace) -> bool:
    """Whether one parsed command makes a directory under the temp root, so
    that `core.require_temp_root` refuses it, before anything runs, when no
    directory can be made there or when TMPDIR is relative or spelled with `..`.

    Every command does but two, which run under any TMPDIR. `init` writes
    only into the directory it is given. `compare --against` reads two
    recorded directories and starts nothing; `compare.compare` owns that
    fact — its `if against is not None` branch opens no `workspace` — and
    `controls_before` restates it for the census's controls, as this does
    for the temp root. Self-check arm `uuuuuu` runs every command under a
    root with nothing there — `--selftest` and `--selfcheck` in their
    `--manifest` forms — so a drift between this and what the commands do
    turns that row red. `--version`, `--help`, the bare invocation and a
    refused flag never ask: `main` has returned before `anchored`.
    """
    return not (args.command == "init"
                or (args.command == "compare" and args.against is not None))


def run_census(manifest: Manifest, out: Any) -> None:
    """The `census` command: the census as golden-census reads it, its
    preconditions and its state — everything a capture does around the runs,
    without the runs.

    Its controls are printed above this block by `main`, which decides for
    every command which controls precede it; that decision is not made twice.
    """
    census = manifest.census
    out.write(own_log(f"census {census.path}\n", census,
                      manifest.subject.root))
    for row in census.rows:
        out.write(f"  {row.disposition:<13} {row.name}\n")
    for note in census.notes:
        out.write(f"  note: {note}\n")

    def wide_root_note(normalized: str, width: int) -> None:
        """The ONE stated exception to `core.workspace`'s width rule: this
        command runs no subject, and its state block is what the reader came
        for, so a temp root too wide for the pin is a note rather than a
        refusal."""
        out.write(f"  note: this machine's temp root {normalized!r} is "
                  f"{len(normalized)} characters, too wide for the pinned "
                  f"{width}; the `census state` block below reads TMPDIR as unset "
                  "and a capture here would REFUSE.\n")

    with workspace(census, "golden-census-census-", manifest.subject.root,
                   out=out, note=wide_root_note) as roots:
        preconditions(census, roots, out)
        state(census, roots, build_env(census, roots), out)


def _unhanded(flag: str) -> Refusal:
    """The refusal of a call of `main` given `flag` and handed no runner for
    it.

    Unreachable from this version's command line: its console script and
    `python3 -m golden_census` both call `console.main`, which hands `main`
    both runners. A console script an older install wrote still calls
    `cli.main` directly — an editable install brought forward by `git pull`
    keeps the script it was installed with — and reaches it. Stated as a
    refusal rather than asserted, because a call of `main` handed none is a
    precondition that does not hold, and that is one sentence, never a
    traceback.
    """
    return Refusal(f"`{flag}` was given to a call of `cli.main` that was "
                   "handed no runner for it.",
                   next="The command's entry point is `golden_census.console:"
                        "main`, which hands `cli.main` the runners of "
                        "`--selfcheck` and `--selftest`; a console script "
                        "that still calls `cli.main` was written by an older "
                        "install, so reinstall golden-census or run `python3 "
                        f"-m {IMPORT_NAME}`.")


def main(argv: list[str] | None = None, run_selfcheck: bool = True, *,
         selfcheck: Callable[..., int] | None = None,
         selftest: Callable[..., int] | None = None) -> int:
    """One command, start to finish.

    `main` is the ONE decider of which controls precede which command: they
    run here, after the manifest is read and before anything is dispatched, so
    no command decides it again and no command's first log line can precede
    them. `controls_before` above is the whole of that decision.
    `run_selfcheck` is off for the measurement of the priced commands only
    (`docs.measure`); nothing on the command line reaches it.

    It is also the one place that says a block is QUIET — a reader who typed
    `capture` asked for a capture, not for a block — and that decision is a
    single value on the call below, so the blocks a reader CAN ask for by name
    print exactly what they did before.

    It decides a second sentence for the same reason: which forms LAUNCH
    anything. Everything but `--version`, `--help` and a flag refused ahead of
    the dispatch does, so everything but those opens the run's process group,
    prints the line that kills it, and sweeps it on the way out — decided
    here, above the dispatch, so no command's first log line can precede the
    line saying what to kill.

    `selfcheck` and `selftest` are what the two whole-program flags run,
    called here, inside the run's group and under the same handlers as every
    other command. This module imports neither self-test module, because
    both import this one; `console.main` hands both, an arm hands a
    stand-in, and a call handed none for the flag it was given is refused
    (`_unhanded`).
    """
    stream = sys.stdout
    # UTF-8 on both streams, whatever `PYTHONIOENCODING` or the locale says:
    # nearly every line holds a dash an ASCII stream cannot encode, and a
    # diff quotes the subject's own bytes, so an encoding taken from the
    # environment makes the first such write a traceback. BEFORE `usable`,
    # whose probe is a write: an encoding that opens with a byte-order mark
    # writes the mark on the first write, a zero-length one included.
    # `surrogateescape` on standard output, because naming an encoding resets
    # the error handler to `strict`: an argument holding a byte that is not
    # UTF-8 is written back as that byte, as UTF-8 mode writes it. Standard
    # error keeps the handler it has.
    # Line-buffered, because the documents tell a caller to send this output
    # to a FILE and read it while a run is stuck: a file is block-buffered,
    # and a hung run's log would otherwise be EMPTY — no process-group line,
    # no rows — until the buffer filled or the process ended. Measured: 0
    # bytes after 60 s of a hung probe.
    in_utf8(stream, errors="surrogateescape", line_buffering=True)
    in_utf8(sys.stderr)
    if not usable(stream):
        # Before argparse, not after: `--help` and argparse's own usage go to
        # stdout as well, so an unusable fd 1 has to be caught ahead of
        # parsing. Every command here writes its verdict — capture progress,
        # the self-check rows, every diff — to stdout, and a run whose verdict
        # goes nowhere is not a run.
        refuse_on_stderr(Refusal(
            f"standard output is unusable (closed, as with `>&-`). "
            f"{WHOLE_VERDICT} and does not run blind.",
            next="Re-run without closing standard output: drop the `>&-`, or redirect to a file."))
        return EXIT_REFUSED
    # The second way standard output becomes unusable: a write to it fails
    # under the run — a reader such as `head` stopped reading, a descriptor
    # open for reading only, a full disk. Every write of the body goes
    # through `out`, which keeps the `OSError` it raised, and the handler
    # around the whole body, `anchored`'s sweep included — it runs first, on
    # the way out of the `with` — answers that error and no other. fd 1 is
    # pointed at the null device before the refusal, so the interpreter's own
    # flush at exit has nowhere to fail.
    out = _Stdout(stream)
    helping = False
    try:
        try:
            # argparse writes `--help` to `sys.stdout` itself; redirected, it
            # writes through `out`, which keeps the error a write raised.
            with contextlib.redirect_stdout(out):
                args = build_parser().parse_args(argv)
        except SystemExit:
            # argparse prints `--help` — the one thing it writes to standard
            # output; its usage errors go to stderr — and swallows any
            # `OSError` of the write. `out` recorded it. A buffered stream
            # meets the error again at the flush; an unbuffered one does not
            # (`PYTHONUNBUFFERED`, `-u`), so `main` asks `out`, not the flush:
            # raised here, the handler below answers it, and the interpreter's
            # own flush at exit, which ends at 120, never meets it.
            helping = True
            out.flush()
            if out.refused is not None:
                raise out.refused from None
            raise
        try:
            # A flag given more than once, FIRST: every refusal below reads a
            # value of `args`, and argparse kept only the last one a repeated
            # flag was given. `_Parser` owns which flags repeat.
            again = [f"`{flag}` was given {times} times"
                     + (f" ({', '.join(map(repr, values))})" if values else "")
                     for flag, times, values in args.given_again]
            if again:
                each = len(again) > 1
                raise Refusal(
                    f"{' and '.join(again)}, and golden-census takes "
                    f"{'each' if each else 'it'} once.",
                    next="Give "
                    + " and ".join(f"`{flag}`" for flag, _, _ in args.given_again)
                    + f" once{' each' if each else ''}.")
            # A path flag given an empty or white-space value, SECOND: every
            # command below
            # reads a path flag as given when it is not None, and `_Parser`
            # owns which flags name a path.
            # The same rule for a flag that names an environment variable:
            # one sentence per kind, one `next:` beside them.
            said: list[str] = []
            then: list[str] = []
            for given, reads, names, gives in (
                    (args.given_empty, "a path", "no file and no directory",
                     "a path"),
                    (args.given_empty_names, "an environment variable's name",
                     "no variable", "a variable name"),
                    (args.given_empty_commands, "a command",
                     "no program and no argument",
                     "the program and its arguments, none of them empty")):
                if given:
                    each = len(given) > 1
                    flags = " and ".join(f"`{flag}`" for flag in given)
                    said.append(
                        f"{flags} {'were' if each else 'was'} given an empty "
                        f"or white-space value, and golden-census reads "
                        f"{reads} from {'each' if each else 'it'}: such a "
                        f"value names {names}.")
                    then.append(f"Give {flags} {gives}"
                                f"{' each' if each else ''}.")
            if said:
                raise Refusal(" ".join(said), next=" ".join(then))
            # The forms that launch NOTHING, together and first: they start no
            # process group and print no line naming one, because a kill command
            # for an empty group is a line that can only mislead. `--help` and an
            # argparse usage error never reach here at all — argparse exits inside
            # `parse_args`.
            # A flag golden-census would not act on is REFUSED, naming it, and
            # before `anchored` — `--version` beside anything else, a
            # whole-program flag beside a subcommand or beside the other one,
            # a `--manifest` before one.
            given = [f"`{name}`" for name, on in (("--selfcheck", args.selfcheck),
                                                  ("--selftest", args.selftest),
                                                  ("--manifest",
                                                   args.top_manifest is not None),
                                                  (args.command, args.command))
                     if on]
            if args.version and given:
                raise Refusal(
                    "`--version` prints the version and takes nothing else "
                    f"(given beside it: {', '.join(given)}).",
                    next="Run `--version` alone, or the rest without it.")
            if args.version:
                out.write(f"{PROG} {__version__}\n")
                return EXIT_OK
            # A flag golden-census would not act on is REFUSED, naming it, and
            # before `anchored`, so the refusal opens no group and prints the
            # same bytes on every run. Dropped instead, `--selftest census`
            # exited 0 over a self-test that never ran.
            for flag, on in (("--selftest", args.selftest),
                             ("--selfcheck", args.selfcheck)):
                if on and args.command is not None:
                    raise Refusal(
                        f"`{flag}` is a command of its own and takes no "
                        f"subcommand (`{args.command}` was given).",
                        next=f"Run `{flag}` alone, or the subcommand alone.")
            # The two whole-program flags beside each other, in either order.
            # Dropped instead, `--selfcheck` beside `--selftest` exited 0 over
            # a self-test and no word about the flag that was not acted on.
            if args.selftest and args.selfcheck:
                raise Refusal(
                    "`--selftest` and `--selfcheck` cannot be combined: each "
                    "is a command of its own, and both were given.",
                    next="Run `--selftest` alone, or `--selfcheck` alone.")
            if (args.command is not None and args.top_manifest is not None
                    and getattr(args, "manifest", None) is not None):
                raise Refusal(
                    f"`--manifest` was given twice, before `{args.command}` and "
                    "after it, and golden-census would read only one of them.",
                    next=f"Keep the one after `{args.command}` and drop the other.")
            if args.command is not None and args.top_manifest is not None:
                raise Refusal(
                    f"`--manifest` was given before the subcommand `{args.command}`, "
                    "where golden-census reads no manifest: a command's manifest "
                    "is named after the command.",
                    next=f"Move --manifest after `{args.command}` if it reads one — "
                    f"{_READS_A_MANIFEST} — or drop it.")
            if getattr(args, "override", []) and args.against is not None:
                raise Refusal(
                    "`compare --command` names the command the fresh capture "
                    "runs, and `--against` runs nothing: it reads two "
                    "recorded directories, so there is no command to replace.",
                    next="Drop `--command` to compare the two directories, or "
                    "drop `--against` to compare a fresh capture run with "
                    "that command.")
            if args.command is None and not args.selftest and not args.selfcheck:
                if args.top_manifest is not None:
                    raise Refusal(
                        "`--manifest` names the manifest a command reads, and no "
                        "command was given.",
                        next=f"Put it after one of the commands that read one: "
                        f"{_READS_A_MANIFEST}.")
                helping = True
                build_parser().print_help(out)
                return EXIT_REFUSED
            # ONE `with` and not one sweep per exit: every return below, every
            # `Refusal` raised through it and every signal caught under it leaves
            # through the same place, and the sweep is that place. The group is
            # started and named BEFORE the manifest is read and before the
            # self-check, so the first line of the command's own output is the
            # line that says what to kill — a line printed after the hang is a
            # line nobody gets.
            with anchored(out):
                # The temp root FIRST, inside the group and ahead of the
                # self-check, the manifest load and the census's controls:
                # it is a fact about the machine, and every one of those
                # makes a directory under it.
                if needs_temp_root(args):
                    require_temp_root()
                if args.command is None:
                    if args.selftest:
                        if args.top_manifest is not None:
                            raise Refusal(
                                "--selftest checks golden-census on its own "
                                "bundled fixture and reads no other manifest.",
                                next="Drop --manifest to run the self-test, or "
                                "use `--selfcheck --manifest M` to run that "
                                "census's own controls.")
                        if selftest is None:
                            raise _unhanded("--selftest")
                        return selftest(out)
                    if args.selfcheck:
                        # A name of its own: the bare `--selfcheck` reads an OPTIONAL
                        # manifest, while the dispatch below reads the COMMAND's; one
                        # variable for both would make the second look like the first.
                        optional = (load_manifest(args.top_manifest)
                                    if args.top_manifest is not None
                                    else None)
                        if selfcheck is None:
                            raise _unhanded("--selfcheck")
                        return selfcheck(out, optional)
                # The load sits UNDER the dispatch and ABOVE the one call below.
                # `probe` runs before a manifest exists — that is what it is for — so
                # "which file does this command read" is the command's own question,
                # while "which controls precede this command" is decided exactly
                # here, once, for all of them (self-check arm ii walks the source and
                # proves it).
                manifest = (load_manifest(args.manifest)
                            if args.command in MANIFEST_COMMANDS else None)
                # The override replaces the loaded manifest's command, here and
                # not in `compare`: the census's controls run the subject too,
                # and they run the command the fresh capture will run.
                if manifest is not None and getattr(args, "override", []):
                    manifest = manifest.with_command(tuple(args.override))
                probe_census = (load_census(args.census)
                                if args.command == "probe" and args.census is not None
                                else None)
                # Every path the command is handed is read HERE by its one
                # owner: under the manifest's load and above the census's
                # controls, which start the subject, so a path the owner
                # refuses costs no run of it. In the order the parser declares
                # the flags: `--golden`, `--against`, `--allow-diff`; `--out`
                # after the `--input` names its guard reads; `--mutants`.
                # What `guard_capture` returns is what the command is
                # handed. `--golden`, `--against` and `--allow-diff`
                # are read here to be refused, and read again
                # where the command reads them, below the controls: a verdict
                # is of the golden and the table as they stand once the
                # census's controls have run, not of a copy
                # taken before the subject ran. The mutants file is read
                # here once and its object handed on: the controls cannot
                # change it, and the mutants are what the file said here.
                if args.command == "compare":
                    read_sides(os.path.abspath(args.golden),
                               os.path.abspath(args.against)
                               if args.against is not None else None)
                # The `--allow-diff` table is asked of the namespace and not
                # of a command's name, so a command whose parser declares the
                # flag is read for from the commit that declares it; a
                # command with no such flag has no table, and `read_allow`
                # reads no file for `None`.
                read_allow(getattr(args, "allow", None))
                guarded = (guard_capture(manifest, os.path.abspath(args.out_dir),
                                         tuple(args.inputs), args.force)
                           if args.command == "capture" and manifest is not None
                           else None)
                planted = chosen = None
                if args.command == "mutants" and manifest is not None:
                    # Loaded here to be refused, as the paths above are, and
                    # loaded once: `run_mutants` is handed this object. The
                    # `--only` check and the stale-mutant check sit here too:
                    # both read files and run nothing, so a reader does not
                    # pay the controls' time to learn of a typo or a stale
                    # mutant.
                    planted = load_mutants(args.mutants)
                    chosen = chosen_and_checked(manifest, planted,
                                                tuple(args.only))
                # QUIET in front of a command the reader typed, so the block prints
                # its verdict and stands aside — the tally, every disclosed SKIP,
                # and the failing rows when there are any. LOUD for `census`, and
                # absent altogether where the command starts no subject.
                runs, quiet = controls_before(args)
                code = (census_check(out, manifest, quiet)
                        if run_selfcheck and runs and manifest is not None
                        else EXIT_OK)
                if code and args.command != "census":
                    # `census` is the one command that prints its state block
                    # anyway, and it is stated here rather than left to
                    # `run_census` to decide by omission: a reader whose census
                    # control has gone red wants the environment that census
                    # describes, which is exactly what the block below it is.
                    # Everything else stops — and the sentence below sends them
                    # there, so the reader is told and not only the code. The
                    # block holds the environment as the subject would see it,
                    # the preconditions, and the version of every tool the
                    # census names, which is why it usually names the cause of
                    # a red control. `--selfcheck --manifest M` also runs the
                    # same controls, with golden-census's own arms beside
                    # them; the help text says so.
                    # The README's command table and the skill say it too.
                    raise Refusal(
                        f"golden-census does not run `{args.command}` when a control "
                        "of this manifest's census did not pass: the rows above are "
                        "every control that ran, and nothing of the command below "
                        "them was started.",
                        next="Fix the census row each FAILED control above names; "
                        "`census --manifest M` prints the `census state` block "
                        "that usually names the cause.")
                if args.command == "probe":
                    return probe(list(args.probe_command), out, probe_census,
                                 args.writes_env)
                if args.command == "init":
                    return init(args.init_dir, args.template, args.list_templates, out)
                if manifest is None:
                    # Unreachable by the parser: every subcommand that reaches here is
                    # one of `MANIFEST_COMMANDS`, which make --manifest required, so the
                    # load above read one. Stated as a refusal rather than asserted,
                    # because a tool that cannot meet a precondition says so in a
                    # sentence and does not crash — and a checker that cannot see
                    # argparse's constraint is right to ask what happens here.
                    raise Refusal(
                        f"`{args.command}` reads a manifest and none was loaded.",
                        next="Pass --manifest M naming the manifest this subject is "
                             "described by.")
                if args.command == "capture":
                    return capture(manifest, os.path.abspath(args.out_dir), out,
                                   tuple(args.inputs), args.force, args.twice,
                                   landed_note=True, guarded=guarded)
                if args.command == "census":
                    run_census(manifest, out)
                    return code
                if planted is not None:
                    return run_mutants(manifest, planted, out,
                                       tuple(args.only), chosen=chosen)
                return compare(manifest, os.path.abspath(args.golden),
                               os.path.abspath(args.against)
                               if args.against is not None else None,
                               read_allow(args.allow), out,
                               tuple(args.override))
        except Refusal as refusal:
            out.write(refusal_text(refusal) + "\n")
            return EXIT_REFUSED
        except OSError as error:
            # An `OSError` no site answered — a disk that filled, a directory
            # removed under the run — is one sentence too, printed after
            # `anchored`'s sweep as every refusal is. Where it was standard
            # output's own, this write fails as well and the handler below
            # answers that.
            out.write(refusal_text(_unanswered(error)) + "\n")
            return EXIT_REFUSED
        finally:
            # A write whose `OSError` a callee swallowed — argparse's
            # `print_help`, `capture._say` — left its text in the buffer:
            # flushed here, it fails again and reaches the handler below.
            # An exception already leaving the body is left to leave as it
            # was raised: fd 1 is pointed at the null device instead.
            leaving, refused = sys.exc_info()[1], out.refused
            try:
                out.flush()
            except OSError:
                if leaving is None or leaving is refused:
                    raise
                to_null(1)
    except OSError as error:
        if error is not out.refused:
            raise
        return _output_lost(error, helping)


class _Stdout:
    """Standard output as `main` hands it to every command: each write and
    flush is the stream's own, and an `OSError` either raises is kept in
    `refused` before it goes on, so `main` tells a write that failed
    (`_output_lost`) from any other `OSError` (`_unanswered`)."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.refused: OSError | None = None

    def write(self, text: str) -> int:
        try:
            return self.stream.write(text)
        except OSError as error:
            self.refused = error
            raise

    def flush(self) -> None:
        try:
            self.stream.flush()
        except OSError as error:
            self.refused = error
            raise

    def fileno(self) -> int:
        return self.stream.fileno()


def _unanswered(error: OSError) -> Refusal:
    """The refusal of an `OSError` that no site of the package answered and
    that is not standard output's own: `main` prints it for every command,
    after the run's group is swept. It quotes the error as Python states it
    — its class, the operating system's words and the path when the error
    carries one — and says nothing the error does not."""
    return Refusal(
        f"{PROG} stopped on an operating-system error that none of its own "
        f"checks answers — {type(error).__name__}: {error} — and the command "
        "did not finish, so what it printed above is not a whole verdict.",
        next="Fix what the error names, then run the command again; if it "
        f"names nothing you can fix, report it as a {PROG} defect, quoting "
        "this line.")


def _output_lost(error: OSError, helping: bool = False) -> int:
    """The refusal for a standard output that stopped taking what `main`
    writes: `main`'s handler of the `OSError` a write to it raised returns
    it, around its whole body.

    A `BrokenPipeError` says standard output closed: its reader is gone.
    Any other `OSError` — a descriptor open for reading only, a full disk —
    says standard output refused a write and quotes the operating system's
    words, which are all that was measured of why. `helping` says the help
    was being written: it has no verdict, and nothing was taken back.

    fd 1 is pointed at the null device first, so the interpreter's own flush
    at exit has nowhere to fail.
    """
    to_null(1)
    if isinstance(error, BrokenPipeError):
        how, why, where = "closed", " (a reader such as `head` stopped reading)", "a file"
    else:
        how, why, where = f"refused a write ({error})", "", "a file that can be written,"
    if helping:
        what, after, whole = "its help", ".", f"{PROG} writes its whole help to standard output"
    else:
        what, after, whole = ("its verdict", "; a command that had not finished took "
                              "back what it wrote.", WHOLE_VERDICT)
    lost = Refusal(f"standard output {how} while {PROG} was still writing {what}{why}, "
                   f"so the rest of it is missing or cut short{after}",
                   next=f"Send the output to {where} and read the file: {whole}.")
    # `2>&1 | head` closed stderr with it: the refusal has nowhere to go,
    # and fd 2 is pointed at the null device too, so the interpreter's
    # flush at exit cannot fail and turn exit 2 into 120.
    if not refuse_on_stderr(lost):
        to_null(2)
    return EXIT_REFUSED


# Run as a script — `python3 -m golden_census.cli …` — this module would run
# its body, print nothing and exit 0. It cannot run the command: `main` takes
# the runners of `--selfcheck` and `--selftest` from `console`, and an import
# of `console` here would make the cycle `console`'s docstring keeps out. So
# it refuses, in one sentence naming the command that runs.
if __name__ == "__main__":
    in_utf8(sys.stdout)
    sys.stdout.write(refusal_text(Refusal(
        f"{IMPORT_NAME}.cli is the module that reads {PROG}'s command line, "
        "not the command, so it ran nothing.",
        next=f"Run `python3 -m {IMPORT_NAME}` with the same arguments.")) + "\n")
    raise SystemExit(EXIT_REFUSED)
