# The golden-census reference

This document contains:
1. A glossary of every term of art the documents and the program use 
2. Commands and exit codes
3. Flags

## Glossary

Terms are in alphabetical order. A term in `monospace` is spelled that way in a file or in the program's output. From the command line `grep -i '^- \*\*<SEARCH TERM>' reference.md` to read a definition.

- **Arm.** One of golden-census's own guards, each run beside the planted case that proves it can go red. `--selfcheck` runs the arms and `--selftest` runs them and the whole program on a bundled fixture. A consumer's `capture` or `compare` runs none of them. Rules: [`using-golden-census.md`](using-golden-census.md), "Checking golden-census itself".
- **Attribution.** The sentence that says why a row was allowed to move: the `attribution` of a `[[movements]]` row, or the text after `::` in an `--allow-diff` line. A movement without one is a `[DIFF]`. Rules: [`manifest-format.md`](manifest-format.md), `[[movements]]`.
- **Capture.** Recording every row of a manifest into a directory: the subject runs once per row, the output is normalized, and the bytes are written. A capture into the committed golden directory is a baseline; a capture into a scratch directory is a comparison's other side. Rules: "Commands and exit codes" below, and [`manifest-format.md`](manifest-format.md), "The golden directory".
- **Census.** The file that lists every input to the subject's output that is not the subject's own code, with what golden-census does about each: pin it, fold it, state it or require it as a precondition. It is `census.toml`, written by `init` and committed by the consumer. Rules: [`census-format.md`](census-format.md).
- **Check.** A command the mutants file names, run against each mutated copy of the subject. Its result is `FIRED` when its `fires` condition held, `SILENT` when it did not, and `REFUSED` when the check is the comparator and its capture or comparison refused. Rules: [`mutants-format.md`](mutants-format.md), `[checks.<name>]` and "The output".
- **Clause.** One of the five requirements a command meets to be a subject: it takes an output path and writes one file, it is deterministic, it exits non-zero on failure, it prints nothing that moves and writes no machine fact, and it runs under the census's environment. `probe` checks all five. Rules: [`subject-requirements.md`](subject-requirements.md), "The five clauses".
- **Clone.** The copy of a pinned input's repository that golden-census makes with `git clone` and keeps between captures, under the clone cache. In a manifest the placeholder `<CLONE>` is substituted with the clone's directory; in a golden the census's `clone` fold prints the same token in place of that directory. Rules: [`manifest-format.md`](manifest-format.md), `[inputs.<name>]`, and the skill's `references/machine.md`, "The clone cache".
- **Compare.** A byte comparison of a golden directory with a fresh capture, or with a capture recorded earlier (`--against`). Normalization happens at capture time, never at compare time. Rules: "Commands and exit codes" below, and [`manifest-format.md`](manifest-format.md), "What a manifest is NOT".
- **Consumer.** The project that uses golden-census on a subject. It owns the manifest, the census, the mutants file and the golden, and commits them beside the subject.
- **Contraband scan.** The check a capture runs over every recorded text for a path that is about the machine: the home directory, the checkout, the temp root and the directories golden-census made. A hit refuses the capture and names the file, the line and the token. `probe` runs the same scan. `probe`'s clause 5 is a different check: it looks for the values of variables the built environment did NOT pass, never for a passed-through value. Rules: [`census-format.md`](census-format.md), "The environment rule", and [`subject-requirements.md`](subject-requirements.md), clause 4.
- **Control.** The planted case beside a pin or a fold that proves the row matters: the named surface moves without the pin and holds with it; the fold's sample line folds and a path golden-census did not make survives. The census's controls run in front of every `capture`, `compare` and `mutants`, and their tally is printed beside the verdict. A control that cannot run is a disclosed SKIP. Rules: [`census-format.md`](census-format.md), `pin` and `fold`.
- **Fixed-width directory.** The `TMPDIR` golden-census makes for the subject when the census pins `<FIXED-WIDTH-DIR:N>`: a new directory of exactly `N` characters for every run, so that a temp path reaching an output folds as one token of constant length. The shipped templates pin 51, which is why the temp root may be at most 49 characters. The census's `fixed-width-dir` fold prints it as a token the consumer chooses; the shipped example spells it `<ENGINE-TMPDIR>`. Rules: [`census-format.md`](census-format.md), `pin`.
- **Fold.** A census row that lets an input vary and replaces the token it leaves in the output with a placeholder, at capture time. The three kinds are `path` (a directory golden-census knows), `regex` (a group inside a line) and `json-fields` (named fields of a JSON document). A fold's placeholder is printed in the golden and never typed into a manifest. Folding is the capture's normalization: it runs at capture time only, so a changed fold means a new capture. Rules: [`census-format.md`](census-format.md), `fold`.
- **Golden.** The recorded output of a program, kept and committed as the reference that a later run is compared with, byte for byte. In golden-census, a golden holds the program's normalized output for every row of the manifest. A golden records a bug as faithfully as a feature: `IDENTICAL` means unchanged, never correct. The golden directory is what a capture writes: one subdirectory per input holding `<surface>.out`, `<surface>.err`, `<surface>.exit`, the written file, `<surface>.skip` for a skipped surface, and one `surfaces.json`, the marker that makes a directory a capture. Rules: [`manifest-format.md`](manifest-format.md), "The golden directory".
- **Hole.** A token `<<HOLE:NAME>>` that `init` leaves in a file where only the project knows the value. Every command refuses a manifest or a census that still carries one, naming it. `mutants` refuses a mutants file that still carries one. No command refuses a hole in a template's runner, so the runner is probed before the manifest's holes are filled. Rules: [`adding-a-template.md`](adding-a-template.md), "Holes after `init`".
- **Input.** Two things, in two files. In the manifest, an `[inputs.<name>]` table: a named bundle of arguments the subject is run over, such as a tree, a fixture, a clone, or nothing. In the census, an `[[input]]` row: one thing outside the subject's code that can change its output. The document uses the word in the manifest's sense unless it says census. Rules: [`manifest-format.md`](manifest-format.md), `[inputs.<name>]`; [`census-format.md`](census-format.md), "File format".
- **Manifest.** The file that says what to run: one subject, the inputs it is run over, the surfaces recorded for each input, and the movements a comparison may permit. It is `manifest.toml`, written by `init` and committed by the consumer. Every command finds the census through it. Rules: [`manifest-format.md`](manifest-format.md).
- **Movement.** A row whose recorded bytes differ from the golden's; golden-census says the row *moved*. A code change that leaves every row's bytes as they were moved nothing. A permitted movement is one a `[[movements]]` row of the manifest or an `--allow-diff` line names with its attribution; `compare` prints it as `[ALLOWED]` and the verdict as `IDENTICAL (N permitted movement)`. Any other movement is a `[DIFF]`. Rules: [`manifest-format.md`](manifest-format.md), `[[movements]]`.
- **Mutant.** One deliberate `find`/`replace` edit to one committed file of the subject, with the checks expected to catch it. `mutants` plants each in a repo-shaped copy, runs every check and prints a table of mutant by check. A mutant no expected check catches is a hole in the net: a fault of the checks, not of the subject. Rules: [`mutants-format.md`](mutants-format.md).
- **Mutants file.** The file that lists the checks and the mutants. It is `mutants.toml`, written by `init` and committed by the consumer. Rules: [`mutants-format.md`](mutants-format.md).
- **Neutral three.** The manifest, the census and the mutants file as `init` writes them with no `--template`: enough for a program that already runs from a command line. A template writes its runner and wrapper on top of them.
- **Null mutant.** The unmutated copy of the subject, run through every check before any mutant is planted. A check that fires on the null mutant refuses the run: it would fire at anything, and proves nothing about the net. Rules: [`mutants-format.md`](mutants-format.md), "Mechanics, in order".
- **Passthrough.** A variable copied by name from golden-census's own environment into the subject's. The census lists the names and the reason beside each; everything not pinned or passed through is absent from the subject's environment. Rules: [`census-format.md`](census-format.md), "The environment rule".
- **Pin.** A census row that holds an input at a constant for every subject run, with the control that proves the constant matters. Rules: [`census-format.md`](census-format.md), `pin`.
- **Placeholder.** A token typed into a manifest, a census or a mutants file that golden-census substitutes before the run: `<ROOT>`, `<WORK>`, `<WRITES>`, `<PYTHON>`, `<HERE>`, `<CLONE>` and the rest. A token the program prints in place of a machine path, such as `<REPO>` or `<TMPROOT>`, is a fold's placeholder and is never typed into a manifest. Rules: [`manifest-format.md`](manifest-format.md), "Placeholders"; [`census-format.md`](census-format.md), "File format".
- **Precondition.** A census row stating a fact that must hold before a capture or compare runs, such as a tool being installed or a file matching its checksum. When it does not hold the command is refused at exit 2, never failed. Rules: [`census-format.md`](census-format.md), `precondition`.
- **Re-baseline.** Replacing the committed golden with a new capture, `capture --out <GOLDEN> --force`, after a scratch capture compared against the old golden has shown exactly which rows move. It is a deliberate act, never the shortest command form. Rules: the skill's `references/rebaseline.md`.
- **Refusal.** A command stopping before it makes a verdict: one `REFUSED:` sentence naming what was found, a `next:` line saying what to do, and exit 2. A refusal is a statement about the run, never about the subject. A command line the parser cannot read is refused the same way: `REFUSED: golden-census <command> could not read its command line: …`, with the parser's own words after the colon.
- **Row.** One input crossed with one surface: one golden record, named `<input>/<surface>`.
- **Runner.** A small program in the subject's language that gives a command line to code that has none of its own, such as a function or a module, so golden-census can start it like any other command. The shipped templates carry one each; [`subject-requirements.md`](subject-requirements.md), "Writing a runner", says how to write one.
- **Skip.** A row, a control or an arm that did not run, printed as a `[SKIP]` line with its reason. A skip is never a pass. A surface the manifest declares unrunnable, with `skip = "…"`, records the reason as its golden, in a `.skip` file, so an absent recording is never mistaken for a surface nobody thought of. `compare` prints a `[SKIP]` line for a row that is a skip on both sides. The tally counts the controls and arms skipped: `N/N census controls passed, K arm(s) SKIPPED (disclosed, never a pass)`. Rules: [`manifest-format.md`](manifest-format.md), `[surfaces.<name>]`.
- **State.** A census row that records an input's value in the capture log for later attribution and pins nothing: a toolchain version, say. Rules: [`census-format.md`](census-format.md), `state`.
- **Subject.** The program under golden-census. golden-census drives it by subprocess only and never imports it.
- **Surface.** One thing the subject produces, named by a `[surfaces.<name>]` row of the manifest: an argument suffix that yields one recorded result. The default kind runs the subject once and records its stdout, stderr, exit code and written file; `matrix` and `tallies` are the two compacted kinds. Rules: [`manifest-format.md`](manifest-format.md), `[surfaces.<name>]`.
- **Tally.** The line that counts a block of controls or arms: `N/N census controls passed, K arm(s) SKIPPED (disclosed, never a pass)` in front of a capture, a comparison or a mutants run; `N/N passed` under `census`, `probe` and `--selfcheck`. A report quotes the tally beside the verdict.
- **Template.** What `init --template <NAME>` writes on top of the manifest, the census and the mutants file `init` always writes: a runner and a wrapper for one language or build tool, with the holes the project fills. `init --list` names the shipped ones. Rules: [`adding-a-template.md`](adding-a-template.md), and the skill's `references/templates.md`.
- **Temp root.** The directory under which golden-census makes its work directories: `TMPDIR` when set, otherwise the platform's default. It must be an absolute path of at most 49 characters when the census pins a 51-character fixed-width directory; a wider root is refused, and the refusal's `next:` line names a root that fits. Rules: the skill's `references/machine.md`, "The temp root".
- **Verdict.** The line a command closes with and a report quotes: `IDENTICAL` or `N differing row(s)` from `compare`, `N/N mutants caught by every check they expect` from `mutants`, `N/N passed` from `probe`, `census` and `--selfcheck`, `capture complete` or `--twice: N files, byte-identical`, with `K of N rows recorded no output from the subject:` under it when rows did not run or printed nothing, from `capture`.
- **Work directory.** The new directory golden-census makes for each run under the temp root, holding only what the manifest's `[[setup]]` and `[files]` put there. The manifest spells it `<WORK>`; the census's `work` fold prints it as `<TMPROOT>` in a golden. Rules: [`census-format.md`](census-format.md), "File format", and [`manifest-format.md`](manifest-format.md), "Placeholders".
- **`<WRITES>`.** The placeholder for the one file a surface writes: golden-census substitutes a path under the work directory and records the file the subject wrote there. A surface that only prints has no `writes`. Rules: [`manifest-format.md`](manifest-format.md), `[surfaces.<name>]`, and [`subject-requirements.md`](subject-requirements.md), clause 1.

