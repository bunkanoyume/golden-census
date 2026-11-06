# Subject requirements: what a program must do to be recorded

golden-census records what a program produces. It does this by starting a command, waiting for it to finish, and reading what the command printed and wrote. It knows nothing about languages, test tools or IDEs. To use golden-census with a project, you give golden-census one such command. The program that command runs is called the subject.

This document states the five requirements the command must meet, called clauses. `golden-census probe` runs a candidate command and reports each clause as a pass or a fail. The second half of this document explains how to read that report. Every `probe` report ends by naming this document.

This document covers:
1. The five clauses
2. A program that only prints
3. Writing a runner
4. `golden-census probe`: the five clauses, executed
5. What else golden-census gives the subject
6. What the project owns

## The five clauses

1. **Takes an output path and writes one file there.** golden-census chooses the path and passes it to the command. It passes it in one of two ways: as an argument, where the manifest writes `<WRITES>`, or as an environment variable, which the surface's `env` sets to `<WRITES>`. The command creates the file at that path. It never chooses the path itself.

2. **Is deterministic.** Two runs with the same inputs write byte-identical files. Inputs the command loads itself, such as fixture files, are fine. Four things are not, because they change between runs: the clock, a random number source, the network, and a collection whose order is not fixed, when that order reaches the output. `probe` compares the two files and names the first line that differs. Before comparing, it replaces the paths it gave the command with placeholders, so that the output path itself does not count as a difference. If the files are not UTF-8 text, `probe` compares them as bytes and names the first differing byte.

3. **Exits 0 on success and non-zero otherwise.** A run that could not write the file must not exit 0. The standing example of a tool that breaks this clause is a test runner that prints `SUCCEEDED` when its filter matched no test. The fix is a check in the command itself that the file exists.

4. **Prints nothing that changes between runs, and nothing about the machine.** golden-census records stdout and stderr as well as the file. Empty output is best; output that is the same every run is acceptable; a build log with paths and timings is neither. If the tool prints such a log, a wrapper that discards it is part of the command.

   A machine fact is a path that belongs to this machine: a home directory, the checkout's path or a temporary directory. Output that contains one describes the machine, not the program's behavior. `probe` looks for machine facts in stdout, stderr and the written file, with the same patterns a capture uses for its contraband scan ("What else golden-census gives the subject" below). `probe` scans the written file too, because a command that redirects its output into the file prints nothing on stdout or stderr. `probe` scans only UTF-8 text. It reports a written file that is not UTF-8 text as not scanned, and never counts that file as clean. The path of an input the command was handed counts too: the probe cannot tell it from a leak. A manifest that spells that input through `<CLONE>` or `<WORK>` folds it, and `capture --twice` is then the proof.

   One trap: a child process that inherits the command's stdout or stderr keeps the pipe open for as long as it lives. golden-census reads the pipe until it closes, so a daemon, watcher or helper left running in the background makes golden-census wait after the command has finished. golden-census has no timeout; the caller decides when a run has taken too long (the skill's `references/commands.md`, "Run every command the same way", says how). A command that starts a background process must give that process its own output: redirect it to a file or to `/dev/null`, or start it in a session of its own. A process in its own session is outside the run's process group, so golden-census cannot stop it; that is the subject's job.

5. **Reads no environment variable it was not given.** golden-census builds the command's environment from nothing. It contains the variables the census pins, and the variables the census lists as passed through, and nothing else. A command that needs another variable must ask for it in the census, where the reason is written down. A command that quietly depends on a variable it did not ask for breaks clause 2 the day the machine changes.

## A program that only prints

A command that writes no file can still be a subject. A `run` row in the manifest records its stdout, stderr and exit code, and the `writes` key is optional. In golden-census's own bundled test program, seven of the eight recorded surfaces write no file.

`probe`, however, always expects a file, because clause 1 is about a path golden-census chooses. To probe a program that only prints, run it through a shell that writes the file:

    golden-census probe -- sh -c 'mytool --json > "$1"' _ '<WRITES>'

