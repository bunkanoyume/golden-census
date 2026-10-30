# Manifest rows to copy

Open this file when you write or change a manifest row, or when you read a golden directory. The manifest is the coder's file. Whoever adds or changes a surface writes its row and its golden in the same commit.

The whole rule for every key is in the format document, `docs/manifest-format.md` under the `docs` directory `golden-census --help` names. This file carries the rows to copy.

## The command line of one run

A run's argv is `command`, then the input's `args`, then the surface's `args`, in that order. A surface that only prints omits `writes`; its stdout, stderr and exit code are recorded.

## One rule for all three files

golden-census reads every key of the manifest, the census and the mutants file, or refuses it.

- A table that carries a key golden-census does not read is refused when the file is read.
- The refusal names the key, the table it is in, and the keys that table takes.
- Copy a row from below instead of inventing a key. A key nobody reads does nothing. A misspelled one does nothing under the name of one that would.

## Names

A surface name and an input name are each ONE path component. A capture writes `<out>/<input>/<surface>.out`, so a name that carries a separator, or names this directory or its parent, is refused when the manifest is read.

## The surface kinds and their scaffolding

A surface is one of four kinds: `run` (the default, no `kind` key), `skip`, `matrix` and `tallies`. Every block below was loaded by a run of `census --manifest`.

```toml
# The subject: the five keys of [subject], `version` optional. `root` is
# relative to this file and is the cwd of every run; `census` is the census
# file, relative to this file; `version` is the arguments that print the
# subject's version, run once per capture into the capture log, never a golden.
[subject]
name    = "wordstats"
root    = "../.."
command = ["<PYTHON>", "<HERE>/runner.py"]
# version = ["--version"]
census  = "census.toml"

# A run is one subprocess. It records .out, .err and .exit.
[surfaces.report]
args = []

# A run that writes a file. The file is recorded too, as <surface>.<ext>.
# Streams and the file are recorded as the subject wrote them, a `\r` included.
# `writes` must begin with <WORK>/, its rest must stay under <WORK>, and its
# extension must not be .out, .err, .exit or .skip, nor its name surfaces.json.
# A path with no extension is refused.
# golden-census removes the file at that path before each run.
[surfaces.export]
args    = ["--quiet", "--json", "<WRITES>"]
writes  = "<WORK>/<input>-<surface>.json"
counter = ["<PYTHON>", "<HERE>/counts.py", "<WRITES>"]   # prints one JSON object of integers

# A written file must be UTF-8 text. For a database, an archive or an image,
# record a text DUMP. A wrapper named as `command` builds the file in <WORK>
# and writes a deterministic dump of it to <WRITES>, with an ORDER BY on every table.
# A stream is held to the same rule: a byte no UTF-8 decoder reads refuses the run, naming the offset.
[surfaces.database]
args    = ["--dump", "<WRITES>"]
writes  = "<WORK>/<input>-<surface>.txt"

# A surface declared unrunnable. The reason IS the golden.
[surfaces.index-store]
skip = "needs a real index store; recorded as SKIP, never a pass"

# Many small runs recorded as ONE compacted record, for a refusal matrix.
# The file is a JSON list of {"label": …, "args": […]}, generated and committed.
[surfaces.flagmatrix]
kind        = "matrix"
include     = "flagmatrix.json"              # relative to this file
record_argv = ["the rows of flagmatrix.json"]   # free text, recorded as this row's argv

# One run reduced to the verdict line of every fenced group.
[surfaces.selftest-tallies]
kind    = "tallies"
args    = ["--selftest"]
rule    = "="                                  # a banner is fenced by two lines of this character
verdict = '^\s*\d+/\d+ passed\s*$'
failing = '^\s*(?:\[FAIL\]|actual:)'           # optional: record each group's failing evidence line too

# One name for a group of surfaces.
[surface-sets]
tree = ["report", "export", "flagmatrix", "selftest-tallies"]

# An input names the set. A set name expands IN PLACE, so this is the four of
# `tree`, then the fifth.
[inputs.demo]
args     = ["examples/demo/App"]
surfaces = ["tree", "index-store"]

# A movement you are permitting, with its attribution.
[[movements]]
path        = "tool/version.out"
attribution = "2.0 release — the number moves once per release"

[[movements]]
path        = "tool/index-*"      # a glob, said out loud
attribution = "2.0 release — the whole group of rows was added at once"
```

