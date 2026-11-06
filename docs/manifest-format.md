# The manifest: `manifest.toml`

The manifest tells golden-census what to run and what to record. It names one program, called the subject. It names the inputs the program is run over. It names the surfaces recorded for each input; a surface is one thing the program produces. And it names the movements a comparison may permit: recorded rows that are allowed to differ, each with the reason.

golden-census runs the program as a subprocess only. It never imports it, never reads anything out of it by name, and never runs its code in-process. Everything golden-census knows about the program is in this file and the files it names.

The manifest belongs to the project that uses golden-census. The project keeps it beside the program and commits it; `using-golden-census.md`, "Keeping the recording up to date", says who writes a row and when.

The manifest names a census file, described in [`census-format.md`](census-format.md): the manifest says what to run, the census says what is held constant around every run. golden-census reads both before the first capture. The third file, the mutants file, is described in [`mutants-format.md`](mutants-format.md).

The file is `manifest.toml`, written by `init` with its holes left for the project to fill. Every command refuses a manifest that still contains a hole.

This document covers:
1. File format
2. Placeholders
3. `[subject]`: the program
4. `[inputs.<name>]`: what the program is run over
5. `[surface-sets]`: a named list of surfaces
6. `[surfaces.<name>]`: one thing the program produces
7. `[[setup]]`: a command run before the rows
8. `[files."<name>"]`: a small text file written before any run
9. `[[movements]]`: rows a comparison may permit to differ
10. The golden directory
11. What a manifest is not
12. What golden-census refuses, by name
13. The shipped example

## File format

The file is TOML. Paths in it are relative to the manifest's own directory unless they begin with a placeholder.

Every key in the file must be one golden-census reads. A table with a key golden-census does not read is refused when the manifest is read; the refusal names the key, the table, and the keys the table accepts. This is so that a misspelled key cannot silently do nothing. The census and the mutants file follow the same rule. The one exception is `[surface-sets]`, whose keys are names the author chooses.

A `matrix` surface may take its rows from another file with `include`, in TOML or JSON by extension. `include` is a key of that surface kind only. Use it for a table nobody should write by hand, such as a refusal matrix of several hundred rows: a script the project keeps generates the file, and the project commits the generated file beside the manifest, so a capture never depends on the generator having run.

## Placeholders

These are the only substitutions golden-census makes, and it makes them in `[subject] command`, `[subject] version`, `args`, `writes`, `env` values, setup commands and counters. Everything else is passed as written. A token that looks like a placeholder and is not defined in that place is refused when the manifest is read, and the refusal lists what that place allows (`<TMP>` is not `<WORK>`).

| Placeholder | Stands for | Appears in the shipped example's goldens as |
|---|---|---|
| `<ROOT>` | the program's root, absolute; the working directory of every surface run (setup steps and counters run in `<WORK>`) | `<REPO>` |
| `<WORK>` | golden-census's scratch directory for this capture, absolute | `<TMPROOT>` |
| `<CLONE>` | the input's clone directory, for an input with `git`, absolute | `<CLONE>` |
| `<WRITES>` | the path this surface's `writes` names, after its own expansion | its parent is `<WORK>` |
| `<PYTHON>` | the interpreter running golden-census | never, because the program's own name is what is recorded |
| `<HERE>` | the directory this manifest is in | never (see below) |
| `<input>` | the current input's name, inside `writes` only | none |
| `<surface>` | the current surface's name, inside `writes` only | none |

The third column is not a rule. golden-census replaces each directory in the recording with whatever placeholder the census's matching `path` row names; the tokens shown are the ones `examples/python-function/census.toml` chose. A fold's token, such as `<REPO>`, `<TMPROOT>` or `<CWD>`, is something golden-census prints in place of a path. Never type one into a manifest.

`<HERE>` has its own rules:

- It is allowed only in the three commands golden-census runs: `[subject] command`, a `[[setup]]` command and a `counter`.
- Use it for a file beside the manifest, as opposed to one under `root` or `<WORK>`.
- An element that begins with `<HERE>` must name a file that exists. If it does not, the manifest is refused when it is read.
- `mutants` carries `<HERE>` onto the copy of the program when the manifest is inside the checkout; a manifest outside the checkout keeps its own directory. If the copy does not contain the file, golden-census refuses and names both paths.
- It never appears in a golden, because `command` is the prefix after which a row's argv is recorded, and a setup step's or counter's argv is not recorded.

The program's own `TMPDIR` is another directory golden-census makes, with a fixed width. The example folds it as `<ENGINE-TMPDIR>`. That fold is a census row, not a manifest one: see `<FIXED-WIDTH-DIR:N>` in `census-format.md`.

Two placeholders have no use in the shipped example. Invented fragments, not quoted from it:

```toml
# invented: <ROOT> where a surface hands the subject its own checkout.
env  = { PROJECT_ROOT = "<ROOT>" }

# invented: <CLONE> as the arguments of an input pinned with `git` and `sha`.
args = ["<CLONE>/src", "--tests", "<CLONE>/tests"]
```

