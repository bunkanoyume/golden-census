# The contract: what a project provides to plug in

golden-census knows nothing about languages, test tools or IDEs. It starts a command, waits, and reads what the command wrote. A project plugs in by providing one such command. This page states what that command must do. `golden-census probe` runs a candidate command and names the clause it breaks.

## The five clauses

A command plugs in when it meets all five clauses.

1. **Takes an output path and writes one file there.** The path arrives in one of two ways. It is an argument: the manifest spells `<WRITES>` where it goes. Or it is an environment variable: a surface's `env` sets the variable to `<WRITES>`. The command creates the file. It never chooses the path.

2. **Is deterministic.** Two runs with the same inputs write byte-identical files. Inputs the command loads itself, such as fixtures, are fine. Four sources are not: the clock, a random source, the network, and an unordered collection whose order reaches the output. `probe` names the first differing line of two text files. It folds the paths it handed the command out of both files first. For two files that are not UTF-8 text, `probe` names the first differing byte. A note about a file golden-census could not decode is not the file, so it compares such files as bytes.

3. **Exits 0 on success and non-zero otherwise.** A run that could not write the file must not exit 0. A test tool that prints `SUCCEEDED` when its filter matched nothing is the standing example of a tool that breaks this clause. The fix is the command's own check that the file exists.

4. **Prints nothing that moves, and writes no machine fact.** golden-census records stdout and stderr as goldens too. Empty is best. Stable is acceptable. A build log with paths and timings is neither. The wrapper that swallows the log is part of the command.

   A machine fact is a home directory, a checkout path or a temp path. It makes a golden a golden about one machine. `probe` scans three texts per run: stdout, stderr and the file the command wrote. It scans with the patterns of a capture's contraband scan. The file is the text a golden commits. A command that redirects its output into its file prints nothing, so a scan of the streams alone would find nothing. `probe` does not scan a file that is not UTF-8 text. The row names the run whose file that was. It never counts that file clean.

   A child that inherits the command's stdout or stderr holds the pipe open while the child lives. golden-census reads the pipe until it closes. A daemon, a watcher or a helper left running in the background keeps the pipe open after the command has exited. The capture then waits for output from a command that has finished. golden-census keeps no clock. The caller owns every deadline, and the manual says more. A command that backgrounds anything must give the child its own streams. Redirect them to a file or to `/dev/null`, or start the child in a session of its own. A child started in a session of its own is outside the run's process group, so the sweep and the process-group line never reach it: it is the subject's to stop. Then the command is the last writer to the pipe. `probe` waits for such a child like any other run and reports no clause for the wait.

5. **Runs under the census's environment.** golden-census builds the subprocess environment from nothing. It holds the census's pinned variables and its passthrough list. A command that needs another variable asks for it in the census, where the reason is written down. A command that silently depends on a variable it did not ask for fails clause 2 the day the machine changes.

## A program that only prints

A command that writes no file is still a subject. A `run` row records its stdout, its stderr and its exit code. `writes` is optional. In golden-census's bundled fixture, seven of the eight surfaces write no file.

`probe` is the one place such a program needs help. Clause 1 says golden-census chooses the path. So give `probe` a shell that writes the file:

    golden-census probe -- sh -c 'mytool --json > "$1"' _ '<WRITES>'

The shell's `$0` is `_`, so the path arrives as `$1`. Quote the script and `<WRITES>` both. A shell reads the angle brackets as a redirection.

A tool that prints findings and exits non-zero keeps every clause:

    golden-census probe -- sh -c 'mylinter > "$1"' _ '<WRITES>'

This report reads `5/5 passed`, and clause 3 reads `actual: exit codes [1, 1]`. Clause 3 asks whether the two runs agree and a file was written. It does not ask whether the code is 0.

The pipe belongs to the probe alone. The manifest names the program itself in a `run` row, with no shell anywhere. `capture --twice` is the determinism proof once the manifest exists. The pipe moves everything the command printed into the file. Clause 4 scans that file, so a home path the command prints is found either way.

## Writing a runner

A library has no command line, so it cannot plug in by itself. A runner gives it one. A runner is a small program of your own, in the subject's language, that golden-census starts like any other command. The shipped templates carry one for a Python function and two for a Swift function, under `swift test` and under `xcodebuild`. For any other language, write one to this shape, which is the five clauses applied to a function.

