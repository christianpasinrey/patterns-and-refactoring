# Angular · TypeScript

[← back to router](../framework-idioms.md)

See also [../frontend-patterns.md](../frontend-patterns.md) for framework-neutral frontend
patterns (state placement, data fetching, rendering strategies).

Checked against Angular 22.2. Defaults moved quickly: standalone since v19, zoneless since v21,
`OnPush` since v22. Advice older than that, including what you may remember, is often wrong.

---

## What Angular already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Singleton** | `@Service()`, or `@Injectable({providedIn: 'root'})` | `@Service()` for a root singleton built with `inject()`. Use `@Injectable` for constructor injection, a non-root scope or `useClass`-style providers. A singleton is app-wide state: scope it lower if one screen uses it |
| **Observer** | `signal`, `computed`, `effect` for state; RxJS for event streams | Never build a subject-based bus for state. A read-only signal stops `set`, not deep mutation of its value |
| **Strategy** | A provider swap: `useClass`, `useFactory`, an `InjectionToken` | Needs two real implementations. A token with one implementation is a harder-to-find direct call |
| **Chain of Responsibility** | Functional interceptors via `withInterceptors`; route guards | Interceptors run in list order; class-based ones are harder to order. **Guards are UX, never access control:** the server must enforce it too |
| **Decorator** | `hostDirectives` | Applied statically at compile time, so never at runtime. Their inputs stay private until you list them, which is one more mapping to maintain |
| **Template Method** | `ng-template` + `NgTemplateOutlet` with context | For conditional content too: `ng-content` always instantiates what it projects, so wrapping it in `@if` saves nothing |
| **Facade** | A service exposing `asReadonly()` signals and methods | Add it when several components share the state, not as a mandatory layer per component |
| **State** | A discriminated union with `@switch` and `@default never;` | Not four booleans. The check needs a variable, not a call: bind with `@let` first |
| **Iterator** | `@for` with `track` | Track a stable id. `$index` suits static lists only; tracking the item itself is the last resort |
| **Flyweight** | CDK `cdk-virtual-scroll-viewport`; pure pipes | The stable strategy assumes a fixed `itemSize`; autosize is experimental. Pure pipes re-run on a new reference only, so in-place mutation is missed |
| **Lazy Load / Proxy** | `loadComponent`, `loadChildren`, `@defer` | Later navigation costs extra requests, and nested lazy levels hurt. Keep landing pages eager; do not defer what is visible on first load |

---

## Signals vs RxJS: the most-argued decision

Ask one question: **is there always a current value?** A signal is a value that changes. An
Observable is a sequence of things that happen. Signals are not a replacement for RxJS; the
real mistake is using either for the other's job.

**Signals are justified when:**
- A template or a `computed` reads the value.
- The state is derived, because `computed` is lazy, memoized and tracks only what it read.

**RxJS is justified when:**
- Time is the point: debouncing, retry, or merging several event sources.
- The source is already an Observable, such as `HttpClient` calls in a service.
- Cost: an operator vocabulary, and every subscription needs an owner. `takeUntilDestroyed`
  handles that, but outside an injection context it needs an explicit `DestroyRef`.

**Not justified:**
- A `BehaviorSubject` that only holds a value a signal could hold.
- A `toObservable` then `toSignal` round trip to map a value. That is a `computed`.
- `toSignal` called repeatedly on one Observable: each call subscribes, so reuse the signal.

**Bridge behaviour that surprises people:**
- `toSignal` subscribes immediately, reads `undefined` until the first emission unless given
  `initialValue` or `requireSync`, and rethrows Observable errors when the signal is read.
- `toObservable` emits only the settled value: set 1, 2, 3 in a row and subscribers see 3. It
  cannot stand in for an event stream.

---

## `effect` is the last API to reach for

The docs say so directly. Propagating state through effects risks
`ExpressionChangedAfterItHasBeenChecked`, circular updates and extra change detection.

| You are doing this | Do this instead |
|---|---|
| `effect` copying one signal into another | `computed`, or move the source of truth higher |
| `effect` resetting a choice when its options change | `linkedSignal`: writable, and it resets from its source |
| `effect` fetching on a signal change | `resource` or `httpResource` |
| `effect` measuring the DOM | `afterRenderEffect` with an explicit phase; omitting it can add reflows |

**Legitimate uses** sync signals to something non-reactive: logging, `localStorage`, a canvas,
a charting library. Read signals before any `await`, because later reads are not tracked.

---

## Resource APIs

`resource`, `httpResource` and `rxResource` are stable since v22. They replace the
loading-flag-plus-subscribe boilerplate for **reads**.

- **Choose by source:** `httpResource` over `HttpClient` (interceptors keep working), `resource`
  for any Promise, `rxResource` for an Observable loader, the `stream` option for sockets.
- **Race handling is built in:** a new request cancels the pending one. A `resource` loader
  must pass `abortSignal` to `fetch` for the HTTP call itself to stop.
- **Guard reads:** `value()` throws in the `error` state, so check `hasValue()` first. In
  `loading` the value is `undefined`; only `reloading` keeps the previous one, so a changed
  parameter blanks the UI unless you design for it.
