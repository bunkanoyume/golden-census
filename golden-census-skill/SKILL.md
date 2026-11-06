---
name: golden-census-skill
description: "Record app goldens before and after a code edit to prove that nothing changed, or that it changed only where expected."
---

# golden-census — prove a change altered nothing observable

## What it answers, and what it never answers

golden-census answers one question by comparing a program's output from before and after a code change: **did any recorded surface of this program move?**

golden-census never answers:

- Whether the behavior is CORRECT. A golden records a bug as faithfully as a feature. `IDENTICAL` means unchanged, never right.
- What a difference MEANS. It gives you the row, the line and the diff. The attribution is yours to write.
- Whether your test suite is adequate.
- Anything about source code. It never imports the subject and never reads a table out of it by name. If a fact is not in the manifest, the census or the bytes the subject wrote, golden-census does not have it.

## Run it

Run `golden-census --version` first. It confirms that golden-census is installed and runs from any directory, and it prints `golden-census 1.0.1`, the version this skill documents. (Python imports the package as `golden_census`, so `python3 -m golden_census` works from a checkout's root.) If it does not run, or the version differs, report that and trust the program's own `--help` and refusals over this skill. Spell every command below the way you ran this one.

Set `TMPDIR` before any command that runs the subject. It must be an absolute path to a directory that exists, at most 49 characters long. golden-census makes no temp root of its own. A wider root is refused, and the refusal's `next:` names a root that fits: `/tmp` on Linux, `$(getconf DARWIN_USER_TEMP_DIR)` on macOS.

Run one golden-census command at a time against a subject. Change nothing under the subject, the golden directory or the temp root while it runs. `--selfcheck` and `--selftest` count: each makes directories under the temp root, so run them alone too.

Substitute an absolute path for each of these four:

```
<MANIFEST> = the consumer's manifest.toml: the subject's command, its inputs and its surfaces
<GOLDEN>   = the committed golden directory: the recorded, normalized bytes of every row
<MUTANTS>  = the consumer's mutants.toml: planted edits and the checks expected to catch each
<CENSUS>   = the consumer's census.toml: the pins and folds that make a run reproducible, each with its control
```

Fill `<DIR>`, `<NAME>`, `<SCRATCH>` and `<the command>` with your own values, and every token written in words, such as `<interpreter>` or `<path>`.

Other angle-bracket tokens belong to golden-census. There are two kinds:

- **Placeholders.** Write them exactly as shown in a manifest, a census, a mutants file or a golden-census command line. golden-census replaces each one before it runs anything. For example, `<WRITES>` becomes the path of the file a surface writes. `references/manifest.md`, "Placeholders", lists them.
- **Path tokens.** golden-census writes them into its output and into the golden in place of a path on this machine. For example, `<REPO>` stands for the subject's root. Never write one into a manifest. "Reading the verdict" lists them.

Only `probe` takes the census file on its command line, as `probe --census <CENSUS>`. Every other command, the `census` command included, reads the census file that the manifest's `census` key names.

## Which command, when

| You are about to | Run | It is done when |
|---|---|---|
| touch a surface: refactor, rename, restructure | `compare` against the committed golden; `capture` one first if there is none | `IDENTICAL`, exit 0 |
| hand back a refactor | `compare`, or `compare --against` a capture taken after the change ("Before every hand-back" below) | `IDENTICAL`, exit 0 |
| write a manifest for the first time | the eight steps of `references/first-run.md`: `init`, `probe`, `census`, then `capture --twice` | `--twice: N files, byte-identical`, and no row you meant to record is named under it |
| change the manifest, the census or the runner; add or remove a surface; keep a change of output you intended | `references/rebaseline.md`: a scratch capture compared against the old golden, then `capture --force` | `compare` is `IDENTICAL` and the golden is committed with the change |
| find out whether the checks catch anything | `mutants` | `N/N mutants caught`, exit 0 |
| find out whether a command can be a subject, before the first `capture` | `probe -- <the command>` | five `[PASS]` rows and `5/5 passed`, exit 0; for `swift-package`, clause 4 red (`references/templates.md`) |
| find out why a census control went red | `census --manifest <MANIFEST>` | see "When a control of YOUR census is red" below |

Redirect every command to a file: `golden-census compare … > run.log 2>&1`. Read the log as UTF-8. A run that hangs or crashes leaves its partial output in the file, where you can read it; on a pipe it is out of reach until the run ends. `references/commands.md` has every flag of every command, its rules, and the exact invocations.

## Reading the verdict

**Exit codes: 0 a pass or IDENTICAL, 1 a FAIL or differing rows, 2 REFUSED, 130 or 143 interrupted.**

Exit 1 is a statement about what the command measured: the subject under `compare`, your census under `census`, your checks under `mutants`, golden-census itself under `--selfcheck`. Exit 2 is a statement about the RUN: a path, a precondition, an unfilled hole, or a subject that would not hold still under `--twice`. No verdict was made. Never report a 2 as a failure of the code.

Each command ends with a **verdict**: the line that answers its question, such as `IDENTICAL` or `2 differing row(s)`. Before the verdict, `capture`, `compare` and `mutants` print a **tally**: how many of your census's controls passed, such as `3/3 census controls passed`. The tally shows that the census held while the verdict was made. Quote both.

The tokens golden-census prints in place of a machine path. Never write one into a manifest.

- `<REPO>`: the subject root, in printed lines and in goldens.
- `<TMPROOT>` in a printed header line: the temp root, your own scratch directories under it included. `<TMPROOT>/golden-census-abcd/x` is a file in a work directory under it.
- `<TMPROOT>` inside a recorded golden: the whole work directory, the neutral census's `work` fold. `<TMPROOT>/x` in a `[DIFF]` and `<TMPROOT>/golden-census-abcd/x` in a header name the same file. A census may spell this `placeholder` as it likes.
- `<CLONE>`: both a placeholder and a path token. Written in a manifest, it is replaced with a pinned input's clone directory; inside a golden it is the neutral census's `clone` fold of that directory.
- `<PYTHON>`: both a placeholder and a path token. Written in a manifest or on a command line, it is the interpreter running golden-census; printed, in a `probe` banner, a `ran:` block or the `census state` block, it is the fold of that interpreter's path.
- `<CWD>`: the current directory, in a `probe` banner.
- `<HOME>`: the reader's home directory, in a refusal's environment block.
- `<ENGINE-TMPDIR>`: the fixed-width directory, the neutral census's `fixed-width-dir` fold, in goldens and in a refusal's block.
- `<TMPDIR>`: the probe's own fixed-width directory, in a `probe` banner.

The lines you meet most. Each was printed by a run on the shipped example, or on a copy of it with one planted change. A letter `N` stands for a number that moves with your project. Quote the numbers you saw.

| What you see | What it means | What to do |
|---|---|---|
| `  IDENTICAL` under `  N golden files, N new files` | Every recorded byte of every row matched. | Quote both lines, with the numbers you saw. |
| `  IDENTICAL (1 permitted movement)` | A row moved, and a `[[movements]]` row of the manifest or an `--allow-diff` file attributes it ("Which permit, when" below). | Quote the `[ALLOWED]` lines too. A permitted movement is still a movement. |
| `  [ALLOWED] fixtures/results.json — fixed in review` | This row moved, and somebody wrote down why. | Check the attribution still describes what you did. |
| `  [DIFF]    fixtures/results.json (changed)`, then a unified diff | This row moved and nobody attributed it. | This is the finding. Name the row, quote the diff, then fix the change or attribute the movement. |
| `  [DIFF]    fixtures/results.json (only-in-golden)` | A surface stopped being produced, or something else left a file in the folder. | The capture log's `<surface>: exit N` line shows how the run ended. For its stderr, take `capture --out /tmp/after`, then read `/tmp/after/<input>/<surface>.err`. If the file named in the row matches no surface in the manifest, golden-census did not write it: ask what to do with the file. |
| `  [DIFF]    fixtures/stray.out (only-in-new)` | A surface appeared with no golden, or something else left a file in the folder. | If you added the surface's row, re-baseline with `capture --force` and commit the golden with the row. If the file named in the row matches no surface in the manifest, golden-census did not write it: ask what to do with the file. |
| `  1 differing row(s)` | The count of `[DIFF]` rows. | Exit 1. |
| `REFUSED: --golden names … which is not a directory. …` | A precondition, a manifest key, a path or a contraband hit stopped the run. | Read the sentence. It names the key or the file to fix. Nothing was compared. |
| `  next: Each [DIFF] row above is a change nobody attributed. For an intended change, …` | The one sentence saying what to do. When every `[DIFF]` is a surface the manifest names and the golden does not record, it instead says to record them with `capture --force`. When every `[DIFF]` is a surface the golden records and the manifest no longer names, it says to delete the files marked `only-in-golden` from the golden, then run `capture --force`. | Do that, or say in your report why you did not. Every refusal ends in one. |
| `  N/N census controls passed, K arm(s) SKIPPED (disclosed, never a pass)` | The tally of your census's controls, one row per pin and per fold, in front of `capture`, `compare` and `mutants`. Under `census` the block's tally reads `N/N passed`. | Quote it beside a clean verdict, with the numbers you saw. |
| `  contraband scan: N files written, N read, 0 hit(s)`, then `  contraband positive control: PASS — …` | golden-census read back every file the capture wrote and found no path from this machine. The control planted such paths in a scratch file and the scan found all of them, so the scan can go red. | Quote both lines beside every clean capture. |
| `  census note: no `path` fold names clone, fixed-width-dir. …` | The census has no fold for one of the four directories golden-census knows (`references/first-run.md`, step 4). | A fact, not a finding. Nothing to fix until a capture is refused for leaking that directory; the refusal then names the row to uncomment. |
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

| Command | What it prints beside its verdict |
|---|---|
| `capture`, `compare` without `--against` | the tally, the `contraband scan:` and `contraband positive control:` lines, the file counts |
| `mutants` | the tally, the null mutant line and the mutant table; it prints no capture line |
| `census` | the controls as a block with the tally, then the rows and the `census state` block (`references/first-run.md`, step 4, gives the order) |
| `compare --against` | the verdict line, the file counts and the `  --against:` line saying the controls and the scan to quote are the capture's; nothing else |
| `probe` | its `N/5 passed` |
| `init`, `--version` | no verdict; quote what they printed |

## Procedures

**Before touching a surface.** Make sure there is a floor to compare against. With a committed golden, run `golden-census compare --manifest <MANIFEST> --golden <GOLDEN>` and get `IDENTICAL`: a `[DIFF]` before you changed anything is somebody else's movement, to attribute before you start. With no golden, capture one, `golden-census capture --manifest <MANIFEST> --out /tmp/before`, and the hand-back then compares with `--golden /tmp/before`. If a command refuses, read the sentence and fix the named thing. A refactor with nothing to compare against is a refactor you cannot report on.

**Before every hand-back: `compare`.** Run `golden-census compare --manifest <MANIFEST> --golden <GOLDEN>` and quote what "Report hygiene" above lists. A `[DIFF]` row is the finding. Name it, quote its diff, then attribute it or fix it. Say whether it is the change you intended. Never re-baseline to make a comparison pass; a change you intended is `references/rebaseline.md`. Use `--against <DIR>` only with a capture taken AFTER the change: `golden-census capture --manifest <MANIFEST> --out /tmp/after`, then `golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --against /tmp/after`.

**Which permit, when.** A `[[movements]]` row in the manifest permits a movement from now on and records why. Use it for output the project changes on purpose, such as a version number or a release date. `--allow-diff` permits a movement for this one comparison. Use it for a change under review that the golden does not yet carry. A re-baseline makes the new bytes the golden. Nothing else makes a `[DIFF]` go away.

**When a run is stuck or crashed.** The run's first line names its process group and the one command that stops everything the run started. Your environment's rules, not golden-census, decide whether you may run that command. If you may, run only the line of a run you started and are still watching. A process group id is reused once every member has died, so a line from an old log can name an unrelated tree.

golden-census keeps no clock, and a build can be slow. A run that has not returned has not failed: judge it as you judge any process you started. A subject that reads the terminal does not hang the run; golden-census refuses it and names the read. If you cannot tell a slow run from a stuck one, report it rather than kill it. A wait costs time; a kill costs the build tool's state and makes a working run look like a failure.

In your report, quote the line, say which command produced it, and say how long the run had been silent.

**When the gate asks whether the checks work.** Run `golden-census mutants --manifest <MANIFEST> --mutants <MUTANTS>`. A `SILENT` where `expect` named a check is the finding. So is `(no check fired)`. Both are faults of the CHECKS. The fix is a better check, never a smaller `expect`.

**When a control of YOUR census is red.** The commands that make a golden or a verdict refuse: `REFUSED: golden-census does not run <command> when a control of this manifest's census did not pass`. Run `golden-census census --manifest <MANIFEST>`. Its output is that of `references/first-run.md`, step 4: the controls, then the rows and the `census state` block. The red row and that block together are what you report. The fix is in the CENSUS. Point an `UNPROVEN` pin's control at a surface the variable does move, or rewrite the row as a `state` row: `name`, `disposition = "state"`, `variables = ["<the variable>"]`, `finding`, and no other key. That records the value and pins nothing. Correct a fold whose control folds nothing, or remove it. Never delete the row to make the command run.

## Open on demand

Open a reference for the step or the line in front of you.

| Open | When |
|---|---|
| `references/first-run.md` | You write a manifest for the first time: the eight steps from `init` to the first hand-back. |
| `references/rebaseline.md` | The manifest, the census or the runner changes; a `[DIFF]` is the change you intended; a capture will not reproduce. |
| `references/commands.md` | You need the rule of a flag, or a refusal names one. |
| `references/verdicts.md` | A line in the output is not in the table above, or a `probe` block is red. |
| `references/manifest.md` | You write or change a manifest row, or read a golden directory. |
| `references/census.md` | You write a census row, or a capture will not reproduce. |
| `references/mutants.md` | You write the mutants file (`first-run.md`, step 7), or the gate asks whether the checks work. |
| `references/machine.md` | A refusal names the temp root, `HOME` or the cache directory; Linux; a pinned input. |
| `references/templates.md` | You run `init` (`first-run.md`, step 2), or you choose a template. |
