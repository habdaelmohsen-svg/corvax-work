from __future__ import annotations

import json
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CORVAX — The Core Business Platform"
    app_version: str = "1.0.0-agreement-completion-rc27.4-r9.4"
    environment: str = "development"
    database_url: str = "sqlite:///./data/corvax.db"

    # Legacy secret remains for password-independent development derivations only.
    # Access tokens use asymmetric JWT keys in RC11.
    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    jwt_algorithm: str = "RS256"
    jwt_active_kid: str = "dev-rs256-2026-01"
    jwt_private_key_path: str | None = None
    jwt_private_key_pem: str | None = None
    jwt_public_keys_json: str = "{}"

    # Application-level envelope encryption key ring. JSON maps kid -> base64 key.
    field_encryption_active_kid: str = "dev-field-2026-01"
    field_encryption_keys_json: str = "{}"

    seed_demo_data: bool = False
    # H17 first-run bootstrap: creates the base structure and the first
    # administrator when the users table is empty. Safe in production because
    # it is idempotent and the credentials must be changed at first sign-in.
    bootstrap_first_admin: bool = True
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin"
    # Recovery door: when true, the administrator password is reset on every
    # start. Intended to unlock a locked-out owner. Turn it off afterwards.
    bootstrap_force_admin_reset: bool = False
    # Destructive reset is explicitly enabled only for UAT/testing. The full
    # reset additionally requires SUPER_ADMIN, confirmation, backup acknowledgement
    # and a fresh signed preview. Production validation always rejects this flag.
    allow_data_reset: bool = False
    auto_create_schema: bool = True
    allowed_origins: str = "*"
    trusted_hosts: str = "*"
    force_https: bool = False
    docs_enabled: bool = True

    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    password_min_length: int = 12
    password_history_count: int = 5
    mfa_issuer: str = "CORVAX Business Platform"
    enforce_sensitive_role_mfa: bool = False
    sensitive_role_codes: str = "SUPER_ADMIN,CFO,FINANCIAL_CONTROLLER,PRODUCTION_MANAGER,HR_MANAGER"

    rate_limit_enabled: bool = True
    enable_rate_limit_testing: bool = False
    rate_limit_login_per_minute: int = 5
    rate_limit_refresh_per_minute: int = 10
    rate_limit_mrp_per_minute: int = 1
    rate_limit_write_per_minute: int = 300
    rate_limit_read_per_minute: int = 100

    backup_dir: str = "./data/backups"
    log_level: str = "INFO"
    json_logging: bool = True
    metrics_enabled: bool = True
    # Shared secret for /metrics (audit H-09). Required in production.
    metrics_token: str = ""
    sentry_dsn: str | None = None
    otel_exporter_otlp_endpoint: str | None = None

    # MRP executes through a durable database queue in production. Inline mode is
    # retained only for development/tests and is rejected by the production validator.
    mrp_inline_execution: bool = True
    payroll_strict_workflow: bool = False

    # Outbound DGTERA/Odoo connector.  The allow-list is mandatory protection
    # against turning a configurable integration URL into an SSRF primitive.
    dgtera_allowed_hosts: str = "cheesehouse.dgtera.com"
    dgtera_request_timeout_seconds: int = 30
    dgtera_max_orders_per_sync: int = 10000
    dgtera_max_order_lines_per_sync: int = 100000
    dgtera_max_payments_per_sync: int = 50000
    dgtera_scheduler_enabled: bool = True
    dgtera_scheduler_poll_seconds: int = 60
    # Historical imports are intentionally drained in small, independently
    # committed business-day units.  A web process must remain responsive
    # while the 2025 backfill is running on a modest PostgreSQL instance.
    dgtera_history_days_per_cycle: int = 8
    # Historical corrections are deliberately serialized.  An Odoo write-date
    # scan can surface thousands of old orders at once; only one already
    # imported business day is rechecked after the initial backfill completes.
    dgtera_changed_days_per_cycle: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def hosts(self) -> list[str]:
        if self.trusted_hosts.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def backup_path(self) -> Path:
        path = Path(self.backup_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def sensitive_roles(self) -> set[str]:
        return {code.strip().upper() for code in self.sensitive_role_codes.split(",") if code.strip()}

    @property
    def dgtera_hosts(self) -> tuple[str, ...]:
        return tuple(host.strip().lower() for host in self.dgtera_allowed_hosts.split(",") if host.strip())

    @property
    def jwt_public_keys(self) -> dict[str, str]:
        try:
            value = json.loads(self.jwt_public_keys_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("JWT_PUBLIC_KEYS_JSON must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("JWT_PUBLIC_KEYS_JSON must be an object mapping kid to PEM")
        return {str(k): str(v).replace("\\n", "\n") for k, v in value.items()}

    @property
    def field_encryption_keys(self) -> dict[str, str]:
        try:
            value = json.loads(self.field_encryption_keys_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("FIELD_ENCRYPTION_KEYS_JSON must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("FIELD_ENCRYPTION_KEYS_JSON must be an object mapping kid to base64 key")
        return {str(k): str(v) for k, v in value.items()}

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.environment.lower() == "production":
            if self.secret_key == "dev-only-change-me" or len(self.secret_key) < 32:  # nosec B105
                raise ValueError("Production SECRET_KEY must be changed and contain at least 32 characters")
            if self.allowed_origins.strip() == "*":
                raise ValueError("Production ALLOWED_ORIGINS cannot be wildcard")
            if self.trusted_hosts.strip() == "*":
                raise ValueError("Production TRUSTED_HOSTS cannot be wildcard")
            if self.seed_demo_data:
                raise ValueError("Production SEED_DEMO_DATA must be false")
            if self.allow_data_reset:
                raise ValueError("Production ALLOW_DATA_RESET must be false")
            if self.auto_create_schema:
                raise ValueError("Production AUTO_CREATE_SCHEMA must be false; use Alembic migrations only")
            if self.jwt_algorithm != "RS256":
                raise ValueError("Production JWT_ALGORITHM must be RS256")
            if not (self.jwt_private_key_path or self.jwt_private_key_pem):
                raise ValueError("Production JWT private key is required")
            if self.jwt_active_kid not in self.jwt_public_keys:
                raise ValueError("JWT_ACTIVE_KID must exist in JWT_PUBLIC_KEYS_JSON")
            if self.field_encryption_active_kid not in self.field_encryption_keys:
                raise ValueError("FIELD_ENCRYPTION_ACTIVE_KID must exist in FIELD_ENCRYPTION_KEYS_JSON")
            if not self.enforce_sensitive_role_mfa:
                raise ValueError("Production ENFORCE_SENSITIVE_ROLE_MFA must be true")
            if self.access_token_minutes > 60:
                raise ValueError("Production ACCESS_TOKEN_MINUTES cannot exceed 60")
            if self.mrp_inline_execution:
                raise ValueError("Production MRP_INLINE_EXECUTION must be false; run the durable MRP worker")
            if not self.payroll_strict_workflow:
                raise ValueError("Production PAYROLL_STRICT_WORKFLOW must be true")
        return self


settings = Settings()
