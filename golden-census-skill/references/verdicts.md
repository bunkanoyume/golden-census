# Every line the tool prints

Open this file when a line in the output is not in the table under "Reading the verdict" in `SKILL.md`, or when a `probe` block is red. That table covers `IDENTICAL`, a permitted movement, `[ALLOWED]`, the three `[DIFF]` shapes, `REFUSED:`, `next:`, the tally, the two `[SKIP]` shapes met most, the mutants verdict and the process-group line. This file covers the rest.

Each quoted line was printed by a run on the shipped example, or on a copy of it with one planted change, or on a scratch subject. A path of the machine inside a quoted line is shown as `<path>`. A row's or a control's name is printed as Python spells it: in double quotes when the name holds an apostrophe, in single quotes otherwise. A row says so where the line is quoted from the program's source instead, because no run made for this file printed it.

The exit codes are in `SKILL.md`, under "Reading the verdict".

## The capture log

A `capture`, a `compare` without `--against` and a `mutants` run each print a capture log. These lines are in it.

| Line | What it means | What to do |
|---|---|---|
| `capture -> <TMPROOT>/…/before  [new directory]` | Where the capture goes, and what stood there. | Nothing. |
| `  subject: wordstats at <REPO>` | The subject's name and root. | Nothing. |
| `  subject TMPDIR: 51 characters (pinned at 51)` | The width of the subject's own temp root. | Nothing. |
| `    [OK] the subject's tree is a git checkout: b0effa2 base` | A precondition of your census held. The text after the colon is what git printed. | Nothing. |
| `    <PYTHON> --version -> Python 3.14.7` | The census's `state` rows. They are never a golden. | Quote it when you attribute a movement to a toolchain change. |
| `    results: exit 0` | One row ran and exited 0. | A non-zero exit is a recorded fact, not a refusal. |
| `  contraband scan: 5 files written, 5 read, 0 hit(s)` | golden-census read back every file it wrote and looked for machine paths. | Quote it. A file the scan could not open is a refusal, not a clean file. |
| `  contraband positive control: PASS — the scan found all 11 absolute paths it planted in a scratch file (first: line 2 of <TMPROOT>/golden-census-contraband-…/planted.out)` | The scan found the paths planted for it. The count moves with the machine's home roots. | Quote it beside every clean capture. |
| `  capture complete` | The capture was moved into place. | Nothing. |
| `  --twice: 5 files, byte-identical` | The two captures agree. | The manifest is complete enough to have goldens. |
| `REFUSED: two captures of one subject differ: fixtures/results.json line 3`, then `first:` and `second:` lines quoting the line from each capture | Under `--twice`, the row did not reproduce. Something around the subject moves and no census row folds or pins it. Exit 2, and `--out` is left as it was. | Add the census row that pins or folds what moved (`references/census.md`), then capture again; the `census state` block of `census --manifest <MANIFEST>` usually names it. Quoted from the program's source. |
| `REFUSED: two captures of one subject differ: fixtures/results.json exists in only one of them.` | A row was recorded in one capture and not the other. | Something around the subject decides whether the row is recorded; read the `census state` block of `census --manifest <MANIFEST>`. Quoted from the program's source. |
| `REFUSED: the capture would commit an absolute path.`, under a `fixtures/results.err:1 an absolute home path: <the path>` hit | The contraband scan found a machine path in what the subject wrote. | The subject printed a machine fact, which clause 4 forbids. Fix the subject where you can. Otherwise add a census `regex` fold that names the directory; a `path` fold folds only the four directories golden-census knows. |
| `  [SKIP]  fixtures/never: needs a network this machine lacks` | A surface declared unrunnable by a `skip` row. Its reason IS its golden. | It is not a pass and not a refusal. Report it by name and reason. |
| `  [SKIP]  pinned: git clone exited 128: fatal: …` | A whole input recorded as nothing, because its pinned tree could not be cloned. | Every surface of that input is missing. Never report the run as clean. Name the input and quote the reason from the log. |
| `  [SKIP]  pinned/show: SKIP — the pinned tree is unavailable: …` | The same failure, said again on each surface of the input. | The recorded `.skip` file and `surfaces.json` hold one fixed sentence. The reason is in the log only, because it is a fact about the machine. |
| `      records nothing: both streams are empty and no file is written, so a comparison of this row passes against any capture that also records nothing` | Under a row: that run put no byte anywhere. | Not a refusal. Decide whether the surface is meant to be silent. A golden of nothing stays green when the subject stops producing the surface. |
| `      counter not run: the run wrote no file for it to count, so no counts are recorded for this row; read the row's .exit and .err for why` | Under a row: its `writes` file was never written, so its `counter` was not started. | Read the row's `.exit` and `.err` for why. A row meant to write the file that did not is the finding. |
| `      counts {'lines': 1}` | The counter printed this JSON object. | Compare it with `expect_counts` if the input sets one. `AGREES` or `DIFFERS` never gates. |
| `    every surface of this input exits non-zero — the rows above record a subject that is failing` | After an input's rows: every surface failed. | Not a refusal. A whole input failing is usually the fixture or a `[[setup]]`, not the subject. |
| `  a directory golden-census made could not be removed: <path> — delete it by hand and name it in your report` | A directory golden-census made was still on disk when the command ended. A file the subject left in it may not be removable, or the temp root may be read-only. | The verdict and the exit code stand. Delete the directory by hand and name it in your report. This line is quoted from the program's source, not from a run. |
| `clone: <url> @ <full sha>, clean` | A pinned input's clone was used and git lists nothing in it. | Nothing. |
| `  clone: git ignores 1 path in it that is not the pinned content: 'a.log'; delete the clone's folder to start clean` | A kept clone holds a file git ignores. It is not the pinned content. | The line changes no verdict and no exit code. Delete the clone's folder to start clean. |

