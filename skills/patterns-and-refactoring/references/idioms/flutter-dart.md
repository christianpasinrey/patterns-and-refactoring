# Flutter · Dart

[← back to router](../framework-idioms.md)

See also [../frontend-patterns.md](../frontend-patterns.md) for framework-neutral UI patterns
(state placement, forms, performance) and [../concurrency-patterns.md](../concurrency-patterns.md).

Checked against Flutter 3.47, Dart 3.13, Riverpod 3 and flutter_bloc 9.

---

## What Flutter already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Composite** | The widget tree | Build a new widget from existing ones. Do not subclass `Container` |
| **Decorator** | Wrapper widgets: `Padding`, `Center`, `Align` | Wrap rather than add options. Toggling a wrapper in and out changes tree depth and forces a full rebuild, so prefer flipping a property (`IgnorePointer.ignoring`) |
| **Strategy** | A function parameter: `onTap`, `itemBuilder` | A callback is enough for one method. An abstract class needs two real variants |
| **Template Method** | The `State` lifecycle: `initState`, `dispose`, `build` | Allocate in `initState`, release in `dispose`. Keep `build` free of side effects: it can run every frame |
| **Observer** | `ChangeNotifier`, `ValueNotifier`, `Stream`, with `ListenableBuilder` | `ValueNotifier` fires only when `==` says the value changed, so mutating a list in place is silent. Use immutable values, or `ChangeNotifier` and call `notifyListeners()` yourself |
| **Registry / Provider** | `InheritedWidget`, as in `Theme.of(context)`; `package:provider` | Reading through `of` subscribes the caller, so a frequently changing value rebuilds every reader. `InheritedModel` narrows that, at more code |
| **Command** | `Intent` + `Action`; a Command class in a view model | Intents pay off when keys, buttons and menus share an operation or it needs an enabled state. For one button, use a callback |
| **State** | A `sealed` class with a `switch` | Not four booleans. The cost is that adding a case breaks every switch: usually what you want inside an app |
| **Flyweight** | `const` widgets; `ListView.builder` | `builder` builds visible children only. If order can change, supply `findChildIndexCallback` or risk state loss |
| **Front Controller** | `Router`, usually through go_router | `Navigator` alone suits small apps with simple deep links. Named routes are not recommended for most apps. Pageless routes cannot be deep-linked |

### Widgets are the pattern layer

The whole class hierarchy is deliberately shallow and broad, so that small single-purpose widgets
combine. `Container` itself is just a composition of simpler widgets. Reach for a new widget
class before an option flag, and **before a helper method**: a method returning widgets is
rebuilt whole with its parent, while a widget gets its own rebuild boundary and can be `const`.

Three trees exist. **Widgets** are immutable, disposable configuration. **Elements** persist
across frames. **RenderObjects** do layout and paint. Creating widget objects is cheap by design,
so measure before optimising. When a rebuild is really slow, push state down to the leaf that uses
it, cache unchanging subtrees in `final` fields or `const`, and pass static content through a
builder's `child`.

---

## State options, and when each is justified

| Option | Justified when | What it costs |
|---|---|---|
| **`setState`** | One widget's ephemeral state: a tab index, animation progress | The whole `build` re-runs. Refactor if other widgets start needing it |
| **`ValueNotifier`** + `ValueListenableBuilder` | A single value observed from outside the widget | One value only; see the equality trap above |
| **`ChangeNotifier`** + `ListenableBuilder` | A view model with several fields. No dependency needed | A forgotten `notifyListeners()` is a stale UI, and the owner must dispose it |
| **`InheritedWidget`** / `InheritedNotifier` | A value read across a subtree | Boilerplate. Its `context` must be a descendant, a classic assertion failure |
| **`provider`** | Injecting those same objects without the boilerplate | One dependency, and a runtime lookup rather than a compile-time one |
| **Riverpod or Bloc** | See below | A dependency, and a style the whole team adopts |

