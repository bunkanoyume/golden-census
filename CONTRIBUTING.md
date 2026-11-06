# Contributing to golden-census

These are the instructions for an LLM coding agent that changes golden-census's code, its documents or its templates; a person contributing reads them the same way. To USE the tool, read the [README](README.md) and the skill, [`golden-census-skill/SKILL.md`](golden-census-skill/SKILL.md).

## Why the tool is shaped as it is

golden-census is for LLM agents. An agent that refactors a program has no way to show that it altered nothing observable, so it asserts it, and the assertion is the least reliable line in the report. Reviews and test suites do not close the gap: a suite proves the cases somebody thought of, and a refactor's whole risk is the cases nobody did. This tool records what a program actually produces, normalizes away everything that is about the machine, and compares byte for byte afterwards. `IDENTICAL` is a finding an agent can hand back, and a moved row is a finding it cannot talk its way past.

### Three goals

1. Move verification OUT of the LLM into deterministic code. Whether two runs agree is a byte comparison, not a judgment, and it should never cost a model a paragraph of reasoning or a reader a paragraph of trust.
2. Deliver pre-derived, byte-level answers, so a session stops re-deriving what an earlier session already recorded and stops re-verifying prior sessions' claims at handoff. The golden IS the handoff.
3. Prove a change altered nothing observable BEFORE the hand-back — not at review, not at the gate, not after the merge. Capture before you touch a surface; compare before you hand it back.

*This is not a tool that says whether behavior is correct — it is a tool that says whether behavior MOVED, and names the byte.* A golden records a bug as faithfully as a feature. The judgment stays with the reader.

### Principles

No change to the app may violate any of these principles.

- **Deterministic.** Two captures of an unchanged subject are byte-identical, or golden-census refuses and names the row and the line that moved.
- **Refuse, don't guess.** A precondition that does not hold, a manifest key that does not resolve, an `--out` directory golden-census did not write: one sentence and exit 2, before anything is run.
- **Crashing is never the appropriate choice.** Every refusal is a sentence on stdout, stderr when stdout is unusable, never a traceback.
- **Never relies on other programs.** An absent optional tool is a disclosed SKIP, never a pass — perfect output regardless is the only sanctioned shape.
- **Output is measured as a diagnostic, never as a target.** Self-tests measure what a command prints so that an unexpected change shows up after a change was made: a figure that moved for no stated reason is evidence something went wrong, and that is their whole purpose. No figure is a contract, a budget, or a design goal: nothing is written, trimmed or padded to reach a number, and a change that moves a figure on purpose just says so.
- **Evidence is `file:line`.** Always. A diff names the row and the line; a contraband hit names the file, the line and the token.
- **A zero result is not a clean result.** Every guard ships with a positive control in `--selfcheck` proving it can go red, and the control is quoted whenever the guard's clean result is quoted.
- **A fact that qualifies a verdict is printed beside the verdict.** Agents act on the verdict line, and `IDENTICAL` is quoted into reports by readers who never open the log. So when golden-census knows something that makes a verdict mean less than it says, such as a row that ran on neither side or a fold that rewrote the subject's own path, the command prints it beside the verdict, naming the rows. A sentence in the skill does not mitigate a false all-clear; the skill is for what the tool cannot know, such as which surface to choose. The printed line is a fact the run already holds: printed only when it applies, never a guess, and a refusal where the fact is a fault.
- **Standalone.** Nothing about any other app may be embedded in this project. The one exemption is `work/dev/`, the tool's own frozen command line, inside the directory that does not ship.
- **Simple and predictable.** golden-census is an app, not an LLM. Its behavior should not surprise users, and its documents stay short. A rare edge case is handled by refusing, naming everything that was found, and saying what to do — never by code that tries to anticipate the case. A fix that needs a list of special names, a classifier, a cap, or paragraphs of rules in the skill file is the wrong fix. Two sentences of instruction beat hundreds of lines of rarely executed code that need paragraphs of instruction. This is about HANDLING a case; a fact the run already holds that qualifies its own verdict is printed, not documented — see "A fact that qualifies a verdict is printed beside the verdict."

