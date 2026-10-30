# The golden-census manual

This manual gives the procedure, the commands, the flags, the output and the rules for running it safely. The [README](../README.md) covers installation.

Read this manual first, whole. The other documents in this folder are references, each linked from the step or rule it serves: [`manifest-format.md`](manifest-format.md), [`census-format.md`](census-format.md) and [`mutants-format.md`](mutants-format.md) for the three files, [`contract.md`](contract.md) for what a program must provide to be a subject and how to write a runner, and [`adding-a-template.md`](adding-a-template.md) for shipping a new template. None is read front to back.

Commands are spelled `golden-census …`. In a checkout without an install, `bin/golden-census` is the same command. So is `python3 -m golden_census`, run from the checkout root under Python 3.11 or newer. `golden-census` is the command and `golden_census` is the name Python imports.

Three principles decide how golden-census behaves.

- **Deterministic.** Two captures of an unchanged subject are byte-identical. If they are not, golden-census refuses and names the row and the line that moved.
- **Refuse, don't guess.** A precondition that does not hold is refused. So is a manifest key that does not resolve, and so is an `--out` directory golden-census did not write. Each refusal is one sentence at exit 2, before anything is run.
- **A zero result is not a clean result.** Every guard ships with a positive control that proves it fires. The comparator has a planted difference. The contraband scan has a planted home path. Every census pin and fold has a planted case.

## How it works

golden-census runs a program, records what the program produces and compares that record with the record from an earlier run.

- **Subject.** The program under golden-census.
- **Input.** A named bundle of arguments the subject is run over: a tree, a fixture, a clone, or nothing.
- **Surface.** A named argument suffix that produces one recorded result.
- **Row.** One input with one surface. Each row has one golden record.
- **Golden.** The recorded, normalized bytes of a row. The project commits them.

The loop has four moves.

1. `capture` runs every row and records the normalized bytes. The result is the golden.
2. You change the program.
3. `compare` runs every row again and compares the bytes with the golden.
4. `IDENTICAL` means nothing observable moved. Any other result names the row and the line.

Normalizing removes what is about the machine rather than the program, such as a temp path or a home path. The census says how to normalize.

## The three files of golden-census

golden-census reads three files. All three are TOML, all three are the project's, and `init` writes all three (step 2). Each has a format document, which is the authority for its keys and rules. A key golden-census does not read is refused when the file is read. [`manifest-format.md`](manifest-format.md), "File format", states that rule for all three.

The three files and the golden belong to the project. Commit them beside the program. The person who adds or changes a surface writes its manifest row and golden in the same commit.

- **The manifest** says what to run. It names the subject, the inputs it is run over, and the surfaces recorded for each. See [`manifest-format.md`](manifest-format.md).
- **The census** says what surrounds every run. It pins or folds away the environment, states what it cannot pin, and requires the preconditions. See [`census-format.md`](census-format.md).
- **The mutants file** lists deliberate small changes to the subject, with the checks that must catch each one. `mutants` plants them in a copy and prints which checks fired. See [`mutants-format.md`](mutants-format.md).

## Plugging a project in, in order

Eight steps. Each step names the line it prints when it is done. The skill states the same eight steps for an agent, under the same names. Before the first, run `golden-census --version` once; it prints `golden-census 1.0.0`.

1. **Choose the function.** Pick one whose inputs you can save to a file. Its output must be a value a JSON encoder can write. Nothing else may reach the output: no clock, no random source, no network, no unordered collection. Step 5 is the proof. Under `--twice`, the line `two captures of one subject differ: <path> line N` names the line the function read for itself.
2. **`init`.** Run `golden-census init <DIR> --template <NAME>`. `golden-census init --list` names the templates. The last line of the output is:

   > Fill every hole above. Commands that read manifest.toml, census.toml or mutants.toml refuse one that still spells <<HOLE:NAME>>; none checks runner.py, so a hole left there is not refused and a capture records the run it breaks.

   - The clause after `<<HOLE:NAME>>` names the template's own files that carry a hole. `init` prints it only when there is one.
   - `<DIR>` is the subject's own checkout, or any directory whose manifest spells `root` from there. The shipped example is the second shape, with `root = "../.."`.
   - The subject is ONE repository. Never `git init` a directory inside it. Step 7 says why.
   - The `python-function` runner lands beside the manifest; the Swift runners land in the literal `<<HOLE:TEST_TARGET_DIR>>/` directory, and their READMEs say where to move them. A relative element of `[subject] command` resolves under `root`. So spell a runner beside the manifest `<HERE>/runner.py`. `<HERE>` is the manifest's own directory, right wherever the manifest sits. [`manifest-format.md`](manifest-format.md), "Placeholders", has its rules.
   - Every command that reads the manifest, the census or the mutants file refuses a hole left in it. The refusal names the hole and the file.
   - golden-census never looks for a hole in the runner. Fill its holes next, and step 3 probes it before the manifest's holes are filled. A hole left there is the subject failing, recorded at exit 0.
   - The template's README is what to read here.
