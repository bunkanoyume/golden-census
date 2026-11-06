# The census: `census.toml`

The census lists everything outside the program's own code that can change what the program produces. Such a thing is called an input. Examples: an environment variable, the width of the temporary directory's path, the clock a renderer reads, the absolute path of the checkout, the program's own temporary file names, the versions of the tools it calls, and whether it runs inside a git checkout.

Each `[[input]]` row names one input and says what golden-census does about it. There are four choices, called dispositions:

- **pin**: set it to a constant in every run;
- **fold**: let it vary, and replace the text it leaves in the output with a placeholder;
- **state**: record its value with the capture, so a later change can be attributed;
- **precondition**: require it to hold before anything runs, and refuse if it does not.

Every pin and fold also carries a control: a small test, run before every capture, that proves the row matters. Without the control, a row is a claim nobody checked.

If an input is neither pinned nor folded, the recording changes whenever that input does, for no reason a reader can see. golden-census reads the census before the first run of a capture, runs the controls, and refuses to capture if a control fails or a precondition does not hold. `capture --twice` records everything twice and refuses if the two differ; a manifest is not finished until it passes.

Add a row for an input that has been seen to change a golden, not for one that could in principle. The row's `finding` key records what was seen, so a later reader knows why the row exists.

The file is `census.toml`, written by `init` beside the manifest with its holes left for the project to fill. Every command refuses a census that still contains a hole.

This document covers:
1. The environment rule
2. File format
3. `pin`: hold an input constant
4. `fold`: replace what varies with a placeholder
5. `state`: record a value with the capture
6. `precondition`: require a fact before anything runs
7. `[fixtures]`
8. What golden-census does with the census, in order
9. The shipped example

## The environment rule

Every run of the program gets an environment that golden-census builds from nothing. It contains the pinned variables at their pinned values, the variables named in `passthrough`, the surface's own `env` from the manifest, and golden-census's own marker variable. Nothing from golden-census's own environment gets in by accident. A variable the census does not name cannot reach the program, so it cannot change the output. This is not something golden-census detects; it is how the environment is built.

What no environment variable controls, such as a clock, the width of a temp path or a tool's version, has to be detected instead. Those are the rows with controls.

```toml
[environment]
inherit     = false                     # the only value golden-census accepts
passthrough = ["PATH", "HOME"]          # copied by name; nothing else is
```

- `PATH` is passed through because the program calls `git`. `HOME` is passed through because `git` reads its configuration there.
- A program that needs another variable gets it added to the list, with a TOML comment beside it saying why. `passthrough` holds names only, so the comment is the only place for the reason.
- The contraband scan looks for paths only. If a passed-through value, such as a user name or a host name, reaches the output, it is the census author's job to keep it out. Neither `probe` nor a capture scans for passed-through values. `probe`'s clause 5 looks for the opposite leak: the value of a variable that was not passed.

One variable belongs to golden-census and appears in no census: `GOLDEN_CENSUS_CHILD=1`. golden-census sets it in every run's environment after the pins and the passthrough list. A census row that pins it is refused when the census is read, and a surface `env` that names it is refused when the manifest is read; each refusal names the file and the row or surface. The variable tells the program that golden-census started it; `subject-requirements.md` says what a program may do with that. A census that records the environment in a `state` row records this variable like any other. A golden recorded with a version of golden-census that did not yet set this variable differs by that row, and the difference is golden-census's, not the program's.

## File format

The file is TOML. Each row is an `[[input]]` table with three required keys: `name`, `disposition` and `finding`. Pins and folds also have `control`. `finding` is the sentence that says how this input was seen to change a surface; it is the reason the row exists.

Every key in the file must be one golden-census reads. A row, a `control`, `[environment]` or `[fixtures]` with a key golden-census does not read is refused when the census is read. The refusal names the key, the table, and the keys the table accepts. A row may have the three required keys, the keys of its own disposition, and `control` where its disposition takes one; a `control` on a `state` or `precondition` row is refused by name, because those dispositions do not use it. A `serialization` table is read only on a `json-fields` fold and is refused on any other.

Strings in the census may contain these placeholders, which golden-census substitutes before use. They are allowed in a pin's `value`, a `state` command, a `precondition` command, a control's `command`, and a `drift` control's `output` (which may contain `<WORK>` only, at its start).

| Placeholder | Stands for |
|---|---|
| `<ROOT>` | the program's root directory |
| `<WORK>` | golden-census's work directory for this run |
| `<CLONE>` | an input's clone directory, when the run made one |
| `<PYTHON>` | the interpreter running golden-census |
| `<HERE>` | the directory this census file is in |
| `<FIXTURE>` | the `[fixtures]` directory, allowed in a control's `command` only |

Any other `<…>` token is refused when the census is read, before anything runs; so is `<FIXTURE>` anywhere but a control's `command`. The refusal names the token and lists what that string may contain. `<FIXED-WIDTH-DIR:N>` is not a placeholder in this sense: it is a pin value that golden-census resolves itself, and it must be the whole value.

