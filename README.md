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

- API: `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`, `TODO_READ_DELAY_SECONDS`, `TODO_CACHE_TTL_SECONDS`, `TODO_UPSTREAM_URL`, `TODO_UPSTREAM_TIMEOUT_SECONDS`
- Web: `NEXT_PUBLIC_API_BASE_URL`

Recommended Railway values:

- `DATABASE_URL`: use Railway Postgres `DATABASE_URL`
- `REDIS_URL`: use Railway Redis `REDIS_URL` if you add Redis
- `CORS_ORIGINS`: `https://<your-web-domain>`
- `TODO_READ_DELAY_SECONDS`: `0` normally, `2` for the latency drill
- `TODO_CACHE_TTL_SECONDS`: `30`
- `TODO_UPSTREAM_URL`: optional slow dependency for timeout drills
- `TODO_UPSTREAM_TIMEOUT_SECONDS`: `3`
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