1. **Take the output path and nothing else.** It is the last argument, where the manifest spells `<WRITES>`, or the environment variable the surface's `env` names.
2. **Load fixed inputs from files beside the runner,** found from the runner's own location and never from the working directory. A list of fixture names in the runner's source is the usual shape.
3. **Call the function once per fixture** and collect the results, keyed by the fixture's name.
4. **Encode the results as text in a fixed order:** JSON with sorted keys, a fixed indent and one trailing newline. Order every collection yourself. An encoder that walks a hash map in the map's own order writes a file that moves.
5. **Write that text to the output path, print nothing, and exit 0.**
6. **On any failure, print one line to standard error and exit non-zero:** the error's name and its first line, never a stack trace and never a path of the machine. Standard error is a golden too.

[`templates/python-function/runner.py`](../templates/python-function/runner.py) is this shape, and [its README](../templates/python-function/README.md) explains every line. The Swift runner is the same shape written as a test, because a Swift function is reached through its test target; [its README](../templates/swift-package/README.md) says how the job reaches it. `probe` is the proof that a runner meets the clauses. Run it on the runner before a manifest names it.

## `golden-census probe`: the five clauses, executed

    golden-census probe [--census FILE] [--writes-env NAME] -- <command…>

Everything after `--` is the candidate. Write `<WRITES>` where its output path goes. Quote it, because a shell reads the angle brackets as a redirection. These four forms are complete commands:

    golden-census probe -- mytool --json '<WRITES>'
    golden-census probe --writes-env OUT_PATH -- mytool --json
    golden-census probe --census census.toml -- ./run.sh '<WRITES>'
    golden-census probe -- sh -c 'mytool --json > "$1"' _ '<WRITES>'

The last form is for a command that only prints. The section above explains it.

`probe` runs the candidate twice. Each run gets a fresh output path. Each run gets an environment built from nothing. Without `--census`, that environment is golden-census's built-in default. It holds `COLUMNS=80`, `SOURCE_DATE_EPOCH=0`, a `TMPDIR` of exactly 51 characters, and `PATH` and `HOME` carried by name. A capture runs a subject under the same rule, built by the same code. With `--census`, the environment is that census's pins and its passthrough list.

`probe` runs the candidate in the current directory and never changes it. Run it from the project's directory. A relative path in the candidate resolves there.

`probe` exits 0 when all five clauses pass, 1 when a clause failed, and 2 when it refused. It needs no manifest and no census, because it answers its question before either exists.

### A green report

This is one report, on a command that keeps every clause. Every command that launches a process opens with a line naming the run's process group. The sample leaves that line out; the manual explains it.

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

  Clause numbers are those of docs/contract.md.
```

With no `--census`, clause 5 lists exactly six names: `COLUMNS, GOLDEN_CENSUS_CHILD, HOME, PATH, SOURCE_DATE_EPOCH, TMPDIR`. A list of five is a bug in golden-census, not in the command. Report it.

### A red report

This is one report, on a command that exits 0 and writes no file.

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

  Clause numbers are those of docs/contract.md.
```

### Reading a red row

A `[FAIL]` row states the fact that broke the clause on its `actual:` line. A `next:` line under it says what to change. One entry per clause follows. Each says what red means and where to look.

1. **Clause 1.** The command chose its own path, or it wrote nothing. The `actual:` line reads `run 1 wrote nothing, run 2 wrote nothing`. Put `<WRITES>` where the path goes, or name the variable with `--writes-env`.

2. **Clause 2.** Something in the output reads the clock, a random source, the network or an unordered collection. The `actual:` line reads `they differ at line 7`. A `first:` line and a `second:` line quote the differing line from each run. For files that are not UTF-8 text, the line reads `they differ at byte 2`, with both bytes. When a run wrote no file, the line reads `not judged` and clause 1 says why.

3. **Clause 3.** A run exited 0 and wrote no file. The `actual:` line reads `exit codes [0, 0]; run(s) [1, 2] exited 0 and wrote no file`. Add the command's own check that the file is there.

4. **Clause 4.** The row asks two questions. Did the streams move between the two runs? Does anything the run produced carry a machine fact? The detail says which half broke. It names each hit by run, text and line:

   - `run 1 stdout:3 an absolute home path: /Users/someone`
   - `run 1 the written file:1 an absolute home path: /Users/someone`

   A hit on `the written file` is about bytes your command put on disk, not about anything it printed. A path in a hit is one your command found for itself, because `probe` folds its own paths first. It folds the output path it chose, its work directory and the fixed-width `TMPDIR` to `<WRITES>`, `<WORK>` and `<TMPDIR>`. It folds them in each run's stdout, stderr and written file before clauses 2, 4 and 5 look at anything. When a file is not UTF-8 text, the detail says it was `NOT scanned` and ends `disclosed, not a pass`.