## Commands and exit codes

There are six subcommands and three whole-program flags: `--version`, `--selfcheck` and `--selftest`.

| Command | What it does | Exit |
|---|---|---|
| `capture` | Runs every row of a manifest and records the normalized bytes into a directory. | 0 recorded; 2 refused |
| `compare` | Compares a golden directory with a fresh capture, or with one recorded earlier. | 0 `IDENTICAL`; 1 differing rows; 2 refused |
| `census` | Reads a census, runs its controls, checks its preconditions and prints its state. That is everything a capture does around the runs, without the runs. A red-control refusal sends you to it. | 0 pass; 1 a control failed; 2 refused |
| `mutants` | Plants every mutant in a repo-shaped copy of the subject and prints which checks caught it. | 0 all caught; 1 a hole in the net or a REFUSED mutant; 2 refused |
| `probe` | Runs a candidate command twice and reports the five clauses of [`subject-requirements.md`](subject-requirements.md). It takes no manifest: it answers whether a command can BE a subject. | 0 all five pass; 1 a clause failed; 2 refused |
| `init` | Writes a project's manifest, census and mutants file from a template. Every project fact is left as a marked hole. | 0 written; 2 refused |
| no arguments | Prints the whole `--help` text. | 2 |

Exit codes: 0 a pass or IDENTICAL, 1 a FAIL or differing rows, 2 REFUSED, 130 or 143 interrupted.