### How changes are found

The primary user is an LLM coding agent, so the only way to learn how a change lands is to make it and watch agents meet it — not to reason about it. Build it, point agents at real consumers' manifests and at this tool's own output, and let what they hit become the change. Use models of several sizes. If the agents do not use the app correctly, update the skill. If the app does not behave correctly, update the app. If an agent reaches for something that is not there, consider adding the feature.

Beware the leading test. A prompt that tells agents which distinction to look for measures whether they can reason about it when told, not whether they would trip over it unprompted. Give them a real task and an open question.

## The checkout

golden-census needs Python 3.11 or newer and the standard library. Run it from a checkout with `bin/golden-census`, or with `python3 -m golden_census` from the checkout's root. `golden-census` is the command and `golden_census` is the import name; the README says why.

| Path | What it holds |
|---|---|
| `golden_census/` | The package. `core.PROG` owns the command's name and `core.IMPORT_NAME` the import name; read them from there. |
| `golden_census/fixture/` | The bundled stub program, its manifest, its census and its committed golden. `--selftest` runs on it. |
| `templates/` | What `golden-census init` scaffolds. |
| `examples/` | A worked example to copy. |
| `docs/` | The documents for a person: `reference.md`, `using-golden-census.md`, the three format documents, the subject requirements, the template guide, the known issues and the change log. |
| `golden-census-skill/` | The documents for an LLM agent. |
| `bin/golden-census` | The launcher. |
| `docs/Known_Issues.md` | The open defects of the released code. |
| `pyproject.toml`, `mypy.ini` | The packaging and the type checker's settings. |

## What every change carries

1. **An edit to the package** runs `--selftest` green, and `ruff check golden_census` and bare `mypy` clean, before the commit. The checks are below.
2. **A new guard** ships with its positive control in the same change. Write the planted case first and watch the arm go red. A guard that was never seen to fail has not shown that it can.
3. **A new or changed surface** of a consumer adds its manifest row and its golden in the same commit. The bundled fixture is a consumer: its manifest is `golden_census/fixture/manifest.toml` and its golden is `golden_census/fixture/subject/golden/`. The COMPARE group of `--selftest` compares that golden with a fresh capture of the stub, and a golden left behind fails it with a `[DIFF]` row naming the file.
4. **A behavior or command-line change** updates the set that states the fact, in the same commit. The rules are under "The documents".
5. **A new template** follows [`docs/adding-a-template.md`](docs/adding-a-template.md). Adding one changes no code. The TEMPLATES group of `--selftest` scaffolds every shipped template.
6. **A fixed defect** leaves `docs/Known_Issues.md` in the same commit.

## The checks

Run all three from the checkout's root.

1. **`--selfcheck`** runs golden-census's own arms: each a guard beside the planted case that proves the guard can fire. The arms live in the `checks_*.py` modules. Run it alone while you work on a guard.
2. **`--selftest`** runs the arms, then the whole program on the bundled fixture, the two document sets against the parser, the first line of every command and every shipped template. It takes minutes. `docs/using-golden-census.md`, "Checking golden-census itself", says what it prints. Only these two commands run the arms: a `capture` or a `compare` of any manifest runs that census's controls and none of them, so running a consumer's command does not exercise an edit to the package.
3. **`ruff check golden_census`** prints `All checks passed!`. Its rules are in `pyproject.toml`. **`mypy`** with no argument prints `Success: no issues found`. Give it no argument: `mypy.ini` lists the files with a glob, an argument replaces that list, and mypy then silently skips a module whose name collides with a sibling directory and still reports success. The stance is mypy's default checking plus `check_untyped_defs`, against Python 3.11. Output produced under any other configuration is not a bug report.

The checks that read the documents run in a checkout and in an install alike, because the wheel carries the documents under the package. The packaging row runs only in a checkout, because an install does not carry `pyproject.toml`. Verify a build in a scratch virtual environment, never on your own machine.

## The documents