The commands a census can name are a `precondition`'s, a `state` row's and a `drift` control's. The skill's `references/machine.md`, "Standard input and operating-system errors", says what standard input every command golden-census starts receives.

## `pin`: hold an input constant

```toml
[[input]]
name        = "terminal width"
disposition = "pin"
variable    = "COLUMNS"
value       = "80"
finding     = "argparse and most renderers wrap at $COLUMNS, so an unpinned width moves a surface by itself"
control     = { shape = "vary", surface = "the-input/the-surface", value = "40" }
```

`variable` is set to `value` in every run's environment. A variable may be pinned by one row only; two rows that pin the same variable are refused when the census is read, naming both rows and both values, because the second value would silently replace the first.

A pin's control has one of three shapes: `vary`, for a variable whose value golden-census can change; `drift`, for an input that changes with time; and `builtin`, for the fixed-width temp directory.

### The `vary` control

A `vary` control names one surface of the manifest and a second value. golden-census runs that surface three times: twice with the pin, and once with the variable set to the control's `value`. The two runs with the pin must be identical, and the third must differ. If the third run is the same as the other two, the variable does not affect that surface, and the pin is unproven.

How the three runs are made:

- Each run happens alone, in a new work directory that contains only what preparation put there. If the census pins `<FIXED-WIDTH-DIR:N>`, each run also gets a new fixed-width temp directory.
- Preparation is what a capture does before its first row, done for this one surface: golden-census checks the preconditions, writes the manifest's `[files]`, and runs the setup steps the surface's row `needs`, and no others. A row that reads what another row's setup step made must name that step in its own `needs`.
- Preparation is done again before each of the three runs. So a setup step the surface needs runs three times for every `vary` pin, before every command that runs the controls. If two surfaces would both show the pin, name the one that needs less setup.
- Two directories are not part of the work directory and are the same in all three runs: the program's own tree, and the pinned tree of the surface's input, which is the clone kept in the cache, checked out at the pinned commit and checked clean before each run, as before a capture. `manifest-format.md`, `[inputs.<name>]`, says what a run may leave in a tree; a control run that leaves something `git status` lists in the pinned tree refuses the command, exit 2, as a capture's rows do.
- The capture's own log lines, the `census state` block and the program's `version`, are not preparation and are not run.
- `census --manifest <MANIFEST>` and `--selfcheck --manifest <MANIFEST>` print, under the control's row, the `clone:` lines each run printed, and for a kept clone the line naming what git ignores there, each line saying which of the three runs printed it. The control block that runs before `capture`, `compare` or `mutants` prints no row that passed, so it prints none of these lines.

What the control reports:

- The difference between the third run and the other two may be in the exit code, or in what a capture records of stdout, stderr or the written file. golden-census judges the difference after the census's folds, under the surface's own `env`.
- A run the control could not make or compare is a disclosed `SKIP`, never a pass. The row says which run and why. The causes: the work directory could not be made or its preparation was refused (a precondition that does not hold, a setup step that exits non-zero, a temp root too wide for the pin); the input's pinned tree could not be cloned; the run would not start, for example a program not on this machine; or the run was refused before it could be compared, including by a fold's refusal of its text.
- Three identical runs make the row `UNPROVEN`. That is a `FAIL` of the census, because the census claims the pin matters and the control could not show it. Either find a surface the variable does change, or rewrite the row as a `state` row with `variables = [...]`, which records the value and pins nothing.
- When the two pinned runs agree before the folds as well, the row also says whether the third run differs from them before the folds. If it does, but not after, the variable changes something that the folds remove, so it does not reach the golden.
- When the two pinned runs differ from each other, the row is a `FAIL` whose `actual:` line begins `the two runs under the pin differ`, whatever the third run did; it is never `UNPROVEN`. Something else is changing the surface between runs. Find it and pin or fold it, or point the control at a surface that is steady. Until the two pinned runs agree, the control cannot say whether the pin matters.
- The surface must be one of the manifest's `<input>/<surface>` rows whose surface is run: no `kind`, or `kind = "run"`. A `vary` control that names anything else is refused when the manifest is read.

**A Python program pins `PYTHONHASHSEED`.** The interpreter picks a random seed for string hashes at startup, so a set of strings comes out in a different order on each run. The pin holds within one Python version. The program should still sort its own output. The neutral template carries this row, commented out:

```toml
[[input]]
name        = "Python's hash seed"
disposition = "pin"
variable    = "PYTHONHASHSEED"
value       = "0"
finding     = "a set of strings prints in an order the interpreter chose at startup, so two runs differ by bytes nobody changed"
control     = { shape = "vary", surface = "the-input/the-surface", value = "1" }
```

### The `drift` control

`drift` is for an input that changes with time rather than with a value golden-census can choose.