An exit 1 is a statement about what the command measured: the subject under `compare`, your census under `census`, your checks under `mutants`, golden-census itself under `--selfcheck`. An exit 2 is a statement about the run: a path, a precondition, an unfilled hole, or a subject that would not hold still under `--twice`. No verdict was made.

Every `REFUSED:` sentence is followed by a `next:` line saying what to do about it. A command line the parser cannot read is one of them: `REFUSED: golden-census <command> could not read its command line: …`, with the parser's own words after the colon, at exit 2. Its `next:` line says to run the command with `--help`.

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
| `--template NAME` | `init` | The template written on top of the manifest, the census and the mutants file. An unknown name is refused, and the refusal lists the shipped ones. |
| `--list` | `init` | Prints `name — summary` for every shipped template and writes nothing. |
| `--selfcheck` | whole program | Runs golden-census's own controls and exits. |
| `--selftest` | whole program | Runs the whole app against its bundled fixture and exits. |
| `--version` | whole program | Prints the version and exits. |
| `--manifest FILE` | whole program | The manifest `--selfcheck` reads its census from. Optional with `--selfcheck`, where it adds that census's own controls. |

`--help` stands wherever a flag may, before any `--`. It prints the help and exits 0. The bare command's help ends with a `directories:` section that names where this install keeps `docs/`, the examples, the README, the skill and the templates, with `(not present)` after one the install lacks. After a subcommand it prints that subcommand's help. Nothing else on the command line runs, so `--selfcheck --help` runs no self-check.

