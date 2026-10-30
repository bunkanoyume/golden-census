# swift-package: one pure function of a SwiftPM package, frozen

`golden-census init <dir> --template swift-package` writes
`GoldenCensusRunner.swift` beside the neutral three. The runner is a Swift
Testing test in the package's test target. It reads a job from the
environment and loads the fixtures beside it. It calls ONE pure function over
each fixture. It writes every answer as one canonical JSON document to the
path the job names. `swift test --filter GoldenCensusRunner` is the subject
command. The written file is the surface.

## 1. What the runner freezes

One function's answers to fixed inputs, keyed by fixture name. The runner
encodes them with sorted keys and pretty-prints them, so a diff names the key
that moved. The test is disabled unless `GOLDEN_CENSUS_OUT` is set:
`.enabled(if: outPath != nil)`. So an ordinary `swift test` never reaches it
and never writes anything.

Anything the function reads for itself breaks this: the clock, a random
source, a dictionary whose iteration order reaches the output. `capture
--twice` refuses it, and it calls for a census row nobody has written yet.

## 2. The five holes

| hole | what goes in it | example |
|---|---|---|
| `TEST_TARGET_DIR` | the test target's source directory, relative to the project. The hole is in the file's PATH, not its text | `Tests/MyPackageTests` |
| `MODULE` | the module the function lives in, as `@testable import` spells it | `MyPackage` |
| `FIXTURES` | the fixture files beside the runner, one quoted name per element. The brackets are already there | `"a.txt", "b.txt"` |
| `LOAD_INPUT` | the statement(s) turning the fixture at `url` into the function's input | `let text = try String(contentsOf: url, encoding: .utf8)` |
| `FUNCTION_CALL` | the call over the loaded input, whose value is `Encodable` | `MyPackage.parse(text)` |

`surface(of:)` returns `some Encodable`. A function whose answer the JSON
encoder cannot encode is a compile error at the hole, not an empty surface at
capture time. Make a result type of the package's own `Encodable` in an
extension in the test target. A tuple is not `Encodable`, so return a struct
or a dictionary instead.

## 3. How `swift test --filter` passes the environment, and the manifest lines

`swift test` runs the test process with the environment it was given. A
variable set for `swift test` is the variable the test reads through
`ProcessInfo.processInfo.environment`. So the manifest passes the out path as
`env`, and the subject command is the test tool with a filter:

```toml
[subject]
command = ["swift", "test", "-q", "--filter", "GoldenCensusRunner"]

[inputs.fixtures]
args     = []                              # the fixture list is FIXTURES inside the runner
surfaces = ["results"]

[surfaces.results]
args   = []
env    = { GOLDEN_CENSUS_OUT = "<WRITES>" }
writes = "<WORK>/results.json"
```

Put the manifest at the package's root, or spell `root` from where it sits.
`root` is the directory holding `Package.swift` (§8). It is the cwd of every
run, and it is the directory `swift test` finds the package from.

Two facts stand behind those lines. Both were measured on a scratch package.

- **`<WRITES>` is valued in `env` exactly as it is in `args`.** The path is
  spelled once, in `writes`, and the variable names it. A surface that declares
  no `writes` and spells the token anyway is still refused, and the refusal
  names the row (`docs/manifest-format.md`, the `env` key).
- **`swift test` prints timestamps, even with `-q`.** XCTest's suite banners
  (`Test Suite 'Selected tests' started at 2026-09-05 14:56:01.936.`), their
  durations and Swift Testing's own summary go to stdout. Stdout is a golden.
  `probe` reports them as clause 4 (`stdout moved between the runs at
  line 1`). `probe` folds only its own paths, never a census row. So that FAIL
  is expected here, and the census is the fix. One `regex` fold covers them:

```toml
[[input]]
name        = "the test tool's timestamps and durations"
disposition = "fold"
kind        = "regex"
pattern     = '(?P<volatile>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}|\d+\.\d{3} \(\d+\.\d{3}\) seconds|after \d+\.\d{3} seconds|Version: \d+)'
placeholder = "<TOOL-TIME>"
scope      = ["fixtures/results"]
finding     = "`swift test` prints XCTest's suite banners with wall-clock timestamps and durations, and Swift Testing's own summary with a duration and its library version; the file the runner writes carries none of them"
control     = { sample = "Test Suite 'Selected tests' started at 2026-09-05 14:56:01.936.", moved = "Test Suite 'Selected tests' started at 2026-09-05 14:57:22.104." }
```

The probe's `next:` line says to quiet the command or to swallow what moves
in a wrapper. This template has no wrapper, so the four other clauses are its
proof, and the census row above is where `swift test`'s own lines are folded.

With that row and the `path` folds of the neutral census, `capture
--twice` of the scratch package is `5 files, byte-identical`. The recorded
`.out` reads `Test Suite 'Selected tests' started at <TOOL-TIME>.`, and `.err`
is empty. `compare` is IDENTICAL. Without `-q`, a cold build's log lands on
stderr with the package's absolute path in it. The census's `<REPO>` fold
covers that path, but `-q` makes the smaller golden.