The `_` becomes the shell's `$0`, so the output path arrives as `$1`. Quote both the script and `<WRITES>`, or the shell reads the angle brackets as a redirection.

A tool that prints findings and exits non-zero, such as a linter, meets every clause:

    golden-census probe -- sh -c 'mylinter > "$1"' _ '<WRITES>'

This report reads `5/5 passed`, with clause 3 reading `actual: exit codes [1, 1]`. Clause 3 asks whether the two runs agree and a file was written, not whether the exit code is 0.

The shell is for the probe only. In the manifest, name the program itself in a `run` row, with no shell. Once the manifest exists, `capture --twice` is the determinism proof. Clause 4 scans the file the shell wrote, so a home path the program prints is found either way.

## Writing a runner

Code with no command line of its own, such as a function or a module, cannot be a subject by itself. A runner gives it one: a small program you write, in the same language, that calls the code and writes the result to the path it is given. It is the five clauses applied to a function.

The shipped templates provide a runner for a Python function and two for a Swift function, one under `swift test` and one under `xcodebuild`. [`templates/python-function/runner.py`](../templates/python-function/runner.py) is the model, and [its README](../templates/python-function/README.md) explains every line. For any other language, follow the six steps in the skill's `references/templates.md`, "A language with no template". Run `probe` on the runner before a manifest names it; that is the proof it meets the clauses.

## `golden-census probe`: the five clauses, executed

    golden-census probe [--census FILE] [--writes-env NAME] -- <command…>

Everything after `--` is the candidate command. Write `<WRITES>` where its output path goes, and quote it. These four forms are complete commands:

    golden-census probe -- mytool --json '<WRITES>'
    golden-census probe --writes-env OUT_PATH -- mytool --json
    golden-census probe --census census.toml -- ./run.sh '<WRITES>'
    golden-census probe -- sh -c 'mytool --json > "$1"' _ '<WRITES>'

The second form passes the path in an environment variable instead of an argument. The last form is for a program that only prints, explained above.

`probe` runs the candidate twice. Each run gets a fresh output path and an environment built from nothing. Without `--census`, that environment is golden-census's built-in default: `COLUMNS=80`, `SOURCE_DATE_EPOCH=0`, a `TMPDIR` of exactly 51 characters, and `PATH` and `HOME` copied from your environment. A capture builds a subject's environment with the same code. With `--census`, the environment is that census's pinned variables and its passthrough list.

`probe` runs the candidate in the current directory and never changes it, so run it from the project's directory. A relative path in the candidate is resolved from there.

`probe` exits 0 when all five clauses pass, 1 when a clause failed, and 2 when it refused to run. It needs no manifest and no census, because its question comes before either exists.

### A green report

This is one report, on a command that meets every clause. Every command that starts a process first prints a line naming the run's process group; the sample leaves that line out. The skill's `references/commands.md` explains it. `<install>` in the last line stands for the directory that holds `docs/`; the real line prints the path in full.

```
==============================================================================
PROBE  <PYTHON> <CWD>/tools/export.py --json <WRITES>
==============================================================================
  [PASS]  1  takes an output path and writes one file there
           actual: run 1 wrote 173 bytes, run 2 wrote 173 bytes
  [PASS]  2  is deterministic: two runs write byte-identical files
           actual: identical
  [PASS]  3  exits 0 on success and non-zero otherwise
           actual: exit codes [0, 0]
  [PASS]  4  prints nothing that moves: stdout and stderr identical across the runs, and no machine fact in either stream or in the written file
           actual: identical and clean
  [PASS]  5  runs under the census's environment: reads no variable the built environment did not pass
           actual: 6 variable(s) passed — COLUMNS, GOLDEN_CENSUS_CHILD, HOME, PATH, SOURCE_DATE_EPOCH, TMPDIR; no variable value of 8 or more characters appears in the output (shorter values coincide with ordinary text, and a value inside a path the probe handed the command is skipped): clean

  5/5 passed

  Each clause row is explained in <install>/golden-census-skill/references/verdicts.md, "The `probe` block".
```

