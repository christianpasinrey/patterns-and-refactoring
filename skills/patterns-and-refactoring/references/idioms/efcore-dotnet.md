# EF Core · .NET

[← back to router](../framework-idioms.md)

Checked against EF Core 10 LTS (October 2026). EF Core 11 is due November 2026; differences are
noted. Web-stack concerns are in [dotnet-csharp.md](dotnet-csharp.md).

---

## What EF Core already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Unit of Work** | `DbContext`; `SaveChanges` commits in one transaction when the provider supports them | One context per business operation. No wrapping `IUnitOfWork` unless the domain cannot see EF |
| **Repository** | `DbSet<T>` | See the decision below |
| **Identity Map** | The change tracker, in tracking queries | The same row gives the same instance within a context. No-tracking queries give this up |
| **Query Object** | LINQ over `IQueryable`; `EF.CompileAsyncQuery` for a hot, fixed query | Compose in a method. Compiled queries take simple scalar parameters only, so keep them for proven hot paths |
| **Value Object** | Complex types (`ComplexProperty`, `[ComplexType]`) | See below: these replaced owned types as the documented recommendation |
| **Optimistic Offline Lock** | Concurrency tokens: `[Timestamp]`, `IsRowVersion` | Catch `DbUpdateConcurrencyException` and decide. Often that means retrying the whole operation |
| **Soft Delete, Multi-tenancy** | `HasQueryFilter`; named filters from EF Core 10 | Declared once, applied everywhere. An unnamed second call overwrites the first, and a filter is invisible in the query it changes |
| **Interceptor** | `ISaveChangesInterceptor`, `IDbCommandInterceptor` | For audit and cross-cutting work. Hidden behaviour on each save, so keep them few |
| **Retry** | `EnableRetryOnFailure` | Each query and `SaveChanges` retries as a unit. A manual transaction must run inside `CreateExecutionStrategy()` or it throws |
| **Object Pool** | `AddDbContextPool` | Benchmark first: a context is already cheap, and per-request state such as a tenant ID takes extra work when pooled |

---

## Repository over EF Core: the actual trade-off

`DbContext` is documented as a combination of the Unit of Work and Repository patterns. So the
question is not "should we have a repository?" but "do we need a second one?"

Both camps overstate this. EF's testing guidance recommends a repository layer as the reliable
test double, if a double is required. It also warns that the layer has significant cost, that
real-database tests come first, and that they are still needed for the queries inside it.

**Not justified when:**

- The reason is "testability" and you can run a real database. Local databases are usually fast, and containers remove setup. An in-memory database "for speed" is almost never needed.
- It is a generic `IRepository<T>` with `GetAll`, `GetById`, `Add`: it strips LINQ composition and encapsulates nothing.
- It returns `IQueryable`. That defeats the purpose: EF is still in the test, and callers still write queries.
- It forwards one `DbContext` call per method in a CRUD service. Direct use gives the simplest code.

**Justified when:**

- Tests must run without the database, and each query can move behind an `IEnumerable`-returning method. A method per query is the price.
- The domain cannot reference EF Core, and a repository per aggregate root returns a fully loaded aggregate. That is a DDD decision; see [ddd-patterns.md](../ddd-patterns.md).
- The application targets several databases, and queries need per-provider adjustment.

**Middle path:** use `DbContext` directly in handlers, extract a named query method on its second
use, and add the layer only when one of the above is real.

### Test doubles, ranked by the docs

| Approach | Verdict |
|---|---|
| **Your real database system** | Recommended first. Test isolation is the work to plan for |
| **Repository stub or mock** | Recommended if a double is needed. Costs a layer, and removes LINQ from the test |
| **SQLite in-memory** | Fallback. Different provider, different behaviour: case sensitivity, unsupported queries |
| **Mocking `DbContext`, `DbSet`** | Avoid for queries: LINQ is static extension methods, so it evaluates in memory. Fine for checking `SaveChanges` was called |
| **In-memory provider** | Avoid. Discouraged, supported for legacy use, and receiving no new features |

---

## Change tracking costs

Tracking is the default and is what makes Unit of Work work. EF keeps a dictionary of tracked
instances for identity resolution, plus a snapshot of each to compare at `SaveChanges`. That
costs time and memory per entity loaded.

