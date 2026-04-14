"""Runtime settings.

Owner: member 1.
Responsibility: centralized environment config.
Avoid placing retrieval/answer business logic here.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    enable_real_llm: bool


def get_settings() -> Settings:
    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        enable_real_llm=os.getenv("ENABLE_REAL_LLM", "false").lower() == "true",
    )
