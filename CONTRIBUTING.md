# Contributing to golden-census

These are the instructions for an LLM coding agent that changes golden-census's code, its documents or its templates; a person contributing reads them the same way. To USE the tool, read the [README](README.md) and the [manual](docs/manual.md).

## Why the tool is shaped as it is

golden-census is for LLM agents. An agent that refactors a program has no way to show that it altered nothing observable, so it asserts it, and the assertion is the least reliable line in the report. Reviews and test suites do not close the gap: a suite proves the cases somebody thought of, and a refactor's whole risk is the cases nobody did. This tool records what a program actually produces, normalizes away everything that is about the machine, and compares byte for byte afterwards. `IDENTICAL` is a finding an agent can hand back, and a moved row is a finding it cannot talk its way past.

### Four goals

1. Move verification OUT of the LLM into deterministic code. Whether two runs agree is a byte comparison, not a judgment, and it should never cost a model a paragraph of reasoning or a reader a paragraph of trust.
2. Deliver pre-derived, byte-level answers, so a session stops re-deriving what an earlier session already recorded and stops re-verifying prior sessions' claims at handoff. The golden IS the handoff.
3. Prove a change altered nothing observable BEFORE the hand-back — not at review, not at the gate, not after the merge. Capture before you touch a surface; compare before you hand it back.
4. The Apple ecosystem raises the stakes: training data is stale about Swift and Apple churn, so agents rewrite more than they were asked to and hallucinate the rest. A frozen record of what the program did yesterday is the antidote, and `templates/swift-package/README.md` and `templates/swift-xcodebuild/README.md` are how a Swift app gets one.

*This is not a tool that says whether behavior is correct — it is a tool that says whether behavior MOVED, and names the byte.* A golden records a bug as faithfully as a feature. The judgment stays with the reader.

### Principles

Every change honors these. A change that cannot is the wrong change.

- **Deterministic.** Two captures of an unchanged subject are byte-identical, or golden-census refuses and names the row and the line that moved.
- **Refuse, don't guess.** A precondition that does not hold, a manifest key that does not resolve, an `--out` directory golden-census did not write: one sentence and exit 2, before anything is run.
- **Crashing is never the appropriate choice.** Every refusal is a sentence on stdout, stderr when stdout is unusable, never a traceback.
- **Never relies on other programs.** An absent optional tool is a disclosed SKIP, never a pass — perfect output regardless is the only sanctioned shape.
- **Output is measured as a diagnostic, never as a target.** Self-tests measure what a command prints so that an unexpected change shows up after a change was made: a figure that moved for no stated reason is evidence something went wrong, and that is their whole purpose. No figure is a contract, a budget, or a design goal: nothing is written, trimmed or padded to reach a number, and a change that moves a figure on purpose just says so. The README's cost guide is rounded, for a human's sense of scale, and checked by nothing.
- **Evidence is `file:line`.** Always. A diff names the row and the line; a contraband hit names the file, the line and the token.
- **A zero result is not a clean result.** Every guard ships with a positive control in `--selfcheck` proving it can go red, and the control is quoted whenever the guard's clean result is quoted.
- **The tool informs where the reader is looking.** Agents read the manual once, before first use. Then context fills and is compacted. But agents read the tool's output on every run, and act on the verdict line — IDENTICAL is what gets quoted into a gate report or a commit message, by readers who never open the log or the golden folder. So when golden-census KNOWS something that makes a verdict mean less than it says — a row that ran on neither side, a fold that rewrote the subject's own path, a check that could not be made — it says so in the output of the command whose verdict it qualifies, beside that verdict, naming the rows. A sentence in the skill file is not a mitigation for a false all-clear. The skill file sentence is for what the tool cannot know: which surface to choose, when to re-baseline, what a file outside the tree means to the subject. The line reports a fact the run already has in hand: it is printed only when it applies, it is never a guess about a case that might arise, and where the fact is a fault it is a refusal.
- **Two documents, two audiences, one truth.** `README.md` serves humans, `golden-census-skill/SKILL.md` serves agents; any behavior or CLI change updates both in the same commit. The parity check in `--selftest` reads the argument parser — never a hand-kept list — and fails when either document is missing a subcommand or a flag, names one the parser does not expose, or states the adopter's procedure differently from the other.
- **Standalone.** Nothing about any other app may be embedded in this project. The one exemption is `work/dev/`, the tool's own frozen command line, inside the directory that does not ship.
- **Simple and predictable.** golden-census is an app, not an LLM. Its behavior should not surprise users, and its manual stays short. A rare edge case is handled by refusing, naming everything that was found, and saying what to do — never by code that tries to anticipate the case. A fix that needs a list of special names, a classifier, a cap, or paragraphs of rules in the skill file is the wrong fix. Two sentences of instruction beat hundreds of lines of rarely executed code that need paragraphs of instruction. This is about HANDLING a case; a fact the run already holds that qualifies its own verdict is printed, not documented — see "The tool informs where the reader is looking."

### How changes are found

The primary user is an LLM coding agent, so the only way to learn how a change lands is to make it and watch agents meet it — not to reason about it. Build it, point agents at real consumers' manifests and at this tool's own output, and let what they hit become the change. Use models of several sizes. If the agents do not use the app correctly, update the skill. If the app does not behave correctly, update the app. If an agent reaches for something that is not there, consider adding the feature.

An experiment that fails succeeds. It converts an opinion into a settled question, and experiments routinely surface a second defect on the way. Trying two approaches to one problem is not wasted work. Record what the experiment settled.

Beware the leading test. A prompt that tells agents which distinction to look for measures whether they can reason about it when told, not whether they would trip over it unprompted. Give them a real task and an open question.

## The checkout

