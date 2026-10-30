# The census

The census lists every input to the subject's output that is not the subject's own code. The inputs include:

- environment variables;
- the width of the temp root;
- the clock a renderer reads;
- the checkout's absolute path;
- the subject's own temporary names;
- the versions of the tools it shells out to;
- the fact that it runs inside a git checkout.

Each row is one input and its disposition: pinned to a constant, folded to a placeholder, stated with the capture, or required as a precondition. For every pin and fold, the row also carries the control that proves the disposition matters.

A row nobody pinned or folded is a capture that will move. golden-census reads the census before the first run of a capture and runs the controls. It refuses to capture if a control fails or a precondition does not hold.

Two captures of an unchanged subject must be byte-identical before a manifest counts as complete. `capture --manifest <MANIFEST> --out <DIR> --twice` shows that.

The standard for adding a row is evidence, not possibility. A row defends against an input seen to move a golden when nobody expected it to. It does not defend against a thing that could in principle reach the output. `finding` records what the row defends against, so a later reader knows.

## Vocabulary

| word | meaning |
|---|---|
| input | one thing outside the subject's code that can change its output |
| pin | hold the input at a constant for every subject run |
| fold | let the input vary, and replace the token it leaves in the output with a placeholder at capture time |
| state | record the input's value in the capture log; it is not known to move a surface |
| precondition | a fact that must hold before a capture or compare runs; a REFUSAL (exit 2) when it does not |
| control | a planted case that proves a pin or fold matters: the output moves without it and holds with it |
| passthrough | a variable copied from golden-census's own environment into the subject's, by name |

## The environment rule

Every subject subprocess runs under an environment the census builds from nothing. It holds the pinned variables at their pinned values, the passthrough list, the surface's own `env`, and golden-census's child marker, and nothing that golden-census's own environment happens to hold.

A variable the census does not name cannot reach the subject, so it cannot move a surface. This is enforcement by construction, not detection.

What no environment variable carries is left to detection: a clock, the file system's temp path width, a tool's version. Those are the rows with controls.

```toml
[environment]
inherit     = false                     # the only value golden-census accepts
passthrough = ["PATH", "HOME"]          # copied by name; nothing else is
```

- `PATH` is passed through because the subject shells out to `git`.
- `HOME` is passed through because `git` reads its configuration there.
- A consumer whose subject needs another variable adds its name to the list and writes why in a TOML comment beside it. `passthrough` is a list of names and holds nothing else, so the reason has nowhere else to live.
- The contraband scan finds paths only. A passed-through secret, user name or host name that reaches a golden is the census author's to keep out of the subject's output; `probe` scans for passed-through values and a capture does not.

One variable is golden-census's own and appears in no census: `GOLDEN_CENSUS_CHILD=1`. golden-census sets it in every subject environment, after the pins and the passthrough.

- A census row that pins it is refused when the census is read.
- A surface's `env` that names it is refused when the manifest is read.
- Each refusal names its file and its row or surface.
- The variable states a fact about the run, not about the machine: this process was started by golden-census. `docs/contract.md` says what a subject may do with it.
- A census that pins the environment records the variable in its environment rows like any other. A golden recorded before golden-census set it moves by that row. The movement is attributed to golden-census, not to the subject.

## File format

The census is TOML, read with `tomllib`. Rows are `[[input]]` tables. Every row has `name`, `disposition` and `finding`. Pins and folds also have `control`.

`finding` is the sentence that says how this input was seen to move a surface. It is the reason the row exists.

**Every key is read or refused.** golden-census reads every key of every table of this file, or refuses it.

- A row, a `control`, `[environment]` or `[fixtures]` that carries a key golden-census does not read is REFUSED when the census is read.
- The refusal names the key, the table it is in, and the keys that table takes.
- A key of a json-fields fold's `serialization` table is refused the same way. So is the key `serialization` on any other fold, which reads none.
- A row's keys are the three every row has, its own disposition's keys, and `control` where that disposition reads one. A `control` on a `state` or a `precondition` row is refused by name, because neither reads it.

