# Project rules

Architecture is decided, do not reopen it: controllers are pure REST, business logic lives in
Actions, and every side effect that follows an action is a domain event handled by a listener.
