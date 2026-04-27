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
    failover_enabled: bool
    llm_temperature: float
    llm_top_p: float
    llm_max_tokens: int
    llm_frequency_penalty: float
    llm_top_k: int
    enable_kb_admin: bool
    web_access_primary: bool
    web_access_proxy_url: str
    web_access_timeout_s: float
    web_access_max_pages: int
    web_access_fallback_enabled: bool


def get_settings() -> Settings:
    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        enable_real_llm=os.getenv("ENABLE_REAL_LLM", "false").lower() == "true",
        failover_enabled=os.getenv("LLM_FAILOVER_ENABLED", "true").lower() == "true",
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        llm_top_p=float(os.getenv("LLM_TOP_P", "0.7")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
        llm_frequency_penalty=float(os.getenv("LLM_FREQUENCY_PENALTY", "1")),
        llm_top_k=int(os.getenv("LLM_TOP_K", "50")),
        enable_kb_admin=os.getenv("ENABLE_KB_ADMIN", "true").lower() == "true",
        web_access_primary=os.getenv("WEB_ACCESS_PRIMARY", "true").lower() == "true",
        web_access_proxy_url=os.getenv("WEB_ACCESS_PROXY_URL", "http://localhost:3456"),
        web_access_timeout_s=float(os.getenv("WEB_ACCESS_TIMEOUT_S", "14")),
        web_access_max_pages=int(os.getenv("WEB_ACCESS_MAX_PAGES", "3")),
        web_access_fallback_enabled=os.getenv("WEB_ACCESS_FALLBACK_ENABLED", "true").lower() == "true",
    )
