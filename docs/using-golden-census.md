# Using golden-census: what the owner of a project needs to know

This document is for the person who owns a project that uses golden-census. It covers what an install contains, how to check that golden-census itself works, how to start using golden-census with a project, and how to make a project's agents keep the recording up to date. It ends with a list of every other document and what each is for.

The instructions for running the tool are in the skill, [`golden-census-skill/SKILL.md`](../golden-census-skill/SKILL.md), and its reference files. The skill is written for the agent that runs the commands, and a person can read it the same way. The command table, the flag table and the glossary are in [`reference.md`](reference.md).

This document covers:
1. What an install contains
2. Checking golden-census itself
3. How to start using golden-census with a project
4. Keeping the recording up to date
5. The documents

## What an install contains

An install contains the Python package, the small test program the self-test runs against, and a copy of `docs/`, `examples/`, `golden-census-skill/`, `templates/`, the README and the license. `golden-census --help` ends with a `directories:` section that prints where this install keeps each of those; a directory the install lacks is marked `(not present)`. In a checkout they sit beside the package.

An install does not contain `pyproject.toml` or `CONTRIBUTING.md`. Those are for someone changing golden-census, not using it.

The templates are needed only by `init`. Every other command runs without them. `--selfcheck` reports whether they are present.

## Checking golden-census itself

golden-census has two commands that test golden-census itself.

- `golden-census --selftest` runs the whole program against the test program bundled in the install. Run it once after installing or upgrading. It takes a few minutes (158 seconds on the machine it was measured on, 2026-10-13) and prints hundreds of lines, so send its output to a file.
- `golden-census --selfcheck` runs only golden-census's internal checks and is the quick one. Run it when a golden-census command itself seems to misbehave.

These two commands are the only ones that test golden-census. A `capture` or `compare` of your own project runs your project's census controls, not golden-census's checks.

Each internal check is run against a planted fault it is supposed to catch, as well as against the clean case. A check that does not catch its planted fault is reported red. This is how golden-census shows that a clean result means something.

`--selftest` prints seven groups, each ending in a tally such as `214/214 passed`: GOLDEN-CENSUS SELF-CHECK, CAPTURE, COMPARE, MUTANTS, DOCS PARITY, FIRST LINE and TEMPLATES.

A red row means golden-census or the machine is broken. It says nothing about your project. Report the row's name and its `actual:` line, and say that any other results were taken while it was red. A row that crashes or refuses instead of reporting a pass or a fail is marked `[FAIL]  !` and is a defect in golden-census.

In an installed copy, one row is always skipped, because an install does not contain `pyproject.toml`:

```
  [SKIP]  sss  pyproject.toml, read with tomllib: every sdist include pattern is ANCHORED …
           pyproject.toml is not in this layout: … holds none. The packaging tables are the repository's; nothing was read and nothing is claimed.
```

A skipped row is never counted as a pass. This particular skip is expected and is not a defect.

## How to start using golden-census with a project

An agent sets up a project by following the eight steps in the skill's `references/first-run.md`, from `init` to the first hand-back. Every program needs two kinds of work:

- Learning how to run the program: its arguments, the inputs it reads and the outputs it produces.
- Choosing the inputs to record the program over, or making them, such as small fixture files or a sample project, and choosing which outputs to record from each.

Some programs also need new code before golden-census can run them:

- A program that already runs from a command line needs none. golden-census runs it with the inputs the agent chose.
- Code with no command line of its own, such as a function or a module, needs a runner: a short script that calls the code and writes the result to a file. golden-census ships runner templates for Python and Swift.
- For a GUI app the runner must call the part of the app that computes a result without the user interface. The app's test tool may also need a wrapper script to keep its output quiet, as the `swift-xcodebuild` template provides.

After that, each hand-back costs one `compare` command, which prints one line.

A golden can be defined to capture as little or as much output as desired. For projects that have used golden-census since inception, there will be little risk of an output being missed, for existing project, some effort will be needed to create goldens that capture all of the program's output. 

For an existing project, for a first run, it is recommended to use stronger models to create the first golden, which will determine which data is recorded. The model must learn how to use your program and how to use golden-census. Instruct agents to investigate the operation of the subject program by reading any skill files or other documentation and reading the program's --help, so that the agents can exercise the program through all of its commands and arguments. After that, an agent on any model can run the comparison, and the comparison command can be saved in a plan or prompt file. 