### Rules for every flag

- **Give a flag once.** A flag given twice on the same side of the subcommand is refused before anything runs. The refusal names the flag, how many times it was given and, for a flag that takes a value, every value.
- **The parser speaks first.** A command line it cannot read is one `REFUSED:` sentence with argparse's own words in it and a `next:` line that points at `--help`. A required flag left out, a flag the command lacks, a flag without its value and a subcommand it does not know are turned down that way. If a flag was also given twice, the refusal for it comes only after the parser's error is fixed.
- **Only the flags marked repeatable repeat.**
- **An empty path is refused.** An empty or white-space value, as an unset or blank shell variable gives one, is refused. The flags are `--manifest`, `--out`, `--golden`, `--against`, `--allow-diff`, `--mutants`, every `compare --command` element and `probe --census`, and the directory `init` takes. The refusal names the flag. An empty value is never read as the flag left out, or as the current directory. `probe --writes-env` is refused an empty or white-space name the same way.
- **Paths are checked before the controls run.** A path golden-census refuses costs one sentence at exit 2 and no run of the subject. The checked paths are `--manifest`, then `--golden`, `--against` and `--allow-diff`, then the `--input` names, then `--out` and whether a capture can land there, then `--mutants`. `probe --census` and `init`'s directory are checked too. Those two commands run no controls.
- **Some paths are read again.** `--golden`, `--against` and `--allow-diff` are read again where the command uses them. A verdict is of the golden and the table as they stand once the controls have run.

### Rules for one flag

- **`--manifest`.**
  - `probe` and `init` take no manifest. They refuse the flag as a command line the parser cannot read, `REFUSED: golden-census <command> could not read its command line: unrecognized arguments: --manifest …`, at exit 2 (`init` lists the flag's value after it; `probe` takes the value as part of the candidate).
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
