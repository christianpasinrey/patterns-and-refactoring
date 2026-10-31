# Symfony · Doctrine · PHP

[← back to router](../framework-idioms.md)

Written against Symfony 8.1 and Doctrine ORM 3.7. Goes deeper than the "Symfony specifics" table
in [laravel-php.md](laravel-php.md), whose PHP language table also applies here.

---

## What Symfony already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Abstract Factory + DI** | Compiled container, autowiring, autoconfiguration | Type-hint the constructor; no hand-written factory to pick an implementation. Keep services private |
| **Strategy** | Tagged services + `#[AutowireLocator]` or `#[AutowireIterator]` | See below. Under three variants, a `match` is cheaper than a tag |
| **Chain of Responsibility** | Kernel events; Messenger middleware; a priority-ordered `#[AutowireIterator]` | Listen on `RequestEvent` rather than wrapping the kernel. The order is invisible in code; `debug:event-dispatcher` shows it |
| **Decorator** | `#[AsDecorator]` or `decorates:`; `stack:` for a named chain | Declare it; no subclass, no wrapping in a factory |
| **Proxy** (virtual) | `#[Lazy]`, service closures, locators | Only for a heavy service most calls never touch; lazy everywhere is indirection for nothing |
| **Observer** | EventDispatcher; Doctrine events | Not interchangeable — see below |
| **Command** | Messenger: message + handler | Synchronous until routed, so the seam is cheap. The real cost arrives with the first async route |
| **State** | Workflow component, `type: 'state_machine'` | Guards, events and audit trail for a real lifecycle. A two-value status needs an enum |
| **Data Mapper** | Doctrine ORM | Entities stay plain objects; mapping lives in attributes |
| **Unit of Work** | `EntityManager` + `flush()` | One `flush()` is already one transaction; no transaction helper around every write |
| **Identity Map** | `EntityManager` | Same ID, same instance, for that manager. `clear()` resets it and detaches everything you still hold |
| **Repository** | `ServiceEntityRepository` | Named queries live here. An extra interface on top is a separate decision — see below |
| **Specification** | Doctrine `Criteria` with `matching()` | SQL if the collection is unloaded, in memory if loaded, and results can differ. Stick to scalar values |
| **DTO at the boundary** | `#[MapRequestPayload]`, `#[MapQueryString]` | Validated DTO in the signature. Failure defaults to 422 for the body but **404** for the query string; set `validationFailedStatusCode` |
| **Policy** | Voters | One place for "may this user do this to this object" |
| **Retry** | `retry_failed` on HTTP clients; `retry_strategy` on Messenger transports | Three retries by default on both. A hand-written loop on top multiplies attempts |
| **Rate Limiting** | RateLimiter: `fixed_window`, `sliding_window`, `token_bucket`, `compound` | Fixed window is simplest but allows bursts at the edges |

---

## Compiled DI: what it buys and what it charges

The graph is resolved ahead of time and cached in `var/cache/`. Unused private services vanish,
and a broken reference fails on any page load, not only on the path that reaches it. Run
`lint:container` in CI: it adds type checks left off by default for compile speed.

The price: **anything decided at runtime cannot be wired directly.** A handler chosen by a request
value needs a locator. A public service plus `$container->get()` hides the dependency.

```php
#[AutoconfigureTag('app.payment_handler')]
interface PaymentHandler { public function charge(Order $order): void; }

#[AsTaggedItem(index: 'card')]
final class CardPayment implements PaymentHandler { /* ... */ }

final class Checkout {
    public function __construct(
        #[AutowireLocator('app.payment_handler')] private ContainerInterface $handlers,
    ) {} // $this->handlers->get('card') instantiates only that handler
}
```

- **Locator** to pick one by key; **iterator** to run all. A locator loses the type, and an unknown key fails at runtime, so check `has()` on untrusted input.
- **Index and priority go in `#[AsTaggedItem]`.** Since 8.1 the default-method routes are deprecated.
- **Decoration order trips people up.** Higher `decoration_priority` sits *closer* to the original, so the lowest runs first. A decorator also takes over the decorated service's custom tags.
- **`stack:` reads better from three decorators**, but by default it defines a new service: only code injecting the stack gets the chain, unless you add `decorates:` (8.1).