```toml
[[input]]
name        = "the clock renderers read"
disposition = "pin"
variable    = "SOURCE_DATE_EPOCH"
value       = "0"
finding     = "a renderer stamps the time into what it writes, so two runs a second apart differ by bytes nobody changed"
control     = { shape = "drift", command = ["<PYTHON>", "-c", "import os, time; open('<WORK>/stamp.txt', 'w').write(os.environ.get('SOURCE_DATE_EPOCH') or repr(time.time()))"], output = "<WORK>/stamp.txt", wait = 1.2 }
```

- golden-census runs `command` twice without the pin, `wait` seconds apart, and expects the two outputs to differ. It then runs it twice with the pin and expects them to be identical.
- `output` is either absent or a file. When absent, golden-census compares the command's standard output. Otherwise it compares the file's contents as a string. A file is a path relative to `<WORK>`, the directory the command runs in, or a path that begins with `<WORK>/`. Any other spelling (empty, absolute, another placeholder, a path with `..`, or a value that is not a string) is refused when the census is read.
- golden-census deletes the file before each of the four runs, so each run is judged on what it wrote. If a symbolic link takes the file out of `<WORK>`, before or after a run, the command is refused and the file is neither deleted nor read.
- A command not on `PATH`, or named by an absolute path or a placeholder path that does not exist, makes the control a disclosed `SKIP`, never a pass. A pin whose only control skipped is reported as such.
- A command named by a relative path containing `/` is refused when the census is read, because the command runs in `<WORK>` and the path would be looked for there. Write it as `<HERE>/…` or `<ROOT>/…`.
- The row above runs the interpreter, which is always present, so the pin is tested on every machine. Point it at the tool that actually stamps the time when you have one, and accept the `SKIP` on a machine without that tool as the price.
- The row's label prints the first word of `command` as written, so a `<PYTHON>` stays `<PYTHON>` and the verdict you paste contains no path of your machine.

**A program that prints a time pins `TZ` to `UTC`,** so every machine prints the time in the same zone. The neutral template carries this row, commented out:

```toml
[[input]]
name        = "the zone renderers print a time in"
disposition = "pin"
variable    = "TZ"
value       = "UTC"
finding     = "a renderer prints the clock in the machine's zone, so a golden captured under one zone moves by whole hours under another"
control     = { shape = "vary", surface = "the-input/the-surface", value = "Asia/Tokyo" }
```

### The fixed-width temp directory

```toml
[[input]]
name        = "the subject's temp root, and its width"
disposition = "pin"
variable    = "TMPDIR"
value       = "<FIXED-WIDTH-DIR:51>"
finding     = "the length of TMPDIR, not the subject, decides how much of a temp path reaches a golden whenever a subject prints one through a fixed-width slice; pinning the width moves that decision out of the machine and into this file"
control     = { shape = "builtin", name = "fixed-width-dir" }
```

A program that prints a temp path through a fixed-width field records more or less of the path depending on how long the temp root is on this machine. Pinning the width makes the path the same length everywhere, so a fold can recognize it as one token.

- For `<FIXED-WIDTH-DIR:N>`, golden-census makes a fresh directory under the machine's temp root whose absolute path is exactly `N` characters long, padding the last name to reach that width, and removes it when the run ends.
- Fold its path with a `path` row whose `source` is `fixed-width-dir`. The placeholder is the project's choice; the shipped example uses `<ENGINE-TMPDIR>`.
- A path of `N` characters needs the root, a separator and at least one character of name, so the widest temp root that works is `N-2` characters. A root of `N-1` or more is refused, and the refusal's `next:` line names the command that prints a root that fits. On macOS that is `getconf DARWIN_USER_TEMP_DIR`, whose root is 49 characters and fits the `N` of 51 the shipped example uses.
- A census has one width. Two `<FIXED-WIDTH-DIR:N>` pins with different `N` are refused when the census is read, naming both rows, because a capture makes one directory. The `fixed-width-dir` control belongs on the pin whose value is `<FIXED-WIDTH-DIR:N>` and is refused on any other.
- An `N` that needs a single name longer than the file system allows is refused too, naming the root, `N`, the name's length and the operating system's error. golden-census meets this limit when it makes the directory, not when it reads the census.
- `compare --against` makes no such directory and runs at any width. `--selfcheck` alone reads no census of yours and makes none for it; its own checks make and remove fixed-width directories from the bundled fixture's census, and are disclosed `SKIP`s under a root too wide for them. `--selfcheck --manifest <MANIFEST>` runs your census's `fixed-width-dir` control, which makes one real directory when the root fits.
- The builtin control does arithmetic on constructed widths, so it runs on every machine, plus one real directory when the machine's root fits. It is a disclosed `SKIP` when the root does not fit. The skill's `references/machine.md`, "The temp root", lists the commands that check the temp root and the rule for a root where no directory can be made.

## `fold`: replace what varies with a placeholder

A fold names a piece of text that varies between runs or machines and the placeholder that replaces it in the recording. There are three kinds: `path` replaces a directory golden-census knows; `regex` replaces a group of a regular expression; `json-fields` replaces named fields of a JSON document.

### `scope`

