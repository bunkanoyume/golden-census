---
name: golden-census-skill
description: Prove that a code change altered nothing observable. golden-census records a program's stdout, stderr, exit codes and written files as goldens, normalizes away the machine, and compares byte for byte after a change. Use it before and after a refactor, when a surface is added, when a golden moved and the movement must be attributed, and to test whether existing checks catch a planted change (mutants). Language-neutral: it drives any program by subprocess and never imports it.
---

# golden-census — prove a change altered nothing observable

## Run it

Run `golden-census --version` first. It confirms that golden-census is installed and runs from any directory, and it prints `golden-census 1.0.0`, the version this skill documents. If it does not run, or the version differs, report that and trust the program's own `--help` and refusals over this skill.

When `golden-census` is not on PATH, run a checkout's launcher instead: `<checkout>/bin/golden-census` is the same command from any directory, and so is `python3 -m golden_census` from the checkout root under a Python of 3.11 or later. Spell every command below the way you ran this one.

Set `TMPDIR` before any command that runs the subject. It must be an absolute path of at most 49 characters when the census pins the width the template does, 51; a wider root is refused, and the refusal's `next:` names a root that fits: `/tmp` on Linux, `$(getconf DARWIN_USER_TEMP_DIR)` on macOS. A Claude Code session's default temp root is wider. `references/machine.md`, "The temp root", has the rules.

After an install or an upgrade, run `golden-census --selftest`; it takes minutes. Whenever a result surprises you, run `golden-census --selfcheck`; it is the quick one. `--selfcheck` prints `N/N passed, K arm(s) SKIPPED (disclosed, never a pass)` and exits 0 when every arm passed. `--selftest` prints one such tally per group and ends with the version line. Those are golden-census's own arms, each beside the planted case that proves it can go red. They run only under those two flags, never as part of your commands. Your census's tally has the same shape, and in front of `capture`, `compare` and `mutants` it names its rows: `N/N census controls passed`. A red arm: see "When an arm of golden-census's OWN is red" below.

Four path placeholders are defined below. Substitute absolute paths. `<DIR>`, `<NAME>`, `<SCRATCH>` and `<the command>` are yours to fill too, and so is every token written in words, such as `<interpreter>` or `<path>`. Every other angle-bracket token is golden-census's own. In a command line or a manifest row, such as `<WRITES>` and `<HERE>`, type it as it stands. In a line the tool prints, such as `<REPO>` and `<TMPROOT>`, it is the fold of a machine path. Never type one into a manifest; the census types each once, as a fold's `placeholder`. "Reading the verdict" lists them. `<CLONE>` and `<PYTHON>` are both typed and printed.

```
<MANIFEST> = the consumer's manifest.toml
<GOLDEN>   = the committed golden directory
<MUTANTS>  = the consumer's mutants.toml
<CENSUS>   = the consumer's census.toml
```

Every command finds the census through the manifest; `census` itself takes `--manifest`. `<CENSUS>` is typed in one place, `probe --census`.

## What it answers, and what it never answers

It answers one question: **did any recorded surface of this program move?** A surface is one thing the program produces, named by a `[surfaces.<name>]` row of the manifest. A row of the golden is one input crossed with one surface. golden-census records the stdout, stderr, exit code and written file of one run. It normalizes them. Everything about the machine is folded away. Everything about the program stays a byte comparison.

It never answers these.

- Whether the behavior is CORRECT. A golden records a bug as faithfully as a feature. `IDENTICAL` means unchanged, never right.
- What a difference MEANS. It gives you the row, the line and the diff. The attribution is yours to write.
- Whether your test suite is adequate. `mutants` asks a narrower question: can the checks you already have catch a planted change?
- Anything about source code. It never imports the subject and never reads a table out of it by name. If a fact is not in the manifest, the census or the bytes the subject wrote, golden-census does not have it.

## Which command, when

