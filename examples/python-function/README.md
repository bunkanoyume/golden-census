# wordstats — the python-function template, filled in and frozen

A worked example of the whole loop on the smallest subject there is: one pure
function.

- `wordstats/tokenize.py` counts the words of a text.
- `runner.py` is the file `golden-census init <dir> --template python-function`
  writes, with its three holes filled.
- `manifest.toml`, `census.toml` and `mutants.toml` are the neutral three with
  their fourteen holes filled. In `mutants.toml` alone, the second
  `[checks.<name>]` table and the second `[[mutant]]` row are uncommented.
  That is why there are two of each.
- `golden/` is committed.

The template this fills in has its own README, which explains the runner and the three holes: [`templates/python-function/README.md`](../../templates/python-function/README.md).

## The ten commands, in order

Every command runs from THIS directory. The two `export` lines make that true.
A reader on another machine changes the first.

```
export PY=python3   # must be Python 3.11 or newer — name another interpreter here if this one is older
export PYTHONPATH=../..               # `-m golden_census` from a subdirectory of the checkout

$PY -m golden_census --version
$PY -m golden_census probe -- $PY runner.py '<WRITES>'
$PY -m golden_census census --manifest manifest.toml
$PY -m golden_census capture --manifest manifest.toml --out "${TMPDIR:-/tmp}/wordstats-capture"
$PY -m golden_census capture --manifest manifest.toml --out "${TMPDIR:-/tmp}/wordstats-twice" --twice
$PY -m golden_census compare --manifest manifest.toml --golden golden
$PY -m golden_census compare --manifest manifest.toml --golden golden --against "${TMPDIR:-/tmp}/wordstats-capture"
$PY -m golden_census mutants --manifest manifest.toml --mutants mutants.toml
$PY -m golden_census init "${TMPDIR:-/tmp}/wordstats-scaffold" --template python-function
$PY -m golden_census --selfcheck --manifest manifest.toml
```

The table below gives the line each command prints. It is the verdict, not a
block of controls.

Commands 4, 5, 6 and 8 run THIS census's own controls first. Each prints their
tally before its own log: one line, plus any disclosed `[SKIP]`. Here the
tally is `3/3 census controls passed`: the pin and the two folds. Each then
prints, under its header, `census note: no \`path\` fold names clone,
fixed-width-dir. …`: this
census folds no clone directory and no fixed-width temp directory, because
nothing here pins an input or prints a temp path. A capture that leaked either
would be refused, and the refusal names the row to add.

Command 3 prints the same controls as a whole block, because that block is what
`census` was asked for.

Commands 1, 2, 7 and 9 run nothing first.

- `--version` starts nothing.
- `compare --against` reads two recorded directories and starts no subject.
- `probe` and `init` are both asked before a census exists. Command 2's `5/5
  passed` is the five clauses of `probe`'s own contract and nothing else.

Command 9 prints two hole lines. The first counts the neutral three's fourteen
holes. The second counts the template's holes, and row 9 quotes it.

Command 10 is golden-census's OWN arms, asked for by name. Its tally is the
only thing it has to print. Row 10's `N` and `K` are this install's own. They
move with golden-census's version and with the machine. Run the command for the
numbers.

| # | command | the line |
|---|---|---|
| 1 | `--version` | `golden-census 1.0.0` |
| 2 | `probe` | `  5/5 passed` |
| 3 | `census` | `  3/3 passed`, then `census <REPO>/examples/python-function/census.toml` |
| 4 | `capture` | `  capture complete` |
| 5 | `capture --twice` | `  --twice: 5 files, byte-identical` |
| 6 | `compare` | `  IDENTICAL` |
| 7 | `compare --against` | `  IDENTICAL` |
| 8 | `mutants` | `  2/2 mutants caught by every check they expect` |
| 9 | `init` | `  3 hole(s) to fill; each is written as <<HOLE:NAME>> in the file named under it:` |
| 10 | `--selfcheck --manifest` | `  N/N passed, K arm(s) SKIPPED (disclosed, never a pass)` |

Commands 6 and 7 are the same verdict from two places. Command 6 runs the
subject again. Command 7 compares a capture already on disk and runs nothing.
Command 7 is the one an agent hands back, because it needs no working subject.

## What is frozen

`summarize` returns the token count, the number of distinct words, and the
words ranked by `(-count, word)`. Two fixtures reach one JSON document under
two keys, so a diff names the fixture as well as the key. Nothing here reads
the clock, the filesystem or a random source. `capture --twice` checks that,
and clause 2 of `docs/contract.md` is what it checks it against.

## The two mutants, and why there are two

| mutant | what it edits | the check that catches it |
|---|---|---|
| the hyphen rule the counts carry | `HYPHEN_JOINS = True` → `False` | `comparator` — the counts of `fixtures/hyphens.txt` move, and `fixtures/plain.txt` does not |
| a constant no recorded surface carries | `LABEL = "wordstats/1"` → `"wordstats/2"` | `label` — a `command` check running `label_check.py` |

The second exists because the first proves only that the comparator can see
what the subject WRITES. `LABEL` reaches no surface, so the comparator is blind
to it. A net with one hole in it and no second check reads as a pass. The two
checks catch DIFFERENT mutants. That is the whole point of the table.

## Traps

- **`root` is `../..`, the repository top, not this directory.** `mutants`
  copies the subject with `git clone --local`. That command refuses a
  subdirectory of a repository. A nested `.git` here would make these files
  untrackable. So the subject is the checkout. A relative path in the manifest
  or the mutants file is relative to the repository top. That covers each
  mutant's `file` and the `label` check's command. `command` is the exception,
  and it is the reason `<HERE>` exists. The runner lives beside this manifest,
  not at the repository top. So `command` spells `<HERE>/runner.py`, this
  file's own directory. It says where the runner is, not where the run starts.
- **`mutants` reads the COMMITTED example.** `git clone --local` copies HEAD,
  not the working tree. An uncommitted edit that moves the output leaves the
  null mutant SILENT, and `mutants` says nothing about the edit. Commit first.
- **The golden is committed, and re-baselining is a decision.** The command
  `$PY -m golden_census capture --manifest manifest.toml --out golden --force`
  overwrites it. Nothing here runs that on its own.
- **`$TMPDIR` must be at most 49 characters.** The census pins the subject's
  own `TMPDIR` to a fresh directory of exactly 51 characters. A directory made
  under a root needs the root, a separator and a name. So the arithmetic is the
  census's, not the platform's. A wider root is a refusal, not a silent skip.
  On macOS the refusal's `next:` line says to run the same command with
  `TMPDIR=$(getconf DARWIN_USER_TEMP_DIR)`, a root that fits.
