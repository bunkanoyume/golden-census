# Re-baseline: a new golden after a change

Open this file when the manifest, the census or the runner changes, when a `[DIFF]` is the change you intended, or when a capture will not reproduce. Every procedure here ends the same way: a scratch capture compared against the old golden, so you can quote exactly which rows move and why, then `capture --force` over the committed golden. Never re-baseline to make a comparison pass; a re-baseline makes the new bytes the golden, and `SKILL.md`, "Which permit, when", says when a `[[movements]]` row or `--allow-diff` is the right tool instead.

## What each kind of change should move

Decide this before step 3 below, and hold the comparison to it.

| The change | What `compare --against` the scratch capture should report |
|---|---|
| a new surface | one `only-in-new` row for each input that runs it, and nothing else |
| a surface removed from the manifest | its `only-in-golden` rows, and nothing else |
| a new or renamed input | the rows of that input, `only-in-new` for the new name and `only-in-golden` for the old |
| a changed `[subject] command` or runner | the rows you expect that change to touch; every other row `IDENTICAL` |
| an intended change of output | the rows you meant to move, and no others |
| a census row added, changed or removed | nothing, unless the row folds, or folded, a token a golden carried; then exactly the rows that carried it |

A row that moved and is not in your expectation is a finding, not a reason to widen the expectation. Attribute it or fix it before the golden is replaced.

## The four steps

1. Capture the new set into a scratch directory: `golden-census capture --manifest <MANIFEST> --out <SCRATCH> --twice`.
2. Compare it with the old golden: `golden-census compare --manifest <MANIFEST> --golden <GOLDEN> --against <SCRATCH>`.
3. Check that it reports exactly the rows the table above says, and no others. Quote its row count: that count is the new golden's positive control.
4. Replace the golden: `golden-census capture --manifest <MANIFEST> --out <GOLDEN> --force`. Commit the golden with the manifest row, the census row or the code change that moved it, in the same commit. Then run `golden-census mutants --manifest <MANIFEST> --mutants <MUTANTS>` again: the mutants read the committed tree, and its verdict is part of the hand-back.

## When you add a surface

First `compare` and get `IDENTICAL`, so that what follows absorbs the new row and nothing else. Write the `[surfaces.<name>]` row. Add it to the input that runs it. Then the four steps, expecting one `only-in-new` row per input. A surface with no row is a surface nobody will notice moving. `references/manifest.md` has the rows to copy.

## When a capture will not reproduce

`capture --twice` names the row and the first differing line. That line is a census row nobody has written. Pin the variable or fold the token, and give the row the control that proves it matters. A `state` row only records, for attribution later; it makes nothing reproduce. `references/census.md` has the rows to copy. Then the four steps: a pin should move nothing, and a new fold moves exactly the rows that carried the token it folds.
