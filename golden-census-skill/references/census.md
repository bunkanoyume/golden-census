# Census rows to copy

Open this file when you write a census row, or when a capture will not reproduce. The census lists every input to the subject's output that is not the subject's own code, and says what to do with each: pin it, fold it, state it or require it.

The whole rule for every key is in the format document, `docs/census-format.md` under the `docs` directory `golden-census --help` names. This file carries the rows to copy. The strict-key rule of `references/manifest.md` holds here too: a key golden-census does not read is refused.

## The rule

- Every row has `name`, `disposition` and `finding`. `finding` is the sentence that says how this input was seen to move a surface.
- Every pin and every `regex` or `json-fields` fold carries a `control`. A `path` fold's control is built in. A row without a control is refused, because a pin nobody can show matters is a claim, not a measurement.
- Add a row for evidence, not for possibility. A row defends against an input seen to move a golden.
- Every subject subprocess runs under an environment built from nothing: the pinned variables at their pinned values, the `passthrough` list, the surface's own `env`, and golden-census's child marker. An unlisted variable cannot reach the subject.
- The contraband scan finds paths only. A passed-through secret, user name or host name that reaches a golden is the census author's to keep out of the subject's output; `probe` scans for passed-through values and a capture does not.
- Keep the four `path` folds that `init` wrote: `root`, `work`, `clone` and `fixed-width-dir`. The block below shows all four, as `init` writes them. A census missing any of `work`, `clone` or `fixed-width-dir` prints ``note: no `path` fold names work, clone, fixed-width-dir``, because the contraband scan refuses a capture that leaks one of those directories.

## The rows

Every block below was loaded by a run of `census --manifest` against a manifest that records the rows the controls name (`tool/help` and `report/summary`).