`<HERE>` appears twice in the shipped example: the manifest's `command = ["<PYTHON>", "<HERE>/runner.py"]`, because the runner is beside the manifest and not under `root`, and the mutants file's `golden = "<HERE>/golden"`.

## `[subject]`: the program

```toml
[subject]
name    = "wordstats"                       # the product name, for the report
root    = "../.."                           # the checkout; cwd of every run
command = ["<PYTHON>", "<HERE>/runner.py"]  # <HERE> is this file's own directory
# version = ["--version"]                   # optional: args that print the version
census  = "census.toml"                     # required
```

- `command` is the argv prefix of every run. golden-census appends the input's `args`, then the surface's `args`.
- An element of `command` that is an absolute path under `root` is refused by `mutants`, which would otherwise run your tree instead of its copy. Write it relative to `root`, and golden-census carries it onto the copy.
- `surfaces.json` records a row's argv as everything after `command`, so a golden never contains the interpreter path or the entry point.
- `compare --command ARG …` runs the fresh capture with a different argv in place of `command`; nothing else in the manifest changes. Its elements are checked as `command`'s are, with `<HERE>` as this manifest's directory; the skill's `references/commands.md`, "`--command`", has the rest. Because a golden holds no command, the golden is the same whichever command ran.
- `version` runs once per capture, and its result is printed in the capture log beside the census state. It is not part of the golden unless a surface also records it.

## `[inputs.<name>]`: what the program is run over

An input is a named set of arguments the program is run over: a tree, a fixture, a clone, or nothing.

The name must be one path component, because a capture writes every surface of an input into a directory of that name under `--out`. A name containing a separator, or naming this directory or its parent, would write outside `--out` and is refused when the manifest is read. Two names that are the same once case and Unicode normalization are ignored are refused, naming both: `Café` beside `café`, or `é` as one character beside `e` with a combining accent. On a file system that ignores those differences they would be one directory, and the second input's recording would replace the first's, so a change to the first input would compare `IDENTICAL`.

```toml
[inputs."fixtures"]                         # the shipped example's own input
args     = []                               # this input takes no arguments
surfaces = ["results"]                      # a list, or the bare name of a surface set

# The rest are invented for this document: the shipped example has one input.
[inputs.demo]
args     = ["examples/demo"]
surfaces = "tree"                           # a surface-set name, or a list

[inputs.cloned]
git      = "https://example.invalid/some/repo"
sha      = "0000000000000000000000000000000000000000"
args     = ["<CLONE>/src", "--tests", "<CLONE>/tests"]
surfaces = "tree"
expect_counts = { rows = 0 }

[inputs._tool]                              # the input-less surfaces
args     = []
surfaces = ["help", "version"]
```

- `args` are put before every surface's `args` for this input.
- `args = []` is a real input. Surfaces that take no tree, such as `--help`, `--version` or a refusal matrix, go under it.
- `surfaces` lists the surfaces recorded for this input. An entry is a surface name or a surface-set name; a set name expands in place. The value may also be the bare name of one set.
- `expect_counts` is a baseline the author states, printed as `AGREES` or `DIFFERS` beside a counter's result in the capture log. It is not a golden and never blocks. An empty table is refused when the manifest is read, and so is an input that sets `expect_counts` but names no surface with a `counter`, counting the members of its surface sets.
- `git` and `sha` pin the input to one commit of a repository. The rules follow, in six groups.

### The pin

- `git` and `sha` come together or not at all. An empty string counts as absent, so `git = ""` beside a `sha` is refused when the manifest is read; read as a pin, it would capture against the local tree while the manifest claims a clone.
- `sha` is the commit's id as `git rev-parse HEAD` prints it, in lowercase hexadecimal, or a prefix of it. Anything else is refused.
- A `git` address containing a password is refused. Keep the credential in a git credential helper: the manifest is committed, and the capture log prints the address.
- A `git` of `.` or `..`, or one beginning with `-`, is refused: a file system reads the first two as directions, and git reads the third as an option.
- golden-census checks out `sha` as a commit id, never as a branch of that name. It requires the full id of the checked-out commit to begin with the pin. Where git prefers a branch or tag named like the pin, golden-census accepts it only if its commit's id begins with the pin.
- After checkout, `git status --porcelain` must print nothing. The skill's `references/machine.md`, "The settings of git", lists the settings golden-census gives every git it runs, so that the global git configuration cannot change an answer.

### Where the clone lives

- A pinned input is cloned whole, with the full history: a plain `git clone` with no depth limit and no size check, once per repository and commit, kept until you delete it. Pin a large repository knowing that its full clone lands on this disk.
- The clone goes in the user's cache directory: `~/Library/Caches/golden-census/` on macOS, `$XDG_CACHE_HOME/golden-census/` or `~/.cache/golden-census/` on Linux. Never under the temp root. Its path is `golden-census-trees/<repository>/<sha>/`, where `<repository>` is the `git` value as git resolves it (a path that names a file or directory becomes its real absolute path; any other address stays as written), with every character that is not an ASCII letter, a digit, `.`, `_` or `-` replaced by `-`, and `<sha>` is the pin as the manifest spells it.
- Two inputs that pin the same repository at the same commit share the clone, whether they are in one manifest or two. A kept clone is used only when its `remote.origin.url` is the address asked for; two addresses that land in one folder are a `SKIP` naming both.
- golden-census keeps no index of the cache and no other file beside the clones. Deleting a commit, a repository or the whole cache breaks nothing except that the next run clones again. golden-census removes nothing it did not make in the current run, and keeps clones nowhere else.
- The cache persists, so a clone from an earlier run can be stale. A git step that fails inside such a clone is reported, and so is a kept clone that is not clean. The reason in the log names the directory and tells you to delete it and capture again.

