# swift-xcodebuild: one pure function of an Xcode app or framework, frozen

`golden-census init <dir> --template swift-xcodebuild` writes two files beside
the neutral three.

- `GoldenCensusRunner.swift` is the same Swift Testing runner the swift-package
  template ships, byte for byte. `--selftest` asserts it.
- `golden-census/wrapper.py` is the subject command.

A Swift app has no command line, and its pure functions live behind a build.
So the runner is a test in the app's own test target. It reads a job from the
environment and loads the fixtures beside it. It calls ONE pure function and
writes canonical JSON to the path the job names. `xcodebuild test
-only-testing:` is the subprocess. The written file is the surface. The
wrapper makes that subprocess quiet, single, entitled and honest.

## 1. What the runner freezes

One function's answers to fixed inputs, keyed by fixture name. The runner
sorts the keys, pretty-prints, and leaves slashes unescaped, so a diff names
the key that moved. Nothing the app prints is a golden. A build log is all
paths and timings. So the wrapper prints nothing on success, and the surface's
`writes` is the only record. The test is disabled unless `GOLDEN_CENSUS_OUT`
is set, so an ordinary test run never reaches it.

## 2. The five holes

| hole | what goes in it | example |
|---|---|---|
| `TEST_TARGET_DIR` | the test target's source directory, relative to the project. The hole is in the file's PATH, not its text | `ExampleTests` |
| `MODULE` | the module the function lives in, as `@testable import` spells it. It is the app or framework target | `Example` |
| `FIXTURES` | the fixture files beside the runner, one quoted name per element. The brackets are already there | `"page-1.json", "page-2.json"` |
| `LOAD_INPUT` | the statement(s) turning the fixture at `url` into the function's input | `let page = try JSONDecoder().decode(Page.self, from: Data(contentsOf: url))` |
| `FUNCTION_CALL` | the call over the loaded input, whose value is `Encodable` | `Report.build(page: page, options: Options())` |

The wrapper spells no hole. Every fact about the project is an ARGUMENT on the
manifest's `command` line (§3). So a renamed scheme is a change to the
manifest, never an edit to a file the template owns.

The function may take inputs beyond the fixture: a settings object, a lookup
table, a locale. FIX them in `FUNCTION_CALL`, with default settings or a
lookup that answers nil. A process-global input such as the user's locale
makes the golden a golden of the machine.

## 3. The wrapper's arguments, and the manifest lines

```
wrapper.py --project P --scheme S --test ID --entitlements E [--destination D] <root> <out>
wrapper.py --project P --scheme S --test ID --entitlements E [--destination D] <root> --version
```

| argument | what it is | default |
|---|---|---|
| `--project` | the `.xcodeproj`, relative to `<root>` | required |
| `--scheme` | the scheme that builds the test target | required |
| `--test` | the `-only-testing:` id, `<TestTarget>/<Suite>` — `ExampleTests/GoldenCensusRunner` | required |
| `--entitlements` | the app's own entitlements plist, relative to `<root>` | required |
| `--destination` | the `xcodebuild` destination | `platform=macOS,arch=arm64` |
| `<root>` | the subject root, the directory the project sits in | positional |
| `<out>` | the file the test writes | positional, or `--version` instead |

The manifest names the wrapper and the four facts, with `--destination` as an optional fifth that defaults to `platform=macOS,arch=arm64`. It spells `<ROOT>` itself
as the wrapper's last argument. Per surface, `<WRITES>` is the out path:

```toml
[subject]
command = ["<PYTHON>", "<HERE>/golden-census/wrapper.py",
           "--project", "Example.xcodeproj", "--scheme", "Example",
           "--test", "ExampleTests/GoldenCensusRunner",
           "--entitlements", "Example/Example.entitlements",
           "<ROOT>"]
version = ["--version"]                    # `xcodebuild -version`, one line, in the capture log

[inputs.fixtures]
args     = []                              # the fixture list is FIXTURES inside the runner
surfaces = ["results"]

[surfaces.results]
args   = ["<WRITES>"]
writes = "<WORK>/results.json"
```

`init` wrote the wrapper to `golden-census/wrapper.py`, under the directory you
gave it. The manifest sits in that directory. A relative element of `command`
resolves under `root`, so name the wrapper by `<HERE>`, the directory the
manifest sits in. While the manifest stays where `init` wrote it, the element
is `<HERE>/golden-census/wrapper.py`. The element `<HERE>/wrapper.py` is for a
manifest and a wrapper that sit in one directory. In the directory `init`
wrote, `<HERE>/wrapper.py` is refused: `[subject] command names
…/wrapper.py, which does not exist`. `<HERE>` names the wrapper wherever the
manifest is: inside the app's repository or in another one.

`mutants` clones the subject. When the manifest sits inside the app's
repository, `mutants` carries `<HERE>` onto the clone. So the wrapper every
check executes is the clone's. A manifest in another repository keeps its own
directory, which is the only place its wrapper is.

