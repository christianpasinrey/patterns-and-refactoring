# Application security patterns

Security decisions are design decisions about who may do what to which data, and where that
is enforced. Broken Access Control sits first in the OWASP Top 10:2025 and Insecure Design has
its own category, because these failures are structural: no amount of careful coding repairs a
check that was placed where it cannot see the object.

**How the YAGNI gate applies here.** An attacker is a named source of variation, so the
*control* is never speculative: every request is authorized, every secret stays out of the
repository. The *machinery* still has to pass the gate. A policy engine for three rules, or a
hand-built login, fails it like any other abstraction.

---

## Start here

| The question in front of you | Go to |
|---|---|
| "This feature adds a new surface or a new kind of data" | [Threat modelling](#threat-modelling-as-a-design-step) |
| "Where does this value or caller stop being trusted?" | [Trust boundaries](#trust-boundaries) |
| "Who is this caller?" | [Authentication](#authentication-vs-authorization) |
| "Where does the permission check go?" | [Controller anti-pattern](#anti-pattern-authorization-bolted-on-at-the-controller) |
| "What shape do the permission rules have?" | [RBAC, ABAC, ReBAC](#choosing-a-permission-model) |
| "Can one customer reach another's rows?" | [Tenant isolation](#tenant-isolation) |
| "Where does this credential live?" | [Secrets](#secrets) |
| "This value came from outside" | [Input handling](#input-handling) |
| "What happens if nobody configures this?" | [Secure defaults](#secure-defaults) |

---

## Threat modelling as a design step

- **Force** — A flawed design is cheapest to change before code depends on it, and a scanner cannot find a control that was never designed.
- **How** — Answer the four questions from the OWASP cheat sheet: what are we working on, what can go wrong, what are we going to do about it, did we do a good enough job. Sketch a data flow diagram with its trust boundaries, then walk each flow that crosses one through STRIDE as a prompt list.
- **Output** — Add it to the decision: *threat → mitigation*, or *threat → accepted, by whom*. An accepted risk with an owner is a valid result; an unexamined one is not.
- **Cost** — A focused session per feature, and a model that has to be updated as the system changes or it becomes misleading.
- **Not when** — TRIVIAL work, or a change that crosses no boundary and touches no new data. Tie it to triage: ARCHITECTURAL work always, STANDARD work when it adds an entry point, an integration, an input parser or upload, or a new class of personal data.

STRIDE names what each threat attacks: spoofing (authentication), tampering (integrity),
repudiation (accountability), information disclosure (confidentiality), denial of service
(availability), elevation of privilege (authorization).

---

## Trust boundaries

- **Force** — Data and callers change trust level when they cross from one owner to another, and something has to check them at that crossing.
- **How** — List the crossings for this kind of software: browser to server, tenant to tenant, service to service, webhook, queue consumer, admin tool, third-party response, and stored content another user wrote; on local software, arguments, parsed files, IPC, deep links, plugins and device input. Check once at each crossing, then carry a typed, validated value inward so inner code does not repeat the work.
- **Cost** — Internal callers need real credentials, every crossing needs an owner, and service-to-service checks add latency.
- **Not when** — Two modules in one process acting for the same principal. A function call is not a trust boundary; revalidating at every layer is noise that hides the checks that matter.

Three boundaries are routinely missed:

- **The internal network.** NIST SP 800-207 states the principle plainly: no implicit trust based solely on network location. "It is behind the VPN" is not an authorization decision.
- **The queue.** A job payload is input, and a job often runs long after the request that created it. Decide explicitly whether permissions are evaluated at enqueue or at execution, because a revoked user's queued export is a real case.
- **The service acting on behalf of someone.** A service that calls another with its own broad credentials can be steered into doing for a caller what that caller may not do. Pass the caller's identity along, and authorize against it.

---

## Authentication vs authorization

Authentication establishes *who* the caller is. Authorization decides *whether this caller may
do this to this object, now*. They fail differently: broken authentication lets a stranger
become a user, while broken authorization lets a legitimate user reach what is not theirs. The
second is far easier to ship, because every test logged in as a real user passes.

### Use a vetted authentication system

- **Force** — Credential storage, recovery, throttling and multi-factor flows have few correct shapes and many subtle wrong ones, and none of them is your product.
- **How** — Use the framework's authentication or an identity provider. Whichever you choose, verify these properties rather than assuming them.
- **Cost** — A dependency to keep current, and protocol complexity if you federate.
- **Not when** — A hosted provider would be a new dependency for an application the framework's built-in authentication already covers. Use the built-in one.

| Property | Requirement |
|---|---|
| Password hashing | Argon2id as first choice (OWASP Password Storage) |
| Password policy | No forced periodic change, no composition rules, length instead (NIST SP 800-63B) |
| Failure responses | Same message, status and timing for unknown user and wrong password, to prevent enumeration |
| Throttling | Count failures against the account, since an attacker can rotate IP addresses; let password reset work during a lockout |
| Multi-factor | Offered wherever practical; OWASP calls it the best defence against most password attacks |
| Sessions | Regenerate the session ID on login and on every privilege change |

Stateless tokens versus server sessions is the trade-off in
[enterprise-patterns.md](enterprise-patterns.md#session-state).

---

## Anti-pattern: authorization bolted on at the controller

- **Looks like** — A role check at the top of each action, followed by a lookup of whichever ID the URL supplied.
- **Why it fails, object level** — The route says "editors may update invoices", not "this editor may update *this* invoice". Skipping the object check is the first entry in the OWASP API Security Top 10:2023, Broken Object Level Authorization.
- **Why it fails, other doors** — Queue jobs, console commands, imports, webhooks, resolvers, exports and the second endpoint for the same data all reach the logic without passing that controller.
- **Why it fails, sets** — Lists, counts, search and reports need the rule *inside the query*. Filtering after loading breaks pagination and leaks through totals.
- **Why it fails, default** — Protection is something each action must remember. The action someone forgets is open, and nothing fails to tell you.
- **Cure** — Enforcement that is global and closed by default, with the decision in one place per resource and the scope inside data access:

| Layer | Decides | Failing closed looks like |
|---|---|---|
| Edge, middleware | An authenticated principal exists; the route is declared | A route with no declared access rule is rejected |
| Use case, service layer | May this principal do this operation to this object | The operation cannot be reached without a policy decision |
| Data access | Which rows exist for this principal | An unscoped query needs a named, greppable escape hatch |
| Response | Which properties this principal sees or sets | Allowlisted output and input fields, not entity serialization |

The Authorization Cheat Sheet asks for application-wide mechanisms and a decision on every
request, and ASVS 5.0 requirement 8.3.1 places enforcement at a trusted service layer.
Middleware alone cannot make the object check, because it has not loaded the object. **Test the
denials:** run the matrix of role, resource and action, asserting the *refusals*.

### Policy object

- **Force** — The same permission rule is needed from several entry points and must not drift.
- **Cost** — One more class per resource, and a convention everyone has to follow.
- **Not when** — One entry point and one rule. Frameworks usually ship policies and gates; check [framework-idioms.md](framework-idioms.md) before writing your own.

---

## Choosing a permission model

Write the rule as a sentence first; its grammar names the model. The OWASP cheat sheet prefers
attribute and relationship models over roles for application development, citing weak object
level control and role explosion. Take that as the warning about where roles stop working, not
as an instruction to install an engine. Most applications want a few roles for *function*
access plus an ownership or relationship rule for *object* access.

| Model | Rule sentence | Force | Cost | Not when |
|---|---|---|---|---|
| **RBAC** | "Accountants can open the billing section" | Permissions follow a small, stable set of job functions | Role explosion: `editor_region_north_team_b` is an attribute wearing a role's name | The decision depends on the object, on tenant membership, or on cross-organisation access |
| **ABAC** | "Managers can approve expenses under their limit, in their region" | The decision depends on attributes of subject, object, operation or environment, as NIST SP 800-162 defines it | "Who can see this record?" is hard to answer without evaluating policy; stale attributes become stale decisions | A few roles and an owner check already state the rules |
| **ReBAC** | "Anyone a document was shared with, or who belongs to a group owning its folder, can read it" | Access follows relationships users create at runtime: sharing, teams, nesting, delegation | A graph to store and traverse, and a consistency question: how soon does revoking a share take effect? | No sharing and no hierarchy. One `owner_id` comparison needs no graph |

---

## Tenant isolation

For the choice of database, schema or shared table, read
[architectural.md](architectural.md#multi-tenancy). OWASP does not mandate one model; it asks
that the boundary be documented and tested per data class. Whichever you choose, ASVS 8.4.1
requires that one tenant's consumers can never affect a tenant they have no access to.

### Tenant scope enforced by the data layer

- **Force** — Tenant scope added by hand to each query fails on the one query that forgot it, and shared tables make that a data breach.
- **How** — Resolve the tenant from server-verified identity and current membership; a client-supplied tenant ID is only a selector, never proof. Refuse to run when tenant context is missing.
- **Cost** — A global scope or row-level policy is invisible at the call site, background work needs an explicit context, and cross-tenant reporting needs a deliberate bypass.
- **Not when** — A database per tenant already isolates the data, and the connection is chosen from verified identity.

**Row-level security in PostgreSQL** moves enforcement below the application. Table owners
bypass policies unless the table is set to `FORCE ROW LEVEL SECURITY`, and superusers and
`BYPASSRLS` roles always bypass them, so the request role must be neither. Set the tenant with
transaction-scoped settings (`SET LOCAL`) so a pooled connection cannot carry it into the next
request. OWASP treats an ORM filter as defence in depth rather than complete enforcement.

**The channels teams forget:** cache keys must include the tenant wherever the value varies by
tenant; queued jobs must carry verified tenant context; file storage paths, logs, search
indexes and backup restores all have to respect the same boundary. Test isolation by asserting
that a second tenant's data is absent, as in
[testing-patterns.md](testing-patterns.md#testing-the-constraints-a-decision-depends-on).

---

## Secrets

- **Force** — A process needs a credential that must not live in the repository, the image or the logs, and whose useful life after a leak must be short. Software on users' devices cannot keep a shared secret: use per-user or per-device credentials, the platform keystore, or a backend that holds it.
- **How** — Pick the strongest delivery your platform supports, scope each secret to one service and one environment, automate rotation, and audit reads.
- **Cost** — A secret store is one more critical dependency, and rotation has to be rehearsed before it is needed.
- **Not when** — A secret store is not worth it for one small application on one host, provided the secret stays out of the repository, is scoped, and can be rotated.

| Delivery | Force it answers | Cost | Not when |
|---|---|---|---|
| Environment variable | Simple separation of config from code | Visible to the process tree, leaks into dumps and logs | The platform offers files or a store |
| Mounted file | Same simplicity with tighter access control | File permissions and reload logic to manage | The application cannot reread it on rotation |
| Fetched from a store | Central audit and access control | Runtime dependency at boot | One service, one host |
| Dynamic, short-lease | A stolen credential expires on its own | Needs a backend that can issue credentials | The dependency only supports static keys |

The Twelve-Factor App prefers environment variables to code; the OWASP cheat sheet advises
against them unless the alternatives are impossible. Both hold: they beat a committed file and
lose to a store.

**A leak is a revocation event.** Deleting the commit does not invalidate the credential, and
neither does restarting the application. Revoke first, then clean up.

---

## Input handling

- **Force** — External data reaches interpreters, queries, templates and object binders that treat some of it as instructions.
- **How** — Validate on the trusted side of the boundary against an allowlist of what is acceptable, checking syntax (format, type) and semantics (does this make sense for this operation). Then apply the control belonging to the *sink*: validation and output handling are separate defences.
- **Cost** — Schemas to maintain, and legitimate input rejected when rules are guessed. Blocking apostrophes rejects real names and fixes nothing.
- **Not when** — Do not escape on the way in. Encoding at input assumes one output context and corrupts stored data; keep the value intact and encode at output.

| Threat | Primary control | Not sufficient |
|---|---|---|
| SQL injection | Parameterized queries | Input filtering |
| Cross-site scripting | Context-aware output encoding; a maintained sanitizer for user-authored HTML | Regular expressions |
| Mass assignment | Bind to a DTO, or allowlist fields | Blocklisting, which misses every field added later |
| Server-side request forgery | Allowlisted destinations, a request you build yourself, redirects off, network egress rules | A denylist, except as a last resort |
| Unsafe deserialization | A pure data format such as JSON, with a DTO | Checking the type afterwards, when code may already have run |

---

## Secure defaults

- **Force** — The state nobody configured is the state that ships. Security Misconfiguration is A02 in the OWASP Top 10:2025, and Mishandling of Exceptional Conditions is A10.
- **How** — Access denied unless granted; new response fields hidden unless listed; debug output off; no default credentials; errors that end in refusal; least privilege for database roles, service accounts and CI credentials, reviewed periodically. State access rules explicitly, because the OWASP cheat sheet warns that framework defaults can change between versions.
- **Cost** — Every new route and field needs a deliberate grant, which is friction by design, and over-strict defaults invite blanket exceptions.
- **Not when** — Failing closed is not universal. A rate limiter or a recommendation call may reasonably fail open to protect availability, if the decision is written down. Authorization, tenant scope and signature checks never fail open.

---

## Choosing: the honest defaults

1. **Threat model anything ARCHITECTURAL, briefly.** Thirty honest minutes beat a template nobody reopens.
2. **Authorize in the use case and scope in the query.** The controller only proves there is a caller.
3. **Roles for functions, ownership or relationships for objects.** Add a policy engine when the rules outgrow code, not before.
4. **Tenant context comes from verified identity, and its absence is an error.**
5. **Never write your own password storage, token format or cryptography.**
6. **Validate at the boundary, encode at the sink, parameterize every query, default deny.**

---

## Sources

OWASP: [Top 10:2025](https://top10.owasp.org/2025) · [API Security Top 10:2023](https://api-security.owasp.org/editions/2023/en/0x11-t10) · [ASVS 5.0](https://asvs.owasp.org/), V8 Authorization ·
[Cheat Sheet Series](https://cheatsheetseries.owasp.org/): Authorization, Authentication, Password Storage, Session Management, Multi-Tenant Security, Secrets Management, Input Validation, Mass Assignment, Server-Side Request Forgery Prevention, Deserialization, Threat Modeling ·
NIST: [SP 800-207, Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final),
[SP 800-162, Guide to ABAC](https://csrc.nist.gov/pubs/sp/800/162/upd2/final),
[SP 800-63B, revision 4](https://pages.nist.gov/800-63-4/sp800-63b.html) ·
PostgreSQL, [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) ·
[The Twelve-Factor App, Config](https://12factor.net/config). Original commentary.