You get the best results by recording the program over several inputs. Each input exercises a different part of the program, and a golden records only the behavior its inputs reach. Start with at least three: an ordinary case, an empty case, and a case the program refuses. Not everything needs to be captured into one golden. For example, if a certain process is time consuming, that process can be excluded from golden A and captured in golden B. This allows golden A to be run frequently, and while maintaining the complete capture of golden B. 

The chart below has ballpark estimates of how much context these commands use.

| Command | Output |
|---|---|
| `--version` | two words |
| `compare --against` | a paragraph |
| `capture`, `compare`, `census`, `mutants`, `probe`, `init` | depends on the subject program |
| `--selfcheck`, `--selftest` | dozens of pages |

A comparison is cheap and a capture is not. `compare --against` reads two recorded directories and runs nothing. A capture runs your program once per row, and `mutants` runs one capture per mutant.

## Keeping the recording up to date

golden-census only helps if the recording keeps up with the program. When someone adds or changes an output, they must add or change its row in the manifest and record a new golden, in the same commit. Nothing in golden-census can know that a new output exists until someone writes its row.

Three lines in a project's instructions make this happen.

1. In the project's instructions for agents, beside its rule about keeping documents in step with the code:

   ```
   A new or changed surface adds its manifest row and golden in the same
   commit; the parity self-test enforces it.
   ```

2. In the instructions a coding agent follows when it writes and checks code:

   ```
   Capture before you touch a surface, compare before you hand back, update
   the manifest when you add one.
   ```

3. In the report every coding agent writes, one line it must fill in:

   ```
   Manifest rows added or changed.
   ```

Whoever approves the merge checks that the rows and the goldens changed together. That check is mechanical.

## The documents

Open a document when a step or a printed line sends you to it.

- **The skill**, [`golden-census-skill/SKILL.md`](../golden-census-skill/SKILL.md): the instructions for running golden-census. Read it first and whole. Its `references/` files are opened one at a time as a step needs them: `first-run.md` (the eight steps from `init` to the first hand-back), `rebaseline.md` (recording a new golden after a change), `commands.md` (the rules of every flag), `verdicts.md` (every line the tool prints and what to do about it), `manifest.md`, `census.md` and `mutants.md` (the rows to copy into each file), `machine.md` (the temp directory, the clone cache and git) and `templates.md` (which template to use, and what `init` prints).
- **The reference**, [`reference.md`](reference.md): the glossary, the command table with exit codes, the flag table, and the rules every flag follows.
- **The three file formats**, one document per file golden-census reads:
  - [`manifest-format.md`](manifest-format.md): `manifest.toml`, which says what to run and what to record.
  - [`census-format.md`](census-format.md): `census.toml`, which says what surrounds every run and must be held still.
  - [`mutants-format.md`](mutants-format.md): `mutants.toml`, which lists deliberate changes to the program that the checks must catch.
- **The subject requirements**, [`subject-requirements.md`](subject-requirements.md): what a program must do to be recorded, and how to read a `probe` report. Every `probe` report ends by naming this document.
- **The templates**, for `golden-census init`. Each template's README explains its runner, every hole, the manifest lines it needs, and what the test tool does that the template works around.
  - [`templates/python-function/README.md`](../templates/python-function/README.md): a Python function.
  - [`templates/swift-package/README.md`](../templates/swift-package/README.md): a SwiftPM package, under `swift test`.
  - [`templates/swift-xcodebuild/README.md`](../templates/swift-xcodebuild/README.md): an Xcode app or framework, under `xcodebuild test` through a wrapper.
  - A program that runs from a command line needs no template. Code with no command line in a language with no template needs a runner you write yourself, following the six steps in the skill's `references/templates.md`. [`adding-a-template.md`](adding-a-template.md) explains what a template is and how to add one.
- **The worked example**, [`examples/python-function/README.md`](../examples/python-function/README.md): the Python template filled in and committed, with ten commands in order and the line each prints. Read it and copy it.
- **Known issues**, [`Known_Issues.md`](Known_Issues.md): open defects and cautions.
- **The change log**, [`change_log.md`](change_log.md).
- **For someone changing golden-census**, [`CONTRIBUTING.md`](../CONTRIBUTING.md): the instructions for an agent or a person working on the code, the documents or the templates.
