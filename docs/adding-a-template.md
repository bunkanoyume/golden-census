# Templates

A template is a folder under `templates/` that `golden-census init` copies into your project. It holds a runner for one test tool, a wrapper if that tool needs one, and `template.toml`, which lists each file, where it goes in your project, and the holes you fill in. Every file arrives with its holes still marked `<<HOLE:NAME>>`; `init` prints the list and you fill them.

A runner is a small program in your project's language that gives a command line to code that has none of its own, such as a function or a module, so that golden-census can run it like any other command. A wrapper is a script that runs the test tool quietly and makes its output usable; the `swift-xcodebuild` template has one because `xcodebuild test` prints too much and sandboxes its test host. A hole is a value only your project knows, such as the name of the module under test. The template leaves a marker where the value goes, and you replace the marker.

This document is for someone adding a template. To use a template in a project, read the skill's `references/templates.md`.

This document covers:
1. Why there is more than one template
2. What `init` does
3. `template.toml`
4. A template that does not load
5. Holes after `init`
6. The `_neutral` template
7. Adding a template
8. The shipped templates

## Why there is more than one template

The three files every project has, `manifest.toml`, `census.toml` and `mutants.toml`, are the same whatever language the project is written in. They come from a template of their own, called `_neutral`, which `init` copies into every project first.

The runner is different for every test tool, because it is written in that tool's language and follows that tool's rules for finding a test and writing a file. So there is one template per test tool: `python-function`, `swift-package` and `swift-xcodebuild` today. A template for `pytest`, `cargo-test`, `go-test` or `ctest` would be one more folder of the same shape. Two Swift templates exist because Swift has two test tools.

A program that already runs from a command line needs no runner, so it needs no template beyond `_neutral`.

## What `init` does

- `golden-census init <dir>` copies `_neutral` into `<dir>`. It creates `<dir>` if it does not exist.
- `golden-census init <dir> --template NAME` copies `_neutral` first, then the named template.
- `golden-census init --list` prints the name and summary of every template and writes nothing.
- `init` never overwrites a file. If any file it would write already exists, or anything else is wrong, it refuses in one sentence and writes nothing at all. A refusal while copying the named template leaves the directory as it was before the command; the `_neutral` files are not left behind.
- When it is done, `init` prints every hole with its description. For a hole that is part of a file's path, it also names the file that must be moved once the hole is filled.

## `template.toml`

The file that lists what the template carries. This example has every kind of entry:

```toml
name    = "mytool"
summary = "a project tested through mytool: a runner script plus a quiet wrapper"

[[file]]
source = "runner.sh"
dest   = "<<HOLE:TEST_DIR>>/runner.sh"   # relative to the project directory

[[file]]
source = "wrapper.py"
dest   = "golden-census/wrapper.py"

[[hole]]
name        = "FUNCTION_CALL"
description = "the call to the pure function under test, from the loaded fixture values"

[[hole]]
name        = "TEST_DIR"
description = "the directory the runner belongs in"
```

`init` reads this file and checks every entry before it writes anything. A wrong entry is refused in a sentence that names the key.

### `name` and `summary`

Both are required.

- `name` must equal the folder's name. It is the word you give `--template`.
- `summary` is one line, not empty. `init --list` prints it beside the name.

### `[[file]]`: a file to copy

At least one `[[file]]` entry is required. A template that copies nothing is refused. Each entry has two required keys.

- `source` is the file's path inside the template folder.
- `dest` is where `init` writes it, relative to the project directory. No two entries may have the same `dest`.

Rules `init` enforces on `dest`:

- The file must not already exist in the project. A symbolic link counts as existing, even a broken one.
- The path must stay inside the project directory. `../out.txt` is refused, and so is a path that leaves the directory through a symbolic link.
- Neither `source` nor `dest` may contain a NUL character.

A `dest` may contain a hole, as `<<HOLE:TEST_DIR>>/runner.sh` does above. `init` cannot know the value, so it writes the file into a directory literally named `<<HOLE:TEST_DIR>>` and tells you to move it. For the example above, `init` prints:

```
    TEST_DIR — the directory the runner belongs in
      in the PATH of <<HOLE:TEST_DIR>>/runner.sh — that file was written to the literal <<HOLE:TEST_DIR>> directory, so MOVE it once you have filled the hole
```

`init` does this rather than stop and ask for the value, because a command that asks questions cannot be run by an agent from a single line.

### `[[hole]]`: a value you fill in

Every hole that appears in a copied file or in a `dest` must have a `[[hole]]` entry, and every entry must be used in at least one file or `dest`. This is called hole parity, and `--selfcheck` checks it. A template whose files have no holes has no `[[hole]]` entries. Each entry has two required keys and one optional one.