## 4. Why each line exists

- **`static let outPath = ProcessInfo.processInfo.environment["GOLDEN_CENSUS_OUT"]`**
  — the job, read once. Nil is the ordinary test run.
- **`.enabled(if: outPath != nil)`** — the trait that keeps the runner out of
  every test run that is not golden-census's. A skipped test is reported as
  `skipped`, never as a pass with no file.
- **`fixtureURL` through `#filePath`** — the fixtures sit beside the runner and
  resolve against ITS directory. So `Package.swift` needs no `resources:`
  declaration, and the list reads the same whatever directory `swift test`
  runs from. The path is fixed at compile time, which is why the runner
  belongs in the test target's source tree rather than a bundle.
- **`surface(of:) throws -> some Encodable`** — one place for the two holes
  that are the project's. Its `Encodable` bound makes an unencodable answer a
  compile error.
- **`try #require(Self.outPath)`** — the trait already proved it non-nil.
  `#require` is how a Swift Testing body says so without a force-unwrap.
- **`Dictionary(uniqueKeysWithValues:)`** — the results are keyed by fixture
  name in one document. So one surface records every fixture, and a diff names
  the fixture AND the key. Two fixtures with one name is a runtime trap here
  (duplicate keys), which is the right place for it.
- **`[.sortedKeys, .prettyPrinted, .withoutEscapingSlashes]`** — canonical
  bytes. Sorted keys make the encoding deterministic. Pretty-printing makes a
  diff a line and not one enormous row. Unescaped slashes let paths and URLs
  in the answer read as written.
- **`.write(to: out)`** — the file is the whole record. The test prints
  nothing. What `swift test` itself prints is the tool's, and the census folds
  it (§3).

## 5. Recording fixtures, as text

A runner that FREEZES a function's answers needs its inputs frozen too. Sometimes
the inputs are themselves the output of something non-deterministic or
expensive: a recognizer, a network response, a parse of a large document. Then
the pattern is a second test in the same file, disabled the same way on a
second variable:

    GOLDEN_CENSUS_RECORD=<dir>   run the real producer over the raw inputs and
                           write each result beside the runner as a fixture
                           file; run ONCE, by hand; commit the files.

The recording test stamps each fixture with the producer's version where the
producer has one. So the census can read the engine the INPUTS were recorded
at out of the files (a `state` row with a one-line command). A re-recording is
visible as a new version in the capture log. A re-recording is
a re-baseline of every golden. Attribute it as such, and never do it silently.
The template ships the surface test only. What a recorder does is the
project's, and a hole cannot describe it.

## 6. The `dest` hole

`init` writes this file to the literal directory
`<<HOLE:TEST_TARGET_DIR>>/GoldenCensusRunner.swift`, because a scaffold that
asked the question first could not be run from one line. It prints this beside
the hole: `that file was written to the literal <<HOLE:TEST_TARGET_DIR>>
directory, so MOVE it once you have filled the hole`. Fill `TEST_TARGET_DIR`,
then MOVE the file into the test target's source directory.

## 7. Written against

Swift 6.3.3, `swift-tools-version: 6.3`, Swift Testing (the `Testing` module),
macOS 26.6.2. Measured in a scratch package made by `swift package init --type
library`: `GOLDEN_CENSUS_OUT=<file> swift test --filter GoldenCensusRunner`
writes the file. It takes `real 6.34` s on a cold build and `real 0.52` s
warm. The same command with `GOLDEN_CENSUS_OUT` unset reports the test
`skipped` and writes nothing.

`URL(filePath:)`, `appending(path:)` and `deletingLastPathComponent()` are
unmarked in the SDK 26.5 availability data, checked with an availability tool
(for example `apicheck lookup`). The first two need macOS 13 / iOS 16, which
is the runner's floor. `appendingPathComponent` is the
deprecated spelling, and the runner does not use it.

## 8. Traps

- **`--filter GoldenCensusRunner` that matches nothing still exits 0.** Causes
  are a renamed struct, a runner in the wrong target, and a file never moved
  out of the `<<HOLE:TEST_TARGET_DIR>>` directory. In each case `swift test`
  reports `Executed 0 tests` and succeeds. `writes` catches it: a surface
  whose file was not written records no `.json`, and `compare` reports the
  row.
- **A cold build is not a capture.** The first run after a clean or a
  toolchain change builds the package. `swift test` prints the build log to
  stderr then, with the package path in it. The census's `<REPO>` fold covers
  the path. `-q` keeps the log out of the golden on the runs that follow.
- **`#filePath` is the path at COMPILE time.** Suppose you move the test target
  after the build, or build in one tree and run in another. The runner then
  points at fixtures that are not there. `String(contentsOf:)` throws, and the
  test fails naming the URL.
- **`@testable import` needs a debug build.** `swift test` builds debug by
  default. A `-c release` run cannot see internal symbols, and the runner
  will not compile.
- **The package is the subject root.** `root` in the manifest is the directory
  holding `Package.swift`, because `swift test` finds the package from its cwd
  and nowhere else.