### Checks before the clone

- golden-census refuses a cache directory it cannot make or write; a `HOME` that is not an absolute path or contains `..`; and on Linux an `XDG_CACHE_HOME` containing `..`.
- The refusal comes when the command is about to clone, after whatever ran before. A command that clones nothing never makes these checks and never makes the folder.

### When the clone cannot be used

- An input whose clone cannot be made has all its rows recorded as `SKIP`. That is never a pass, and it never bypasses the network policy. The log gives the reason: where a git command did not exit 0, the reason names it, says how it ended, and quotes its stderr or says it printed nothing.
- A clone folder found with files in it and no `.git` directory is a clone cut short: the input's rows are skipped and the reason names the folder to delete.
- A clone directory or its `.git` that is a symbolic link is a `SKIP` naming the linked path.
- A `[[setup]]` step or the `[subject] version` command runs before the clone is entered. One that writes into a kept clone makes the input a `SKIP` in the same run, before any row.
- Whether a skipped clone blocks a hand-back is the project's rule. golden-census prints the `SKIP` where it cannot be missed.

### A clone must stay clean

- A row or a setup step must not write anything `git status` would list, in the program's tree or in a pinned tree. It writes under `<WORK>`, or where the repository's `.gitignore` or `.git/info/exclude` ignores the file. In the clones golden-census made this is enforced; in the program's own tree it is a rule you keep, and a capture that breaks it still succeeds.
- After the rows, golden-census runs `git status --porcelain` again in every clone the rows used. It also compares the clone's `.git/config`, `.git/hooks/` and `.git/info/` before and after.
- If anything was left or changed, the command is refused, exit 2, naming every input that entered the clone in order, the clone, and what git lists or which parts changed. A capture's `--out` is left as it was.

### Files git ignores in a shared clone

- Files git ignores persist in a shared clone across runs, inputs and manifests. They are not the pinned content.
- A kept clone that holds some is reported by a second `clone:` line in the log, naming their count and the first three. The line changes no verdict and no exit code.
- A clone's `.git/info/exclude` goes with the clone when it is deleted; deleting the folder starts clean.
- `census` and `mutants` print these lines under their own headings: see `census-format.md` (the `vary` control) and `mutants-format.md` ("The output").

## `[surface-sets]`: a named list of surfaces

```toml
[surface-sets]
tree = ["report", "export"]
```

A surface set is one name for a list of surfaces, so that several inputs need not repeat the list and a new surface is added in one place. The shipped example carries this table commented out, because one input over one surface has nothing to abbreviate.

A set name is used as an entry in an input's `surfaces` list. It expands in place, keeping the list's order. Invented, since the example has no set:

```toml
[inputs.demo]
surfaces = ["tree", "extra"]                # the two of `tree`, then the third
```

- An input that names a set and one of its members records that surface once.
- An entry that is neither a surface nor a set is refused, and the refusal says both things an entry can be.
- A set with the same name as a `[surfaces.<name>]` table is refused when the manifest is read, whether or not any input lists it, because an entry of that name would be read as the set and the surface would never run.

## `[surfaces.<name>]`: one thing the program produces

The name must be one path component, for the same reason as an input's: a capture writes `<out>/<input>/<surface>.out`. A name containing a separator, or naming this directory or its parent, is refused when the manifest is read.

A surface is one of four kinds. `kind = "run"` is the default and needs no `kind` key.

### `run`: one subprocess

Recorded as `<input>/<surface>.out`, `.err` and `.exit`, plus `.<ext>` for a written file.

```toml
[surfaces."results"]                         # the shipped example's own surface
args   = ["<WRITES>"]
writes = "<WORK>/<input>-<surface>.json"     # captured as results.json

# Invented for this document: the keys the example leaves commented out.
[surfaces.report]
args = []

[surfaces.export]
args    = ["--quiet", "--json", "<WRITES>"]
writes  = "<WORK>/<input>-<surface>.json"
counter = ["<PYTHON>", "<HERE>/counts.py", "<WRITES>"]

[surfaces.extra]
args   = ["--quiet", "--extra"]
inputs = ["demo"]                            # narrows the input list

[surfaces.with-fixture]
args  = ["<WORK>/fixture/tree"]
env   = { FIXTURE_STORE = "<WORK>/fixture/store" }
needs = ["fixture"]                          # a setup step, below
```

