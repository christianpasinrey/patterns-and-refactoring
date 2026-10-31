# Blazor · .NET

[← back to router](../framework-idioms.md)

Checked against .NET 10 LTS (October 2026; .NET 11 is at release candidate). The general
ASP.NET Core catalogue is in [dotnet-csharp.md](dotnet-csharp.md); data access is in
[efcore-dotnet.md](efcore-dotnet.md).

---

## What Blazor already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Composite** | The component tree; `RenderFragment`, `ChildContent` | Compose components. A `RenderFragment` is code, so it cannot cross from a static parent into an interactive child |
| **Template Method** | `OnInitializedAsync`, `OnParametersSetAsync`, `OnAfterRenderAsync(firstRender)` | Override the hook. A custom component base class is the costly version: it adds a hierarchy every component inherits |
| **Strategy for markup** | Templated components: `RenderFragment<T>` parameters | Use when callers really vary the markup. With one caller it is a parameter nobody varies |
| **Observer (child to parent)** | `EventCallback<T>` | Not a C# `event`, not a shared service, when the parent is right there |
| **Observer (across the tree)** | A registered state container with an `event Action`; `INotifyPropertyChanged` with `CascadingValueSource` | Unsubscribe in `Dispose`, or the service keeps the component alive |
| **Mediator** | A parent cascading `this`, as a tab set does for its tabs | Fits a closely coupled family. The coupling is invisible in markup, so keep it inside one component set |
| **Dependency Injection** | `@inject`; constructor injection (.NET 9+); keyed via `[Inject(Key = "...")]` | Lifetimes do not mean what they mean in MVC. See the table below |
| **Unit of Work** | `IDbContextFactory<T>` with one context per operation | A scoped `DbContext` is shared across a circuit. See below |
| **Layout / Two Step View** | `LayoutComponentBase` and `@Body` | `Body` is a render fragment, so an interactive layout fails under per-page rendering. It needs global interactivity, or a static layout |
| **Form handling** | `EditForm`, `DataAnnotationsValidator`; `[SupplyParameterFromForm]` + `@formname` under static SSR | Not a custom validation pipeline for field rules |
| **Virtual List** | `Virtualize<TItem>` | Renders only the items in the viewport. A short list does not need it |
| **Progressive rendering** | `[StreamRendering]` under static SSR or prerendering | Explicit opt-in because content can shift, and it degrades to no streaming on buffering hosts |
| **Single-threaded execution** | Blazor's synchronization context | Lifecycle methods and events run on one logical thread per circuit. A component is still re-entrant at every incomplete `await` |

---

## Which render mode: the decision that shapes everything

Components are static unless told otherwise, and modes are set per component, per page, or
globally on `Routes`.

| Mode | Runs on | Interactive | What it costs |
|---|---|---|---|
| **Static SSR** | Server | No | No events or DOM state; each request starts fresh. Forms post, as on any server-rendered site |
| **Interactive Server** | Server, over a SignalR circuit | Yes | A network hop per interaction, no offline, and server memory per open tab |
| **Interactive WebAssembly** | Browser | Yes | Larger download, slower first load, restricted to browser capabilities, and all code is inspectable |
| **Interactive Auto** | Server first, then browser | Yes | Every component and service must work in both places |

Prerendering is on by default for interactive modes, so components render twice.

**Static SSR.** Justified when pages are mostly read and interaction is forms and links: no
circuit to scale, so it is the cheapest default, and you add interactivity per component. Not
justified when the screen reacts on each keystroke or holds rich client state.

**Interactive Server.** Justified for internal tools and thin clients: fast to load, code never
leaves the server, direct access to server APIs. Not justified when users are many, far from the
server, or offline: each browser screen needs its own circuit and server resources.

**Interactive WebAssembly.** Justified when work should move to the client, or a standalone app
must survive server loss or ship from a CDN. Not justified when first load matters on poor
devices or logic must stay private: secrets and rules sent to the client are exposed. It also
needs a secured web API, as the sandbox prevents most direct database access.

**Interactive Auto.** Justified when you need Server's first load and WebAssembly's later
independence, and can pay for a shared `.Client` project, an API, and DI registrations on both
sides. Not justified as a safe default: it is the sum of the other two's costs.

**Rules the modes impose:**

- A child cannot change to a different interactive mode. A Server component cannot sit inside a WebAssembly one.
- Parameters from a static parent to an interactive child must be JSON-serializable, so child content fails at runtime.

---

## DI scopes per render mode

`AddScoped` is the one lifetime whose meaning changes. Getting it wrong leaks state or memory.

| Where it runs | `Scoped` means | Watch for |
|---|---|---|
| **Static SSR** | One HTTP request | `HttpContext` is available here and generally not during interactive rendering. Avoid `IHttpContextAccessor` outside it |
| **Interactive Server** | One circuit, not one interaction | A long-lived instance shared by all components on the circuit. It is recreated only by a new circuit: reload, new tab, new window |
| **WebAssembly** | Effectively `Singleton`; no DI scopes exist on the client | State lasts for the app's lifetime in that tab |
| **Prerendering** | A server pass, separate from the interactive one | A service registered only in `.Client` throws here. Register it on the server too, or disable prerendering |

Three consequences:

- **Disposable transients leak.** The container holds them for the circuit, or the app's life on the client. Avoid them.
- **Need component lifetime?** Inherit `OwningComponentBase` and resolve through `ScopedServices`. `@inject` still resolves from the outer scope. It adds a base class, so use it where lifetime really matters.
- **Never put user state in a singleton** on the server. It is shared with every user. `IJSRuntime` is scoped there: pass it as a method argument rather than injecting it into one.

### `DbContext` on a circuit

