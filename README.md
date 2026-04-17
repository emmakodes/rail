# Simple Todo

Minimal monorepo with:

- `apps/api`: FastAPI backend
- `apps/web`: Next.js frontend
- `docker-compose.yml`: local PostgreSQL + API + web stack

The backend exposes only two product endpoints:

- `GET /todos`
- `POST /todos`
- `GET /health`
- `GET /metrics`

Todos are stored in PostgreSQL.

## Local Docker run

```bash
docker compose up --build
```

Default local URLs:

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`

## API run

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Web run

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

## Railway deploy shape

Create three Railway services:

- PostgreSQL
- API from `apps/api`
- Web from `apps/web`

Useful env vars:

- API: `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`, `TODO_READ_DELAY_SECONDS`, `TODO_CACHE_TTL_SECONDS`, `TODO_UPSTREAM_URL`, `TODO_UPSTREAM_TIMEOUT_SECONDS`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`
- API: `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`, `TODO_READ_DELAY_SECONDS`, `TODO_CACHE_TTL_SECONDS`, `TODO_CACHE_TTL_JITTER_SECONDS`, `TODO_CACHE_LOCK_TIMEOUT_SECONDS`, `TODO_CACHE_LOCK_WAIT_TIMEOUT_SECONDS`, `TODO_CACHE_LOCK_POLL_SECONDS`, `TODO_CACHE_REBUILD_DELAY_SECONDS`, `TODO_UPSTREAM_URL`, `TODO_UPSTREAM_TIMEOUT_SECONDS`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`
- Web: `NEXT_PUBLIC_API_BASE_URL`

Recommended Railway values:

- `DATABASE_URL`: use Railway Postgres `DATABASE_URL`
- `REDIS_URL`: use Railway Redis `REDIS_URL` if you add Redis
- `CORS_ORIGINS`: `https://<your-web-domain>`
- `TODO_READ_DELAY_SECONDS`: `0` normally, `2` for the latency drill
- `TODO_CACHE_TTL_SECONDS`: `30`
- `TODO_CACHE_TTL_JITTER_SECONDS`: `0` normally, `5` for jittered expiry
- `TODO_CACHE_LOCK_TIMEOUT_SECONDS`: `5`
- `TODO_CACHE_LOCK_WAIT_TIMEOUT_SECONDS`: `6`
- `TODO_CACHE_LOCK_POLL_SECONDS`: `0.05`
- `TODO_CACHE_REBUILD_DELAY_SECONDS`: `0` normally, `1` for cache stampede drills
- `TODO_UPSTREAM_URL`: optional slow dependency for timeout drills
- `TODO_UPSTREAM_TIMEOUT_SECONDS`: `3`
- `DB_POOL_SIZE`: `5` normally, `3` for the pool exhaustion drill
- `DB_MAX_OVERFLOW`: `10` normally, `0` for the pool exhaustion drill
- `DB_POOL_TIMEOUT_SECONDS`: `30` normally, `1` to surface pool timeout quickly
- `NEXT_PUBLIC_API_BASE_URL`: `https://<your-api-domain>`

Railway config files:

- `apps/api/railway.json`
- `apps/web/railway.json`

## Observability baseline

The API now includes:

- structured JSON logs
- `x-request-id` response header
- Prometheus metrics at `GET /metrics`

Useful first checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

## Production Battlefield Scenario 01

Symptom:

- `GET /todos` slows to multiple seconds under concurrent load

Injection:

- set `TODO_READ_DELAY_SECONDS=2` on the API service
- redeploy the API
- run:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> load-tests/todos-read-latency.js
```

What to observe:

- Railway logs will show `event=latency_injection`
- `/metrics` will show `todo_http_request_duration_seconds` moving into higher buckets for `/todos`
- browser requests will feel slow even though CPU may look normal

## Scenario 01 Fix Direction

The first fix path is now implemented:

- `GET /todos` checks Redis cache first
- `POST /todos` invalidates the todo list cache
- optional upstream calls can be protected with a timeout
- `uvicorn.access` can now inherit the request ID because the middleware no longer resets it before access logging

Recommended fix-mode settings:

```text
TODO_READ_DELAY_SECONDS=0
TODO_CACHE_TTL_SECONDS=30
```

## Production Battlefield Scenario 02

Symptom:

- search is fast on a tiny table, then crawls once the table grows large

Injection:

1. Seed 100k todos:

```bash
cd apps/api
PYTHONPATH=. python scripts/seed_todos.py --count 100000
```

2. Trigger the bad query shape:

```bash
curl "http://localhost:8000/todos?search=work&search_mode=contains&limit=50&offset=0"
```

3. Inspect the plan:

```bash
curl "http://localhost:8000/todos/explain?search=work&search_mode=contains&limit=50&offset=0"
```

4. Load test it:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e SEARCH=work -e SEARCH_MODE=contains -e LIMIT=50 load-tests/todos-search-fullscan.js
```

