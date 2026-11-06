# The mutants file: `mutants.toml`

A golden proves that a change moved nothing the recording covers. It cannot prove that the recording covers everything a change could affect. If a change alters a part of the program whose output is never recorded, `compare` still says `IDENTICAL`. The mutants file is how a project tests for that. It lists small deliberate changes to the program, called mutants, and for each one the check that must notice it. A check that stays silent on a mutant shows a change the recording would miss.

The `mutants` command makes a copy of the program's repository, applies one mutant to it, runs every check, and repeats for each mutant. It prints a table with one row per mutant and one column per check. Each cell is `FIRED` (the check noticed the change), `SILENT` (it did not) or `REFUSED` (the check could not run). A mutant that a check named in its `expect` list does not notice is a failure of the checks, not of the program.

A check is either golden-census's own comparison, which captures the mutated copy and compares it with the golden, or any command of the project's own, with a rule for when it counts as having fired.

The file is `mutants.toml`, written by `init` beside the manifest, with its holes left for the project to fill. `mutants` refuses a file that still contains a hole.

This document covers:
1. File format
2. `[checks.<name>]`: a check
3. `[[mutant]]`: a change to the program
4. What `mutants` does, in order
5. The output
6. How golden-census checks `mutants` itself
7. The shipped example

## File format

The file is TOML. Three placeholders may appear in its strings:

- `<PYTHON>` is the interpreter running golden-census.
- `<ROOT>` is the mutated copy of the program, never the original.
- `<HERE>` is the directory this file is in.

Any other `<…>` token is refused when the file is read, before any copy is made. The refusal names the token and lists the three.

Every key in the file must be one golden-census reads. A `[checks.<name>]` or `[[mutant]]` table with a key golden-census does not read is refused when the file is read. The refusal names the key, the table, and the keys that table accepts.

A complete file, with every kind of entry:

```toml
[checks.comparator]
builtin = "compare"                 # golden-census's own compare of a fresh capture
golden  = "<HERE>/golden"           # beside this file: the shipped example's form

[checks.label]
command = ["<PYTHON>", "examples/python-function/label_check.py"]   # cwd = <ROOT>
fires   = { absent = "wordstats/1" }

[checks.differential]
command = ["<PYTHON>", "run_differential.py", "<ROOT>"]   # cwd = this file's directory
fires   = "exit-nonzero"

[[mutant]]
name    = "a constant no recorded surface carries"
file    = "examples/python-function/wordstats/tokenize.py"
find    = 'LABEL = "wordstats/1"'         # must occur EXACTLY once in the file
replace = 'LABEL = "wordstats/2"'
expect  = ["label"]
```

The `comparator` and `label` checks and the mutant are from the shipped example. The `differential` check is invented for this document, to show the third shape.

## `[checks.<name>]`: a check

A check is one of two kinds. It has either `builtin = "compare"` with a `golden`, or a `command` with a `fires` rule. A `golden` on a command check, or a `fires` on a builtin check, is refused when the file is read, naming the check and the key.

### The builtin comparison

`builtin = "compare"` captures the mutated copy under the manifest and compares the capture with the golden directory named by `golden`.

- It is `FIRED` when the comparison is not `IDENTICAL`.
- A row that the manifest's `[[movements]]` permits to move does not count as a difference.
- A moved row that two `[[movements]]` rows both name is `REFUSED`, as `compare` itself refuses it.
- When the capture of the mutated copy is refused, the check is `REFUSED`, never `FIRED`. The mutant may have made the program do something golden-census will not record, or the machine may have stopped the capture. Either way nothing was compared. golden-census prints the refusal's first line under the mutant's row; if the refusal has a block, the block's first line, which names the command, is printed under that.

`golden` is read in one of three forms, decided by how it is written:

| Written as | Resolved against |
|---|---|
| a bare path, such as `golden` or `tests/golden` | the mutated copy, so the golden must be committed in the program's own repository |
| `<HERE>/…` | the directory this file is in; the form for a project whose goldens are not inside the program's repository |
| an absolute path | itself |

A refusal about a golden directory that is not there says which of the three forms the value was read as. The shipped example uses the second form. The other two, for illustration:

```toml
golden = "tests/golden"                 # a bare path: inside the mutated copy
golden = "/an/absolute/path/to/golden"  # itself, wherever it is
```

### A command check

`command` is the argv of a command of the project's own. `fires` says when it counts as having noticed the mutant. There are three rules:

- `"exit-nonzero"`: fired when the command exits non-zero.
- `{ pattern = <regex> }`: fired when the regular expression matches stdout or stderr. Each stream is searched on its own, in multiline mode, exactly as printed. A command that ends its lines with `\r\n` keeps the `\r`, so a pattern that ends in `$` must end in `\r?$` to match.
- `{ absent = <text> }`: fired when text that a clean run prints is missing.

Where the command runs:

- Normally, in the directory this file is in.
- If the first element after `<PYTHON>` names a file under the program's root, either as an absolute path under it or as a relative path that exists from the root, the command runs in the mutated copy instead. `label` above is this case, because its script is inside the program. `differential` is the normal case.

What the command runs under:

- The environment the census builds: its pinned variables and its passthrough list, the same as every run of the program gets. One variable differs: `TMPDIR`.
- golden-census sets `TMPDIR` to a directory of the check's own, made before the check starts and removed when it ends, so that a check whose temporary files follow `TMPDIR` never writes into the copy it runs in. The path is `<temp root>/golden-census-mutants-XXXXXXXX/XXXXXXXX`, 40 characters longer than the temp root. golden-census does not make the census's fixed-width directory for a check.
- If that `TMPDIR` cannot be removed when the check ends and is still there when the run ends, golden-census prints one line for it, under the table or above the refusal that ended the run: `a directory golden-census made could not be removed: <path> — delete it by hand and name it in your report`. The check's result stands.
- No time limit. golden-census never stops a command for taking too long; the caller does, as the skill's `references/commands.md` explains.

## `[[mutant]]`: a change to the program

Each mutant has five keys.

- `name` is the row's label in the table and the word every refusal about this mutant uses.
- `file` is the file to change, as a relative path under the program's root. Three rules:
  - It must be relative, with no `..` component. An absolute path or one with `..` is refused when the file is read, naming the mutant and the value.
  - It must resolve under the root. A symbolic link that points out of the tree looks like an ordinary relative path, so golden-census also asks the file system where it leads. A destination outside the root is refused, naming the mutant and the destination.
  - It must be committed. `mutants` works in a `git clone` of the program, and a clone contains the last commit, not the working tree. A file that was never committed is not in the clone, and the mutant is refused when golden-census tries to apply it (step 4 below), after the null mutant's checks have run. The skill's `references/machine.md`, "The settings of git", lists the git settings the clone is made with.
- `find` is the exact current text to replace. It must occur exactly once in `file`. Zero occurrences, or more than one, is refused when the file is read, before any control runs or any copy is made, naming the mutant. This means a mutants file is written against one state of the program and refuses when the code changes under it, instead of silently passing. If the text occurs twice, use a larger block around one occurrence as the `find`.
- `replace` is what the text becomes.
- `expect` lists the checks that must fire. Every other check still runs and its result is printed, but it does not decide the verdict.
  - A check not in `expect` that fires prints `FIRED` in its cell and `(<check>: unexpected)` at the end of the row, where every note about the row is collected.
  - A check in `expect` that stays `SILENT` adds `(<check>: expected, SILENT)` to the notes, and the mutant is a failure.

This table is from a run of the shipped example with its second mutant replaced by one whose change moves a recorded surface and the `LABEL` constant, expecting only the comparator:

```text
  mutant                            comparator  label
  the hyphen rule the counts carry  FIRED       SILENT
  a mutant                          FIRED       FIRED     (label: unexpected)
```

The checks caught more than expected. That is worth reading, not a failure.

## What `mutants` does, in order

1. **Reads the manifest and the mutants file.** It refuses on any of these: a key no table reads; a `fires` on a builtin check or a `golden` on a command check; a check name in `expect` that does not exist; a missing `file`; a `file` that is not a relative path under the root, or that resolves out of it; a `find` that does not occur exactly once.
2. **Clones the program's root** with `git clone` into a scratch directory under the temp root (the skill's `references/machine.md`, "The temp root"). This clone is not kept in the clone cache. When the temp root is on the same file system as the program, git links the object files instead of copying them. The copy is a repository, not a bare copy of the files, because a program that stamps its output with its commit needs one to read; a bare copy would make every stamped surface differ. The note on Linux in `references/machine.md` says what the temp root needs for a large program.
3. **Runs the null mutant.** Every check runs on the unchanged clone first.
   - A check that fires on the unchanged program would fire on anything, and its results on the real mutants would mean nothing. So any `FIRED` here refuses the whole run, naming the check.
   - A capture or comparison that refuses on the unchanged clone refuses the run with that refusal, whole, with its own `next:` line, naming the null mutant and the check, and naming any other check that fired.
4. **For each mutant:** makes a fresh clone; applies the change (a `file` the clone does not contain is refused here, naming the mutant and the file); runs `git commit` inside the clone, so that the tree is clean at a new commit (a program that stamps its output with its commit would otherwise print a longer "dirty" stamp, which by itself moves the size of some recorded lines); then runs every check with `<ROOT>` set to the clone and the manifest's root overridden to it.
5. **Prints the table and the verdict.** The exit code is 0 when every mutant was caught by every check in its `expect` and no check was `REFUSED`; 1 otherwise; 2 when the run itself was refused.

## The output

This is the shipped example's own run, from `examples/python-function/`, with the command `golden-census mutants --manifest manifest.toml --mutants mutants.toml`:

```text
process group <PGID> — if this run hangs or crashes, stop everything it started with: kill -- -<PGID>

  3/3 census controls passed

MUTANTS  mutants.toml  (2 mutants, 2 checks)
  null mutant: comparator SILENT, label SILENT

  mutant                                  comparator  label
  the hyphen rule the counts carry        FIRED       SILENT
  a constant no recorded surface carries  SILENT      FIRED

  2/2 mutants caught by every check they expect
```