The docs' own rule of thumb is that there is no clear-cut rule: ephemeral state can grow into
app state, and the fix is a refactor, not a library chosen up front.

---

## Riverpod vs Bloc vs built-ins: the most-argued decision

The Flutter docs endorse no state package; the choice depends on complexity and team. Their
own architecture guide uses `ChangeNotifier` view models, as a conditional recommendation.

**Built-ins are justified when:**
- State is mostly per-screen, and view models over repositories cover it.
- You want no third-party upgrade path in the core of the app.
- Cost: you hand-write caching, retry and loading state, and keep discipline by review.

**Riverpod is justified when:**
- Much of the state is asynchronous data derived from other data. Providers cache, recompute on
  `ref.watch`, and dispose when unused.
- Cost: new vocabulary. `ref.watch` depends, `ref.read` is for one-off actions, and using it to
  dodge rebuilds makes the UI drift; use `select`.
- Cost: with code generation, state vanishes when the last listener leaves. Without auto-dispose,
  parameterised providers can leak one entry per parameter.
- Cost: failed providers retry automatically. Offline persistence and mutations are experimental,
  and `StateProvider` and `StateNotifierProvider` are legacy.

**Bloc is justified when:**
- You need an audit trail: a `Transition` records the event that caused each state.
- Events need operators, such as debouncing a search through an event transformer.
- Cost: event and state classes per feature, which is why its docs say to start with `Cubit` and
  move up only if needed. A Cubit gives up the event record.
- Rule: blocs must not depend on sibling blocs. Bridge through a `BlocListener` in the UI or a
  shared repository stream.

**Not justified:**
- Any library for ephemeral state. The docs are explicit that `setState` is enough there.
- Two state libraries in one app, without a migration under way.

### Layers, from the official architecture guide

Views hold widgets, with no business logic. View models turn app data into UI state, one per
view. Repositories are the source of truth; services wrap APIs and hold no state. A domain layer
is optional. These are guidelines, not rules. The guide strongly recommends abstract
repositories, so run that through the YAGNI gate: a test fake is a real second variant, while one
implementation and no fake is a guess. Its Command class earns its place only when several
actions need running and error state, and ready-made packages exist.

---

## Keys

Without a key, Flutter matches widgets by type and position. Stateful items in a list that
reorders can then keep the wrong state. **Add a key when siblings of one type can move, or when
state must reset on purpose.** Elsewhere, keys are noise.

| Key | Identity comes from | Use when | Watch out |
|---|---|---|---|
| `ValueKey` | The value's `==` | A stable id. The default choice | Must be unique among siblings |
| `ObjectKey` | Object identity (`identical`) | No id, but stable object instances | A rebuilt but equal object is a new key |
| `UniqueKey` | Nothing: equal only to itself | Forcing a fresh element | Created in `build`, it discards the subtree on every rebuild |
| `GlobalKey` | App-wide uniqueness | Moving a subtree while keeping state, or reaching `State` from outside | Expensive reparenting. A duplicate asserts at runtime; a new one in `build` drops state. Own it in `State` |

---

## Isolates: use one when a frame is at risk

`async` does not mean parallel: a long synchronous parse in a `Future` still blocks the frame.
The docs' one hard rule is to use an isolate when a large computation causes jank (16ms at 60Hz).

- **One-off work:** `Isolate.run`, which transfers its result rather than copying it. Use
  `compute` when the code also targets web.
- **Repeated work:** a long-lived isolate with ports. A robust one needs request ids and shutdown.
- **No shared memory:** messages are copied, immutable objects are shared. Globals are per
  isolate, so a change in a worker is invisible to the main isolate.
- **Limits:** no UI work, `dart:ui` or `rootBundle` in a spawned isolate. Plugins need
  `BackgroundIsolateBinaryMessenger`, and host-initiated messages do not arrive.
