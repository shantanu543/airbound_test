# Profiling and Improvement

## Target component

The order-list API is on the main dashboard load path, so an avoidable per-row query cost becomes noticeable as the queue grows. The initial implementation fetched all order IDs and then called `order_payload` for each order. That meant two additional `SELECT`s per order (order detail and optional flight), even though the list needed only a compact summary.

## Method

`scripts/profile_list_orders.py` seeds a temporary SQLite database, invokes the WSGI app in-process five times, and reports median wall time and traced `SELECT` count. The run used 1,000 orders on the local development machine with a temporary SQLite file. The measurement excludes browser rendering, network, cold process startup, and concurrent writers. It is a microbenchmark, not an SLA or capacity claim.

Command:

```sh
python3 scripts/profile_list_orders.py --orders 1000 --repeats 5
```

## Result

| Measure | Before | After | Change |
| --- | ---: | ---: | ---: |
| Median in-process list time | 21.71 ms | 5.22 ms | 4.16× faster (about 76% lower) |
| SQLite `SELECT`s for 1,000 orders | 2,001 | 1 | 2,000 fewer |

The baseline was measured with the initial per-order lookup implementation; the after value is reproducible with the checked-in script. Hardware and Python/SQLite versions can change timings. Query count is the more stable evidence for the change in work performed.

## Change made

`list_order_payloads` now uses one `LEFT JOIN` from orders through assignments to flights and constructs compact list records from those rows. `list_flight_payloads` similarly groups assignments once to calculate flight load and assigned IDs. Detail reads keep their separate timeline query because a detail response has a different shape.

## Trade-offs and next steps

- The joined list query returns a compact order/flight record and avoids the N+1 pattern, but currently loads the whole queue into memory. Add cursor pagination, filters, and a bounded default page before production scale.
- The microbenchmark does not include concurrent assignment writes. Measure realistic mixed read/write traffic with production-like volumes before selecting a database or claiming throughput.
- Add query-duration histograms and page-size instrumentation in production. Re-profile when adding filters, geospatial joins, customer-safe field projection, or multi-hub tenancy.