**The placeholders a census string may spell** are these. They apply wherever a string appears: a pin's `value`, a `state` command, a `precondition` command, a control's `command`, and a `drift` control's `output`. `output` spells `<WORK>` alone, and only at its start.

| token | what it is |
|---|---|
| `<ROOT>` | the subject root |
| `<WORK>` | golden-census's work directory for this run |
| `<CLONE>` | an input's clone directory, when the run made one |
| `<PYTHON>` | the interpreter running golden-census |
| `<HERE>` | the directory this census file sits in |
| `<FIXTURE>` | the `[fixtures]` directory, in a control's `command` only |

- golden-census refuses any other token, and `<FIXTURE>` anywhere but a control's `command`. It refuses when the census is read, before anything runs. The refusal names the token and the whole list that string may spell.
- `<FIXED-WIDTH-DIR:N>` is not a placeholder. It is a pin value that golden-census resolves itself, and it is the whole of the value.

## Dispositions

The commands a census names are a `precondition`'s, a `state` row's and a `drift` control's. The manual states what standard input every command golden-census starts receives.

### `pin`

```toml
[[input]]
name        = "terminal width"
disposition = "pin"
variable    = "COLUMNS"
value       = "80"
finding     = "argparse and most renderers wrap at $COLUMNS, so an unpinned width moves a surface by itself"
control     = { shape = "vary", surface = "the-input/the-surface", value = "40" }
```

- `variable` and `value` are set in every subject environment.
- A variable is pinned by one row. Two rows that pin one variable are refused when the census is read, naming both rows and both values, because the later value would replace the earlier.
- `control` of shape `vary` runs the row the control names three times: twice under the pin, and once under `value`.

**The three runs of a `vary` control.**

- golden-census makes each run alone, in a new place that holds only what preparation put there. The place is a new work directory. Where the census pins `<FIXED-WIDTH-DIR:N>`, it is also a new fixed-width temp directory.
- Preparation is what a capture does to the place before its first row, done for this row alone. golden-census checks the census's preconditions. It writes the manifest's `[files]`. It runs the setup steps the row `needs`, and no other row's.
- A row that reads what another row's setup step made must name that step in its own `needs`.
- golden-census does all of the preparation again before each of the three runs. A setup step the row needs therefore runs three times for every `vary` pin, in front of every command that runs the controls. Where two rows show the pin, name the one that needs less.
- Two trees are not part of the place. They are the same in all three runs. One is the subject's own tree. The other is the pinned tree of the row's input: the clone kept in the cache directory, checked out at the pinned commit and checked clean before each run, as it is before a capture.
- `manifest-format.md` states what a row may leave in a tree (see `[inputs.<name>]`). A run of the control that leaves something `git status` lists in the pinned tree refuses the command at exit 2, as a capture's rows do.
- A capture's own log lines, the `census state` block and the subject's `version`, are not preparation. golden-census does not run them.
- `census --manifest <MANIFEST>` and `--selfcheck --manifest <MANIFEST>` print the `clone:` lines that each run printed under the control's row. They are the `clone:` line and, in a kept clone, the line that names what git ignores there. Each line opens with which of the three runs printed it. A block in front of `capture`, `compare` or `mutants` prints no row that passed, and so none of these lines.

**What the control expects.**

- The two runs under the pin are expected IDENTICAL.
- The run under `value` is expected to DIFFER from them.
- The difference may be in the row's exit code. It may be in what a capture records of the row's stdout, its stderr or the file it `writes`.
- golden-census judges the difference after the census's folds, under the surface's own `env`.
- A run the control cannot compare is a disclosed SKIP. It names which of the three runs it was and why. It is never a pass. The causes are:
  - a place that could not be made, or whose preparation was refused: a precondition that does not hold, a setup step that exits non-zero, a temp root too wide for the pin;
  - an input whose pinned tree could not be cloned;
  - a run that would not start, such as a program not on this machine;
  - a run refused before it could be compared, a fold's refusal of its text included.