Without `--census`, clause 5 lists exactly six variables: `COLUMNS, GOLDEN_CENSUS_CHILD, HOME, PATH, SOURCE_DATE_EPOCH, TMPDIR`. If it lists five, that is a bug in golden-census, not in your command. Report it.

### A red report

This is one report, on a command that exits 0 but writes no file.

```
==============================================================================
PROBE  <PYTHON> <CWD>/tools/nowrite.py <WRITES>
==============================================================================
  [FAIL]  1  takes an output path and writes one file there
           actual: run 1 wrote nothing, run 2 wrote nothing
           next: Make the command create the file at the path it is given. It arrives as <WRITES> in the argv, or as the variable --writes-env names; the command never chooses the path.
  [FAIL]  2  is deterministic: two runs write byte-identical files
           actual: not judged — one of the two runs wrote no file, so there is nothing to compare. Clause 1 above says which.
           next: Fix clause 1 first; determinism is a statement about two files, and this run has fewer than two.
  [FAIL]  3  exits 0 on success and non-zero otherwise
           actual: exit codes [0, 0]; run(s) [1, 2] exited 0 and wrote no file
           next: Add the command's own check that the file exists, and exit non-zero when it does not. A tool that prints SUCCEEDED when its filter matched nothing is the standing example.
  [PASS]  4  prints nothing that moves: stdout and stderr identical across the runs, and no machine fact in either stream or in the written file
           actual: identical and clean
  [PASS]  5  runs under the census's environment: reads no variable the built environment did not pass
           actual: 6 variable(s) passed — COLUMNS, GOLDEN_CENSUS_CHILD, HOME, PATH, SOURCE_DATE_EPOCH, TMPDIR; no variable value of 8 or more characters appears in the output (shorter values coincide with ordinary text, and a value inside a path the probe handed the command is skipped): clean

  2/5 passed

  Each clause row is explained in <install>/golden-census-skill/references/verdicts.md, "The `probe` block".
```

### Reading a red row

A `[FAIL]` row has an `actual:` line that states what broke the clause, and a `next:` line that says what to change. What each clause's red means:

1. **Clause 1.** The command chose its own path, or wrote nothing. The `actual:` line reads `run 1 wrote nothing, run 2 wrote nothing`. Put `<WRITES>` where the path goes, or name the variable with `--writes-env`.

2. **Clause 2.** Something in the output comes from the clock, a random source, the network or an unordered collection. The `actual:` line reads `they differ at line 7`, and a `first:` and a `second:` line quote that line from each run. For files that are not UTF-8 text it reads `they differ at byte 2`, with both bytes. If one run wrote no file, it reads `not judged`, and clause 1 says why.

3. **Clause 3.** A run exited 0 and wrote no file. The `actual:` line reads `exit codes [0, 0]; run(s) [1, 2] exited 0 and wrote no file`. Add a check in the command that the file exists.

4. **Clause 4.** This row asks two questions: did stdout or stderr differ between the two runs, and does anything the runs produced contain a machine fact. The detail says which question failed. A machine fact is named by run, text and line:

   - `run 1 stdout:3 an absolute home path: /Users/someone`
   - `run 1 the written file:1 an absolute home path: /Users/someone`

   A hit on `the written file` is about bytes the command wrote to disk, not about what it printed. Any path in a hit is one the command found by itself: before scanning, `probe` replaces the paths it gave the command with `<WRITES>`, `<WORK>` and `<TMPDIR>` in stdout, stderr and the written file. Those paths are the output path, the probe's work directory and the fixed-width `TMPDIR`. If the written file is not UTF-8 text, the detail says `NOT scanned` and ends `disclosed, not a pass`.

