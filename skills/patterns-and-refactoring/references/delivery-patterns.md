# Delivery patterns

A deployment is not an instant. For minutes, sometimes hours, several versions of your code run
against one database and one queue. Most release incidents happen inside that window, and most
designs pretend it does not exist.

Deploying and releasing are separate acts: code can reach production dark and be exposed later.
And the DORA research behind *Accelerate* found that speed does not come at the expense of
stability, so a slower, larger release is not the safe one.

The force throughout is concurrent versions under live traffic. Without it, a short maintenance
window is a legitimate design and most of this file is unnecessary.

---

## Start here

Answer these before merging anything that touches a schema, a message or a stored format.

| Question | If the answer is no |
|---|---|
| Can the **previous** code run on the **new** schema? | [Reorder the deploy](#backward-compatible-deploy-order) |
| Can the **new** code run on the **previous** schema, for the rollout's duration? | Expand first, in an earlier deploy |
| Can a worker built from either release read jobs written by the other? | [Version the payload or drain](#long-lived-workers) |
| Is the rollback target still valid after this migration? | You are committed to [roll forward](#rollback-vs-roll-forward); say so now |
| Will a metric show this release is unhealthy, tagged by version? | [Add the signal first](#observability-to-know-a-release-is-healthy) |

---

## The migrate-to-restart window

### Every neighbouring pair must be compatible

- **Force** — The schema changes at one moment, web processes roll over minutes, and workers restart last. Between those moments every pairing occurs: old code on the new schema, new web feeding old workers, new workers reading old jobs.
- **How** — For each change, write the pairs out and ask what each one does. Typical failures are an old worker selecting a dropped column, a process caching table metadata from startup, and a job class that exists only in the new release.
- **Cost** — More deploys per change, and a phase in which code has to tolerate both shapes.
- **Not when** — You can stop the world: traffic off, queue drained, workers stopped, migrate, start. For an internal tool that is simpler and entirely honest.

---

## Backward compatible deploy order

**The rule: the schema expands first and contracts last. A reader tolerates a shape before any
writer emits it, and every writer produces a shape before any reader requires it.** Removal is
the same rule reversed: readers stop requiring it before writers stop producing it.

| Change | Order |
|---|---|
| Add a column | Migrate → deploy code that uses it |
| Remove a column | Deploy code that stops reading → stops writing → verify → drop, in a later deploy |
| Rename a column | Expand and contract, per [refactoring-workflow.md](refactoring-workflow.md#parallel-change-expand--contract) |
| New optional field in a message | Consumers tolerate it → producers send it |
| New enum value | Consumers handle it → producers emit it |
| New job type | Workers know it → producers enqueue it |
| Make a field required | Producers always send it → consumers require it |

Newman catalogues the alternatives to this: lockstep deployment and coexisting incompatible
versions. Both exist because compatibility was not achievable, and both cost more than it.

### Schema deploys separate from code deploys

- **Force** — A compatible schema change can be verified alone, which gives a rollback point before any code depends on it. That is the blue-green database sequence: deploy a change that supports both versions, verify, deploy the application, later remove the old support.
- **Cost** — Two pipeline runs per change, and discipline to do the second one.
- **Not when** — The migration is additive and already compatible; running it just before rollout in one pipeline is fine. Destructive steps stay separate regardless. See [refactoring-workflow.md](refactoring-workflow.md#refactoring-the-schema).

**Run migrations once, from one place.** Several replicas each migrating at boot race each other,
and a long migration then holds up their startup and health checks.

---

## Long-lived workers

A worker, a consumer or a scheduler keeps its code and configuration in memory across deploys.

### Graceful shutdown

- **Force** — Restarting must not lose or corrupt in-flight work. The Twelve-Factor App's rule: on `SIGTERM` a web process stops listening and finishes current requests, and a worker hands its job back to the queue.
- **How** — Stop taking new work, finish or return the current job, exit. Returning jobs assumes they can safely run again, so reentrancy is a precondition; see [Idempotent Receiver](distributed-patterns.md#idempotent-receiver).
- **Cost** — Deploys take as long as the slowest job, unless long jobs are split or checkpointed. A job longer than the platform's kill timeout dies mid-flight regardless.
- **Not when** — Never skip it for work with side effects. A stateless, disposable consumer may accept redelivery alone.

### Explicit restart with a version check

- **Force** — "We deployed" does not prove workers run the new code.
- **How** — Restart as a pipeline step, and have each worker report its build identifier, so the pipeline can confirm that no old version remains.
- **Cost** — A small amount of reporting plumbing.
- **Not when** — The platform replaces processes on each deploy and already shows you which version is running.

### Queued work outlives the release

- **Force** — A job written today may run after the next deploy. Delayed and scheduled jobs and dead-letter replays can outlast several releases.
- **How** — Keep payloads small and explicit: IDs plus a version, never serialized objects from your own class hierarchy. Treat payloads like any stored format, as in [data-evolution.md](data-evolution.md#changing-stored-formats-while-old-code-reads-them), and contract a job shape only when the oldest scheduled job has run.
- **Cost** — Handlers tolerate older shapes for as long as those jobs can exist.
- **Not when** — The queue is empty at every deploy and nothing is delayed; even then, verify rather than assume.

### A new queue for incompatible work

- **Force** — A change is too large for one handler to read both shapes.
- **How** — Add a new queue or job type, run workers for both, send new work to the new one, and retire the old one when it drains.
- **Cost** — Additional worker configuration, and a retirement step that gets forgotten.
- **Not when** — An optional field would have done it.

---

## Feature flags

- **Force** — Separating deploy from release, so unfinished code can merge and a risky change can be turned off without a build. *Software Engineering at Google* advises flag-guarding changes for this reason.
- **Cost** — Each flag roughly doubles the states the code can be in, adds a conditional, and needs a test plan. Flag flips are production changes too: the same book warns that they need careful rollout.
- **Not when** — A small change that a redeploy reverses quickly. Or a schema change: a flag can hide new code, never undo a migration. Or a security boundary, where a flag service outage must not decide access. Or a business rule pretending to be configuration, the [soft-coding](antipatterns.md#soft-coding) trap.

Hodgson's taxonomy matters because each kind has a different lifetime and owner:

| Kind | Answers | Lifetime | Removal |
|---|---|---|---|
| **Release** | Incomplete work is merged but dark | Days to weeks | Ticket created with the flag, deleted after full rollout |
| **Experiment** | Which variant performs better | Until statistically significant | Deleted with the losing branch |
| **Ops** | Shed load or disable a feature during an incident | Mostly short; kill switches may be long-lived | Reviewed, since an untested switch fails when needed |
| **Permissioning** | Which users get a feature | Can last years | Not really a flag: treat it as entitlement data |

Rules that keep the inventory down:

- **Default off means old behaviour**, and an unreachable flag service must resolve to a safe default.
- **Test what can occur**: the production configuration with the new flags on, the same with them off, and occasionally everything on. Do not chase all combinations.
- **Give each flag an expiry**, even a test that fails once it passes. Cap the total count if needed.
- **Decide when jobs evaluate it.** A flag read at enqueue and one read at execution behave differently during the rollout.
- **Remove the branch as well.** See [Branch by Abstraction](refactoring-workflow.md#branch-by-abstraction), where the skipped last step is the usual failure.

---

## Rollout strategies

Whichever you use, schema and messages must support both versions during the rollout, and a
strategy never substitutes for that compatibility.

| Strategy | Force | Cost | Not when |
|---|---|---|---|
| **Rolling** | Replace instances gradually with no spare environment | No clean comparison; mixed versions for the whole duration | You need an instant, complete switch back |
| **Blue-green** | A complete, tested environment and a one-step rollback by switching the router | Two production-grade environments, transactions missed during a switch back, connections and sessions to handle | The database cannot serve both versions |
| **Canary** | Limit exposure and measure the real release under real traffic | Multiple live versions, routing control, and analysis | Too little traffic for a signal, or a defect the sampled traffic cannot reach |

**Canary analysis, done properly** (*The Site Reliability Workbook*): compare canary and control
side by side, because before-and-after comparisons are confounded by time. Use a small set of
user-facing metrics, perhaps no more than a dozen, and prefer status codes and latency to CPU.
Run one canary at a time. The population has to be large enough, and the duration long enough,
to be representative; for non-interactive work, at least one unit of work.

**Workers are the blind spot.** A canary of web instances says nothing about a job that runs
nightly. Route a share of jobs to new workers, or accept that this code has no canary.

---

## Rollback vs roll forward

Code can go backwards; data does not. Choose before the deploy, by asking what the release
writes, then keep the answer in the release notes.

| Situation | Move | Why |
|---|---|---|
| Behind a flag | Flag off | Fastest, no deploy |
| Code only, schema compatible | Roll back code | The previous build is known to work |
| Additive migration ran | Roll back code, leave the schema | The old code ignores the new column |
| New format already written, and old readers cannot read it | Roll forward | Old code would misread or fail |
| Contract step ran | Roll forward | The data is gone from the schema |
| Bad data written | Stop the writer, then repair forward | Neither move fixes rows already written |

### Rollback

- **Force** — The fastest route back to a known-good state, shortening failed deployment recovery time.
- **Cost** — Rollback must be practised and the target must still work on today's schema; data written meanwhile stays.
- **Not when** — The release wrote something the old code cannot read, or a destructive migration has run. Check [migration status first](refactoring-workflow.md#refactoring-the-schema), since a framework rollback undoes the last successful migration, which may not be the one you think.

### Roll forward

- **Force** — Moving back is impossible or more dangerous than a small fix.
- **Cost** — A fix under pressure, so it needs a fast pipeline and the same checks as any other change. No hand edits in production.
- **Not when** — The cause is unknown and a safe rollback exists. Restoring service comes before understanding it.

---

## Observability to know a release is healthy

- **Force** — The decision to continue or stop needs a signal, and a green deploy step shows only that processes started.
- **Cost** — Instrumentation, version labels on telemetry, thresholds to maintain, and time spent watching a release finish baking.
- **Not when** — Scale it down, but do not drop it. A small service still needs errors and latency by version, plus queue age if it has workers.

**Define healthy before the deploy.** A threshold chosen while staring at a graph is a
rationalization. Mark each deployment on the dashboards, label all telemetry with the build
identifier so old and new can be compared, and page on symptoms users feel rather than causes.

| Signal | What it answers |
|---|---|
| **Latency** by version | Slower? Track failed requests separately, since a slow error is worse than a fast one |
| **Traffic** | Did requests stop arriving, which can look healthy? |
| **Errors** | Explicit ones, and implicit ones such as a `200` with wrong content |
| **Saturation** | How full is the tightest resource? Latency often moves first |
| **Business outcome** | Are orders, sign-ups, or messages still happening at the usual rate? |
| **Queue age and failures** | Oldest job's age, failures per job type, arrivals in the dead letter channel |
| **Migration effects** | Lock waits, replica lag, backfill progress |

The first four are the golden signals from *Site Reliability Engineering*. The business row
catches what they miss: a release that fails politely.

**Measure delivery itself** with the DORA metrics, currently change lead time, deployment
frequency, failed deployment recovery time, change fail rate and deployment rework rate. As with
the refactoring metrics in [refactoring-workflow.md](refactoring-workflow.md#measuring-that-it-worked),
they show direction over months. They do not grade a team.

---

## Choosing: the honest defaults

1. **Assume two versions are live at once**, unless you truly stop everything.
2. **Schema expands first and contracts last; tolerate before emitting, produce before requiring.**
3. **Destructive changes go out alone, a deploy after the last reader is gone.**
4. **Restart workers explicitly and confirm their version.** Treat queued jobs as stored data.
5. **Flags are inventory.** Every release flag has a removal ticket from day one.
6. **Rolling by default, canary when traffic gives you a signal, blue-green when instant switch-back justifies a second environment.**
7. **Decide rollback or roll forward before deploying, and call a release without a version-tagged signal unverified.**

---

## Sources

Nicole Forsgren, Jez Humble & Gene Kim, *Accelerate* (2018) · DORA, [software delivery metrics](https://dora.dev/guides/dora-metrics/) and [their history](https://dora.dev/insights/dora-metrics-history/) ·
Jez Humble & David Farley, *Continuous Delivery* (2010), chapters 10 "Deploying and Releasing Applications" and 12 "Managing Data" ·
Sam Newman, *Building Microservices*, 2nd ed. (2021), chapters 5, 8 and 10 · Michael Nygard, *Release It!*, 2nd ed. (2018), "Design for Deployment" and "Handling Versions" ·
Titus Winters, Tom Manshreck & Hyrum Wright (eds.), [*Software Engineering at Google*](https://abseil.io/resources/swe-book/html/ch24.html), "Continuous Delivery" ·
Betsy Beyer et al., *Site Reliability Engineering*, [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/); *The Site Reliability Workbook*, [Canarying Releases](https://sre.google/workbook/canarying-releases/) ·
Martin Fowler, [Blue-Green Deployment](https://martinfowler.com/bliki/BlueGreenDeployment.html) · Danilo Sato, [Canary Release](https://martinfowler.com/bliki/CanaryRelease.html) · Pete Hodgson, [Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) · [The Twelve-Factor App, Disposability](https://12factor.net/disposability). Original commentary.
