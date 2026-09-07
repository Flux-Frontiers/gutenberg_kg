# Conversations and a sidebar for The Knowledge Press

| Field | Value |
|---|---|
| **Author** | Eric G. Suchanek, PhD (Flux-Frontiers) |
| **Date** | 2026-09-07 |
| **Status** | Draft, ready to execute |
| **Repo tip** | `main` @ `62531da` (PR #118 merged) |
| **Workspace** | `/Users/egs/repos/gutenberg_kg/app/GutenbergKGKit` |
| **Audience** | Agents implementing this; each phase is one PR |

---

## Overview

The app forgets every chat the moment it is relaunched, and its only way to
start over is a trash button that discards what is on screen. The Claude iPad
app, in landscape, does what this app should do: a persistent sidebar lists
past conversations grouped by day, a mode switcher sits at the top of it, and
a new chat is one tap away. Portrait collapses the sidebar behind the standard
toggle; the phone reaches the same list from a leading toolbar button.

This plan adds two things, in that order:

1. **Conversations that persist.** A conversation is an ordered list of the
   existing `ChatTurn` values plus a title and timestamps, stored as one
   directory per conversation under `Application Support/Conversations/`.
   Nothing about a turn's shape changes for the view code.
2. **A sidebar shell** on iPad and Mac, and a conversation list sheet on the
   iPhone, all sharing one list component. The sidebar owns the two controls
   that change what a question means, the answer engine and the corpus scope;
   everything else stays in Settings.

The shared package already carries the state this needs. `ChatTurn` records
its own `corpus` and `engine`; `AppModel` already persists two settings
through an injectable `UserDefaults`; the three shells already differ per
platform on purpose. The work is mostly plumbing plus one new view family.

---

## Background

`AppModel.turns` is a plain in-memory array. `send()` appends to it, the
streaming paths mutate it by index at ten call sites, and three separate
"Clear" controls (`PhoneRootView`, `PadRootView`, `SettingsView`) empty it.
There is no identity above a turn: no title, no timestamp, no way to have two
chats at once.

Two findings from the 2026-09-07 investigation shape the design:

- **Scope dominates answer quality** on the on-device engine
  (`analysis/CONTEXT_BUDGET_MEASUREMENT_20260907.md`). Unscoped, "circles of
  Hell" retrieves Les Miserables and Lovecraft next to Dante. That is why
  scope belongs in the sidebar next to the engine, where it is visible per
  chat, and not three taps away in Settings.
- **Rendered images are large.** One real `imagine` result measured 4.2 MB
  as base64 (`GeneratedImage.imageB64`). A conversation file that inlines
  images would be unreadable in an editor and slow to list. Images go out of
  line from the start.

---

## Goals

- A chat survives relaunch, on all three platforms, with its passages,
  answer, metrics, and any rendered illustration.
- The iPad shows a persistent sidebar in landscape: new chat, browse the
  corpus, engine and scope pickers, and recent conversations grouped by day,
  with search. Portrait collapses it behind the standard toggle.
- The Mac gets the same sidebar; Settings moves to the standard `Settings`
  scene (Cmd-comma).
- The iPhone reaches the same list from a leading toolbar button.
- Switching, deleting, and renaming a conversation is discoverable from the
  list itself (swipe and context menu), not from Settings.
- Nothing in the retrieval or synthesis path changes. `SynthesisTrace` is
  untouched.

## Non-goals

- iCloud or CloudKit sync between devices. The on-disk layout is chosen so a
  later move into the ubiquity container is a path change, not a rewrite, but
  the entitlement work is its own project (see the Private Cloud Compute
  entitlement history in `app/ios/project.yml`).
- Multi-window on iPad. One active conversation per scene.
- Editing a past question or regenerating a past answer.
- Folders, projects, pinning, or sharing links.
- Automatic titling with the on-device model. Listed as optional in Phase 4
  with the reason it is optional.

---

## Key decisions

1. **One directory per conversation, JSON inside, images beside it.**
   `Conversations/<uuid>/conversation.json` plus
   `Conversations/<uuid>/images/<turn-uuid>.png`. Plain files match how the
   app already stores the corpus and the synthesis traces; they can be
   inspected with `devicectl device copy from`, the same way the traces were
   pulled today. No SwiftData, no Core Data.
2. **An index file, rebuilt on every write and self-healing on read.**
   `Conversations/index.json` holds `[ConversationSummary]` so the sidebar
   lists titles without decoding every answer. If it is missing or fails to
   decode, the store rebuilds it by scanning directories. The index is a
   cache, never the source of truth.
3. **`AppModel.turns` stays the live buffer.** The ten mutation sites keep
   working unchanged. `activeConversation` is metadata beside it; selecting
   another conversation swaps the buffer. This is the least invasive shape
   and it keeps the streaming code out of the diff.
4. **A conversation is created on the first completed turn, not on "New
   chat".** Tapping New chat with an empty buffer is a no-op. This avoids
   the Claude-app failure mode of a sidebar full of untitled empty chats.
5. **Switching conversations cancels an in-flight query.** The alternative,
   a query finishing into a buffer the user is no longer looking at, would
   mutate the wrong conversation. Cancel is what the Claude app does.
6. **Cancelled turns persist truthfully.** `ChatTurn.isStreaming` is derived:
   retrieval present, no metrics, no failure, no error. A turn cancelled
   mid-answer satisfies that forever once reloaded, and would show a
   streaming caret on a chat that finished yesterday. `cancel()` therefore
   records `synthesisFailure = .cancelled`, a new case with `displayMessage`
   "Stopped." and `isRecoverableRemotely == false`.
7. **The sidebar owns engine and scope on iPad and Mac; Settings hides them
   there.** One home per control. `SettingsView` gains
   `showsEngineAndScope` (default `true`), and the two shells with a sidebar
   pass `false`. The iPhone has no sidebar, so its Settings keeps both.
8. **Conversations are backed up; the corpus is not.** The corpus directory
   is marked `isExcludedFromBackup` because it is regenerable. Conversations
   are the user's own content and get the default backup treatment. The
   store must not copy the exclusion flag from `CorpusPacks.defaultDirectory`.
9. **Titles are the first question, trimmed at a word boundary to 48
   characters.** Deterministic, instant, and never wrong in a way the reader
   cannot see. Rename is a context-menu action.
10. **Siri starts a new conversation when the current one has turns.** A
    spoken question is not a follow-up to whatever was last on screen.
11. **`schemaVersion: 1` in every `conversation.json`.** The turn shape will
    change; the field costs nothing now and makes migration a switch rather
    than a guess later.

---

## Proposed design

### Data model (`GutenbergKGKit` and `KnowledgePressUI`)

Conformances to add in `GutenbergKGKit`, all synthesized:

| Type | File | Change |
|---|---|---|
| `RetrievalResult` | `Retrieval/RetrievalEngine.swift` | `+ Codable` |
| `SynthesisMetrics` | `Synthesis/SynthesisBackend.swift` | `+ Codable` |
| `SynthesisFailure` | `Synthesis/SynthesisBackend.swift` | `+ Codable`, `+ case cancelled` |

`Hit`, `GeneratedImage`, and `AnswerEngine` (String raw value) are already
Codable. Enums with associated `String` values synthesize Codable; no custom
coding is needed for `SynthesisFailure`.

`ChatTurn` (`KnowledgePressUI/AppModel.swift`) becomes `Codable` with an
explicit `CodingKeys` that omits the transient state:

```swift
public struct ChatTurn: Identifiable, Sendable, Codable {
    public let id: UUID
    let question: String
    let corpus: String
    let engine: AnswerEngine
    var retrieval: RetrievalResult?
    var answer: String = ""
    var metrics: SynthesisMetrics?
    var synthesisFailure: SynthesisFailure?
    var errorMessage: String?

    /// In-memory illustration, set by renderImage(for:) in this session.
    var generatedImage: GeneratedImage?
    /// On-disk illustration, relative to the conversation directory.
    var imageFile: String?
    var imageError: String?
    var isRenderingImage = false        // not encoded

    init(question: String, corpus: String, engine: AnswerEngine) {
        self.id = UUID()
        ...
    }

    enum CodingKeys: String, CodingKey {
        case id, question, corpus, engine, retrieval, answer, metrics,
             synthesisFailure, errorMessage, imageFile, imageError
    }
}
```

`id` changes from `public let id = UUID()` to `public let id: UUID` assigned
in the initializer. A property with a default value and no initializer
assignment cannot be decoded; this is the one line in the struct that
would otherwise stop `Codable` from compiling.

`generatedImage` is never encoded. When a render completes, the store writes
the PNG (`Data(base64Encoded:)`) to `images/<turn-id>.png` and sets
`imageFile`. `AssistantTurnView` prefers `generatedImage` when present and
falls back to loading `imageFile` from the conversation directory; the
existing `decodedImage(_:)` helper gains a sibling that takes a file URL.

New types in `KnowledgePressUI/Conversations.swift`:

```swift
struct Conversation: Codable, Identifiable {
    static let currentSchema = 1
    var schemaVersion = Conversation.currentSchema
    let id: UUID
    var title: String
    let createdAt: Date
    var updatedAt: Date
    var turns: [ChatTurn]
}

struct ConversationSummary: Codable, Identifiable, Hashable {
    let id: UUID
    var title: String
    let createdAt: Date
    var updatedAt: Date
    var turnCount: Int
    /// Engine and scope of the most recent turn, for the row's badge.
    var lastEngine: AnswerEngine
    var lastCorpus: String
}
```

### `ConversationStore` (`KnowledgePressUI/ConversationStore.swift`)

A `struct` over an injected directory, mirroring how `AppModel.defaults` is
injectable for tests:

```swift
struct ConversationStore: Sendable {
    let directory: URL

    static func defaultDirectory() -> URL?   // Application Support/Conversations
    func summaries() throws -> [ConversationSummary]   // newest first
    func load(_ id: UUID) throws -> Conversation
    func save(_ conversation: Conversation) throws     // writes json, rewrites index
    func delete(_ id: UUID) throws                     // removes directory, rewrites index
    func writeImage(_ data: Data, conversation: UUID, turn: UUID) throws -> String
    func imageURL(conversation: UUID, file: String) -> URL
}
```

Rules the implementation must follow:

- `save` writes to a temporary file in the same directory and renames it into
  place, so a crash mid-write cannot leave a truncated `conversation.json`.
- `summaries()` reads `index.json`; on any decode failure it scans
  `Conversations/*/conversation.json`, rebuilds the index, and returns the
  result. This is the self-healing path and it needs a test.
- Encoding uses `.iso8601` dates and `.sortedKeys` so files diff cleanly.
- The store does no I/O on the main actor. `AppModel` calls it from
  `Task.detached`, the same pattern `loadCorpusPacks()` already uses.

### `AppModel` changes

New state:

```swift
private(set) var conversations: [ConversationSummary] = []
private(set) var activeConversation: Conversation?   // nil until first turn completes
let store: ConversationStore
```

`init` gains a `store` parameter defaulting to `ConversationStore.defaultDirectory()`,
the same seam `defaults` provides. The initializer loads `summaries()` off
the main actor.

New methods:

| Method | Behavior |
|---|---|
| `newConversation()` | If `turns` is empty, no-op. Otherwise cancel any query, persist the active conversation, clear `turns`, set `activeConversation = nil`. |
| `select(_ id: UUID)` | Cancel any query, persist the active conversation, load `id`, replace `turns`, set `activeConversation`. |
| `delete(_ id: UUID)` | Remove from store and `conversations`; if it was active, behave as `newConversation()` without saving. |
| `rename(_ id: UUID, to title: String)` | Trimmed, non-empty; update store and summaries. |
| `persistActiveConversation()` | Create the `Conversation` on first call (title from the first question), else update `updatedAt` and `turns`; save off-main; refresh `conversations`. |

Where `persistActiveConversation()` is called, and nowhere else:

- `stream(...)`: after `.finished`, after `.synthesisUnavailable`, and in the
  `catch`.
- `sendViaWorker(...)`: after the result is applied, and in the `catch`.
- `renderImage(for:)`: after `generatedImage` is set (the store writes the
  PNG and sets `imageFile` first) and after `imageError` is set.
- `cancel()`: after marking the in-flight turn `.cancelled`.
- Not on every streamed partial. Partials are visual; the file is written
  once per completed step.

The Siri path (`.askKnowledgePress` observer in `init`) calls
`newConversation()` before `send(question)` (Decision 10).

`SettingsView`'s "Clear chat" button and both shells' trash buttons are
replaced by "Delete conversation" with a confirmation dialog, disabled when
`activeConversation == nil && turns.isEmpty`. "New chat" is a separate
control in the sidebar and the phone sheet.

### Views

New files in `KnowledgePressUI`:

| File | Contents |
|---|---|
| `ConversationSidebar.swift` | The iPad/Mac sidebar column: New chat, Browse corpus, engine picker, scope picker, then `ConversationListView`, then a Settings button in the footer. |
| `ConversationListView.swift` | The grouped, searchable list. Used by the sidebar and the phone sheet. Sections: Today, Yesterday, Previous 7 days, Older. Swipe to delete; context menu Rename / Delete. |
| `RecentsGrouping.swift` | Pure function `group(_ summaries: [ConversationSummary], now: Date, calendar: Calendar) -> [(section: String, items: [ConversationSummary])]`. Testable with a fixed `now`. |
| `ConversationTitle.swift` | Pure function `title(for question: String, limit: Int = 48) -> String`, word-boundary trim, ellipsis as three ASCII periods. Testable. |

Sidebar selection is an enum, replacing the tab bar on iPad and Mac:

```swift
enum SidebarItem: Hashable {
    case chat            // the active conversation, or a fresh one
    case browse
    case conversation(UUID)
}
```

Choosing `.conversation(id)` calls `model.select(id)` and shows `.chat`.
`.browse` shows `BrowseView` in the detail column. The Chat/Browse `TabView`
goes away on iPad and Mac; the iPhone keeps its tabs.

The engine picker in the sidebar reuses the `answerEngineSection` binding
from `SettingsView` (`$model.engine`, the same `onChange` that prewarms
on-device and refreshes worker models). Extract that section into its own
view, `AnswerEnginePicker`, used by both. Same for the scope picker,
`CorpusScopePicker`. Two shared views, zero duplicated logic.

**iPad (`PadRootView`).** `NavigationSplitView(columnVisibility:)` with
`ConversationSidebar` in the sidebar column and, in detail, a
`NavigationStack` around `ChatView(showsHeader: false)` or `BrowseView`.
Binding `columnVisibility` is what surfaces the built-in toggle
(established in `MacRootView`); landscape shows both columns, portrait
collapses to an overlay. The detail title is the conversation title, or
"New chat". The existing Settings popover moves to the sidebar footer
button and passes `showsEngineAndScope: false`.

**Mac (`MacRootView`).** Same sidebar and detail. `SettingsView` leaves the
sidebar and becomes a `Settings { SettingsView(showsEngineAndScope: false).environment(model) }`
scene in `KnowledgePressApp.swift`, which gives Cmd-comma for free. Add
`CommandGroup(after: .newItem) { Button("New Chat") { model.newConversation() }.keyboardShortcut("n") }`.

**iPhone (`PhoneRootView`).** Tabs stay. The Chat tab gains a leading
toolbar button (`sidebar.left`) presenting a sheet containing a
`NavigationStack { ConversationListView() }` with a "New chat" row at the
top and Done in the toolbar. Selecting a row selects the conversation and
dismisses. Settings is unchanged and keeps engine and scope.

**`ChatView`.** Unchanged except that the empty state's suggestion buttons
already route through `send`, which now persists. The `onChange(of:
model.turns.count)` scroll-to-bottom keeps working when a conversation is
selected because the buffer is replaced wholesale.

---

## Data on disk

```
Application Support/
  Corpus/                     (existing; excluded from backup)
  Diagnostics/                (existing; SynthesisTrace)
  Conversations/
    index.json                [ConversationSummary], newest first
    3F2504E0-.../
      conversation.json
      images/
        9A1B2C3D-....png
```

Size expectations, so nobody adds a cap prematurely: a turn with 25 hits at
the corpus's typical 268 to 510 characters is 15 to 30 KB of JSON. A hundred
conversations of ten turns is on the order of 20 MB, before images. Images
are the only thing that grows quickly and they are already out of line.

---

## Alternatives considered

**SwiftData.** Gives free querying and iCloud sync later. Rejected for v1:
it introduces a model layer the rest of the package does not have, its iCloud
path needs the same entitlement work as Private Cloud Compute, and the files
would no longer be inspectable with `devicectl`, which is how every
on-device question in this project has been answered so far.

**One JSON file for everything.** Simplest possible store. Rejected because a
single 4 MB image would sit inside it, every save would rewrite every
conversation, and a corrupt write would lose all of them at once.

**Keep engine and scope only in Settings.** Fewer views to build. Rejected
because scope is the single largest lever on answer quality and belongs
where the reader can see it per chat.

**A custom edge-swipe drawer on the iPhone.** Closer to the Claude app.
Rejected for v1: a sheet is one modifier and has no gesture code to get
wrong. A drawer can replace it later without touching the list component.

---

## Risks

| Risk | Mitigation |
|---|---|
| A streamed partial races a conversation switch | `select` and `newConversation` cancel first (Decision 5); `cancel()` marks the turn `.cancelled` before the buffer is swapped |
| `ChatTurn` gains `Codable` but a nested type is missed | The compiler catches it; the three conformances above are the complete list as of `62531da` |
| The index drifts from the directories | Index is rebuilt on every write and on any read failure; a test deletes `index.json` and asserts `summaries()` still returns every conversation |
| Portrait iPad hides the sidebar and the toggle is not obvious | Same affordance as Files and Notes; the detail toolbar also gets a "New chat" button so the common action never needs the sidebar |
| Loading a conversation with a missing image file | `imageFile` present but file absent shows the Render button again rather than an error |
| A rename to an empty string | `rename` trims and refuses empty; the row keeps its old title |

---

## Implementation plan

Each phase is one branch off `develop` and one PR into `develop`. Branch
names follow the repo's `feat/...` convention. Every PR: `swift test` from
`app/GutenbergKGKit` with the full count reported and no skips, `make
ios-check`, a CHANGELOG entry under `[Unreleased]`, and a real-device check
where the phase touches a shell.

Conventions the executing agent must follow, learned the hard way in this
package:

- Test suites that touch `AppModel` are `@MainActor @Suite`. Inject the
  store's directory the way `WorkerURLTests.withScratchDefaults` injects
  `UserDefaults`; never write to the real `Application Support`.
- A `public struct`'s memberwise initializer is internal across module
  boundaries. Test fixtures for `GutenbergKGKit` types are built by decoding
  JSON, as `ImagePromptTests` does, or through an explicit `public init`.
- New Swift files under `Sources/` are picked up by both Xcode projects
  automatically (`sources: - Sources` in `project.yml`); no `xcodegen` step.
- ASCII punctuation in comments, docs, changelog, and commit messages: `--`
  for a dash, `...` for an ellipsis. Comments say why, not what.
- `SynthesisTrace` is deliberately ungated while an upstream report is open.
  Do not touch it.

### Phase 1 -- Persistence (`feat/conversation-store`)

- `GutenbergKGKit`: the three `Codable` conformances; `SynthesisFailure.cancelled`
  with `displayMessage` "Stopped." and `isRecoverableRemotely == false`.
- `KnowledgePressUI`: `ChatTurn: Codable` per the sketch; `Conversations.swift`;
  `ConversationStore.swift`; `ConversationTitle.swift`.
- `AppModel`: `store` injection, `conversations`, `activeConversation`,
  `newConversation`, `select`, `delete`, `rename`, `persistActiveConversation`,
  the call sites listed above, `cancel()` marking `.cancelled`, and the Siri
  observer calling `newConversation()` first.
- Replace the three "Clear" controls with "Delete conversation" behind a
  confirmation. No other UI change. Chats now persist but there is no way to
  reopen one until Phase 2; that is acceptable on `develop`.
- `AssistantTurnView`: load `imageFile` when `generatedImage` is nil.

Tests (`Tests/GutenbergKGKitTests/`):

- `ConversationStoreTests`: save then load round-trips a two-turn
  conversation including `retrieval`, `metrics`, a `.cancelled` failure, and
  `imageFile`; `summaries()` is newest-first; delete removes the directory
  and the index entry; deleting `index.json` and calling `summaries()`
  rebuilds it; a partially written temporary file is never visible as a
  conversation.
- `ConversationLifecycleTests` (`@MainActor`): first completed turn creates a
  conversation titled from the question; `newConversation()` on an empty
  buffer is a no-op and creates nothing; `select` swaps the buffer; `delete`
  of the active conversation clears the buffer; `rename` refuses empty.
- `ConversationTitleTests`: 48-character limit, word-boundary trim, short
  questions untouched, whitespace collapsed.
- `ChatTurn` encodes without `isRenderingImage` or `generatedImage`
  (assert the keys are absent from the JSON).

Acceptance: ask a question on the iPhone, force-quit, relaunch, and the
answer is on screen with its passages and stats line. Cancel a query, relaunch,
and the turn shows "Stopped." with no caret.

### Phase 2 -- Shared list and the iPad shell (`feat/ipad-sidebar`)

- `RecentsGrouping.swift`, `ConversationListView.swift`,
  `ConversationSidebar.swift`, `AnswerEnginePicker`, `CorpusScopePicker`
  (extracted from `SettingsView`), `SettingsView(showsEngineAndScope:)`.
- `PadRootView` rebuilt on `NavigationSplitView` with `SidebarItem`; tabs
  removed on iPad; Settings popover moves to the sidebar footer.
- Search via `.searchable` on the list, matching title and any question text
  in the summary's conversation. (Summaries carry only the title; searching
  question text loads conversations lazily and can be limited to titles in
  this phase if the lazy load is not ready. State which was done in the PR.)

