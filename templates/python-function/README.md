# python-function: one Python function, frozen

`golden-census init <dir> --template python-function` writes `runner.py` beside
the neutral three. The runner imports one module. It calls one function over a
list of fixture files. It writes every answer as one sorted-key JSON document
to the path golden-census names. That document is the surface. The runner
prints nothing.

## 1. What the runner freezes

One function's answers to fixed inputs. The runner reads each fixture file as
UTF-8 text and calls the function once per fixture. It keys the results by the
fixture's path and writes them together. A diff names the fixture and the key
that moved.

Anything the function reads for itself breaks this: the clock, a random
source, an unordered collection whose order reaches the output. `capture
--twice` refuses it, and it calls for a census row nobody has written yet.

## 2. The three holes

| hole | what goes in it | example |
|---|---|---|
| `MODULE` | the module the function lives in. The hole sits after `import ` in `runner.py`, so the value is the module name alone | `mytool.parser` |
| `FIXTURES` | the fixture paths, one quoted string per element, each relative to the runner's own directory. The brackets are already there | `"fixtures/a.txt", "fixtures/b.txt"` |
| `FUNCTION_CALL` | one expression over `text` (the fixture's contents) and `path` (its path), whose value `json.dumps` can serialize | `mytool.parser.parse(text)` |

`MODULE` is spelled inside `main`. A module that will not import is one line
on stderr and exit 1, not a traceback. For a module named `nopkg` the line is
`ModuleNotFoundError: No module named 'nopkg'`.

When Python runs a script, the script's own directory is the first entry on
`sys.path`. A package beside `runner.py` imports by its name. For a package
elsewhere, move the runner beside it, or spell `MODULE` as the path from there.

A result that is not JSON-serializable fails the same way, in one line. A
dataclass, a set and a custom object are such results. For a set the line is
`TypeError: Object of type set is not JSON serializable`. Convert the result
in `FUNCTION_CALL`: `dataclasses.asdict(...)`, `sorted(...)`, `str(...)`.

## 3. The manifest lines this runner implies

`init` wrote the neutral manifest with its holes in place. This block shows the
lines of the holes `COMMAND`, `INPUT_ARGS`, `SURFACE_ARGS` and `WRITES_EXT`,
filled for this runner.

```toml
[subject]
command = ["<PYTHON>", "<HERE>/runner.py"]  # `init` wrote runner.py beside this manifest; <HERE> is that directory

[inputs.fixtures]
args     = []                              # the fixture list is FIXTURES inside the runner, not an argument
surfaces = ["results"]

[surfaces.results]
args   = ["<WRITES>"]
writes = "<WORK>/<input>-<surface>.json"
```

The `writes` line is the neutral manifest's line with `WRITES_EXT` set to
`json`. The line `writes = "<WORK>/results.json"` is a different valid
choice. It loads and captures, and the golden records the file as
`results.json` under either spelling, because the recorded name is always
`<surface>.<ext>`.

**Why `<HERE>` and not a bare `runner.py`.**

- A relative element of `command` resolves under `root`, the cwd of every run.
- `init` wrote `runner.py` beside the manifest.
- The manifest is usually in a subdirectory, not at the subject's root.
- `<HERE>` is the directory the manifest sits in.
- So `<HERE>/runner.py` names the runner wherever the manifest is: in a
  subdirectory of the subject, at its root, or in another repository.

`mutants` clones the subject and runs this manifest against the clone. When the
manifest sits inside the subject, `mutants` carries `<HERE>` onto the clone.
The runner is a file of the subject there, so the clone has its own copy. Every
check executes that copy. A manifest that describes a tree in another
repository keeps its own directory. That directory is the only place its runner
is.

golden-census checks `<HERE>` when it reads the manifest. An element that opens
with it must name a file that is there. A runner that is not there is one
refusal before anything runs. Without the check, a capture would record a
Python that could not open a script.

A runner the clone does not carry is a refusal naming both paths. A runner that
was never committed is one. The refusal says `which the copy of the subject
under test does not have`. Its `next:` line says to commit the file.
golden-census never falls back quietly to the tree you are standing in.

`version` (`docs/manifest-format.md`'s `[subject]` key) is optional. This block
leaves it out, because the runner has no version mode. A `version =
["--version"]` line is not refused if it reaches this runner. `argv` is then
`["runner.py", "--version"]`, which satisfies the two-argument check. The run
writes its results JSON to a file named `--version` under `root`. Measured:
`runner.py --version` exits 0 and writes `<root>/--version`.

Probe the runner before the first capture. The steps run from the directory
the manifest sits in, where the runner is, because `probe` runs the candidate
in the current directory.

1. Print the interpreter that runs golden-census. Use the `python3` you run
   `python3 -m golden_census` with:

   ```
   PYTHON="$(python3 -c 'import sys; print(sys.executable)')"
   ```

2. Probe the runner. Quote `<WRITES>`, because a shell reads the angle brackets
   as a redirection:

   ```
   golden-census probe -- "$PYTHON" runner.py '<WRITES>'
   ```

3. Check the tally line. It reads `  5/5 passed`.

`probe` takes no manifest, so it does not expand `<PYTHON>`. Spell the
interpreter as golden-census's own, by its full path. A bare `python3` can name
another interpreter, and then the probe checks a Python the manifest never
runs. The banner shows the difference. golden-census's own interpreter prints
as `PROBE  <PYTHON> runner.py <WRITES>`, and any other spelling prints as
spelled. The probe runs the runner twice and reports the five clauses of
`docs/contract.md`.

## 4. Why each line of the runner exists

- **`HERE = os.path.dirname(os.path.abspath(__file__))`** — fixtures resolve
  against the runner's directory, not the cwd. The list reads the same
  whichever directory golden-census runs from.
- **`if len(argv) != 2` → usage, exit 2** — an argument the runner did not
  expect is a wrong manifest. A wrong manifest is a refusal, never an empty
  file that reads as a pass.
- **`import <<HOLE:MODULE>>` inside `main`** — see §2: one line, not a
  traceback.
- **`open(path, encoding="utf-8", newline="")`** — the encoding is stated.
  The default is the machine's locale, and a golden that depends on the
  locale is a golden of the machine. `newline=""` keeps the fixture's own
  line endings. A `\r\n` reaches the function as written, not as `\n`.
- **`RuntimeError(f"fixture {fixture}: …")`** — a missing fixture is reported
  by its relative name. Python's own message would carry the absolute path.
  Stderr is a golden, and a home directory in one is a diff between two
  machines.
- **`json.dumps(results, sort_keys=True, indent=2, ensure_ascii=False)`** —
  sorted keys make the bytes canonical. The indent makes a diff name the key
  that moved, instead of reporting one enormous line. `ensure_ascii=False`
  keeps non-ASCII text readable in the golden. The runner adds a trailing
  newline, so the file ends the way a text file does.
- **`newline="\n"`** — the written bytes are the same on every platform.
- **`except Exception` at the entry point → one line, exit 1** — this is
  clause 3 of the contract: a run that could not write the file exits
  non-zero. It is also clause 4: what the run prints is one stable line. A
  traceback carries paths and line numbers, and both move.
- **Nothing printed on success** — clause 4 again. golden-census records
  stdout and stderr as `.out` and `.err`. Empty is the cheapest golden there
  is.

## 5. Written against

Python 3.11, standard library only. `tomllib` makes 3.11 golden-census's
floor. The runner itself needs nothing newer than 3.9. `--selftest`'s
TEMPLATES group measures this: it scaffolds this template into a scratch
project on every run and holds it to hole parity.

## 6. Traps

- **The runner's directory is `sys.path[0]`, the cwd is not.** Python puts a
  script's own directory first on the path. The manifest's `root` is the cwd of
  the run, and it is not on the path unless the two coincide. Put `runner.py`
  beside the package it imports, or spell `MODULE` from there.
- **A dict's order is not a fixture's order.** `sort_keys=True` sorts the keys
  of every object the function returns. It does not sort lists. A function
  that returns a list built from a set, or from a dict of unknown order, moves
  between runs. `capture --twice` names the line.
- **An absolute path in the result is contraband.** A function that echoes the
  path it was given (`path`) writes the machine's directory into the golden.
  The census's `<REPO>` fold covers the subject root and nothing outside it.
  Pass `text`, or fold the path yourself before returning it.
- **Two fixtures with one name collide.** The result is keyed by the fixture
  path as written in `FIXTURES`. So `a/x.txt` and `b/x.txt` are two keys.
  `x.txt` twice is one key written twice, and the second answer wins silently.
- **The runner's import writes `__pycache__/` into the subject's tree.** The
  environment golden-census builds for a run does not pass
  `PYTHONDONTWRITEBYTECODE`, so Python writes bytecode beside the imported
  module, such as `mypkg/__pycache__/`. `git status` then lists it. Add
  `__pycache__/` to the subject's `.gitignore`: `init` writes no `.gitignore`.
  Without the line a capture still succeeds, and the directory stays in `git
  status`.
