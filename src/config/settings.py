"""Application configuration and environment settings."""

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram Bot Configuration
    telegram_bot_token: str = Field(
        ...,
        description="Telegram bot token from @BotFather",
    )

    # OpenAI API
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key for Whisper and GPT-4 Vision",
    )

    # Anthropic API
    anthropic_api_key: str = Field(
        ...,
        description="Anthropic API key for Claude Vision",
    )

    # Splitwise API
    splitwise_consumer_key: str | None = Field(
        default=None,
        description="Splitwise consumer key",
    )
    splitwise_consumer_secret: str | None = Field(
        default=None,
        description="Splitwise consumer secret",
    )

    # Tricount API
    tricount_api_key: str | None = Field(
        default=None,
        description="Tricount API key",
    )

    # Database
    database_url: str = Field(
        default="sqlite:///cheqmate.db",
        description="Database connection URL",
    )

    # Application Settings
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # Phoenix Tracing (Observability)
    phoenix_enabled: bool = Field(
        default=True,
        description="Enable Phoenix tracing for LLM observability",
    )
    phoenix_collector_endpoint: str = Field(
        default="http://localhost:4317",
        description="Phoenix OTLP gRPC collector endpoint",
    )


# Global settings instance
settings = Settings()