Tests: `RecentsGroupingTests` with a fixed `now` covering a conversation at
23:59 yesterday, one exactly seven days old, and one older; empty input gives
no sections.

Acceptance, on a real iPad: landscape shows the sidebar with today's
conversations grouped correctly; rotating to portrait collapses it and the
toggle restores it; picking a conversation loads it; New chat clears the
detail without creating a row until a turn completes; switching mid-answer
stops the answer and the abandoned chat shows "Stopped." in the list's
conversation. Engine and scope changed in the sidebar are reflected in the
next question's chip and in Settings, which no longer shows those two
sections on the iPad.

### Phase 3 -- iPhone sheet and the Mac shell (`feat/phone-history-and-mac-sidebar`)

- `PhoneRootView`: leading toolbar button and the list sheet; "New chat" row;
  selection dismisses.
- `MacRootView`: the sidebar from Phase 2; `SettingsView` removed from the
  sidebar; `KnowledgePressApp.swift` gains the `Settings` scene and the
  Cmd-N command.

Acceptance: on the iPhone, open the list, select yesterday's chat, and it
loads; swipe to delete works. On the Mac, Cmd-comma opens Settings without
engine or scope, Cmd-N starts a new chat, and the sidebar collapse toggle
still works.

### Phase 4 -- Polish (`feat/conversation-polish`)

Any subset, each its own commit:

- Rename via an alert with the current title prefilled.
- "Export as Markdown" in the conversation's context menu, producing the
  question, answer, and cited passages through the share sheet.
- Keyboard shortcuts on iPad: Cmd-N new chat, Cmd-Shift-D delete.
- Optional automatic titling with the on-device model: a single short
  `LanguageModelSession` call producing a 3-to-6-word title, run after the
  first answer completes, never blocking `send`, falling back to the
  question-derived title on any failure. Optional because the on-device
  model's behavior currently differs by device
  (`analysis/FOUNDATION_MODELS_DIVERGENCE_20260907.md`) and a bad title is
  more visible than a bad answer.

---

## What done looks like

A reader on an iPad in landscape sees their past week of questions down the
left, picks yesterday's chat about the Great Fire, and it is there with its
passages and the illustration they rendered. They switch the scope to
`philosophy` at the top of the sidebar, tap New chat, and ask about the
categorical imperative. On the train, in portrait, the sidebar is one tap
away. On the phone that evening, the same list is behind the leading button.
Nothing they did today was lost, and nothing left the device to make that so.