- A pin whose three runs agree is `UNPROVEN`. It is a FAIL of the census, because the census claims the pin matters. Find the surface it moves, or rewrite the row as a `state` row with `variables = [...]`, which records the value and pins nothing.
- Where the two runs under the pin agree before the census's folds as well, the row also says whether the run under `value` differs from them before the folds. When it does, what the variable changed does not reach the golden.
- When the two runs under the pin differ, the row is a FAIL whose `actual:` line opens `the two runs under the pin differ`. It is never `UNPROVEN`, whatever the run under `value` did. Find what differs between two runs of the row, and pin or fold it. Or point the control at a surface that is steady. Until those two runs agree, the control cannot say whether the pin matters.
- The surface is one of the manifest's own `<input>/<surface>` rows whose surface runs: no `kind`, or `kind = "run"`. golden-census refuses a `vary` control that names any other key when the manifest is read.

**A Python subject pins `PYTHONHASHSEED`.** The interpreter draws a random seed at startup for its string hashes, so a set of strings walks out in a per-run order. The pin holds within one Python version. The subject should still order its own output. The neutral template carries this row, commented out:

```toml
[[input]]
name        = "Python's hash seed"
disposition = "pin"
variable    = "PYTHONHASHSEED"
value       = "0"
finding     = "a set of strings prints in an order the interpreter chose at startup, so two runs differ by bytes nobody changed"
control     = { shape = "vary", surface = "the-input/the-surface", value = "1" }
```

**Shape `drift`** is for an input that moves with time, not with a value golden-census can choose.

```toml
[[input]]
name        = "the clock renderers read"
disposition = "pin"
variable    = "SOURCE_DATE_EPOCH"
value       = "0"
finding     = "a renderer stamps the time into what it writes, so two runs a second apart differ by bytes nobody changed"
control     = { shape = "drift", command = ["<PYTHON>", "-c", "import os, time; open('<WORK>/stamp.txt', 'w').write(os.environ.get('SOURCE_DATE_EPOCH') or repr(time.time()))"], output = "<WORK>/stamp.txt", wait = 1.2 }
```

- golden-census runs `command` twice, `wait` seconds apart, without the pin. It expects the outputs to differ. It runs `command` twice with the pin and expects the outputs to be identical.
- `output` is either absent or a file. When it is absent, golden-census compares the command's standard output. Otherwise it compares the file, as a string.
- A file is a path relative to `<WORK>`, the directory the command runs in, or a path that opens with `<WORK>/`.
- golden-census refuses any other spelling when the census is read. That covers an empty one, an absolute path, another placeholder, and a path that climbs out with `..`. It refuses a value that is not a string too.
- golden-census removes the file before each of the four runs, so each run is judged on the file it wrote.
- A file that a link takes out of `<WORK>`, before a run or after it, refuses the command. golden-census neither removes nor reads that file.
- A command not on `PATH` is a disclosed SKIP of this control, never a pass. So is a command named by an absolute path, or by one that opens with a placeholder, that is not there. A pin whose only control SKIPs is reported as such.
- golden-census REFUSES a program named by a relative path with a `/` when the census is read. The command runs in `<WORK>`, so the path would be looked for there. Spell it `<HERE>/…` or `<ROOT>/…`.
- The row above runs the interpreter, which is always there, so the pin is exercised on every machine. Point it at the tool that actually stamps the time when you have one. Read the SKIP as the price of naming a tool that may be absent.
- The row's label prints the first word of `command` as you spell it. A `<PYTHON>` stays `<PYTHON>`, so the verdict you paste carries no path of your machine.

The next pin holds the width of the subject's own temp root:

```toml
[[input]]
name        = "the subject's temp root, and its width"
disposition = "pin"
variable    = "TMPDIR"
value       = "<FIXED-WIDTH-DIR:51>"
finding     = "the length of TMPDIR, not the subject, decides how much of a temp path reaches a golden whenever a subject prints one through a fixed-width slice; pinning the width moves that decision out of the machine and into this file"
control     = { shape = "builtin", name = "fixed-width-dir" }
```

**`<FIXED-WIDTH-DIR:N>`**

- golden-census makes a fresh directory under the machine's temp root whose absolute path is exactly `N` characters long. It pads the leaf name to reach that width, asserts the width, and removes the directory in `finally`.
- Fold its path with a `path` row whose `source` is `fixed-width-dir`. The placeholder that row names is the consumer's own word. The census below spells it `<ENGINE-TMPDIR>`, as one choice among many.
- A root needs the root itself, a separator and at least one character of leaf name. The widest root that can hold an `N`-character path is therefore `N-2`.
- A census has one width. Two `<FIXED-WIDTH-DIR:N>` pins of different `N` are refused when the census is read, naming both rows, because a capture makes one directory, of the first width. The `fixed-width-dir` control belongs to the pin whose value is `<FIXED-WIDTH-DIR:N>`; on a pin of any other value it is refused when the census is read.
- A root of `N-1` characters or more cannot hold the path. That is a REFUSAL. Its `next:` line names the command that prints a root that fits. On macOS that is `getconf DARWIN_USER_TEMP_DIR`, whose root is 49 characters and does fit at the `N` of 51 that the census below uses.
- An `N` that leaves more room than the file system allows in one name is a REFUSAL too. It names the root, `N`, the name's length and the operating system's answer. The limit is the file system's, so golden-census meets it when it makes the directory, not when it reads the census.
- `compare --manifest <MANIFEST> --golden <GOLDEN> --against <DIR>` makes no such directory and runs at any width.
- `--selfcheck` alone reads no manifest, so it makes no such directory for a census of yours. Its own arms make and remove fixed-width directories under the temp root, from the bundled fixture's census and their own. They are disclosed SKIPs under a root too wide for them.
- `--selfcheck --manifest <MANIFEST>` runs the census's `fixed-width-dir` control. When the machine's root fits, that control makes one real directory. An `N` the file system refuses is refused there too.
- The manual lists the commands that check the temp root before the width, and the refusal for a root where no directory can be made.
- The `fixed-width-dir` builtin control is arithmetic on constructed widths, never a real wide directory. A control that only runs on a short temp root is not a control. The builtin control adds one real directory when the machine's root fits. It is a disclosed SKIP when the root does not fit.

### `fold`

A fold names the token that moves and the placeholder that replaces it.

A `regex` fold is also scoped to the surfaces it may touch. A fold applied everywhere would swallow a future timing on any surface without anyone seeing it. A consumer's regex fold therefore names its rows. The neutral census's `path` folds use `"*"`, because the directories they fold are golden-census's own and can appear on any row.

**`scope`**

- `scope` is a `regex` fold's key.
- golden-census REFUSES a narrowing `scope` on a `path` or `json-fields` fold when the census is read. The refusal names the row and its kind. The row key a scope is matched against reaches only the regex loop. A scope on either of the other two kinds would be checked at load and ignored at record.
- `scope = "*"` is the default said out loud. It is legal on every kind. So is a list that holds only `"*"`, which is the same statement in the format's other spelling.
- golden-census REFUSES a list that mixes `"*"` with row names. `"*"` is every row, so such a list says every row and these rows at once. Only one of them can be what the fold does.
- To narrow what a path fold reaches, name a narrower directory. To narrow a json-fields fold, name narrower `paths`.

**A `regex` fold and the subject root**

