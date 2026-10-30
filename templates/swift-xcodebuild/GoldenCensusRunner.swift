//
//  GoldenCensusRunner.swift
//
//  The bridge between this module and golden-census. A Swift
//  module has no command line for its pure functions, so golden-census drives
//  one through the test tool — `swift test --filter GoldenCensusRunner`, or
//  `xcodebuild test -only-testing:` behind the swift-xcodebuild wrapper — and
//  reads the FILE this test writes. Nothing the build prints is a golden.
//
//  Disabled unless the job is present: only golden-census sets GOLDEN_CENSUS_OUT, so
//  an ordinary test run never reaches this test. `swift test` passes its
//  environment through as it is; `xcodebuild` forwards a variable to the test
//  process only when the caller spells it TEST_RUNNER_GOLDEN_CENSUS_OUT, which the
//  wrapper does.
//
//  Four holes, written in place, each a fact only this project knows: the
//  module under test, the fixture list, how a fixture file becomes the
//  function's input, and the call itself. golden-census never guesses one.
//

import Foundation
import Testing
@testable import <<HOLE:MODULE>>

struct GoldenCensusRunner {

    /// The file golden-census wants the surface written to, or nil when this
    /// is an ordinary test run.
    static let outPath = ProcessInfo.processInfo.environment["GOLDEN_CENSUS_OUT"]

    /// The fixtures, by name, kept beside this file. A new fixture is one
    /// element here and nothing in the manifest.
    static let fixtures: [String] = [<<HOLE:FIXTURES>>]

    /// A fixture's URL, resolved against this file's own directory:
    /// `#filePath` is the source path at compile time, so the list reads the
    /// same whichever directory the test tool runs from, and no bundle
    /// resource declaration is needed.
    static func fixtureURL(_ name: String) -> URL {
        URL(filePath: #filePath).deletingLastPathComponent().appending(path: name)
    }

    /// One fixture in, the function's answer out. LOAD_INPUT turns the file
    /// at `url` into the function's input(s); FUNCTION_CALL is the call. The
    /// answer must be `Encodable`: the JSON encoder below is what makes it a
    /// golden, and a type it cannot encode is a compile error here, not a
    /// silent empty surface.
    static func surface(of url: URL) throws -> some Encodable {
        <<HOLE:LOAD_INPUT>>
        return <<HOLE:FUNCTION_CALL>>
    }

    @Test("golden-census's surface, written to $GOLDEN_CENSUS_OUT",
          .enabled(if: outPath != nil))
    func writeSurface() throws {
        let out = URL(filePath: try #require(Self.outPath))
        let results = try Dictionary(uniqueKeysWithValues: Self.fixtures.map { name in
            (name, try Self.surface(of: Self.fixtureURL(name)))
        })
        // Sorted keys and unescaped slashes so the bytes are canonical;
        // pretty-printed so golden-census's comparator names the key that
        // moved instead of reporting one enormous line.
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes]
        try encoder.encode(results).write(to: out)
    }
}