Rules that go with those rows:

1. A `writes` recorded under one of the reserved names is refused because `compare` would then read a row that ran as one that ran on neither side.
2. A `\r` is a byte like any other. A change of line ending alone is a `[DIFF]`. A written file's final newline, or its absence, is recorded too.
3. A `failing` pattern records the lines of each group that match it, under that group's verdict line. A standing failure hides a new one under the same tally, so aim the pattern at the row's evidence line, not its name alone. Aim it at lines that hold no timing or digest your census does not fold. The capture log reports `M failing line(s)`. A pattern that reaches nothing shows as zero.
4. `path` in a `[[movements]]` row names ONE surface path exactly, or carries a glob character. A bare directory name permits nothing: `path = "tool"` matches the path `tool` and never `tool/version.out`. To attribute a group, write the glob.
5. `attribution` says why the row moved. A blank one is refused when the manifest is read. Leave the key out to record `(no attribution)`.
6. Two `[[movements]]` rows with the same `path` string are refused when the manifest is read. A comparison in which two rows name one moved row is refused too, naming both. Give one row every reason.
7. A `[[movements]]` row that matches no moved row is reported before the verdict as `unused: …`. The verdict does not change.

A `matrix` surface runs `command`, the input's `args` and each row's `args` once per row of the included file and records the whole set as one compacted record, built for refusal matrices where every row prints the same usage block. `record_argv` is the text `surfaces.json` records as the row's argv, since no single command line exists.

## A surface that needs a fixture, an environment or a pinned input

Every block below was loaded by a run of `census --manifest`. Paste them as separate blocks. A surface or an input name defined twice in one manifest is refused.

```toml
# Runs once per capture, in the work directory, before any row that `needs` it.
# Two [[setup]] tables with one `name` are refused. Every element is passed as
# written: a relative path names one in the work directory, and a script beside
# the manifest is <HERE>/… — never a bare name.
[[setup]]
name    = "fixture"
command = ["<PYTHON>", "<HERE>/make_fixture.py", "<WORK>/fixture"]

# Small text files written into <WORK> before any setup step or row runs.
# The key is a path under <WORK>, such as "fixtures/a.txt", whose every
# component names something. A key that is absolute, climbs with "..", or
# resolves to a directory ("fixtures/", ".") is refused at load. So is a key
# that is a directory above another ("a" beside "a/b.txt"), also when the file
# system folds case or Unicode normalization.
[files."plan.txt"]
lines = ["the first line", "the second line"]

# A surface that needs that setup and carries `env`. <WRITES> is valued in
# `env` exactly as in `args`, so a subject told where to write through a
# variable spells the path once. A `counter` belongs on a `run` surface with
# `writes`; elsewhere it is refused when the manifest is read. An input may
# record only one surface with a `counter`, or it is refused likewise.
# An `env` that sets a variable the census pins is refused when the manifest is read; one of the two owns the variable.
[surfaces.export-env]
args    = ["--json", "<WRITES>"]
writes  = "<WORK>/<input>-<surface>.json"
counter = ["<PYTHON>", "<HERE>/counts.py", "<WRITES>"]
env     = { FIXTURE_STORE = "<WORK>/fixture/store", GOLDEN_CENSUS_OUT = "<WRITES>" }
needs   = ["fixture"]

# A surface narrowed to some inputs, whatever a surface set says. A surface an
# input NAMES that also narrows itself away from that input is refused.
[surfaces.pinned-only]
args   = []
inputs = ["pinned"]

# An input pinned to a commit. golden-census clones it, and <CLONE> is the
# clone's directory. `git` and `sha` come together, and an empty string is
# neither. `expect_counts` never gates: it prints AGREES or DIFFERS beside the
# counter's numbers. It may not be an empty table, and an input none of whose
# surfaces has a `counter` may not set it.
[inputs.pinned]
git           = "https://example.invalid/some/repo"
sha           = "0000000000000000000000000000000000000000"
args          = ["<CLONE>/src"]
surfaces      = ["export-env", "pinned-only"]
expect_counts = { rows = 1 }
```