A `regex` fold is limited to the surfaces it may touch, with `scope`. A fold applied to every surface would hide a new timing on any surface without anyone noticing. So a project's `regex` fold names its rows. The neutral census's `path` folds use `"*"`, because the directories they fold are golden-census's own and can appear anywhere.

- `scope = "*"`, or a list containing only `"*"`, means every row. It is allowed on every kind of fold.
- A list of `<input>/<surface>` rows is allowed on a `regex` fold only. On a `path` or `json-fields` fold it is refused when the census is read, naming the row and its kind, because only the `regex` loop checks a row's name against a scope. To narrow a `path` fold, name a narrower directory; to narrow a `json-fields` fold, name narrower `paths`.
- A list that mixes `"*"` with row names is refused, because it says "every row" and "these rows" at once.

### A `regex` fold and the program's root

A `regex` fold sees the text as the program wrote it, before the `path` folds run. For a written `.json` file, it sees the text after that file's `json-fields` folds. This order is deliberate: a fold for the program's own temporary directories, which sit under a directory a `path` fold replaces, needs to see the raw path. A `regex` fold never reads `surfaces.json`, the record of each row's argv; only the `path` folds reach it, and they name the four directories. A machine path in the argv is the manifest's to fix: reach the directory through `<WORK>` with a `[[setup]]` step, or pin it as a `git`/`sha` input and spell `<CLONE>/…`.

The consequence is that a pattern which can match inside the program's root path must be scoped to the rows that need it. A fold that applies to every row and whose `volatile` group would take part of the root path and leave the rest is refused when the manifest is read, naming the row and quoting what the group matched (the group, because that is all a fold replaces). A group that takes the whole root is not refused, since nothing is left for the `path` fold to miss. A pattern that reaches the root only with surrounding text cannot be seen at load time; during a capture, any fold whose group would replace part of the root in a row's text and leave the rest is refused at that row, naming the row, the fold, the pattern and the text.

### `kind = "path"`

```toml
[[input]]
name        = "the checkout's absolute path"
disposition = "fold"
kind        = "path"
source      = "root"                    # root | work | clone | fixed-width-dir
placeholder = "<REPO>"
finding     = "every JSON root field and every report header carries it; without the fold no golden reproduces in another worktree and a home path is committed"
```

- `source` names one of the four directories golden-census knows: the program's root, its work directory, an input's clone, or the fixed-width temp directory.
- golden-census replaces the directory's path in both its written form and its resolved form (on macOS, `/tmp` and `/private/tmp` are the same directory), longest first.
- It replaces the path only where the directory's name ends: `<root>/x`, `<root>.` and `<root>.bak` are folded; `<root>-old`, `<root>2` and `<root>_x` are other directories, and the contraband scan refuses them.
- The scope is every surface.
- A census with no `path` row for one of the four directories is told so in the capture log, because the contraband scan would refuse a capture that contains that directory anyway.
- A fold for a source the run never makes, such as a `clone` fold in a manifest with no git input, still has a control that runs: it makes a stand-in directory under the work directory and proves the fold on that. Its `[PASS]` says the fold's arithmetic is right, not that a capture ever made the directory.

### `kind = "regex"`

```toml
[[input]]
# invented for this document: a subject that stamps the commit it was built
# from on a line of its own.
name        = "the freshness stamp the subject prints"
disposition = "fold"
kind        = "regex"
pattern     = '^(?P<lead>[ \t]*(?:#)?[ \t]*stamp: )(?P<volatile>.*?)(?P<keep> \(a repository of its own\))?$'
placeholder = "<PROVENANCE>"
scope       = "*"
finding     = "the subject reads its own commit out of git and prints it, so every commit of the subject moves every surface that carries the line"
control     = { sample = "stamp: 1aca2c6 clean", moved = "stamp: 2086ce1 dirty — uncommitted changes" }
```

- `pattern` is a Python regular expression with a group named `volatile`. Only that group is replaced, so the rest of the line is still compared byte for byte. Multi-line mode is on.
- A program that prints `\r\n` is recorded with the `\r`, and `$` does not match before it. A pattern anchored on `$` must end `\r?$`.
- A pattern containing a single quote goes in a TOML multi-line literal string (`'''…'''`); a one-line literal string cannot hold one.
- `scope` is `"*"`, a list containing only `"*"`, or a list of `<input>/<surface>` rows.
- The fold also applies to a written `.json` file, after that file's `json-fields` folds.
- The `control` gives two sample lines, `sample` and `moved`, that differ only in the token. golden-census checks three things, and a fourth when the fold has a `scope` list:
  1. After folding, `sample` and `moved` are identical: the fold fired. It also applies this row's own `pattern` alone to each and expects each to change; another fold that happens to replace the same token does not count, so a row whose own pattern matches nothing fails.
  2. Before folding, they differ: the fold was needed.
  3. Changing one byte of `sample` outside the `volatile` group is still reported after folding: the fold replaced the token, not the whole line.
  4. With a `scope` list, running the sample through a surface outside the scope reports the token as a difference there.

