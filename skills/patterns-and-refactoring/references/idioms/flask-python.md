# Flask · Python

[← back to router](../framework-idioms.md)

Written against Flask 3.1. The Python language table in [django-python.md](django-python.md) also
applies here. Flask decides little on purpose: no database layer, no form library, no container.
So the question is less "what does it give me" than "which seam did it leave, and what does each
choice cost".

---

## What Flask already gives you

| Pattern | Where it already lives | Do this, not that |
|---|---|---|
| **Factory Method** | Application factory, `create_app()` | One function builds and returns the app. A single-file service can skip it |
| **Front Controller** | `Flask.wsgi_app()` + Werkzeug routing | Declare routes in any order; Werkzeug sorts them. Write no dispatcher |
| **Template Method** | `View`, `MethodView` | `MethodView` replaces `if request.method == "POST"`. A class reads heavier than a function, so keep it for reuse |
| **Chain of Responsibility** | `before_request`, `after_request`, WSGI middleware | A value returned from `before_request` short-circuits the view |
| **Decorator** | View decorators; `View.decorators` | Use `functools.wraps`; `route` stays outermost. On class views use `decorators`: the class is not the view function |
| **Observer** | Signals (Blinker); `Namespace` for your own | For metrics, audit and tests. Core flow belongs in a direct call |
| **Context Object** | `g`, `request`, `session`, `current_app` | `g` lasts one context, never between requests |
| **Proxy** | `LocalProxy` behind every context global | `isinstance` fails on a proxy, and signal senders need `_get_current_object()` |
| **Registry** | `app.extensions` | One flat namespace: use a unique key |
| **Strategy** | `app.session_interface`, `app.json` provider | Set during setup only. Replace the interface rather than patching behaviour |
| **Exception translation** | `@errorhandler`, by code or class | Map domain exceptions once, and set the status yourself. A handler for `Exception` also catches every HTTP error |
| **Data Mapper + Unit of Work** | **Not provided.** SQLAlchemy, usually via Flask-SQLAlchemy | The session is scoped to the app context and cleaned up after each request or CLI command |
| **Command** | **Not provided.** Celery, with the documented `FlaskTask` | Pass IDs, not model objects; a model is tied to the session that loaded it |
| **Form Object** | **Not provided.** WTForms, or Flask-WTF on top | Worth it once there are many forms |

---

## The application factory

```python
db = SQLAlchemy()  # no app yet: the extension holds no per-app state

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object("project.default_settings")
    app.config.update(test_config or {})
    db.init_app(app)
    app.register_blueprint(orders)
    return app
```

**Buys:** an app per test with its own config, several instances in one process, and no circular
import between app and views, because views use `current_app`.

**Costs:** no `app` to import, so `@app.route` is gone and import-time code cannot read config.
Tools needing a module-level object need an entry point: Celery points at a `make_celery.py`.

**Skip it** for a single-file service with one configuration; the test client works on a plain app
too. Adopt it when a second configuration or a circular import appears.

Finish all setup before serving. Registering routes or changing config from a request is unsafe:
workers would diverge, and Flask only catches some of these cases.

---

## Blueprints: a recording, not a module system

A blueprint records operations and replays them on `register_blueprint`. A three-route app does
not need one; add them when a second feature wants its own prefix.

- **They share everything:** one config, one extension set, one `g`. A blueprint is a folder with a URL prefix, not a boundary.
- **For real isolation, dispatch at WSGI level.** `DispatcherMiddleware` combines separate apps with separate configs, at the cost of sharing nothing.
- **A blueprint cannot be unregistered** without discarding the app object, and registering twice works only if it was written for that.
- **Blueprint 404 and 405 handlers do not fire on bad URLs**, because routing fails before any blueprint owns the request. Branch on `request.path` in an app-level handler.
- **Blueprint `before_request` runs only for its own routes**, the right place for auth on a group. A parent blueprint's handlers apply to its children.
- **App templates override blueprint templates**, so namespace them: `orders/templates/orders/`.

---

## Request context: convenient, and a coupling you chose

`request` and friends are context-local proxies over `contextvars`. They save passing arguments,
and they make any function touching them depend on an active request.

**Read the request in the view, then pass plain values down.** A function reading `request` needs
`test_request_context()` to test and cannot run from a CLI command or a Celery task. A function
taking `user_id` runs anywhere. `current_app` in a service has the same cost, more gently.

- **Contexts do not cross threads.** A new thread has no `request`. Passing the data you need is the documented preference over `copy_current_request_context()`.
- **`g` is the per-request resource slot:** `get_x()` caches on `g`, and a `teardown_appcontext` function closes it. DI by convention, adequate for most Flask apps.
- **Teardown runs even after an unhandled exception**, with no guarantee earlier stages ran, so it must tolerate missing state and must not fail.
- **"Working outside of application context"** during setup means push `with app.app_context():`. Elsewhere it usually means the code belongs in a view or CLI command.
- **Flask 3.2**, unreleased at the time of writing, merges `RequestContext` into `AppContext`, keeping the old name as a deprecated alias. Avoid building on the distinction.

---

## Extensions are the integration seam