- **stdout and stderr** must be UTF-8 text. A row that prints a byte that is not UTF-8 is refused when it runs, naming the stream, the byte and its offset. Make the command print UTF-8 there, or wrap it so that it writes the raw bytes to a file under `<WORK>` and prints a text dump of them.
- `writes` names the file the run is expected to write. The rules are below.
- `counter` is a command run after the surface. The rules are below.
- `inputs` limits a surface to some inputs. Use it when a surface set names a surface that some inputs must not run. A surface whose `inputs` leaves out an input that names it is refused before the first run.
- `env` adds variables to the census's environment for this run only. A variable the census pins cannot be overridden here, and naming one is refused. A `passthrough` variable can be overridden for this run.
- `<WRITES>` has the same value in `env` as in `args`, so a program told where to write through a variable writes the path once: `env = { GOLDEN_CENSUS_OUT = "<WRITES>" }` beside `writes = "<WORK>/…"`. `<WRITES>` on a surface with no `writes` is refused, naming the row.
- `needs` names the setup steps that must have run first (see `[[setup]]`).
- `record_argv` belongs to a `matrix` surface only and is refused on any other kind when the manifest is read, naming the surface, the key and the kind.

#### `writes`

- golden-census captures the file after the run as `<surface>.<ext>`, taking the extension from the path. A path with no extension would fall back to `out`, which is a stream's name, so such a path is always refused.
- The path must begin with `<WORK>/`. The rest must not be absolute, must not contain `..`, and must not have an empty component. Any other path is refused when the manifest is read.
- golden-census deletes whatever is at the path before the run, so a file left by an earlier row, a `[files]` entry or a setup step is never recorded as this run's. If the path is a symbolic link to a file when the row starts, only the link is removed; the file it points to is kept.
- A run that does not write the file records nothing under that extension; the `.exit` and `.err` say why.
- A `writes` path that a symbolic link leads outside `<WORK>` is refused when the row runs, before anything is removed, naming the row, the path as written and where it resolves. The link may come from a setup step, an earlier row, or a link put in place of the temp root. golden-census removes nothing outside the work directory. A path that the row's own command makes lead outside `<WORK>` is refused after the row runs, naming the same three things, and nothing is recorded from it.
- A written JSON file passes through the census's `json-fields` folds and their round-trip check.
- Five file names are golden-census's own in a capture: `<surface>.out`, `.err`, `.exit`, `.skip` and `surfaces.json`. A `writes` that would be recorded under one of them, in any case, is refused when the manifest is read. If the file were recorded over a stream, it would replace the stream's golden. If it were recorded as `.skip`, `compare` would report a surface that ran as one that ran on neither side.
- The file must be UTF-8 text. golden-census reads it, normalizes it and compares it line by line. A file it cannot decode is refused when the row runs, naming the row and the file. For a file that is not text, such as a database, an archive or an image, make the row's command a wrapper that writes the file under `<WORK>` and a deterministic text dump of it to `<WRITES>`, and give `writes` the dump's extension.

#### `counter`

A counter is a command of the project's own that is handed the written file and prints a JSON object of integers. golden-census records the numbers; the project's script knows what they mean.

- It belongs on a `run` surface with `writes`. On any other surface it would never run, so it is refused when the manifest is read.
- golden-census records the counts as `_counts` under the input in `surfaces.json`. There is one `_counts` per input, so an input may name only one surface with a `counter`; two are refused when the manifest is read, counting the expanded `surfaces` list.
- A run that wrote no file runs no counter. The capture log says `counter not run` under its row, and no `_counts` is recorded.
- A counter that does not exit 0, or prints anything but a JSON object, refuses the capture, with a block naming the counter's command after `ran:`. A counter that could not be started refuses with a block beginning `about to run:`.
- `expect_counts` never blocks; it prints `AGREES` or `DIFFERS` in the log.
- The counter runs in `<WORK>`. Name it `<HERE>/…`, since it lives beside the manifest.

### `skip`: a surface declared unrunnable

```toml
[surfaces.unrunnable]
skip = "why this surface cannot be recorded here, as one sentence"
```

The reason is recorded as the golden, as `<input>/<surface>.skip`, and in `surfaces.json` with `status = "skipped"`. The row exists so that an absent golden is never mistaken for a surface nobody thought of. The sentence is yours, and it is the same on every machine, which is what makes it a golden.

An input pinned to a `git`/`sha` tree that could not be cloned also records a `.skip` for each surface, holding one fixed sentence. The actual reason comes from git, the network or the operating system, so it goes to the log and never into the golden.

### `matrix`: many small runs recorded as one file

A `matrix` surface is built for refusal matrices, where every row prints the same usage block and a one-line refusal. Storing the usage block seven hundred times would hide the differences.

```toml
[surfaces.flagmatrix]
kind        = "matrix"
include     = "flagmatrix.json"              # [{label, args}, ...], committed beside this manifest
record_argv = ["the rows of flagmatrix.json"]
```

