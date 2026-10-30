# Commands and flags

Open this file for the rule of a flag, or when a refusal names one. `SKILL.md` carries every subcommand and every flag once. This file carries the rules.

## Run every command the same way

`SKILL.md` says it: send every command's output to a file and read the file as UTF-8. golden-census keeps no clock, so the deadline is yours; it ends no run for you. It keeps no size either: every byte a child prints is held in memory with no limit, so a child that prints without end is yours to stop. A child started in a session of its own is outside the run's process group, so the sweep and the process-group line never reach it: it is the subject's to stop.

Why the file matters:

- A run that hangs or crashes leaves its partial output in the file, where you can read it. On a pipe it is out of reach until the run ends.
- A crashed run looks like a stuck one from outside. The children it left behind hold its stdout open.
- Nearly every command opens with one line that names the run's process group and the command that kills everything the run started. "When a run is stuck or crashed" in `SKILL.md` says what to do with it. The commands that print no such line are `--version`, `--help` and a flag refused before anything starts.
- A reader that stops early, such as `| head`, closes standard output while the run still writes. golden-census refuses, on standard error, at exit 2:

  ```
  REFUSED: standard output closed while golden-census was still writing its verdict (a reader such as `head` stopped reading), so the rest of it is missing or cut short; a command that had not finished took back what it wrote.
  ```

- Closing standard output (`>&-`) is refused before anything is parsed:

  ```
  REFUSED: standard output is unusable (closed, as with `>&-`). golden-census writes its whole verdict to standard output and does not run blind.
  ```

- A full disk or a read-only file refuses the writes the same way: `REFUSED: standard output refused a write (<the operating system's words>) while golden-census was still writing its verdict …`, on standard error, at exit 2.
- A verdict you cut short is no verdict. Never report a run whose output you did not read to the end.

## `--help`, no arguments, and exit codes

- `--help` stands wherever a flag may stand, before any `--`. It prints the help and exits 0. Nothing else on the command line runs. `golden-census --selfcheck --help` prints the help and runs no self-check.
- `golden-census` with no arguments prints the usage block and exits 2.
- The exit codes are in `SKILL.md`, under "Reading the verdict".
- The parser's own usage errors print `golden-census: error: …`, or `golden-census <command>: error: …` for a subcommand's own flags, at exit 2. They carry no `REFUSED:` line and no `next:` line.

## Rules every flag follows

1. **Give a flag once.** A flag given twice on the same side of the subcommand is refused before anything runs. It is never read as its last value. The refusal names the flag, how many times it was given and every value.
2. **The parser speaks first.** Its own refusals name only what the parser names. A required flag you left out, or a flag the command does not have, is the refusal you get. A flag you also gave twice is not named until that is fixed. For example:

   ```
   golden-census compare: error: the following arguments are required: --manifest
   ```

3. **Only the flags marked repeatable repeat.** They are `--input`, `--only` and `compare --command`.
4. **An empty path is refused.** An empty or white-space value, as an unset or blank shell variable gives one, is never read as the flag left out or as the current directory. The flags are `--manifest`, `--out`, `--golden`, `--against`, `--allow-diff`, `--mutants`, every `compare --command` element and `probe --census`, and the directory `init` takes. `probe --writes-env` is refused an empty or white-space name the same way.
5. **Paths are checked before the controls run.** A refused path costs one `REFUSED:` sentence at exit 2 and no run of the subject. Fix the path and run again. After the temp root (`references/machine.md`), the order of the checks is: `--manifest`, then `--golden`, `--against` and `--allow-diff`, then the `--input` names, then `--out` and whether a capture can land there, then `--mutants`. `probe --census` and the directory `init` takes are checked too. Those two commands run no controls.
6. **Some paths are read again.** `--golden`, `--against` and `--allow-diff` are read again where the command uses them. A verdict is of the golden and the table as they stand once the census's controls have run.

## The flag table

One row per flag and command. A flag that takes a value shows its placeholder: `FILE`, `DIR`, `NAME` or `ARG`. The placeholder names the kind of value and is not part of the flag.