5. **Clause 5.** The command's output carries the value of a variable the built environment did not pass. The `actual:` line reads `run 1 stdout carries the value of $SDKROOT, which the built environment did not pass`. The command found the variable some other way. A golden recorded under it is a golden about your machine. Add a census row for the variable, a `pin` or a `passthrough` entry with the reason, or stop the command reading it.

   The canary has two exceptions. Both are stated in the row.

   - It ignores values shorter than 8 characters. Short values such as `1`, `xterm` or a language code coincide with ordinary output. A threshold that reported them would make a row nobody could read.
   - It ignores a value that is contained in a path the probe handed the command. The probe hands the command four strings: the working directory, its work directory, the fixed-width `TMPDIR` and each run's output path. A variable whose value is contained in any of them is not evidence of anything. The command was told that string.

   The test is containment, not equality. A shell's `$PWD` holding the whole working directory is the obvious case. A variable holding one component of that path, such as a session id, is the same case. So is a variable holding a prefix of it, such as a temp root. Both occur in the directories an agent works from. A tool that writes down the directory it scanned does what it was told. A census `path` fold, not this clause, keeps that directory out of a golden.

### The banner

The banner shows the candidate's argv with every absolute directory golden-census knows folded to a token. A report pasted into a hand-back then carries no home directory, provided the command is spelled with those paths.

The banner folds through the census's `path` rows. It folds the interpreter to `<PYTHON>` first. Without `--census`, the `path` rows are `<CWD>`, `<TMPROOT>` and `<TMPDIR>`. So the banner reads `<PYTHON>` and `<CWD>`.

Three spellings of the interpreter fold:

- the path golden-census is running under
- that path resolved
- the short name `PATH` resolves to, when it is the same file

The fold covers the spellings this machine offers. It does not cover every path that could point at the binary. Any other link to the interpreter is printed as typed. That includes a symlink you made and a shim in front of it. A directory spelled through a symbolic link is printed as typed too.

A path that begins with a folded one and goes on past a `.` is printed as the token followed by the rest. `…/python3.12` beside `…/python3` reads `<PYTHON>.12`. The working directory followed by `.bak/y` reads `<CWD>.bak/y`.

### What `next:` means

Every refusal golden-census prints ends in a line that says what to do next, in one sentence. A red row may carry that line or not. A `probe` clause row carries one. So does the verdict row of every census pin and fold. A row without one has said everything it has on its detail line.

## What else golden-census gives back

- **`GOLDEN_CENSUS_CHILD=1` in every subject environment.** No census names this variable, and every command gets it. golden-census sets it after the pins and the passthrough. A census never pins it, and a surface's `env` never overrides it. The census format and the manifest format give the two refusals.

  The variable says the one thing a subject cannot find out for itself: golden-census started this process.

  A command may honor it. It is not a sixth clause. A subject whose own self-test would run the census again reads the marker and refuses. A subject that ignores the marker behaves exactly as it did before.

  The value is one character. That is below the 8-character floor of clause 5's canary, so the canary never reads it as contraband in your output.

- **The `state` and `precondition` rows of the census.** They record the machine facts the command depends on, such as the toolchain version and the OS version. A golden that moves for a machine's reason is then attributed to the machine.

- **The contraband scan.** It refuses any capture whose output carries an absolute path the census did not fold. A command that leaks its project path is caught at the first capture, not in a committed golden.

## What the project owns

The project owns everything about its own tool.

- A Swift app under `xcodebuild` needs a wrapper. The wrapper quiets the build log, disables parallel test hosts, gives the sandboxed test host an entitlement to write the file, and checks that the file exists.
- A Python function needs a 56-line script. The script imports the function, loads a fixture and dumps JSON.
- A compiled CLI needs nothing.

The shipped templates in `templates/` carry that ownership for Python functions and for Swift under `swift test` and `xcodebuild`. They mark the holes. A language with no template needs only a runner, written to the shape in "Writing a runner" above. A template for another tool is a directory anyone can add. `docs/adding-a-template.md` says how.

## The cost of plugging in, honestly

Writing the command once costs between nothing and an afternoon. A CLI that already writes files costs nothing. A GUI app costs an afternoon: its pure seam has to be found first, then a runner test and a wrapper. After that, each hand-back costs one `compare`, which prints one line.

The command is worth writing when a refactor could silently change the output of at least one function. Without the command, no one would notice until a user did.
