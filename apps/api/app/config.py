import os


class Settings:
    app_name = "Simple Todo API"
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@db:5432/todos",
    )
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    todo_cache_ttl_seconds = int(os.getenv("TODO_CACHE_TTL_SECONDS", "30"))
    todo_read_delay_seconds = float(os.getenv("TODO_READ_DELAY_SECONDS", "0"))
    todo_upstream_url = os.getenv("TODO_UPSTREAM_URL", "")
    todo_upstream_timeout_seconds = float(os.getenv("TODO_UPSTREAM_TIMEOUT_SECONDS", "3"))
    cors_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def normalized_database_url(self) -> str:
        if self.database_url.startswith("postgresql+psycopg://"):
            return self.database_url
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        return self.database_url


settings = Settings()