The two `SILENT` cells are the point. Each check catches the mutant the other misses: the comparator notices a change that reaches a recorded surface and cannot notice one that does not; the `label` command check notices a constant that no recorded surface contains.

A column of `FIRED` all the way down would mean a check that fires at anything, which proves nothing. The `null mutant` line above the table rules that out: both checks are `SILENT` on the unchanged program, so every `FIRED` below is caused by the mutant.

Two figures in this output are not fixed. `<PGID>` stands for the process group number, which differs every run. The `3/3 census controls passed` tally counts this census's own controls, one per pin and fold; it changes with the census and with what the machine's temp root allows a control to test. golden-census's own checks are not in that tally; `--selfcheck` runs those.

A program with a pinned input prints more. Each capture the comparator makes prints the lines `capture` prints about that input, under a heading naming the copy and the check: the `clone:` line, and, for a kept clone, the line naming what git ignores there (see `manifest-format.md`, `[inputs.<name>]`). A blank line ends each block. The null mutant's block comes before the `null mutant:` line, and each mutant's block before the table. From a run on a scratch program with a pinned input, with `<url>` and `<full sha>` standing for the clone's address and commit:

```text
  the null mutant, check 'comparator':
    clone: <url> @ <full sha>, clean
  null mutant: comparator SILENT
  mutant 'a mutant', check 'comparator':
    clone: <url> @ <full sha>, clean
```

## How golden-census checks `mutants` itself

`--selfcheck` runs `mutants` on a throwaway program golden-census writes, and checks that:

- a `find` that occurs twice is refused, naming the mutant;
- a mutant whose expected check stays silent is reported as a failure;
- a check that fires on the null mutant refuses the run;
- a mutant that every check misses is reported as a failure.

Without these, a table full of `FIRED` would prove only that the table printer works.

## The shipped example

`examples/python-function/mutants.toml`, in full. It has two checks and two mutants, which is the smallest table that can show anything: with one check, nothing can show that it catches what another misses.

The live entries are the builtin `comparator`, whose golden is named with `<HERE>/` because the goldens sit beside this file rather than inside the program; the `label` command check, whose `fires` is `{ absent = … }`; and two mutants, one aimed at each check. The commented-out entries are the two `fires` rules this example does not use, left in the file so that a reader sees all three without leaving it.

```toml
# The mutants file: deliberate small changes to the subject's code, each with
# the name of the check that must catch it. `golden-census mutants` plants every one
# in a repo-shaped copy of the subject, runs every check, and prints the table
# mutant × check → FIRED, SILENT or REFUSED. A mutant no check catches is a
# FAIL of golden-census, not of the subject: it shows a hole in the net.
# `docs/mutants-format.md` is authoritative for every key.
#
# `golden-census init` wrote this file with its holes IN PLACE; `mutants` REFUSES a
# file that still spells one.

# ------------------------------------------------------------------ checks

[checks.comparator]
builtin = "compare"                # golden-census's own: a full capture of the mutated copy under the manifest, compared to `golden`; FIRED when it is not IDENTICAL
golden  = "<HERE>/golden"        # the golden directory that capture is compared against; docs/mutants-format.md says how the path resolves

# A check of the consumer's own: any command, with the condition that counts
# as caught. Two or more checks that catch DIFFERENT mutants is the point of
# the table; one check that catches everything proves only that it is loud.
[checks.label]
command = ["<PYTHON>", "examples/python-function/label_check.py"]   # cwd = the MUTATED COPY, because that path is a file inside it
fires   = { absent = "wordstats/1" }      # FIRED when the text a clean run prints is MISSING

# The other two shapes the format offers, unused here and left as the neutral
# template wrote them:
# [checks.differential]
# command = ["<PYTHON>", "run_differential.py", "<ROOT>"]   # cwd = this file's directory; <ROOT> is the MUTATED COPY, never the original
# fires   = "exit-nonzero"                  # FIRED when the command exits non-zero

# [checks.one-walk]
# command = ["<PYTHON>", "tool/__main__.py", "--selftest"]  # cwd = <ROOT>, because the first element after <PYTHON> is a path inside it
# fires   = { pattern = '\[FAIL\]' }        # FIRED when the regular expression matches stdout or stderr

# ----------------------------------------------------------------- mutants

[[mutant]]
name    = "the hyphen rule the counts carry"  # the row of the printed table and the word every refusal about it uses
file    = "examples/python-function/wordstats/tokenize.py"  # the subject file this mutant edits, relative to the subject root
find    = "HYPHEN_JOINS = True"  # the exact current text; it must occur EXACTLY once in that file, or the run is refused naming the mutant
replace = "HYPHEN_JOINS = False"    # what that text becomes
expect  = ["comparator"]           # the checks that MUST fire; every other verdict is reported and does not gate

# A second mutant, aimed at a check the comparator cannot make: something no
# recorded surface carries, which only a command check can see.
[[mutant]]
name    = "a constant no recorded surface carries"
file    = "examples/python-function/wordstats/tokenize.py"
find    = 'LABEL = "wordstats/1"'
replace = 'LABEL = "wordstats/2"'
expect  = ["label"]
```
