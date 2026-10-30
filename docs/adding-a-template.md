# Templates: how `golden-census init` scaffolds a project, and how to add one

A template is a directory under `templates/`. `golden-census init <dir> --template TEMPLATE` copies it into a project, holes and all. A template exists so that an adopter's first hour is filling marked holes. The alternative is reading the contract from scratch. Adding a template for a new language or test tool is adding a directory. golden-census's code does not change.

`golden-census init <dir>` with no template writes the three neutral files: `manifest.toml`, `census.toml` and `mutants.toml`. Every key in them is commented. The project's facts are holes. A template adds a runner and, when the tool needs one, a wrapper.

`init` creates `<dir>` if it is absent. It writes in two passes: the neutral three first, then the template's own files. It overwrites nothing. It is all or nothing across both passes. A refusal in either pass leaves the directory exactly as `init` found it. `golden-census init --list` names the shipped templates and writes nothing.

## Holes

A hole is the token `<<HOLE:NAME>>` in any template file, the neutral three included. `init` copies the files with the holes in place and prints the list of holes. The agent or the human fills them. golden-census never guesses a hole.

Five commands refuse a hole. `capture`, `compare`, `census` and `mutants` refuse a manifest, a census or a mutants file that still contains `<<HOLE:`; `probe`, which reads no manifest, refuses a candidate command line that does. The refusal names the hole and the file. An unfilled hole is a project that has not finished plugging in.

No command looks for a hole in a template's own files, such as the runner or the wrapper. A hole left there is not refused. The run it breaks is recorded like any other.

`init`'s last line says both things. Its second half names only the files whose text carries a hole. For the `python-function` template the line reads:

```
  Fill every hole above. Commands that read manifest.toml, census.toml or mutants.toml refuse one that still spells <<HOLE:NAME>>; none checks runner.py, so a hole left there is not refused and a capture records the run it breaks.
```

For `init <dir>` with no template, and for a template whose files carry no hole in their text, the second half is absent:

```
  Fill every hole above. Commands that read manifest.toml, census.toml or mutants.toml refuse one that still spells <<HOLE:NAME>>.
```

The line names a file by its `dest`. A `dest` that holds a hole appears with the hole in it. For `swift-package` the line names `<<HOLE:TEST_TARGET_DIR>>/GoldenCensusRunner.swift`.

## `template.toml`

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

`init` reads the file and checks every row before it writes anything. Every refusal names the key at fault.

- `name` equals the directory name. A mismatch is refused.
- `summary` is one non-empty line. `golden-census init --list` prints it beside the name.
- A `[[file]]` row has a `source` and a `dest`. Both are required.
  - `source` is relative to the template directory. It must be a file there.
  - `dest` is relative to the project directory. Two rows may not share a `dest`.
  - A `source` or a `dest` that holds a NUL character is refused when the template is read. The refusal names the row.
- A `dest` may contain a hole. The hole stays in the path. `init` writes the file into the literal `<<HOLE:NAME>>` directory. It prints the hole with that file beside it, and says to move the file once the hole is filled. For the example above, `init` prints:

  ```
      TEST_DIR — the directory the runner belongs in
        in the PATH of <<HOLE:TEST_DIR>>/runner.sh — that file was written to the literal <<HOLE:TEST_DIR>> directory, so MOVE it once you have filled the hole
  ```

  Holes are filled in place, in a path as in a text. The alternative is an `init` that asks questions. A scaffold that cannot run from one line is no use to an agent.
- `init` refuses a `dest` that already exists in the project directory. A link counts, dangling or not. `init` overwrites nothing.
- `init` refuses a `dest` that lands outside the project directory. It refuses one by its spelling, such as `../out.txt`. It refuses one through a link on its way. `init` writes nothing outside the directory it was given.
- A `[[hole]]` row has a `name` and a `description`. Both are required.
  - `name` is a letter followed by letters, digits or underscores. Two rows may not share a `name`.
  - `description` is what the reader has to go on when `init` prints the hole. It may not be empty.
