# The manifest

The manifest tells golden-census what to run. It names one subject (a program), the inputs the subject is run over, the surfaces recorded for each input, and the golden movements a comparison may permit.

golden-census drives the subject by subprocess only. It never imports the subject, never reads a table out of it by name, and never runs its code in-process. Everything golden-census knows about the subject is in this file or in the files this file includes.

The manifest is the consumer's file. The manual says who keeps it and when.

The companion document is [`census-format.md`](census-format.md). The manifest says what to run. The census says what the environment around every run is pinned to, folded away, or merely stated. A manifest names its census, and golden-census reads both before the first capture. The third file, the mutants file, is described in [`mutants-format.md`](mutants-format.md).

## Vocabulary

| word | meaning |
|---|---|
| subject | the program under golden-census |
| input | a named argument bundle the subject is run over: a tree, a fixture, a clone, or nothing (`args = []`) |
| surface | a named argument suffix that produces one recorded result |
| row | one input × one surface: one golden record |
| golden | the recorded, normalized bytes of a row, committed by the consumer |
| capture | recording every row of a manifest into a directory |
| compare | a fresh capture (or a recorded one) against a golden directory |
| movement | a golden diff a comparison is allowed to accept, with its attribution |
| fold | a normalization that replaces a volatile token with a placeholder at capture time (defined in the census) |
| pin | an environment value held constant for every subject run (defined in the census) |

## File format

The manifest is TOML, read with Python's `tomllib` (3.11+).

A `matrix` surface may pull its rows from another file with `include` (TOML or JSON, by extension); `include` is a key of that surface kind alone. Use it for tables nobody should write by hand. A refusal matrix of several hundred rows is one example. A script the consumer keeps generates the file. The consumer commits the generated file beside the manifest, so a capture never depends on the generator having run.

Paths in the manifest are relative to the manifest's own directory, unless they begin with a placeholder.

**Every key is read or refused.** golden-census reads every key of every table of this file, or refuses it. A table that carries a key golden-census does not read is REFUSED when the manifest is read. The refusal names the key, the table it is in, and the keys that table takes. A key nobody reads does nothing. A misspelled key does nothing under the name of one that would. The census and the mutants file follow the same rule, so there is nothing to remember about which of the three files is strict. `[surface-sets]` is the one exception, because its keys are set names the author chooses.

## Placeholders

These are the only substitutions golden-census performs. It performs them in `[subject] command`, `args`, `writes`, `env` values, setup commands and counters. Anything else is passed as written. A token that looks like a placeholder and is not defined in that place is refused when the manifest is read. The refusal names the whole list for that place. (`<TMP>` is not `<WORK>`.)

