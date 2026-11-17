# Taking the Prototype to Production with a Small Team

## Operating principles

- Treat this OMS as a coordination and evidence service. Drone flight control, obstacle avoidance, and safety interlocks remain in the aircraft/fleet system.
- Do not release dispatch without a versioned readiness decision from authoritative fleet, airspace, weather, and pilot systems.
- Keep rollout reversible and start with one hub, one vehicle class, one delivery category, and an explicit human dispatch gate.

## Suggested team

Four to six people can deliver the first controlled pilot: one product/operations lead, two backend engineers (one owns integrations/data), one frontend engineer, one platform/security engineer shared part time, and a test/flight-operations specialist shared with the drone program. The flight safety authority and privacy/legal representative are required reviewers, not optional downstream stakeholders. A smaller team can combine roles but should preserve independent safety review.

## Phased delivery

### Phase 0 — Validate the operation (1–2 weeks)

- Map current hub intake, package custody, flight authorization, no-fly/abort, return, and delivery proof procedures.
- Agree status definitions, exception ownership, SLAs, retention, and offline/manual fallback.
- Confirm volume, peak concurrency, service boundary, aircraft and pilot systems, and applicable jurisdictional requirements with counsel and safety owners.
- Convert operational cases into acceptance scenarios, especially stale telemetry, duplicate scans, loss of connectivity, and abort/return.

### Phase 1 — Harden the operational core (3–5 weeks)

- Replace the demo server with a supported web framework and managed PostgreSQL; introduce versioned migrations and repository/service boundaries.
- Add SSO/MFA, dispatcher/hub/pilot/support roles, audit actor IDs, secure secret storage, TLS, encryption at rest, CSRF protection, rate limits, and input/output schemas.
- Add idempotency keys, pagination, optimistic versions, active-assignment history, safe concurrent capacity reservations, and an outbox in the same transaction as state changes.
- Implement hub scans, package dimensions/hazards, delivery windows, proof of handoff, exception/return handling, and operator override audit.
- Create integration contract tests with stubs and reconciliation jobs for partners, identity, fleet, and notification systems.

### Phase 2 — Safety and integration validation (4–8 weeks, parallel)

- Integrate authoritative drone status, maintenance/battery, pilot assignment, route/geofence, airspace approval, and weather sources through versioned adapters.
- Specify readiness outputs, validity period, source timestamps, and fail-closed conditions with the designated safety authority.
- Ingest telemetry via authenticated broker/API; deduplicate by producer event ID, record observed/received times, and flag sequence gaps and stale feeds.
- Run simulator and hardware-in-the-loop scenarios, including link loss, diversion, emergency landing, and return-to-hub.
- Conduct threat modeling, privacy review, penetration testing, backup restore, incident drills, and operational training.

### Phase 3 — Controlled pilot and scale decision (2–4 weeks)

- Launch one hub with human approval before every dispatch and a documented manual fallback. Use shadow mode first to compare system recommendations with current dispatch decisions.
- Monitor false readiness, assignment conflicts, telemetry lag, package custody gaps, late deliveries, failed handoffs, safety incidents, and operator workload.
- Set explicit pause/rollback thresholds with the safety and operations leads; collect evidence before expanding fleet, hubs, or autonomy.
- Review capacity, cost, and recovery evidence; then decide whether to scale to more hubs or add a separate optimization service.

Durations are directional planning estimates and depend on partner access, regulatory approvals, and test-fleet availability.

## Production architecture and deployment

- Deploy a stateless API and operator SPA behind an identity-aware gateway. Use a managed PostgreSQL cluster with automated backups, point-in-time recovery, and tested failover.
- Publish domain events through a transactional outbox to a managed broker. Isolate telemetry and notifications in consumers with bounded retries, dead-letter queues, idempotent handlers, and replay controls.
- Use infrastructure as code, separate dev/staging/prod accounts, managed secrets, signed build artifacts, dependency scanning, and reviewed CI/CD with canary/blue-green rollback.
- Separate raw telemetry from operational records; apply retention and data minimization. Use object storage for larger immutable artifacts and encrypted evidence references.
- Initially deploy in one region across availability zones. Set recovery objectives with operations and verify them in restore and failover exercises before considering multi-region writes.

## Readiness checklist for launch

- Named service owner, on-call rotation, escalation path, incident severity guide, and tested support runbooks.
- Agreed SLOs and dashboards for API availability/latency, event lag, stale telemetry, dispatch queue age, failed handoff, and integration errors.
- Reconciled partner order counts, idempotent webhook replay, backup restoration, and manual dispatch fallback demonstrated in a drill.
- Privacy retention and access review complete; audit records available for overrides and handoff decisions.
- Safety case approved by accountable authority; readiness inputs are current and fail closed; simulator/HIL evidence covers lost link and abort paths.
- Rollback criteria and the operator communication plan are written and exercised.