| You are about to | Run | It is done when |
|---|---|---|
| touch a surface: refactor, rename, restructure | `compare` against the committed golden; `capture` one first if there is none | `IDENTICAL`, exit 0 |
| hand back a refactor | `compare`, or `compare --against` a capture taken after the change (step 8) | `IDENTICAL`, exit 0 |
| add a surface: a flag, an export, a refusal | write its `[surfaces.<name>]` row, then `capture --force`, and commit the new golden in the same commit | the new row is in the golden and `compare` is `IDENTICAL` |
| write a manifest for the first time | the eight steps below: `init`, `probe`, `census`, then `capture --twice` | `--twice: N files, byte-identical` |
| find out whether the checks catch anything | `mutants` | `N/N mutants caught`, exit 0 |
| find out whether a command can be a subject, before the first `capture` | `probe -- <the command>` | five `[PASS]` rows and `5/5 passed`, exit 0; for `swift-package`, clause 4 red (`references/templates.md`) |
| doubt golden-census itself | `--selfcheck`; after an install or an upgrade, `--selftest` | every arm PASS or a disclosed SKIP; `--selftest` takes minutes, not seconds |
| find out why a census control went red | `census --manifest <MANIFEST>` | see "When a control of YOUR census is red" below |

The exact invocations. This block spells every subcommand and every flag.

```
golden-census capture --manifest <MANIFEST> --out /tmp/before
golden-census capture --manifest <MANIFEST> --out /tmp/before --twice
golden-census capture --manifest <MANIFEST> --out <GOLDEN> --force
golden-census capture --manifest <MANIFEST> --out /tmp/one --input demo
golden-census compare --manifest <MANIFEST> --golden <GOLDEN>
golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --against /tmp/after
golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --allow-diff /tmp/moved.txt
golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --command <PYTHON> --command <HERE>/runner.py
golden-census census --manifest <MANIFEST>
golden-census mutants --manifest <MANIFEST> --mutants <MUTANTS>
golden-census mutants --manifest <MANIFEST> --mutants <MUTANTS> --only "lost role"
golden-census probe -- mytool --json '<WRITES>'
golden-census probe --census <CENSUS> -- mytool --json '<WRITES>'
golden-census probe --writes-env OUT_PATH -- mytool --json
golden-census probe -- sh -c 'mytool --json > "$1"' _ '<WRITES>'
golden-census init <DIR>
golden-census init <DIR> --template <NAME>
golden-census init --list
golden-census --selfcheck
golden-census --selfcheck --manifest <MANIFEST>
golden-census --selftest
golden-census --version
golden-census --help
```

Redirect every command to a file: `golden-census compare … > run.log 2>&1`. Read the log as UTF-8. A run that hangs or crashes leaves its partial output in the file, where you can read it; on a pipe it is out of reach until the run ends. `references/commands.md` has the flag table and the rules every flag follows.

## Plugging a project in, in order

Eight steps. Each ends with the command and the line that proves it done. Run them in this order.

1. **Choose the function.** This step is a rule, not a command. A program that is already a command is its own candidate, and the rule below is all that step 1 asks of it. A candidate is a function whose inputs you can save to a file. Its value must be one a JSON encoder can write. Nothing else may reach its output: no clock, no random source, no network, no unordered collection. Step 5 is the proof. Under `--twice`, the line `two captures of one subject differ: <path> line N` names what the function read for itself.
2. **`init`.** Run `golden-census init <DIR> --template <NAME>`. `golden-census init --list` names the templates. A program that runs from a command line: run `golden-census init <DIR>` alone; it needs no runner. A library in a language with no template: the same, then write the runner yourself to the six steps in `references/templates.md`, "A language with no template". The last line of the output is the template's hole notice, and every hole above it is yours to fill.
   - A hole left in the runner is not refused. The capture records it as a failing row, a non-zero exit of the subject, and the capture itself exits 0. Fill the runner's holes next; step 3 probes it before the manifest's holes are filled.
   - `<DIR>` is the subject's checkout, or any directory whose manifest spells `root` from there. `init` creates it if it is absent and overwrites nothing.
   - `init` writes in two passes: the neutral three, then the template's runner and wrapper. It is all or nothing across both. A refusal, or a reader that stops reading its output, leaves no file behind; a directory `init` made on the way stays. A refusal's `next:` line says what to do.
   - The subject is ONE repository. Never `git init` a directory inside it. Step 7 says what that costs.
   - The `python-function` runner lands beside the manifest: spell it `<HERE>/runner.py`, where `<HERE>` is the manifest's own directory wherever the manifest sits. The Swift runners land in the literal `<<HOLE:TEST_TARGET_DIR>>/` directory and are moved; `references/templates.md` says where. A relative element of `[subject] command` resolves under `root`.
   - Open the template's README here: `references/templates.md` says where it is and which sections to read.