---

## Doctrine: living with a real Unit of Work

- **Only `flush()` writes.** A managed entity is tracked without `persist()`. Generated IDs are guaranteed only after a successful flush.
- **Flush cost grows with the managed set.** The default policy compares every managed entity on each flush. Flush once at the end of the use case, never in a loop, and do not rely on statement order.
- **The ORM is the wrong tool for mass writes.** Use DQL `UPDATE`/`DELETE`, or `flush()` and `clear()` in batches. DQL skips `preUpdate`, so a rule living in a listener is bypassed.
- **An exception closes the manager.** Entities detach with their in-memory state unreverted, and new work needs a new manager. Long-running workers must plan for this.
- **Lost updates need `#[Version]`.** Carry the version through the form, so the check compares with what the user read.

---

## EventDispatcher, Doctrine events, Messenger

| | EventDispatcher | Doctrine events | Messenger |
|---|---|---|---|
| **Reacts to** | Something your code says happened | The ORM writing a row | Work to perform |
| **Runs** | Inline, before `dispatch()` returns | Inside `flush()` | Inline, or in a worker once routed |
| **Fits** | In-process domain events; HTTP lifecycle | Audit columns, slugs, derived columns | Slow, retryable or external work |
| **Costs** | Hidden control flow; a listener failure hits the caller | Cannot safely flush; heavily restricted | Repeat delivery; a worker fleet to run |

Calling `flush()` from a handler running inside a flush can lose changes, and `preUpdate` ignores
association changes. `postPersist` fires **before the transaction commits**, so a message sent
there can reach a consumer before the row is visible, or describe a row that gets rolled back.
Dispatch from the use case after `flush()`.

Take the narrowest Doctrine tool: a lifecycle callback for simple logic on one entity, an entity
listener when it needs services, a lifecycle listener only for logic shared across entities.

---

## Messenger: what the seam really promises