- A `regex` fold sees the text as the subject wrote it, before the built-in `path` folds. For a written `.json` file, that text is the file's text after its `json-fields` folds.
- A pattern that can match inside one of the directories golden-census made must be scoped to the rows that need it. The subject root is the main case.
- A fold that applies to every row, and whose `volatile` group takes part of the subject root and leaves the rest, is REFUSED when the manifest is read. The refusal names the row and quotes what that group matched. It quotes the group, not the whole match, because the group is all a fold replaces. A match its group took no part in moves nothing and is no overlap.
- A group that takes the whole root leaves nothing for the root fold to miss. golden-census does not refuse it.
- A pattern that reaches the subject root only with the text around it cannot be seen at load. During a capture, golden-census REFUSES any fold whose group would replace part of the subject root in a row's text and leave the rest. The refusal names the row, the fold, the pattern and the text.
- The order is a contract, not an accident. A fold that names the subject's own temporary directories, made under a directory a `path` fold folds, depends on seeing the raw path.

There are three kinds.

```toml
[[input]]
name        = "the checkout's absolute path"
disposition = "fold"
kind        = "path"
source      = "root"                    # root | work | clone | fixed-width-dir
placeholder = "<REPO>"
finding     = "every JSON root field and every report header carries it; without the fold no golden reproduces in another worktree and a home path is committed"
```

- `kind = "path"` folds an absolute directory that golden-census knows: the subject root, its work directory, an input's clone, or the fixed-width temp directory.
- golden-census replaces the directory longest-first, in both its given and its `realpath` form. macOS serves `/tmp` and `/private/tmp` as one directory.
- It replaces the directory only where its name ends. `<root>/x`, `<root>.` and `<root>.bak` fold. `<root>-old`, `<root>2` and `<root>_x` are other directories, which the contraband scan then refuses.
- The scope is every surface.
- The four `source` values are the four directories. A census that omits one of them is told so, because the contraband scan would refuse the capture anyway.
- A fold for a source no input produces is a disclosed SKIP in the self-check, never a pass. A `clone` fold in a manifest with no `git` input is one example. Such a fold is unexercised by construction until an input makes the directory.

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

- `kind = "regex"` takes a Python regular expression with a group named `volatile`. golden-census replaces only that group, so the rest of the line stays a byte comparison. Multi-line mode is on.
- A subject that prints `\r\n` is recorded with it, and `$` does not match before a `\r`. A pattern that anchors on `$` spells `\r?$`.
- A pattern that contains a single quote goes in a TOML multi-line literal string (`'''…'''`). A one-line literal string cannot hold one.
- `scope` is `"*"`, or a list that holds only `"*"`, or a list of `<input>/<surface>` rows. `scope` belongs to this kind.
- A `regex` fold reaches a written `.json` file too, after that file's `json-fields` folds.
- The `control` has three arms, and a fourth when the fold has a `scope` list:
  1. golden-census normalizes `sample` and `moved` and expects them IDENTICAL. The fold fired. It also applies this row's own `pattern`, alone, to `sample` and to `moved` and expects each to change. A second fold that folds the same token does not count for this row: a row whose own pattern matches nothing is a FAIL.
  2. It compares them unnormalized and expects them DIFFERENT. The fold was needed. This is the honesty arm.
  3. It changes one byte of `sample` outside the volatile group and expects that still REPORTED. The fold replaced the token, never the line.
  4. For a fold with a `scope` list, it also runs the sample through a surface outside the scope and expects the moved token REPORTED there.

A second regex row is scoped to the rows it touches. It is the shipped example's own row, commented out in `examples/python-function/census.toml` because that subject prints no duration:

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

The `scope` list is why the fold is safe. `<DURATION>` replaces the token on the rows that carry a duration and nowhere else. A duration that appears on a row nobody scoped is a diff a reader sees, not a token something swallowed.

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