The clone is the whole repository with its history, made once into the cache directory and kept there; a large repository lands on this disk at full size. The rest of a pinned input's rules are in `references/machine.md`: where the clone lives, what a `sha` may be, and the refusals.

## Placeholders

These are the only substitutions golden-census makes. They apply in `[subject] command`, `args`, `writes`, `env` values, setup commands and counters. Anything else is passed as written.

A token that looks like a placeholder and is not defined in that place is refused when the manifest is read. The refusal names the whole list for that place. A near miss such as `<TMP>` for `<WORK>` is refused, never read as the nearest name.

| Placeholder | Expands to |
|---|---|
| `<ROOT>` | the subject root |
| `<WORK>` | the per-capture scratch directory |
| `<CLONE>` | an input's clone directory |
| `<WRITES>` | the path this surface's `writes` names, valued in `args`, in `env` and in a `counter` |
| `<PYTHON>` | the interpreter running golden-census |
| `<HERE>` | the directory the manifest sits in; in the manifest, valid only in `[subject] command`, a `[[setup]]` command and a `counter`. The census and the mutants file have a `<HERE>` of their own, each the directory of its own file; `references/census.md`, "Placeholders in a census", says where the census's is valid. |
| `<input>`, `<surface>` | the current input's and surface's names; valid inside `writes` only |

- `<HERE>` is how a project spells a file beside its manifest. An element that opens with `<HERE>` must name a file that is there, or the manifest is refused at load.
- `mutants` carries `<HERE>` onto the copy of the subject when the manifest sits inside the checkout. A manifest outside the checkout keeps its own directory. A file the copy does not carry is refused, naming both paths.
- `<REPO>`, `<TMPROOT>`, `<CWD>` and the other tokens `SKILL.md` lists under "Reading the verdict" are not placeholders in this sense. They are tokens golden-census prints in place of a path it folded; `<CLONE>` and `<PYTHON>` are both. The census chooses them, under its own `placeholder` key, whose sense is the opposite: a token written INTO a golden, not one substituted before a run. Never type one into a manifest.

## The golden directory

`compare` reads this shape. A `[DIFF]` path names one of these files.

```
<golden>/<input>/<surface>.out      stdout, normalized
<golden>/<input>/<surface>.err      stderr, normalized
<golden>/<input>/<surface>.exit     the exit code and a newline
<golden>/<input>/<surface>.<ext>    the file `writes` named, normalized
<golden>/<input>/<surface>.skip     a SKIP's reason; a declared SKIP's reason IS the golden
<golden>/<input>/surfaces.json      {surface: {argv, status, exit | reason, shares_invocation_with?}, "_counts": {...}}
```

- A given golden carries only what its manifest produced. There is no `.skip` without a `skip` surface or an input whose pinned tree could not be cloned. There is no `_counts` without a `counter`. There is no `shares_invocation_with` unless two surfaces of one input recorded the same argv.
- Read an absence as the manifest's shape, not as a golden that is missing something.
- A declared skip holds the manifest author's own sentence, the same on every machine. A failed clone records one fixed sentence and leaves its reason in the log, because the reason came from git, the network or the machine.
- A golden folder holds only what golden-census wrote. Anything else, even a `.DS_Store`, is refused if it is not text, and shows up as an `only-in-golden` or `only-in-new` row if it is.
- On an `only-in-golden` row, that surface's `.exit` and `.err` in the NEW capture say why the run stopped producing it.
- `surfaces.json` is the marker. A directory that holds at least one `<input>/surfaces.json` is a capture directory.
- Normalization happens at capture time, never at compare time. A fold change means a re-capture, and it shows as a diff against the old golden.
