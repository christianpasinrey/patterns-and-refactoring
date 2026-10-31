# Kotlin · Ktor

[← back to router](../framework-idioms.md)

Checked against Kotlin 2.4 and Ktor 3.6 (October 2026). Kotlin on Spring: read
[spring-java.md](spring-java.md) for the container and this file for the language.

---

## What Ktor already gives you

Ktor is a toolkit, not a container. It installs nothing by default, so much of what Spring does
implicitly is a line you write here, and the rest is plain Kotlin.

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Chain of Responsibility** | Installed plugins around the pipeline; `Routing` is itself a plugin | A plugin, not a wrapper around handlers. Not for logic one route needs: that is a function call |
| **Decorator (per route)** | `createRouteScopedPlugin`; `install` inside a `route` block | Route-level configuration overrides global. Repeating a route takes the last install, which is easy to misread |
| **Front Controller** | `routing { }` | Group with `route` and split with `fun Route.orders()`. An interface per route group adds nothing |
| **Abstract Factory + DI** | `ktor-server-di` (`provide`, `resolve`, `by dependencies`); or constructor arguments | Plain arguments in `fun Application.module()` are enough for a small service. See the decision below |
| **Factory Method** | `provide<() -> T> { { ... } }`; top-level functions | The DI plugin calls a provider when resolving; register a factory lambda only for a real need for new instances |
| **Observer** | `monitor.subscribe`, `EventDefinition<T>`, `monitor.raise` | Documented for lifecycle and server events. Delivery guarantees for domain events are not stated, so do not build one on it without testing |
| **Strategy** | A function-typed parameter; `fun interface`; `provide("name")` + `@Named` | Start with a function. Add a named binding only when the variants are chosen by configuration |
| **Template Method** | Higher-order function taking a lambda; `suspend` wrappers | `withRetry { }` beats an abstract base class. Cost: an `inline` lambda bloats call sites, a non-inline one allocates |
| **Adapter** | `ContentNegotiation`; `call.receive<T>()`, `call.respond(obj)` | Let it map request and response bodies. Hand-parsing belongs only where the format is truly unusual |
| **Exception Shielding** | `StatusPages` (`exception<T>`, `status`) | One place for error responses. A catch-all handler turns every bug into the same reply, so map specific types |
| **Validation** | `RequestValidation` (`validate<T>`) | Boundary shape checks only. Domain rules belong in the domain |
| **Authentication** | `Authentication` + `authenticate("name") { }`, `call.principal<T>()` | Scope with the route block, not an `if` in each handler |
| **Rate Limiter** | `RateLimit` + `rateLimit()` | Check what one instance's limit means once you run several |
| **Retry** | Client `HttpRequestRetry` (`retryOnServerErrors`, `exponentialDelay`) | Client-side only, and repeats side effects unless the call is idempotent |
| **Logging Decorator** | `CallLogging` | Not a home-grown interceptor |

Plugin order is not documented as install order. The docs define precedence between route and
global installs, and ordered phases inside a pipeline, nothing more. If two plugins depend on
order, pin it with a test rather than a comment.

---

## Custom plugin or plain function?

```kotlin
val RequestId = createApplicationPlugin("RequestId") {
    onCall { call -> call.response.headers.append("X-Request-Id", newId()) }
}
```

Handlers are `onCall`, `onCallReceive`, `onCallRespond` and `on(...)` hooks such as
`ResponseSent` and `CallFailed`. `call.attributes` shares values between them.

**A custom plugin is justified when:**

- The concern applies to many routes and must see every call, including failures: request IDs, metrics, tenant resolution.
- It needs a lifecycle hook, through `MonitoringEvent`.

**Not justified when:**

- One or two routes need it. Call a function. A plugin hides control flow; a call is visible where it runs.
- It reaches business data. Plugins are for transport concerns. A plugin that loads an order is a service wearing a costume.

Configuration passed to a plugin stays mutable during installation, so copy values into local
variables if handlers use them. Reach for the base pipeline API only when the simplified API
has no equivalent hook: it needs knowledge of phases.

---

## Do you need a DI container at all?

The third router question has a real answer here, since the default is no container.

**The `ktor-server-di` plugin is justified when:**

- Several modules need the same graph, or startup is concurrent and one module must wait for a dependency that another provides: `resolve()` suspends until it is ready.
- Tests need to swap implementations. Test environments default to the `IgnoreConflicts` policy, so a test override does not fail.
- Resources need shutdown handling. `AutoCloseable` instances are closed at stop by default, and a reported double-close means `close()` should be idempotent.

**Not justified when:**