| Situation | Use | Cost or limit |
|---|---|---|
| **Read-only query** | `AsNoTracking()` | No identity resolution: one row referenced 100 times becomes 100 objects. `AsNoTrackingWithIdentityResolution()` de-duplicates within the query |
| **Display a subset** | `Select` into a DTO | Least data, at the cost of a shape per view. Entity instances in a projection stay tracked |
| **Change many rows** | `ExecuteUpdate`, `ExecuteDelete` | Immediate, with no implicit transaction. The tracker is not updated, so tracked instances go stale, and anything hooked to `SaveChanges` does not run |
| **Insert or edit several** | `SaveChanges` once | Batches automatically, up to 42 statements per roundtrip on SQL Server by default. Costs a read for edits |
| **Long-lived context** | Avoid | Designed to be short-lived and not thread-safe. In Blazor, see [blazor-dotnet.md](blazor-dotnet.md#dbcontext-on-a-circuit) |

---

## N+1, Include and split queries

**N+1 usually comes from lazy loading.** Touching a navigation in a loop runs one query per row.
Lazy loading is opt-in (`UseLazyLoadingProxies` or `ILazyLoader`) and suits small graphs where
roundtrips are cheap. On a web request it is not justified: the extra queries are invisible at
the call site. Prefer `Include` or a `Select` when you know what you need.

**`Include` on two sibling collections causes cartesian explosion.** Ten posts and ten
contributors return a hundred rows for one blog. Split queries fix it:

```csharp
await context.Blogs.Include(b => b.Posts).Include(b => b.Contributors)
    .AsSplitQuery().ToListAsync();
```

**Justified when** sibling collections are large and the result is big.

**Not justified when:**

- Only one collection is loaded, or they are nested rather than siblings. Duplication from one JOIN is usually negligible.
- Consistency matters. Nothing is guaranteed across queries under concurrent updates, unless a serializable or snapshot transaction wraps them, at its own cost.
- Latency or memory is tight: each query is a roundtrip, and most databases buffer earlier results.

EF warns when a query loads several collections with no mode chosen. Decide per query with
`AsSplitQuery` / `AsSingleQuery`, or globally with `UseQuerySplittingBehavior`. Before EF 10, make
the ordering fully unique when combining with `Skip`/`Take`.

---

## Value objects: complex types, not owned types

Owned types were the old answer. EF's docs now point value objects at complex types, because an
owned type is an entity with a hidden key and so has reference semantics.

| | Owned entity types | Complex types |
|---|---|---|
| **Identity** | Hidden key | None; compared by value |
| **Same value on two properties** | Fails: an instance can't be referenced twice | Works; values are copied |
| **`ExecuteUpdate`** | Not supported | Supported |
| **Navigations** | Can hold them | Cannot |
| **Table mapping** | Own table, table splitting or JSON | Containing table or JSON |

**Use a complex type when** it is a real value object: `Address`, `Money`, `Coordinate`. Optional
complex properties and JSON-mapped complex collections need EF Core 10.

**Use an owned type when** you need what complex types lack: a separate table, navigations, or a
collection in its own table. `OwnsMany` needs a primary key, a sign you may be modelling a child
entity. For a single-column value, a value converter (`HasConversion`) is enough.

---

## Migrations

**Generated code is a proposal.** The tool may drop a column when you meant a rename, so inspect
each migration and test it before production.

| Strategy | Use when | Cost |
|---|---|---|
| **SQL script** | A DBA or review gate must see the SQL | Manual step; no migration lock; no seeding delegates |
| **Migration bundle** | Automated deployment | Less review. No SDK or source needed at deploy time |
| **`MigrateAsync` at startup** | Simple deployments that accept the trade-offs | The app needs schema rights, and may run against a changing schema. EF 9+ locks against concurrent runs |
| **`dotnet ef database update`** | Local development | Needs the SDK and source |

Use a separate deployment identity with schema rights; the running app should only read and
write. Branches diverge: EF 10 may merge the model snapshot silently, while EF 11 records the
latest migration ID so a conflict shows. Either way, remove yours, merge, and re-add it.

---

## Signs you are fighting the framework

- `IRepository<T>` and `IUnitOfWork` wrapping one `DbContext`, with mocks asserting on them.
- The in-memory provider in the test suite.
- A `DbContext` kept as a singleton, or shared between threads.
- `SaveChanges` after each `Add` in a loop, or a loop loading rows to set one column.
- `ExecuteUpdate` followed by reading stale tracked entities.
- Lazy loading on in a web API, with `Include` added case by case after incidents.
- Unreviewed migrations applied at startup in a multi-instance production service.

---

## Sources

- EF Core docs: [`DbContext` API](https://learn.microsoft.com/en-us/dotnet/api/microsoft.entityframeworkcore.dbcontext?view=efcore-10.0), [`DbContext` lifetime](https://learn.microsoft.com/en-us/ef/core/dbcontext-configuration/), [change tracking](https://learn.microsoft.com/en-us/ef/core/change-tracking/), [tracking queries](https://learn.microsoft.com/en-us/ef/core/querying/tracking), [transactions](https://learn.microsoft.com/en-us/ef/core/saving/transactions), [concurrency](https://learn.microsoft.com/en-us/ef/core/saving/concurrency), [releases](https://learn.microsoft.com/en-us/ef/core/what-is-new/), [testing strategy](https://learn.microsoft.com/en-us/ef/core/testing/choosing-a-testing-strategy), [testing without the database](https://learn.microsoft.com/en-us/ef/core/testing/testing-without-the-database), [in-memory provider](https://learn.microsoft.com/en-us/ef/core/providers/in-memory/), [efficient querying](https://learn.microsoft.com/en-us/ef/core/performance/efficient-querying), [efficient updating](https://learn.microsoft.com/en-us/ef/core/performance/efficient-updating), [advanced performance](https://learn.microsoft.com/en-us/ef/core/performance/advanced-performance-topics), [single and split queries](https://learn.microsoft.com/en-us/ef/core/querying/single-split-queries), [lazy loading](https://learn.microsoft.com/en-us/ef/core/querying/related-data/lazy), [query filters](https://learn.microsoft.com/en-us/ef/core/querying/filters), [`ExecuteUpdate` and `ExecuteDelete`](https://learn.microsoft.com/en-us/ef/core/saving/execute-insert-update-delete), [complex types](https://learn.microsoft.com/en-us/ef/core/modeling/complex-types), [owned entity types](https://learn.microsoft.com/en-us/ef/core/modeling/owned-entities), [value conversions](https://learn.microsoft.com/en-us/ef/core/modeling/value-conversions), [migrations](https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/), [applying migrations](https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/applying), [team environments](https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/teams), [connection resiliency](https://learn.microsoft.com/en-us/ef/core/miscellaneous/connection-resiliency), [interceptors](https://learn.microsoft.com/en-us/ef/core/logging-events-diagnostics/interceptors)
- Architecture: [.NET Microservices guide, persistence with EF Core](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/infrastructure-persistence-layer-implementation-entity-framework-core)
- Fowler, *Patterns of Enterprise Application Architecture* (2002), for Repository, Unit of Work and Identity Map
