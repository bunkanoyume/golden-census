# golden-census

**Proves that a change altered nothing observable.**

A manifest describes a program: the inputs it runs over, and the surfaces it produces (stdout, stderr, exit codes or a file it writes). golden-census runs the program and normalizes away everything that is about the machine rather than the program, and records the bytes. That record is the golden. After a code change, record them again and compare them byte for byte. Commit the golden beside the program. Any later commit, branch or worktree runs `compare` against it; golden-census checks out nothing to do so. Two recorded captures, from two worktrees, say, are compared without running the program: `compare --against`. A built copy of the program, a bundle say, is compared with the golden its source recorded by running the fresh capture with another command: `compare --command`.

`IDENTICAL` is a finding. A change in the code has not changed the code's behavior.

golden-census drives any program by subprocess. It never imports the subject and never runs its code in-process. The subject can be written in any language. A library needs a runner: it has no command line, so a small program of your own calls the function under test and writes the result to a file; golden-census starts it directly, or through your build or test tool when the language needs one. A program that already runs from a command line needs no runner. golden-census starts the runner and records what it writes.

## What golden-census is not

- **Not a correctness oracle.** Reports whether behavior MOVED. A golden that records a bug records the bug faithfully. A change that fixes the bug shows up as a differing row, exit 1, for you to attribute; golden-census does not say whether the new bytes are better.
- **Not a generator.** Writes no tests, no mutants and no manifests. Whoever knows a surface exists writes its row.
- **Not a judge of permitted movements.** The project writes the attribution for a movement it permits. golden-census prints it beside the row and does not judge it.
- **Not a file comparer.** It compares only what it recorded itself, surface by surface, against the golden. It takes no two files from you, and it explains no difference: it names the row and the line.


## Install

golden-census needs Python 3.11 or newer and the standard library. It has no third-party packages. It has no configuration file of its own and nothing to compile. It reads TOML, which Python reads with `tomllib` from 3.11. `git` is needed in three cases: the `git-checkout` precondition of a census, which the census `init` writes carries; a manifest input pinned to a clone; and `mutants`, which makes a repo-shaped copy of the subject.

The command is `golden-census`. Python imports the package as `golden_census`, so `python3 -m golden_census` works from a checkout's root. A hyphen cannot be imported, which is why the two names differ.

There are two routes to the command, and one more step for an agent.

1. **An installer.** Each puts the `golden-census` command on your PATH, in an environment of its own:
   - `pipx install git+https://github.com/bunkanoyume/golden-census`
   - `uv tool install git+https://github.com/bunkanoyume/golden-census`
   - `brew install bunkanoyume/golden-census/golden-census`

   From a checkout, `pipx install .` or `uv tool install .` installs that checkout.
2. **A checkout, with no install.** The launcher `bin/golden-census` runs the package beside it, from any working directory. Link it from a directory on your PATH to use it as `golden-census`. It finds an interpreter itself. It uses `$GOLDEN_CENSUS_PYTHON` when that is set. Otherwise it tries `python3.15` down to `python3.11`, then a bare `python3` that proves itself 3.11 or newer.
3. **The skill, for an LLM agent.** Copy the `golden-census-skill/` folder to wherever your agent loads skills from. It is the manual written for the agent. `golden-census --help` ends with a `directories:` section that names where this install keeps it, beside `docs/`, the examples, this README and the templates; in a checkout they are beside the package. `golden-census-skill/SKILL.md` is the file the agent reads first.

## A first run

```
golden-census --version
golden-census --selftest
```

`--version` prints `golden-census 1.0.0`. `--selftest` runs the whole app against a fixture bundled inside the package and prints the version on its last line. The [manual](docs/manual.md) says what it prints and how long it takes.

Your own program starts with `golden-census init <dir> --template python-function`, which writes the manifest, census and mutants file with their holes marked, and a runner to fill in. The manual's procedure takes it from there, one command at a time, to a golden you commit beside the program.

`examples/python-function/` is a sample Python app, `wordstats`, which counts the words of a text, with the manifest, runner, mutants, census, and golden. See [`examples/python-function/README.md`](examples/python-function/README.md).

## Where to read next

Read the manual first, whole. Every other document is a reference the manual links where it applies; open one when it does.

- **The manual:** [`docs/manual.md`](docs/manual.md). It gives the procedure for plugging a project in, every command and flag, the lines golden-census prints, and the rules for running it safely.
- **The file formats**, one document for each file golden-census reads:
  - [`docs/manifest-format.md`](docs/manifest-format.md) says what to run.
  - [`docs/census-format.md`](docs/census-format.md) says what surrounds every run.
  - [`docs/mutants-format.md`](docs/mutants-format.md) lists the deliberate changes that test the net.
- **The contract:** [`docs/contract.md`](docs/contract.md) says what a program must provide to be a subject.
- **The templates**, for `golden-census init`:
  - [`templates/python-function/README.md`](templates/python-function/README.md)
  - [`templates/swift-package/README.md`](templates/swift-package/README.md)
  - [`templates/swift-xcodebuild/README.md`](templates/swift-xcodebuild/README.md)
- **The worked example:** [`examples/python-function/README.md`](examples/python-function/README.md).
- **Known issues and cautions:** [`docs/Known_Issues.md`](docs/Known_Issues.md).
- **For an agent that changes golden-census:** [`CONTRIBUTING.md`](CONTRIBUTING.md) is the project's instructions for an LLM coding agent working on the code, the documents or the templates: the goals and principles every change honors, what a change carries, the checks and the document rules. CLAUDE.md imports it, so a Claude Code session reads it at start.
- **For an LLM agent:** the skill in [`golden-census-skill/SKILL.md`](golden-census-skill/SKILL.md) is written for the agent to read first, whole.