| placeholder | expands to | folded in the shipped example's goldens as |
|---|---|---|
| `<ROOT>` | the subject root, absolute (every subprocess's cwd) | `<REPO>` |
| `<WORK>` | golden-census's per-capture scratch directory, absolute | `<TMPROOT>` |
| `<CLONE>` | the input's clone directory (inputs with `git`), absolute | `<CLONE>` |
| `<WRITES>` | the path this surface's `writes` names, after its own expansion | (its parent is `<WORK>`) |
| `<PYTHON>` | the interpreter running golden-census | never appears in a golden: the subject spells its own program name |
| `<HERE>` | the directory this manifest sits in | never appears in a golden (see below) |
| `<input>` | the current input's name (inside `writes` only) | none |
| `<surface>` | the current surface's name (inside `writes` only) | none |

The third column is the shipped example's own vocabulary, not a rule. golden-census folds each of these directories through whatever `placeholder` the census's matching `path` row names. The tokens in the third column are the ones `examples/python-function/census.toml` chose.

A fold's token is what golden-census prints in place of a path. `<REPO>`, `<TMPROOT>` and `<CWD>` are three of them. Never type one into a manifest.

`<HERE>` follows its own rules:

- It is valid only inside the three commands golden-census runs: `[subject] command`, a `[[setup]]` command and a `counter`.
- Use it for a file beside the manifest, rather than under `root` or `<WORK>`.
- An element that opens with `<HERE>` must name a file that is there. golden-census refuses the manifest at load if the file is missing.
- `mutants` carries `<HERE>` onto the copy of the subject when the manifest sits inside the checkout. A manifest outside the checkout keeps its own directory. When the copy does not carry the file, golden-census refuses and names both paths.
- It never appears in a golden. `command` is the prefix a row's argv is recorded after. A setup step's or a counter's argv is not recorded.

The subject's own `TMPDIR` is a fourth directory golden-census makes. It has a fixed width. The example folds it as `<ENGINE-TMPDIR>`. That fold is the census's row, not the manifest's: see `<FIXED-WIDTH-DIR:N>` in `census-format.md`, under `pin`.

Two of these placeholders have no use in the shipped example's manifest. They are shown here as fragments **invented for this document**, not quoted from it:

```toml
# invented: <ROOT> where a surface hands the subject its own checkout.
env  = { PROJECT_ROOT = "<ROOT>" }

# invented: <CLONE> as the arguments of an input pinned with `git` and `sha`.
args = ["<CLONE>/src", "--tests", "<CLONE>/tests"]
```

`<HERE>` is spelled for real twice in the shipped example. The manifest has `command = ["<PYTHON>", "<HERE>/runner.py"]`: the runner is a file beside the manifest, not under `root`. The mutants file has `golden = "<HERE>/golden"`: a golden directory named from the file that spells it.

## Sections

### `[subject]`

```toml
[subject]
name    = "wordstats"                       # the product name, for the report
root    = "../.."                           # the checkout; cwd of every run
command = ["<PYTHON>", "<HERE>/runner.py"]  # <HERE> is this file's own directory
# version = ["--version"]                   # optional: args that print the version
census  = "census.toml"                     # required
```

- `command` is the argv prefix of every run. golden-census appends an input's `args`, then a surface's `args`.
- An element of `command` that is an absolute path under `root` is refused by `mutants`, which would otherwise run your tree and not the copy. Spell it relative to `root`, and golden-census carries it onto the copy.
- `surfaces.json` records a row's argv as everything after `command`. A golden never carries the interpreter path or the entry-point path.
- `compare --command ARG …` runs the fresh capture with another argv in place of `command`, and nothing else of the manifest changes. Its elements are checked as `command`'s are, `<HERE>` being this manifest's directory; the manual's "Rules for one flag" has the rest. Because a golden holds no command, the golden is the same whichever one ran.
- `version` runs once per capture. golden-census prints its result in the capture log beside the census state. It is not a golden unless a surface also records it.

### `[inputs.<name>]`

The name is one path component. A capture writes every surface of an input into a directory of that name under `--out`. A name that carries a separator, or names this directory or its parent, would write outside `--out`. golden-census refuses it when the manifest is read.

Two input names that are the same name once case and Unicode normalization are folded are refused the same way, naming both. `Café` beside `café` is one pair, and so is `é` as one character beside `e` and a combining accent. On a file system that folds case or Unicode normalization they are one directory under `--out`, and the later input's record replaces the earlier's. A change to the earlier input would then compare `IDENTICAL`.

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

- `args` are prepended to every surface's args for this input.
- `args = []` is an input in its own right. The surfaces that take no tree (`--help`, `--version`, a refusal matrix) are filed under it.
- `surfaces` lists the surfaces recorded for this input. An entry is a surface name or a surface-set name. A set name expands in place. The value may also be the bare name of a surface set.
- `expect_counts` is a baseline the coder states. It is not a golden. golden-census prints `AGREES` or `DIFFERS` beside the counter's result in the capture log. An empty table is refused when the manifest is read. So is an input that sets `expect_counts` and names no surface with a `counter`, the members of its surface sets included.
- `git` and `sha` pin the input to a commit of a repository. The rules follow, in six groups: the pin, where the clone lives, the checks before the clone, when the clone cannot be used, keeping the clone clean, and files git ignores in a shared clone.

**The pin.**

- `git` and `sha` come together, or neither is set. An empty string is neither. golden-census refuses `git = ""` beside a `sha` at load. Read as a pin, it would capture the input against the local tree, while the manifest claims a clone.
- `sha` must be made of lowercase hexadecimal digits: the commit's id as `git rev-parse HEAD` prints it, or a prefix of it. golden-census refuses anything else at load.
- A `git` whose address carries a password is refused at load. Keep the credential in a git credential helper; the manifest is committed, and the capture log prints the address.
- golden-census refuses a `git` of `.` or `..` at load, and one that opens with `-`. A file system reads the first two as a direction, not as the folder the clone is kept in; git reads the third as an option.
- golden-census checks out `sha` as a commit's id. It never makes a branch of the clone from a remote branch of that name.
- It requires the full id that `git rev-parse HEAD` prints to begin with the pin.
- git's checkout prefers a branch or a tag named like the pin. golden-census takes such a branch or tag only where its commit's id begins with the pin.
- It requires `git status --porcelain` to print nothing. The manual lists the settings golden-census gives every git it runs, so that the global git configuration cannot change an answer.

**Where the clone lives.**

- A pinned input is cloned whole, at full size, with the whole history: golden-census runs a plain `git clone` with no depth limit and no size check, once per repository and commit, and keeps the clone until you delete it. Pin a large repository knowing that its full clone lands on this disk, in the cache directory named here.
- golden-census clones the repository once into a persistent cache in the user's cache directory. On macOS that is `~/Library/Caches/golden-census/`. On Linux it is `$XDG_CACHE_HOME/golden-census/` or `~/.cache/golden-census/`. The cache is never under the temp root.
- The clone lives at `golden-census-trees/<repository>/<sha>/`:

  ```text
  golden-census-trees/<repository>/<sha>/
    <repository>  the `git` value as git resolves it: a path that names a file or a directory, by its real absolute path; any other address as spelled; then each character that is not an ASCII letter, a digit, `.`, `_` or `-` made `-`
    <sha>         the pin, as the manifest spells it
  ```

- Two inputs that pin one repository at one commit share the clone. They may sit in one manifest or in two. A kept clone is taken only when its `remote.origin.url` is the address asked for; two addresses that meet one folder are a SKIP naming both.
- golden-census keeps no index of the cache and no file beside the clones. Deleting one commit, one repository or the whole cache breaks nothing but the next run's need to clone again.
- golden-census removes nothing it did not make in this run.
- golden-census keeps the clones nowhere else.
- The cache is kept between runs. A git step that fails inside a clone kept from an earlier run says so. A kept clone that is not clean says so too. The log's reason names that directory and tells you to delete it and capture again.

**Checks before the clone.**

- golden-census refuses a cache directory that cannot be made or written. It refuses a `HOME` that is not an absolute path. It refuses a `HOME` spelled with `..`, and on Linux an `XDG_CACHE_HOME` spelled with `..`.
- The refusal comes when the command is about to clone, so it follows whatever ran before that clone.
- A command that clones nothing is never asked, and makes no folder there.

**When the clone cannot be used.**

- A clone that cannot be made is that input's rows recorded as SKIP. It is never a pass, and it never bypasses the network policy. The log gives the reason.
- Where a git run did not exit 0, the reason names that run and says how it ended. It holds what the run printed on stderr, or says that it printed no text there.
- A clone's folder found with files in it and no `.git` directory is a clone cut short. It is that input's rows SKIPPED. The reason names the folder to delete.
- A clone's directory, or its `.git`, that is a symbolic link is that input's SKIP. The reason names the linked path.
- A `[[setup]]` step or the `[subject] version` command runs before the clone is entered. One that writes into a clone kept from an earlier run is that input's SKIP in the same run, before any row.
- Whether a SKIPPED clone is a gate is the consumer's rule, not golden-census's. golden-census prints the SKIP where it cannot be missed.

**A clone must stay clean.**

- A row or a setup step writes nothing that `git status` lists, in the subject's tree or in a pinned tree. It writes under `<WORK>`, or where the repository's own `.gitignore` or `.git/info/exclude` ignores the file. golden-census enforces this in the clones it made, as the next point says; in the subject's own tree it is a rule you keep, and a capture that breaks it still succeeds.
- After the rows, golden-census runs `git status --porcelain` again in every clone the rows ran in.
- golden-census also reads the clone's `.git/config`, `.git/hooks/` and `.git/info/` before the rows and after them. A row that changed one is refused the same way, naming the parts.
- A command whose rows left something there that git lists is refused at exit 2. The refusal names every input that entered the clone, in the order they entered. It names the clone and what git lists. A capture's `--out` is left as it was.

**Files git ignores in a shared clone.**

- The files git ignores in a shared clone persist across runs, inputs and manifests. They are not the pinned content.
- A kept clone that holds some is reported by a second `clone:` line in the log. The line names their count and the first three, as paths that are not the pinned content. The line changes no verdict and no exit code.
- A kept clone's `.git/info/exclude` goes with the clone when it is deleted. Deleting the clone's folder starts clean.
- `census` and `mutants` print these lines under their own headings: see `census-format.md` (the `vary` control) and `mutants-format.md` ("The output").

### `[surface-sets]`

```toml
[surface-sets]
tree = ["report", "export"]
```

A surface set is one name for the surfaces every input of a kind gets. Seven inputs do not repeat the same list, and a further surface is added in one place. The shipped example's manifest carries this row commented out, because one input over one surface has nothing to abbreviate.

A set name is an entry of an input's `surfaces` list like any other. It expands **in place**, and keeps the list's order. This fragment is invented for this document, because the example has no set to expand:

```toml
[inputs.demo]
surfaces = ["tree", "extra"]                # the two of `tree`, then the third
```

- An input that names a set and one of the set's own members records that surface once.
- An entry that is neither a surface nor a set is refused. The refusal says both things an entry can be.
- A set that has the name of a `[surfaces.<name>]` table is refused when the manifest is read, whether or not an input lists the name. The refusal names both. An entry is read as the set when it names one, so the surface of that name would never run.

### `[surfaces.<name>]`

The name is one path component, for the same reason an input's is. A capture writes `<out>/<input>/<surface>.out`. A name that carries a separator, or names this directory or its parent, would write outside the capture directory. golden-census refuses it when the manifest is read.

A surface is one of four kinds. `kind = "run"` is the default and needs no `kind` key.

**`run`** is one subprocess. It is recorded as `<input>/<surface>.out`, `.err` and `.exit`, and `.<ext>` for a written file.

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

- **Streams.** A row's standard output and standard error must be UTF-8 text. golden-census refuses a row that prints a byte that is not UTF-8 when that row runs. The refusal names the stream, the byte and its offset in that stream. Make the command print UTF-8 there, or wrap it so that it writes the raw bytes to a file under `<WORK>` and prints a text dump of them.
- `writes` names a file the run is expected to write. The rules follow.
- `counter` is a command run after the surface. The rules follow.
- `inputs` narrows a surface to some inputs. Use it when a surface set names a surface that some inputs must not run. A surface that an input's list names, and that also narrows itself away from that input, is a manifest error. golden-census refuses it before the first run.
- `env` holds variables added to the census's environment for this run only. A variable the census has pinned cannot be overridden here, and naming one is a manifest error. A `passthrough` variable can be overridden: the surface's value replaces the one passed through, for this run only.
- `<WRITES>` has the same value in `env` as in `args`. A subject told where to write through a variable spells the path once: `env = { GOLDEN_CENSUS_OUT = "<WRITES>" }` beside `writes = "<WORK>/…"`. The same token on a surface that declares no `writes` is refused, naming the row.
- `needs` names setup steps that must have run first (see `[[setup]]`).
- `record_argv` belongs to a `matrix` surface alone (see **`matrix`** below). golden-census refuses it on any other kind when the manifest is read. The refusal names the surface, the key and the kind.

**`writes`**

- golden-census captures the file after the run as `<surface>.<ext>`. The extension comes from the path.
- A path that carries no extension falls back to `out`, which is a stream's own name. golden-census therefore always refuses such a path: `writes` needs an extension of its own.
- The path must begin with `<WORK>/`. Its rest must not be absolute, must not climb with `..`, and must not have a component that names nothing. golden-census refuses any other path when the manifest is read.
- golden-census removes whatever is at that path before the run. A file that an earlier row, a `[files]` entry or a setup step leaves there is never recorded as this run's.
- A run that does not write the file records nothing under that extension. The `.exit` and `.err` say why.
- A `writes` path that is itself a link to a file when the row starts is not refused. golden-census removes the link alone and keeps the file it leads to.
- golden-census refuses a `writes` path that a link leads outside `<WORK>`. It refuses the path when that row runs, before it removes anything. The refusal names the row, the path as written and the path it resolves to. The link may come from a `[[setup]]` step, from an earlier row, or from a link put in place of the temp root `<WORK>` is in. golden-census removes nothing outside the work directory.
- A path that a `run` row's own command makes lead outside `<WORK>` is refused after that row runs. The refusal names the same three things, and nothing is recorded from the path.
- A written JSON file passes through the census's `json-fields` folds and its round-trip assertion.
- The capture writes `<surface>.out`, `<surface>.err` and `<surface>.exit` for every surface. It writes `<surface>.skip` for a surface it skipped. It writes one `surfaces.json` per input. golden-census refuses a `writes` recorded as one of those five names, whatever its case, when the manifest is read.
  - Recorded over a stream, the written file replaces a golden written moments earlier, and that stream has no golden at all.
  - Recorded as `.skip`, a surface that really ran is reported by `compare` as one that ran on neither side.
- The file must be UTF-8 text. golden-census reads it, normalizes it and compares it line by line. It refuses a file it cannot decode when that row runs, naming the row and the file.
- For a file that is not text, such as a database, an archive or an image, make the row's `command` a wrapper. The wrapper writes the file under `<WORK>` and a deterministic dump of it to `<WRITES>`. Give `writes` the dump's extension.

**`counter`**

- The counter is handed the written file. It prints a JSON object of integers.
- It belongs on a `run` surface with `writes`. On any other surface it would never run, so golden-census refuses it when the manifest is read.
- golden-census records the counts under the input's `_counts` in `surfaces.json`.
- `surfaces.json` holds one `_counts` per input, so an input may name only one surface with a `counter`. golden-census refuses an input that names two, over the expanded `surfaces` list, when the manifest is read.
- A run that wrote no file runs no counter. The capture log says `counter not run` under its row, and no `_counts` is recorded for it.
- A counter that does not exit 0, or prints anything but a JSON object, is a REFUSAL of the capture. The refusal carries a block that names the counter's own command after `ran:`.
- A counter that was never started is a REFUSAL over a block that opens `about to run:`.
- `expect_counts` never gates. It prints `AGREES` or `DIFFERS` in the log and nothing more.
- golden-census does not know what the numbers mean. The consumer's script does, which is the point. The counter lives beside the manifest. Name it `<HERE>/…`, because it runs in `<WORK>`.

**`skip`** is a surface declared unrunnable, with the reason recorded as the golden. The row exists so that nobody mistakes an absent golden for a surface nobody thought of.

```toml
[surfaces.unrunnable]
skip = "why this surface cannot be recorded here, as one sentence"
```

- golden-census records it as `<input>/<surface>.skip`, and in `surfaces.json` with `status = "skipped"`.
- The sentence is yours. It is the same on every machine, which is what makes it a golden.
- An input pinned to a `git`/`sha` tree that could not be cloned records a `.skip` too. That `.skip` holds one fixed sentence instead. The reason comes from git, the network or the operating system, so golden-census writes it to the log and never to the golden.

**`matrix`** is many small runs recorded as ONE compacted record. It is built for refusal matrices. Every row is expected to print a usage block and a refusal. Storing the same usage block seven hundred times hides nothing and helps nobody.

```toml
[surfaces.flagmatrix]
kind        = "matrix"
include     = "flagmatrix.json"              # [{label, args}, ...], committed beside this manifest
record_argv = ["the rows of flagmatrix.json"]
```

- The included file is a JSON list of `{"label": "(mode, --flag)", "args": [...]}`, or the TOML equivalent (`[[rows]]`).
- A script the consumer owns generates the file, and the consumer commits it. A capture never imports the subject to learn its rows.
- Each row runs `command + input.args + row.args` with the null device as its standard input.
- A matrix surface has no `args` of its own. golden-census refuses the key on one when the manifest is read, because no row would read it. Put the arguments on the rows.
- `record_argv` is what `surfaces.json` records as this row's argv. A matrix runs one command line per row, so there is no single argv to record. The key says what the row is.
- Only `capture.record_matrix` reads `record_argv`, so the key belongs to this kind alone. golden-census refuses it on a `run`, `tallies` or `skip` surface when the manifest is read.
- Every other kind records the argv it really ran. `shares_invocation_with` is derived from that argv: two rows are recorded as sharing an invocation when the argvs they really ran are equal. A key that could fake a shared invocation is therefore not allowed to sit in a manifest doing nothing.

The record is:

- `.out` opens with a header of three lines: `pairs: N`, `usage-prefix-lines: K` and `stdout-prefix-lines: J`. The J lines every row printed first on standard output follow the third line, each indented four spaces. A blank line ends the header.
- Per row, sorted by label, `.out` then holds a line `<label> exit=<code>` and two sub-headings, always in this order, each indented two spaces: `stderr tail-newline=<yes|no>`, then `stdout tail-newline=<yes|no>`. Under each sub-heading are that stream's lines, with the common prefix of all rows removed, indented four spaces. A stream that printed nothing after its prefix is one blank indented line under its sub-heading, so an empty stream is recorded as empty. A line is what ends in `\n`, so a `\r` stays in the line it ends.
- `.err` is the longest common prefix of every row's stderr, cut at a line break. It is the shared usage block. The common prefix of standard output is cut the same way and is stored in the header of `.out`.
- `.exit` is `0`. The per-row exit codes are in `.out`.
- A row whose standard output or standard error is not UTF-8 text refuses the capture, naming the row.

This record is from a run on a scratch subject with two rows, each printing a banner line and a row line on standard output:

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

- The census's `path` folds apply to both halves of the record, exactly as they do to a `run` row's `.out` and `.err`.
- The `regex` and `json-fields` folds do not apply. They are scoped to named `<input>/<surface>` rows, and a compacted matrix record is a reduction of many runs, not one row's bytes.
- The `tail-newline` word exists because `splitlines()` cannot tell `"abc"` from `"abc\n"`. A stream that gains or loses its final newline would otherwise move no golden byte. golden-census's own control proves that `no` is a value the recorder can produce.

**`tallies`** is one run whose stdout is reduced to the verdict line of every fenced group. Use it for a self-test whose body carries timings and paths the consumer does not want as goldens, but whose tallies it does.

```toml
[surfaces.tallies]
kind    = "tallies"
args    = ["--tallies"]
rule    = "="                                # a banner is fenced by two rules of this char
verdict = '^\s*\d+/\d+ passed\s*$'           # the expression matching each group's verdict line
failing = '^\s*(?:\[FAIL\]|actual:)'         # optional: lines recorded under their group's verdict
```

- A rule line is at least eight characters, all of the `rule` character. A shorter line fences nothing.
- `.out` is `groups: N`, then `<banner>: <verdict>` per group in print order. A group with no verdict line records `<no tally line>`. It never disappears.
- `.err` is empty. The reduction is of stdout. By declaration, the run's stderr is not a golden here.
- `.exit` is the run's exit.
- A line is what ends in `\n`. golden-census matches a rule line, `verdict` and `failing` with one trailing `\r` set aside. A transcript written with `\r\n` therefore records the same groups. A `failing` line is recorded with its `\r`.
- A `verdict` or `failing` that is not a string, or does not compile, is refused when the manifest is read. The refusal names the table and the key.

`failing` is optional. It is a regular expression, matched from the start of each line as `verdict` is.

- Every line of a group that matches it is recorded under that group's verdict line, exactly as printed and in print order. A failure that changed places, or whose evidence changed, is then a `[DIFF]` and not a tally that stood still.
- Write it to reach the failing row's evidence, the line that says what went wrong. Do not reach only the row's name. A row can keep its name and its count while its evidence changes.
- The recorded lines pass through the census's folds like any surface. Pick lines that are deterministic, or fold what moves in them.
- The capture log's line for the surface says how many lines it caught, as `M failing line(s)`. A pattern that reaches nothing shows as that, and not as a clean record.
- golden-census refuses `failing` on any other kind when the manifest is read. The refusal names the surface, the key and the kind.

This record is from a run on a scratch subject. `GROUP three` prints no verdict line. The capture log's line for the surface reads `tal: 3 group tallies, 2 failing line(s), exit 0`.

```text
groups: 3
GROUP one: 2/3 passed
  [FAIL] row a: wrong
  actual: 3
GROUP two: 3/3 passed
GROUP three: <no tally line>
```

The census's folds apply to the recorded text as they do to a `run` row's stdout. They are the `path` folds, and every `regex` fold whose scope takes this row.

A `matrix` or `tallies` surface may spell `writes`, and `<WRITES>` has its value there.

- golden-census expands the path, and refuses it before the run, exactly as for a `run` row.
- It clears the path before the run, once before a matrix's rows.
- It captures nothing from the path. These kinds record stdout and stderr reductions only.
- The refusal after the run, of a path the row's own command makes lead outside `<WORK>`, is a `run` row's alone.

### `[[setup]]`

A setup command runs once per capture, in the work directory, before the rows that `needs` it.

For fixtures that a subject's test module knows how to build, the consumer writes a one-line runner script, and the manifest names it. golden-census runs a subprocess and never imports the module.

golden-census passes every element of the command as written. A relative path names a path in the work directory. Name the script beside the manifest `<HERE>/…`, as in `[subject] command`. golden-census never looks beside the manifest for a name it was not given that way. An argument that shares its name with a file there is never that file.

```toml
[[setup]]
name    = "fixture"
command = ["<PYTHON>", "<HERE>/make_fixture.py", "<WORK>/fixture"]
```

- A setup command that does not exit 0 is a REFUSAL of the capture. A fixture that half-exists would record goldens about the fixture, not the subject.
- The refusal says how the command ended: its exit code, or the signal that ended it. It quotes the command's stderr, folded as the block under it is, or says that it printed no text there.
- The block under the sentence names the step's own command after `ran:`, and the environment the step was given.
- A step that was never started is a REFUSAL whose block opens `about to run:`.
- Two `[[setup]]` tables with one `name` are refused when the manifest is read. The refusal names both tables by their number and both commands. Keep one, or give the other a name of its own.

### `[files."<name>"]`

A `[files]` table is a small text file that golden-census writes into `<WORK>` before any `[[setup]]` step or row runs. Use it for surfaces that take a file argument whose content is the manifest's to state.

```toml
[files."plan.txt"]
lines = ["the first line", "the second line"]
```

Reference it as `<WORK>/plan.txt` in a surface's args.

The key is a path under `<WORK>`. A nested key, such as `"fixtures/a.txt"`, is what the key is for. The rules:

- Every component of the key names something, and the whole path stays under `<WORK>`.
- golden-census refuses a key that is absolute, or climbs with `..`, or resolves to a directory rather than a file, such as `"fixtures/"` or `"."`. It refuses it when the manifest is read, because it resolves the key against `<WORK>` and opens a file at the result.
- golden-census refuses two keys of which one is a directory above the other. `"a"` beside `"a/b.txt"` is one pair, because `"a"` would have to be a file and a directory at once. `"A"` beside `"a/b.txt"` is the same pair on a case-insensitive file system.
- golden-census compares keys with case and Unicode normalization folded. A name whose accent is encoded two ways is therefore one name.
- The refusal names every such pair. It follows each of two keys that print alike with its code points.
- `"a.txt"` and `"ab"` beside `"a/b.txt"` are two files, and they load.
- A key the operating system will not write is refused when the files are written, not at load. Such a key is a name too long for the file system, or two spellings it reads as one name. golden-census refuses it before any `[[setup]]` step or row runs. The refusal names the table, `<WORK>/<name>` and the operating system's reason.

### `[[movements]]`

The `[[movements]]` table is the attribution table: the golden movements a comparison permits.

```toml
[[movements]]
path        = "the-input/the-surface.out"
attribution = "the change that moved it, and the reason for it"

[[movements]]
path        = "the-input/prefix-*"           # a glob, said out loud
attribution = "the change that added the whole group of rows"
```

- A `compare` that finds a differing row not in this table FAILS, like any other diff.
- A row that is in the table prints as `[ALLOWED] <path> — <attribution>`. It does not block.
- A row that matches no moved row is named on an `unused:` line before the verdict. The verdict does not change.
- A row names ONE surface path exactly, or carries a glob character and says so out loud.
- A bare directory name permits nothing. A row that covered every file under a directory would let a permitted movement on one surface quietly cover its siblings.
- `attribution` says why the row moved. Left out, the row reads `(no attribution)`. Present and empty or blank, it is REFUSED when the manifest is read.
- Two rows whose `path` is the same string are REFUSED when the manifest is read. The refusal names both rows by their number and both attributions. Keep one row, with every reason in its attribution.
- A comparison in which two rows name one moved row is REFUSED. The two rows may be two globs, or a glob and an exact path, from `[[movements]]` or `--allow-diff`. The refusal names that row and both rows with their attributions.
- `mutants`' comparator check reads this table too. There, that refusal makes the comparator's verdict REFUSED.

`compare` always takes `--manifest`, even with `--against`. The movements table comes from the manifest, so a directory-to-directory comparison still names the manifest it is judged by. `--against` runs no controls in front of itself. It starts no subject, and a census's controls are about a subject being run.

`compare --manifest <MANIFEST> --golden <GOLDEN> --allow-diff FILE` adds rows at comparison time, from a plain text file of `path :: attribution` lines; the file's line format is a rule of the flag, in [`manual.md`](manual.md), "Rules for one flag". Use it for a change that permits movements the committed manifest does not yet.

- golden-census reads the file whole, as UTF-8 text, before anything is compared. It refuses a file that holds a byte that is not UTF-8. The refusal names the byte and its offset.

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

Every file holds what the subject printed or wrote, line endings included, with the census's folds applied. A `\r` is recorded. A change of line ending alone is a `[DIFF]` that quotes the line.

`compare`'s unified diff splits lines on `\n` alone, as the census does.

- It quotes a line that holds a `\r`, a form feed, another character Python reads as a line break, or a control character such as ESC or BEL, with `!r`, so the byte shows and no terminal acts on it. A run on a scratch subject shows `-report ok` against `+'report ok\r'`.
- A file whose only change is its final newline gets a one-line `[DIFF]` detail that says which side has it. A second run shows `the files differ in their final newline; the first has it`.

The diagram is the full shape. A given golden carries only what its manifest produced. The shipped example's golden, `examples/python-function/golden/`, is one input over one `run` surface. It holds `results.out`, `results.err`, `results.exit`, `results.json` and `surfaces.json`. It holds none of the last three lines' extras:

- no `.skip` file, because it declares no `skip` surface;
- no `_counts`, because it declares no `counter`;
- no `shares_invocation_with`, because one surface cannot share an argv with another.

Read the absence as the manifest's shape, not as a golden that is missing something.

A golden folder holds only what golden-census wrote. If anything else writes a file there, even a `.DS_Store`, delete it. golden-census refuses a file that is not text and names it. A text file shows up as an `only-in-golden` or `only-in-new` row.

`shares_invocation_with` is derived at capture. It appears only where it applies: when two or more `captured` surfaces of ONE input recorded the same argv, each names the others, sorted.

- Two rows can price one invocation. A stdout surface and its `[stderr]` twin are a single command line run twice.
- Without the key, a later reader takes two copies of one run for two independent pieces of evidence.
- Nothing in a manifest turns the key on. A row that starts sharing an argv gains the key, and one that stops loses it. Either way the golden moves, which makes the change visible.

**The marker.** `surfaces.json` is the marker. A directory that holds at least one `<input>/surfaces.json` is a capture directory. What `capture` refuses to write into, what `--force` replaces, and what a stopped capture leaves beside `--out` are rules of the flags: [`manual.md`](manual.md), "Rules for one flag" and "What a stopped command leaves".

- The manifest alone decides what a capture records. For each of its inputs, that is `<input>/` holding `surfaces.json` and, for each surface that input records:
  - `.skip` for a `skip` row;
  - `.out`, `.err` and `.exit` for a `tallies` or `matrix` row;
  - those three and the file its `writes` names, for a `run` row;
  - for an input with `git`, the `.skip` that a failed clone records for each surface.
- You may remove a surface, change a surface to or from a skip, change a surface's `writes`, or remove an input. Each leaves a file or directory this capture does not record. Delete it, then run `capture --manifest <MANIFEST> --out <GOLDEN> --force`.
- `compare` refuses a symbolic link anywhere in a capture. It never reads a capture short of one, nor through a link.

**Normalization happens at capture time, never at compare time.** `compare` is a byte comparison of two directories of already-normalized files. A fold change means a re-capture. It shows as a diff against the old golden. It is never a retroactive re-reading of the golden.

## What a manifest is NOT

- Not the census. Environment pins and folds are the census's rows. The manifest names the census, and golden-census reads both.
- Not the goldens. The manifest says how to produce them. The consumer commits what was produced.
- Not the mutant list. Mutants (a patch plus the check expected to fire) are their own file, driven by the `mutants` command.
- Not documentation. The consumer's docs-parity check judges README and skill text. The manifest does not record it.

## Errors golden-census refuses on, by name

Read this list before the first run, so that a wrong manifest costs one sentence and not ten minutes of capturing. Each entry says what golden-census refuses. Where a section above states the rule, the entry points to it.

- A surface named by an input or a set that no `[surfaces.<name>]` defines.
- A `[surface-sets]` name that is also a `[surfaces.<name>]` name (see `[surface-sets]`).
- An `args` key on a `matrix` surface (see **`matrix`**).
- Two `[surfaces.<name>]` keys, or two `[inputs.<name>]` keys, that are the same name once case and Unicode normalization are folded. `é` as one character and `e` followed by a combining accent are one name. Their recorded files are one set of files on a file system that folds case or Unicode normalization. golden-census names each of two keys that print alike with its code points.
- A `needs` that names no `[[setup]]`.
- Two `[[setup]]` tables with one `name` (see `[[setup]]`).
- An `env` key the census has pinned.
- A placeholder golden-census does not define in that place (see "Placeholders").
- An `include` file that does not exist or does not parse.
- A key no table of this file reads (see "File format"). The refusal names the key, the table it is in, and the keys that table takes.
- A `[surfaces.<name>]` or `[inputs.<name>]` key that is not one path component. It becomes a directory or file name under the capture directory (see `[inputs.<name>]` and `[surfaces.<name>]`).
- A `writes` that does not begin `<WORK>/`, or whose rest is absolute, climbs with `..`, or has a component that names nothing (see `writes`).
- A `writes` recorded as `<surface>.out`, `<surface>.err`, `<surface>.exit`, `<surface>.skip` or `surfaces.json`, whatever its case (see `writes`).
- A `[files."<name>"]` key that is absolute, climbs with `..`, or resolves to a directory (see `[files."<name>"]`).
- Two `[files."<name>"]` keys of which one is a directory above the other (see `[files."<name>"]`).
- A `[files."<name>"]` key the operating system will not write. golden-census refuses it when the files are written, not at load (see `[files."<name>"]`).
- A `verdict` or `failing` that is not a string or does not compile (see `tallies`).
- A standard output or standard error that is not UTF-8 text. golden-census refuses it when the row runs (see `run`, "Streams").
- A `writes` file the surface produces that is not UTF-8 text. golden-census refuses it when the row runs, not at load (see `writes`).
- A `writes` path that a link leads outside `<WORK>`. golden-census refuses it when the row runs, not at load. It refuses a path that a `run` row's own command makes lead outside after that row runs (see `writes`).
- A `[[movements]]` `attribution` that is present and empty or blank. Leave the key out to record `(no attribution)` (see `[[movements]]`).
- Two `[[movements]]` rows whose `path` is the same string (see `[[movements]]`).
- A `census` file that is missing or fails its own checks (see `census-format.md`).

## Example — the shipped worked example

`examples/python-function/manifest.toml`, whole. The subject is one pure function over two text fixtures. The manifest is what `golden-census init <DIR> --template python-function` writes with its holes filled and nothing else changed. That is why the file reads as a form rather than as prose.

The live rows are everything with no `#` in front of it. They are a complete manifest: one `[subject]`, one input, one `run` surface, and the census beside it. Three tables and eight keys are the floor. A subject with one entry point needs nothing more.

Everything behind a `#` is a key this subject has no use for. Each is written out with the sentence that says when it is the right key:

- `version`;
- an input's `git`, `sha` and `expect_counts`;
- a surface's `inputs`, `env`, `needs` and `counter`;
- the `skip`, `matrix` (with its own `record_argv`) and `tallies` kinds;
- `[surface-sets]`, `[[setup]]`, `[files."<name>"]` and `[[movements]]`.

A consumer uncomments what their subject calls for. Read the commented rows as the rest of this document in one page.

The file shows two things that no fragment above can.

1. `command` spells `<PYTHON>` and `<HERE>/runner.py`. The runner lives beside the manifest, not under `root`. The recorded argv of every row therefore carries neither the interpreter nor the entry point: `surfaces.json` records what comes after `command`.
2. `writes` is `"<WORK>/<input>-<surface>.json"`. The two name placeholders make one line serve every row. The `<WORK>` prefix is what makes the path foldable, which is why a `writes` without it is refused.

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
