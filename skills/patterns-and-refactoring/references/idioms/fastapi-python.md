# FastAPI · Pydantic · SQLAlchemy · Python

[← back to router](../framework-idioms.md)

Written against FastAPI 0.162, Pydantic 2.14 and SQLAlchemy 2.1. Goes deeper than the "FastAPI
specifics" table in [django-python.md](django-python.md), whose Python language table also
applies here. FastAPI is pre-1.0 and ships breaking changes in minor releases: pin it.

---

## What FastAPI already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Dependency Injection** | `Depends()` on any callable | Declare it in the signature; alias it with `Annotated`. No container library |
| **Factory + cleanup** | A dependency with `yield` | One `try`/`finally`. If you `except`, re-raise, or the client gets a 500 with nothing in the server log |
| **Configured Strategy** | A callable instance: `Depends(Checker("bar"))` | `__init__` holds configuration; `__call__` gets request values. A plain function when nothing varies |
| **Singleton** | `lifespan` state; `@lru_cache` on a settings dependency | Once per worker process, overridable in tests. Not a module-level `settings = Settings()` |
| **Chain of Responsibility** | Middleware; nested dependencies; router `dependencies=[...]` | Middleware sees every request; dependencies see a route and reach OpenAPI. Prefer the narrower one |
| **Composite** | `APIRouter` + `include_router` | Group by feature; set auth once at router level, so it cannot be forgotten per route |
| **DTO / Parse, don't validate** | Pydantic models for body, query, headers, responses | Separate input and output models when the shapes differ |
| **Adapter** | `model_validate`, `from_attributes=True` | Map at the edge. Reading attributes from an ORM object is opt-in |
| **Exception translation** | `@app.exception_handler` | Raise a domain exception; translate it once |
| **Data Mapper** | SQLAlchemy ORM; the tutorial uses SQLModel on top | SQLModel cuts duplicate classes but ties table and API shapes together. Split them when they diverge |
| **Unit of Work + Identity Map** | SQLAlchemy `Session` | Not a cache: queries still run. Only `session.get()` can skip SQL for a loaded object |
| **Command** | `BackgroundTasks`; Celery | Not equivalents — see below |

**`app.dependency_overrides` is the testing seam.** It swaps a dependency wherever it is used.
Reset it after each test: the dict lives on the app.

**Know the limit of `Depends`.** FastAPI resolves it for path operations; a Celery task or CLI
command gets nothing. Keep use cases as plain functions with plain arguments, and `Depends` at
the edge. A service that only works inside a request has lost what DI promised.

---

## `async def` or `def`: the pitfall that costs the most

| You write | FastAPI does | Consequence |
|---|---|---|
| `async def` route or dependency | Calls it on the event loop | One blocking call stalls **every** request in that worker |
| `def` route or dependency | Runs it in a threadpool and awaits it | Safe for blocking libraries; costs a thread per in-flight call |
| Your own `def` helper | Nothing: your code calls it directly | Inside `async def` it still blocks the loop |
| Your own `async def` helper | Nothing: you must `await` it | Forgetting returns a coroutine that never runs |

**Choose by what the body blocks on.** A synchronous driver or SDK belongs in `def`. Use `async def`
only when every wait inside is awaited. When unsure, `def` is the safe default, and mixing the
two across a dependency tree works.

- Push a blocking call out of `async def` with `asyncio.to_thread()`. It helps I/O; the GIL generally stops it helping CPU work, which belongs in another process.
- Inside a request, prefer `asyncio.TaskGroup`: it cancels siblings on failure, whereas plain `gather()` leaves them running.
- Never use a bare `asyncio.create_task()` for "background" work: the loop holds tasks weakly, so an unreferenced task can be collected mid-run.

---

## Pydantic at the boundary

- **Separate models per direction.** A return type or `response_model` **filters output to the declared fields**, which keeps a password out of a response. The cost is more classes; stop at one when the shapes truly match.
- **Avoid `response_model_exclude`:** the OpenAPI schema keeps showing the full model.
- **Input is forgiven by default.** Extra keys are dropped silently and `"123"` becomes `123`. Use `extra="forbid"` or strict mode when a client's mistake should fail rather than vanish.
- **`frozen=True` is shallow**, so it is not a full Value Object. **`model_construct()` skips validation:** trusted data only.
- **Null and omitted differ.** Since 0.151 a JSON `null` does not mean "use the default". Since 0.148 omitted-parameter defaults are not validated unless you set `validate_default=True`.

Keep models at the edge. A request model used as the domain object couples rules to the wire
format, so every API version changes the core. For small CRUD, that coupling is fine.

---

## Background tasks or a real queue?

| | `BackgroundTasks` | Celery or another queue |
|---|---|---|
| **Runs** | Same process, after the response is sent | Other processes, other machines |
| **On failure** | Tasks run in order; an exception skips the rest | Whatever retry and routing you configure |
| **On crash or deploy** | Gone: nothing persisted it | Survives in the broker, subject to its configuration |
| **Costs** | Almost no setup; competes with that process's requests | Broker, worker fleet, serialization, monitoring |

**If losing this task silently is a bug, it does not belong in `BackgroundTasks`.** A receipt for
a payment fails that test; a cache warm usually passes. Do not reuse the request's session in a
task: since 0.106 `yield` resources are not held for it. Pass IDs and open a fresh session.