`--destination` is omitted when the default is the answer. A project that
builds for another destination spells it.

## 4. Why each step of the wrapper exists

- **argparse, and `<out>` XOR `--version`** — the four facts, the optional destination and the
  destination are arguments, so the manifest is the whole description of the
  subject. Giving both `<out>` and `--version`, or neither, is one refusal with
  a `next:` line and exit 2.
- **`--project` checked before anything runs; `--entitlements` before a
  build** — a missing project is a refusal naming the argument, before
  `--version` or a build starts. `--version` needs the project only, so it runs
  `xcodebuild -version` before `--entitlements` is checked. A missing plist is
  a refusal naming the argument, before a half-started build. The plist is what
  the test host is built against, and with none to copy there is nothing
  honest to run.
- **`cache_base()` from `getconf DARWIN_USER_TEMP_DIR`** — the derived-data
  cache cannot live under the subject's `$TMPDIR`. The census pins that to a
  fresh fixed-width directory, and golden-census deletes it after every
  capture. A cache there would be a full build every time. The per-user temp
  root is the same directory whatever `$TMPDIR` says.
- **`derived_data(root, scheme)` — `golden-census-dd/<scheme>/<sha256(root)[:16]>/dd`**
  — one store per subject root, so the worktree and every `mutants` clone build
  into their own. The scheme is a name, never a path: a value holding a separator, or `.` or `..`, is refused before the cache is touched. `root.txt` beside each records which root built it. The next
  run prunes entries whose root has gone, so a run of mutants cannot leave a
  build tree per clone behind. A warm cache makes a capture a test run rather
  than a rebuild.
- **`test_host_entitlements()`** — the test host is sandboxed. An app whose
  entitlements carry `com.apple.security.app-sandbox` runs its test bundle
  inside the app, and that process cannot write golden-census's out file
  (`NSCocoaErrorDomain 513 … Operation not permitted`). The wrapper reads the
  project's own plist fresh every run. It adds
  `com.apple.security.temporary-exception.files.absolute-path.read-write`
  with the value `/`, the whole file system,
  writes the result into the cache, and passes it as `CODE_SIGN_ENTITLEMENTS=`. Every product built into that cache carries the exception until the cache is pruned, and while it does, the sandbox no longer restricts the test host's file access; the exception is what lets the test bundle write golden-census's out file.
  The file is derived, never a committed copy, so it cannot drift from the
  project's. The sandbox stays on for everything but file access. `CODE_SIGN_ENTITLEMENTS=` with an empty
  value is silently ignored, which is why the wrapper always passes the file.
- **`-parallel-testing-enabled NO`** — a scheme with `parallelizable = "YES"`
  launches two test hosts. Two hosts running this suite write the same out
  file concurrently.
- **`TEST_RUNNER_GOLDEN_CENSUS_OUT`** — `xcodebuild` forwards a variable to the
  test process only when the caller spells it with the `TEST_RUNNER_` prefix.
  The test reads it as `GOLDEN_CENSUS_OUT`.
- **The out file removed before the run** — so a leftover from an earlier run
  cannot answer for this one.
- **Verdict = exit 0 AND the file exists** — an `-only-testing:` filter that
  matches nothing still prints `TEST SUCCEEDED` and exits 0. Measured on one
  macOS project with a `--test` id that matches no suite: `xcodebuild exited
  0; the out file was not written`, the last 40 log lines, a `next:` line
  naming the id, exit 1.
- **Nothing printed on success; the tail of the log on failure** — golden-census
  records stdout and stderr as goldens. The wrapper never prints the out file's
  own path either. It is an absolute path under golden-census's work directory.
- **`--version` → `xcodebuild -version` on one line** — the toolchain the
  census's `state` rows care about. The capture log prints it, and it is never
  a golden.
- **Imports nothing from golden-census** — the wrapper is the consumer's file.
  golden-census runs it and records the bytes.

## 5. The census rows a Swift subject adds

| input | how the census carries it | why |
|---|---|---|
| the host macOS version | `precondition` with `command = ["sh", "-c", "test \"$(sw_vers -productVersion)\" = <the recorded version>"]` and `expect = "exit 0"` | text APIs the function reaches can differ across OS releases, such as `CFStringTokenizer` transliteration and `NSString` comparison. A diff they produce is not a statement about the subject |
| Xcode / Swift toolchain | `state` (`xcodebuild -version`, `swift --version`) | the surface is the output of a BUILD. A toolchain upgrade can move floating-point arithmetic or string handling. The recorded version attributes the move |
| the version the fixtures were recorded at | `state` (read from a fixture file, one line) | this is provenance of the INPUTS, not a pin on the run. A re-recording moves every golden at once, and this row names the engine that changed |
| `DEVELOPER_DIR` | `passthrough` if set, else a `state` row recording `<unset>` | `xcodebuild` honors it. Unlisted, it cannot reach the wrapper, and unset it is the `xcode-select` default |
| `PATH`, `HOME` | `passthrough` | the wrapper shells out to `xcodebuild` and `getconf`. `xcodebuild` reads `~/Library` (toolchain caches, the signing keychain) |

