"""
Configuration management for code-daily.

Loads GitHub credentials from environment variables.
"""

import os
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")


def validate_config():
    """Validate that required configuration is present."""
    missing = []

    if not GITHUB_TOKEN or GITHUB_TOKEN == "your_token_here":
        missing.append("GITHUB_TOKEN")

    if not GITHUB_USERNAME or GITHUB_USERNAME == "your_username_here":
        missing.append("GITHUB_USERNAME")

    if missing:
        raise ValueError(
            f"Missing required configuration: {', '.join(missing)}\n"
            "Please copy .env.example to .env and fill in your values.\n"
            "Get a GitHub token at: https://github.com/settings/tokens"
        )
