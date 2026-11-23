 # settings + env vars
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    gemini_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./sentinelai.db"
    postgres_url:   str = "postgresql+asyncpg://sentinel:sentinel_dev_pass@localhost:5432/sentinelai"

    environment: str = "development"

    # Master admin key — always valid, bypasses per-key rate limiting.
    # Used to bootstrap the system and to authenticate /v1/keys management endpoints.
    # Per-tenant keys (see app/services/api_keys.py) are the normal auth path for /v1/chat.
    api_key: str = "sentinel-dev-key-123"

    # Performance / profiling toggles
    # - PRELOAD_EMBEDDING_MODEL=true  => load the embedding model, NER model
    #                                    and classifiers at process start
    # - LOG_STAGE_TIMINGS=true        => print per-stage timings in /v1/chat
    preload_embedding_model: bool = False
    log_stage_timings: bool = False

    # ── Redis ──────────────────────────────────────────────────────────
    # Backs the Celery broker/result backend, the API key lookup cache,
    # and per-key rate limiting.
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── API key management ────────────────────────────────────────────
    api_key_cache_ttl_seconds: int = 60
    default_rate_limit_per_minute: int = 100

    # ── Circuit breaker webhook ────────────────────────────────────────
    # WEBHOOK_URL unset => webhook delivery is a no-op (checked before every send).
    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_timeout_seconds: float = 5.0

    # ── Health checks ─────────────────────────────────────────────────
    health_db_timeout_seconds: float = 2.0
    health_redis_timeout_seconds: float = 1.0
    celery_queue_depth_degraded_threshold: int = 50

    # ── CORS ───────────────────────────────────────────────────────────
    # Comma-separated list of origins allowed to call the API from a
    # browser. Defaults to local dev; set to the deployed dashboard's
    # origin(s) in production — never "*" while allow_credentials=True.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── LLM provider endpoints ─────────────────────────────────────────
    # Overridable so load testing (see backend/tests/mock_provider.py) can
    # point the gateway at a local mock instead of the real APIs.
    groq_base_url: str = "https://api.groq.com/openai/v1"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # ── Guardrails (see services/guardrails.py) ────────────────────────
    # Prompt-injection detection: blocks requests the classifier trained in
    # ml/train_injection.py flags. INJECTION_THRESHOLD (a probability)
    # overrides the threshold stored in the artifact.
    injection_detection_enabled: bool = True
    injection_threshold: float | None = None

    # PII redaction before anything leaves the gateway. en_core_web_lg
    # caught every name in our checks where en_core_web_sm missed several;
    # en_core_web_md is a lighter middle ground for small machines.
    redaction_enabled: bool = True
    redaction_ner_model: str = "en_core_web_lg"
    # Comma-separated names never redacted (public figures, product names,
    # NER false positives). Matching is exact and case-insensitive.
    redaction_allowed_names: str = ""

    # Model routing: the classifier from ml/train_router.py sends prompts
    # it scores as hard to the large model, the rest to the small one.
    # A request that names a model explicitly is never re-routed.
    # ROUTER_THRESHOLD (a probability) trades cost against quality: lower
    # sends more traffic to the large model.
    routing_enabled: bool = True
    router_threshold: float | None = None
    groq_small_model: str = "openai/gpt-oss-20b"
    groq_large_model: str = "openai/gpt-oss-120b"
    gemini_small_model: str = "gemini-2.5-flash-lite"
    gemini_large_model: str = "gemini-2.5-flash"

    # ── Logging ────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # env_ignore_empty: "INJECTION_THRESHOLD=" in .env means "use the
    # default", not "parse an empty string as a float" (which fails at
    # startup). Same meaning as before for the empty string/None settings
    # (WEBHOOK_URL=, WEBHOOK_SECRET=), whose defaults are already empty.
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    @property
    def redaction_allowed_names_list(self) -> list[str]:
        return [n.strip() for n in self.redaction_allowed_names.split(",") if n.strip()]

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

settings = Settings()