A second `regex` row, scoped to the rows it touches. It is the shipped example's own row, commented out in `examples/python-function/census.toml` because that program prints no duration:

```toml
[[input]]
name        = "the scan duration the report prints"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>\b\d+us\b)'
placeholder = "<DURATION>"
scope       = ["the-input/the-surface"]
finding     = "the last line prints the microseconds the run took, and two captures of an unchanged subject differ in exactly that token"
control     = { sample = "  scan finished in 137us", moved = "  scan finished in 2041us" }
```

The `scope` list is what makes this fold safe. `<DURATION>` replaces the token on the rows that print a duration and nowhere else. A duration on a row nobody scoped shows up as a difference a reader sees, not as a token something silently swallowed.

### `kind = "json-fields"`

```toml
[[input]]
name        = "the export's provenance commit"
disposition = "fold"
kind        = "json-fields"
paths       = ["provenance.engine"]
fields      = ["commit"]
placeholder = "<PROVENANCE>"
serialization = { indent = 2, ensure_ascii = false }
finding     = "the subject stamps the commit it was built from, so every mutant's clone would differ for the sha alone and say nothing about the mutant"
control     = { sample = "provenance-sample.json", moved = "provenance-moved.json" }
```

- This kind applies to written `.json` files; the extension may be in any case.
- golden-census parses the document, replaces every named field under every named path with the placeholder (an absent path or field is skipped), and writes the document out again with exactly the stated `serialization`.
- `serialization` takes exactly two keys: `indent`, an integer (`true` is refused), and `ensure_ascii`, a boolean.
- Before replacing anything, golden-census checks that writing the untouched document out again reproduces the program's document exactly, apart from trailing line endings, which are recorded as written. If it does not, the capture is refused: the program's JSON writer no longer matches the stated `serialization`, and the golden would silently reformat it.
- After this fold, the file passes through every `regex` fold whose scope includes its row, then the `path` folds.
- The `control` names two files under `[fixtures]`. golden-census reads both when it reads the census, and refuses then, naming the file, if one is missing, cannot be opened or is not UTF-8 text. The control checks the same three things as a `regex` fold's.

## `state`: record a value with the capture

```toml
[[input]]
name        = "tool versions"
disposition = "state"
commands    = [["<PYTHON>", "--version"], ["git", "--version"]]
finding     = "the subject's output is toolchain-bound wherever it shells out to another program, so an upgrade that moves a surface is attributed as a toolchain change and not as a subject change"

[[input]]
name        = "locale"
disposition = "state"
variables   = ["LANG", "LC_ALL"]
finding     = "not observed to move a surface; recorded so a capture that moves under another locale can be attributed"
```

- golden-census runs each command and reads each variable, and prints the results in a `census state` block in the capture log. A variable is read as the program will see it, after the environment rule, so a variable that is not pinned or passed through reads `<unset>`. With the second row above and neither variable passed through, the block shows `LANG = '<unset>'` and `LC_ALL = '<unset>'`.
- A `state` row takes `variables`, `commands` or both, and no other key.
- The state is not part of the golden. A version string that differs between machines would make every golden a statement about the machine.

## `precondition`: require a fact before anything runs

```toml
[[input]]
name        = "the subject's tree is a git checkout"
disposition = "precondition"
check       = "git-checkout"
clean       = false
finding     = "a copy with no repository is a different subject: anything the subject reads from git — a commit stamp, a describe line, a dirty flag — changes shape or disappears, and the capture log's `git log -1 --oneline` is what a later reader attributes a movement against"
```

A precondition that does not hold is a refusal, exit 2, before the first run, naming the check. It is not a `FAIL`: a `FAIL` says something about the program, a refusal says something about the run.

### `check = "git-checkout"`

- `git -C <ROOT> rev-parse --is-inside-work-tree` must print `true`.
- The capture log prints `git log -1 --oneline` for the record. If that git command does not exit 0, the log prints `no revision quoted`, with how the command ended and the first line of its stderr, or that it printed nothing there.
- `clean = true` also requires `git status --porcelain` to exit 0 and print nothing. The skill's `references/machine.md`, "The settings of git", lists the settings golden-census gives that command so that the global git configuration cannot change the answer.
- The default is `clean = false`, because comparing against an uncommitted tree is the ordinary development loop. A project rule that a comparison counts only after the commit is the project's to state.

Whether a program outside a git checkout is refused or merely recorded is the row's choice. A `precondition` with `check = "git-checkout"` refuses before the first run. A `state` row with `commands = [["git", "rev-parse", "--is-inside-work-tree"]]` records what git says and captures anyway, and every row that then changes for want of a repository is a difference a reader has to attribute by hand. The shipped example chooses `precondition`, because differences caused by a missing repository say nothing about the program.

### `check = "command"`

Any other question about the machine, asked as a command.

