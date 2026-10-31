# Swift · SwiftUI · iOS

[← back to router](../framework-idioms.md)

See also [../frontend-patterns.md](../frontend-patterns.md) for framework-neutral UI patterns
(state placement, forms, performance) and [../concurrency-patterns.md](../concurrency-patterns.md).

Checked against Swift 6.4 and Xcode 27. Observation needs iOS 17, macOS 14 and aligned releases;
older deployment targets stay on `ObservableObject`.

---

## What SwiftUI and Swift already give you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Observer** | `@Observable`; `withObservationTracking`; `Observations` (OS 26+) | No delegate or notification plumbing for model-to-view updates. Writing the `Observable` protocol by hand adds nothing: use the macro |
| **Decorator** | `ViewModifier`, wrapped in a `View` extension | Worth it for a bundle reused across screens. A one-off chain of modifiers needs no type |
| **Strategy** | `ButtonStyle` and similar styles; a closure; a generic `some` parameter | A style covers a whole hierarchy with `.buttonStyle`. For a single method, pass a closure rather than define a protocol |
| **Registry / Provider** | `@Environment`, `@Entry` for custom values | Reading a missing object by type throws at runtime. Declare it optional if presence is not guaranteed |
| **Singleton** | An object placed in the environment from the `App` | A mutable `static var` fails strict concurrency checking. An environment object is also easy to replace in a preview or test |
| **Repository / Active Record** | SwiftData: `@Model`, `ModelContext`, `@Query` | `@Query` keeps a view in sync, and outside views you use `FetchDescriptor`. Do not wrap it in a repository without a named second store |
| **State** | An `enum` with associated values and an exhaustive `switch` | Not four booleans. Adding a case breaks every `switch` that has no `default`, which is the point |
| **Flyweight** | `List`, whose content closure runs lazily | Each row depends only on what it reads. Keep row views small so that this helps |
| **Front Controller** | `NavigationStack(path:)` with `navigationDestination` | The path is plain state, which gives deep links and restoration without a coordinator class. `NavigationView` is deprecated. Cost: mixed destinations need `NavigationPath` |

---

## SwiftUI state ownership

The question for every property is **who owns this?** One source of truth, declared in the
highest view that needs it.

| Situation | Use | Note |
|---|---|---|
| A view owns a value | `@State private var` | Always `private`: a memberwise init would conflict with SwiftUI's storage |
| A child reads it | A plain `let` | SwiftUI re-renders it when the value changes |
| A child writes it | `@Binding`, passed with `$` | Only for the parent's source of truth, never a local copy |
| A view owns an observable model | `@State private var model = Model()` | The same wrapper as for values |
| A child reads the model | A plain property | The dependency forms where `body` reads, not where it is passed |
| A child needs bindings into the model | `@Bindable` | Works on local variables in a `List` row too |
| Many descendants need it | `.environment(model)` and `@Environment(Model.self)` | Hides the dependency. In a shallow tree, just pass it |
| Before iOS 17 | `@StateObject`, `@ObservedObject`, `@EnvironmentObject` | Legacy. A `State` holding an `ObservableObject` only updates when the reference changes |

**With Xcode 27, `State` is a macro.** Classes in `@State` are created once per view lifetime,
and this is back-deployed to iOS 17. Earlier, the initial expression ran on every view init and
the extras were thrown away. It can break source: a property with both a default value and an
assignment in `init` must drop the default. Move slow setup to `.task`, which is cancelled when
the view goes away. That is cooperative, and does not reach a `Task.detached` started inside.

### What Observation tracks

Only properties read in `body`, including through computed properties. A collection is tracked
as a whole for insertions and removals, while a lazy `List` row depends only on what that row
reads. This is why `@Observable` replaced `ObservableObject`, where any `@Published` change
updated every observer. **Migration cost:** views that relied on broad updates can stop
refreshing, so review their reads. Use `@ObservationIgnored` for bookkeeping properties.