golden-census needs Python 3.11 or newer and the standard library. Run it from a checkout with `bin/golden-census`, or with `python3 -m golden_census` from the checkout's root. `golden-census` is the command and `golden_census` is the import name; the README says why.

| Path | What it holds |
|---|---|
| `golden_census/` | The package. `core.PROG` owns the command's name and `core.IMPORT_NAME` the import name; read them from there. |
| `golden_census/fixture/` | The bundled stub program, its manifest, its census and its committed golden. `--selftest` runs on it. |
| `templates/` | What `golden-census init` scaffolds. |
| `examples/` | A worked example to copy. |
| `docs/` | The manual, the format documents, the contract and the template guide. |
| `golden-census-skill/` | The documents for an LLM agent. |
| `bin/golden-census` | The launcher. |
| `docs/Known_Issues.md` | The open defects of the released code. |
| `pyproject.toml`, `mypy.ini` | The packaging and the type checker's settings. |

## What every change carries

1. **An edit to the package** runs `--selftest` green, and `ruff check golden_census` and bare `mypy` clean, before the commit. The checks are below.
2. **A new guard** ships with its positive control in the same change. Write the planted case first and watch the arm go red. A guard that was never seen to fail has not shown that it can.
3. **A new or changed surface** of a consumer adds its manifest row and its golden in the same commit. The bundled fixture is a consumer: its manifest is `golden_census/fixture/manifest.toml` and its golden is `golden_census/fixture/subject/golden/`. The COMPARE group of `--selftest` compares that golden with a fresh capture of the stub, and a golden left behind fails it with a `[DIFF]` row naming the file.
4. **A behavior or command-line change** updates the human set and the agent set in the same commit. The rules are under "The documents".
5. **A new template** follows [`docs/adding-a-template.md`](docs/adding-a-template.md). Adding one changes no code. The TEMPLATES group of `--selftest` scaffolds every shipped template.
6. **A fixed defect** leaves `docs/Known_Issues.md` in the same commit.

## The checks

Run all three from the checkout's root.

1. **`--selfcheck`** runs golden-census's own arms: each a guard beside the planted case that proves the guard can fire. The arms live in the `checks_*.py` modules. Run it alone while you work on a guard.
2. **`--selftest`** runs the arms, then the whole program on the bundled fixture, the two document sets against the parser, the first line of every command and every shipped template. It takes minutes. The manual says what it prints. Only these two commands run the arms: a `capture` or a `compare` of any manifest runs that census's controls and none of them, so running a consumer's command does not exercise an edit to the package.
3. **`ruff check golden_census`** prints `All checks passed!`. Its rules are in `pyproject.toml`. **`mypy`** with no argument prints `Success: no issues found`. Give it no argument: `mypy.ini` lists the files with a glob, an argument replaces that list, and mypy then silently skips a module whose name collides with a sibling directory and still reports success. The stance is mypy's default checking plus `check_untyped_defs`, against Python 3.11. Output produced under any other configuration is not a bug report.

The checks that read the documents run in a checkout and in an install alike, because the wheel carries the documents under the package. The packaging row runs only in a checkout, because an install does not carry `pyproject.toml`. Verify a build in a scratch virtual environment, never on your own machine.

## The documents

Two sets of documents carry the same facts for two readers.

- **The human set:** `README.md` and `docs/manual.md`.
- **The agent set:** `golden-census-skill/SKILL.md` and the files in `golden-census-skill/references/`.

The format documents under `docs/` are the authority for each file format. Each fact has one home; everywhere else points to it. The tool prints the paths of `docs/manifest-format.md`, `docs/census-format.md`, `docs/mutants-format.md`, `docs/contract.md` and `docs/adding-a-template.md`, so moving or renaming one changes what the tool prints.

### What the parity check reads

The DOCS PARITY group of `--selftest` reads the argument parser, never a hand-kept list, and holds each set to six rules.

1. **The human set** names every subcommand and long option. Every (subcommand, flag) pair has its own row in a flag table: a table whose first header cell is `Flag`, whose row names the flag in its first cell and, in its second, the subcommand in backticks or `whole program` for a flag of the bare command. No row names a flag the parser lacks. A row deleted from the table fails, even when the prose still names the flag.
2. **The agent set** meets the same inventory and the same table rule. `SKILL.md` alone names every subcommand and flag. Every `references/<name>.md` that `SKILL.md` names exists.
3. **The version.** Every place in either set and in the example's README that spells the command's name and a version spells `golden_census.__version__`. Each set spells it at least once.
4. **The exit-code sentence.** One member of each set carries the line of the `cli.py` module docstring that begins `Exit codes:`, word for word. `cli.py` owns that sentence because it sits beside `cli.main`, which decides the exit codes. Change it there first.
5. **The procedure.** Exactly one member of each set has the heading `Plugging a project in, in order`. The two procedures have the same number of steps, numbered alike, each opening with the same bold phrase.
6. **The links.** Every `templates/*/README.md` and `examples/*/README.md` is a link target in the human set.

A red row's `actual:` line says what is missing.

### Writing the text

1. One sentence carries one thought. Split a sentence that carries two.
2. Keep the subject and its verb close together.
3. A table cell holds one rule. A cell with several rules becomes a list.
4. A step is an imperative. Number the steps when they have an order.
5. Spell every command example as the parser takes it, required flags included. `--help` of each subcommand is the authority.
6. Quote every claim about what the tool prints from a run you made.
7. Write American English.

## The release set

The release set is the sdist's `include` list in `pyproject.toml`, under `[tool.hatch.build.targets.sdist]`. Nothing else is released. A file is released when the public repository carries it and shipped when an install does.

Every file in it is written for a stranger. It names no other project, no path on a machine, no working session and no person. `LICENSE.txt` is the one exception.