- Give `command = [...]` and `expect = "exit 0"` or `expect = "empty stdout"`. `empty stdout` holds when the command exits 0 and prints nothing but white space on standard output.
- Under either expectation, a command that exits non-zero or is ended by a signal is refused, naming the exit code or the signal and what the command printed.
- A command that prints a byte that is not UTF-8 is refused, naming the stream; make the command print UTF-8, or change or drop the row. The `git-checkout` check's git is held to the same rule.
- `command` may contain the placeholders listed under "File format"; any other is refused when the census is read.
- A `command` precondition runs in `<ROOT>` under golden-census's own environment, not the one the census builds. The built environment is for runs of the program; a precondition is a question about the machine, asked before any run, and a question asked under an environment built from nothing could not find its tools on `PATH` unless the census had already listed them. `git-checkout` runs the same way, also because git needs `HOME` for its configuration. So a precondition command does not see a pinned variable.

### A file the program reads from outside its tree

A cache, a database or a downloaded index is an input golden-census cannot see: it records what the program printed and wrote, never that file. Without a row for it, a comparison made against a different copy of the file says `IDENTICAL`. Hold the file still with a `command` precondition over its checksum, and commit the new `sums.txt` with each new golden:

```toml
[[input]]
name        = "the index is the one the golden was recorded against"
disposition = "precondition"
check       = "command"
command     = ["shasum", "-a", "256", "-c", "sums.txt"]   # its cwd is <ROOT>
expect      = "exit 0"                    # commit the new sums.txt with the new golden
finding     = "the subject answers from this file; a different one moves every row"
```

While the file matches, `census` prints `[OK] the index is the one the golden was recorded against: shasum -a 256 -c sums.txt — exit 0` under its preconditions. When it differs, golden-census refuses, exit 2, with `REFUSED: precondition 'the index is the one the golden was recorded against' (check command, expect exit 0): shasum -a 256 -c sums.txt exited 1: shasum: WARNING: 1 computed checksum did NOT match`. Both lines are from a run on a scratch program.

## `[fixtures]`

```toml
[fixtures]
dir = "fixtures"            # relative to the census; <FIXTURE> in controls
```

The directory of small files the controls need, committed beside the census. The bundled fixture's are two provenance JSON documents for its `json-fields` control; a `drift` control that renders something would keep its input here.

- `dir` is a path relative to the census file, or an absolute path, and must be a directory. `<HERE>` is the only placeholder it may contain; any other is refused when the census is read.
- A `json-fields` row in a census with no `[fixtures]` is refused when the census is read.

## What golden-census does with the census, in order