Integration lives in extensions, configured from `app.config` and attached through `init_app(app)`.

**Writing your own is justified** when a client needs per-app config and per-request lifecycle, and
more than one app will use it. Follow the contract: no `self.app`; `current_app` outside
`init_app`; prefix config keys and `g` attributes; keep state in `app.extensions`.

**It is not justified** for one app and one client. A module with `get_client()` and a teardown
function is ten lines, and the contract buys nothing without a second consumer.

**The costs of depending on them:**

- Flask retired its approved-extensions list, so maintenance is yours to check before adopting one.
- Extensions predating async support will probably not work as decorators on `async def`. Check the changelog; authors adapt through `ensure_sync()`.
- An extension hides lifecycle behind globals. `scoped_session` plus a `teardown_appcontext` calling `remove()` is the documented alternative to Flask-SQLAlchemy.

---

## When does Flask stop being the right choice?

The most-argued decision here. "Flask does not scale" is no argument: "micro" describes the core,
not production readiness. Decide on what the workload asks for.

**Staying is justified when:**

- The app is traditional request and response, and WSGI workers fit the load.
- Each decision (ORM, auth, validation) really is better made per project.
- It is a small service where a heavier framework would bring more than it returns.

**Moving is justified when:**

- **The workload is mostly concurrent I/O.** `async def` views still hold one worker per request, so capacity does not rise. Look at Quart, a Flask reimplementation on ASGI. Gevent gets close without a rewrite, but it relies on monkey-patching and combines badly with asyncio.
- **You need in-process background tasks.** Tasks spawned in an async view are cancelled when it returns. Use a queue, or wrap the app with `WsgiToAsgi`.
- **The API is the product.** If you are assembling validation and OpenAPI by hand, [FastAPI](fastapi-python.md) has them built in.
- **You have rebuilt Django.** Auth, admin, forms, ORM and migrations from extensions mean you own an integration [Django](django-python.md) maintains for you.

**Migration is a rewrite of the seams** (context globals, extensions, tests), so the trigger must
be a present requirement. Keeping use cases free of `request` is the cheap insurance. Repository
questions follow the ORM, not Flask: see [fastapi-python.md](fastapi-python.md#repository-over-sqlalchemy).

---

## Python features that replace patterns here

| Feature | Replaces |
|---|---|
| **Decorators + `functools.wraps`** | Base controllers that exist only to share auth or caching |
| **`contextvars`** (via Flask's proxies) | Passing a request through every layer. Edge only: the proxy hides the dependency |
| **Modules** | Singleton classes. A module-level extension object is one instance, with state per app |
| **Pytest fixtures around `create_app()`** | A hand-rolled test base class managing app lifecycle |

---

## Signs you are fighting the framework

- `from project import app` inside views, with late imports working around the cycle.
- `self.app = app` in an extension or a service.
- `request` read deep in service code, forcing `test_request_context()` in unit tests.
- `current_app.config` mutated while serving.
- Business flow running through signals, which are meant to observe.
- `asyncio.create_task()` in a view, expecting it to outlive the response.
- `async def` everywhere under WSGI, expecting more throughput.

---

## Sources

Flask: [application factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) · [blueprints](https://flask.palletsprojects.com/en/stable/blueprints/) · [app context](https://flask.palletsprojects.com/en/stable/appcontext/) · [request context](https://flask.palletsprojects.com/en/stable/reqcontext/) · [lifecycle](https://flask.palletsprojects.com/en/stable/lifecycle/) · [extensions](https://flask.palletsprojects.com/en/stable/extensions/) · [extension development](https://flask.palletsprojects.com/en/stable/extensiondev/) · [design decisions](https://flask.palletsprojects.com/en/stable/design/) · [async](https://flask.palletsprojects.com/en/stable/async-await/) · [gevent](https://flask.palletsprojects.com/en/stable/gevent/) · [ASGI](https://flask.palletsprojects.com/en/stable/deploying/asgi/) · [class-based views](https://flask.palletsprojects.com/en/stable/views/) · [view decorators](https://flask.palletsprojects.com/en/stable/patterns/viewdecorators/) · [signals](https://flask.palletsprojects.com/en/stable/signals/) · [error handling](https://flask.palletsprojects.com/en/stable/errorhandling/) · [configuration](https://flask.palletsprojects.com/en/stable/config/) · [testing](https://flask.palletsprojects.com/en/stable/testing/) · [SQLAlchemy](https://flask.palletsprojects.com/en/stable/patterns/sqlalchemy/) · [Celery](https://flask.palletsprojects.com/en/stable/patterns/celery/) · [WTForms](https://flask.palletsprojects.com/en/stable/patterns/wtforms/) · [application dispatching](https://flask.palletsprojects.com/en/stable/patterns/appdispatch/) · [changes](https://flask.palletsprojects.com/en/latest/changes/).
[Flask-SQLAlchemy contexts](https://flask-sqlalchemy.palletsprojects.com/en/stable/contexts/). [Django documentation](https://docs.djangoproject.com/en/stable/). Martin Fowler, *Patterns of Enterprise Application Architecture* (2002), for the pattern names. Original commentary.