- The included file is a JSON list of `{"label": "(mode, --flag)", "args": [...]}`, or the TOML equivalent as `[[rows]]`. A script the project owns generates it, and the project commits it. A capture never imports the program to learn its rows.
- Each row runs `command + input.args + row.args`, with the null device as standard input.
- A matrix surface has no `args` of its own; the key is refused on one when the manifest is read. The arguments go on the rows.
- `record_argv` is what `surfaces.json` records as the surface's argv, since there is no single argv. It is read only by the matrix recorder, which is why it is refused on every other kind: every other kind records the argv it really ran, and `shares_invocation_with` is derived from real argvs, so a key that could fake a shared argv must not sit in a manifest unread.
- A row whose stdout or stderr is not UTF-8 text refuses the capture, naming the row.

The record:

- `.out` begins with a header of three lines, `pairs: N`, `usage-prefix-lines: K` and `stdout-prefix-lines: J`, followed by the J lines every row printed first on stdout, each indented four spaces, then a blank line.
- Then, per row sorted by label, a line `<label> exit=<code>` and two sub-headings in this order, each indented two spaces: `stderr tail-newline=<yes|no>`, then `stdout tail-newline=<yes|no>`. Under each are that stream's lines after the common prefix of all rows is removed, indented four spaces. A stream that printed nothing beyond the prefix is one blank indented line, so an empty stream is recorded as empty. A line is what ends in `\n`, so a `\r` stays in its line.
- `.err` is the longest common prefix of every row's stderr, cut at a line break: the shared usage block. The common prefix of stdout is cut the same way and kept in the `.out` header.
- `.exit` is `0`; the per-row exit codes are in `.out`.

From a run on a scratch program with two rows, each printing a banner line and a row line on stdout:

```text
pairs: 2
usage-prefix-lines: 1
stdout-prefix-lines: 1
    stub 1.0

(a, --bogus) exit=2
  stderr tail-newline=yes
    error: bogus flag
  stdout tail-newline=yes
    rows: bogus
(b, --other) exit=2
  stderr tail-newline=yes
    error: other flag
  stdout tail-newline=yes
    rows: other
```

- The census's `path` folds apply to both halves of the record, as to a `run` row's `.out` and `.err`. The `regex` and `json-fields` folds do not: they are scoped to named `<input>/<surface>` rows, and a matrix record is a reduction of many runs, not one row's bytes.
- `tail-newline` exists because splitting on lines cannot tell `abc` from `abc\n`; without it, a stream that gained or lost its final newline would move no golden byte. golden-census's own control proves that `no` is a value the recorder can produce.

### `tallies`: one run reduced to its verdict lines

A `tallies` surface is for a self-test whose body prints timings and paths the project does not want recorded, but whose tallies it does.

```toml
[surfaces.tallies]
kind    = "tallies"
args    = ["--tallies"]
rule    = "="                                # a banner is fenced by two rules of this char
verdict = '^\s*\d+/\d+ passed\s*$'           # the expression matching each group's verdict line
failing = '^\s*(?:\[FAIL\]|actual:)'         # optional: lines recorded under their group's verdict
```

- A rule line is at least eight characters, all the `rule` character; a shorter line fences nothing.
- `.out` is `groups: N`, then `<banner>: <verdict>` per group in print order. A group with no verdict line records `<no tally line>`; it never disappears.
- `.err` is empty: the reduction is of stdout, and by declaration the run's stderr is not recorded here. `.exit` is the run's exit code.
- A line is what ends in `\n`. A rule line, `verdict` and `failing` are matched with one trailing `\r` set aside, so a transcript written with `\r\n` records the same groups; a `failing` line is recorded with its `\r`.
- A `verdict` or `failing` that is not a string or does not compile is refused when the manifest is read, naming the table and the key.
- `failing` is optional. It is a regular expression matched from the start of each line, like `verdict`. Every line of a group that matches is recorded under the group's verdict line, as printed and in order, so a failure that changed places or changed its evidence is a `[DIFF]` rather than a tally that stood still. Write it to reach the failing row's evidence, not only its name: a row can keep its name and count while its evidence changes. The recorded lines pass through the census's folds like any surface, so pick deterministic lines or fold what moves. The capture log's line for the surface says how many lines it caught, as `M failing line(s)`, so a pattern that reaches nothing shows as that. `failing` on any other kind is refused when the manifest is read.

From a run on a scratch program where `GROUP three` prints no verdict line; the capture log's line reads `tal: 3 group tallies, 2 failing line(s), exit 0`:

```text
groups: 3
GROUP one: 2/3 passed
  [FAIL] row a: wrong
  actual: 3
GROUP two: 3/3 passed
GROUP three: <no tally line>
```

The census's `path` folds, and every `regex` fold whose scope includes this row, apply to the recorded text.

### `writes` on a `matrix` or `tallies` surface