1. **Reads and checks the file**, and refuses a wrong census in one sentence before any run. It checks that every row has a known disposition; that every pin and every `regex` or `json-fields` fold has a control (a `path` fold's is built in: the directory folds to its placeholder, and an absolute path golden-census did not make survives); that every key of every table is one golden-census reads; that every narrowing `scope` is on a `regex` fold and names rows the manifest defines; that no `scope` list mixes `"*"` with row names; that no fold applied to every row has a `volatile` group matching inside the program's root; that every `vary` control names a row the manifest records and whose surface is run; that `[fixtures] dir` is a directory and every `json-fields` control's two files are there and are UTF-8 text; that no variable is pinned twice; that every `<FIXED-WIDTH-DIR:N>` has the same `N`, and a `fixed-width-dir` control sits only on such a pin; that every `source` is one of the four; and that `[environment]` has `inherit = false`. A control whose key does not resolve is refused here; golden-census never skips it later.
2. **Runs the controls.** Every pin's and fold's control runs and prints a row: `[PASS]`, `[FAIL]`, or a disclosed `[SKIP]` with the reason. The block contains this census's controls only; golden-census's own checks are `--selfcheck`'s. After any `[FAIL]`, the capture or compare is refused. A tool that cannot show its checks go red has shown nothing.
3. **Checks the preconditions.** A precondition that does not hold is a refusal naming the row.
4. **Reads and prints the `state` rows.**
5. **Captures**, under the environment the census built. A `regex` fold whose `volatile` group would replace part of the program's root in a row's text and leave the rest is refused at that row, naming the row.
6. **Runs the contraband scan.** golden-census reads back every file it wrote and counts them; a file it could not open is a refusal, not a clean file. It searches for an absolute home path; for the program's root, the work directory, the clone and the fixed-width directory, each in written and resolved form; and for any path under the machine's temp root that no fold recognized, and the temp root itself, with or without a trailing `/` (a longer name that merely begins with the root's letters is not the root). A home path counts only where a path can start: not after a name character, `.`, `~` or `-`, and not after a placeholder that this census's `path` rows put in the file (`<REPO>/home/x` is a path under the program's root; `<BR>/home/x` is a tag the program printed followed by a home path). It does count right after an option word such as `-I`, `-L` or `-isystem`. One hit refuses the capture, exit 2, naming the file, the line and the token; the `next:` line names the `path` row, by its `source`, that would fold a directory of the four this census has no row for; for a hit in `surfaces.json`, the manifest's `args`, which no `regex` fold reads; or a `regex` fold for anything else. The scan's own control, a planted home path in a scratch file, runs first, and golden-census prints it: a capture of the shipped example prints `contraband scan: 5 files written, 5 read, 0 hit(s)` and then a line beginning `contraband positive control: PASS — the scan found all`.

## The shipped example

`examples/python-function/census.toml`, in full. The program is one pure function over two text fixtures, the smallest program there is. The file is what `golden-census init <DIR> --template python-function` writes, with its holes filled and nothing else changed, so it carries every disposition as a row, most of them commented out.

Read it as two layers. The rows with no `#` in front are live: the environment rule, the `TMPDIR` pin with its builtin control, two of the four `path` folds (`root` and `work`), one `state` row and one `precondition`. They are the whole census a single-function program needs, and the floor every census starts from. The other two `path` folds, `clone` and `fixed-width-dir`, are left out of this file; a capture then prints one `census note:` line naming the two, and a capture that leaks either directory is refused with the row to add. The neutral template carries them as commented rows. The rows behind a `#` are the other dispositions, written out with their keys and left commented because this program has no use for them: a `vary` pin, a `drift` pin, a `regex` fold, a `json-fields` fold, a `state` row that reads variables, a `command` precondition, and the `[fixtures]` directory a fold control needs. A project uncomments the rows its program calls for and fills in the values. Each row carries the comment that says when it is the right row, which a reader could not work out from the format alone.

```toml
# The census: everything around the subject that is not the subject's code.
# Each [[input]] row is one thing that can move a surface — an environment
# variable, the width of the temp root, the clock a renderer reads, the
# checkout's absolute path — with its disposition and, for pins and folds, the
# control that proves the disposition matters.
# `docs/census-format.md` is authoritative for every key.
#
# `golden-census init` wrote this file with its holes IN PLACE; every command REFUSES
# a census that still spells one.

[environment]
inherit     = false                # the only value golden-census accepts: every subject subprocess runs under an environment built FROM NOTHING
passthrough = ["PATH", "HOME"]     # the variables carried through by name, on top of the pins below; nothing else reaches the subject

# [fixtures]
# dir = "fixtures"                 # optional: the small files the controls need, relative to this census; <FIXTURE> in a control command

# --------------------------------------------------------------------- pins
#
# A pin sets a variable to a constant in every subject environment, and its
# control shows the surface moves without it.

# Why 51. golden-census makes the subject a TMPDIR of exactly 51 characters and
# pins it there — the same width golden-census's own built-in default uses. The
# width is FIXED so that a temp path reaching an output folds as one token of
# constant length: a subject that prints a temp path through a fixed-width
# slice records a whole directory name under a short root and half a path
# under a wide one, and no fold recognizes the half. A directory made under
# a root needs the root, one separator and at least one character of name, so
# the widest temp root a 51-character pin can run under is 49 — the census's
# own arithmetic, on every platform. A wider root is a REFUSAL naming the
# cause, whose `next:` line names the command that prints a root that fits on
# the platform you are on.
# The generic rule is `<FIXED-WIDTH-DIR:N>` in docs/census-format.md.
[[input]]
name        = "the subject's temp root, and its width"   # the row's word: what every control row and every refusal about it says
disposition = "pin"                # pinned to a constant in every subject environment
variable    = "TMPDIR"             # the environment variable this row pins
value       = "<FIXED-WIDTH-DIR:51>"   # the one value golden-census resolves itself: a fresh directory of exactly 51 characters, removed in finally
finding     = "the length of TMPDIR, not the subject, decides how much of a temp path reaches a golden whenever a subject prints one through a fixed-width slice; pinning the width moves that decision out of the machine and into this file"
control     = { shape = "builtin", name = "fixed-width-dir" }   # golden-census's own: arithmetic on constructed widths, plus one real directory when this machine's root fits

# A pin whose control VARIES the value and expects the named surface to move.
# [[input]]
# name        = "terminal width"
# disposition = "pin"
# variable    = "COLUMNS"
# value       = "80"
# finding     = "argparse and most renderers wrap at $COLUMNS, so an unpinned width moves a surface by itself"
# control     = { shape = "vary", surface = "the-input/the-surface", value = "40" }

# A pin for an input that moves with TIME rather than with a value golden-census
# can choose: the command is run twice `wait` seconds apart with and without it.
# [[input]]
# name        = "the clock renderers read"
# disposition = "pin"
# variable    = "SOURCE_DATE_EPOCH"
# value       = "0"
# finding     = "a renderer stamps the time into what it writes, so two runs a second apart differ by bytes nobody changed"
# control     = { shape = "drift", command = ["<PYTHON>", "-c", "import os, time; open('<WORK>/stamp.txt', 'w').write(os.environ.get('SOURCE_DATE_EPOCH') or repr(time.time()))"], output = "<WORK>/stamp.txt", wait = 1.2 }

# -------------------------------------------------------------------- folds
#
# A fold lets an input vary and replaces the token it leaves in the output
# with a placeholder. The four `path` folds below name the four directories
# golden-census itself knows the absolute path of; the contraband scan REFUSES a
# capture that leaks one of them, so a missing fold is a refusal later rather
# than a golden now. A path fold's control is built in — the directory folds
# to its placeholder, and an absolute path golden-census did not make survives.

[[input]]
name        = "the subject root's absolute path"   # the row's word
disposition = "fold"               # let it vary, and replace what it leaves behind
kind        = "path"               # one of the four directories golden-census made or was given
source      = "root"               # which one: root, work, clone, fixed-width-dir
placeholder = "<REPO>"             # the token the folded text is replaced by in every golden
finding     = "the checkout's absolute path reaches a surface through recorded argv, a printed working directory or a resolved input path, and without the fold no golden reproduces in a second directory"

[[input]]
name        = "golden-census's work directory"
disposition = "fold"
kind        = "path"
source      = "work"
placeholder = "<TMPROOT>"
finding     = "every file a surface `writes` lands under <WORK>, and both the path handed to the subject and whatever the subject prints about it carry the directory"

# A fold of a token that moves inside a line — a duration, a pid, a stamp.
# Only the (?P<volatile>...) group is replaced, so the rest of the line stays a
# byte comparison.
# [[input]]
# name        = "the scan duration the report prints"
# disposition = "fold"
# kind        = "regex"
# pattern     = '(?P<volatile>\b\d+us\b)'
# placeholder = "<DURATION>"
# scope       = ["the-input/the-surface"]   # optional: the <input>/<surface> rows this fold applies to
#                                           # the default is every row, said out loud as scope = "*" (a list holding only "*" means the same)
# finding     = "the last line prints the microseconds the run took, and two captures of an unchanged subject differ in exactly that token"
# control     = { sample = "  scan finished in 137us", moved = "  scan finished in 2041us" }

# A fold of named fields inside a JSON document the subject writes.
# [[input]]
# name        = "the export's provenance commit"
# disposition = "fold"
# kind        = "json-fields"
# paths       = ["provenance.engine"]       # the dotted paths, resolved from the document root
# fields      = ["commit"]                  # the keys blanked under each path
# placeholder = "<PROVENANCE>"
# serialization = { indent = 2, ensure_ascii = false }   # exactly the subject's own json.dumps call; the round trip is asserted
# finding     = "the subject stamps the commit it was built from, so every mutant's clone would differ for the sha alone and say nothing about the mutant"
# control     = { sample = "provenance-sample.json", moved = "provenance-moved.json" }   # two files under [fixtures]

# ------------------------------------------------------------------- state
#
# Stated, not pinned: printed in the capture log so a movement can be
# attributed, and never recorded as a golden — a version string that moves
# between machines would make every golden a statement about the machine.

[[input]]
name        = "the tool versions this capture was taken under"   # the row's word
disposition = "state"              # read and printed, never pinned and never folded
# the state block prints only the FIRST LINE of each command, so pipe a multi-line answer into one (`… | tr '\n' ' '`)
commands    = [["<PYTHON>", "--version"]]     # one argv list per tool
# variables = ["LANG", "LC_ALL"]   # optional: variables read AS THE SUBJECT SEES THEM — an unlisted one reads <unset>
finding     = "the subject's output is toolchain-bound wherever it shells out to another program, so an upgrade that moves a surface is attributed as a toolchain change and not as a subject change"

# ------------------------------------------------------------ preconditions
#
# Checked before the first run. A failure is a REFUSAL naming the check, never
# a FAIL: a FAIL is a statement about the subject, a REFUSAL about the run.

[[input]]
name        = "the subject's tree is a git checkout"   # the row's word
disposition = "precondition"       # asked about the machine before anything runs
check       = "git-checkout"       # `git rev-parse --is-inside-work-tree` must answer true in the subject root
clean       = false                # true also requires `git status --porcelain` to print nothing
finding     = "a copy with no repository is a different subject: anything the subject reads from git — a commit stamp, a describe line, a dirty flag — changes shape or disappears, and the capture log's `git log -1 --oneline` is what a later reader attributes a movement against"

# Any other question about the machine, asked as a command.
# [[input]]
# name        = "the tool the subject shells out to is installed"
# disposition = "precondition"
# check       = "command"
# command     = ["git", "--version"]        # may spell <ROOT>, <WORK>, <CLONE> and <PYTHON>; its cwd is <ROOT>
# expect      = "exit 0"                    # or "empty stdout"
# finding     = "the surface that tool produces is empty without it, and an empty golden looks like a surface nobody thought of"

# A file the subject READS from outside its tree — a cache, a database, a
# downloaded index — held still by its checksum: golden-census records what the
# subject printed and wrote, and never that file, so without this row a
# comparison against a different copy of it says IDENTICAL.
# [[input]]
# name        = "the index is the one the golden was recorded against"
# disposition = "precondition"
# check       = "command"
# command     = ["shasum", "-a", "256", "-c", "sums.txt"]   # its cwd is <ROOT>
# expect      = "exit 0"                    # commit the new sums.txt with the new golden
# finding     = "the subject answers from this file; a different one moves every row"

```