3. **`probe` — before the first `capture`.** The rule: probe the command before a capture records it. Then nothing false is ever recorded as a golden.
   - Run `golden-census probe -- <the command> '<WRITES>'`. It prints `  5/5 passed` and exits 0.
   - The command is the manifest's future `[subject] command`. For a script it is `<interpreter> <script>`. For a compiled tool it is the tool. For a template's runner, `references/templates.md` gives each template's probe line.
   - Quote `<WRITES>`. A shell reads the angle brackets as a redirection.
   - Run it from the directory where the command's relative paths resolve: `probe` runs the candidate in the current directory and has no `root`. For the `python-function` runner that is the manifest's directory, where `runner.py` is; for `swift test` it is the directory holding `Package.swift`, the manifest's `root`. From anywhere else a relative path resolves to the wrong place, and clause 1 fails because the path was wrong, not because the program is unfit.
   - Spell a Python interpreter by the path of the one running golden-census, so the banner folds it to `<PYTHON>`: `python3 -c 'import sys; print(sys.executable)'` with the `python3` that runs it, or `head -1 "$(command -v golden-census)"` for an installed command. A symbolic link to that interpreter, such as a package manager's `python3` link, is printed as typed, not folded.
   - For a template's runner: fill the runner's holes, probe it, then fill the manifest's holes (step 4). Running `census` before the runner's `probe` is harmless: only a hole in the manifest or the census gates it. A hole in a template's runner is refused by no command, and one in the mutants file by `mutants` alone.
   - A runner whose hole is filled wrong is a golden of the wrong function. Examples are the wrong `MODULE` and a `FUNCTION_CALL` that calls the wrong thing. golden-census records it as faithfully as a golden of the right one. `probe` on the runner catches that.
   - A program that only prints is still a subject. `probe` needs a file, so hand it a shell that writes one: `golden-census probe -- sh -c 'mytool --json > "$1"' _ '<WRITES>'`. The shell and its redirection are for the probe only. The manifest names the program itself, with no shell, and `capture --twice` (step 5) is its determinism proof once the manifest exists.
   - A tool that prints findings and exits non-zero keeps every clause. Clause 3 asks whether the two runs agree and a file was written, not whether the code is 0.
   - `references/templates.md` says what each template's `probe` prints. The `swift-package` runner is red at clause 4 on `swift test`'s own timestamps, even with `--census`; that file says why the red is expected, and step 5 is its proof instead. `references/verdicts.md` reads any other red block.