- `kind = "json-fields"` applies to written `.json` surfaces. The extension may be in any case: `.JSON` counts too.
- golden-census parses the document. It replaces every named field under every named path with the placeholder. A path that is absent is skipped, and so is a field that is absent. It re-serializes the document with exactly the stated `serialization`.
- `serialization` takes two keys and no others: `indent`, an integer (`true` is refused), and `ensure_ascii`, a boolean.
- Before it replaces anything, golden-census asserts the round trip. Re-serializing the untouched document must reproduce the subject's document, with its trailing line endings set aside. Those are recorded exactly as written.
- When the round trip fails, the capture REFUSES. The subject's JSON writer no longer matches the stated `serialization`, and the golden would silently re-format it.
- A written `.json` file then passes through every `regex` fold whose scope takes its row, and then the `path` folds, in that order.
- The `control` is two files under `[fixtures]`. golden-census reads each when it reads the census. It REFUSES then a file that is missing, will not open, or is not UTF-8 text, and names the file. The control has the same three arms as the regex fold.

### `state`

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

- golden-census runs each command and reads each variable. It reads a variable as the subject will see it, after the environment rule, so an unlisted variable reads `<unset>`.
- It prints a `census state` block in the capture log. With the second row, the block shows `LANG = '<unset>'` and `LC_ALL = '<unset>'` when neither variable is passed through.
- The state is not a golden. A version string that moves between machines would make every golden a statement about the machine.

### `precondition`

```toml
[[input]]
name        = "the subject's tree is a git checkout"
disposition = "precondition"
check       = "git-checkout"
clean       = false
finding     = "a copy with no repository is a different subject: anything the subject reads from git — a commit stamp, a describe line, a dirty flag — changes shape or disappears, and the capture log's `git log -1 --oneline` is what a later reader attributes a movement against"
```

**`check = "git-checkout"`**

- `git -C <ROOT> rev-parse --is-inside-work-tree` must answer `true`.
- The capture log prints `git log -1 --oneline` for the record. When that git does not exit 0, the log prints `no revision quoted`, with how it ended and what it printed on stderr: its first line, or that it printed no text there.
- `clean = true` also requires the tree to be clean: `git status --porcelain` must exit 0 and print nothing. The manual lists the git settings golden-census gives that command, so that the global git configuration cannot change the answer.
- The default is `clean = false`. A `compare` against a dirty tree is the developer's ordinary loop. The consumer's rule that a comparison counts only after the commit is theirs to state.

**`check = "command"`**

- Give it `command = [...]` and `expect = "exit 0"` or `expect = "empty stdout"`. Use it for anything the git check does not cover.
- `empty stdout` holds when the command exits 0 and prints nothing but white space on standard output.
- Under either expectation, golden-census refuses a command that exits non-zero, or that a signal ends. The refusal names its exit code or the signal, whatever the command printed.
- golden-census refuses a command that prints a byte that is not UTF-8. The refusal names the stream and tells you to make that command print UTF-8, or to change or drop the row. A `git-checkout` row's git is held to the same rule.
- `command` may spell the placeholders listed under "File format". golden-census refuses any other when the census is read.
- A `command` precondition runs under golden-census's OWN environment, not the built one. Its cwd is `<ROOT>`.
  - The pins and the passthrough list are what every subject subprocess sees. That is what `[environment] inherit = false` states.
  - A precondition is not a subject run. It is a question asked about the machine before any subject run happens.
  - A check that asked the question under an environment built from nothing could not find its tools on `PATH`, unless the census had already listed them.
  - `git-checkout` runs the same way, for the same reason, and because git needs `HOME` to read its config.
  - A precondition command that depends on a pinned variable does not see the pin.

**A fact must hold, or golden-census refuses.**

- A precondition that fails is a REFUSAL (exit 2) before the first run, with the check named.
- It is not a FAIL. A FAIL is a statement about the subject. A REFUSAL is a statement about the run.
- Whether a subject outside a git checkout is refused or merely recorded is the row's disposition. `disposition = "precondition"` with `check = "git-checkout"` refuses before the first run. A `state` row with `commands = [["git", "rev-parse", "--is-inside-work-tree"]]` records what git says and captures anyway; a `state` row takes `variables`, `commands` or both and no other key, so `check` and `clean` go with the disposition. Every row that moves for the missing repository is then a diff a reader must attribute by hand. The shipped example chooses `precondition`, because diffs produced by the absence of a repository are not statements about the subject.