3. **`probe` — before the first `capture`.** The rule: probe the command before a manifest names it. Then nothing false is recorded as a golden. A runner whose hole names the wrong module, or calls the wrong function, still launches, and `capture` records whatever it writes at exit 0, so the first capture looks like a success. `probe` shows the fault as a red clause.
   - Run `golden-census probe -- <interpreter> <script> '<WRITES>'`. It prints `  5/5 passed`. The Swift templates' READMEs name the one clause their test tool fails there, and why.
   - Run it from the directory the manifest sits in, where the runner is. `probe` runs the candidate in the current directory and has no `root` to run under yet.
   - For a template's runner: fill the runner's holes, probe it, then fill the manifest's holes (step 4).
   - [`contract.md`](contract.md) has the five clauses, a worked red block, and the shell form for a program that only prints.
4. **Fill the holes.** Run `golden-census census --manifest <MANIFEST>`. It prints `census <REPO>/…/census.toml`, the rows, the preconditions and the `census state` block. While a hole is open, it prints `REFUSED: the manifest … still carries the unfilled hole(s) …` instead.
   - The manifest's own placeholders are `<ROOT>`, `<WORK>`, `<WRITES>` and `<PYTHON>`.
   - `<REPO>`, `<TMPROOT>` and `<CWD>` are golden-census's own folds of the paths it prints about the machine. Never type one into a manifest. The neutral census also names its work-directory fold `<TMPROOT>`, inside a recorded golden; that is the consumer's own word for a `placeholder`, and the census may spell it as it likes.
   - A subject that is not a git checkout stops here: the neutral census's `git-checkout` precondition refuses it. Make the tree a repository, which `mutants` needs anyway, or delete that row. A `precondition` row does not become a `state` row by changing one key: `state` takes `variables`, `commands` or both, and no other key, so the row is refused as a whole.