4. **Fill the holes.** Run `golden-census census --manifest <MANIFEST>`. It prints the census controls as a block with their tally, then `census <REPO>/…/census.toml`, the rows, the preconditions and the `census state` block. Exit 0. While a hole is open, it prints `REFUSED: the manifest … still carries the unfilled hole(s) <<HOLE:…>>` instead. The refusal names every hole left and the file it is in.
   - The manifest's own placeholders are `<ROOT>`, `<WORK>`, `<WRITES>` and `<PYTHON>`; `references/manifest.md` lists the rest. They are not holes: leave them as typed. `<REPO>`, `<TMPROOT>` and the other tokens in printed lines are folds, never typed into a manifest; "Reading the verdict" lists them.
   - A surface that prints a time needs the `TZ` pin as well as the clock pin; the template has both, commented. A fixed instant still renders in the machine's zone, and `--twice` cannot see a zone that does not change between its two runs.
   - A census made by `init` folds two of the four directories golden-census knows, `root` and `work`; the `clone` and `fixed-width-dir` fold rows sit commented in the file. A capture then prints one line under its header, `census note: no `path` fold names clone, fixed-width-dir. If a captured file prints one of those directories, the contraband scan refuses the capture.` `census` prints the same sentence as `note:` under its rows. It is a fact, not a finding. When a capture is refused for leaking one of those directories, the refusal names the `path` row to add: uncomment it.
   - A subject that is not a git checkout stops here: the neutral census's `git-checkout` precondition refuses it. Make the tree a repository, which step 7 needs anyway, or delete that row. A `precondition` row does not become a `state` row by changing one key: `state` takes `variables`, `commands` or both, and no other key, so the row is refused as a whole (`references/census.md`).
5. **`capture --twice`.** Run `golden-census capture --manifest <MANIFEST> --out <GOLDEN> --twice`. It prints `  --twice: N files, byte-identical` and exits 0.
   - Commit `<GOLDEN>` beside the manifest, the census and the mutants file. The golden IS the handoff. Step 7 reads the committed tree, and the mutants file's `GOLDEN` hole must name this same directory: `<HERE>/golden` when it sits beside that file.
   - `init` writes no `.gitignore`: a scratch capture goes in a scratch directory of yours, such as `/tmp/before`, never in the tree.
   - Run one golden-census command at a time against a subject. Change nothing under the subject, the golden directory or the temp root while it runs. `--selfcheck` and `--selftest` count: each makes directories under the temp root, so run them alone too.
   - `TMPDIR`, when set, is an absolute path of at most 49 characters; a wider one is refused once the manifest and the census are read, before any control or run starts. `references/machine.md` has the temp-root rules, the clone cache and the git settings. Open it on any refusal that names `TMPDIR`, `HOME` or a cache directory.
6. **`compare`.** Run `golden-census compare --manifest <MANIFEST> --golden <GOLDEN>`. It prints `  IDENTICAL` under `N golden files, N new files` and exits 0. That is a fresh capture. `--against <DIR>` compares a capture already recorded instead (step 8). `--command ARG`, one flag per element of an argv, runs the fresh capture with that argv in place of the manifest's `command`: use it to compare a built copy, a bundle say, with the golden the source recorded. The `COMPARE` block prints `command:` under `new:`, quote it with the verdict; `IDENTICAL` then says that argv printed what the golden recorded. It is refused with `--against`.
7. **One mutant.** Fill the mutants file's holes with one edit a check must catch; its `find` must match the committed text exactly once. Commit the subject and the golden; the mutants file is read where it is. Then run `golden-census mutants --manifest <MANIFEST> --mutants <MUTANTS>`. It prints `  1/1 mutants caught by every check they expect` and exits 0.
   - `mutants` clones the COMMITTED tree. An uncommitted edit of the subject is invisible to it. The golden is read where `golden` points: `<HERE>/golden` beside the mutants file as it stands, committed or not; a bare path inside the clone, so committed.
   - That tree must CONTAIN the subject. A repository `git init`-ed inside the subject's checkout clones only itself and carries nothing to mutate. The null mutant then comes back not SILENT, and that is the sign.
   - `references/mutants.md` has the mutant row, the rules for `file`, and the cwd rule of a `command` check. Its trap: a check that runs beside the mutants file imports the UNMUTATED package and stays SILENT on every mutant.
8. **Before every hand-back: `compare`.** Run step 6 again and quote what "Report hygiene" below lists. `compare --against` prints no tally and no contraband line; quote the ones from the `capture` that made the directory, with that command line. The COMPARE block says so itself, in a line under `new:`.
   - A `[DIFF]` row is the finding. Name it, quote its diff, then attribute it or fix it. Say whether it is the change you intended. Never re-baseline to make a comparison pass.
   - `--against <DIR>` only with a capture taken AFTER the change: `golden-census capture --manifest <MANIFEST> --out /tmp/after`, then `golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --against /tmp/after`. A capture taken before the change holds nothing you changed, and comparing the golden with it says `IDENTICAL` whatever you did.