What to look for:

- `Seq Scan`, `Bitmap Index Scan`, or wide filtering in `EXPLAIN ANALYZE`
- large `Rows Removed by Filter`
- higher DB CPU and slower `/todos` search requests

Senior fix direction:

- avoid `%term%` when you can
- for exact search, use `search_mode=exact` plus an index on `title`
- if you really need contains-search, use `pg_trgm` with a GIN index

Scenario 02 fix now applied:

- `/todos` is paginated with `limit` and `offset`
- default `limit=50`, max `limit=100`
- startup creates:
  - `ix_todos_title`
  - `pg_trgm` extension
  - `ix_todos_title_trgm`

## Production Battlefield Scenario 03

Symptom:

- `GET /todos` looks fine with plain todos, then becomes slow when each todo causes its own follow-up tag query

Injection:

1. Seed tags for 200 todos:

```bash
cd apps/api
PYTHONPATH=. python scripts/seed_todo_tags.py --limit 200 --tags-per-todo 4
```

2. Trigger the N+1 path:

```bash
curl -i "http://localhost:8000/todos?include_tags=true&tag_load_strategy=n_plus_one&limit=200&offset=0"
```

3. Look at the response headers:

- `x-db-queries`

4. Load test it:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e TAG_LOAD_STRATEGY=n_plus_one -e LIMIT=200 load-tests/todos-n-plus-one.js
```

What to observe:

- `x-db-queries` climbs toward `1 + N`
- latency increases even if each single query is individually fast
- logs show `include_tags=true` and `tag_load_strategy=n_plus_one`

Fix direction:

- use `tag_load_strategy=selectin`
- compare `x-db-queries` before and after
- this is the concrete proof that eager loading fixed the N+1 pattern

## Production Battlefield Scenario 04

Symptom:

- `GET /todos` returns huge payloads and the frontend freezes when pagination is removed

Injection:

1. Trigger the unbounded response path:

```bash
curl -i "http://localhost:8000/todos?disable_pagination=true"
```

2. Observe:

- `x-response-bytes`
- response body size
- Railway logs for `response_bytes`

3. Load test the bad version:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e DISABLE_PAGINATION=true load-tests/todos-response-bloat.js
```

4. Compare with paginated version:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e DISABLE_PAGINATION=false -e LIMIT=50 load-tests/todos-response-bloat.js
```

5. Compare cursor pagination:

```bash
curl "http://localhost:8000/todos/cursor?limit=20"
```

What to observe:

- `x-response-bytes` explodes when pagination is disabled
- backend latency may look acceptable while payload size and client experience become terrible
- cursor pagination keeps payload size flat and avoids deep offset scanning

Fix direction:

- keep pagination on by default
- use cursor pagination for feed-like scrolling
- track response size as a first-class signal, not only latency

## Production Battlefield Scenario 05

Symptom:

- requests fail with `Cannot acquire connection from pool` even though PostgreSQL itself is mostly idle

Injection:

1. Set a tiny pool on the API service:

```text
DB_POOL_SIZE=3
DB_MAX_OVERFLOW=0
DB_POOL_TIMEOUT_SECONDS=1
```

2. Redeploy the API.

3. Check pool status:

```bash
curl "http://localhost:8000/pool/status"
```

4. Run the connection-hold path with concurrent load:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e HOLD_SECONDS=5 -e VUS=10 -e DURATION=20s load-tests/todos-pool-exhaustion.js
```

5. Inspect pool and database activity:

```bash
curl "http://localhost:8000/pool/status"
curl "http://localhost:8000/pool/pg-stat-activity"
```

What to observe:

- only 3 requests can hold DB connections at once
- extra requests start failing with `503` and `Cannot acquire connection from pool`
- `/pool/status` shows the pool as fully checked out
- `pg_stat_activity` shows a small number of sessions occupied, not a busy database

What this drill teaches:

- pool exhaustion is about connection availability, not necessarily database CPU
- a request can exhaust the pool simply by holding a connection too long
- the fix is usually:
  - always close sessions with `finally`
  - keep external I/O outside the DB connection window
  - size and timeout the pool deliberately

Fix comparison:

1. Hit the fixed path once:

```bash
curl "http://localhost:8000/pool/exhaust-fixed?wait_seconds=5"
```

