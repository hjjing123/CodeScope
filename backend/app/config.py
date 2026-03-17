from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DATABASE_ENV_FILE = Path(__file__).resolve().parents[1] / "config" / "database.env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODESCOPE_",
        extra="ignore",
        env_file=_DATABASE_ENV_FILE,
        env_file_encoding="utf-8",
    )

    api_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+psycopg://codescope:codescope@127.0.0.1:5432/codescope"
    )

    jwt_secret: str = "codescope-dev-jwt-secret-change-me-2026"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    storage_root: str = "./storage"
    import_workspace_root: str = "./storage/workspaces/imports"
    snapshot_storage_root: str = "./storage/snapshots"
    scan_workspace_root: str = "./storage/workspaces/scans"

    import_upload_max_bytes: int = 500 * 1024 * 1024
    import_archive_max_entries: int = 50_000
    import_archive_max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    import_archive_max_depth: int = 20
    git_command_timeout_seconds: int = 120

    version_file_preview_max_bytes: int = 512 * 1024
    version_file_preview_max_lines: int = 2000

    scan_engine_mode: str = "stub"
    scan_dispatch_backend: str = "celery"
    scan_dispatch_fallback_to_sync: bool = True
    ai_dispatch_backend: str = "celery"
    ai_dispatch_fallback_to_sync: bool = True
    ai_default_max_context_tokens: int = 32768
    ai_reserved_output_tokens: int = 6144
    ai_reserved_system_tokens: int = 2048
    ai_context_safety_margin_tokens: int = 1024
    ai_assessment_max_flow_steps: int = 7
    scan_log_root: str = "./storage/job-logs"
    import_log_root: str = "./storage/import-logs"
    selftest_log_root: str = "./storage/selftest-logs"
    ai_log_root: str = "./storage/ai-logs"
    task_log_storage_backend: str = "minio"
    task_log_object_prefix: str = "logs/tasks"
    task_log_minio_endpoint: str = ""
    task_log_minio_access_key: str = ""
    task_log_minio_secret_key: str = ""
    task_log_minio_bucket: str = "codescope-task-logs"
    task_log_minio_secure: bool = False
    task_log_minio_region: str = ""
    task_log_minio_auto_create_bucket: bool = True

    scan_external_runner_workdir: str = ""
    scan_external_reports_dir: str = (
        "./storage/workspaces/scans/{job_id}/external/reports"
    )
    scan_external_runtime_profile: str = "wsl"
    scan_external_container_compat_mode: bool = False

    scan_external_runner_command: str = ""
    scan_external_timeout_seconds: int = 3600
    scan_external_joern_home: str = "/opt/joern"
    scan_external_joern_bin: str = "/opt/joern/joern"
    scan_external_joern_export_script: str = "./assets/scan/joern/export_java_min.sc"
    scan_external_joern_enable_calls_default: bool = False
    scan_external_joern_enable_ref_default: bool = True

    scan_external_stage_joern_command: str = "builtin:joern"
    scan_external_stage_import_command: str = "builtin:neo4j_import"
    scan_external_stage_post_labels_command: str = "builtin:post_labels"
    scan_external_stage_source_semantic_command: str = "builtin:source_semantic"
    scan_external_stage_rules_command: str = "builtin:rules"

    scan_external_stage_joern_timeout_seconds: int = 3600
    scan_external_stage_import_timeout_seconds: int = 3600
    scan_external_stage_post_labels_timeout_seconds: int = 1800
    scan_external_stage_source_semantic_timeout_seconds: int = 900
    scan_external_stage_rules_timeout_seconds: int = 3600

    scan_external_post_labels_cypher: str = "./assets/scan/query/post_labels.cypher"
    scan_external_rules_dir: str = "./assets/scan/rules"
    scan_external_rule_sets_dir: str = "./assets/scan/rule_sets"
    scan_external_rules_max_count: int = 0
    scan_external_rules_failure_mode: str = "permissive"

    scan_external_neo4j_uri: str = "bolt://127.0.0.1:7687"
    scan_external_neo4j_user: str = "neo4j"
    scan_external_neo4j_password: str = ""
    scan_external_neo4j_database: str = "neo4j"
    scan_external_neo4j_cleanup_enabled: bool = False
    scan_external_neo4j_connect_retry: int = 15
    scan_external_neo4j_connect_wait_seconds: int = 2

    scan_external_import_docker_image: str = "neo4j:5.26"
    scan_external_import_data_mount: str = "/var/lib/neo4j/data"
    scan_external_import_csv_host_path: str = ""
    scan_external_import_database: str = "neo4j"
    scan_external_import_id_type: str = "string"
    scan_external_import_array_delimiter: str = "\\001"
    scan_external_import_clean_db: bool = False
    scan_external_import_multiline_fields: bool = True
    scan_external_import_multiline_fields_format: str = ""
    scan_external_import_preflight: bool = True
    scan_external_import_preflight_check_docker: bool = True
    scan_external_cleanup_host_path_allowlist: str = "./storage/workspaces/scans"

    scan_external_neo4j_runtime_restart_mode: str = "docker_ephemeral"
    scan_external_neo4j_runtime_container_name: str = "codescope_neo4j_{job_id}"
    scan_external_neo4j_runtime_network: str = ""
    scan_external_neo4j_runtime_network_alias: str = ""
    scan_external_neo4j_runtime_network_auto_create: bool = False
    scan_external_neo4j_runtime_restart_wait_seconds: int = 10
    scan_external_runtime_max_slots: int = 2
    scan_external_runtime_slot_wait_seconds: int = 1
    scan_external_runtime_slot_timeout_seconds: int = 3600

    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    celery_result_backend: str = "redis://127.0.0.1:6379/1"
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = True

    runtime_http_log_sample_rate: float = 0.05
    runtime_http_log_slow_threshold_ms: int = 1200
    runtime_http_log_record_success: bool = False

    ai_default_timeout_seconds: int = 60
    ai_default_temperature: float = 0.1
    ai_chat_history_limit: int = 12
    ai_system_ollama_auto_configure: bool = True
    ai_system_ollama_display_name: str = "System Ollama"
    ai_system_ollama_base_url: str = "http://127.0.0.1:11434"
    ai_system_ollama_default_model: str = ""

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        required_hmac_bytes = {
            "HS256": 32,
            "HS384": 48,
            "HS512": 64,
        }.get(self.jwt_algorithm.upper())
        if required_hmac_bytes is not None:
            actual_bytes = len(self.jwt_secret.encode("utf-8"))
            if actual_bytes < required_hmac_bytes:
                raise ValueError(
                    "jwt_secret is too short for the configured HMAC algorithm; "
                    f"expected at least {required_hmac_bytes} bytes"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