**A file the subject reads from outside its tree.** A cache, a database or a downloaded index is an input golden-census cannot see. golden-census records what the subject printed and wrote, and never that file. Without a row for it, a comparison against a different copy of the file says IDENTICAL. Hold the file still with a `command` precondition over its checksum:

```toml
[[input]]
name        = "the index is the one the golden was recorded against"
disposition = "precondition"
check       = "command"
command     = ["shasum", "-a", "256", "-c", "sums.txt"]   # its cwd is <ROOT>
expect      = "exit 0"                    # commit the new sums.txt with the new golden
finding     = "the subject answers from this file; a different one moves every row"
```

- Commit the new `sums.txt` with the new golden.
- While the file matches, `census preconditions` shows `[OK] the index is the one the golden was recorded against: shasum -a 256 -c sums.txt — exit 0`.
- When the file differs, golden-census refuses at exit 2 with `REFUSED: precondition 'the index is the one the golden was recorded against' (check command, expect exit 0): shasum -a 256 -c sums.txt exited 1: shasum: WARNING: 1 computed checksum did NOT match`. (Both lines are from a run on a scratch subject.)

## `[fixtures]`

```toml
[fixtures]
dir = "fixtures"            # relative to the census; <FIXTURE> in controls
```

`[fixtures]` holds the small files the controls need. The bundled fixture's are two provenance JSON documents for its json-fields control. A `drift` control that renders something would keep its input here. Commit them beside the census.

- `dir` is a path relative to the census, or an absolute path.
- `<HERE>` is the one placeholder `dir` may spell. golden-census REFUSES any other when the census is read.
- `dir` must be a directory.
- golden-census REFUSES a json-fields row in a census with no `[fixtures]` when the census is read.

## What golden-census does with the census, in order

1. **Read and check the file.** golden-census refuses a wrong census in one sentence, before any run. It checks that:
   - every row has a known disposition;
   - every pin, and every `regex` or `json-fields` fold, has a control. A `path` fold's control is built in: the directory folds to its placeholder, and an absolute path golden-census did not make survives;
   - every key of every table is one golden-census reads;
   - every narrowing `scope` is on a `regex` fold and names rows the manifest defines;
   - no `scope` list mixes `"*"` with row names;
   - no fold that applies to every row has a `volatile` group that matches inside the subject root;
   - every `vary` control names a row the manifest records whose surface runs;
   - a `[fixtures] dir` is a directory, and every json-fields control's two files are there and read as UTF-8 text;
   - no variable is pinned by two rows;
   - every `<FIXED-WIDTH-DIR:N>` pin has the same `N`, and a `fixed-width-dir` control sits only on such a pin;
   - every `source` is one of the four;
   - the environment has `inherit = false`.

   A control whose key does not resolve is refused here. golden-census never skips it when the controls run.
