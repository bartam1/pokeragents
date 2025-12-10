"""
Pytest configuration and shared fixtures for agent scenario tests.
"""
import os

import pytest

from backend.config import Settings
from backend.logging_config import setup_logging

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Configure pytest settings."""
    # Set up logging based on LOG_LEVEL env var
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(log_level)


@pytest.fixture(scope="session")
def settings() -> Settings:
    """
    Load settings from environment.

    Requires OPENAI_API_KEY to be set (either in .env or environment).
    Skips tests if API key is not available.
    """
    try:
        s = Settings()
        if not s.openai_api_key:
            pytest.skip("OPENAI_API_KEY not set - skipping LLM tests")
        # Configure the OpenAI client
        s.configure_openai_client()
        return s
    except Exception as e:
        pytest.skip(f"Failed to load settings: {e}")


@pytest.fixture(scope="session")
def scenarios_dir() -> str:
    """Get the path to the scenarios directory."""
    return os.path.join(os.path.dirname(__file__), "agent_scenarios", "scenarios")
