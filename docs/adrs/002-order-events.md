# ADR-002: Append tracking events and maintain a current status projection

- **Status:** Accepted for prototype
- **Date:** 2026-11-17

## Context

Operations and support need both the parcel's current state and an explainable custody timeline. Updating only one status field would erase the history needed to investigate handoff delays.

## Decision

Keep `orders.status` as the current projection and append a `parcel_events` row for each valid transition. Update both in one database transaction and reject transitions outside the allowed state graph. The order list reads the projection; the order detail reads its timeline.

## Consequences

- The UI can give a fast queue view while a support view can reconstruct events.
- A process crash cannot commit only one of the status and event writes when both are in the same transaction.
- The prototype lacks actor identity, source, event ID, observed-vs-received times, immutable storage enforcement, and robust out-of-order reconciliation.
- Production should accept idempotent events, preserve provenance, and make the projection rebuildable. Customer notifications should consume a transactional outbox, not be sent inside the state update transaction.

## Alternatives considered

- Full event sourcing: potentially useful for audit/replay, but imposes event schema evolution, projection, and operational overhead before the workflow is proven.
- Mutable status only: smallest schema, but loses evidence needed to answer where a parcel was handed over or when it changed state.
