# Svelte · SvelteKit · TypeScript

[← back to router](../framework-idioms.md)

See also [../frontend-patterns.md](../frontend-patterns.md) for framework-neutral frontend
patterns (state placement, data fetching, rendering strategies).

Checked against Svelte 5.57 and SvelteKit 3.1. Kit 3 renamed things older advice relies on:
`$lib` is now `#lib`, `$env/*` gave way to `$app/env/private` and `$app/env/public`, `$app/stores`
is gone in favour of `$app/state`, and `refreshAll` replaces the deprecated `invalidateAll`.

---

## What Svelte already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Observer** | `$state`, `$derived`, `$effect` | Never build an event bus for state. Reactivity *is* the observer |
| **Proxy** | Deep `$state` on arrays and plain objects | Reads go through a proxy, so use `$state.raw` for large data you replace wholesale, and `$state.snapshot` before handing state to an external API |
| **Template Method** | Snippets passed as props, drawn with `{@render}` | Replaces deprecated slots. Rest parameters are not supported |
| **Decorator** | A wrapper using `children`; `{@attach}` for element behaviour | An attachment re-runs when state it reads changes, so pass a getter when setup is expensive. Needs Svelte 5.29+ |
| **Registry / Provider** | `createContext` (5.40+), or `setContext` / `getContext` | Safe across SSR requests, unlike module state. Mutate shared objects: reassigning breaks the link |
| **Facade** | A class with `$state` fields in a `.svelte.ts` file | Methods passed as handlers lose `this`: use arrow-function fields. Do not wrap a single value in a class |
| **Fault boundary** | `<svelte:boundary>`; `+error.svelte` | Render-time only: errors in event handlers and timeouts are not caught |

### `.svelte.ts` files are the pattern layer

Runes work in `.svelte.ts` modules, so a function or class there does what a hook or composable
does elsewhere. **One concern per module.** Extract when two components share logic.

---

## Stores vs runes: the most-argued decision

Stores were the only way to share reactive state outside a component before Svelte 5. The docs
say runes greatly diminished their use, but stores are not deprecated.

**Stores are justified when:**
- You have a complex asynchronous stream, or need manual control over updates and listeners.
  `readable` has a start function with teardown.
- A library exposes the store contract. `fromStore` and `toStore` bridge in both directions.
- Cost: subscription semantics, and `$store` auto-subscription works only at component top level.

**Runes are justified when (the default):**
- You share ordinary state, using a `$state` object in `.svelte.ts`.
- You extract stateful logic. Runes work outside a component's top level.
- Cost: state crosses functions by value, so getters are needed, and only compiled files count.

**Not justified:**
- New `writable` stores for a counter or a flag.
- Rewriting working stores just to modernise them, with no bug or requirement forcing it.

---

## Reactivity traps that look like design problems

| Symptom | Cause |
|---|---|
| Importers do not see a reassigned `$state` | A reassigned state variable cannot be exported. Export an object and mutate it, or export accessors |
| A function keeps seeing the old value | Arguments are passed by value. Pass a getter or an object holding the state |
| A destructured value goes stale | Destructuring `$state` copies at that moment. `$derived` destructuring stays reactive |
| An effect ignores a dependency | Reads after `await` or inside `setTimeout` are not tracked |
| Code does not re-run between two pages of one route | Kit reuses the component. Use `$derived`, `afterNavigate`, or `{#key}` |

### `$effect` is an escape hatch

Effects are for analytics, third-party libraries, canvas and direct DOM work, and run only in
the browser. Deriving state with one is wrong: use `$derived`. Since 5.25 a non-`const` derived
can be overridden, which covers optimistic UI: assign it, and roll back on failure.

---

## Load functions

| | Universal (`+page.ts`, `+layout.ts`) | Server (`+page.server.ts`, `+layout.server.ts`) |
|---|---|---|
| **Runs** | On the server for SSR, again in the browser to hydrate, then in the browser | Only on the server |
| **Can return** | Anything, including classes and component constructors | Data serializable by devalue; custom types need transport hooks |
| **Use for** | External APIs without private credentials; non-serializable values | Database, filesystem, private env vars, cookies |
| **Cost** | Code ships to the browser and must work in both places | A server round trip on each client navigation that re-runs it |

Default to server `load` for secrets and data access, universal when the browser can reach the
source directly. If both exist, the server result reaches the universal `load` as `data`.

- **Keep `load` pure.** Do not write to stores or shared state; return data. Read it from the
  `data` prop or `page.data`.
- **Avoid waterfalls.** `load` functions for a page run concurrently unless you `await parent()`,
  so start independent fetches before awaiting it.
- **Stream the slow part** by returning a promise from server `load`. Headers are then fixed.
- **Do not call `redirect()` inside `try`.** It works by throwing, so your `catch` swallows it.

