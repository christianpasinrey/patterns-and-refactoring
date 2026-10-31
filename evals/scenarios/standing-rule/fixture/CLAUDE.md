# Project rules

Architecture is decided, do not reopen it: `internal/orders` never talks to the outside world
directly. Every external system is a port in `internal/ports` with an adapter in
`internal/adapters`, even when it has only one adapter.
