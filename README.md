# Airbound Operations Management System

A small, dependency-free prototype for coordinating drone delivery orders, parcel handoffs, and flight assignments. The backend uses Python's WSGI server and SQLite; the frontend is plain HTML, CSS, and JavaScript.

## Run locally

Requires Python 3.9 or later. From the repository root:

```sh
python3 oms.py
```

Open [http://localhost:8000](http://localhost:8000). The database is created at `data/oms.sqlite3` on first launch. Set `PORT` to choose another port.

## Core workflow

1. Create a delivery order and add recipient, route, weight, and urgency.
2. Plan a flight with a drone, pilot, route, departure time, and payload capacity.
3. Assign route-matched orders to the flight. The API checks available payload capacity.
4. Advance the parcel through pickup, in-transit, and delivered states; each update appends a timestamped tracking event.

The UI shows the live order queue, summary counts, flight load, search, and priority filtering. All data is local to the prototype database.

## API quick reference

All request bodies and responses use JSON. Error responses have the form `{"error":"..."}`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness check |
| GET, POST | `/api/orders` | List orders; create an order |
| GET | `/api/orders/{id}` | Order details and parcel timeline |
| PATCH | `/api/orders/{id}/status` | Advance a parcel status |
| POST | `/api/orders/{id}/events` | Record a location and valid next status |
| GET, POST | `/api/flights` | List flights; plan a flight |
| POST | `/api/flights/{id}/assign` | Assign a route-matched order within capacity |

See [docs/low-level-design.md](docs/low-level-design.md) for fields and response details. [docs/high-level-design.md](docs/high-level-design.md) describes the wider production target and boundaries.

## Tests and performance profile

```sh
python3 -m unittest discover -s tests -v
python3 scripts/profile_list_orders.py --orders 1000 --repeats 5
```

The profile script measures the WSGI app in-process using a temporary SQLite database. Results are local microbenchmark evidence, not a production capacity estimate; interpretation and the query improvement are in [docs/profiling.md](docs/profiling.md).

## Project notes

- [High-level design](docs/high-level-design.md)
- [Low-level design](docs/low-level-design.md)
- [Architecture decision records](docs/adrs/)
- [Production plan for a small team](docs/production-plan.md)

## Prototype scope

This is an operational demo, not a flight safety or regulatory system. It has no authentication, authorization, real drone telemetry, route/weather/airspace validation, persistent task queue, or multi-region availability. Those concerns are made explicit in the design and production plan.