- One `Application.module()` builds everything. Constructor calls are compile-checked. A plugin swaps that for a startup check.
- You add it "for later". Moving from arguments to `provide` is mechanical, so wait for the second module.

---

## Kotlin features that replace patterns

| Feature | Replaces | Cost or limit |
|---|---|---|
| **`sealed` + exhaustive `when`** | Visitor, State, Result types | Closed by design: direct subclasses stay in the same package and module. Plugin-style extension needs an interface. Adding `else` silently drops the exhaustiveness check |
| **`data class`** | Value Object, DTO, Prototype via `copy()` | `equals` covers primary-constructor properties only, and `copy()` is shallow, so shared mutable lists leak |
| **`@JvmInline value class`** | Primitive Obsession (`OrderId`, `Email`) | Boxes when used as a generic, interface or nullable. Function names get mangled for Java callers |
| **`by` class delegation** | Decorator, Proxy forwarding | The delegate never sees your overrides. A forwarded method calling another still runs the delegate's version. Use real inheritance if you need that |
| **`by lazy`, `Delegates.observable`, `vetoable`** | Lazy Initialization, Observer on one property | `lazy` is `SYNCHRONIZED` by default, a small cost on hot paths. `observable` is not an event system |
| **`object`** | Singleton as a keyword | Thread-safe and lazy, and still a global. Read [antipatterns.md](../antipatterns.md#singleton) first. Inject anything with state |
| **`companion object`** | Static Factory | Members look static but belong to an instance; plain top-level functions are often simpler |
| **Default and named arguments** | Builder, telescoping constructors | Java sees the full signature unless you add `@JvmOverloads`, which cannot go on abstract methods |
| **Extension functions** | Introduce Foreign Method | Resolved statically from the declared type, and a matching member always wins. So they are not Decorator, whatever the name suggests |
| **Lambdas with receiver + `@DslMarker`** | Builder, for configuration | A DSL is an API to maintain. Use a plain constructor when one call is enough |
| **`fun interface` or `typealias`** | Strategy, Command | Prefer a function type; a `fun interface` when you need a name, members or extensions |
| **`Result<T>`, `runCatching`** | Railway error handling | `runCatching` catches every `Throwable`. That includes `CancellationException`, so never wrap a `suspend` call in it without rethrowing. For modelled errors use a `sealed` result |
| **`when` guards** | Nested conditionals in dispatch | Keep guards short, or the branch list stops reading as a table |

Rich errors have been discussed publicly, are not in Kotlin 2.4, and are not a current option.

---

## Coroutines instead of concurrency patterns

Structured concurrency is the pattern. Coroutines form a tree: a parent waits for its children,
and cancelling or failing a parent cancels them. See
[concurrency-patterns.md](../concurrency-patterns.md).

| Need | Use | Cost or limit |
|---|---|---|
| **Fork-join** | `coroutineScope { async { } }` | One child failing cancels its siblings. That is usually what you want |
| **Bulkhead for children** | `supervisorScope`, `SupervisorJob` | Failures stop propagating, so every child must handle its own |
| **Producer-Consumer** | `Channel`, `produce` | Default capacity is rendezvous, which suspends the sender until received; capacity buffers memory |
| **Pipes and Filters** | `Flow` operators, or `produce` stages | A cold `Flow` restarts per collector, so a shared expensive source repeats its work |
| **Observer, in-process** | `SharedFlow`, `StateFlow` | `StateFlow` conflates: slow collectors miss intermediate values, so it is state, not an event log |
| **Thread confinement** | `withContext` on a single-thread context, coarse-grained | Fine-grained hops are slow, and a dedicated thread must be closed |
| **Mutual exclusion** | `Mutex.withLock` | Suspends, does not block. Pays per lock; use atomics for simple counters |
| **Offloading blocking work** | `withContext(Dispatchers.IO)` | Shared pool, capped by default at 64 threads or the core count, whichever is larger. Not for CPU-bound work |

The `actor` builder carries `@ObsoleteCoroutinesApi`; prefer a `Channel` and a coroutine.

**In Ktor, know whose scope you are in.** `RoutingHandler` is a `suspend` function, and
`launch` inside it belongs to the call. `Application` is itself a `CoroutineScope`, cancelled
immediately at stop, so use it for work that must outlive the request; such work needs its own
error handling. By default Ktor keeps processing after a client disconnects: the
`HttpRequestLifecycle` plugin with `cancelCallOnClose` changes that on CIO and Netty, and
blocking code must still check `call.coroutineContext.ensureActive()`.

`GlobalScope` is a delicate API: nothing can cancel or wait for its coroutines, and failures
reach the platform's last-resort handler. It is justified only for a process-long background
loop with its own `CoroutineExceptionHandler`. A `CoroutineScope().launch { }` replacement has
the same pitfalls.

---

## Signs you are fighting the framework

- A `BaseController` or `BaseHandler` class in a routing DSL that has no such concept.
- Classes wrapping `call` so that handlers can be "framework independent", with one framework.
- `runBlocking` inside a request handler. It blocks the current thread; handlers are already `suspend`.
- `GlobalScope.launch` for fire-and-forget work in a route.
- `catch (e: Exception)` around `suspend` calls with no rethrow, swallowing cancellation.
- `else` in a `when` over your own sealed hierarchy.
- `object` holding mutable state, shared between tests.
- A DI container for four classes in one module.
- Plugins that depend on another plugin's order with no test pinning it.

---

## Sources

- Kotlin: [releases](https://kotlinlang.org/docs/releases.html), [sealed classes](https://kotlinlang.org/docs/sealed-classes.html), [data classes](https://kotlinlang.org/docs/data-classes.html), [inline value classes](https://kotlinlang.org/docs/inline-classes.html), [delegation](https://kotlinlang.org/docs/delegation.html), [delegated properties](https://kotlinlang.org/docs/delegated-properties.html), [object declarations](https://kotlinlang.org/docs/object-declarations.html), [extensions](https://kotlinlang.org/docs/extensions.html), [functional interfaces](https://kotlinlang.org/docs/fun-interfaces.html), [functions](https://kotlinlang.org/docs/functions.html), [inline functions](https://kotlinlang.org/docs/inline-functions.html), [calling Kotlin from Java](https://kotlinlang.org/docs/java-to-kotlin-interop.html), [type-safe builders](https://kotlinlang.org/docs/type-safe-builders.html), [control flow](https://kotlinlang.org/docs/control-flow.html), [`runCatching`](https://kotlinlang.org/api/core/kotlin-stdlib/kotlin/run-catching.html), [language features and proposals](https://kotlinlang.org/docs/kotlin-language-features-and-proposals.html), [What's new in 2.4.0](https://kotlinlang.org/docs/whatsnew24.html)
- Coroutines: [basics](https://kotlinlang.org/docs/coroutines-basics.html), [exception handling](https://kotlinlang.org/docs/exception-handling.html), [channels](https://kotlinlang.org/docs/channels.html), [flow](https://kotlinlang.org/docs/coroutines-flow.html), [shared mutable state](https://kotlinlang.org/docs/shared-mutable-state-and-concurrency.html), [context and dispatchers](https://kotlinlang.org/docs/coroutine-context-and-dispatchers.html), API: [`GlobalScope`](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/-global-scope/), [`StateFlow`](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/-state-flow/), [`Dispatchers.IO`](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/-dispatchers/-i-o.html), [`actor`](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.channels/actor.html)
- Ktor: [server plugins](https://ktor.io/docs/server-plugins.html), [custom plugins](https://ktor.io/docs/server-custom-plugins.html), [base API](https://ktor.io/docs/server-custom-plugins-base-api.html), [routing](https://ktor.io/docs/server-routing.html), [modules](https://ktor.io/docs/server-modules.html), [dependency injection](https://ktor.io/docs/server-dependency-injection.html), [registration](https://ktor.io/docs/server-di-dependency-registration.html), [resolution](https://ktor.io/docs/server-di-dependency-resolution.html), [DI configuration](https://ktor.io/docs/server-di-configuration.html), [events](https://ktor.io/docs/server-events.html), [HTTP request lifecycle](https://ktor.io/docs/server-http-request-lifecycle.html), [status pages](https://ktor.io/docs/server-status-pages.html), [client retry](https://ktor.io/docs/client-request-retry.html), [`Application` API](https://api.ktor.io/ktor-server-core/io.ktor.server.application/-application/index.html), [`RoutingHandler` API](https://api.ktor.io/ktor-server-core/io.ktor.server.routing/-routing-handler/index.html), [`DependencyInjectionConfig` API](https://api.ktor.io/ktor-server-di/io.ktor.server.plugins.di/-dependency-injection-config/index.html), [3.5 changelog](https://ktor.io/changelog/3.5/), [authentication](https://ktor.io/docs/server-auth.html), [rate limit](https://ktor.io/docs/server-rate-limit.html), [content negotiation](https://ktor.io/docs/server-serialization.html), [request validation](https://ktor.io/docs/server-request-validation.html), [call logging](https://ktor.io/docs/server-call-logging.html)
