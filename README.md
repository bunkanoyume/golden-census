# golden-census

**Built for LLM agents, golden-census proves that a code change altered nothing observable.** Move verification OUT of the LLM into deterministic code.

## What golden-census does

golden-census runs your program and records exactly what it produces. This record is called a "golden." After a code change, a second recording is compared with the first, byte for byte. golden-census identifies every place the output changed, so you can confirm that no output changed, or that output changed only where you intended.

What is recorded is up to you: a command's stdout, stderr and exit code, or a file the command writes. golden-census holds steady or replaces details that come from outside the program, such as a temp path, a home directory, the locale, a timestamp or a commit id, so the recording of the program's output is the same on every machine. The recording is committed beside the program, and any later commit, branch or worktree is compared against it.

golden-census can record a program written in any language. golden-census runs it as a subprocess and never imports it. A program that already runs from a command line is run and recorded directly. Code with no command line of its own, such as a function or a module, needs a small runner that calls it and writes the result to a file.

## What golden-census is not

- **Not a correctness oracle.** It reports whether behavior MOVED. A golden that records a bug records the bug faithfully; a fix shows up as a differing row for you to attribute.
- **Not a generator.** It writes no tests, no mutants and no manifests. Whoever knows a surface exists writes its row.
- **Not a judge of permitted movements.** The project writes the attribution for a movement it permits. golden-census prints it beside the row and does not judge it.
- **Not a file comparer.** It compares only what it recorded itself, against the golden. It takes no two files from you.

## How golden-census helps LLM coding agents

LLM agents have no direct way to validate that their code edits did not have unintended consequences. Agents burn context, tokens, and time trying to validate their work. An agent asked to validate a code change will sometimes disagree with the agent that wrote the code change. golden-census gives the agent a deterministic byte-comparison check against a recording the project committed, run before the work is handed back.

golden-census ships with a skill file with instructions broken up into reference files so agents read only what is needed. Refusals include guidance for the agent so the agent does not need to search in the skill files.

When run on a program, golden-census prints `kill -- -<PGID>`, a command that stops every process the run started. If the program being recorded hangs, the agent can kill the process group with that command. This allows agents that cannot list processes, because of the sandbox or harness, to stop a hung run.

## Requirements

Python 3.11 or newer and the standard library. No third-party packages, no configuration file, nothing to compile. `git` is needed in three cases: the `git-checkout` precondition of a census, a manifest input pinned to a clone, and `mutants`, which makes a repo-shaped copy of the subject.

golden-census requires macOS or Linux, and has been tested on macOS and Debian-family Linux.

An agent on any model can run a comparison. For creating a golden, strong Opus-class models are recommended. You may of course create the first golden by hand without an agent.

## Install

Use one of these to install:

1. **An installer**
   - `brew install bunkanoyume/golden-census/golden-census`
   - `pipx install git+https://github.com/bunkanoyume/golden-census`
   - `uv tool install git+https://github.com/bunkanoyume/golden-census`
2. **A checkout, with no install.** `bin/golden-census` runs the package beside it from any directory; link it from a directory on your PATH. It uses `$GOLDEN_CENSUS_PYTHON` when set, otherwise the newest `python3.11` or later it finds. `python3 -m golden_census` from the checkout root is the same command.
3. **For an LLM agent**, include the path to `golden-census-skill/` in your prompt, or copy `golden-census-skill/` to wherever your agent loads skills from.

The command is `golden-census`. (Because a hyphen cannot be imported, the package Python imports is `golden_census`.)

## Confirm the install

`golden-census --help` lists the arguments, the options and the full path of each install directory. Running `golden-census` without any flags prints the same output and exits 2 because it ran nothing.

`golden-census --version` prints `golden-census 1.0.1`, allowing coding agents to confirm that the version of the skill the agent is reading is the same version of golden-census that the agent is running.

`golden-census --selftest` runs the whole app against a fixture bundled inside the package. Run it once after an installation and after each update (app, Python, or system). The test can take a couple of minutes and the test output is hundreds of lines.

## Read next

- [`golden-census-skill/SKILL.md`](golden-census-skill/SKILL.md) is the instructions for running golden-census: the procedure, the lines golden-census prints, every flag's rules, and temp-folder and cache rules.
- [`docs/reference.md`](docs/reference.md) is the glossary, the command table with exit codes, the flag table, and the rules every flag follows.
- [`docs/using-golden-census.md`](docs/using-golden-census.md) is for the person who owns the project: what an install contains, checking golden-census itself, how to start using golden-census with a project, keeping the recording up to date, and a list of every other document.