```toml
[environment]
inherit     = false                  # required; false is the only value accepted
passthrough = ["PATH", "HOME"]       # copied by name; nothing else reaches the subject

[fixtures]                           # the directory beside this census that holds a
dir         = "fixtures"             # json-fields control's two files; a json-fields
                                     # fold with no [fixtures] is refused at load

[[input]]                            # a pin, proven by varying it
name        = "terminal width"
disposition = "pin"
variable    = "COLUMNS"
value       = "80"
finding     = "argparse wraps --help at $COLUMNS"
control     = { shape = "vary", surface = "tool/help", value = "40" }

[[input]]                            # a pin against something that moves with TIME
name        = "the clock renderers read"
disposition = "pin"
variable    = "SOURCE_DATE_EPOCH"
value       = "0"
finding     = "the renderer stamps the second it ran inside a compressed stream"
control     = { shape = "drift", command = ["<PYTHON>", "-c", "import os, time; open('<WORK>/stamp.txt', 'w').write(os.environ.get('SOURCE_DATE_EPOCH') or repr(time.time()))"], output = "<WORK>/stamp.txt", wait = 1.2 }

# The clock's other half, commented as the template ships it: uncomment it when a
# surface prints a time. The control runs that surface under another offset.
# [[input]]
# name        = "the zone renderers print a time in"
# disposition = "pin"
# variable    = "TZ"
# value       = "UTC"
# finding     = "a renderer prints the clock in the machine's zone, so a golden captured under one zone moves by whole hours under another"
# control     = { shape = "vary", surface = "the-input/the-surface", value = "Asia/Tokyo" }

[[input]]                            # the four path folds: each an absolute directory
name        = "the subject root's absolute path"   # golden-census knows
disposition = "fold"
kind        = "path"
source      = "root"                 # root | work | clone | fixed-width-dir
placeholder = "<REPO>"
finding     = "the checkout's path reaches a surface through recorded argv or a printed working directory"

[[input]]
name        = "golden-census's work directory"
disposition = "fold"
kind        = "path"
source      = "work"
placeholder = "<TMPROOT>"
finding     = "every file a surface `writes` lands under <WORK>, and the path handed to the subject carries the directory"

# The other two path folds, commented as the template ships them. Uncomment one
# when a refusal names it: `clone` when an input is pinned, `fixed-width-dir`
# when a surface prints its temp path.
# [[input]]
# name        = "an input's clone directory"
# disposition = "fold"
# kind        = "path"
# source      = "clone"
# placeholder = "<CLONE>"
# finding     = "an input pinned with `git` and `sha` is cloned into the cache directory, and a surface can print that path"
#
# [[input]]
# name        = "the fixed-width temp directory"
# disposition = "fold"
# kind        = "path"
# source      = "fixed-width-dir"
# placeholder = "<ENGINE-TMPDIR>"
# finding     = "the day a surface prints a temp path, the scan refuses the capture unless the directory folds"

[[input]]                            # a volatile token inside a line
name        = "the subject's wall-clock durations"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>\b\d+(?:\.\d+)?ms\b)'
placeholder = "<DURATION>"
scope       = ["report/summary"]   # the rows this fold applies to
finding     = "two occurrences in summary.out and nowhere else"
control     = { sample = "refusal 160ms writing a 600-file scan", moved = "refusal 165ms writing a 600-file scan" }

[[input]]                            # fields of a written JSON document
name        = "JSON provenance"
disposition = "fold"
kind        = "json-fields"
paths       = ["provenance.engine"]
fields      = ["stamped", "commit", "dirty"]
placeholder = "<PROVENANCE>"
serialization = { indent = 2, ensure_ascii = false }
finding     = "the export's provenance block carries the sha and the dirty flag"
control     = { sample = "provenance-sample.json", moved = "provenance-moved.json" }

[[input]]                            # the pin every census carries: the subject's TMPDIR,
name        = "the subject's temp root, and its width"   # a fresh directory of exactly 51 characters
disposition = "pin"
variable    = "TMPDIR"
value       = "<FIXED-WIDTH-DIR:51>"
finding     = "the length of TMPDIR, not the subject, decides how much of a temp path reaches a golden"
control     = { shape = "builtin", name = "fixed-width-dir" }

[[input]]                            # recorded in the log: commands, one argv list per tool
name        = "the tool versions this capture was taken under"
disposition = "state"
commands    = [["<PYTHON>", "--version"]]
finding     = "an upgrade that moves a surface is attributed as a toolchain change"

[[input]]                            # recorded in the log; not known to move a surface
name        = "locale"
disposition = "state"
variables   = ["LANG", "LC_ALL"]
finding     = "not observed to move a surface; recorded so a move can be attributed"

[[input]]                            # must hold, or the run is refused
name        = "the subject's tree is a git checkout"
disposition = "precondition"
check       = "git-checkout"
clean       = false
finding     = "a `git archive` copy has no repository, so every row that stamps a commit splits in two"
```

## The four dispositions

| Disposition | What it does | Needs a control |
|---|---|---|
| `pin` | Holds a variable at a constant in every subject environment. | yes: `vary`, `drift` or the built-in `fixed-width-dir` |
| `fold` | Lets an input vary and replaces the token it leaves with a placeholder at capture time. | yes for `regex` and `json-fields`; built in for `path` |
| `state` | Prints the input's value in the capture log. Never a golden. | no |
| `precondition` | A fact that must hold before a capture or compare runs. A failure is a refusal, never a FAIL. | no |

A `state` row records its `commands` and `variables` in the capture log. The `census state` block prints only the first line of each command, so pipe a multi-line answer into one line.

## `vary`: the control of a pin

- It names one of the manifest's own `<input>/<surface>` rows whose surface is a `run`. A key that names any other row is refused when the manifest is read.
- It runs that row three times: twice under the pin, once under `value`. Each run is alone, in a new place that holds only what preparation put there: the manifest's `[files]` and the setup steps the row `needs`, and no other row's.
- A row that reads what another row's setup step made must name that step in its own `needs`.
- A setup step the row needs runs three times for every `vary` pin, in front of `capture`, `compare`, `mutants` and `census`. Name a row that needs none where one shows the pin.
- The control compares the exit code and what a capture records of the row's stdout, stderr and written file, after the census's folds, under the surface's own `env`.
- The two runs under the pin must agree, and the run under `value` must differ. A pin whose three runs agree is `UNPROVEN`. Two runs under the pin that differ read `actual: the two runs under the pin differ, and …`. `references/verdicts.md` quotes both rows and says what to do.
- The subject's own tree is the same tree in all three runs, and so is the kept clone of a pinned input. A row that keeps state in either can differ between runs.
- A run the control cannot make is a disclosed `[SKIP]` naming which of the three runs it was and why. It is never a pass.

