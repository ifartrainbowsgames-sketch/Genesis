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

    approval_ttl_seconds: int = 600
    max_file_write_bytes: int = 1_000_000

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