## Reading the verdict

**Exit codes: 0 a pass or IDENTICAL, 1 a FAIL or differing rows, 2 REFUSED, 130 or 143 interrupted.**

Exit 1 is a statement about what the command measured: the subject under `compare`, your census under `census`, your checks under `mutants`, golden-census itself under `--selfcheck`. Exit 2 is a statement about the RUN: a path, a precondition, an unfilled hole, or a subject that would not hold still under `--twice`. No verdict was made. Never report a 2 as a failure of the code.

The tokens golden-census prints in place of a machine path. Never type one into a manifest.

- `<REPO>`: the subject root, in printed lines and in goldens.
- `<TMPROOT>` in a printed header line: the temp root, your own scratch directories under it included. `<TMPROOT>/golden-census-abcd/x` is a file in a work directory under it.
- `<TMPROOT>` inside a recorded golden: the whole work directory, the neutral census's `work` fold. `<TMPROOT>/x` in a `[DIFF]` and `<TMPROOT>/golden-census-abcd/x` in a header name the same file. A census may spell this `placeholder` as it likes.
- `<CLONE>`: both typed and printed. Typed in a manifest, it is substituted with a pinned input's clone directory; inside a golden it is the neutral census's `clone` fold of that directory.
- `<PYTHON>`: both typed and printed. Typed, it is the interpreter running golden-census; printed, in a `probe` banner, a `ran:` block or the `census state` block, it is the fold of that interpreter's path.
- `<CWD>`: the current directory, in a `probe` banner.
- `<HOME>`: the reader's home directory, in a refusal's environment block.
- `<ENGINE-TMPDIR>`: the fixed-width directory, the neutral census's `fixed-width-dir` fold, in goldens and in a refusal's block.
- `<TMPDIR>`: the probe's own fixed-width directory, in a `probe` banner.

The lines you meet most. Each was printed by a run on the shipped example, or on a copy of it with one planted change. A letter `N` stands for a number that moves with your project. Quote the numbers you saw.

| What you see | What it means | What to do |
|---|---|---|
| `  IDENTICAL` under `  N golden files, N new files` | Every recorded byte of every row matched. | Quote both lines, with the numbers you saw. |
| `  IDENTICAL (1 permitted movement)` | A row moved, and the manifest or the allow file attributes it. | Quote the `[ALLOWED]` lines too. A permitted movement is still a movement. |
| `  [ALLOWED] fixtures/results.json — fixed in review` | This row moved, and somebody wrote down why. | Check the attribution still describes what you did. |
| `  [DIFF]    fixtures/results.json (changed)`, then a unified diff | This row moved and nobody attributed it. | This is the finding. Name the row, quote the diff, then fix the change or attribute the movement. |
| `  [DIFF]    fixtures/results.json (only-in-golden)` | A surface stopped being produced, or something else left a file in the folder. | Read that surface's `.exit` and `.err` in a capture you kept: a plain `compare` removes its fresh capture when it ends, so take `capture --out /tmp/after` and `compare --against /tmp/after`, whose `new:` line names the directory; the capture log's `{surface}: exit N` line already shows the exit. If golden-census never wrote the file, delete it. |
| `  [DIFF]    fixtures/stray.out (only-in-new)` | A surface appeared with no golden, or something else left a file in the folder. | If you added the surface's row, re-baseline with `capture --force` and commit the golden with the row. If golden-census never wrote the file, delete it. |
| `  1 differing row(s)` | The count of `[DIFF]` rows. | Exit 1. |
| `REFUSED: --golden names … which is not a directory. …` | A precondition, a manifest key, a path or a contraband hit stopped the run. | Read the sentence. It names the key or the file to fix. Nothing was compared. |
| `  next: Each [DIFF] row above is a change nobody attributed. For an intended change, …` | The one sentence saying what to do. When every `[DIFF]` is a surface the manifest names and the golden does not record, it instead says to record them with `capture --force`. When every `[DIFF]` is a surface the golden records and the manifest no longer names, it says to stop recording them with `capture --force`. | Do that, or say in your report why you did not. Every refusal ends in one. |
| `  N/N census controls passed, K arm(s) SKIPPED (disclosed, never a pass)` | The tally of your census's controls, one row per pin and per fold, in front of `capture`, `compare` and `mutants`. Under `census` the block's tally reads `N/N passed`. | Quote it beside a clean verdict, with the numbers you saw. |
| `  census note: no `path` fold names clone, fixed-width-dir. …` | The census has no fold for one of the four directories golden-census knows (step 4). | A fact, not a finding. Nothing to fix until a capture is refused for leaking that directory; the refusal then names the row to uncomment. |
| `  [SKIP]    1 row(s) are a skip on both sides, so nothing ran to compare: fixtures/never` | A row was recorded as a skip in the golden and in the new capture. Nothing ran on either side. | `IDENTICAL` then says only that the two recorded reasons matched. Name each row in your report and say why it is skipped. |
| `  N/N mutants caught by every check they expect` | The `mutants` verdict. | `N/N` is the pass. Anything less names the mutant and the check. |
| `process group <PGID> — if this run hangs or crashes, stop everything it started with: kill -- -<PGID>` | The first line of nearly every command. | The one command that stops the run. "When a run is stuck or crashed" says when you may run it. |