2. Run the same 10-user load against the fixed path:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e PATH=/pool/exhaust-fixed -e HOLD_SECONDS=5 -e VUS=10 -e DURATION=20s load-tests/todos-pool-exhaustion.js
```

What should change:

- the requests still take about 5 seconds overall
- but they should stop failing from pool exhaustion
- `/pool/status` should no longer stay pinned at all connections checked out
- this proves the issue was connection hold time, not just total request time

## Production Battlefield Scenario 06

Symptom:

- one slow async endpoint causes unrelated fast endpoints to become slow too

Injection:

1. Hit the intentionally broken async endpoint:

```bash
curl "http://localhost:8000/loop/blocking?block_seconds=1"
```

This endpoint is declared `async`, but it uses `time.sleep(1)`, which blocks the event loop.

2. Compare with the fast endpoint:

```bash
curl "http://localhost:8000/loop/fast"
```

3. Run the mixed load test:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e BLOCKING_PATH=/loop/blocking -e BLOCK_SECONDS=1 -e BLOCKING_VUS=5 -e FAST_VUS=5 -e DURATION=20s load-tests/todos-event-loop-blocking.js
```

What to observe:

- `GET /loop/fast` slows down even though it contains no blocking work
- Railway logs show `event=event_loop_lag`
- `/metrics` will show latency moving up on both endpoints, not just the blocking one

Fix direction:

- move blocking sync work off the event loop
- use `run_in_executor` for truly sync work that has no async equivalent

Fixed comparison:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e BLOCKING_PATH=/loop/blocking-fixed -e BLOCK_SECONDS=1 -e BLOCKING_VUS=5 -e FAST_VUS=5 -e DURATION=20s load-tests/todos-event-loop-blocking.js
```

What should change:

- the blocking endpoint still takes about 1 second
- but `GET /loop/fast` should stay much faster
- event loop lag warnings should drop sharply

## Production Battlefield Scenario 07

Symptom:

- after a cache wipe or Redis restart, many requests miss at once and all hammer the database

Injection:

1. Set API env vars:

```text
TODO_CACHE_TTL_SECONDS=10
TODO_CACHE_TTL_JITTER_SECONDS=0
TODO_CACHE_REBUILD_DELAY_SECONDS=1
```

2. Prime and inspect the cache:

```bash
curl "http://localhost:8000/todos?cache_strategy=plain"
curl "http://localhost:8000/cache/todos/status"
```

3. Simulate the Redis restart / hot-key wipe:

```bash
curl "http://localhost:8000/cache/todos/reset"
```

4. Hammer the hot key:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e CACHE_STRATEGY=plain -e VUS=200 -e DURATION=5s load-tests/todos-cache-stampede.js
```

What to observe:

- many requests show `x-cache-status: miss`
- latency jumps because every request rebuilds the same key
- logs show many `cache_status=miss` lines clustered together

Fix direction:

- `jitter`: use randomized TTLs so expiries do not line up in normal operation
- `lock`: allow only one request to rebuild the hot key while others wait for the cache to be filled

Hot-key fix comparison:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e CACHE_STRATEGY=lock -e VUS=200 -e DURATION=5s load-tests/todos-cache-stampede.js
```

What should change:

- only one request should rebuild the cache
- the others should show `x-cache-status: lock_wait_hit` or `lock_wait`
- latency and DB pressure should drop sharply compared with `plain`

Jitter baseline:

- set `TODO_CACHE_TTL_JITTER_SECONDS=5`
- use `cache_strategy=jitter`
- this does not fix a full Redis restart on a single hot key, but it prevents synchronized TTL expiries during normal operation

## Production Battlefield Scenario 08

Symptom:

- RAM climbs steadily until the process is restarted or OOM-killed

Injection:

1. Reset the in-process memory drill state:

```bash
curl -X POST "http://localhost:8000/memory/reset"
```

2. Inspect baseline memory:

```bash
curl "http://localhost:8000/memory/status"
curl "http://localhost:8000/memory/diff"
```

3. Hammer the leaky path:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e PATH=/memory/leak -e VUS=20 -e DURATION=20s -e PAYLOAD_SIZE=50000 load-tests/todos-memory-leak.js
```

4. Inspect memory again:

```bash
curl "http://localhost:8000/memory/status"
curl "http://localhost:8000/memory/diff"
```

What to observe:

- `rss_mb` keeps growing
- `leaky_items` keeps growing
- `/memory/diff` points at the leaking line in `main.py`

Bounded comparison:

```bash
k6 run -e API_BASE_URL=https://<your-api-domain> -e PATH=/memory/bounded -e VUS=20 -e DURATION=20s -e PAYLOAD_SIZE=50000 load-tests/todos-memory-leak.js
```

What should change:

- `bounded_items` plateaus at its max size
- `rss_mb` grows much more slowly or stabilizes

What this drill teaches:

- a module-level mutable collection written from a request path is a leak unless it is bounded
- RSS is the production signal Railway actually OOMs on
- `tracemalloc` tells you which line is retaining memory