Either may have `writes`, and `<WRITES>` has its value there. golden-census expands and checks the path before the run as for a `run` row, clears it before the run (once, before a matrix's rows), and captures nothing from it: these kinds record stdout and stderr reductions only. Only a `run` row is refused after the run when its command made the path lead outside `<WORK>`.

## `[[setup]]`: a command run before the rows

A setup command runs once per capture, in the work directory, before the rows whose `needs` name it. Use it for a fixture that the program's own test code knows how to build: write a one-line runner script, and name it here. golden-census runs it as a subprocess and never imports the module.

```toml
[[setup]]
name    = "fixture"
command = ["<PYTHON>", "<HERE>/make_fixture.py", "<WORK>/fixture"]
```

- Every element is passed as written. A relative path names a path in the work directory. A script beside the manifest is named `<HERE>/…`; golden-census never looks beside the manifest for a name it was not given that way, and an argument that happens to share its name with a file there is never that file.
- A setup command that does not exit 0 refuses the capture, because a half-built fixture would produce goldens about the fixture, not the program. The refusal says how the command ended, its exit code or the signal, and quotes its stderr, folded, or says it printed nothing. The block under it names the command after `ran:` and the environment it was given. A step that could not be started refuses with a block beginning `about to run:`.
- Two `[[setup]]` tables with one `name` are refused when the manifest is read, naming both by number and both commands.

## `[files."<name>"]`: a small text file written before any run

```toml
[files."plan.txt"]
lines = ["the first line", "the second line"]
```

golden-census writes the file into `<WORK>` before any setup step or row runs. Use it for a surface that takes a file argument whose content is the manifest's to state, and refer to it as `<WORK>/plan.txt` in a surface's `args`.

- The key is a path under `<WORK>`; a nested key such as `"fixtures/a.txt"` is what the key is for. Every component must name something and the whole path must stay under `<WORK>`.
- A key that is absolute, contains `..`, or resolves to a directory (`"fixtures/"`, `"."`) is refused when the manifest is read.
- Two keys of which one is a directory above the other are refused: `"a"` beside `"a/b.txt"`, since `"a"` cannot be a file and a directory at once, and `"A"` beside `"a/b.txt"` on a case-insensitive file system. Keys are compared with case and Unicode normalization ignored, so an accent encoded two ways is one name. The refusal names every such pair, with the code points of two keys that print alike. `"a.txt"` and `"ab"` beside `"a/b.txt"` are two files and load.
- A key the operating system will not write, such as a name too long for the file system, is refused when the files are written, before any setup step or row, naming the table, `<WORK>/<name>` and the operating system's reason.

## `[[movements]]`: rows a comparison may permit to differ

```toml
[[movements]]
path        = "the-input/the-surface.out"
attribution = "the change that moved it, and the reason for it"

[[movements]]
path        = "the-input/prefix-*"           # a glob, said out loud
attribution = "the change that added the whole group of rows"
```

- A `compare` that finds a differing row not in this table fails, like any other difference. A differing row that is in the table prints as `[ALLOWED] <path> — <attribution>` and does not block.
- A row that matches no differing row is named on an `unused:` line before the verdict; the verdict does not change.
- A row names one surface path exactly, or contains a glob character. A bare directory name permits nothing, because a row that covered every file under a directory would let a permitted movement on one surface quietly cover its siblings.
- `attribution` says why the row moved. Left out, the row reads `(no attribution)`. Present but empty or blank, it is refused when the manifest is read.
- Two rows with the same `path` are refused when the manifest is read, naming both by number with their attributions. Keep one row with every reason in it.
- A comparison in which two rows match one differing row is refused, naming the row and both matching rows with their attributions. The two may be two globs, or a glob and an exact path, from `[[movements]]` or `--allow-diff`. In `mutants`, that refusal makes the comparator's result `REFUSED`.

`compare` always takes `--manifest`, even with `--against`, because the movements come from the manifest; a comparison of two directories still names the manifest it is judged by. `--against` runs no controls, since it starts no program.

`compare … --allow-diff FILE` adds rows at comparison time from a plain text file of `path :: attribution` lines, for a change that permits movements the committed manifest does not yet. The line format is a rule of the flag, in the skill's `references/commands.md`, "`--allow-diff`". golden-census reads the file whole as UTF-8 before comparing, and refuses a file holding a byte that is not UTF-8, naming the byte and its offset.

## The golden directory

```
<golden>/
  <input>/
    <surface>.out      stdout, normalized
    <surface>.err      stderr, normalized
    <surface>.exit     the exit code and a newline
    <surface>.<ext>    a written file as the subject wrote it — line endings and final newline included — with the census's folds applied (json-fields first for .json)
    <surface>.skip     a declared SKIP's reason; a fixed sentence when a pinned tree could not be cloned
    surfaces.json      {surface: {argv, status, exit | reason,
                       shares_invocation_with?}, "_counts": {...}}
```

Every file holds what the program printed or wrote, line endings included, with the census's folds applied. A `\r` is recorded, and a change of line ending alone is a `[DIFF]` that quotes the line. `compare`'s diff splits lines on `\n` alone, as the census does. It quotes a line containing a `\r`, a form feed, another character Python reads as a line break, or a control character such as ESC or BEL, in Python's `repr` form, so the byte is visible and no terminal acts on it: a run on a scratch program shows `-report ok` against `+'report ok\r'`. A file whose only change is its final newline gets a one-line detail saying which side has it: `the files differ in their final newline; the first has it`.

The diagram is the full shape; a given golden holds only what its manifest produced. The shipped example's golden, `examples/python-function/golden/`, is one input over one `run` surface, and holds `results.out`, `results.err`, `results.exit`, `results.json` and `surfaces.json`. It has no `.skip` file (no `skip` surface), no `_counts` (no `counter`) and no `shares_invocation_with` (one surface cannot share an argv with another). That absence is the manifest's shape, not a golden missing something.

A golden directory holds only what golden-census wrote. If anything else puts a file there, even a `.DS_Store`, remove it: a file that is not text is refused by name, and a text file shows up as an `only-in-golden` or `only-in-new` row.

`shares_invocation_with` is derived at capture and appears only where it applies: when two or more captured surfaces of one input recorded the same argv, each names the others, sorted. Two rows can share one invocation, for example a stdout surface and its stderr twin, which are a single command line run twice; without the key, a reader would take the two recordings for two independent pieces of evidence. Nothing in a manifest turns the key on. A row that starts or stops sharing an argv gains or loses the key, and either way the golden changes, so the change is visible.

**The marker.** `surfaces.json` is what makes a directory a capture: a directory holding at least one `<input>/surfaces.json` is one. What `capture` refuses to write into, what `--force` replaces, and what a stopped capture leaves beside `--out` are rules of the flags, in the skill's `references/commands.md`, "`--out`" and "`--force`".

- The manifest alone decides what a capture records: for each input, `<input>/surfaces.json` and, for each surface, `.skip` for a `skip` row; `.out`, `.err` and `.exit` for a `tallies` or `matrix` row; those three plus the written file for a `run` row; and for an input with `git`, the `.skip` a failed clone records for each surface.
- Removing a surface, changing one to or from a skip, changing a surface's `writes`, or removing an input leaves a file or directory this capture no longer records. Delete it, then run `capture --manifest <MANIFEST> --out <GOLDEN> --force`.
- `compare` refuses a symbolic link anywhere in a capture. It never reads part of a capture, and never reads through a link.

**Normalization happens at capture time, never at compare time.** `compare` compares two directories of already-normalized files byte for byte. A change to a fold means a new capture, which shows as a diff against the old golden; the golden is never re-read under new folds.

## What a manifest is not

- Not the census. Pins and folds are census rows; the manifest names the census, and golden-census reads both.
- Not the goldens. The manifest says how to produce them; the project commits what was produced.
- Not the mutant list. Mutants are their own file, run by the `mutants` command.
- Not documentation. A project's own documents-match-code check is the project's; the manifest records nothing about it.

## What golden-census refuses, by name

Read this before the first run, so that a wrong manifest costs one sentence instead of ten minutes of capturing. Where a section above states the rule, the entry points to it.

- A surface named by an input or a set that no `[surfaces.<name>]` defines.
- A `[surface-sets]` name that is also a `[surfaces.<name>]` name (see `[surface-sets]`).
- An `args` key on a `matrix` surface (see `matrix`).
- Two `[surfaces.<name>]` or two `[inputs.<name>]` keys that are the same name once case and Unicode normalization are ignored; the refusal shows the code points of two keys that print alike (see `[inputs.<name>]`).
- A `needs` that names no `[[setup]]`.
- Two `[[setup]]` tables with one `name` (see `[[setup]]`).
- An `env` key the census has pinned.
- A placeholder not defined in that place (see "Placeholders").
- An `include` file that does not exist or does not parse.
- A key no table reads; the refusal names the key, the table and the keys it accepts (see "File format").
- A `[surfaces.<name>]` or `[inputs.<name>]` key that is not one path component (see those sections).
- A `writes` that does not begin `<WORK>/`, or whose rest is absolute, contains `..` or has an empty component (see `writes`).
- A `writes` that would be recorded as `<surface>.out`, `.err`, `.exit`, `.skip` or `surfaces.json`, in any case (see `writes`).
- A `[files."<name>"]` key that is absolute, contains `..` or resolves to a directory; two such keys of which one is a directory above the other; and a key the operating system will not write, refused when the files are written rather than at load (see `[files."<name>"]`).
- A `verdict` or `failing` that is not a string or does not compile (see `tallies`).
- Stdout or stderr that is not UTF-8 text, refused when the row runs (see `run`).
- A `writes` file that is not UTF-8 text, refused when the row runs (see `writes`).
- A `writes` path that a link leads outside `<WORK>`, refused when the row runs, and one the row's own command makes lead outside, refused after the row runs (see `writes`).
- A `[[movements]]` `attribution` that is present and empty; two `[[movements]]` rows with the same `path` (see `[[movements]]`).
- A `census` file that is missing or fails its own checks (see `census-format.md`).

## The shipped example

`examples/python-function/manifest.toml`, in full. The program is one pure function over two text fixtures. The file is what `golden-census init <DIR> --template python-function` writes with its holes filled and nothing else changed, which is why it reads as a form.

The lines with no `#` in front are a complete manifest: one `[subject]`, one input, one `run` surface, and the census beside it. Three tables and eight keys are the floor; a program with one entry point needs nothing more. Everything behind a `#` is a key this program has no use for, written out with the comment that says when it is the right key: `version`; an input's `git`, `sha` and `expect_counts`; a surface's `inputs`, `env`, `needs` and `counter`; the `skip`, `matrix` and `tallies` kinds; `[surface-sets]`, `[[setup]]`, `[files."<name>"]` and `[[movements]]`. A project uncomments what its program needs. The commented rows are the rest of this document on one page.

Two things in the file are worth noticing. `command` is `<PYTHON>` and `<HERE>/runner.py`: the runner is beside the manifest, not under `root`, and because `surfaces.json` records only what comes after `command`, no recorded argv contains the interpreter or the entry point. And `writes` is `"<WORK>/<input>-<surface>.json"`: the two name placeholders let one line serve every row, and the `<WORK>` prefix is what makes the path foldable, which is why a `writes` without it is refused.

```toml
# The manifest: one subject, its inputs, its surfaces, its permitted
# movements. `docs/manifest-format.md` is authoritative for every key.
#
# `golden-census init` wrote this file with its holes IN PLACE. Each hole is a fact
# about this project that only this project knows; replace it, fence and all,
# with the project's own value. Every command REFUSES a manifest that still
# carries one, naming it — an unfilled hole is a project that has not finished
# plugging in.

[subject]
name    = "wordstats"                     # the subject's own word, printed at the head of every comparison
root    = "../.."                         # the subject's checkout, relative to this file; the cwd of every run
command = ["<PYTHON>", "<HERE>/runner.py"]  # the argv prefix of every run; <PYTHON> is the interpreter running golden-census, <HERE> this file's own directory
census  = "census.toml"                     # the census beside this manifest: what the environment around every run is pinned to
# version = ["--version"]                   # optional: the argv that prints the subject's version

# ------------------------------------------------------------------- inputs
#
# One [inputs.<name>] table per thing the surfaces are run over. The name is
# the first half of every recorded row's key, `<input>/<surface>`.

[inputs."fixtures"]
args     = []                             # this input's own arguments, one string per argument; `args = []` for an input that takes none
surfaces = ["results"]                    # the [surfaces.<name>] tables this input is recorded over
# git  = "https://example.invalid/some/repo"          # optional: a clone as the input; `git` and `sha` come together, and an empty string is neither
# sha  = "0000000000000000000000000000000000000000"   # optional: the commit that clone is pinned to
# expect_counts = { rows = 0 }              # optional: printed as AGREES/DIFFERS beside a counter's numbers; never gates

# ----------------------------------------------------------------- surfaces
#
# One [surfaces.<name>] table per surface. `kind = "run"` is the default: one
# subprocess, recorded as `.out`, `.err` and `.exit`.

[surfaces."results"]
args   = ["<WRITES>"]                     # this surface's arguments, one string per argument; <WRITES> where the output path goes
writes = "<WORK>/<input>-<surface>.json"                # the file this run writes, recorded beside the streams; must begin with <WORK>/
# inputs  = ["the one input this surface runs for"]        # optional: narrow the surface to some inputs
# env     = { NAME = "value" }              # optional: extra variables for this surface; one the census pins is refused
# needs   = ["fixture"]                     # optional: the [[setup]] steps that must have run first
# counter = ["<PYTHON>", "<HERE>/counts.py", "<WRITES>"]   # optional: a command handed the written file, printing one JSON object of counts

# A surface declared unrunnable here: the reason IS the golden, so an absent
# recording is never mistaken for a surface nobody thought of.
# [surfaces.unrunnable]
# skip = "why this surface cannot be recorded here, as one sentence"

# Many small runs recorded as ONE compacted file — a refusal matrix.
# [surfaces.flagmatrix]
# kind        = "matrix"
# include     = "flagmatrix.json"           # the generated row file, committed beside this manifest
# record_argv = ["the rows of flagmatrix.json"]

# One run reduced to the verdict line of each fenced group.
# [surfaces.tallies]
# kind    = "tallies"
# args    = ["--tallies"]
# rule    = "="                             # the single character the subject fences its banners with
# verdict = '^\s*\d+/\d+ passed\s*$'        # the regular expression matching each group's verdict line
# failing = '^\s*(?:\[FAIL\]|actual:)'      # optional: every line of a group matching this is recorded under its verdict line — reach the failing row's evidence, not only its name

# A named list of surfaces an input may ask for by one word.
# [surface-sets]
# tree = ["report", "export"]

# Commands run once per capture, in the work directory, before the rows that
# `needs` them: a relative path names one there, and <HERE> this file's own
# directory. golden-census runs a subprocess and never imports the module.
# [[setup]]
# name    = "fixture"
# command = ["<PYTHON>", "<HERE>/make_fixture.py", "<WORK>/fixture"]

# Small text files written into <WORK> before any run, for a surface whose file
# argument is the manifest's to state. Referenced as <WORK>/plan.txt in `args`.
# [files."plan.txt"]
# lines = ["the first line", "the second line"]

# The permitted golden movements: a row that moved, and the attribution that
# says why. A row not named here that moves is a diff like any other.
# [[movements]]
# path        = "the-input/the-surface.out"
# attribution = "the change that moved it, and the reason for it"
```
