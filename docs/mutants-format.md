# The mutants file

A mutant is a deliberate small change to the subject's code, together with the name of the check that must catch it. The `mutants` command plants each mutant in a repo-shaped copy of the subject and runs every check. It prints a table: mutant × check → FIRED, SILENT or REFUSED.

Three things are a FAIL of the checks, not of the subject:

- A mutant that no check catches. It shows a hole in the net.
- A check that a mutant names in `expect`, and that stays SILENT.
- A mutant whose comparator is REFUSED.

Hand-planted mutants are re-planted by hand at every gate, or not at all. This file makes them data the gate re-runs.

## Vocabulary

| word | meaning |
|---|---|
| mutant | one `find`/`replace` edit to one file of the subject, with the checks expected to fire |
| check | a command run against the mutated copy whose result is read as FIRED or SILENT, or REFUSED for a comparator whose capture or comparison refused |
| the null mutant | the unmutated copy, run through every check first (see "Mechanics, in order", step 3) |
| FIRED | the check reported the change: its `fires` condition held |
| SILENT | the check did not report the change |
| REFUSED | the comparator's capture of the mutated copy refused, or its comparison did, over a moved row that two `[[movements]]` rows name. No comparison was made, so the check neither caught nor missed the mutant. The mutant is a FAIL. |

## File format

The mutants file is TOML, beside the manifest.

A string of this file may spell three placeholders:

- `<PYTHON>` is the interpreter running golden-census.
- `<ROOT>` is the MUTATED COPY, never the original.
- `<HERE>` is the directory this mutants file sits in.

golden-census refuses any other token when the file is read. The refusal names the token and the whole list. It comes before golden-census makes a clone.

**Every key is read or refused.** golden-census reads every key of every table of this file, or refuses it. A `[checks.<name>]` or a `[[mutant]]` that carries a key golden-census does not read is REFUSED when the file is read. The refusal names the key, the table it is in, and the keys that table takes.

**`golden`** resolves three ways. The form it is written in is the whole of how golden-census reads it:

| written as | resolved against |
|---|---|
| a bare path, such as `golden` or `tests/golden` | the MUTATED COPY, so the golden set has to be committed in the subject's own repository |
| `<HERE>/…` | the directory this mutants file sits in; the form a consumer whose goldens do not live in the subject needs |
| an absolute path | itself |

A refusal about a golden directory that is not there names which of the three forms it was read as.

The shipped example writes the second form. The other two are **invented for this document**, because that example has no use for them:

```toml
golden = "tests/golden"                 # a bare path: inside the mutated copy
golden = "/an/absolute/path/to/golden"  # itself, wherever it is
```

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

The `differential` check is invented for this document. The other two checks and the mutant are the shipped example's own.

The `find` is the current text of the file. A mutants file is therefore written against one state of the subject, and it refuses when the code moves under it. A value that is set at two places needs the whole block around one of them as its `find`. Otherwise the uniqueness rule refuses the run.

**Where a check runs.**

- The working directory of a `command` check is the mutants file's own directory.
- One case differs. When the command's first element after `<PYTHON>` names a file under the subject root, an absolute path under it or a relative one that exists from the root, the working directory is the mutated clone.
- `label` above is the second case: its script lives inside the subject. `differential` is the first.

**What a `command` check runs under.**

- The environment is the census's built environment, its pins and its `passthrough`, as every subject subprocess gets it. One variable differs: `TMPDIR`.
- golden-census sets `TMPDIR` to a directory of the check's own under the run's scratch directory, made before the check starts and removed when it ends, so a check whose temporary files follow `TMPDIR` never writes into the copy it runs in. Its path is `<temp root>/golden-census-mutants-XXXXXXXX/XXXXXXXX`, 40 characters longer than the temp root. golden-census does not make the census's fixed-width directory for a check.
- A `TMPDIR` the check left unremovable, and still on disk when the run ends, is named after the table, or above the refusal that ended the run, one line each: `a directory golden-census made could not be removed: <path> — delete it by hand and name it in your report`. The check's verdict stands.