| Flag | Where | Rule |
|---|---|---|
| `--manifest FILE` | `capture` | Required. The manifest to read. There is no default. |
| `--out DIR` | `capture` | Required. Where the capture lands. See "`--out`". |
| `--input NAME` | `capture` | Repeatable. Restricts the capture to that `[inputs.<name>]`. |
| `--force` | `capture` | Replaces an `--out` that holds a capture. The only way to overwrite a golden. See "`--force`". |
| `--twice` | `capture` | Records the set twice. Refuses at exit 2 if the two captures differ, and names the row and the first differing line. |
| `--manifest FILE` | `compare` | Required, even with `--against`: the permitted movements come from the manifest. |
| `--golden DIR` | `compare` | Required. The committed golden set. |
| `--against DIR` | `compare` | Compares a capture recorded earlier and runs nothing. Neither side is normalized again. |
| `--allow-diff FILE` | `compare` | Permits movements this once, as `path :: attribution` lines. See "`--allow-diff`". |
| `--command ARG` | `compare` | Repeatable. Runs the fresh capture with this argv in place of the manifest's `command`. See "`--command`". |
| `--manifest FILE` | `census` | Required. The manifest whose census is read. |
| `--manifest FILE` | `mutants` | Required. The manifest of the subject the mutants are planted in. |
| `--mutants FILE` | `mutants` | Required. The mutants file. |
| `--only NAME` | `mutants` | Repeatable. Plants only the named mutant. The null mutant runs either way. |
| `--census FILE` | `probe` | The census whose environment the candidate runs under. Without it, a built-in default applies. |
| `--writes-env NAME` | `probe` | Exports the output path as this variable instead of substituting `<WRITES>` in the argv. |
| `--template NAME` | `init` | The template written on top of the neutral three. |
| `--list` | `init` | Prints `name — summary` for every shipped template and writes nothing. |
| `--selfcheck` | whole program | Runs golden-census's own controls and exits. |
| `--selftest` | whole program | Runs the whole app against its bundled fixture and exits. |
| `--version` | whole program | Prints the version and exits. |
| `--manifest FILE` | whole program, beside `--selfcheck` | Optional. Adds that manifest's census controls to the run. |

## Rules for one flag

### `--manifest`

- `probe` and `init` take no manifest. They reject the flag with the parser's own error, at exit 2, with no `REFUSED:` line and no `next:` line:

  ```
  golden-census: error: unrecognized arguments: --manifest
  ```

- Given alone, with no command, it is refused.
- Given before a subcommand, it is refused too. A command's manifest follows the command.
- `--selftest` reads golden-census's bundled fixture and takes no `--manifest`. It refuses one, and the `next:` line says to use `--selfcheck --manifest M` for a consumer's census.

### `--out`

- A path that does not exist is created. An existing empty directory is used as it is; the header says `[empty directory]`.
- A directory that holds a capture is refused without `--force`.
- A file golden-census did not write, such as a `.DS_Store`, beside a capture already there, is refused with the file named; with no capture there, the refusal is the one for a directory that is not a capture. Delete the file, or point `--out` at a path that does not exist yet.
- A symbolic link is refused, as `--out` itself or anywhere inside a directory that holds a capture, whatever `--force` and `--input` say. The refusal names the link and its target. `--force` replaces the directory whole, and what a link points at is not what you named.
- golden-census records the capture under the temp root and moves it into place, through a new directory beside `--out`. The directory `--out` sits in must therefore be writable.
- A capture refused or failed before that move leaves `--out` exactly as it was. If `--out` was absent, it stays absent.
- Whether `--out` replaces a capture is decided when the command starts. A capture the subject writes into `--out` during the controls is refused, never replaced.
- A capture killed outright can leave a `.golden-census-capture-*` directory beside `--out`. Look in it before you delete it. When the kill landed mid-swap, it holds the previous golden under `retired/`.
- After the move, two events each say `--out holds the new capture` on standard error, where it can be written:
  - Standard output refusing the capture's last line. That is a refusal at exit 2. When the reader merely stopped, the line is `standard output closed as the capture completed: --out holds the new capture.` at exit 0.
  - An interruption: `interrupted after the capture landed: --out holds the new capture.` at exit 130 or 143.
- A `capture` that exits 2, 130 or 143 with nothing on standard error after a long run (a `> run.log 2>&1` on a full disk) may hold the new capture. List `--out` to find out.

### `--input`

- It restricts a capture to the named `[inputs.<name>]`. Give it once per input.
- A name no input has is refused.
- With `--force`, only that input's directory is replaced. See "`--force`".

### `--force`

- It is a deliberate act. Attribute it in your report.
- It replaces what this manifest's capture records, and nothing else. With `--input NAME`, it replaces only that input's directory, whole.
- It refuses, naming them, any file in the directory that this manifest's capture does not record: `s.out~`, a note, a stray `.skip`, a link, a file that appeared during the run. It refuses again right before the swap.
- A surface you removed, changed to or from a skip, or whose `writes` you changed leaves such a file. So does an input you removed. Delete the file or directory, then run `--force`.
- It refuses a `surfaces.json` it cannot read.

