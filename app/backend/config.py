"""
Configuration for the Poker POC.

Environment Variables:
- OPENAI_BASE_URL: API endpoint (required for Azure, optional for OpenAI)
- OPENAI_API_KEY: API key
- OPENAI_MODEL: Model name / deployment name
- ENDPOINT_TYPE: "azure" or "openai" (default: auto-detect)
- AZURE_OPENAI_API_VERSION: API version for Azure (default: 2025-03-01-preview)
- REASONING_EFFORT: Optional (low, medium, high)
- TEMPERATURE: Generation temperature (default: 0.7)
"""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core OpenAI settings (used for both OpenAI and Azure)
    openai_base_url: str = ""  # Required for Azure, optional for OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"  # Model name (OpenAI) or deployment name (Azure)

    # Endpoint type: "azure", "openai", or "" (auto-detect)
    endpoint_type: str = ""

    # Azure-specific (only used when endpoint_type=azure)
    azure_openai_api_version: str = "2025-03-01-preview"

    # Model parameters
    reasoning_effort: str = ""  # low, medium, high
    temperature: float = 0.7

    # Tournament defaults
    default_starting_stack: int = 1500
    default_small_blind: int = 10
    default_big_blind: int = 20

    # Logging
    log_level: str = "INFO"

    # Knowledge persistence
    knowledge_persistence_dir: str = "data/knowledge"
    
    # Game state persistence (for statistics recalculation)
    gamestates_dir: str = "data/gamestates"

    @property
    def model_name(self) -> str:
        """Get the model/deployment name."""
        return self.openai_model

    @property
    def is_azure(self) -> bool:
        """Check if using Azure OpenAI."""
        if self.endpoint_type.lower() == "azure":
            return True
        if self.endpoint_type.lower() == "openai":
            return False
        # Auto-detect from URL
        return "azure" in self.openai_base_url.lower() if self.openai_base_url else False

    def configure_openai_client(self) -> None:
        """
        Configure the OpenAI client based on settings.
        Call this at startup before creating agents.
        """
        from openai import AsyncOpenAI
        from agents import set_default_openai_client

        if self.is_azure:
            # Azure OpenAI
            from openai import AsyncAzureOpenAI
            client = AsyncAzureOpenAI(
                azure_endpoint=self.openai_base_url,
                api_key=self.openai_api_key,
                api_version=self.azure_openai_api_version,
            )
            set_default_openai_client(client, use_for_tracing=False)
        elif self.openai_base_url:
            # Custom endpoint (with base URL)
            client = AsyncOpenAI(
                base_url=self.openai_base_url,
                api_key=self.openai_api_key,
            )
            set_default_openai_client(client, use_for_tracing=False)
        else:
            # Default OpenAI - just set env vars, SDK handles it
            if self.openai_api_key:
                os.environ["OPENAI_API_KEY"] = self.openai_api_key

        # Disable tracing for non-OpenAI endpoints
        if self.is_azure or self.openai_base_url:
            os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