---

## Lifespan

The place for process-wide resources: engine, HTTP client pool, loaded model.

- **It runs once per worker**, so `--workers 4` means four engines, each needing `await engine.dispose()` after `yield`. Migrations do not belong here: they would race. Run them as a deploy step.
- **Yield a dict** and it reaches handlers as `request.state`, a shallow copy, so shared mutable objects stay shared.
- **All or nothing.** Passing `lifespan` silences `on_event` handlers, which are deprecated. Mounted sub-applications do not run theirs.
- **`TestClient` runs it only as a context manager:** `with TestClient(app) as client:`.

---

## SQLAlchemy session handling

```python
Sessions = async_sessionmaker(engine, expire_on_commit=False)

async def get_session():
    async with Sessions.begin() as session:  # commit on success, rollback on exception
        yield session

SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
```

**`scope="function"` matters.** By default the code after `yield` runs after the response is
sent, so a failing commit reaches no client: they already have a 200. The cost: the session is gone
before a `StreamingResponse` iterates, and a `request`-scoped dependency cannot depend on it. The
alternative is a dependency that only opens the session, with the commit in the use case.

- **One session per request, one engine per app.** Never share an `AsyncSession` between concurrent tasks; `gather()` over one session is a bug.
- **Lazy loading fails under asyncio**, because implicit I/O is not allowed. Use `selectinload()` for collections and `joinedload()` for many-to-one; `raiseload("*")` makes a missed load fail in tests rather than become N+1.
- **`expire_on_commit=False`** stops reloads after commit, at the cost of possibly stale objects for the rest of the request.
- **Build response models before the session closes.** A detached object cannot load anything.
- **Keep the session lifecycle outside data functions.** A helper that calls `commit()` stops callers composing two of them into one transaction.
- **SQLAlchemy 2.1:** async needs the `sqlalchemy[asyncio]` extra; `greenlet` no longer installs by default.

---

## Repository over SQLAlchemy?

The most-argued decision here. SQLAlchemy is a Data Mapper, so this is not the Active Record
mistake from Django, but `Session` and `select()` are already good abstractions.

**Justified when:**

- The domain must stay free of SQLAlchemy imports and has rules worth testing without a database.
- A second store exists today behind the same operations.

**Not justified when:**

- Each method wraps one `session.get()` or `session.add()`.
- "For testing." `dependency_overrides` can point a real session at a test database.
- The repository commits, taking the Unit of Work boundary away from the use case.

**The middle path:** query functions in a module, taking `session` first. Named and reusable, at no
interface cost. See [enterprise-patterns.md](../enterprise-patterns.md#repository).

---

## Python features that replace patterns here

| Feature | Replaces |
|---|---|
| **`Annotated` aliases** (`SessionDep`) | Repeated injection declarations; base classes that only hold dependencies |
| **`contextlib.asynccontextmanager`** | Paired startup and shutdown hooks. Not on `yield` dependencies: FastAPI wraps those itself |
| **`functools.lru_cache`** | A hand-written settings Singleton. The value is global, so tests must override the dependency |
| **`asyncio.TaskGroup`** | Hand-rolled fan-out with manual cancellation and error collection |

---

## Signs you are fighting the framework

- A DI container library next to `Depends`, or module-level clients created at import time.
- `time.sleep()` or a sync driver called inside `async def`.
- One Pydantic model for input, output and the table, with a `password` field in it.
- Tests patching module globals where `dependency_overrides` would do.
- A commit after `yield` under the default scope, or `commit()` scattered through helpers.
- Payment work in `BackgroundTasks` with a retry loop written around it.
- An in-process dict used as a cache or rate limiter while running several workers.

---

## Sources

FastAPI: [dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) · [with yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/) · [advanced dependencies](https://fastapi.tiangolo.com/advanced/advanced-dependencies/) · [testing dependencies](https://fastapi.tiangolo.com/advanced/testing-dependencies/) · [async](https://fastapi.tiangolo.com/async/) · [background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) · [lifespan](https://fastapi.tiangolo.com/advanced/events/) · [testing lifespan](https://fastapi.tiangolo.com/advanced/testing-events/) · [response model](https://fastapi.tiangolo.com/tutorial/response-model/) · [SQL databases](https://fastapi.tiangolo.com/tutorial/sql-databases/) · [bigger applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/) · [middleware](https://fastapi.tiangolo.com/tutorial/middleware/) · [handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/) · [settings](https://fastapi.tiangolo.com/advanced/settings/) · [server workers](https://fastapi.tiangolo.com/deployment/server-workers/) · [release notes](https://fastapi.tiangolo.com/release-notes/).
Starlette: [background](https://starlette.dev/background/) · [lifespan](https://starlette.dev/lifespan/). [Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/). [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html).
SQLAlchemy 2.1: [session basics](https://docs.sqlalchemy.org/en/21/orm/session_basics.html) · [state management](https://docs.sqlalchemy.org/en/21/orm/session_state_management.html) · [asyncio](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html) · [relationship loading](https://docs.sqlalchemy.org/en/21/orm/queryguide/relationships.html).
Martin Fowler, *Patterns of Enterprise Application Architecture* (2002), for Data Mapper, Unit of Work, Identity Map and Repository. Original commentary.
