# API design

An API is a promise made to code you do not control. Hyrum's Law, as recorded in *Software
Engineering at Google*: with enough users, every observable behaviour is depended on by somebody,
whatever the contract says. The choices below are about what you can still change later.

---

## Start here

**The first force is whether you can change the consumers.** It decides almost everything else.

| Consumers | Can you change them together with the API? | Consequence |
|---|---|---|
| Same team, same deploy | Yes | It is a module boundary. No versioning, no contract ceremony |
| Other teams, same organisation | Yes, with coordination | Compatible evolution plus [contract tests](#contract-tests) |
| Public or third-party | No | Versioning policy, deprecation windows, idempotency, stable errors |
| Installed clients | No, old versions persist for years | As public, with a much longer window |

Then decide in order, since each step constrains the next: [style](#rest-vs-graphql-vs-grpc-by-force),
[resources](#resource-modelling), [evolution](#versioning), [retries](#idempotency-keys) and
[pagination](#pagination), [errors](#error-shapes). Authorization runs through all of them, per
[security-patterns.md](security-patterns.md#anti-pattern-authorization-bolted-on-at-the-controller).

---

## REST vs GraphQL vs gRPC by force

Choose by the force in front of you. Mixing is normal: gRPC inside, HTTP resources outside.

### REST over HTTP

- **Force** — Many or unknown consumers, on any platform, benefiting from standard semantics and infrastructure: methods, status codes, caching, and tooling.
- **Cost** — Over- and under-fetching for clients with very different needs, and the contract is a discipline unless you maintain a schema for it.
- **Not when** — Several clients each need different deep shapes of a connected graph, or internal calls need streaming and generated clients.

### GraphQL

- **Force** — Varied clients need different shapes of connected data, and one schema owner can serve them. Clients receive only what they ask for, so adding fields is non-breaking, and GraphQL's own guidance favours continuous evolution over versions.
- **Cost** — Query shape is now attacker-controlled. You need depth, breadth and complexity limits, plus rate limits on object count, since batching defeats per-request limits (OWASP GraphQL Cheat Sheet). Authorization has to hold on every node and edge. N+1 is the default without batching in resolvers. HTTP caching needs `GET` or persisted queries, since `POST` is the default.
- **Not when** — One or two clients with stable needs, where a [Backend for Frontend](distributed-patterns.md#gateways-proxies-and-topology) or plain resources would do, or the team cannot run the demand controls.

### gRPC

- **Force** — Service-to-service calls with a strict schema, generated clients across languages, and streaming in either or both directions.
- **Cost** — A binary protocol harder to inspect by hand, and browsers reach it through a gRPC-Web setup, typically a proxy. By default gRPC sets no deadline, so clients must always set one; see [Timeout](distributed-patterns.md#timeout).
- **Not when** — Public consumers you do not control, or browser-first APIs.

"One system states a fact and does not care who listens" is not a request API: read
[messaging](distributed-patterns.md#messaging-and-integration).

---

## Resource modelling

### Model the consumer's domain, not your tables

- **Force** — The API must outlive the current schema and let the two change at different speeds.
- **How** — Name what consumers think about. Keep a translation between internal model and public contract; Khononov's treatment of the Open-Host Service and model translation is the strategic form of this rule. In-process, a response DTO is enough.
- **Cost** — A mapping layer, and fields added in two places.
- **Not when** — A private admin API used by one client from the same team. Direct resources for CRUD are the [honest Transaction Script](enterprise-patterns.md#domain-logic) of APIs.

A generated API over your tables publishes your schema, and then Hyrum's Law freezes it. It
also exposes fields by default, which is OWASP's API3:2023, Broken Object Property Level
Authorization. Allowlist what goes out and what may be set.

### Make state transitions explicit

- **Force** — Moving an order to cancelled is a business action with rules, not a field edit.
- **How** — Give the action a resource: `POST /orders/{id}/cancellation` rather than `PATCH {status: "cancelled"}`. Then it can have its own permission, validation and audit entry.
- **Cost** — More routes, and a vocabulary to design.
- **Not when** — The field really is free-form data with no rules attached.

### Method semantics are a contract

| Method | Safe | Idempotent | Note |
|---|---|---|---|
| `GET`, `HEAD`, `OPTIONS` | Yes | Yes | Must not change state, since infrastructure repeats and prefetches them |
| `PUT`, `DELETE` | No | Yes | Repeating has the same intended effect |
| `POST` | No | No | Needs [an idempotency key](#idempotency-keys) if retried |
| `PATCH` | No | Not by default | Can be made idempotent by design (RFC 5789) |

**Lost updates:** return an `ETag` and require `If-Match`, so a stale write gets `412`; this is
[optimistic locking](enterprise-patterns.md#offline-concurrency) over HTTP. **Long operations:**
return `202` with a status resource rather than holding the connection open.

**Granularity:** see [Remote Facade](enterprise-patterns.md#distribution). **Identifiers** protect
nothing: holding an ID is not permission to use it.

---

## Versioning

**Evolve first, version last.** A new version keeps two contracts alive and moves every consumer.
Most change is possible through [Parallel Change](refactoring-workflow.md#parallel-change-expand--contract)
with tolerant readers; Newman calls these expansion changes.

| Usually compatible | Breaking, whatever the diff looks like |
|---|---|
| New optional request field | New required request field |
| New response field, for tolerant readers | Removing or renaming a field; changing its type or meaning |
| New endpoint or resource | Tighter validation of input that used to pass |
| New enum value, if documented as open | New enum value where clients match exhaustively; changed default, ordering, rounding or error code |

When a break is unavoidable:

| Mechanism | Force | Cost | Not when |
|---|---|---|---|
| **Path version** (`/v2/`) | Visible, easy to route and to log | The whole surface shifts at once | One resource changed |
| **Header or media type** | Per-resource evolution with stable URIs | Harder to see, test and cache | Consumers are not sophisticated HTTP clients |
| **Schema evolution** (GraphQL, protobuf) | One live contract, deprecating fields individually | Dead fields accumulate | A semantic redesign that fields cannot express |

For protobuf the rule is absolute: never reuse a field number, and `reserved` every deleted
number and name, because reuse risks corrupted data and leaks.

**Serve versions from one core.** Translate old shapes to the current model at the edge, so an
old version is an adapter rather than a fork. **Retire deliberately:** announce with the
`Deprecation` header (RFC 9745) and `Sunset` header (RFC 8594). Both are hints; the promise is
your policy. Measure use per consumer before removing anything, since improper inventory is
OWASP's API9:2023, and old versions are where unpatched behaviour survives.

---

## Pagination

Every list is paginated from its first day, with a server-enforced maximum page size.
Unrestricted Resource Consumption is OWASP's API4:2023, and adding limits later is a breaking change.

| Approach | Force | Cost | Not when |
|---|---|---|---|
| **Offset** | Page numbers and jump-to-page for humans | Skipped rows are still computed, and concurrent inserts shift pages, so rows repeat or vanish | Deep, large or fast-changing lists |
| **Cursor / keyset** | Stable, cheap traversal of large or live data | Needs a unique, indexed sort key, no jumping to page 50, and a new cursor when sort changes | A small admin table where page numbers help |

- **Sort on something unique.** Without a total order, results between pages are unpredictable. Add the primary key as a tie-breaker.
- **Keep cursors opaque,** as GraphQL's own guidance advises, so the server may change what they encode. Base64 is a reminder, not protection.
- **A cursor is input.** Reapply authorization and tenant scope on each page, whatever it decodes to.

---

## Idempotency keys

- **Force** — A client whose `POST` timed out cannot tell whether it happened, and must be able to retry without charging twice.
- **Cost** — A key store to keep, stored responses that may hold sensitive data, a retention policy to publish, and concurrency handling.
- **Not when** — The operation is already idempotent (`GET`, `PUT`, `DELETE`), or naturally repeatable by design. Keys protect *requests*; for messages see [Idempotent Receiver](distributed-patterns.md#idempotent-receiver).

The mechanics, from Stripe's published guidance and an IETF draft that is not yet an RFC:

1. **The client generates the key:** a V4 UUID or similar random value, without personal data, sent in an `Idempotency-Key` header and reused across retries of that one operation.
2. **The server records the key with a request fingerprint,** in the same transaction as the state change. Stored separately, a crash between the two recreates the original problem.
3. **Same key, same payload, completed** → replay the stored result without running again.
4. **Errors, as the draft suggests:** `422` for the same key with a different payload, `409` while the original is still running, `400` for a missing required key.

| Decision | Options |
|---|---|
| Failed first attempt | Replay it, as Stripe's API v1 does once execution has begun, including `500`; or resume the work, as its API v2 describes. Pick one and document it |
| Validation failure | Do not store it, so that a corrected request can use the key |
| Retention | Must exceed the longest client retry horizon. Stripe's API v1 keeps keys at least 24 hours |
| Scope | Per account or tenant, or one customer's key may replay another's response |

Clients pair keys with [backoff and jitter](distributed-patterns.md#retry). A side effect leaving
the transaction (an email, a provider call) needs the
[Transactional Outbox](distributed-patterns.md#transactional-outbox) as well.

---

## Error shapes

- **Force** — Clients have to branch on an error by code, and humans need to read it; one string cannot do both.
- **How** — Use RFC 9457 problem details: `application/problem+json`, with `type` (a stable URI, the thing clients match on), `title`, `status`, `detail`, `instance`, plus extension members for machine-readable data.
- **Cost** — A registry of problem types to document, and each `type` is now part of the contract.
- **Not when** — gRPC, which has its own status model, and GraphQL, which reports errors in the response. Keep the same discipline there, with a stable machine-readable code.

```json
{
  "type": "https://api.example.com/problems/insufficient-funds",
  "title": "Insufficient funds",
  "status": 422,
  "detail": "The balance is 30.00, and this transfer needs 50.00.",
  "balance": "30.00"
}
```

- **Never parse `detail`.** The RFC says consumers should not; put what code needs in extensions, as `balance` above.
- **Keep the real status.** The body's `status` is advisory and generic HTTP software will not read it.
- **No stack traces, SQL or internals.** The RFC warns specifically against exposing implementation details, and a trace identifier gives support what it needs.
- **Avoid disclosing existence.** A `404` for objects the caller may not see avoids confirming they exist; apply the same thinking to [login failures](security-patterns.md#use-a-vetted-authentication-system).

Statuses clients act on: `409` a conflict they can resolve, `412` a failed precondition, `422`
well-formed but unprocessable, `429` rate limited (with `Retry-After` when known).

---

## Contract tests

A contract test answers one question early: *did this change break a consumer's expectations?*
It checks shape, not business behaviour. Doubles are in [testing-patterns.md](testing-patterns.md#test-doubles).

| Kind | Force | Cost | Not when |
|---|---|---|---|
| **Schema compatibility check** | Catch accidental breaking changes in provider CI, by diffing the OpenAPI or proto definition | The schema must be the source of truth; semantic breaks pass unseen | No schema exists, or the service has one consumer in the same repository |
| **Consumer-driven contract** | Known consumers publish what they use, so providers know what they can change | Shared infrastructure, coordination, and consumers influencing the provider's design | Public APIs: unknown consumers publish nothing |
| **Double verification** | Your stubs of an external service drift from it | Calls to the real service; run on a schedule, as a failure means investigate, not necessarily stop the build | You own both sides and already run the contract in CI |

Robinson's article states the limit: this suits a closed community of known services, and a
breaking change is still breaking. The test makes the coupling visible; it does not remove it.

---

## Choosing: the honest defaults

1. **Resource-oriented HTTP for anything public**, with a machine-readable schema.
2. **GraphQL only with demand control and per-object authorization.** gRPC for internal calls that need it.
3. **Add, do not change.** Version as a last resort, and retire versions with measured usage.
4. **Paginate every list from day one, with a hard cap,** and prefer cursors for anything that grows.
5. **Idempotency keys on every `POST` with a side effect** that clients may retry.
6. **Problem details for HTTP errors, matched on `type`; contract tests where you cannot deploy together.**

---

## Sources

Titus Winters, Tom Manshreck & Hyrum Wright (eds.), [*Software Engineering at Google*](https://abseil.io/resources/swe-book/html/ch01.html) (Hyrum's Law) ·
Sam Newman, *Building Microservices*, 2nd ed. (2021), chapters 5 and 9 · Vlad Khononov, *Learning Domain-Driven Design* (2021), context mapping and communication patterns ·
IETF: [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) HTTP Semantics, [RFC 5789](https://www.rfc-editor.org/rfc/rfc5789.html) PATCH, [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html) (429), [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) Problem Details, [RFC 9745](https://www.rfc-editor.org/rfc/rfc9745.html) Deprecation, [RFC 8594](https://www.rfc-editor.org/rfc/rfc8594.html) Sunset, [Idempotency-Key header draft](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) ·
Stripe: [Idempotent requests](https://docs.stripe.com/api/idempotent_requests); Brandur Leach, [Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency) ·
OWASP: [API Security Top 10:2023](https://api-security.owasp.org/editions/2023/en/0x11-t10), [GraphQL Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html) ·
GraphQL: [Schema Design](https://graphql.org/learn/schema-design/), [Pagination](https://graphql.org/learn/pagination/), [Performance](https://graphql.org/learn/performance/) ·
gRPC: [Introduction](https://grpc.io/docs/what-is-grpc/introduction/), [Core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/), [Deadlines](https://grpc.io/docs/guides/deadlines/), [Web basics](https://grpc.io/docs/platforms/web/basics/) ·
[Protocol Buffers language guide](https://protobuf.dev/programming-guides/proto3/) · PostgreSQL, [LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html) · Ian Robinson, [Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html) ·
Martin Fowler, [Contract Test](https://martinfowler.com/bliki/ContractTest.html). Original commentary.
