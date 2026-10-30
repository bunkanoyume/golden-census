# The machine: the temp root, the clone cache and git

Open this file when a refusal names `TMPDIR`, `HOME` or a cache directory, when you work on Linux, or when a manifest pins an input to a commit. A refusal's `next:` line says what to do; this file states the rules behind it.

The manual (`docs/manual.md`) says the same for a person, and `docs/manifest-format.md` has the whole rule for a pinned input; both are under the `docs` directory `golden-census --help` names.

## Run one command at a time

- `SKILL.md` step 5 states the rule: one command at a time, and nothing changed under the subject, the golden directory or the temp root while it runs.
- A pinned input whose kept clone a row has dirtied is skipped by later captures until the clone is deleted (`references/census.md`, "What a row leaves behind"). A file edited during a run is read as it was when the run reached it.

## The temp root

golden-census makes its scratch directories under the temp root. That is `TMPDIR` when it is set.

1. **Use an absolute path.** golden-census starts each child in a directory of its own, where a relative path names a different directory.
2. **Spell it without `..`.** After a symbolic link, `..` names the parent of the link's target, not the directory spelled before it.
3. **Point it at a root where a directory can be made.** golden-census makes no temp root and tries no other. An unset or empty `TMPDIR` falls back to Python's own choice.
4. **Keep it narrow.** A capture needs a root of at most 49 characters. The census pins the subject's own `TMPDIR` to 51, and a directory made under a root needs the root, a separator and a name. A Unix socket path holds 103 characters, and a socket a `mutants` check makes under its own `TMPDIR` fits only under a root of that width.
   - Every command that runs the subject, `capture`, `compare` without `--against`, `mutants` and `probe`, refuses under a wider root. `census` runs under one and says so twice: a `note:` under its rows that a capture here would REFUSE, and a `[SKIP]` of the fixed-width-dir control's real-directory arm.
   - A root that fits is `$(getconf DARWIN_USER_TEMP_DIR)` on macOS and `/tmp` on Linux.
5. **On Linux, mind tmpfs.** The temp root is usually `/tmp`, a tmpfs sized at a fraction of RAM. `mutants` holds a clone and a capture per mutant under it, and `capture --twice` holds two capture trees. For a large subject, point `TMPDIR` at `/var/tmp`.

Every subcommand makes a directory under the temp root and checks the root first, except two. `init` writes only into the directory it is given. `compare --against` reads two recorded directories and starts nothing. Both run under any `TMPDIR`.

The check of the root runs right after the process-group line. It runs before the manifest is read and before the census's controls and the width rule.

## Standard input and operating-system errors

- Every child golden-census starts has the null device as its standard input. A child that reads meets end of file at once, whatever golden-census itself was started with.
- An error of the operating system that none of golden-census's own checks answers is one `REFUSED:` sentence on standard output, at exit 2. It quotes the error as Python states it. It is never a traceback. Examples are a disk that fills, a file-size limit, and a directory removed or made read-only under the run.
- What was printed above such a sentence is not a whole verdict. Fix what the error names and run the command again.

## The clone cache

A manifest input pinned with `git` and `sha` is cloned once into a persistent cache. A pinned input is cloned whole, at full size, with the whole history: golden-census runs a plain `git clone` with no depth limit and no size check, once per repository and commit, and keeps the clone until you delete it. Pin a large repository knowing that its full clone lands on this disk, in the cache directory named here. The cache is not under `TMPDIR`.

- It is `~/Library/Caches/golden-census/` on macOS. On Linux it is `$XDG_CACHE_HOME/golden-census/`, or `~/.cache/golden-census/` when that variable is unset.
- There is one folder for each repository and commit:

  ```text
  golden-census-trees/<repository>/<sha>/
    <repository>  the `git` value as git resolves it: a path that names a file or a directory, by its real absolute path; any other address as spelled; then each character that is not an ASCII letter, a digit, `.`, `_` or `-` made `-`
    <sha>         the pin, as the manifest spells it
  ```

- A `sha` that is not lowercase hexadecimal digits (the commit's id, or a prefix of it) is refused when the manifest loads. So is a `git` of `.` or `..`, one that opens with `-`, and an address that carries a password.
- golden-census takes a clone only where the full id of the commit it checked out begins with the `sha`. A branch or a tag that is only named like the pin does not count.
- A clone's folder found with files in it and no `.git` directory is a clone cut short. That input is SKIPPED, and the reason names the folder to delete.
- There is no index and no file beside the clones. Delete one commit, one repository or the whole cache whenever you like. The next run clones again.
- The cache directory is checked right before a clone is made. A command about to clone is refused there, after whatever ran before that clone, in three cases. The cache directory cannot be written. `HOME` is not an absolute path. `HOME` (on Linux, `XDG_CACHE_HOME`) is spelled with `..`. A command that clones nothing is never asked and makes no folder.
- A git step that fails inside a clone kept from an earlier run is that input SKIPPED. The reason names the directory and says to delete it and capture again.

## The settings of git

Every git golden-census runs in a tree gets the same settings on its command line. The trees are a pinned input's clone, the subject's checkout under a `git-checkout` precondition, and the clone `mutants` plants in. `core.excludesFile` is the null device, `core.autocrlf` is `false` and `core.eol` is `lf`. Every `git status` lists untracked files.

What a clone holds, and whether a tree is clean, are therefore the repository's answer and never your global git configuration's.

## Shared clones

- A clone is shared by every input, of any manifest, that pins one repository at one commit.
- The files git ignores in a shared clone persist across runs, inputs and manifests. They are not the pinned content.
- A kept clone that holds some is reported by a second `clone:` line: `clone: git ignores 1 path in it that is not the pinned content: 'a.log'; delete the clone's folder to start clean`. The line names the first three. It changes no verdict and no exit code.
- Under `census` and `--selfcheck --manifest`, a `vary` control's row prints the `clone:` lines each of its three runs printed, each opened with which run it was. `mutants` prints both lines for every capture its comparator makes, under a heading that names the copy, `the null mutant` or `mutant '<name>'`, and the check.
- Delete the clone's folder to start clean.