- **Delivery can repeat.** A worker can finish and crash before acknowledging, so handlers must be idempotent. Derive any idempotency key from the business event, not at dispatch.
- **Send IDs, not entities.** Messages are serialized and can outlive a deploy. Add constructor arguments as optional, or add a new class and drain the old one.
- **`doctrine_transaction` is opt-in.** With it, `DispatchAfterCurrentBusStamp` holds follow-ups until the first handler finishes, so a failed follow-up cannot roll it back. That is ordering, not atomic delivery: a crash after commit can lose the message. If it must not be lost, see [Transactional Outbox](../distributed-patterns.md#transactional-outbox).
- **Workers are long-lived.** Exit with `--limit`, `--memory-limit` or `--time-limit`, because the `EntityManager` grows; run `messenger:stop-workers` on deploy. Without a failure transport, exhausted messages are discarded.
- **Start with one bus.** Add another only for a different middleware stack. Identical command and query buses are ceremony.

---

## Forms, Validator, Voters

- **`handleRequest()` writes into your object before `isValid()` runs.** Bound to an entity, the form can leave it invalid, so setters cannot guard invariants.
- **Bind to the entity** for CRUD where fields match columns: least code, at the cost of an entity shaped by a form. **Bind to a DTO** when the entity has real invariants or the form spans objects: the cost is mapping code.
- **Immutable objects** need a custom `DataMapperInterface`, and the data it receives is still unvalidated.
- **Constraints go on the mapped object**, not the fields, so `$validator->validate($object)` applies them outside the form. They check input; they do not replace invariants the object enforces itself.
- **Pass the form, not `createView()`, to `render()`,** and an invalid submit returns 422. For JSON APIs skip Form and use `#[MapRequestPayload]`.
- **Voters** keep authorization beside the subject, testable alone, and reachable from `#[IsGranted]` and Twig's `is_granted()`. One rule used once needs no voter: `#[IsGranted('ROLE_ADMIN')]` is enough.
- **The default strategy is affirmative:** one grant wins even if another voter denies. A veto needs a different strategy. Every voter runs on every check unless you override `supportsAttribute()` and `supportsType()`.

---

## A repository interface over Doctrine?

The most-argued decision here. `ServiceEntityRepository` is not in question; the argument is about
an interface you own in front of it. Doctrine is already the mapper.

**Justified when:**

- The domain sits behind a Ports & Adapters boundary and must not import Doctrine.
- Use cases are worth unit-testing with in-memory fakes, and the rules are complex enough to pay.
- A second implementation exists today, such as a read model in a different store.

**Not justified when:**

- Every interface has one implementation forwarding to `ServiceEntityRepository`.
- "To swap the ORM." Flush timing and lazy loading leak through any interface.
- It hides `flush()`, so callers no longer know when anything is written.

**The middle path:** concrete repositories, one use-case service owning `flush()`, integration
tests on a real database. See [enterprise-patterns.md](../enterprise-patterns.md#data-source-architecture).

---

## PHP features that replace patterns here

| Feature | Replaces |
|---|---|
| **`#[AsMessageHandler]`, `#[AsEventListener]`, `#[AsDecorator]`** | Hand-kept registration lists. Wiring gets scattered; the `debug:*` commands reassemble it |
| **Property hooks** (PHP 8.4, required by Symfony 8.1) | Getter and setter pairs guarding one value. Arbitrary code now runs behind what reads like a field |
| **Asymmetric visibility** `public private(set)` (8.4) | Read-only accessor boilerplate |
| **`#[Target]`** | A factory selecting one of several named services of the same type |

---

## Signs you are fighting the framework

- `$container->get()` in application code, or a hand-written registry a tag would collect.
- `flush()` inside a loop or a Doctrine event handler.
- Sending messages from `postPersist` and assuming the row is committed.
- A Messenger handler receiving an entity rather than an ID.
- Role and ownership checks copied across controllers instead of one voter.
- Constraints on form fields that the same object needs outside the form.

---

## Sources

Symfony: [container](https://symfony.com/doc/current/service_container.html) · [tags](https://symfony.com/doc/current/service_container/tags.html) · [locators](https://symfony.com/doc/current/service_container/service_subscribers_locators.html) · [decoration](https://symfony.com/doc/current/service_container/service_decoration.html) · [lazy services](https://symfony.com/doc/current/service_container/lazy_services.html) · [events](https://symfony.com/doc/current/event_dispatcher.html) · [Messenger](https://symfony.com/doc/current/messenger.html) · [controllers](https://symfony.com/doc/current/controller.html) · [forms](https://symfony.com/doc/current/forms.html) · [data mappers](https://symfony.com/doc/current/form/data_mappers.html) · [validation](https://symfony.com/doc/current/validation.html) · [voters](https://symfony.com/doc/current/security/voters.html) · [Doctrine events](https://symfony.com/doc/current/doctrine/events.html) · [Workflow](https://symfony.com/doc/current/workflow.html) · [HTTP client](https://symfony.com/doc/current/http_client.html) · [rate limiter](https://symfony.com/doc/current/rate_limiter.html) · [best practices](https://symfony.com/doc/current/best_practices.html) · [releases](https://symfony.com/releases).
Doctrine ORM: [working with objects](https://www.doctrine-project.org/projects/doctrine-orm/en/stable/reference/working-with-objects.html) · [events](https://www.doctrine-project.org/projects/doctrine-orm/en/stable/reference/events.html) · [transactions](https://www.doctrine-project.org/projects/doctrine-orm/en/stable/reference/transactions-and-concurrency.html) · [batch processing](https://www.doctrine-project.org/projects/doctrine-orm/en/stable/reference/batch-processing.html) · [change tracking](https://www.doctrine-project.org/projects/doctrine-orm/en/stable/reference/change-tracking-policies.html) · [associations](https://www.doctrine-project.org/projects/doctrine-orm/en/stable/reference/working-with-associations.html).
[PHP 8.4](https://www.php.net/releases/8.4/en.php). Martin Fowler, *Patterns of Enterprise Application Architecture* (2002), for Data Mapper, Unit of Work and Identity Map. Original commentary.