5. **`capture --twice`.** Run `golden-census capture --manifest <MANIFEST> --out <GOLDEN> --twice`. It prints `  --twice: N files, byte-identical`.
   - Commit `<GOLDEN>` beside the three files. The golden IS the handoff.
   - `init` writes no `.gitignore`: a scratch capture goes in a scratch directory of yours, such as `/tmp/before`, never in the tree.
   - Run one golden-census command at a time against a subject. [Running safely](#running-safely) says why.
6. **`compare`.** Run `golden-census compare --manifest <MANIFEST> --golden <GOLDEN>`. It prints `  IDENTICAL`, under `N golden files, N new files`.
   - To compare a built copy of the program, such as a bundle, with the golden the source recorded, add `--command ARG` once per element of that copy's argv, in order. The fresh capture runs that argv in place of the manifest's `command`. The `COMPARE` block names it on a `command:` line, and `IDENTICAL` then says that copy printed what the golden recorded.
7. **One mutant.** Fill the mutants file's holes with one edit a check must catch, commit, then run `golden-census mutants --manifest <MANIFEST> --mutants <MUTANTS>`. It prints `  N/N mutants caught by every check they expect`.
   - `mutants` clones the COMMITTED tree. An uncommitted golden or edit is invisible to it.
   - That tree must CONTAIN the subject. A repository `git init`-ed inside the subject's checkout clones only itself, and the null mutant then comes back not SILENT.
8. **Before every hand-back: `compare`.** Run step 6 again. A hand-back reports three things. The first is `IDENTICAL`, with the file count. The second is the census controls' tally. It reads `N/N census controls passed, K arm(s) SKIPPED (disclosed, never a pass)`, with one row per pin and per fold of your census. The third is the contraband control line.
   - `capture`, `capture --twice`, `compare` and `mutants` print the tally, because each runs your subject.
   - `census` prints the same controls as a block.
   - `compare --against`, `probe`, `init` and `--version` start no subject and print no tally.

### Re-baselining on purpose

Control a new golden before you trust it.

1. Capture the new set into a scratch directory: `golden-census capture --manifest <MANIFEST> --out <SCRATCH> --twice`.
2. Compare it with the old golden: `golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --against <SCRATCH>`.
3. Check that it reports exactly the rows you meant to move and no others. Its row count is the new golden's positive control.
4. Replace the golden: `golden-census capture --manifest <MANIFEST> --out <GOLDEN> --force`.

## Templates and the worked example

`init --template NAME` writes a runner on top of the three files. For a test tool that needs one, it writes a wrapper too. Each template's README is its pattern document. It says what the runner freezes, lists every hole, shows the manifest lines the template implies, and names its traps. [`adding-a-template.md`](adding-a-template.md) says how a template is written.

- [`templates/python-function/README.md`](../templates/python-function/README.md) is for a Python function. `runner.py` imports it, calls it over the fixtures it lists, and writes sorted-key JSON.
- [`templates/swift-package/README.md`](../templates/swift-package/README.md) is for a SwiftPM package. A Swift Testing test runs under `swift test --filter GoldenCensusRunner`.
- A program that runs from a command line needs no runner: the neutral three that `init` writes with no `--template` are enough. A library in a language with no template needs a runner of your own, written to the six steps in [`contract.md`](contract.md), "Writing a runner".
- [`templates/swift-xcodebuild/README.md`](../templates/swift-xcodebuild/README.md) is for an Xcode app or framework. It uses the same test, plus `wrapper.py`. The wrapper runs one quiet `xcodebuild test` and makes the out file, not the exit code, the verdict.

[`examples/python-function/README.md`](../examples/python-function/README.md) is the first template filled in and committed. The subject is `wordstats`, one pure function over two fixture files, with its manifest, census, mutants file and golden. The README lists ten commands in order, with the line each prints. Read it and copy it. Nothing depends on it. `--selftest` reads that README for the version number and nothing else.

## Commands and exit codes

There are six subcommands and three whole-program flags: `--version`, `--selfcheck` and `--selftest`.

| Command | What it does | Exit |
|---|---|---|
| `capture` | Runs every row of a manifest and records the normalized bytes into a directory. | 0 recorded; 2 refused |
| `compare` | Compares a golden directory with a fresh capture, or with one recorded earlier. | 0 `IDENTICAL`; 1 differing rows; 2 refused |
| `census` | Reads a census, runs its controls, checks its preconditions and prints its state. That is everything a capture does around the runs, without the runs. A red-control refusal sends you to it. | 0 pass; 1 a control failed; 2 refused |
| `mutants` | Plants every mutant in a repo-shaped copy of the subject and prints which checks caught it. | 0 all caught; 1 a hole in the net or a REFUSED mutant; 2 refused |
| `probe` | Runs a candidate command twice and reports the five clauses of [`contract.md`](contract.md). It takes no manifest: it answers whether a command can BE a subject. | 0 all five pass; 1 a clause failed; 2 refused |
| `init` | Writes a project's manifest, census and mutants file from a template. Every project fact is left as a marked hole. | 0 written; 2 refused |
| no arguments | Prints the usage block. | 2 |

Exit codes: 0 a pass or IDENTICAL, 1 a FAIL or differing rows, 2 REFUSED, 130 or 143 interrupted.

An exit 1 is a statement about what the command measured: the subject under `compare`, your census under `census`, your checks under `mutants`, golden-census itself under `--selfcheck`. An exit 2 is a statement about the run: a path, a precondition, an unfilled hole, or a subject that would not hold still under `--twice`. No verdict was made.

Every `REFUSED:` sentence is followed by a `next:` line saying what to do about it. The parser's own usage errors are the exception. They print `golden-census <command>: error: …` at exit 2, with no `REFUSED:` and no `next:` line.

A child golden-census cannot start is one `REFUSED:` sentence, never a traceback.

## Flags

One row per flag and command. A flag that takes a value shows its placeholder: `FILE`, `DIR`, `NAME` or `ARG`. The placeholder names the kind of value and is not part of the flag.

| Flag | Command | What it does |
|---|---|---|
| `--manifest FILE` | `capture` | The manifest to read. Required. |
| `--out DIR` | `capture` | Where the capture is written. Required. |
| `--input NAME` | `capture` | Records only this input. Repeatable. |
| `--force` | `capture` | Replaces an `--out` that holds a capture, once the new capture has succeeded. Re-baselining is a deliberate act. |
| `--twice` | `capture` | Records everything twice. Refuses if the two captures differ, and names the row and the first differing line. |
| `--manifest FILE` | `compare` | The manifest to read. Required, even with `--against`. |
| `--golden DIR` | `compare` | The recorded golden set. Required. |
| `--against DIR` | `compare` | Compares a directory recorded earlier instead of running the subject. Neither side is normalized again. No census control and no contraband scan run; the COMPARE block says so in a line under `new:`. |
| `--allow-diff FILE` | `compare` | Extra permitted movements, as `path :: attribution` lines, on top of the manifest's `[[movements]]`. |
| `--command ARG` | `compare` | Runs the fresh capture with this argv in place of the manifest's `[subject] command`. Repeatable: one flag per element, in order. Not with `--against`. |
| `--manifest FILE` | `census` | The manifest to read. Required. |
| `--manifest FILE` | `mutants` | The manifest to read. Required. |
| `--mutants FILE` | `mutants` | The mutants file. Required. |
| `--only NAME` | `mutants` | Plants only this mutant. Repeatable. The null mutant runs either way. |
| `--census FILE` | `probe` | The census whose environment the candidate runs under. Without it, a built-in default applies. |
| `--writes-env NAME` | `probe` | Exports the output path as this variable instead of substituting `<WRITES>` in the argv. |
| `--template NAME` | `init` | The template written on top of the neutral three. An unknown name is refused, and the refusal lists the shipped ones. |
| `--list` | `init` | Prints `name — summary` for every shipped template and writes nothing. |
| `--selfcheck` | whole program | Runs golden-census's own controls and exits. |
| `--selftest` | whole program | Runs the whole app against its bundled fixture and exits. |
| `--version` | whole program | Prints the version and exits. |
| `--manifest FILE` | whole program | The manifest `--selfcheck` reads its census from. Optional with `--selfcheck`, where it adds that census's own controls. |

`--help` stands wherever a flag may, before any `--`. It prints the help and exits 0. The bare command's help ends with a `directories:` section that names where this install keeps `docs/`, the examples, the README, the skill and the templates, with `(not present)` after one the install lacks. After a subcommand it prints that subcommand's help. Nothing else on the command line runs, so `--selfcheck --help` runs no self-check.

### Rules for every flag

- **Give a flag once.** A flag given twice on the same side of the subcommand is refused before anything runs. The refusal names the flag, how many times it was given and, for a flag that takes a value, every value.
- **The parser speaks first.** Its own refusals name only what the parser names. A command line that leaves out a required flag, or gives a flag the command lacks, is turned down for that. A flag given twice beside it is not named until that is fixed.
- **Only the flags marked repeatable repeat.**
- **An empty path is refused.** An empty or white-space value, as an unset or blank shell variable gives one, is refused. The flags are `--manifest`, `--out`, `--golden`, `--against`, `--allow-diff`, `--mutants`, every `compare --command` element and `probe --census`, and the directory `init` takes. The refusal names the flag. An empty value is never read as the flag left out, or as the current directory. `probe --writes-env` is refused an empty or white-space name the same way.
- **Paths are checked before the controls run.** A path golden-census refuses costs one sentence at exit 2 and no run of the subject. The checked paths are `--manifest`, then `--golden`, `--against` and `--allow-diff`, then the `--input` names, then `--out` and whether a capture can land there, then `--mutants`. `probe --census` and `init`'s directory are checked too. Those two commands run no controls.
- **Some paths are read again.** `--golden`, `--against` and `--allow-diff` are read again where the command uses them. A verdict is of the golden and the table as they stand once the controls have run.

### Rules for one flag

- **`--manifest`.**
  - `probe` and `init` take no manifest. They reject the flag with the parser's own error, `golden-census: error: unrecognized arguments: --manifest`, at exit 2, with no `REFUSED:` and no `next:` line.
  - Given alone, with no command, it is refused. Given before a subcommand, it is refused too: a command's manifest follows the command.
- **`--selfcheck`, `--selftest` and `--version`.**
  - `--selfcheck` is refused beside a subcommand and beside `--selftest`.
  - `--selftest` takes no `--manifest`. It is refused beside a subcommand and beside `--selfcheck`.
  - `--version` is refused beside anything else.
- **`init --list`.** It is refused beside a directory and beside `--template`.
- **`--out`.**
  - A path that does not exist is created.
  - golden-census records the capture under the temp root and moves it into place, through a new directory beside `--out`. So the directory `--out` sits in must be writable.
  - Whether `--out` replaces a capture is decided from what stands there when the command starts. A capture the subject puts there during the controls is refused, not replaced.
  - `surfaces.json` is the marker: a directory that holds at least one `<input>/surfaces.json` is a capture directory. `capture` refuses to write into a non-empty directory that lacks the marker, a stranger's directory, and into one that has the marker but was not given `--force`, a prior capture. Re-baselining is a deliberate act, never the shortest command form.
  - It refuses a `surfaces.json` or an input directory it cannot read, and names it. It refuses a symbolic link anywhere in an `--out` that holds a capture, whatever `--force` and `--input` say. It makes each refusal before the run and again right before the swap. A directory that holds no marker, not even behind a link, holds no capture, whatever links it holds.
- **`--force`.** It replaces what this manifest's capture records, and nothing else: [`manifest-format.md`](manifest-format.md), "The golden directory", lists what that is. golden-census refuses any other file in the directory, and names it, before anything runs and again right before the swap. A file that appeared during the run is refused, never deleted. `--force --input X` replaces `X`'s directory whole and no other.
- **`--golden` and `--against`.** A path that is not a directory is refused with nothing compared. So is a directory that holds no capture, a directory golden-census cannot read, and a capture that holds a symbolic link. `--against` follows the same rule as `--golden`.
- **`--command`.**
  - `compare` only. `capture` has none: a golden recorded under another command would carry nothing that says so.
  - Give one flag per element of the argv, in order: `--command <PYTHON> --command <HERE>/runner.py`. An element that begins with `-` is written `--command=-I`. The elements are taken as given, an absolute path included. `<PYTHON>` and `<HERE>` resolve as in `[subject] command`, and `<HERE>` is the manifest's directory, because the flag has none of its own. A placeholder `[subject] command` cannot spell, or a `<HERE>` path that is not there, is refused before anything runs. An empty or white-space element, as a blank shell variable gives one, is refused.
  - It is refused beside `--against`, which reads two recorded directories and runs nothing.
  - Everything but the command is the manifest's and the census's: the inputs, the surfaces, the folds and the contraband scan. The census's controls run the same command as the fresh capture.
  - The golden is the manifest's record whichever command ran. `surfaces.json` holds the arguments after the command and never the command, so the override moves no byte there; only what the program printed can move a row.
  - The `COMPARE` block gains a line under `new:`, `  command: <the argv, shell-quoted>`. It is printed only when the flag was given.
- **`--allow-diff`.**
  - The file is plain text, one `path :: attribution` row per line. A line whose first non-blank character is `#` is a comment, and a blank line is skipped. Any other line is one row, `#` and all: a comment after a path is part of the path, and permits nothing. A line with no `::`, or nothing after it, reads `(no attribution)`. What a row permits is the `[[movements]]` rule: [`manifest-format.md`](manifest-format.md), `[[movements]]`.
  - golden-census reads the file before the subject runs. A path it cannot read, or a file that is not UTF-8 text, is refused there, with nothing run.
  - The table is read again once the controls have run. A table that cannot be read then is refused after the controls ran, with nothing captured.
- **`--only`.** `--only` takes only names the mutants file has; any other name is refused. The preflight checks only the named mutants. A stale mutant you did not name is noticed by the bare `mutants` run and not by `--only`.

## Reading the output

These are the lines you meet most. Each was printed by a run on the worked example, or on a copy of it with one planted change.

| Line | Meaning |
|---|---|
| `process group <PGID> — if this run hangs or crashes, stop everything it started with: kill -- -<PGID>` | The first line of every command that launches anything. See [Running safely](#running-safely). |
| `  3/3 census controls passed, 1 arm(s) SKIPPED (disclosed, never a pass)` | The tally of your census's controls, printed in front of `capture`, `compare` and `mutants`. Each pin and each fold has one row. Under `census` the same controls print as a block, and its tally reads `3/3 passed`. |
| `  [SKIP]  census pin "the subject's temp root, and its width": the real-directory arm` | A control with nothing to exercise on this machine. It is disclosed and never a pass. |
| `  census note: no `path` fold names clone, fixed-width-dir. …` | The census has no fold for one of the four directories golden-census knows. A capture that leaks it is refused, and the refusal names the row to add. |
| `  --twice: 5 files, byte-identical` | `capture --twice` found no difference between its two captures. |
| `REFUSED: two captures of one subject differ: fixtures/results.json line 42` | `--twice` found a difference. The next two lines quote the line from each capture. |
| `  contraband scan: 5 files written, 5 read, 0 hit(s)` | The scan for machine paths in what was recorded. A `contraband positive control: PASS` line follows it. |
| `  capture complete` | The capture was moved into place. |
| `  5 golden files, 5 new files` | The number of files on each side of a comparison. |
| `  IDENTICAL` | No row moved. |
| `  IDENTICAL (1 permitted movement)` | No row moved except the ones the manifest or `--allow-diff` permits. An `[ALLOWED]` line names each, with its attribution. |
| `  [DIFF]    fixtures/results.json (changed)` | The row moved. The unified diff follows. `(only-in-golden)` and `(only-in-new)` name a file present on one side only. |
| `  1 differing row(s)` | The count of `[DIFF]` rows. The verdict is exit 1. |
| `  [SKIP]    1 row(s) are a skip on both sides, so nothing ran to compare: fixtures/never` | A row declared unrunnable on both sides. `IDENTICAL` then says only that their recorded reasons matched. |
| `  unused: [[movements]] row 'fixtures/results.json' permits a movement that did not happen` | A permitted movement matched no moved row. It stands before the verdict and changes nothing. |
| `  2/2 mutants caught by every check they expect` | The `mutants` verdict. |
| `REFUSED: --golden names … nosuchdir, which is not a directory. …` | Nothing was compared. A `next:` line follows. The exit is 2. |
| `  next: Each [DIFF] row above is a change nobody attributed. For an intended change, pass --allow-diff with a file holding one line per row, `<path> :: <attribution>`. That permits the change for this comparison only. For a row that may differ from one comparison to the next, such as a version or a date, add a [[movements]] row to the manifest instead; that permits the row in every comparison from now on. When the new bytes are what the subject should do from now on, capture again with --force and commit the golden. A change that was not intended shows that the code change was not behavior-neutral.` | What to do about the verdict above it. When every `[DIFF]` is a surface the manifest names and the golden does not record, the `next:` instead says to record them with `capture --force`. When every `[DIFF]` is a surface the golden records and the manifest no longer names, it says to stop recording them with `capture --force`. |

### Refusals

A `REFUSED:` sentence ends in a `next:` line. Each refusal below was printed at exit 2.

| Refusal | What it means | What to do |
|---|---|---|
| `REFUSED: the manifest <path> still carries the unfilled hole(s) <<HOLE:SUBJECT_NAME>>, <<HOLE:ROOT>>, …` | A file `init` wrote still has a marked hole. The sentence names every hole left and the file. | Fill every hole it names, then run again. golden-census read nothing past the hole. |
| `REFUSED: <path>/manifest.toml: [subject] command names <path>/runer.py, which does not exist. <HERE> is the directory this manifest sits in, so the path is known before anything runs.` | A `<HERE>/…` element of the command names a file that is not there. | Point the element at a file beside the manifest. |
| `REFUSED: the subject would not run: FileNotFoundError: [Errno 2] No such file or directory: 'nosuchprogram_xyz'.` | The `[subject] command` names a program that is not on `PATH`, or is not executable. | Fix that argv and run again. Nothing was captured, and `--out` is as it was. |
| `REFUSED: golden-census stopped on an operating-system error that none of its own checks answers — <the error as Python states it> — …` | A disk filled, a file-size limit hit, or a directory was removed or made read-only while the command ran. Everything printed above it is not a whole verdict. | Fix what the error names and run the command again. An error that names nothing you can fix is a golden-census defect: report it, quoting the line. This line is quoted from the program's source, not from a run. |
| `REFUSED: main/bin writes <WORK>/<input>-<surface>.txt — not text: 0xff at byte offset 0 (invalid start byte). golden-census records text — …` | A row's `writes` file is bytes golden-census cannot decode. The same sentence says `cannot be read:` for a file whose permissions stop the read. | Record a text dump of the file instead. A wrapper writes the file under `<WORK>` and a deterministic dump of it to `<WRITES>`, with an `ORDER BY` on every table. |
| `REFUSED: the subject ran and printed a byte no UTF-8 decoder can read: 0xff at byte offset 0 of its standard output (invalid start byte).` | A row printed a stream that is not UTF-8 text. | Make the command print UTF-8, or wrap it to write the raw bytes to a file under `<WORK>` and print a text dump. |
| `REFUSED: main/out writes <WORK>/lnk/<input>-<surface>.txt, which resolves to <path>, outside golden-census's work directory. golden-census clears that path before the run, and it removes nothing outside the work directory.` | A link on the `writes` path leads out of `<WORK>`. The row did not run. | Point `writes` at a path that stays under `<WORK>` once its links are followed, or keep what runs before the row from making the link. |
| `REFUSED: <input>/<surface> writes <path>, which resolves to <path> once the row has run, outside golden-census's work directory.` | The row's own command made its `writes` path, or a directory on its way, a link that leads outside `<WORK>`. The row ran. Nothing was recorded from the path. | Point `writes` at a path under `<WORK>`, and keep the row's command from making the link. This line is quoted from the program's source, not from a run. |
| `REFUSED: census <path>: row 'digits' folds EVERY row (scope = "*"), and its pattern matches inside the subject root's own absolute path — it would replace '501' in it. …` | A `regex` fold of your census replaces part of the subject root. This one was found when the census was read. | Narrow the `volatile` group so it takes all of the subject root or none of it, or scope the fold to rows that do not print the root. |
| `REFUSED: census <path>: row 'case word' would rewrite the subject root's own path in the text of fixtures/results: its pattern '…' replaces 'se11'. …` | The same fault, found while a capture ran, because the pattern needs the text around the root. | The same fix. The capture stopped at that row, and `--out` is as it was. |
| `REFUSED: the temp root '<path>' is 69 characters long; a capture needs a root of at most 49, because the census pins the subject's TMPDIR to 51 characters. …` | `TMPDIR` is too wide for the census's fixed-width pin. | `capture`, `compare` without `--against`, `mutants` and `probe` cannot run here. Point `TMPDIR` at the root the `next:` line names, or any shorter directory. `compare --against` needs no temp directory and runs at any width. |
| `REFUSED: golden-census does not take a relative temp root (TMPDIR is 'relative/dir'): …` | `TMPDIR` is relative. | Point `TMPDIR` at an absolute path. |
| ``REFUSED: golden-census does not take a temp root spelled with `..` (TMPDIR is '<path>'): …`` | `TMPDIR` has a `..` component. | Spell it without `..`. |
| `REFUSED: golden-census could not make a directory under its temp root (TMPDIR is '/no/such/root'): No such file or directory. …` | `TMPDIR` names a root where a directory cannot be made, or is unset or empty and Python found no directory it could write in. | Point `TMPDIR` at an absolute path of a directory you can write in. golden-census makes no temp root and tries no other. |
| `REFUSED: HOME is 'relhome', not an absolute path. golden-census takes only an absolute HOME for the home its cache directory is under.` | A clone of a pinned input was about to be made, and `HOME` is relative or empty. | Run again with `HOME` set to an absolute path. No clone was made. |
| ``REFUSED: golden-census does not take a cache directory spelled with `..` (HOME is '<path>'): …`` | A clone was about to be made, and `HOME` (on Linux, an absolute `XDG_CACHE_HOME`) holds a `..` component. | Run again with that variable spelled without `..`. Nothing was made in the cache. |
| `REFUSED: golden-census could not write in its cache directory '<path>': Permission denied. The clones of this manifest's pinned inputs are kept there, and nowhere else.` | The directory the clones are kept in cannot be made or written. | Make it one you can write in, or point `HOME` (on Linux, `XDG_CACHE_HOME`) at a directory you can. What ran before the first clone ran, and `--out` is as it was. |
| `REFUSED: --golden names <path>, which is not a directory. …` | `compare` was given a path that holds no capture. | Point `--golden` at a directory a capture wrote. |
| `REFUSED: <path> already holds a capture (1 entry); replacing it takes --force.`, `… holds 1 entry this capture does not record …`, `… is a symbolic link to out/before. …` | `capture` refused its `--out`. | [Rules for one flag](#rules-for-one-flag) has the `--out` rules. |
| `REFUSED: standard output closed while golden-census was still writing its verdict …`, on standard error | A reader of the output stopped mid-run. The rest of the verdict is missing. | Send the output to a file and read the file. [Send the output to a file](#send-the-output-to-a-file) has the one case that is not a refusal. |
| `REFUSED: standard output refused a write (<the operating system's words>) while golden-census was still writing its verdict …`, on standard error | The output went where a write is refused: a file open for reading only, a full disk, a file-size limit. This line is quoted from the program's source, not from a run. | Send the output to a file that can be written, and read the file. A `capture` whose last line is refused has already moved its capture into place. It says `… as the capture completed, so its last line is missing or cut short; --out holds the new capture.` and exits 2. |
| ``REFUSED: standard output is unusable (closed, as with `>&-`). …`` | Standard output was closed. | Redirect to a file. |
| `REFUSED: probe was given no command to run.` | `probe` has nothing after `--`. | Write the candidate after `--`. |

A directory golden-census made can remain on disk when the command ends. A file a subject left in it may not be removable, or the temp root may have been made read-only. The command names the directory beside the verdict:

```
a directory golden-census made could not be removed: <path> — delete it by hand and name it in your report
```

That line is quoted from the program's source. No run made for this manual produced it.

The line changes no verdict and no exit code. The directory is yours to delete.

## Running safely

### What a command writes

Each command writes its verdict to standard output. A run whose standard output is closed is refused before anything is parsed:

```
REFUSED: standard output is unusable (closed, as with `>&-`). golden-census writes its whole verdict to standard output and does not run blind.
```

What a command writes to standard output and standard error is UTF-8, whatever `PYTHONIOENCODING` or the locale says.

### The process group

Every command except `--version`, `--help`, the bare invocation, a usage error the parser answers, and a flag refused before anything starts opens with one line. It names the run's own process group and the command that kills everything the run started:

```
process group <PGID> — if this run hangs or crashes, stop everything it started with: kill -- -<PGID>
```

`<PGID>` stands for the number the run prints, new on every run.

### Send the output to a file

Send the output to a file: `golden-census compare … > run.log 2>&1`.

- A run that hangs or crashes leaves its partial output in the file, where you can read it. On a pipe it is out of reach until the run ends.
- A reader that stops early, such as `| head`, closes standard output while the run still writes.
- A full disk refuses the writes.
- golden-census refuses each of the last two cases on standard error, at exit 2.

One case differs. A `capture` cut on its last line has already moved its capture into place. It says so on standard error: at exit 0 when a reader stopped, at exit 2 when the write was refused.

### The caller owns the deadline

golden-census keeps no clock. It cannot know how long a subject should run, so nothing it starts has a deadline of its own. It also keeps no size: every byte a child prints, and every file a surface writes, is held in memory whole until it is recorded, so a child that prints without end grows golden-census's memory without limit. That is the second way a run fails to end on its own, and the caller's to stop like the first.

- On every exit it can see, SIGINT and SIGTERM included, it kills the group it opened.
- A subject that reads the terminal is refused, naming the read; the run does not hang on it.
- For the exits it cannot see, its own crash or the caller killing it outright, the process-group line above is the command.
- A crashed run looks like a stuck one from outside. The children it left behind hold its standard output open.

### One command at a time

Run one golden-census command at a time against a subject. Change nothing under the subject, the golden directory or the temp root while a command runs. A second capture of the same pinned input is skipped. A file edited during a run is read as it was when the run reached it.

### Standard input and operating-system errors

Every child golden-census starts has the null device as its standard input. A child that reads meets end of file at once, whatever golden-census itself was started with.

An error of the operating system that no check of golden-census's own answers is one `REFUSED:` sentence on standard output, at exit 2. Examples are a disk that fills, a file-size limit, and a directory removed or made read-only under the run. The sentence quotes the error as Python states it. It is never a traceback.

### What a stopped command leaves

- **`capture`.** golden-census records a capture under the temp root and moves it into place only when every row, the contraband scan and `--twice` have passed. A capture refused or failed before that move leaves `--out` as it was; if `--out` was absent, it stays absent.
  - A capture killed outright can leave a `.golden-census-capture-*` directory beside `--out`. Look in it before you delete it. When the kill lands mid-swap, it holds the previous golden under `retired/`.
  - After the move, two events each say `--out holds the new capture` on standard error, where standard error can be written. One is standard output refusing the capture's last line, a refusal at exit 2. The other is an interruption: `interrupted after the capture landed: --out holds the new capture.` at exit 130 or 143.
  - A `capture` that exits 2, 130 or 143 with nothing on standard error after a long run may hold the new capture. List `--out` to find out.
- **`init`.** `init` is all or nothing. A refusal, or a reader that stops reading its output, leaves the directory as it found it.

## The temp root and the clone cache

### The temp root

golden-census makes its scratch directories under the temp root. That is `TMPDIR` when it is set.

- **Use an absolute path.** golden-census starts each child in a directory of its own, where a relative path names a different directory. A relative `TMPDIR` is refused before anything of the subject runs:

  ```
  REFUSED: golden-census does not take a relative temp root (TMPDIR is 'relative/dir'): a relative path names a different directory for each child golden-census starts in a directory of its own.
  ```

- **Spell it without `..`.** After a symbolic link, `..` names the parent of the link's target, not the directory spelled before it. A `TMPDIR` with a `..` component is refused the same way.
- **It must take a new directory.** A root where no directory can be made is refused in one sentence at exit 2:

  ```
  REFUSED: golden-census could not make a directory under its temp root (TMPDIR is '/no/such/root'): No such file or directory. This command's scratch directories go there, and golden-census does not create that root or try another.
  ```

- **It must be narrow enough.** A capture needs a root of at most 49 characters. The census pins the subject's own `TMPDIR` to 51. [`census-format.md`](census-format.md), "`<FIXED-WIDTH-DIR:N>`", has the rule. The refusal's `next:` line gives a root that fits on your platform.

Every command makes a directory under the temp root, and so checks the root first, except two. `init` writes only into the directory it is given. `compare --against` reads two recorded directories and starts nothing. Both run under any `TMPDIR`. `census` runs under a root too wide for the pin as well: it prints a `note:` under its rows saying so, and its `census state` block then reads `TMPDIR` as unset.

The check of the temp root comes right after the process-group line. It runs before the self-check, before the manifest is read, and before the census's controls and the width rule.

On Linux, the temp root is usually `/tmp`, a tmpfs sized at a fraction of RAM. `mutants` holds a clone and a capture per mutant under it. `capture --twice` holds two capture trees. For a large subject, point `TMPDIR` at `/var/tmp`.

### The clone cache

A pinned input is cloned whole, at full size, with the whole history: golden-census runs a plain `git clone` with no depth limit and no size check, once per repository and commit, and keeps the clone until you delete it. Pin a large repository knowing that its full clone lands on this disk, in the cache directory named here. The clones do not live under `TMPDIR`. They live in your cache directory: `~/Library/Caches/golden-census/` on macOS, and `$XDG_CACHE_HOME/golden-census/` or `~/.cache/golden-census/` on Linux. There is one folder for each repository and commit. golden-census keeps no index of the cache. You may delete one commit, one repository or the whole cache by hand. [`manifest-format.md`](manifest-format.md), `[inputs.<name>]`, has the layout, the checks before a clone, and the cases where a clone cannot be used.

### The settings of git

golden-census gives every git it runs in a tree the same settings on the command line. The trees are a pinned input's clone, the subject's checkout under a `git-checkout` precondition, and the clone `mutants` plants in. The command line begins:

```
git -c core.excludesFile=/dev/null -c core.autocrlf=false -c core.eol=lf -C <tree> …
```

`core.excludesFile` is the null device, `core.autocrlf` is false and `core.eol` is `lf`. Every `git status` also lists untracked files. So what a clone holds, and whether a tree is clean, are the repository's answer and never your global git configuration's.

### Shared clones

Every input of any manifest that pins one repository at one commit shares one clone. A file a row writes into that clone persists across runs, inputs and manifests when the repository's own `.gitignore` or `.git/info/exclude` ignores it. Those files are not the pinned content. [`manifest-format.md`](manifest-format.md), `[inputs.<name>]`, "Files git ignores in a shared clone", describes the second `clone:` line that reports them. Deleting the clone's folder starts clean.

## Checking golden-census itself

`--selfcheck` runs golden-census's own controls. Each control runs beside the planted case that proves it can go red. `--selftest` runs the whole app against the fixture bundled inside the package, then prints the version.

Run `--selftest` after an install or an upgrade, and `--selfcheck`, the quick one, when a result surprises you. `--selftest` takes minutes: 158 s on the machine it was measured on (2026-10-13). It prints these groups, each with a tally: GOLDEN-CENSUS SELF-CHECK, CAPTURE, COMPARE, MUTANTS, DOCS PARITY, FIRST LINE and TEMPLATES.

DOCS PARITY reads this manual, the README and the agent skill's files against the argument parser. It fails when they drift. [`CONTRIBUTING.md`](../CONTRIBUTING.md) says what it checks.

A self-test that raises or refuses instead of reporting a verdict is a `[FAIL]  !` row. It is a defect of golden-census.

### What an install carries

An install carries the package, its bundled fixture, and under the package a copy of `docs/`, the examples, the README, the skill and the templates, in the checkout's own shape, with the license beside them. `golden-census --help` ends with a `directories:` section that names them. The checks that read the documents run in an installed copy as they do in a checkout. An install does not carry `pyproject.toml` or `CONTRIBUTING.md`, so the self-check's packaging row is a disclosed SKIP there:

```
  [SKIP]  sss  pyproject.toml, read with tomllib: every sdist include pattern is ANCHORED …
           pyproject.toml is not in this layout: … holds none. The packaging tables are the repository's; nothing was read and nothing is claimed.
```

A SKIP is never a pass.

Every command but `init` runs without the templates. `--selfcheck` says whether they are there. Its row for the templates begins `the templates beside the package are reported and never assumed`.

## Token Cost for agents

Roughly how much each command prints.

| Command | Output |
|---|---|
| `--version` | two words |
| `compare --against` | a paragraph |
| `capture`, `compare`, `census`, `mutants`, `probe`, `init` | a page |
| `--selfcheck`, `--selftest` | dozens of pages |

A comparison is cheap and a capture is not. `compare --against` reads two recorded directories and answers in a paragraph. A capture runs the subject, and `mutants` runs one capture per mutant.

## For consuming projects

golden-census helps only if the person who adds a surface writes its row. Use these three instructions in the project's agent instructions, in the write-and-verify loop, and in the report format.

**1. In the project's agent instructions, beside its docs-parity rule:**

```
A new or changed surface adds its manifest row and golden in the same
commit; the parity self-test enforces it.
```

**2. In the coder manual's write-and-verify loop:**

```
Capture before you touch a surface, compare before you hand back, update
the manifest when you add one.
```

**3. In every coder prompt, one line in the report's deviation ledger:**

```
Manifest rows added or changed.
```

The agent who adds or changes a surface should also write the manifest row and golden in the same commit. Whoever gates the merge checks that parity held. That check is mechanical.