## The compare summary

| Line | What it means | What to do |
|---|---|---|
| `  unused: [[movements]] row 'fixtures/nothing.out' permits a movement that did not happen` | A `[[movements]]` or `--allow-diff` row matched no moved row, so it is stale. The line names the table the row is in, `[[movements]]` or `--allow-diff`. It comes before the verdict, and the verdict does not change. | Delete the row, or correct its path if the movement you meant to permit is a different row. |
| `  [SKIP]    1 row(s) are a skip on both sides, so nothing ran to compare: fixtures/never`, with a `[DIFF]` row for the same surface | A declared skip's reason IS its golden, so a reason that changed shows as a `[DIFF]` as well as on this line. | Read the new reason, and attribute it or fix it. |

## The `next:` line

`next:` stands under every `REFUSED:` and under some red rows. It is one sentence saying what to do. Do that, or say in your report why you did not.

- A `probe` clause's row carries one. So does the verdict row of every census pin and fold.
- The `[FAIL]  !` row of a control that raised never carries one, and most self-check arms do not.
- A red row without a `next:` is not malformed. Its detail line is everything it has.

## The census controls

A command that makes a golden or a verdict, `capture`, `compare` without `--against` and `mutants`, prints the census controls first. `census` prints them as a block. `probe` prints none.

| Line | What it means | What to do |
|---|---|---|
| `  [PASS]  census fold "the subject root's absolute path": …` | The control fired and the fold held. | Nothing. |
| `  [SKIP]  <name>` and an indented reason | An arm or a control that had nothing to run on; the indented line is the reason. For example: `no --manifest was given, so there is no capture to fault in the window this arm guards. Nothing was made and nothing is claimed.` | It is not a pass. Say which control and why. |
| `  [FAIL]  census pin 'terminal width': fixtures/results MOVES when COLUMNS is varied from '80' to '40', and is identical twice under the pin` with `actual: the two runs under the pin agree, and the run with COLUMNS='40' records the same as they do. UNPROVEN: …` | The census claims the pin moves that surface. Run alone, the row does not depend on it. | The fix is in the census: "When a control of YOUR census is red" in `SKILL.md`. When the detail adds that the run under the varied value does not differ before the census's folds, what the variable changed never reaches the golden. A fold that replaces it is one way this happens. |
| `  [FAIL]  census pin 'terminal width': …` with `actual: the two runs under the pin differ, and the run with COLUMNS='40' differs from the first of them. …` | Two runs of the row, both under the pin, differ after the folds. It is never `UNPROVEN`. | Find what differs between two runs of the row. Pin or fold it in the census, or point the control at a steady surface. Until the two runs agree, the control cannot say whether the pin matters. |
| `  [FAIL]  census fold 'case word': the fold fires on fixtures/results and folds the TOKEN, not the line: …` with `actual: normalized identical=False, unnormalized differs=True, one byte outside the group reported=True, …` | The fold's `pattern` does not match its `control.sample` or its `control.moved` (the detail then ends with `this row's own pattern … replaced nothing`, even when another fold folds the token), or it folded a byte outside the volatile group. | Match the pattern to the sample, and narrow the `(?P<volatile>…)` group. Until then the fold does nothing or blinds the comparator. |
| `  M/N passed, K arm(s) SKIPPED (disclosed, never a pass)`, with M less than N; in front of a command the line reads `M/N census controls passed` | At least one control failed. | `census` exits 1. A command that makes a golden or a verdict refuses next. |
| ``REFUSED: golden-census does not run `capture` when a control of this manifest's census did not pass: the rows above are every control that ran, and nothing of the command below them was started.`` | A red control of YOUR census stopped the command. | Run `golden-census census --manifest <MANIFEST>`. The block and the state under it usually name the cause. The fix is in the census: "When a control of YOUR census is red" in `SKILL.md`. |
| `  0/0 passed, REFUSED after row 0`, then `REFUSED: could not make a directory of exactly 300 characters under '<path>', a name of 284 characters: File name too long` | The census's fixed-width pin, `<FIXED-WIDTH-DIR:N>`, asks for a name longer than the file system takes. The words after the last colon are the operating system's answer. At the neutral census's 51 no root reaches this bound. | Lower `N`, as the `next:` line says. A shorter temp root gives a longer name and does not help. |
| `[FAIL]  !` | A self-test or control raised or refused instead of reporting a verdict. The label says whether the ones after it still ran. | Report it, quoting the row whole. When the label names one of golden-census's own self-tests, it is a golden-census defect. This row is quoted from the program's source, not from a run. |

## Refusals

A `REFUSED:` sentence names what was found and ends in a `next:` line that says what to do. Do what it says. Three refusals point further: one about `--out` has its rules in `references/commands.md`; one naming `TMPDIR`, `HOME` or a cache directory has them in `references/machine.md`; one about standard output closing has its rule in `references/commands.md`.

## Blocks under a refusal

A refusal over a command that ran, or was about to run, carries a block under its `next:` line. It shows the command and the environment the command was given.

```
  about to run: nosuchprogram_xyz <TMPROOT>/golden-census-nvx0og8i/fixtures-results.json
  the environment it was built with (4 variable(s)):
    GOLDEN_CENSUS_CHILD=1
    HOME=<passed through, 18 characters>
    PATH=<passed through, 448 characters>
    TMPDIR=<ENGINE-TMPDIR>