- `probe` is an optional key of a `[[hole]]` row. It is a non-empty list: the argv of a command whose stdout `init` prints under the hole's name. The reader then sees the candidates.
  - No shipped template uses `probe`. The `swift-xcodebuild` wrapper takes the scheme as a manifest argument. A `SCHEME` hole would spell `probe = ["xcodebuild", "-list"]`, which prints the schemes and targets. This is an illustration.
  - `init` starts the probe with the null device as its standard input. A probe that reads its standard input for an answer meets end of file at once. A probe that prints nothing shows `(no output, exited 0)`.
  - `init` prints nothing until the probe returns. Its page, the probe's lines included, is held until every file is written, so a probe that hangs leaves an empty page under the process-group line for as long as it runs. Choose a probe that returns on its own.
  - `init` prints at most 12 lines of the output. It then says how many lines it left out.
  - A probe that cannot start is a note under the hole, not a refusal. `init` still exits 0.
  - golden-census never reads the output. Refuse-don't-guess applies to scaffolding too.
- `README.md` in the template directory is that template's pattern document. It says what the runner does. It says why each line of the wrapper exists. It names the traps the tool sets and how the wrapper handles them.

### Hole parity

Every hole is declared and every declared hole is used. Parity holds when three things hold:

1. Every `<<HOLE:` in a template file has a `[[hole]]` row.
2. Every `<<HOLE:` in a `dest` has a `[[hole]]` row.
3. Every `[[hole]]` row appears in at least one file or `dest`.

A template that fails parity is not shipped. A template that fails parity, or does not load, makes `init` refuse for every template, not only for itself. The refusal begins:

```
REFUSED: `init` writes a project's files FROM a template and this install's templates are not usable:
```

It goes on to list every template with its verdict and names the fault. `--selfcheck` goes red on the same fault.

## The neutral three

`golden-census init` always writes these files first. They come from `templates/_neutral/`. That directory is a template like any other, with two differences: it is always applied first, and its `template.toml` has no runner. `--template _neutral` is accepted and writes the same three files, and `init --list` names it.

- `manifest.toml` has a `[subject]` table with `<<HOLE:ROOT>>` and `<<HOLE:COMMAND>>`. It has one input and one `run` surface with `writes`. It carries a commented-out example of each other surface kind and of `[[movements]]`.
- `census.toml` has the environment rule and the four `path` folds. It has the fixed-width `TMPDIR` pin, with the explanation of the width 51. It has a `state` row for tool versions, with `<<HOLE:VERSION_COMMANDS>>`. It has the `git-checkout` precondition. It carries commented-out examples of `vary`, `drift`, `regex` and `json-fields` rows.
- `mutants.toml` has the `comparator` check, with `<<HOLE:GOLDEN>>`. It has one `[[mutant]]`, with holes for its name, `file`, `find` and `replace`.

## What a template must carry before it ships

To add a template:

1. Create `templates/TEMPLATE/`. Name it after the test tool, not the language.
2. Write the runner, and a wrapper when the tool needs one. Make every app-specific part a hole.
3. Write `template.toml`, as the section above describes. Declare every hole.
4. Write `README.md`. It says what the runner freezes. It says what the wrapper does and why each of its steps exists. It names the tool version the template was written against.
5. Link the template's `README.md` from the project README. `--selftest` goes red on a `templates/*/README.md` the README does not link.
6. Run `--selfcheck` and `--selftest`, and read the result.

The two self-tests check a template as follows.

- `--selfcheck` checks that every `template.toml` loads and holds to hole parity. It reads files and runs nothing.
- `--selftest` has a TEMPLATES group. For every template in `templates/` it runs `init <scratch> --template TEMPLATE` through the real command line. It then checks four things:
  - parity holds
  - every `dest` is written, a hole `dest` as the literal `<<HOLE:…>>` directory
  - the printed hole list matches `template.toml`
  - the real command exits 0 with the same block as the scaffolder prints
- The TEMPLATES group fills no hole and captures and compares nothing. Prove the runner end to end by hand, the way the template's own `README.md` walks through it.

## The shipped templates

The manual lists the shipped templates and links each one's `README.md`.

A template for another tool, such as `cargo-test`, `ctest`, `go-test` or `pytest`, is the same directory shape. Name it after the test tool, not the language. Two Swift templates exist because two Swift test tools do. A runner knows nothing about the app it lands in. The app-specific parts are the holes.