2. **Preconditions.** golden-census checks each `precondition` row. A failure is a REFUSAL that names the row.
3. **Controls.** Every pin's and fold's control runs and prints a row: `[PASS]`, `[FAIL]`, or a disclosed `[SKIP]` with the reason. The block holds this census's controls and none of golden-census's own arms, which `--selfcheck` runs. After any `[FAIL]`, the capture or compare REFUSES. A tool that cannot show its checks go red has shown nothing.
4. **State.** golden-census reads the `state` rows and prints them.
5. **Capture**, under the environment the census built. A `regex` fold whose `volatile` group would replace part of the subject root in a row's text, and leave the rest, is REFUSED at that row. The refusal names the row.
6. **The contraband scan.** golden-census reads back every file written. It counts the files it reads. A file the scan could not open is a REFUSAL, not a clean file. The scan searches for these:
   - an absolute home path;
   - the subject root, the work directory, the clone and the fixed-width directory, each in its given and `realpath` forms;
   - any path under the machine's temp root that no fold recognized, and the temp root itself, with or without its closing `/`. A longer name that begins with the root's letters is not the root.

   A home path counts only where a path can start. It must not follow a name character, `.`, `~` or `-`. It must not follow a placeholder that this census's `path` rows folded into the file. (`<REPO>/home/x` is a path under the subject root. `<BR>/home/x` is a tag the subject printed and then a home path.) It does count right after an option word such as `-I`, `-L` or `-isystem`.

   One hit and the capture is REFUSED. The exit code is 2, the code every refusal carries: nothing was compared. The refusal names the file, line and token. Its `next:` line names a `path` row, by its `source`, that folds a directory of those four this census has no row for, or a `regex` fold for anything else.

   The scan's positive control is a planted home path in a scratch file. It runs first and golden-census prints it. A capture of the shipped example prints `contraband scan: 5 files written, 5 read, 0 hit(s)` and then a line that begins `contraband positive control: PASS — the scan found all`.

## Example — the shipped worked example

`examples/python-function/census.toml`, whole. The subject is one pure function over two text fixtures, the smallest subject there is.

The file is what `golden-census init <DIR> --template python-function` writes, with its holes filled and nothing else changed. `init` scaffolds a manifest, a census and a mutants file together, so this census arrives already carrying every disposition as a row. Most of them are commented out.

Read it as two layers.

1. The rows with no `#` in front of them are live. They are the environment rule, the `TMPDIR` pin with its built-in control, the four `path` folds, one `state` row and one `precondition`. They are the whole census a single-function subject needs, and the floor every census starts from. The four path folds are not optional, because the contraband scan refuses a capture that leaks a directory golden-census made.
2. The rows behind a `#` are the other dispositions. They are written out with their keys and left commented, because this subject has no use for them. They are:
   - a `vary` pin;
   - a `drift` pin;
   - a `regex` fold;
   - a `json-fields` fold;
   - a `state` row that reads variables;
   - a `command` precondition;
   - the `[fixtures]` directory a fold control needs.

A consumer uncomments the rows their subject calls for and fills in the values. Each row carries the sentence that says when it is the right row. A reader cannot derive that sentence from the format alone.

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

# The clock's other half: the zone a renderer prints a time in. A subject that
# prints local time is byte-identical for as long as the machine's zone does
# not change, and moves by whole hours the day it does. Name a surface that
# prints a time; the control runs it under a zone of another offset.
# [[input]]
# name        = "the zone renderers print a time in"
# disposition = "pin"
# variable    = "TZ"
# value       = "UTC"
# finding     = "a renderer prints the clock in the machine's zone, so a golden captured under one zone moves by whole hours under another"
# control     = { shape = "vary", surface = "the-input/the-surface", value = "Asia/Tokyo" }

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

# Two more path folds, for directories most censuses never meet. Leave them
# commented until a refusal names one: the clone fold when an input is pinned
# with `git` and `sha`, the fixed-width fold when a surface prints its temp
# path. Until then a capture prints one `census note:` line naming the two,
# and a capture that leaks either directory is refused with the row to
# uncomment.
#
# [[input]]
# name        = "an input's clone directory"
# disposition = "fold"
# kind        = "path"
# source      = "clone"
# placeholder = "<CLONE>"
# finding     = "an input pinned with `git` and `sha` is cloned once into the user's cache directory, and every later capture that pins the same `git` and `sha` reuses that clone"
#
# [[input]]
# name        = "the fixed-width temp directory"
# disposition = "fold"
# kind        = "path"
# source      = "fixed-width-dir"
# placeholder = "<ENGINE-TMPDIR>"
# finding     = "the pair of the TMPDIR pin above: the day a surface prints a temp path, the scan refuses the capture unless the directory folds"

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
#                                           # the default is every row; say it out loud as scope = "*", never as a list
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