```

- `ran:` opens the block when the command ran and ended. `about to run:` opens it when the command was never started. The line is `  ran: <PYTHON> <REPO>/examples/python-function/runner.py <TMPROOT>/golden-census-ejs4qom4/fixtures-results.json` or `  about to run: …`.
- For a refusal over a subject row, read the block against the manifest. The argv is `[subject] command`, plus the input's `args`, plus the surface's `args`. A matrix row's own `args` replace the surface's. The variables are the census's pins and passthrough; a passthrough variable prints as `NAME=<passed through, N characters>` and never its value.
- For a `[[setup]]` step, a `counter` or a precondition, the argv is its own. Run that command by hand.

## The mutants table

`mutants` prints the census controls, then a table of mutant against check. The counts in this block are the example's own. Quote the counts you saw.

```
MUTANTS  mutants.toml  (2 mutants, 2 checks)
  null mutant: comparator SILENT, label SILENT

  mutant                                  comparator  label
  the hyphen rule the counts carry        FIRED       SILENT
  a constant no recorded surface carries  SILENT      FIRED

  2/2 mutants caught by every check they expect
```

| Line | What it means | What to do |
|---|---|---|
| `FIRED` | That check caught that mutant. For the comparator it means a differing row. | Expected: good. Unexpected, marked `(label: unexpected)`: the net is wider than the table said. Worth reading, not failing. |
| `SILENT` | That check did not catch that mutant. For the comparator it means IDENTICAL, rows the manifest's `[[movements]]` permit included. | A FAIL only when the mutant's `expect` names the check, or when no check fired at all. |
| `(comparator: expected, SILENT)` | `expect` named a check that stayed silent. | The mutant is a FAIL, and the run exits 1: `1/2 mutants caught by every check they expect`, then `FAIL  a constant no recorded surface carries — comparator expected to fire and stayed SILENT (IDENTICAL)`. Widen the check so it sees the change. Remove the mutant only when it no longer describes a change worth catching, and say so. |
| `(no check fired)` | Nothing caught this mutant. | A hole in the net, and a fault of the checks, never of the subject. |
| `REFUSED`, with `comparator: the capture refused: …` and `ran: …` under the row | The comparator's capture of that mutant's copy refused, or its comparison did over a moved row that two `[[movements]]` rows name. No comparison was made. | A FAIL, never a catch. Run `compare` on a copy of the subject with that mutant applied. A refusal the mutant causes comes back there whole. One that does not came from the machine during this run. Act on it before counting the mutant. |
| ``REFUSED: mutant 'stdout gets a raw byte': `find` occurs 0 times in examples/python-function/runner.py, and a mutant is one edit to one place. …`` | The code the mutant names has moved. This is a refusal of the run, at exit 2, before any clone is made. | Re-plant the mutant or drop it. |
| `1/1 mutants caught by every check they expect`, after `--only` | Only the named mutant ran. | The null mutant runs either way. |

## The `probe` block

`probe` prints one row per clause of the contract, each labeled `[PASS]` or `[FAIL]`, then `N/5 passed`. It exits 0 when all five pass, 1 when a clause failed, 2 when it refused. A `[FAIL]` row states the fact that broke the clause on its `actual:` line, and what to change on a `next:` line. The five clauses are in `docs/contract.md` in a checkout. When a command cannot be plugged in yet, quote the clause number and its `actual:` line: they are the finding. The rows:

| Row | Green means | Red means, and where to look |
|---|---|---|
| `1  takes an output path and writes one file there` | Both runs wrote the file. The detail quotes each size. | The command chose its own path, or wrote nothing: `actual: run 1 wrote nothing, run 2 wrote nothing`. Put `<WRITES>` where the path goes, or name the variable with `--writes-env`. |
| `2  is deterministic: two runs write byte-identical files` | The two files are byte-identical. | `actual: they differ at line 1`, then `first:` and `second:` lines quoting the line from each run. For files that are not UTF-8 text the detail reads `they differ at byte N` with both bytes. Something reads the clock, a random source, the network or an unordered collection. When a run wrote no file, the detail reads `not judged`, and clause 1 says why. |
| `3  exits 0 on success and non-zero otherwise` | The detail quotes both exit codes. A command that fails and says so keeps this clause: `actual: exit codes [2, 2]`. | A run exited 0 and wrote no file. The command needs its own check that the file is there. This is the trap of a tool that prints `SUCCEEDED` when its filter matched nothing. |
| `4  prints nothing that moves: stdout and stderr identical across the runs, and no machine fact in either stream or in the written file` | The streams are identical across the runs, and neither they nor the file carry a machine fact. | Two halves in one row; the detail says which. A hit reads `run 1 the written file:1 an absolute home path: <the path>`. The scan reads three texts per run: stdout, stderr and the written file. A hit on the file is bytes your command put on disk, which is what a golden commits. A command piped into `<WRITES>` has its whole output there. A file that is not UTF-8 text is not scanned, and the detail says so: disclosed, never a pass. |
| `5  runs under the census's environment: reads no variable the built environment did not pass` | The detail lists every variable actually passed. | `run 1 the written file carries the value of $ZZ_CANARY, which the built environment did not pass`. The command found the variable another way. Add a census row for it, a `pin` or a `passthrough` entry with the reason, or stop the command reading it. |

