# The mutants file

Open this file at step 7 of "Plugging a project in, in order", or when the gate asks whether the checks work. A mutant is one deliberate edit to the subject, together with the checks that must catch it. `golden-census mutants` plants each mutant in a copy of the subject, runs every check, and prints a table of mutant against check.

The whole rule for every key is in the format document, `docs/mutants-format.md` under the `docs` directory `golden-census --help` names. This file carries the row to copy. The strict-key rule of `references/manifest.md` holds here too.

## What is a fault of whom

Three things are a FAIL of the checks, never of the subject.

- A mutant that no check catches. It shows a hole in the net.
- A check that a mutant names in `expect`, and that stays SILENT.
- A mutant whose comparator is REFUSED.

The fix is a better check, never a smaller `expect`. `references/verdicts.md` reads the table.

## The row to copy

```toml
[checks.comparator]
builtin = "compare"
golden  = "<HERE>/golden"           # beside this file; a bare path is read inside the mutated copy

[checks.differential]
command = ["<PYTHON>", "run_differential.py", "<ROOT>"]   # cwd = this file's directory, when that script sits outside the subject root
# command = ["<PYTHON>", "tests/run_differential.py", "<ROOT>"]   # a path that exists from the subject root: cwd = the mutated copy, and the script is the copy's
fires   = "exit-nonzero"                                  # or { pattern = … } / { absent = … }

[[mutant]]
name    = "lost role"
file    = "app/syntax.py"
find    = 'role = "declaring"'       # must occur EXACTLY once
replace = 'role = "plain"'
expect  = ["differential", "comparator"]
```

This block loaded and ran in a `mutants` run on a scratch project.

## Rules for the row

1. **`find` occurs exactly once in `file`.** The count is taken in the working tree before any clone is made, and again in the clone, which holds the committed text; zero or several occurrences in either is a refusal that names the mutant. A mutants file is written against one state of the subject, and it refuses when the code moves under it.
2. **`file` is a relative path under the subject root.** It is not absolute, has no `..` component, and does not resolve out of the root through a link.
3. **`file` is committed.** A file that was never committed is a refusal naming the mutant and the file. `SKILL.md` step 7 says what `mutants` clones and what a repository `git init`-ed inside the subject costs.
4. **`expect` names the checks that must fire.** Every other check's verdict is reported and does not gate.
5. **Written strings may spell three placeholders.** `<PYTHON>` is the interpreter running golden-census. `<ROOT>` is the MUTATED COPY, never the original. `<HERE>` is the directory the mutants file sits in, and it stays that directory under `mutants`; the manifest's `<HERE>` is carried onto the copy when the manifest sits inside the checkout (`references/manifest.md`), even when the two files sit side by side. Any other token is refused when the file is read.

## The checks

`[checks.<name>]` is a `builtin = "compare"` or a `command` with a `fires` condition.

- `builtin = "compare"` is a full capture of the mutated copy under the manifest, compared to `golden`. It is FIRED when the comparison is not IDENTICAL. It reads the manifest's `[[movements]]` as `compare` does, so a permitted row does not fire it. It is REFUSED, never FIRED, when its capture refuses.
- `golden` resolves three ways. A bare path (`tests/golden`) is read in the mutated copy, so the golden set must be committed in the subject's repository. `<HERE>/…` is read beside the mutants file. An absolute path is itself. A refusal about a missing golden names which form it was read as.
- A `command` check has a `fires` condition. `"exit-nonzero"` fires on a non-zero exit. `{ pattern = <regex> }` searches stdout and stderr, each on its own, in multiline mode, as printed. A check that ends its lines with `\r\n` keeps the `\r`, so a pattern that ends in `$` ends in `\r?$` to match. `{ absent = <text> }` fires when the text that a clean run prints is missing.
- A `command` check runs in the mutants file's own directory. One case differs: when the first element after `<PYTHON>` names a file inside the subject root, an absolute path under it or a relative one that exists from the root, it runs in the mutated clone. A script that lives inside the subject needs this, and a mutants file inside the checkout usually names one. `<HERE>` is the mutants file's own directory, never the copy. An inline `python3 -c …` runs beside the mutants file and imports the UNMUTATED package: a check that stays SILENT forever, which reads as a pass whenever no mutant names it in `expect`.
- It runs under the census's environment, with one change: `TMPDIR` is a directory of the check's own, removed after it. A check whose temporary files follow `TMPDIR` never writes them into the clone. No census needs `TMPDIR` in its `passthrough` for this.
- That directory is 40 characters longer than the temp root. Under the width rule's 49-character root (`references/machine.md`), a Unix socket a check makes in a `tempfile.mkdtemp()` directory under it still fits.
- A `TMPDIR` the check left unremovable is named in one line, `a directory golden-census made could not be removed: <path> — delete it by hand and name it in your report`. The check's verdict stands.

## The run, in order

1. golden-census loads the manifest and the mutants file. It refuses on any of these:
   - an unknown key, or an unknown check name in `expect`;
   - a missing `file`, or a `file` outside the root or not committed;
   - a `find` that is not unique;
   - an element of `[subject] command` that is an absolute path into the subject root — spell it relative to `root`, or as `<HERE>/…`, so that it is carried onto the copy.
2. It clones the subject root. The copy is repo-shaped, because a subject that stamps its output with its commit needs a repository to read.
3. The null mutant runs every check on the unmutated clone. Any FIRED is a refusal of the run, naming the check, because the verdicts on the real mutants would mean nothing. A capture or a comparison that refuses on the unmutated clone is REFUSED, and the run's refusal is that one's.
4. Each mutant gets a fresh clone. golden-census applies the edit, commits it so the tree is clean at a new sha, and runs every check.
5. The table and the verdict print. Exit 0 means every mutant was caught by every check it expects and no check was REFUSED. Exit 1 means otherwise. Exit 2 is a refusal of the run.

Read the SILENT cells of the table, not the FIRED ones. `references/verdicts.md` shows one. In the shipped example, each of the two checks catches the mutant the other misses. A column of FIREDs all the way down would mean a check that fires at anything. The null mutant row rules that out.