**The auth trap:** a layout `load` does not run on every request, so it is not a per-request
check. Guard groups of routes in `handle`, and specific routes in `+page.server.ts`. A guard in
`+layout.server.ts` needs every child to `await parent()`. Never authorize from `params` or `url`.

---

## Form actions

Actions live in `+page.server.ts` and are the **Command** pattern with progressive enhancement.
A `<form method="POST">` works with no JavaScript, and `use:enhance` upgrades it.

- Validate on the server. Return `fail(400, ...)` with the safe fields, never a password.
- After an action the page re-renders and `load` runs again, so you rarely patch client state.
- Use named actions (`?/name`) for several intents, and do not mix them with `default`. A named
  action that does not redirect leaves its query string behind, so redirect after success.
- **Reach for `+server.ts` instead** for non-form callers or a JSON API. Cost: you lose the
  no-JavaScript path, and the page's `load` does not re-run by itself.

**Remote functions** (`query`, `form`, `command`, `prerender`) are still **experimental** behind
`experimental.remoteFunctions`, and may change without notice. Adopt them only if you accept
that churn. Every argument is untrusted: validate with a schema, authorize inside the handler.

---

## Server vs universal modules

**Server-only:** anything under a `server` directory (outside `src/routes` and `static`), any
file with a `.server` suffix, plus `$app/env/private` and `$app/server`. Kit fails the build
when browser-reachable code imports one, directly or through a re-export, including dynamic
imports. That guard is worth keeping: put database clients and secrets there.

**Universal:** `+page.ts`, `+layout.ts`, components and shared utilities run in both places, so
top-level code must not assume a browser. Check `browser` from `$app/env`, or use an `$effect`.
The import guard is off under `process.env.TEST === 'true'`, so green tests prove nothing here.

**The trap that matters most:** the server is shared by every user. Module-level state, whether a
`$state` object or a store, written during a request is visible to the next request. That is a
cross-user data leak, not a singleton. Keep per-request data in `event.locals`, per-tree state in
context, and durable state in a database. Module state is safe only when SSR is off.

---

## SvelteKit specifics

| Pattern | Where it lives |
|---|---|
| **Chain of Responsibility** | `handle` composed with `sequence`; runs per server request, static assets excluded |
| **BFF** | `+server.ts` endpoints and server `load` |
| **Materialized View** | `prerender`: the same content for every visitor, and incompatible with form actions |
| **Zero-JS page** | `csr = false` per page ships no JavaScript, and rules out enhanced forms |

---

## Going against the grain — signs you are fighting the framework

- `$effect` setting state a `$derived` could compute.
- Per-user data in a module-level variable or store on the server.
- `load` writing to shared state instead of returning data.
- Auth checks that live only in a layout `load`.
- Client `fetch` plus loading flags for a form an action would handle.
- New `<slot>` markup, or new `$app/stores` imports.
- Mutating props, or `$bindable` as the default way to talk to a parent.

---

## Sources

- [Runes](https://svelte.dev/docs/svelte/what-are-runes), [`$state`](https://svelte.dev/docs/svelte/$state), [`$derived`](https://svelte.dev/docs/svelte/$derived), [`$effect`](https://svelte.dev/docs/svelte/$effect), [`$props`](https://svelte.dev/docs/svelte/$props), [`$bindable`](https://svelte.dev/docs/svelte/$bindable), [snippets](https://svelte.dev/docs/svelte/snippet), [`{@attach}`](https://svelte.dev/docs/svelte/@attach), [`{#each}`](https://svelte.dev/docs/svelte/each), [`<svelte:boundary>`](https://svelte.dev/docs/svelte/svelte-boundary), [legacy slots](https://svelte.dev/docs/svelte/legacy-slots)
- [Stores](https://svelte.dev/docs/svelte/stores), [`svelte/store`](https://svelte.dev/docs/svelte/svelte-store), [context](https://svelte.dev/docs/svelte/context), [`svelte/reactivity`](https://svelte.dev/docs/svelte/svelte-reactivity)
- [Routing](https://svelte.dev/docs/kit/routing), [loading data](https://svelte.dev/docs/kit/load), [form actions](https://svelte.dev/docs/kit/form-actions), [hooks](https://svelte.dev/docs/kit/hooks), [page options](https://svelte.dev/docs/kit/page-options), [state management](https://svelte.dev/docs/kit/state-management), [server-only modules](https://svelte.dev/docs/kit/server-only-modules), [`$app/state`](https://svelte.dev/docs/kit/$app-state), [`$app/env`](https://svelte.dev/docs/kit/$app-env)
- [Remote functions](https://svelte.dev/docs/kit/remote-functions), [migrating to SvelteKit 3](https://svelte.dev/docs/kit/migrating-to-sveltekit-3), [What's new in Svelte: October 2026](https://svelte.dev/blog/whats-new-in-svelte-october-2026)

All commentary here is original.