- **Web:** isolates are not supported. `compute` runs on the main thread, so it compiles and
  still janks.

---

## Dart features that replace patterns

| Feature | Replaces | Cost or limit |
|---|---|---|
| **`sealed` + `switch`** | Visitor, State | All direct subtypes must share a library. If outsiders must add subtypes, use `final` |
| **Extension types** | Wrapper-object Value Objects | Erased at runtime, so casts bypass them. The docs call them unsafe; use a class when an invariant must hold |
| **Class modifiers** (`final`, `base`, `interface`) | "Do not extend" comments | They apply outside the library only |
| **`freezed` / `built_value`** | Hand-written immutable models | Recommended by the Flutter guide, and adds code generation |

---

## Going against the grain — signs you are fighting the framework

- Subclassing `Container` or another layout widget to change its look.
- Business logic in widgets, or network calls started from `build`.
- A `Future` created inside `build` for a `FutureBuilder`: each rebuild restarts it.
- Mutating a list held in a `ValueNotifier` and expecting listeners to fire.
- `GlobalKey` as a way to call methods on a child.
- A `UniqueKey` in `build` "to fix" stale state.
- Helper methods that return large widget subtrees.
- Isolates added with no measured jank, or relied on for parallelism on web.

---

## Sources

- [Architectural overview](https://docs.flutter.dev/resources/architectural-overview), [`StatefulWidget`](https://api.flutter.dev/flutter/widgets/StatefulWidget-class.html), [`FutureBuilder`](https://api.flutter.dev/flutter/widgets/FutureBuilder-class.html), [`ListView.builder`](https://api.flutter.dev/flutter/widgets/ListView/ListView.builder.html), [navigation](https://docs.flutter.dev/ui/navigation), [actions and shortcuts](https://docs.flutter.dev/ui/interactivity/actions-and-shortcuts)
- [Ephemeral vs app state](https://docs.flutter.dev/data-and-backend/state-mgmt/ephemeral-vs-app), [state options](https://docs.flutter.dev/data-and-backend/state-mgmt/options), [`ValueNotifier`](https://api.flutter.dev/flutter/foundation/ValueNotifier-class.html), [`ListenableBuilder`](https://api.flutter.dev/flutter/widgets/ListenableBuilder-class.html), [`InheritedWidget`](https://api.flutter.dev/flutter/widgets/InheritedWidget-class.html), [architecture guide](https://docs.flutter.dev/app-architecture/guide), [recommendations](https://docs.flutter.dev/app-architecture/recommendations), [Command pattern](https://docs.flutter.dev/app-architecture/design-patterns/command)
- [`Key`](https://api.flutter.dev/flutter/foundation/Key-class.html), [`ValueKey`](https://api.flutter.dev/flutter/foundation/ValueKey-class.html), [`ObjectKey`](https://api.flutter.dev/flutter/widgets/ObjectKey-class.html), [`UniqueKey`](https://api.flutter.dev/flutter/foundation/UniqueKey-class.html), [`GlobalKey`](https://api.flutter.dev/flutter/widgets/GlobalKey-class.html), [Flutter isolates](https://docs.flutter.dev/perf/isolates), [Dart isolates](https://dart.dev/language/isolates)
- [Class modifiers](https://dart.dev/language/class-modifiers), [extension types](https://dart.dev/language/extension-types)
- [Riverpod providers](https://riverpod.dev/docs/concepts2/providers), [refs](https://riverpod.dev/docs/concepts2/refs), [auto-dispose](https://riverpod.dev/docs/concepts2/auto_dispose), [what's new in 3.0](https://riverpod.dev/docs/whats_new), [Bloc concepts](https://bloclibrary.dev/bloc-concepts/), [Flutter Bloc concepts](https://bloclibrary.dev/flutter-bloc-concepts/), [Bloc architecture](https://bloclibrary.dev/architecture/)

All commentary here is original.