5. **Clause 5.** The output contains the value of an environment variable that golden-census did not pass to the command. The `actual:` line reads `run 1 stdout carries the value of $SDKROOT, which the built environment did not pass`. The command found that variable some other way, and a golden recorded under it would be a recording of your machine. Either add a census row for the variable, a `pin` or a `passthrough` entry with the reason, or stop the command reading it.

   This check has two exceptions, and the row states both:

   - It ignores values shorter than 8 characters. Short values such as `1`, `xterm` or a language code occur in ordinary output, and reporting them would make the row unreadable.
   - It ignores a value that is contained in a path `probe` gave the command. `probe` gives the command four strings: the working directory, the probe's work directory, the fixed-width `TMPDIR` and each run's output path. A variable whose value appears inside any of them proves nothing, because the command was given that string.

   The second exception is about containment, not equality. A `$PWD` holding the whole working directory is the plain case. A variable holding one part of that path, such as a session id, or a prefix of it, such as a temp root, is the same case; both occur in the directories agents work from. A tool that writes down the directory it scanned did what it was told. Keeping that directory out of a golden is the job of a census `path` fold, not of this clause.

### The banner

The first line of the report, after the `=====` rule, shows the candidate's argv with every absolute directory golden-census knows replaced by a placeholder. A report pasted into a hand-back then contains no home directory, as long as the command was spelled with those paths.

The placeholders come from the census's `path` rows. The interpreter is replaced by `<PYTHON>` first. Without `--census`, the `path` rows are `<CWD>`, `<TMPROOT>` and `<TMPDIR>`, so the banner reads `<PYTHON>` and `<CWD>`.

Three spellings of the interpreter are replaced: the path golden-census is running under, that path with symbolic links resolved, and the short name that `PATH` resolves to, when it is the same file. Any other path to the same binary, such as a symbolic link you made or a shim in front of it, is printed as typed. A directory spelled through a symbolic link is printed as typed too.

A path that begins with a replaced one and continues past a `.` is printed as the placeholder followed by the rest: `…/python3.12` beside `…/python3` reads `<PYTHON>.12`, and the working directory followed by `.bak/y` reads `<CWD>.bak/y`.

### What `next:` means

Every refusal golden-census prints ends in a `next:` line that says, in one sentence, what to do. A red row may or may not have one. A `probe` clause row always does, and so does the verdict row of every census pin and fold. A row without one has said everything it has on its detail line.

## What else golden-census gives the subject

- **`GOLDEN_CENSUS_CHILD=1` in every subject environment.** golden-census sets this variable in every command it starts, after the pins and the passthrough list. No census names it, a census cannot pin it, and a surface's `env` cannot override it; the census and manifest format documents give the two refusals. It tells the subject the one thing it cannot find out for itself: that golden-census started it. A subject may use it, for example to refuse to run its own self-test, which would start golden-census again, when golden-census is already running it. A subject that ignores it behaves as before. It is not a sixth clause. Its value is one character, below clause 5's 8-character floor, so clause 5 never reports it.

- **The `state` and `precondition` rows of the census.** They record the machine facts the command depends on, such as the toolchain version and the OS version, so that a golden which changes for a machine's reason can be attributed to the machine.

- **The contraband scan.** Every capture is scanned for absolute paths that golden-census knows and the census did not fold: the home directories, the user's home, the temp root and the directories golden-census made. A capture that contains one is refused. A path elsewhere, such as under `/usr`, is not a hit. A command that leaks its project path is caught at the first capture, not in a committed golden.

## What the project owns

Everything about the project's own tool is the project's to write.

- A Swift app under `xcodebuild` needs a wrapper. The wrapper discards the build log, disables parallel test hosts, gives the sandboxed test host permission to write the file, and checks that the file exists.
- A Python function needs a short script that imports the function, loads a fixture and writes JSON.
- A compiled command-line program needs nothing.

The shipped templates in `templates/` provide the Python script and the two Swift runners, with the project-specific parts marked as holes. A language with no template needs only a runner, as described in "Writing a runner" above. A template for another tool is a directory anyone can add; [`adding-a-template.md`](adding-a-template.md) says how.