The middle column holds two different things. `precondition` and `state` are
DISPOSITIONS. `docs/census-format.md` names the four, and these two are the
ones a Swift subject reaches for. `passthrough` is not a disposition. It is a
name in the census's `[environment] passthrough` list, which decides whether a
variable reaches the subject at all. Every row is here because the surface is
the output of a BUILD. The toolchain and the OS are inputs to that build as
surely as the fixtures are inputs to the function.

## 6. The mutant

One mutant is enough to prove the net. Change a rule inside the function's
reach that at least one fixture exercises, such as a threshold or a hide
condition. Set `expect = ["comparator"]`. `mutants` clones the app's
repository, commits the edit, and the wrapper builds the clone. A Swift mutant
costs a build, which is why the comparator is the only check and the fixture
set is small. The clone's derived data is its own cache entry, pruned when the
clone goes. A golden that does not live in the app's repository is named as
`<HERE>/golden` in the mutants file, the directory the file sits in.

## 7. Recording fixtures, as text

Sometimes the function's inputs are the output of something non-deterministic
or slow: a recognizer over bitmaps, a parse of a document. Record them ONCE by
a second test in the same file, disabled on a second variable:

    TEST_RUNNER_GOLDEN_CENSUS_RECORD=<dir>   run the real producer over the raw
                                       inputs; write each result beside the
                                       runner as a fixture file; commit them.

Run it by hand, with the same derived entitlements the wrapper builds. The
sandboxed host cannot write otherwise. The test stamps each fixture with the
producer's version where it has one. So a census `state` row can read the
engine the inputs were recorded at out of the file. A re-recording is a new
version in the census and a re-baseline of every golden. Attribute it as such,
and never do it silently. The template ships the surface test only.

## 8. The `dest` hole

`init` writes the runner to the literal directory
`<<HOLE:TEST_TARGET_DIR>>/GoldenCensusRunner.swift`, because a scaffold that
asked the question first could not be run from one line. It prints this beside
the hole: `that file was written to the literal <<HOLE:TEST_TARGET_DIR>>
directory, so MOVE it once you have filled the hole`. Fill `TEST_TARGET_DIR`,
then MOVE the file into the test target's source directory and add it to that
target. The wrapper lands at `golden-census/wrapper.py` and needs no move.

## 9. Written against

Xcode 26.6 (17F113), Swift 6.3.3, macOS 26.6.2 (25G83), Python 3.11 (standard
library only — `argparse`, `hashlib`, `os`, `plistlib`, `shutil`, `subprocess`,
`sys`, `tempfile`).

Measured on one macOS project:

- A warm capture is a test run rather than a rebuild, and prints nothing.
- A second run with `--destination platform=macOS,arch=arm64` spelled
  explicitly is byte-identical to the first. That is what makes the default
  safe to leave out.
- `--version` prints one line, `Xcode 26.6 Build version 17F113`.

The runner's own floor is macOS 13 / iOS 16 (`URL(filePath:)`,
`appending(path:)`).

## 10. Traps

- **`TEST SUCCEEDED` with no test run.** Causes are a misspelled `--test` id, a
  renamed suite, and a runner never moved out of the `<<HOLE:TEST_TARGET_DIR>>`
  directory or never added to the target. In each case `xcodebuild` exits 0.
  The out file's existence is the verdict, and the wrapper's `next:` line names
  the id that matched nothing.
- **`NSCocoaErrorDomain 513` from the test host.** This is the sandbox. The
  derived entitlements fix it. A project whose test host is NOT the app, such
  as a framework target, has no sandbox, and the exception is harmless.
- **Two hosts, one file.** The cause is `parallelizable = "YES"` in the scheme.
  The wrapper passes `-parallel-testing-enabled NO` unconditionally.
- **A cache under `$TMPDIR` is a rebuild every capture.** The census's
  fixed-width `TMPDIR` is deleted after each run. The wrapper's cache is under
  the per-user temp root instead. `getconf DARWIN_USER_TEMP_DIR` is how it
  finds that root whatever `$TMPDIR` says.
- **Some sandboxed shells refuse the test runner.** Inside one,
  `xcodebuild test` fails on the `com.apple.testmanagerd.control` lookup. Every
  capture, compare and mutants run of an xcodebuild subject then needs the
  sandbox bypass.
- **`DEVELOPER_DIR`.** Suppose it is set on the machine and absent from the
  census's passthrough list. It cannot reach the wrapper, and the build uses
  the `xcode-select` default silently. A census row settles which.
- **A fixture is an input, not a golden.** Re-recording fixtures moves every
  golden. The census `state` row that reads the engine version out of a fixture
  makes that movement attributable.