**`[checks.<name>]`** is either a `builtin = "compare"` or a `command` with a `fires` condition.

`golden` belongs to the `builtin` and `fires` to the `command`. A `fires` on a `builtin` check, or a `golden` on a `command` check, is refused when the file is read, naming the check and the key. The check would run without it.

`builtin = "compare"` is a full capture of the mutated copy under the manifest, compared to `golden`. `golden` is written in whichever of the three forms above.

- It is FIRED when the comparison is not IDENTICAL.
- A row that the manifest's `[[movements]]` permits is not counted.
- A moved row that two of its rows name is REFUSED, as `compare` refuses it.
- It is REFUSED, never FIRED, when the capture of the mutated copy refuses. The mutant may have made the subject do something golden-census will not record, or the machine may have stopped the capture. Either way no comparison was made.
- golden-census prints the refusal's first line under the mutant's row. When the refusal has a block, it prints the block's first line under that. That line names the command.

A `command` check has a `fires` condition. There are three:

- `"exit-nonzero"`.
- `{ pattern = <regex> }`. golden-census searches stdout and stderr, each on its own, in multiline mode, as printed. A check that ends its lines with `\r\n` keeps the `\r`, so a pattern that ends in `$` must end in `\r?$` to match there.
- `{ absent = <text> }`. It is FIRED when the text that a clean run prints is missing.

**`file`**

- `file` is a RELATIVE path under the subject root. It is not absolute and has no `..` component. golden-census resolves it against the root, and `plant` opens it for writing. A `file` that breaks this rule is a REFUSAL that names the mutant and the value, before any clone is made.
- `file` must also RESOLVE under the root. A symbolic link out of the tree is spelled as an ordinary relative path, so golden-census asks the file system for the destination as well. A destination outside the root is a refusal that names the mutant and the path the link resolves to.
- `file` must also be COMMITTED. `mutants` plants each mutant in a `git clone --local` of the subject. That clone copies the last commit and not the working tree. A file that was never committed is not in the clone. It is a refusal that names the mutant and the file. The manual lists the git settings golden-census gives the clone.

**`find`** must occur exactly once in `file`.

- Zero occurrences is a REFUSAL that names the mutant. So are several. golden-census makes the refusal after the census's controls and before it makes any clone or plants any mutant.
- A mutant that no longer applies because the code moved is a refusal, never a silent pass.

**`expect`** names the checks that MUST fire. Every other check's verdict is reported but does not gate.

- A check that fires unexpectedly prints `FIRED` in its own cell. It prints `(<check>: unexpected)` at the end of the row, where every note about that row is collected.
- A check that `expect` names and that stays SILENT adds `(<check>: expected, SILENT)` to those notes. The mutant is then a FAIL.

This table is from a run of the shipped example with its second mutant replaced. The new mutant's edit moves a recorded surface and `LABEL`. It expects only the comparator:

```text
  mutant                            comparator  label
  the hyphen rule the counts carry  FIRED       SILENT
  a mutant                          FIRED       FIRED     (label: unexpected)
```

The net caught more than the table predicted. That is worth reading, not failing.

**A check gets no deadline from golden-census:** the caller owns every deadline, as the manual states.

## Mechanics, in order

1. Load the manifest and the mutants file. golden-census refuses on any of these:
   - a key that no table of the mutants file reads;
   - a `fires` on a `builtin` check, or a `golden` on a `command` check;
   - an unknown check name in `expect`;
   - a missing `file`;
   - a `file` that is not a relative path under the subject root, or that resolves out of it;
   - a `file` the clone does not carry;
   - a `find` that is not unique.
