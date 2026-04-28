import os


class Settings:
    app_name = "Simple Todo API"
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@db:5432/todos",
    )
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    todo_cache_ttl_seconds = int(os.getenv("TODO_CACHE_TTL_SECONDS", "30"))
    todo_cache_ttl_jitter_seconds = int(os.getenv("TODO_CACHE_TTL_JITTER_SECONDS", "0"))
    todo_cache_lock_timeout_seconds = float(os.getenv("TODO_CACHE_LOCK_TIMEOUT_SECONDS", "5"))
    todo_cache_lock_wait_timeout_seconds = float(os.getenv("TODO_CACHE_LOCK_WAIT_TIMEOUT_SECONDS", "6"))
    todo_cache_lock_poll_seconds = float(os.getenv("TODO_CACHE_LOCK_POLL_SECONDS", "0.05"))
    todo_cache_rebuild_delay_seconds = float(os.getenv("TODO_CACHE_REBUILD_DELAY_SECONDS", "0"))
    todo_create_rate_limit_per_minute = int(os.getenv("TODO_CREATE_RATE_LIMIT_PER_MINUTE", "0"))
    todo_read_delay_seconds = float(os.getenv("TODO_READ_DELAY_SECONDS", "0"))
    todo_upstream_url = os.getenv("TODO_UPSTREAM_URL", "")
    todo_upstream_timeout_seconds = float(os.getenv("TODO_UPSTREAM_TIMEOUT_SECONDS", "3"))
    external_hang_url = os.getenv("EXTERNAL_HANG_URL", "https://httpbin.org/delay/30")
    external_timeout_seconds = float(os.getenv("EXTERNAL_TIMEOUT_SECONDS", "3"))
    external_worker_limit = int(os.getenv("EXTERNAL_WORKER_LIMIT", "5"))
    retry_storm_attempts = int(os.getenv("RETRY_STORM_ATTEMPTS", "5"))
    retry_backoff_base_seconds = float(os.getenv("RETRY_BACKOFF_BASE_SECONDS", "0.2"))
    circuit_breaker_failure_threshold = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
    circuit_breaker_open_seconds = float(os.getenv("CIRCUIT_BREAKER_OPEN_SECONDS", "10"))
    migration_read_lock_timeout_seconds = float(os.getenv("MIGRATION_READ_LOCK_TIMEOUT_SECONDS", "1"))
    migration_dangerous_hold_seconds = float(os.getenv("MIGRATION_DANGEROUS_HOLD_SECONDS", "15"))
    migration_backfill_batch_size = int(os.getenv("MIGRATION_BACKFILL_BATCH_SIZE", "5000"))
    migration_backfill_pause_seconds = float(os.getenv("MIGRATION_BACKFILL_PAUSE_SECONDS", "0.05"))
    migration_lock_timeout_seconds = float(os.getenv("MIGRATION_LOCK_TIMEOUT_SECONDS", "5"))
    startup_warm_mode = os.getenv("STARTUP_WARM_MODE", "disabled")
    startup_warm_db_delay_seconds = float(os.getenv("STARTUP_WARM_DB_DELAY_SECONDS", "0"))
    startup_warm_query_limit = int(os.getenv("STARTUP_WARM_QUERY_LIMIT", "5000"))
    startup_warm_stagger_seconds = float(os.getenv("STARTUP_WARM_STAGGER_SECONDS", "0"))
    startup_warm_lock_timeout_seconds = float(os.getenv("STARTUP_WARM_LOCK_TIMEOUT_SECONDS", "30"))
    startup_warm_wait_timeout_seconds = float(os.getenv("STARTUP_WARM_WAIT_TIMEOUT_SECONDS", "45"))
    startup_warm_poll_seconds = float(os.getenv("STARTUP_WARM_POLL_SECONDS", "0.2"))
    railway_replicas = int(os.getenv("RAILWAY_REPLICAS", "1"))
    db_connection_budget = int(os.getenv("DB_CONNECTION_BUDGET", "25"))
    auto_tune_db_pool_for_replicas = os.getenv("AUTO_TUNE_DB_POOL_FOR_REPLICAS", "false").lower() == "true"
    db_pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    db_pool_timeout_seconds = float(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))
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

    @property
    def effective_db_pool_size(self) -> int:
        if not self.auto_tune_db_pool_for_replicas:
            return self.db_pool_size
        per_replica_budget = max(1, self.db_connection_budget // max(1, self.railway_replicas))
        return max(1, min(self.db_pool_size, per_replica_budget))

    @property
    def effective_db_max_overflow(self) -> int:
        if not self.auto_tune_db_pool_for_replicas:
            return self.db_max_overflow
        return 0


settings = Settings()
