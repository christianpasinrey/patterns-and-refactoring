# Schema and data evolution

Code is replaced on every deploy; stored data is not. Rows outlive the code that wrote them,
and a bad write cannot be reverted the way a commit can.

The sequence for any live change is
[Parallel Change](refactoring-workflow.md#parallel-change-expand--contract), with its
[schema rules](refactoring-workflow.md#refactoring-the-schema). This file is what that sequence
leaves open: how each step stays online, repeatable and verifiable. Deploy order is in
[delivery-patterns.md](delivery-patterns.md).

---

## Start here

| The change | What actually bites | Go to |
|---|---|---|
| Add or alter a column on a busy table | A lock queued behind one slow query | [Online schema change](#online-schema-change) |
| A migration failed halfway | Partial state, and a re-run that trips over it | [Idempotent migrations](#idempotent-migrations) |
| Fill a column across millions of rows | Replica lag, lost updates, no way to resume | [Backfills](#backfills) |
| Enforce uniqueness on existing data | Duplicates you did not count, and new ones arriving | [Unique indexes on dirty data](#unique-indexes-on-dirty-data) |
| New format for a stored value | Readers you forgot, including the rollback target | [Changing stored formats](#changing-stored-formats-while-old-code-reads-them) |
| Tests pass, production fails | The test database is a different database | [Test databases](#test-databases-that-differ-from-production) |
| A slow query | The index that makes every write slower | [Indexes and their costs](#indexes-and-their-costs) |

**Before any of them, find out:** engine and exact version, table size, write rate, the
longest-running transaction, replicas, and free disk. The advice below depends on all of them.

---

## Online schema change

### Native online DDL

- **Force** — The table has to keep serving reads and writes during the change.
- **How** — Know which operations your engine does in place. The table below is version-specific; check the manual for yours.
- **Cost** — Slower than the blocking form, more disk, and failure modes of its own (invalid indexes, replica lag).
- **Not when** — The table is small or an agreed maintenance window exists. A plain `ALTER` is then simpler and honest.

| Operation | PostgreSQL | MySQL 8.4 InnoDB |
|---|---|---|
| Add a column | Metadata only with a non-volatile default; a volatile default rewrites the table and its indexes | `INSTANT` by default, up to 64 row versions per table |
| Add an index | `CREATE INDEX CONCURRENTLY`, outside a transaction block; the plain form blocks writes | In place, concurrent writes permitted |
| Change a column type | Rewrite, unless the new type is binary coercible | `COPY` only: rebuilds the table and blocks writes |
| Add a constraint | `NOT VALID`, then `VALIDATE CONSTRAINT` under a weaker lock; `SET NOT NULL` skips its scan if a valid `CHECK` proves it | Not covered here; check the manual |

### The lock queue

**A brief lock is not a cheap lock.** Most `ALTER TABLE` forms in PostgreSQL need `ACCESS
EXCLUSIVE`, the one mode that conflicts with plain `SELECT`. The statement waits for every
transaction already using the table, and conflicting requests are granted in order of arrival,
so later queries queue behind it. One forgotten transaction plus one "instant" migration stalls
the table. MySQL online DDL needs an exclusive metadata lock in its final phase, and a long or
idle transaction can block that until it times out.

- **Force** — A schema statement must not be able to take the table down while it waits.
- **How** — Set a short `lock_timeout` for the migration session, and retry on a schedule rather than waiting. Look for long transactions first.
- **Cost** — Retry logic, and a migration that may need several attempts during a busy period.
- **Not when** — A window with no traffic, where a queued lock harms nobody.

**Replicas pay separately.** In MySQL the DDL finishes on the source before it runs on the
replica, and concurrent changes apply there only afterwards: a long change becomes replication lag.

### Shadow-table copy

- **Force** — The engine cannot do this change online, for example a type change that blocks writes, and the table is too large or too busy to stop.
- **How** — Create an empty copy with the new shape, copy rows in throttled batches, replay concurrent changes through triggers or the replication log, then swap the tables.
- **Cost** — Double the disk, extra write load during the copy, a short lock at the swap, and awkward foreign keys.
- **Not when** — A native online path exists, or a new column plus a backfill gets the same result through ordinary expand and contract. That route is usually easier to pause and verify.

---

## Idempotent migrations

- **Force** — A migration can stop halfway. MySQL commits implicitly around DDL, and `CREATE INDEX CONCURRENTLY` cannot run in a transaction, so "all or nothing" is frequently not on offer. The re-run has to cope with whatever the failure left.
- **How** — Each step checks the state it is about to create. Order the migration so a re-run from the top converges on the same schema.
- **Cost** — Engine-specific guards, and more code in a file that runs once.
- **Not when** — The whole migration runs in one transaction on an engine with transactional DDL, so a failure leaves nothing behind. Even then, guards help when environments have drifted.

Two details decide whether the guard really works:

1. **"Exists" is not "valid".** A failed concurrent build in PostgreSQL leaves an `INVALID` index behind, still costing update overhead. A guard on the name skips it and the application runs without the index. Check `pg_index.indisvalid`, drop what failed, rebuild.
2. **Keep DDL and data apart.** A long update in the same transaction as an `ALTER` holds that lock for its whole duration. Data work belongs in a [backfill](#backfills).

**Down migrations** deserve suspicion: a `down` that recreates a column cannot recreate its
contents. See [rollback vs roll forward](delivery-patterns.md#rollback-vs-roll-forward).

---

## Backfills

- **Force** — Many existing rows need a new value while live traffic keeps writing to them.
- **Cost** — A job to write, operate and watch, extended read and write load, and a period when two shapes coexist.
- **Not when** — The table is small enough for a single statement within your lock budget, or rows can be converted [lazily on read](#changing-stored-formats-while-old-code-reads-them). Do not run a long backfill inside the deploy's migration step: it holds up the release and a failure there looks like a failed deploy.

Each of these is a property to prove:

1. **Writers first.** Deploy code that writes the new shape *before* the backfill starts. Otherwise a row updated just after the job passes it holds a stale value forever.
2. **Dry run through the same code.** A switch that does everything except write, reporting how many rows would change, a sample of before and after, and every row that cannot be converted. Unconvertible rows are the finding that matters.
3. **Batch by indexed key range, never by `OFFSET`.** The server computes every skipped row, so offset batches slow down as they progress, and they shift when rows move.
4. **One short transaction per batch.** Locks stay brief and a failure loses one batch.
5. **Resumable.** Persist the last processed key after each batch. A restart continues from there; it does not start over.
6. **Idempotent and conditional.** Only touch rows still needing work (`WHERE new_col IS NULL`), so re-running is safe and live writes are not overwritten.
7. **Throttled.** Sleep between batches, watch replica lag and error rates, and give it a stop condition that does not need a person.
8. **Verified.** Compare counts and sampled values before switching reads. "The job finished" says nothing about the data being right.

---

## Unique indexes on dirty data

The check, cleanup and creation order is fixed by the
[schema rules](refactoring-workflow.md#refactoring-the-schema). This is what they do not tell you.

- **Force** — A rule the application believes is true has to become one the database guarantees.
- **Cost** — A cleanup that destroys or merges data, plus the application having to handle a violation as a normal outcome.
- **Not when** — The rule holds only for some rows. Then use a partial unique index (PostgreSQL) over the rows it applies to, such as those not soft-deleted, or reconsider the rule. On an engine without partial indexes, that needs another shape.

**Count duplicates the way the index will.**

| Trap | Behaviour |
|---|---|
| Collation | MySQL 8.4 defaults to `utf8mb4_0900_ai_ci`, so `'Ana'`, `'ANA'` and `'Aná'` collide. A byte-exact duplicate check finds nothing and the index still fails |
| NULL | PostgreSQL allows many by default (`NULLS NOT DISTINCT` allows one), MySQL allows many, a SQL Server `UNIQUE` constraint allows one |

**Which row survives is a business decision,** so ask. Repoint foreign keys to the survivor
before deleting, and copy removed rows somewhere first, since this step has no undo.

**Close the race.** Duplicates keep arriving while you clean. Deploy writers that avoid creating
them first, then clean, then build. Only the index truly closes the window.

**Online builds have sharp edges.** In PostgreSQL a concurrent unique build enforces uniqueness
before it finishes, so violations can surface in unrelated requests even if the build fails, and
a failed build's invalid index can go on enforcing it: drop it promptly. In MySQL, an in-place
build can report a temporary duplicate-key error from concurrent changes.

Afterwards, handle the duplicate-key error as an expected result in the code path, not a 500.

---

## Changing stored formats while old code reads them

- **Force** — During a rolling deploy and after a rollback, old and new code read the same data. New code must read old data (*backward compatibility*) and old code must survive new data (*forward compatibility*), as Kleppmann lays out in his chapter on encoding and evolution.
- **Default order** — Readers first. Teach every reader both formats and deploy; start writing the new format and deploy; backfill; remove the old read path. Rolling back the second step is safe because the previous release already understands both.

| Technique | Force | Cost | Not when |
|---|---|---|---|
| **Read both** | Old and new formats coexist during migration | A branch per format until the sweep is done | One atomic change is possible, with no live readers |
| **Version tag in the value** | Opaque values (JSON, blobs, queue payloads) have no schema to consult | Decoders for every live version | A typed column can express it |
| **Lazy migration on read** | Rarely touched rows make a backfill poor value, as with rehashing passwords at next login | Reads become writes, and the old format lasts until a final sweep | You must query or index the new format |
| **Dual write** | Old and new columns must both stay current for a while | Across two stores it races and can diverge silently | The two stores share no transaction: use the [outbox](distributed-patterns.md#transactional-outbox) |
| **Triggers as scaffolding** | Writers you do not control must keep old and new in sync | Hidden logic that must be removed on a date | You own every writer |

Kleppmann's case against dual writes: two clients can apply writes to two stores in different
orders, a crash can leave one applied, and no error reports it. Ambler and Sadalage call the
coexistence window a *transition period*; its scaffolding stays only until that period ends.

**Readers people forget:** the previous release, queue workers with jobs already serialized,
caches, sessions, exports, search indexes, analytics, replicas, and backups you may restore.

**Never reuse a name for a new meaning.** Moving `price` from euros to cents keeps the type, so
nothing fails and old readers are wrong by a factor of a hundred. Add a new column instead.

---

## Test databases that differ from production

### Same engine in tests

- **Force** — A test proves behaviour only on the engine it ran on, and fidelity is how closely a test reflects real behaviour (*Software Engineering at Google*, "Larger Testing").
- **How** — Same engine, same major version, same collation and configuration, in a disposable container or service.
- **Cost** — Slower startup and a service in CI.
- **Not when** — Pure logic that never touches persistence. Those tests should not have a database at all.

| What differs | Consequence with SQLite standing in for a server database |
|---|---|
| Foreign keys | Off by default, per connection; orphan-producing code passes |
| Types | Any column holds any type unless the table is `STRICT`, and there is no date type |
| Collation | `BINARY` by default, so case-insensitive uniqueness conflicts never appear |
| Locks and DDL | Nothing in this file about online change can be observed |

### Rehearsal on production-shaped data

- **Force** — Size and dirt are what break migrations; a hundred seeded rows have neither.
- **How** — Run the migration and the backfill on a recent copy, time them, and note locks and disk. Run migrations from scratch in CI as well, so the history itself stays valid.
- **Cost** — Storage, refresh tooling, and real risk: copied personal data needs masking, and handling it counts as a security decision. Sampling can reduce both size and exposure.
- **Not when** — The table is small and the change is additive.


---

## Indexes and their costs

Well-chosen indexes speed up reads and every index slows down writes, as Kleppmann puts it. So
the question is not "would this help that query?" but "is it worth a tax on all writes?"

- **Force** — A real, measured query is slow and selects a small part of the table.
- **Cost** — Write latency, storage, and maintenance. In PostgreSQL an update that changes an indexed column cannot be a heap-only tuple update, so it adds entries to every index on the table, not just that one.
- **Not when** — The table is small, the column matches most rows, the table is write-heavy and the query is rare, or no measurement shows a problem. See [Premature Optimization](antipatterns.md#premature-optimization).

| Shape | Force | Cost | Not when |
|---|---|---|---|
| **Composite** | Queries filter on several columns together | Usable only by leftmost prefix, so column order is a design decision | The columns are never queried together |
| **Covering** | A hot read can be served from the index alone | A wider index, costing more on each write | The read is not hot |
| **Partial** (PostgreSQL) | Queries target a small subset, or uniqueness applies to a subset | Only queries implying the predicate can use it | As a substitute for partitioning: many partial indexes make the planner test each one |

**Removing one is a change as well.** Counters such as `idx_scan` reset, so look across a full
business cycle and on replicas too. An index with no scans may still be enforcing uniqueness.
MySQL can hide an index from the optimizer first, a cheap way to test removal.

---

## Choosing: the honest defaults

1. **Prefer expand, backfill, contract over one clever statement.** It can be paused and verified at each step.
2. **Set a lock timeout on live tables, and guard every step for validity, not just existence.**
3. **Backfills run as resumable jobs with a dry run, not as migrations.**
4. **Count duplicates under the index's own collation and NULL rules.**
5. **Readers learn a format before writers produce it.**
6. **Tests run on the production engine; migrations are rehearsed on production-shaped data.**

---

## Sources

Martin Kleppmann, *Designing Data-Intensive Applications* (2017), chapters 3 "Storage and Retrieval" and 4 "Encoding and Evolution" (5 in the 2026 second edition, with Chris Riccomini); [Why dual writes are a bad idea](https://martin.kleppmann.com/2015/05/27/logs-for-data-infrastructure.html) ·
Scott Ambler & Pramod Sadalage, *Refactoring Databases* (2006) · Pramod Sadalage & Martin Fowler, [Evolutionary Database Design](https://martinfowler.com/articles/evodb.html) ·
Titus Winters, Tom Manshreck & Hyrum Wright (eds.), [*Software Engineering at Google*](https://abseil.io/resources/swe-book/html/ch14.html), "Larger Testing" ·
[PostgreSQL documentation](https://www.postgresql.org/docs/current/): CREATE INDEX, ALTER TABLE, Explicit Locking, LIMIT and OFFSET, Partial Indexes, Heap-Only Tuples; [lock manager notes](https://github.com/postgres/postgres/blob/master/src/backend/storage/lmgr/README) ·
[MySQL 8.4 manual](https://dev.mysql.com/doc/refman/8.4/en/): Online DDL Operations and Limitations, Implicit Commit, Multiple-Column Indexes, Invisible Indexes ·
SQLite: [Foreign Keys](https://www.sqlite.org/foreignkeys.html), [Datatypes](https://www.sqlite.org/datatype3.html) · SQL Server, [CREATE INDEX](https://learn.microsoft.com/sql/t-sql/statements/create-index-transact-sql). Original commentary.