A model class is justified for shared, identity-bearing state, or logic tested without a view.
A view model per screen is a choice, not a framework requirement. Its cost is one more type
and shared mutation through a reference.

---

## Protocols: the most-argued decision

"Start with a protocol" comes from a 2015 Apple talk arguing against starting with a *class*. It
does not ask for one protocol per type. Apple's 2022 generics talk starts from concrete structs
and generalises when repeated overloads appear, and its guidance prefers protocols to class
inheritance for hierarchies. Together: **concrete first, then a protocol, not a superclass.**

**Justified when:**
- Two or more real types share a capability, including across structs, enums and classes.
- A test fake is a genuine second conformer that makes a test possible or much simpler.
- A framework or generic algorithm requires it.

**Not justified:**
- `FooProtocol` with one `Foo` and no fake. Extract the protocol when a second conformer appears.
  The API guidelines keep the `Protocol` suffix for name collisions, not as a default.
- One-method protocols where a closure would do.
- Protocols shaped around a single implementation; requirements should be the minimum callers use.

**The costs that get forgotten:**
- **`any` is not free.** It is a box: values may be heap-allocated, and calls go through pointer
  indirection and dynamic dispatch. Associated types in parameter position become uncallable
  without unboxing. Write `some` by default, and `any` when a value really must store mixed types.
- **Extension methods are not overrides.** A method only in a protocol extension is shadowed, not
  replaced: code holding the protocol type calls the extension's version. If conformers must
  customise it, make it a requirement.

---

## Value types

Use **structs by default**. Change stays local unless passed on explicitly, which is the local
reasoning that protocol-oriented design is really after. Use a class when you control identity
(a file handle, a connection) or need Objective-C interoperability. If identity lives elsewhere,
such as a server record, use a struct with a `let` id.

Standard-library collections copy only when mutated. Cost: a change must be passed back
explicitly, and a struct holding a class reference shares that object between its copies.

---

## Actors and strict concurrency

**Add concurrency only as needed.** Apple's own progression is single-threaded code, then async,
then concurrent code, then actors, and many apps stop early. Asynchronous single-threaded code
is often enough, and profiling should justify the rest.

- **Main actor first.** SwiftUI's `View` is `@MainActor`, and Xcode 26 enabled main-actor default
  isolation for new app projects. Without that setting, unannotated code stays `nonisolated`.
  Apply it to app and UI modules. Libraries should stay `nonisolated` so that callers decide.
- **Read the build settings before reasoning about `async`.** With
  `NonisolatedNonsendingByDefault` a `nonisolated async` function stays on the caller's actor.
  Without it, the function leaves the actor. The same code behaves differently per module.
- **`@concurrent`** marks work that must leave the actor, such as decoding. Keep state in the caller.
- **`actor`** suits mutable state whose work is too heavy for the main thread, such as a network
  manager. Cost: every outside access is `await`, and models for the UI belong on the main actor.
- **Actors do not make multi-step logic atomic.** Only one task runs at a time, but interruption
  happens at each `await`. Re-check assumptions after one; keep invariant updates synchronous.
- **`Sendable`:** value types of `Sendable` members qualify, and actors always do. `@unchecked
  Sendable` turns the compiler off and leaves proof to you, so reserve it for lock-guarded code.
  Global mutable variables are errors in the Swift 6 language mode.
- **`Task {}`** inherits actor isolation and is yours to manage. `Task.detached` inherits neither
  isolation, priority nor task-local state, so it is rarely what you mean.
- **Adopting Swift 6 mode:** migrate module by module, outer modules first. In Swift 5 mode,
  `-strict-concurrency=complete` shows issues as warnings, and hundreds are normal.

---

## Swift features that replace patterns