## `drift`: the control of a pin against time

- `command` runs twice without the pin, `wait` seconds apart, and the outputs must differ. It runs twice with the pin, and the outputs must be identical.
- `output` is absent, meaning standard output, or a string naming a file under `<WORK>`. Write it relative to `<WORK>` or opening with `<WORK>/`.
- Any other spelling is refused when the census is read: an empty string, an absolute path, another placeholder, a path that climbs out with `..`, and a value that is not a string.
- A file that a link takes out of `<WORK>`, before a run or after it, refuses the command.
- The command runs in `<WORK>`. A program named by a relative path with a `/` is refused when the census is read. Spell it `<HERE>/…` or `<ROOT>/…`.
- A command not on `PATH` is a disclosed SKIP of the control. So is a command named by an absolute path, or by one that opens with a placeholder, that is not there.

## Placeholders in a census

- A census string may spell `<ROOT>`, `<WORK>`, `<CLONE>`, `<PYTHON>` and `<HERE>` (this census file's directory) wherever a string appears: a pin's `value`, a `state` or `precondition` command, a control's `command`, and a `drift` control's `output`, which spells `<WORK>` alone and only at its start. `<FIXTURE>`, the `[fixtures]` directory, is for a control's `command` only. A pin's `value` may also be `<FIXED-WIDTH-DIR:N>`, the one token golden-census resolves itself: a fresh directory of exactly N characters, for the `TMPDIR` pin.

## A Python subject pins `PYTHONHASHSEED`

The interpreter draws a random seed at startup for its string hashes, so a set of strings walks out in a per-run order. The pin holds within one Python version. The subject should still order its own output. The row loads like the `COLUMNS` pin above. Its control is proven only by a row you saw walk out in a different order: a `--help` row does not move with the seed, and a control that names one reads `UNPROVEN`.

```toml
[[input]]
name        = "Python's hash seed"
disposition = "pin"
variable    = "PYTHONHASHSEED"
value       = "0"
finding     = "a set of strings prints in an order the interpreter chose at startup, so two runs differ by bytes nobody changed"
control     = { shape = "vary", surface = "report/summary", value = "1" }   # a row the seed moves
```

## Folds

### `path`

- `source` is one of `root`, `work`, `clone` and `fixed-width-dir`. Those are the four directories golden-census knows. `fixed-width-dir` is the directory of exactly N characters that golden-census makes under the temp root and pins the subject's `TMPDIR` to; the census spells the pin `<FIXED-WIDTH-DIR:N>`, and its control is built in.
- golden-census replaces the directory longest-first, in both its given and its `realpath` form.
- It replaces the directory only where its name ends. `<root>/x` and `<root>.bak` fold. `<root>-old`, `<root>2` and `<root>_x` are other directories, which the contraband scan then refuses.
- A `path` row's control folds one sample line over the directory and checks that the placeholder appears and a path golden-census did not make survives. The controls' work directory holds no clone and no fixed-width directory, so for those two sources the control makes a stand-in directory under it and folds that: every `path` row gets a verdict. The template keeps those two rows commented; a census without them prints the `census note:` line `SKILL.md` step 4 quotes.
- A path fold cannot be narrowed by `scope`.

### `regex`

- The pattern must contain a group named `volatile`. Only that group is replaced, so the rest of the line stays a byte comparison. Never fold the whole line.
- Multi-line mode is on. A subject that prints `\r\n` is recorded with it, and `$` does not match before a `\r`. A pattern anchored on `$` spells `\r?$`.
- A pattern that contains a single quote goes in a TOML multi-line literal string (`'''…'''`).
- `scope` names the rows the fold applies to. The default is every row, spelled `scope = "*"` or a list that holds only `"*"`. A list that mixes `"*"` with row names is refused.
- Scope a fold to the rows that need it. A fold applied everywhere would swallow a future timing on any surface without anyone seeing it.
- A `regex` fold sees the text as the subject wrote it, before the built-in `path` folds. For a written `.json` file, that text is the file's text after its `json-fields` folds.
- A fold whose `volatile` group takes part of the subject root and leaves the rest is refused, when the census is read or while a capture runs. Narrow the group to take all of the root or none of it, or scope the fold to rows that do not print the root.
- The control has three arms: `sample` and `moved` normalize identical, the same pair unnormalized differs, and one changed byte outside the volatile group is still reported. The row's own `pattern`, alone, must also change `sample` and `moved`; a second fold that folds the same token does not count for it. A fold with a `scope` list has a fourth arm: the moved token is still reported on a surface outside the scope.

### `json-fields`

- It applies to written `.json` surfaces. It parses the document, replaces every named field under every named path with the placeholder, and re-serializes with exactly the stated `serialization`. A path or field that is absent is skipped.
- `serialization` takes `indent` (an integer) and `ensure_ascii` (a boolean) and no other key.
- Before it replaces anything, golden-census asserts the round trip. When the round trip fails, the capture is refused: the subject's JSON writer no longer matches the stated `serialization`.
- `sample` and `moved` are files under `[fixtures] dir`. They must read as UTF-8 text. A key that does not resolve is refused when the census is read, never skipped when the controls run.

## Preconditions

- `git-checkout`: `git rev-parse --is-inside-work-tree` must answer `true` in the subject root. The capture log prints `git log -1 --oneline`. `clean = true` also requires `git status --porcelain` to print nothing. The default is `clean = false`.
- `command`: give `command = [...]` and `expect = "exit 0"` or `expect = "empty stdout"`. It runs in `<ROOT>` under golden-census's own environment, not the built one. A command that depends on a pinned variable does not see the pin.
- A failed precondition is a refusal at exit 2 before the first run, with the check named. It is a statement about the run, not about the subject.

## A file the subject reads from outside its tree

A cache, a database or a downloaded index is an input golden-census cannot see. A comparison across a change of that file prints `IDENTICAL`, and no line says the input moved. Hold the file still with a `command` precondition over its checksum.

```toml
[[input]]
name        = "the index is the one the golden was recorded against"
disposition = "precondition"
check       = "command"
command     = ["shasum", "-a", "256", "-c", "sums.txt"]   # its cwd is the subject root
expect      = "exit 0"
finding     = "the subject answers from this file; a different one moves every row"
```

- While the file matches, `census` prints `[OK] the index is the one the golden was recorded against: shasum -a 256 -c sums.txt — exit 0` under the preconditions.
- When it differs, `capture`, and a `compare` that captures, refuse at exit 2. The sentence names the precondition, the command and how it ended.
- When you change the file on purpose, commit the new `sums.txt` with the new golden.

## What a row leaves behind

- A row or a setup step leaves nothing that `git status` lists, in the subject's tree or in a pinned tree. It writes under `<WORK>`, or where the repository's own `.gitignore` or `.git/info/exclude` ignores the file.
- Python's `__pycache__/` is the usual offender. A command whose rows leave something git lists in a pinned tree is refused at exit 2. The refusal names every input that entered the clone in the order they entered, the clone, and what git lists. A capture's `--out` is left as it was.
- The capture whose row wrote the file is the one refused. A later capture skips that input until the directory is deleted.
- A `[[setup]]` step or the `[subject] version` command runs before the clone is entered. One that writes into a clone kept from an earlier run is that input's `[SKIP]` in the same run, before any row.
- A kept clone's `.git/info/exclude` goes with the clone when the clone is deleted.

## `GOLDEN_CENSUS_CHILD`

golden-census adds `GOLDEN_CENSUS_CHILD=1` to every subject environment, after the pins and the passthrough. A census pin of it, and a surface's `env` that sets it, are each refused at load, naming the file and the row or surface. The variable says the one thing a subject cannot find out for itself: golden-census started this process. A subject whose own self-test would run the census again reads it and refuses. A subject that ignores it behaves as before.