`SKILL.md` and the reference files in `golden-census-skill/references/` contain everything needed to run golden-census, broken up so that only what is needed for the current task is read. The documents under `docs/` add explanations that are not needed by an agent running golden-census: `reference.md` is the glossary, the command table with exit codes and the flag table; `using-golden-census.md` is for the person who owns a project and lists every other document; the three format documents, the subject requirements and the template guide explain one file or one procedure each. The README says what golden-census is, what it needs, how to install it and how to confirm the install.

What this means for a change:

1. **A behavior or command-line change** updates the skill and `docs/reference.md` in the same commit, and any `docs/` document that states the changed fact. The parity check, below, catches a flag or subcommand missing from either the skill or the reference; it does not read the other `docs/` files, so those are the author's to search. `grep` the old wording across `docs/` and the skill before the commit.
2. **A fact has one home.** The skill states a rule where the agent meets it. A `docs/` document explains the same rule for a person and must not contradict the skill. Neither restates the other at length.
3. **A path the tool prints** is a path into the skill, so that an agent reading a refusal is sent to the instructions it already has. The one exception is `docs/adding-a-template.md`, which `init` names when a template does not load, because that refusal is for the template's author. Moving or renaming a file the tool names changes what the tool prints, and the FIRST LINE and DOCS PARITY groups of `--selftest` go red until the code follows.
4. **Shipped files reproduced in a document** (`examples/python-function/manifest.toml`, `census.toml` and `mutants.toml` in the format documents) are copied verbatim from the file. A change to the file is a change to the document.

### Writing the text

1. A document opens by defining the subject and listing the sections. `docs/adding-a-template.md` is the model.
2. Every term is defined when it is first used, or is a glossary entry in `docs/reference.md`.
3. In documents and skills, minimize using pronouns, especially "it."
4. One sentence carries one thought. Split a sentence that carries two.
5. Keep the subject and its verb close together.
6. A table cell holds one rule. A cell with several rules becomes a list.
7. A step is an imperative. Number the steps when they have an order.
8. Spell every command example as the parser takes it, required flags included. `--help` of each subcommand is the authority.
9. Quote every claim about what the tool prints from a run you made.
10. Write American English.

### What the parity check reads

The DOCS PARITY group of `--selftest` reads the argument parser, never a hand-kept list, and holds the two sets to six rules.

1. **The skill** names every subcommand and long option, read as one text: `SKILL.md` and the reference files together. Every (subcommand, flag) pair has its own row in the flag table of `references/commands.md`: a table whose first header cell is `Flag`, whose row names the flag in its first cell and, in its second, the subcommand in backticks or `whole program` for a flag of the bare command. No row names a flag the parser lacks. A row deleted from the table fails, even when the prose still names the flag. Every `references/<name>.md` that `SKILL.md` names exists.
2. **The human set** meets the same inventory and the same table rule, read as `README.md` and `docs/reference.md` together; `reference.md` carries the flag table.
3. **The version.** Every place in either set and in the example's README that spells the command's name and a version spells `golden_census.__version__`. Each set spells it at least once: `SKILL.md` under "Read this first", the README under "Confirm the install".
4. **The exit-code sentence.** One member of each set carries the line of the `cli.py` module docstring that begins `Exit codes:`, word for word: `SKILL.md` and `docs/reference.md`. `cli.py` owns that sentence because it sits beside `cli.main`, which decides the exit codes. Change it there first.
5. **The procedure.** `references/first-run.md` alone has the heading `The first run, in order`, with eight numbered steps, each opening with a bold phrase.
6. **The links.** Every `templates/*/README.md` and `examples/*/README.md` is a link target in the README or in a document under `docs/`.

A red row's `actual:` line says what is missing.

## The release set

The release set is the sdist's `include` list in `pyproject.toml`, under `[tool.hatch.build.targets.sdist]`. Nothing else is released. A file is released when the public repository carries it and shipped when an install does.

Every file in it is written for a stranger. It names no other project, no path on a machine, no working session and no person. `LICENSE.txt` is the one exception.