```razor
@inject IDbContextFactory<ContactContext> DbFactory

@code {
    private async Task DeleteAsync(int id)
    {
        using var db = DbFactory.CreateDbContext();
        await db.Contacts.Where(c => c.Id == id).ExecuteDeleteAsync();
    }
}
```

`DbContext` is not thread-safe, and a scoped one is shared across components for the circuit.
Use one context per operation. Create one for the component's lifetime only when you want change
tracking or concurrency handling across an edit, and dispose it with the component. That longer
context holds tracked state, so do not choose it for reads.

---

## Component state

Match the mechanism to how far the state travels. Go no further than needed.

| Reach | Mechanism | Cost or limit |
|---|---|---|
| **One component** | Fields | Gone when the component is |
| **Parent to child** | `[Parameter]`, `EventCallback` | Verbose over many levels, which is a fair signal to rethink the tree |
| **Ancestor to subtree** | `CascadingValue`, `[CascadingParameter]` | See below |
| **Navigation state** | The URL | Survives reload. Fits an ID or a page number, not a draft |
| **Across components** | State container: scoped on the server, singleton on the client | In-memory only. No persistence without more work |
| **Across prerender** | `[PersistentState]` on public properties | JSON in the rendered HTML, so size counts, and never put secrets there |
| **Across a reload** | Browser storage; `ProtectedLocalStorage` server-side | Unavailable during prerendering. Keep it to a few kilobytes |
| **Across reconnects** | Circuit state persistence, on by default in .NET 10 | In memory by default, retention bounded. A full-page refresh defeats it |

**Cascading values** carry a hidden price. Each non-fixed `[CascadingParameter]` subscribes and
is substantially more expensive than a `[Parameter]`, so set `IsFixed` for values that do not
change. Any change rerenders every subscriber, regardless of what it reads: cascade small
objects separately, never one large application state class. They also do not cross render-mode
boundaries. For interactive components use root-level `AddCascadingValue`, which works as a DI
service, with `CascadingValueSource.NotifyChangedAsync` for updates. Static SSR subscribers get
no notifications.

**A state library** (Flux-style) is third-party: Blazor ships none. Reach for one when change
history and many writers are a real need. For two components sharing a value it is ceremony.

---

## Framework features that replace patterns

| Feature | Replaces |
|---|---|
| **`InvokeAsync(StateHasChanged)`** | Hand-marshalling work from a timer or background service. Needed outside Blazor's context, or it throws |
| **`ShouldRender`** | Custom diff logic. Only worth overriding after measuring a hot component |
| **Enhanced navigation** | Hand-written fetch-and-swap in static SSR. It can undo dynamic DOM changes; mark those elements `data-permanent` |

---

## Signs you are fighting the framework

- `AddDbContext` injected straight into interactive server components, with concurrency errors "fixed" by locks.
- `AddScoped` assumed to mean per request on a circuit.
- `IHttpContextAccessor` read during interactive rendering.
- `.Result` or `.Wait()` in a component, which stops the app resuming work until the task ends.
- JS interop in `OnInitializedAsync` with prerendering on. Use `OnAfterRenderAsync` with `firstRender`.
- Data loaded twice on each page because prerender state is never persisted.
- A global state object cascaded to the whole tree.
- `StateContainer.OnChange` subscribed with no matching unsubscribe.
- Connection strings or pricing rules compiled into the `.Client` project.

---

## Sources

- Blazor (ASP.NET Core 10 docs): [render modes](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/render-modes?view=aspnetcore-10.0), [prerendering](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/prerender?view=aspnetcore-10.0), [hosting models](https://learn.microsoft.com/en-us/aspnet/core/blazor/hosting-models?view=aspnetcore-10.0), [security overview](https://learn.microsoft.com/en-us/aspnet/core/blazor/security/?view=aspnetcore-10.0), [lifecycle](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/lifecycle?view=aspnetcore-10.0), [rendering](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/rendering?view=aspnetcore-10.0), [synchronization context](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/synchronization-context?view=aspnetcore-10.0), [cascading values](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/cascading-values-and-parameters?view=aspnetcore-10.0), [event handling](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/event-handling?view=aspnetcore-10.0), [templated components](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/templated-components?view=aspnetcore-10.0), [layouts](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/layouts?view=aspnetcore-10.0), [disposal](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/component-disposal?view=aspnetcore-10.0), [`HttpContext`](https://learn.microsoft.com/en-us/aspnet/core/blazor/components/httpcontext?view=aspnetcore-10.0)
- State and DI: [dependency injection](https://learn.microsoft.com/en-us/aspnet/core/blazor/fundamentals/dependency-injection?view=aspnetcore-10.0), [state overview](https://learn.microsoft.com/en-us/aspnet/core/blazor/state-management/?view=aspnetcore-10.0), [server-side state](https://learn.microsoft.com/en-us/aspnet/core/blazor/state-management/server?view=aspnetcore-10.0), [protected browser storage](https://learn.microsoft.com/en-us/aspnet/core/blazor/state-management/protected-browser-storage?view=aspnetcore-10.0), [prerendered state](https://learn.microsoft.com/en-us/aspnet/core/blazor/state-management/prerendered-state-persistence?view=aspnetcore-10.0), [EF Core in Blazor](https://learn.microsoft.com/en-us/aspnet/core/blazor/blazor-ef-core?view=aspnetcore-10.0), [forms](https://learn.microsoft.com/en-us/aspnet/core/blazor/forms/?view=aspnetcore-10.0), [rendering performance](https://learn.microsoft.com/en-us/aspnet/core/blazor/performance/rendering?view=aspnetcore-10.0)
- Releases: [What's new in .NET 10](https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-10/overview), [.NET 11 RC 1](https://devblogs.microsoft.com/dotnet/dotnet-11-rc-1/)
