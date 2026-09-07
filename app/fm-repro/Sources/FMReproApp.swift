// Minimal reproducer: Apple Foundation Models returns different completions
// for a byte-identical prompt at temperature 0, depending on the device.
//
// Observed on iPadOS 27.0 (24A5430a) / iPad16,3, which returns a short
// completion that quotes one source passage and then repeats it verbatim.
// iOS 27.0 (24A5430a) / iPhone18,1 and macOS 27.0 (26A5425a) both return a
// correct 847-character synthesis, byte-identical to each other.
//
// The prompt and instructions below are reproduced verbatim from a captured
// trace. The app prints their SHA-256 at launch so any transcription drift is
// visible immediately: they must read 89dfc16116d9d769 and e24dd2bf123468fe.
//
// No network, no data files, no dependencies. Build, run, tap Run.

import CryptoKit
import FoundationModels
import SwiftUI

let sessionInstructions = #"""
You are a literary guide to the Project Gutenberg corpus. Answer the question using ONLY the provided source passages. Do NOT use any prior knowledge — if something is in the passages, report it; if it is not in the passages, say so. Never contradict or override what the passages say based on what you believe to be true. Be concise and specific. Cite the author and work when relevant.
"""#

let userPrompt = #"""
Source passages:
[world-literature · Dante Alighieri · The Divine Comedy (Cary's Translation)]
*There is a place within the depths of hell*

Call’d Malebolge, all of rock dark-stain’d
With hue ferruginous, e’en as the steep
That round it circling winds. Right in the midst
Of that abominable region, yawns
A spacious gulf profound, whereof the frame
Due time shall tell. The circle, that remains,
Throughout its round, between the gulf and base
Of the high craggy banks, successive forms
Ten trenches, in its hollow bottom sunk.

[world-literature · Dante Alighieri · The Divine Comedy (Cary's Translation)]
And so far off,
Perchance, as is the halo from the light
Which paints it, when most dense the vapour spreads,
There wheel’d about the point a circle of fire,
More rapid than the motion, which first girds
The world. Then, circle after circle, round
Enring’d each other; till the seventh reach’d
Circumference so ample, that its bow,
Within the span of Juno’s messenger,
lied scarce been held entire. Beyond the sev’nth,
Follow’d yet other two.

[world-literature · Dante Alighieri · The Divine Comedy (Cary's Translation)]
Five centuries and more,
T for that lukewarmness was fain to pace
Round the fourth circle.

[world-literature · Dante Alighieri · The Divine Comedy (Cary's Translation)]
*From centre to the circle, and so back*

From circle to the centre, water moves
In the round chalice, even as the blow
Impels it, inwardly, or from without. Such was the image glanc’d into my mind,
As the great spirit of Aquinum ceas’d;
And Beatrice after him her words
Resum’d alternate: “Need there is (tho’ yet
He tells it to you not in words, nor e’en
In thought) that he should fathom to its depth
Another mystery.

[world-literature · Dante Alighieri · The Divine Comedy (Cary's Translation)]
No long space my flesh
Was naked of me, when within these walls
She made me enter, to draw forth a spirit
From out of Judas’ circle. Lowest place
Is that of all, obscurest, and remov’d
Farthest from heav’n’s all-circling orb. The road
Full well I know: thou therefore rest secure.

Question: circles of Hell
"""#

func shortDigest(_ text: String) -> String {
    let digest = SHA256.hash(data: Data(text.utf8))
    return digest.map { String(format: "%02x", $0) }.joined().prefix(16).description
}

func hardwareIdentifier() -> String {
    var info = utsname()
    uname(&info)
    return withUnsafeBytes(of: &info.machine) { raw in
        String(decoding: raw.prefix { $0 != 0 }, as: UTF8.self)
    }
}

struct RunResult: Identifiable {
    let id = UUID()
    let index: Int
    let text: String
    let elapsedMs: Int

    var lines: [String] { text.split(separator: "\n").map(String.init) }
    var repeats: Bool { lines.count > Set(lines).count }
}

@MainActor
final class Model: ObservableObject {
    @Published var results: [RunResult] = []
    @Published var running = false
    @Published var failure: String?

    func run(times: Int) async {
        running = true
        failure = nil
        results = []
        defer { running = false }

        for index in 1...times {
            let session = LanguageModelSession { sessionInstructions }
            let options = GenerationOptions(temperature: 0)
            let started = Date()
            var latest = ""
            do {
                for try await partial in session.streamResponse(to: userPrompt, options: options) {
                    latest = partial.content
                }
            } catch {
                failure = "\(error)"
                return
            }
            results.append(
                RunResult(
                    index: index,
                    text: latest,
                    elapsedMs: Int(Date().timeIntervalSince(started) * 1000)))
        }
    }
}

struct ContentView: View {
    @StateObject private var model = Model()

    var body: some View {
        NavigationStack {
            List {
                Section("Environment") {
                    LabeledContent("Hardware", value: hardwareIdentifier())
                    LabeledContent("System", value: ProcessInfo.processInfo.operatingSystemVersionString)
                    LabeledContent("Instructions SHA", value: shortDigest(sessionInstructions))
                    LabeledContent("Prompt SHA", value: shortDigest(userPrompt))
                    LabeledContent("Temperature", value: "0")
                }

                Section {
                    Button(model.running ? "Running…" : "Run 3 times") {
                        Task { await model.run(times: 3) }
                    }
                    .disabled(model.running)
                }

                if let failure = model.failure {
                    Section("Failure") { Text(failure).foregroundStyle(.red) }
                }

                ForEach(model.results) { result in
                    Section("Run \(result.index) — \(result.text.count) chars, \(result.elapsedMs) ms") {
                        if result.repeats {
                            Label(
                                "\(result.lines.count) lines, \(Set(result.lines).count) unique",
                                systemImage: "exclamationmark.triangle.fill"
                            )
                            .foregroundStyle(.red)
                        }
                        Text(result.text).font(.callout).textSelection(.enabled)
                    }
                }
            }
            .navigationTitle("FM Repro")
        }
    }
}

@main
struct FMReproApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
