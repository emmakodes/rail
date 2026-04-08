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

- API: `DATABASE_URL`, `CORS_ORIGINS`, `TODO_READ_DELAY_SECONDS`
- Web: `NEXT_PUBLIC_API_BASE_URL`

Recommended Railway values:

- `DATABASE_URL`: use Railway Postgres `DATABASE_URL`
- `CORS_ORIGINS`: `https://<your-web-domain>`
- `TODO_READ_DELAY_SECONDS`: `0` normally, `2` for the latency drill
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
