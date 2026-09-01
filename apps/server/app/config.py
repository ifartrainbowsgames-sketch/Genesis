from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Genesis"
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    web_origin: str = "http://localhost:3000"
    workspace_root: str = "./workspace"
    workspace_allowed_roots: str = ""

    database_url: str = "postgresql+asyncpg://genesis:genesis@localhost:5432/genesis"

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:8b"
    ollama_embed_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    github_token: str | None = None
    github_api_url: str = "https://api.github.com"

    # JSON array of explicitly trusted Streamable HTTP MCP endpoints.
    # Example: [{"name":"local-tools","url":"http://127.0.0.1:9000/mcp","enabled":true}]
    mcp_servers_json: str = "[]"

    # External workers are server-side allowlisted only. Command workers use fixed argv
    # and shell=False; HTTP workers use explicitly configured endpoints.
    # Example: [{"name":"claude-acp","type":"command","argv":["claude","--print"],"enabled":true}]
    external_workers_json: str = "[]"
    external_worker_timeout_seconds: int = 300
    external_worker_max_output_bytes: int = 200_000

    # Durable local schedules. Intervals below 60 seconds are rejected.
    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = 15

    # Source-tracked research broker. The bundled Docker service listens on 8080.
    searxng_url: str | None = "http://127.0.0.1:8080"
    research_timeout_seconds: float = 20.0
    research_max_results: int = 12

    # Optional fully local speech-to-text using a dedicated whisper.cpp CLI binary.
    whisper_cpp_binary: str | None = None
    whisper_cpp_model: str | None = None
    voice_timeout_seconds: float = 120.0
    voice_max_audio_bytes: int = 25_000_000

    approval_ttl_seconds: int = 600
    max_file_write_bytes: int = 1_000_000

    # Cognitive-memory consolidation and bounded prompt evolution.
    memory_consolidation_max_records: int = 200
    evolution_max_variants: int = 3
    evolution_max_cases: int = 10

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env", "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def workspace_path(self) -> Path:
        path = Path(self.workspace_root).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