Clause 4 in a red block, printed on a misspelled script: `actual: run 1 stderr:1 the subject root's absolute path: <path>; run 2 stderr:1 the subject root's absolute path: <path>`. Clause 4's `next:` line is one sentence for both halves. Its first words, `Quiet the command, or make the wrapper swallow what moves`, answer streams that differ between the runs. The rest, that a census `regex` fold is not the fix, answers a machine fact: `probe` applies no fold to the candidate's output (`references/commands.md`, `--census`), and the fix is the program's. A fold still gets a capture past streams that move; that is the `swift-package` case (`references/templates.md`), and the probe stays red.

Clause 5 has two exceptions, both stated in the row. It ignores values shorter than 8 characters, because short ones coincide with ordinary output. It ignores any value contained in a path the probe handed the command: the working directory, the work directory, the fixed-width `TMPDIR` or either run's output path. The test is containment, not equality.

The block's banner, `PROBE  <PYTHON> runner.py <WRITES>`, folds every absolute directory golden-census knows to its token. A block pasted into a hand-back carries no home directory when the command is spelled with those paths.

- The folds are `<PYTHON>`, then the census's `path` rows: `root` is the current directory, `work` the probe's work directory, `fixed-width-dir` its `TMPDIR`, and `clone` nothing. With no `--census` they are `<CWD>`, `<TMPROOT>` and `<TMPDIR>`.
- A path spelled another way is printed as typed. A path that begins with a folded one and goes on past a `.` is printed as the token followed by the rest, such as `<PYTHON>.12` or `<CWD>.bak/y`. Fold it yourself before pasting, or spell it relative.
- An absolute path in a clause 4 detail is the finding.

## The machine paths in header lines

Every command folds the machine paths in the lines it prints about the machine the same way. A header pasted into a hand-back reads `<REPO>` and `<TMPROOT>`, never a home directory. The lines are:

- `capture ->`, `subject: … at`, and `--twice: a second capture into …`;
- the contraband control's planted file;
- `census …` and `MUTANTS …`;
- the `golden:` and `new:` lines of `compare`;
- the `census state` block's command lines;
- the `[OK]` lines of the `command` and `git-checkout` preconditions.

- A path in what git printed that lies under no `path` row's directory is printed as git wrote it. Examples are the main repository of a linked worktree kept outside the temp root, and a path in a commit's subject. Fold it yourself before pasting.
- Any other absolute path in a header line is a bug in golden-census. One inside a recorded golden is what the contraband scan refuses.
- A home path counts as contraband where a path can start. `src/home/x` is none. `-I/home/x` is one. A directory folds only where its name ends, so `<root>-old` is refused rather than recorded as `<REPO>-old`.