- `name` is the word inside the marker: `TEST_DIR` for `<<HOLE:TEST_DIR>>`. It starts with a letter and continues with letters, digits or underscores. No two entries may share a name.
- `description` is the sentence `init` prints beside the name. It is all the reader has to go on, so it must say what value belongs there.
- `probe`, optional, is a command whose output helps you choose the value. `init` runs it and prints its output under the hole. For a hole that takes an Xcode scheme, `probe = ["xcodebuild", "-list"]` would print the schemes to choose from. No shipped template uses `probe`. The rules:
  - The command runs with the null device as its standard input, so a command that waits for an answer gets end of file at once.
  - `init` prints at most 12 lines of the output and says how many it left out. A command that prints nothing shows `(no output, exited 0)`.
  - `init` prints its whole page only after every file is written, so a command that hangs leaves the page empty for as long as it runs. Choose a command that returns on its own.
  - A command that cannot start is noted under the hole. `init` still succeeds.
  - golden-census never reads the output. It is for you.

### `README.md`

A template that ships has a `README.md` in its folder. It explains what the runner does, why each line of the wrapper is there, and what the test tool does that the wrapper has to work around. No command reads it, and `_neutral` has none.

## A template that does not load

If any template in the install has a `template.toml` that does not load, or fails hole parity, `init` refuses for every template, not only the broken one. The refusal begins:

```
REFUSED: `init` writes a project's files FROM a template and this install's templates are not usable:
```

and then lists every template with its verdict. `--selfcheck` reports the same fault.

## Holes after `init`

Four commands refuse to read a manifest, census or mutants file that still contains `<<HOLE:`: `capture`, `compare`, `census` and `mutants`. `probe` reads no manifest, but refuses a command line that contains one. The refusal names the hole and the file. golden-census never guesses what a hole should be.

No command checks the runner or the wrapper for holes. A hole left in a runner is not refused; the run breaks, and a capture records whatever it produced, like any other run.

`init`'s last line states both rules: the three files are checked for holes, and the runner is not. The second half of the line appears only when a copied file's text contains a hole. For `python-function`:

```
  Fill every hole above. Commands that read manifest.toml, census.toml or mutants.toml refuse one that still spells <<HOLE:NAME>>; none checks runner.py, so a hole left there is not refused and a capture records the run it breaks.
```

For `init <dir>` with no template, and for a template whose files have no holes in their text:

```
  Fill every hole above. Commands that read manifest.toml, census.toml or mutants.toml refuse one that still spells <<HOLE:NAME>>.
```

The line names each file by its `dest`, hole included. For `swift-package` it names `<<HOLE:TEST_TARGET_DIR>>/GoldenCensusRunner.swift`.

## The `_neutral` template

`templates/_neutral/` is a template like any other, with two differences: `init` always copies it first, and it has no runner. `--template _neutral` is accepted and copies the same three files, and `init --list` names it. Every key in the three files has a comment explaining it. The project's own facts are holes.

- `manifest.toml` has a `[subject]` table with `<<HOLE:ROOT>>` and `<<HOLE:PROGRAM_RUN_COMMAND>>`, one input, and one `run` surface with `writes`. Each other kind of surface, and `[[movements]]`, is present as a commented-out example.
- `census.toml` has the environment rule; two live `path` folds, `root` and `work`; the `clone` and `fixed-width-dir` folds commented out, with a comment saying when to uncomment each; the fixed-width `TMPDIR` pin, with the explanation of the width 51; a `state` row for tool versions with `<<HOLE:VERSION_COMMANDS>>`; and the `git-checkout` precondition. `vary`, `drift`, `regex` and `json-fields` rows are present as commented-out examples.
- `mutants.toml` has the `comparator` check with `<<HOLE:GOLDEN>>`, and one `[[mutant]]` with holes for its name, `file`, `find` and `replace`.

## Adding a template

1. Create `templates/NAME/`. Name it after the test tool, not the language.
2. Write the runner, and a wrapper if the tool needs one. Everything specific to the project that will use it is a hole. A runner must not know anything about one particular project.
3. Write `template.toml` as described above. Declare every hole.
4. Write `README.md`. Say what the runner records, what the wrapper does and why each step is there, and which version of the test tool the template was written against.
5. Link the template's `README.md` from the document list in `docs/using-golden-census.md`. `--selftest` goes red on a `templates/*/README.md` that no document links.
6. Run `--selfcheck` and `--selftest` and read the result.

What the two checks cover:

- `--selfcheck` loads every `template.toml` and checks hole parity. It runs nothing.
- `--selftest` runs `init <scratch> --template NAME` for every template through the real command line, and checks that parity holds, that every `dest` was written (a hole in a `dest` as the literal `<<HOLE:…>>` directory), that the printed hole list matches `template.toml`, and that the command exited 0 with the expected output.
- Neither check fills a hole or runs the runner. Prove the runner works by hand, the way its `README.md` walks through it.

## The shipped templates

`docs/using-golden-census.md`, "The documents", lists the shipped templates and links each one's `README.md`.
