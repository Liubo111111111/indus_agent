from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

# 加载 .env 文件（项目根目录）
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path, override=False)


# ---------------------------------------------------------------------------
# LLM 配置
# ---------------------------------------------------------------------------

class LLMSettings(BaseModel):
    """从环境变量读取的 LLM 配置。"""
    model_config = ConfigDict(extra="forbid")

    api_key: str = ""
    base_url: str = ""
    model: str = "qwen3-max"
    timeout_sec: int = 30
    max_retry: int = 2


@lru_cache(maxsize=1)
def load_llm_settings() -> LLMSettings:
    api_key = (
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or ""
    )
    base_url = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("DASHSCOPE_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or ""
    )
    return LLMSettings(
        api_key=api_key,
        base_url=base_url,
        model=os.getenv("LLM_MODEL", "qwen3-max"),
        timeout_sec=int(os.getenv("LLM_TIMEOUT_SEC", "30")),
        max_retry=int(os.getenv("LLM_MAX_RETRY", "2")),
    )


# ---------------------------------------------------------------------------
# ODPS 配置
# ---------------------------------------------------------------------------

class ODPSSettings(BaseModel):
    """从环境变量读取的 ODPS (MaxCompute) 配置。"""
    model_config = ConfigDict(extra="forbid")

    access_key_id: str = ""
    access_key_secret: str = ""
    project: str = ""
    endpoint: str = ""


@lru_cache(maxsize=1)
def load_odps_settings() -> ODPSSettings:
    return ODPSSettings(
        access_key_id=os.getenv("ODPS_ACCESS_KEY_ID", ""),
        access_key_secret=os.getenv("ODPS_ACCESS_KEY_SECRET", ""),
        project=os.getenv("ODPS_PROJECT", ""),
        endpoint=os.getenv("ODPS_ENDPOINT", ""),
    )


class TaxonomyLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    short_description: str
    prompt_text: str
    enabled: bool = True


class TaxonomyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    labels: list[TaxonomyLabel] = Field(default_factory=list)


class PromptAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    system_prompt: str
    user_template: str


def _taxonomy_path() -> Path:
    return Path(__file__).with_name("taxonomy_config.yaml")


def _prompt_asset_path(node_name: str, version: str) -> Path:
    return Path(__file__).with_name("prompts") / f"{node_name}_{version}.yaml"


@lru_cache(maxsize=1)
def load_taxonomy() -> TaxonomyConfig:
    with _taxonomy_path().open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return TaxonomyConfig.model_validate(payload)


@lru_cache(maxsize=16)
def load_prompt_asset(node_name: str, version: str) -> PromptAsset:
    with _prompt_asset_path(node_name, version).open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return PromptAsset.model_validate(payload)
