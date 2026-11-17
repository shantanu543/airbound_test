# ADR-003: Validate route and payload capacity during assignment

- **Status:** Accepted for prototype
- **Date:** 2026-11-17

## Context

Assigning a parcel to the wrong route or exceeding nominal payload capacity would undermine the core planning demonstration. For the prototype, route names and package mass are the available inputs.

## Decision

The assignment endpoint requires exact pickup/origin and dropoff/destination string matches and calculates current assigned mass before adding the order. It rejects a route mismatch, duplicate assignment, or assignment that would exceed flight capacity. The assignment and order status/event writes share one transaction.

## Consequences

- Basic operational mistakes are rejected by the authoritative server, even if the UI has stale selection state.
- Text equality is fragile for real addresses and omits service zones, waypoints, route versions, dimensions, wind, battery reserves, and payload envelopes.
- Concurrent assignment writers need a stronger reservation/locking protocol; the current demo does not claim correctness under multi-process load.
- Production must use stable route/site IDs and a versioned flight readiness result. A separate safety/readiness authority must approve takeoff against current aircraft, weather, airspace, and pilot constraints. OMS must not infer that nominal mass alone means a flight is safe.

## Alternatives considered

- Let the UI perform capacity validation: rejected because stale clients could overbook and clients are not an authority.
- Add a routing/geospatial and flight-safety engine now: rejected for prototype scope because it requires authoritative map, aircraft, weather, and regulatory inputs not included with the project.
