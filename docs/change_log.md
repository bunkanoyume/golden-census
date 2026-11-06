# Change log

## 1.0.1 — 2026-11-06

### Fixed

- A temp root on a different file system than the subject, such as a `tmpfs` `/tmp` or a separate volume, refused every mutants run with `Invalid cross-device link`. Now mutants clones the subject with a plain `git clone`, no longer `git clone --local`. git now links the object files where it can and copies them where it cannot.
- Some command line errors printed argparse's text instead of a `REFUSED:` sentence with a `next:` line, on standard output.
- When a capture was refused because the manifest spelled a machine path in an input's arguments, the advice named a fix that could not work. It now names two that do.
- A contraband refusal listed each home path twice, once as an absolute home path and once as the running user's home directory, and counted it twice. Each occurrence is now one hit.
- When every difference was a surface the manifest no longer names, `compare` advised `capture --force`, which refuses a golden that holds those files. It now says to delete them from the golden first.

### Changed

- In `capture` and `compare`, a summary of the rows that recorded nothing from the subject has been added below the verdict.
- `probe`'s clause 4 `next:` line amended, and its last line points to the skill.
- When a `json-fields` control skips a check, its message says what the sample file is missing.
- Began revision and reorganization of the documentation to improve readability and precision. `docs/contract.md` is renamed `docs/subject-requirements.md`, and the `--help` text uses the new name.
- Skill corrected and amended. Additional content was moved from `SKILL.md` to new reference files `first-run.md` and `rebaseline.md` to better manage context usage.

## 1.0.0 — 2026-10-30

Initial release.