2. Clone the subject root with `git clone --local` into the scratch directory. The copy is repo-shaped. A subject that stamps its output with its commit needs a repository to read, and a bare file copy produces spurious diffs on every stamped surface. The manual's temp-root rule says what the temp root needs for a large subject.
3. **The null mutant.** Run every check on the unmutated clone.
   - Any FIRED is a REFUSAL of the run that names the check. Its verdicts on the real mutants would mean nothing.
   - A capture or a comparison that refuses on the unmutated clone is REFUSED. The run's refusal is that one's. It names the null mutant and the check. It carries the refusal whole, with its own `next:` and any about-to-run block it carries. It names any other check that fired there.
4. For each mutant:
   1. Make a fresh clone.
   2. Apply the edit.
   3. Run `git commit` inside the clone, so the tree is CLEAN at a new sha. A dirty stamp is longer than a clean one and moves the acceptance surface's size lines by itself, so the comparison comes after the commit.
   4. Run every check, with `<ROOT>` set to the clone and the manifest's root overridden to it.
5. Print the table and the verdict. The exit code is 0 when every mutant was caught by every check it expects and no check was REFUSED on it. It is 1 otherwise. It is 2 on a refusal of the run.

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

Read the two SILENT cells, not the two FIRED ones. Each check catches the mutant the other misses. The comparator sees a change that reaches a recorded surface, and is blind to one that does not. The `label` command check sees a constant no surface carries.

A column of FIREDs all the way down would mean a check that fires at anything. That proves nothing about the net. The null mutant row above the table rules it out: both checks are SILENT on the unmutated clone, so every FIRED below it is the mutant and not the check.

Two figures in that block are not about the example. `<PGID>` stands for the process group's number, which is this run's and no other's. The tally is of this census's own controls, one row per pin and per fold. It moves with the census and with what this machine's temp root lets a control exercise. Read the shape, and run the command for the number. golden-census's own arms are not in the tally: `--selfcheck` is where those are asked for.

A subject with a pinned input prints more. Each capture the comparator makes prints the lines `capture` prints about that input, under a heading that names the copy and the check:

- the `clone:` line;
- the line that names what git ignores in a kept clone, when there is one (see `manifest-format.md`, `[inputs.<name>]`).

A blank line ends each block. The null mutant's block comes before the null mutant's line. Each mutant's block comes before the table. The heading lines below are from a run on a scratch subject with a pinned input. `<url>` and `<full sha>` stand for the clone's address and commit:

```text
  the null mutant, check 'comparator':
    clone: <url> @ <full sha>, clean
  null mutant: comparator SILENT
  mutant 'a mutant', check 'comparator':
    clone: <url> @ <full sha>, clean
```

## Controls golden-census runs on itself

The `mutants` command has its own arms in `--selfcheck`, on a throwaway subject golden-census writes:

- A `find` that occurs twice is refused, naming the mutant.
- A mutant whose `expect` check stays silent is a FAIL row.
- A check that fires on the null mutant refuses the run.
- A mutant every check misses is a FAIL.

Without these arms, a table of FIREDs proves only that the printer works.

## Example — the shipped worked example

`examples/python-function/mutants.toml`, whole. It has two checks and two mutants. That is the smallest table that can say anything, because one check alone cannot be shown to catch what another misses.

The live rows are:

- `comparator`, the built-in. Its golden is named with `<HERE>/`, because the goldens sit beside this file rather than inside the subject.
- `label`, a command check. Its `fires` is `{ absent = … }`: FIRED when the text a clean run prints goes missing.
- The two mutants, one aimed at each check.

The commented rows are the two `fires` shapes this example does not use, `"exit-nonzero"` and `{ pattern = … }`. They stay in the file so that a consumer can see all three without leaving it.

```toml
# The mutants file: deliberate small changes to the subject's code, each with
# the name of the check that must catch it. `golden-census mutants` plants every one
# in a repo-shaped copy of the subject, runs every check, and prints the table
# mutant × check → FIRED, SILENT or REFUSED. A mutant no check catches is a
# FAIL of the checks, not of the subject: it shows a hole in the net.
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