| Feature | Replaces | Cost or limit |
|---|---|---|
| **`enum` + exhaustive `switch`** | State, Visitor | Closed set: adding a case touches each switch |
| **Closures** | Single-method Strategy, Command | Capturing mutable state needs care across isolation |
| **`some` generics** | Runtime Strategy when the type is fixed by the caller | One concrete type per use |
| **Typed `throws`, `Result`** | Custom result wrappers | `Result` is for storing outcomes; plain `throws` reads better otherwise |

---

## Going against the grain — signs you are fighting the framework

- `@ObservedObject` for an object a view creates, or new `ObservableObject` code on iOS 17+.
- `@State` that is not `private`, or that shadows a value the parent owns.
- `FooProtocol` beside every `Foo`, or `[any Thing]` where one type would do.
- Coordinators wrapping what `NavigationStack(path:)` already models.
- `@unchecked Sendable` or `nonisolated(unsafe)` added to silence a warning.
- `Task.detached` used as "run this in the background" by reflex.
- Actors added without a profile showing main-thread pressure.
- Assuming state is unchanged across an `await` inside an actor.

---

## Sources

- [Model data](https://developer.apple.com/documentation/swiftui/model-data), [`State`](https://developer.apple.com/documentation/swiftui/state), [managing model data](https://developer.apple.com/documentation/swiftui/managing-model-data-in-your-app), [migrating to `@Observable`](https://developer.apple.com/documentation/swiftui/migrating-from-the-observable-object-protocol-to-the-observable-macro), [`Environment`](https://developer.apple.com/documentation/swiftui/environment), [`EnvironmentValues`](https://developer.apple.com/documentation/swiftui/environmentvalues), [Observation](https://developer.apple.com/documentation/observation), [`Observations`](https://developer.apple.com/documentation/observation/observations)
- [`ViewModifier`](https://developer.apple.com/documentation/swiftui/viewmodifier), [`ButtonStyle`](https://developer.apple.com/documentation/swiftui/buttonstyle), [`NavigationStack`](https://developer.apple.com/documentation/swiftui/navigationstack), [migrating to new navigation types](https://developer.apple.com/documentation/swiftui/migrating-to-new-navigation-types), [SwiftData: preserving model data](https://developer.apple.com/documentation/swiftdata/preserving-your-apps-model-data-across-launches), [`Sendable`](https://developer.apple.com/documentation/swift/sendable), [`Result`](https://developer.apple.com/documentation/swift/result), [choosing between structures and classes](https://developer.apple.com/documentation/swift/choosing-between-structures-and-classes)
- *The Swift Programming Language*: [Concurrency](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/), [Protocols](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/protocols/), [Structures and Classes](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/classesandstructures/), [Enumerations](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/enumerations/), [Control Flow](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/controlflow/), [Error Handling](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/errorhandling/)
- [Swift 6 migration guide](https://www.swift.org/migration/documentation/migrationguide/), [API design guidelines](https://www.swift.org/documentation/api-design-guidelines/), [SE-0335](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0335-existential-any.md), [SE-0461](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0461-async-function-isolation.md), [SE-0466](https://github.com/swiftlang/swift-evolution/blob/main/proposals/0466-control-default-actor-isolation.md)
- WWDC sessions: [Protocol-Oriented Programming in Swift (2015)](https://developer.apple.com/videos/play/wwdc2015/408/), [Protocol and Value Oriented Programming in UIKit Apps (2016)](https://developer.apple.com/videos/play/wwdc2016/419/), [Embrace Swift generics (2022)](https://developer.apple.com/videos/play/wwdc2022/110352/), [Design protocol interfaces in Swift (2022)](https://developer.apple.com/videos/play/wwdc2022/110353/), [Analyze hangs with Instruments (2023)](https://developer.apple.com/videos/play/wwdc2023/10248/), [Embracing Swift concurrency (2025)](https://developer.apple.com/videos/play/wwdc2025/268/), [What's new in SwiftUI (2026)](https://developer.apple.com/videos/play/wwdc2026/269/)

All commentary here is original.
