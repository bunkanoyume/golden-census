# Templates

Open this file at step 2 of "Plugging a project in, in order", or when you choose a template. `golden-census init <DIR> --template <NAME>` writes the neutral manifest, census and mutants file, and then a template's own runner on top of them. `golden-census init --list` prints the names and a summary of each.

## Which template

| Template | Use it when | What it writes besides the neutral three |
|---|---|---|
| `python-function` | The subject is a Python function. | `runner.py`: it imports one module, calls one function over a list of fixture files, and writes sorted-key JSON to the path golden-census names. |
| `swift-package` | The subject is a function of a SwiftPM package. | `GoldenCensusRunner.swift`: a Swift Testing test that reads its job from the environment. It runs under `swift test`, filtered to `GoldenCensusRunner`. |
| `swift-xcodebuild` | The subject is a function of an Xcode app or framework. | The same test, plus `golden-census/wrapper.py`, which runs one quiet `xcodebuild test` and makes the out file, not the exit code, the verdict. |
| `_neutral` | The subject already runs from a command line, a compiled tool that writes a file for example. Nothing else fits. | Nothing. The three files are written whatever template you name. |

- With no `--template`, `init` writes the neutral three alone. `--template _neutral` writes the same three, and `init --list` names `_neutral` with the rest.
- An unknown name is refused, and the refusal lists the shipped names.
- `init` is the one command that needs the templates. Without them it refuses. Every other command runs, and `--selfcheck` names their absence as a disclosed SKIP.

## A language with no template

`init <DIR>` with no `--template` writes the neutral three. Write the runner yourself, in the subject's language, to these six steps. A runner that follows them meets the five clauses of `probe`.

1. Take the output path and nothing else: the last argument, where the manifest spells `<WRITES>`, or the variable the surface's `env` names.
2. Load fixed inputs from files beside the runner, found from the runner's own location, never from the working directory.
3. Call the function once per fixture and collect the results, keyed by the fixture's name.
4. Encode the results as text in a fixed order: JSON with sorted keys, a fixed indent and one trailing newline. Order every collection yourself.
5. Write that text to the output path, print nothing, and exit 0.
6. On any failure, print one line to standard error and exit non-zero: the error's name and first line, never a stack trace and never a path of the machine.

The `python-function` runner is this shape; read it as the model. Then `probe` the runner (step 3) before the manifest names it.

## What `init` prints

The neutral three print their holes, and a template adds its own; the sample below shows the template's. The shape of a hole line, from a run of `init . --template python-function`:

```
INIT  python-function  (1 file(s)) — a Python function: a runner script imports it, loads each fixture, dumps sorted-key JSON
  wrote runner.py
  3 hole(s) to fill; each is written as <<HOLE:NAME>> in the file named under it:
    MODULE — the module the function lives in, as `import` spells it — …
      in runner.py
```

- The last line of the output names the template's own files that carry a hole, when there is one, and says that no command refuses a hole left there.
- Fill the runner's holes, and `probe` the runner, before you fill the manifest's holes.
- Every hole's meaning is also the comment beside it in the file, so nothing is lost when `init`'s output scrolls away.
- Both Swift templates write the runner into the literal directory `<<HOLE:TEST_TARGET_DIR>>/`, because `init` cannot ask the question first. The hole's line says: `that file was written to the literal <<HOLE:TEST_TARGET_DIR>> directory, so MOVE it once you have filled the hole`. Fill `TEST_TARGET_DIR`, then move the file into the test target's source directory.
- A shipped example shows the result of a whole run: `examples/python-function/`, in a checkout, holds the python-function template filled in, with its manifest, census, mutants file and golden. Its manifest says `root = "../.."`: `<DIR>` may be a directory below the subject's root. It is for you to copy. In an install it is at `<package>/_shipped/examples/python-function/`.

## The `probe` line of each template's runner, and what it prints

`<interpreter>` is the path of the Python running golden-census (step 3). Fill the holes first.

- `python-function`, from the manifest's directory: `golden-census probe -- <interpreter> runner.py '<WRITES>'`. It prints `5/5 passed`.
- `swift-package`, from the directory holding `Package.swift`: `golden-census probe --writes-env GOLDEN_CENSUS_OUT -- swift test -q --filter GoldenCensusRunner`. The runner reads its output path from `GOLDEN_CENSUS_OUT`, which the manifest's surface sets in `env`. Clause 4 is red on `swift test`'s timestamps and durations, even with `--census`: `4/5 passed`, exit 1. `references/commands.md`, `--census`, says why that red is expected. The fix is the `regex` fold in the template's README, section 3, and step 5 (`capture --twice`) is what proves it, not the probe.
- `swift-xcodebuild`, from the project's root: `golden-census probe -- <interpreter> golden-census/wrapper.py --project <project> --scheme <scheme> --test <test id> --entitlements <entitlements> . '<WRITES>'`, the wrapper's arguments being the manifest's `command` with `.` where it spells `<ROOT>`. It prints `5/5 passed`. The wrapper prints nothing on success.

## Where the template READMEs are

Each template's README is its pattern document: what the runner freezes, every hole, the manifest lines the template implies, and its traps. Read it at step 2.

1. **In a checkout:** `templates/<NAME>/README.md`, beside the `golden_census` package directory.
2. **In an install:** `<NAME>/README.md` under the `templates` directory `golden-census --help` names.

Sections to open:

| Template | Open | For |
|---|---|---|
| `python-function` | section 2 | the three holes |
| `swift-package` | sections 2 and 6 | the five holes; moving the runner out of the literal `TEST_TARGET_DIR` directory, the first of the five |
| `swift-package` | section 3 | how `swift test` passes the environment to a filtered run, and the timestamp fold |
| `swift-xcodebuild` | sections 2, 3 and 8 | the five holes; the wrapper's arguments, which are the manifest's `command`; moving the runner out of the literal `TEST_TARGET_DIR` directory, the first of the five |