`references/verdicts.md` has every other line the tool prints: the `[FAIL]` rows, the mutant table, the `probe` block and the capture log.

## Report hygiene

A zero result is not a clean result. `IDENTICAL` is worth nothing unless the comparator can go red, and a report that says only "IDENTICAL" is indistinguishable from a report of a comparison that never ran. Every number you report from this tool cites the invocation it came from. A run you did not make is not a verification. Quote these.

1. The command line, verbatim.
2. The verdict line: `IDENTICAL`, `N differing row(s)`, or `N/N mutants caught`.
3. The control beside the verdict, as the table below lists per command. In the log the tally opens and the verdict closes; quote them together. Quote the numbers you saw, never numbers from a document. A tally that says `REFUSED after row N` stopped there: the rows above it ran, and nothing below them was claimed.
4. Every disclosed `[SKIP]`, by name and reason. Every SKIP, in a block of controls and in a capture log alike, is a line that begins `[SKIP]`. A SKIP reported as a pass is worse than no check at all. A capture has two kinds, both findings to report: a surface declared unrunnable by its `skip` row, and a whole input whose pinned tree was unavailable, uncloned, cut short or dirtied, so nothing of it was captured.
5. For a run that never returned or died without a verdict: the `process group N — … kill -- -N` line it opened with and the command that produced it, as "When a run is stuck or crashed" says. Such a run has no verdict to quote, and reporting one anyway is the failure this list exists to prevent.
6. The manifest rows you added or changed, if any.

The tally is `N/N census controls passed, K arm(s) SKIPPED (disclosed, never a pass)`, one row per pin and per fold of YOUR census.

| Command | What it prints beside its verdict |
|---|---|
| `capture`, `compare` without `--against`, `mutants` | the tally, the contraband control line, the file counts |
| `census` | the controls as a block with the tally, then the rows and the `census state` block (step 4 gives the order) |
| `compare --against` | the verdict line, the file counts and the `  --against:` line saying the controls and the scan to quote are the capture's; nothing else |
| `probe` | its `N/5 passed` |
| `init`, `--version` | no verdict; quote what they printed |

## Procedures

**Before touching a surface.** Make sure there is a floor to compare against. With a committed golden, run `golden-census compare --manifest <MANIFEST> --golden <GOLDEN>` and get `IDENTICAL`: a `[DIFF]` before you changed anything is somebody else's movement, to attribute before you start. With no golden, capture one, `golden-census capture --manifest <MANIFEST> --out /tmp/before`, and step 8 then compares with `--golden /tmp/before`. If a command refuses, read the sentence and fix the named thing. A refactor with nothing to compare against is a refactor you cannot report on.