- **Never for mutations.** `httpResource` is the wrong tool for POST or PUT, because re-runs
  and cancellation are harmless only for reads. Call `HttpClient` and then `reload()`.

---

## Dependency injection: where to provide

Lookup walks element injectors upward, then environment injectors, then throws unless optional.
**The first match wins**, so a local provider silently shadows one further up.

| Provide in | Lifetime and visibility | Use when | Cost |
|---|---|---|---|
| `@Service()` | One instance, root | Most shared services | Tree-shakable, but global by default |
| `ApplicationConfig` | One instance, root | Global setup: `provideHttpClient(...)` | Always bundled |
| Route `providers` | That route and its children | A feature section | Unavailable outside it |
| Component `providers` | One per component instance, destroyed with it | Per-editor or per-dialog state | Projected content sees it too |
| Component `viewProviders` | The component's own view only | Hiding a dependency from projected content | Harder to trace |

**The SSR trap:** top-level providers are evaluated once when the server loads, so a `useValue`
persists across requests and can leak between users. `useFactory` runs per request.

---

## Standalone, control flow and defaults

- **Standalone is the default,** recommended over `NgModule` for all new code, and `@defer` can
  only split standalone dependencies. Cost: repeated `imports` lists.
- **Built-in control flow** is `@if`, `@for`, `@switch`. `NgIf` and `NgFor` are deprecated since
  v20 with intent to remove, so `*ngIf` and `*ngFor` are legacy in new templates.
- **Zoneless by default (v21+).** Change detection follows notifications: template-read signals,
  `markForCheck`, bound listeners. A plain field changed in a timer does nothing, and
  `NgZone.onStable` never emits, so use `afterNextRender`.
- **`OnPush` by default (v22).** A subtree is checked on new inputs or an event inside it.
  Mutating an input object in place changes nothing, because the reference is identical.

### State placement, in order

1. **Can it be derived?** → `computed`. Do not store it.
2. **One component?** → a `signal` in that component.
3. **Server data?** → a resource, not a hand-written store.
4. **A subtree or feature section?** → a service in component or route `providers`.
5. **App-wide client state?** → a `@Service()` with a private signal exposed by `asReadonly()`.

---

## Framework features that replace patterns

| Feature | Replaces |
|---|---|
| **`input.required<T>()`** | Runtime "was this set?" checks: a missing input is a build error |
| **`model()`** | A hand-paired input and change output; transforms are not supported |
| **`linkedSignal`** | Effects resetting state. With `previous` it can keep a still-valid choice |
| **Signal Forms** (`@angular/forms/signals`, stable since v22) | Hand-rolled form state in new signal-based apps. Existing reactive forms remain a solid choice, so do not migrate for its own sake |

---

## Going against the grain — signs you are fighting the framework

- New `NgModule`s, or `*ngIf` and `*ngFor` in new templates.
- `BehaviorSubject` as a default state holder where a signal would do.
- `effect` keeping two signals in sync.
- Manual subscriptions in a component with no teardown.
- `@Injectable({providedIn: 'root'})` holding state that belongs to one screen.
- Treating a route guard as the security boundary.
- Relying on `NgZone.onStable`, or on timers to "make the view update".

---

## Sources

- [Signals](https://angular.dev/guide/signals), [effects](https://angular.dev/guide/signals/effect), [`linkedSignal`](https://angular.dev/guide/signals/linked-signal), [resource](https://angular.dev/guide/signals/resource), [`httpResource`](https://angular.dev/guide/http/http-resource), [interceptors](https://angular.dev/guide/http/interceptors)
- [RxJS interop](https://angular.dev/ecosystem/rxjs-interop), [`takeUntilDestroyed`](https://angular.dev/ecosystem/rxjs-interop/take-until-destroyed), [hierarchical injectors](https://angular.dev/guide/di/hierarchical-dependency-injection), [providers](https://angular.dev/guide/di/defining-dependency-providers), [services](https://angular.dev/guide/di/creating-and-using-services)
- [Components](https://angular.dev/guide/components), [content projection](https://angular.dev/guide/components/content-projection), [`ng-template`](https://angular.dev/guide/templates/ng-template), [directive composition](https://angular.dev/guide/directives/directive-composition-api), [control flow](https://angular.dev/guide/templates/control-flow), [`@defer`](https://angular.dev/guide/templates/defer), [pipes](https://angular.dev/guide/templates/pipes), [`NgIf`](https://angular.dev/api/common/NgIf), [`NgFor`](https://angular.dev/api/common/NgFor)
- [Route guards](https://angular.dev/guide/routing/route-guards), [loading strategies](https://angular.dev/guide/routing/loading-strategies), [defining routes](https://angular.dev/guide/routing/define-routes), [zoneless](https://angular.dev/guide/zoneless), [`OnPush` subtrees](https://angular.dev/best-practices/skipping-subtrees), [SSR](https://angular.dev/guide/ssr), [Signal Forms](https://angular.dev/guide/forms/signals/overview), [releases](https://angular.dev/reference/releases)
- [CDK scrolling source docs](https://github.com/angular/components/blob/main/src/cdk/scrolling/scrolling.md)

All commentary here is original.