### `--golden` and `--against`

- A path that is not a directory is refused with nothing compared. So is a directory that holds no capture, a directory golden-census cannot read, and a capture that holds a symbolic link. `--against` follows the same rule.
- `compare --against` runs no subject and no census controls. It exits 0 on `IDENTICAL`, and it prints no controls tally.

### `--command`

- One flag per element of the argv, in order: `--command <PYTHON> --command <HERE>/runner.py`. An element that begins with `-` is written `--command=-I`.
- Elements are taken as given, an absolute path included. `<PYTHON>` and `<HERE>` resolve as in the manifest's `command`, and `<HERE>` is the manifest's directory. An unknown placeholder, a `<HERE>` path that is not there, and an empty or white-space element are each refused before anything runs.
- `compare` only, and refused beside `--against`, which runs nothing. `capture` has no `--command`.
- Inputs, surfaces, folds, the contraband scan and the census's controls are the manifest's and the census's; the controls run the same command as the capture.
- The golden is the manifest's record: `surfaces.json` holds the arguments after the command, never the command, so the override moves no byte there. Only what the program printed can move a row.
- The `COMPARE` block gains `  command: <the argv, shell-quoted>` under `new:`, only when the flag was given. Quote it beside the verdict.

### `--allow-diff`

- The file is UTF-8 text. Each line is `path :: attribution`.
- A line whose first non-blank character is `#` is a comment. A blank line is skipped.
- A `#` later in a line is kept. `fixtures/results.json :: has # inside` permits `fixtures/results.json` with the attribution `has # inside`.
- A comment after a bare path is part of the path, and the row permits nothing. `fixtures/results.err # trailing` is reported as an unused row:

  ```
  unused: --allow-diff row 'fixtures/results.err # trailing' permits a movement that did not happen
  ```

- A line with no `::`, or nothing after it, reads `(no attribution)`.
- golden-census reads the file before the subject runs. A path it cannot read, or a file that is not UTF-8 text, is refused there with nothing run.
- It reads the table again once the controls have run. A table that cannot be read then is refused after the controls ran, with nothing captured.

### `--mutants` and `--only`

- A missing mutants file is refused.
- `--only` can only be used with names in the mutants file. Any name not in it is refused. `--only` checks only the named mutants in the preflight. A stale mutant you did not name is noticed by the bare `mutants` run and not by `--only`.

### `--census` and `--writes-env`

- `probe --census FILE` builds the candidate's environment from that census's pins and passthrough, the built-in census without the flag, and folds the banner through its `path` rows. It applies no fold to what the candidate prints or writes, so a timestamp a `regex` fold would remove is still red at clause 4. A missing file is refused.
- With it, clause 5 of the `probe` block lists that census's variables. A run under the shipped example's census listed `4 variable(s) passed — GOLDEN_CENSUS_CHILD, HOME, PATH, TMPDIR`.
- Without `--census`, clause 5 lists exactly six names: `COLUMNS, GOLDEN_CENSUS_CHILD, HOME, PATH, SOURCE_DATE_EPOCH, TMPDIR`. A list of five is a bug in golden-census. Report it.
- `--writes-env OUT_PATH` hands the output path to the candidate as the variable `OUT_PATH`, so the argv holds no `<WRITES>`.
- `probe` with no command is refused: `REFUSED: probe was given no command to run.`

### `--template` and `--list`

- An unknown template is refused, and the refusal lists the shipped ones.
- `init --list` writes nothing. Given a directory, it is refused. Given `--template`, it is refused. `references/templates.md` says which template to choose.
- `init` overwrites nothing. A file that exists is refused.

### `--selfcheck`, `--selftest` and `--version`

Each is a command of its own. Only `--selfcheck` takes a flag, `--manifest`.

- `--selfcheck` runs golden-census's own controls, each beside the planted case that proves it can go red. It prints `N/N passed, K arm(s) SKIPPED (disclosed, never a pass)` and exits 0 when every arm passed. With `--manifest FILE` it also runs that census's controls, so N and K grow. Both move with the census and the machine: quote the numbers you saw.
- `--selftest` runs the whole app against the fixture bundled inside the package: those same controls, then a capture, a comparison with its planted difference, the bundled mutants, the documents against the parser, the first line of every command, and every shipped template scaffolded. Each group prints a tally, and the last line is the version. It takes minutes, not seconds: run it in the background and send its output to a file.
- `--version` prints one line.
- Any of the three beside a subcommand, or `--selfcheck` beside `--selftest`, is refused by a sentence that names what was given. A subcommand missing a required flag gets the parser's own error first.