**When you re-baseline on purpose.**

1. Capture the new set into a scratch directory: `golden-census capture --manifest <MANIFEST> --out <SCRATCH> --twice`.
2. Compare it with the old golden: `golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --against <SCRATCH>`.
3. Check that it reports exactly the rows you meant to move and no others. Quote its row count. It is the new golden's positive control.
4. Replace the golden: `golden-census capture --manifest <MANIFEST> --out <GOLDEN> --force`.

**Which permit, when.** A `[[movements]]` row in the manifest permits a movement from now on, with its attribution: a version number, a date the project stamps on purpose. `--allow-diff` permits it for this one comparison: a change under review that the golden does not yet carry. A re-baseline makes the new bytes the golden. Nothing else makes a `[DIFF]` go away.

**When you add a surface.** First `compare` and get `IDENTICAL`, so that what follows absorbs the new row and nothing else. Write the `[surfaces.<name>]` row. Add it to the input that runs it. Run `capture --force` into the golden directory. Commit the manifest row and the golden together. A surface with no row is a surface nobody will notice moving. `references/manifest.md` has the rows to copy.

**When a capture will not reproduce.** `capture --twice` names the row and the first differing line. That line is a census row nobody has written. Pin the variable or fold the token, and give the row the control that proves it matters. A `state` row only records, for attribution later; it makes nothing reproduce. `references/census.md` has the rows to copy.

**When a run is stuck or crashed.** Its first line named the run's process group and the one command that stops everything the run started. Whether you may run that command is your environment's rule, not golden-census's. If you may, run only the line of the run you started and are still watching: a group id is reused once every member has died, so a line from an old log can name an unrelated tree. A subject that reads the terminal is refused, naming the read; the run does not hang on it. golden-census keeps no clock, and a build can be slow: a run that has not returned has not failed, so judge it as you judge any process you started. If you cannot tell a slow run from a stuck one, report it rather than kill it: a wait costs time, a kill costs the build tool's state and makes a working run look like a failure. Either way, quote the line in your report, say which command produced it and how long it had been silent.

**When the gate asks whether the checks work.** Run `mutants`. A `SILENT` where `expect` named a check is the finding. So is `(no check fired)`. Both are faults of the CHECKS. The fix is a better check, never a smaller `expect`.

**When a control of YOUR census is red.** The commands that make a golden or a verdict refuse: `REFUSED: golden-census does not run <command> when a control of this manifest's census did not pass`. Run `golden-census census --manifest <MANIFEST>`. Its output is step 4's: the controls, then the rows and the `census state` block. The red row and that block together are what you report. The fix is in the CENSUS. Point an `UNPROVEN` pin's control at a surface the variable does move, or rewrite the row as a `state` row: `name`, `disposition = "state"`, `variables = ["<the variable>"]`, `finding`, and no other key. That records the value and pins nothing. Correct a fold whose control folds nothing, or remove it. Never delete the row to make the command run.

**When an arm of golden-census's OWN is red.** Nothing of yours refuses, and a capture you need is still a capture you can take. A red arm says golden-census or this machine is broken. It says nothing about your subject. Report the arm's name and its detail line. Say that your other results were taken on a machine where it was red. Do not paraphrase it as a finding about the code under review.

## Open on demand

Read this file whole. Open a reference only for the step or the line in front of you.

| Open | When |
|---|---|
| `references/commands.md` | You need the rule of a flag, or a refusal names one. |
| `references/verdicts.md` | A line in the output is not in the table above, or a `probe` block is red. |
| `references/manifest.md` | You write or change a manifest row, or read a golden directory. |
| `references/census.md` | You write a census row, or a capture will not reproduce. |
| `references/mutants.md` | Step 7, or the gate asks whether the checks work. |
| `references/machine.md` | A refusal names the temp root, `HOME` or the cache directory; Linux; a pinned input. |
| `references/templates.md` | Step 2, or you choose a template. |
