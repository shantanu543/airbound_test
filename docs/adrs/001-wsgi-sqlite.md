# ADR-001: Single-process WSGI and SQLite

- **Status:** Accepted for prototype
- **Date:** 2026-11-17

## Context

The deliverable needs to be easy to run and demonstrate locally without a package installation step. The workflow needs durable state and relational constraints for orders, parcel events, flights, and assignments.

## Decision

Use Python's built-in WSGI server and `sqlite3`, with a same-origin static frontend. Keep request handling in a small modular application and inject the database path for test isolation.

## Consequences

- The prototype starts with `python3 oms.py` and requires no third-party libraries.
- SQLite gives transactional writes and foreign-key/unique constraints for the demo.
- A single local process and database are not a high-availability or concurrent production deployment. There is no auth, connection pool, migration framework, rate limit, or scaling layer.
- Production should move to a managed relational database and supported application server behind a gateway. Migrate schema via versioned migrations; do not copy the SQLite file into a production environment.

## Alternatives considered

- FastAPI/SQLAlchemy/PostgreSQL: clearer production extension path and rich validation, but adds dependencies and setup that are unnecessary for the runnable prototype.
- Browser-only local storage: even simpler but fails to demonstrate server-side constraints and shared persistent operational state.
